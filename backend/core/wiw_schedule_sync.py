from __future__ import annotations

from datetime import date, timedelta

from .models import Location
from .wiw_directory import (
    ACTIVE_CLIENT_NAMES,
    cache_location_aliases,
    canonical_client_name,
    canonical_martha_location_name,
    clean_display_name,
    find_location_by_external,
    get_canonical_client,
    merge_wiw_payload,
)
from .wiw_sync import (
    WhenIWorkSynchronizer as BaseWhenIWorkSynchronizer,
    address_from,
    as_decimal,
    as_id,
    first,
)


SCHEDULE_LOOKBACK_DAYS = 1
SCHEDULE_LOOKAHEAD_DAYS = 28
SCHEDULE_PAGE_LIMIT = 500
FULL_SCHEDULE_START = date(2000, 1, 1)
FULL_SCHEDULE_END = date(2100, 1, 1)
WIW_UNASSIGNED_USER_ID = '0'


class _ScheduleWindowClient:
    """Keep normal incremental WIW sync, but always refresh the future schedule.

    WIW's plain /shifts response is intentionally short-lived and does not
    include OpenShifts. That is fine for generic incremental resources, but it
    means a shift already created for next week can be visible in the live
    mobile WIW overlay while never reaching the local Shift table used by PDF
    reports. For the shifts resource only, use an explicit rolling window and
    include OpenShifts. Do not carry updated_since into this request: a future
    shift may have been created before the previous incremental run and still
    needs to be backfilled when it enters the schedule horizon.
    """

    def __init__(self, client, now):
        self._client = client
        self._now = now

    def collection(self, name, params=None, optional=False):
        if name != 'shifts':
            return self._client.collection(name, params=params, optional=optional)

        shift_params = dict(params or {})
        shift_params.pop('updated_since', None)
        shift_params.update({
            'start': (self._now - timedelta(days=SCHEDULE_LOOKBACK_DAYS)).isoformat(),
            'end': (self._now + timedelta(days=SCHEDULE_LOOKAHEAD_DAYS)).isoformat(),
            'include_open': 'true',
            'include_allopen': 'true',
            'all_locations': 'true',
            'limit': SCHEDULE_PAGE_LIMIT,
        })
        return self._client.collection(name, params=shift_params, optional=optional)


class _CompleteScheduleClient:
    """Preserve caller-provided bounded ranges while forcing every shift scope on."""

    def __init__(self, client):
        self._client = client

    def collection(self, name, params=None, optional=False):
        request_params = dict(params or {})
        if name == 'shifts':
            request_params.update({
                'include_open': 'true',
                'include_allopen': 'true',
                'all_locations': 'true',
            })
        return self._client.collection(name, params=request_params, optional=optional)


def fetch_complete_schedule_snapshot(client):
    """Fetch and validate every API-visible WIW shift from old history to 2100."""

    from .wiw_migration import _assert_dynamic_probe_is_in_snapshot, _fetch_dynamic_range

    complete_client = _CompleteScheduleClient(client)
    rows = _fetch_dynamic_range(
        complete_client,
        'shifts',
        FULL_SCHEDULE_START,
        FULL_SCHEDULE_END,
    )
    _assert_dynamic_probe_is_in_snapshot(complete_client, 'shifts', rows)
    return rows


