from __future__ import annotations

from datetime import date, timedelta

from .wiw_sync import WhenIWorkSynchronizer as BaseWhenIWorkSynchronizer


SCHEDULE_LOOKBACK_DAYS = 1
SCHEDULE_LOOKAHEAD_DAYS = 28
SCHEDULE_PAGE_LIMIT = 500
FULL_SCHEDULE_START = date(2000, 1, 1)
FULL_SCHEDULE_END = date(2100, 1, 1)


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
    """Preserve caller-provided bounded ranges while forcing every shift scope on.

    Complete reconciliation intentionally does not use the short rolling window
    above. The history fetcher splits the 2000..2100 range into safe bounded
    requests; this wrapper only guarantees that assigned shifts, OpenShifts and
    all locations are part of every one of those requests.
    """

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
    """Fetch and validate every API-visible WIW shift from old history to 2100.

    Wide WIW date requests are not trusted because the API can silently return
    an empty result for an excessively broad range. Reuse the bounded migration
    fetcher, which recursively splits windows and rejects capped/silent-empty
    responses. This makes the result suitable for a repair/reconciliation pass,
    not just a best-effort incremental refresh.
    """

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
    """Operational WIW synchronizer with a reliable future schedule window."""

    def __init__(self, client=None, triggered_by=None):
        super().__init__(client=client, triggered_by=triggered_by)
        self.client = _ScheduleWindowClient(self.client, self.now)