class WhenIWorkSynchronizer(BaseWhenIWorkSynchronizer):
    """Operational WIW synchronizer with A+ as the canonical directory.

    WIW remains the source for schedule changes and raw metadata, but customer
    grouping, local display names and location ownership are business-owned in
    A+. Multiple historical/current WIW location or site ids may therefore point
    at the same canonical A+ Location through aliases stored in ``wiw_payload``.
    """

    def __init__(self, client=None, triggered_by=None):
        super().__init__(client=client, triggered_by=triggered_by)
        self.client = _ScheduleWindowClient(self.client, self.now)
        self.location_clients: dict[str, object] = {}
        # Critical for incremental runs: a shift can change while its WIW
        # location does not, so the locations endpoint may omit that dependency.
        cache_location_aliases(self.locations)

    @staticmethod
    def _wiw_user_id(item):
        return as_id(first(item, 'user_id', 'user'))

    @classmethod
    def _without_unassigned_users(cls, items):
        """Drop WIW's user-id 0 sentinel from worker-owned resources.

        WIW uses user id 0 for an unassigned/OpenShift card. It is not a real
        employee and must never become ``wiw-0@sync.invalid`` in A+.
        """
        return [item for item in items if cls._wiw_user_id(item) != WIW_UNASSIGNED_USER_ID]

    def sync_users(self, items):
        rows = []
        for item in items:
            wiw_id = as_id(first(item, 'id', 'user_id'))
            if wiw_id == WIW_UNASSIGNED_USER_ID:
                continue
            rows.append(item)
        super().sync_users(rows)
        self.workers.pop(WIW_UNASSIGNED_USER_ID, None)

    def sync_times(self, items):
        super().sync_times(self._without_unassigned_users(items))

    def sync_availabilities(self, items):
        super().sync_availabilities(self._without_unassigned_users(items))

    def sync_requests(self, items):
        super().sync_requests(self._without_unassigned_users(items))

    @staticmethod
    def _raw_location_name(item, fallback=''):
        return str(first(item, 'name', 'label', default=fallback) or fallback).strip()

    @staticmethod
    def _raw_client_name(item):
        company = first(item, 'company', 'client', 'account')
        if isinstance(company, dict):
            return str(first(company, 'name', default='') or '').strip()
        return str(first(item, 'client_name', 'company_name', default='') or '').strip()

    def _canonical_for_item(self, item):
        location_name = self._raw_location_name(item)
        if canonical_martha_location_name(location_name):
            return 'Martha'
        return canonical_client_name(self._raw_client_name(item)) or canonical_client_name(location_name)

    def _client_for_location(self, item, wiw_id):
        canonical = self._canonical_for_item(item)
        if canonical in ACTIVE_CLIENT_NAMES:
            return get_canonical_client(canonical)

        # Unknown WIW customers are retained for audit/history but never become
        # operational customers merely because a sync happened.
        client = super()._client_for_location(item, wiw_id)
        if client.active:
            client.active = False
            client.save(update_fields=['active', 'updated_at'])
        return client

    def _canonical_location_for_client(self, client, raw_name, *, create=True):
        if not client:
            return None
        canonical_client = canonical_client_name(client.name)
        if canonical_client == 'Martha':
            canonical_location = canonical_martha_location_name(raw_name)
            if not canonical_location:
                return None
            location = Location.objects.filter(
                client=client,
                name=canonical_location,
                active=True,
            ).first()
            if not location and create:
                location = Location.objects.create(
                    client=client,
                    name=canonical_location,
                    address=canonical_location,
                    active=True,
                )
            return location

        if canonical_client in ACTIVE_CLIENT_NAMES:
            location = Location.objects.filter(client=client, active=True).order_by('created_at').first()
            if not location:
                location = Location.objects.filter(client=client).order_by('created_at').first()
            if not location and create:
                display = clean_display_name(raw_name) or canonical_client
                location = Location.objects.create(
                    client=client,
                    name=display,
                    address=display,
                    active=True,
                )
            return location
        return None

    def _update_location_from_wiw(self, location, item, *, location_id=None, site_id=None):
        raw_address = address_from(item)
        if raw_address and not location.address:
            location.address = raw_address
        latitude = as_decimal(first(item, 'latitude', 'lat'))
        longitude = as_decimal(first(item, 'longitude', 'lng', 'lon'))
        if latitude is not None:
            location.latitude = latitude
        if longitude is not None:
            location.longitude = longitude
        incoming_timezone = str(first(item, 'timezone', default='') or '').strip()
        if incoming_timezone:
            location.timezone = incoming_timezone
        location.wiw_payload = merge_wiw_payload(
            location,
            item,
            location_ids=[location_id] if location_id else [],
            site_ids=[site_id] if site_id else [],
        )
        location.wiw_synced_at = self.now
        fields = ['address', 'latitude', 'longitude', 'timezone', 'wiw_payload', 'wiw_synced_at', 'updated_at']
        if location_id and not location.wiw_location_id:
            location.wiw_location_id = str(location_id)
            fields.append('wiw_location_id')
        if site_id and not location.wiw_site_id:
            location.wiw_site_id = str(site_id)
            fields.append('wiw_site_id')
        location.save(update_fields=list(dict.fromkeys(fields)))

    def sync_locations(self, items):
        for item in items:
            try:
                wiw_id = as_id(first(item, 'id', 'location_id'))
                if not wiw_id:
                    continue
                raw_name = self._raw_location_name(item, f'WIW Standort {wiw_id}')
                # Inactive unknown rows are deliberately retained. Reuse them so
                # the same external id can never create a fresh duplicate later.
                obj = find_location_by_external('location', wiw_id, active_only=False)
                created = False

                if not obj:
                    client = self._client_for_location(item, wiw_id)
                    obj = self._canonical_location_for_client(client, raw_name)
                    if not obj:
                        # Martha may expose a grouping/root location in addition
                        # to its three actual sites. Keep such a row non-active so
                        # it cannot become a fourth operational Martha location.
                        obj = Location.objects.create(
                            client=client,
                            name=clean_display_name(raw_name) or f'WIW Standort {wiw_id}',
                            address=address_from(item) or raw_name or 'Aus WIW importiert',
                            active=False,
                        )
                        created = True
                    self._update_location_from_wiw(obj, item, location_id=wiw_id)
                else:
                    # Local name/client/active state are authoritative. Only safe
                    # remote metadata is refreshed.
                    self._update_location_from_wiw(obj, item, location_id=wiw_id)

                self.locations[wiw_id] = obj
                if obj.client_id:
                    self.location_clients[wiw_id] = obj.client
                self.counts['locations_created' if created else 'locations_updated'] += 1
            except Exception as exc:
                self.errors.append({'resource': 'locations', 'id': item.get('id'), 'error': str(exc)})

    def sync_sites(self, items):
        for item in items:
            try:
                site_id = as_id(first(item, 'id', 'site_id'))
                parent_id = as_id(first(item, 'location_id', 'location'))
                if not site_id:
                    continue

                raw_name = self._raw_location_name(item, f'WIW Einsatzort {site_id}')
                obj = find_location_by_external('site', site_id, active_only=False)
                created = False
                parent = self.locations.get(parent_id) or find_location_by_external(
                    'location', parent_id, active_only=False
                )

                if not obj:
                    client = parent.client if parent and parent.client_id else self.location_clients.get(parent_id)
                    if not client:
                        client = self._client_for_location(item, site_id)

                    # A Martha site name can select one of the three canonical
                    # locations even when WIW's parent is a generic Martha row.
                    obj = self._canonical_location_for_client(client, raw_name)
                    if not obj and parent and parent.active:
                        obj = parent
                    if not obj:
                        obj = Location.objects.create(
                            client=client,
                            name=clean_display_name(raw_name) or f'WIW Einsatzort {site_id}',
                            address=address_from(item) or (parent.address if parent else raw_name) or 'Aus WIW importiert',
                            active=False,
                        )
                        created = True
                    self._update_location_from_wiw(obj, item, site_id=site_id)
                else:
                    self._update_location_from_wiw(obj, item, site_id=site_id)

                self.locations[f'site:{site_id}'] = obj
                self.counts['sites_created' if created else 'sites_updated'] += 1
            except Exception as exc:
                self.errors.append({'resource': 'sites', 'id': item.get('id'), 'error': str(exc)})

    def sync_shifts(self, items):
        rows = []
        for original in items:
            item = dict(original)
            if self._wiw_user_id(item) == WIW_UNASSIGNED_USER_ID:
                # Normalize WIW's user 0 sentinel before the base importer sees
                # it. The existing shift then becomes a normal open assignment.
                item['user_id'] = None
                item['user'] = None
            rows.append(item)

        # Repair dependency lookup before the base importer runs. This prevents
        # its emergency fallback from creating another operational customer or
        # location when WIW only returned a changed shift in an incremental run.
        for item in rows:
            location_id = as_id(first(item, 'location_id', 'location'))
            site_id = as_id(first(item, 'site_id', 'site'))
            if site_id and f'site:{site_id}' not in self.locations:
                mapped = find_location_by_external('site', site_id, active_only=False)
                if mapped:
                    self.locations[f'site:{site_id}'] = mapped
            if location_id and location_id not in self.locations:
                mapped = find_location_by_external('location', location_id, active_only=False)
                if mapped:
                    self.locations[location_id] = mapped

            # If WIW sends a shift before its dependency metadata, create one
            # non-operational placeholder instead of letting the base fallback
            # create an active duplicate. The next location/site sync will reuse
            # this external id and enrich the same row.
            if location_id and location_id not in self.locations:
                client = self._client_for_location(item, location_id)
                placeholder = Location.objects.create(
                    client=client,
                    name='WIW Einsatzort',
                    address=client.address or 'Aus WIW importiert',
                    active=False,
                )
                self._update_location_from_wiw(placeholder, item, location_id=location_id)
                self.locations[location_id] = placeholder
        super().sync_shifts(rows)
