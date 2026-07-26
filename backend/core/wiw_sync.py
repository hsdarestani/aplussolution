from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from .document_catalog import DOCUMENT_CATALOG
from .models import (
    Availability,
    ClientCompany,
    EmployeeMasterData,
    IntegrationSyncRun,
    Location,
    Position,
    Shift,
    TimeEntry,
    TimeOffRequest,
    User,
    WorkerProfile,
)
from .wiw import WhenIWorkClient, WhenIWorkError


MASTER_REQUIRED_FIELDS = sorted({
    item['name']
    for document in DOCUMENT_CATALOG
    for item in document.get('fields', [])
    if item.get('required') and item.get('source', '').startswith('master.')
})


def first(data, *keys, default=None):
    for key in keys:
        value = data.get(key)
        if value not in (None, ''):
            return value
    return default


def nested(data, *path, default=None):
    value = data
    for key in path:
        if not isinstance(value, dict):
            return default
        value = value.get(key)
    return default if value in (None, '') else value


def as_id(value):
    if isinstance(value, dict):
        value = value.get('id') or value.get('user_id') or value.get('location_id')
    return str(value) if value not in (None, '') else None


def as_decimal(value):
    if value in (None, ''):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def as_datetime(value):
    if not value:
        return None
    if isinstance(value, datetime):
        result = value
    else:
        result = parse_datetime(str(value))
    if not result:
        return None
    if timezone.is_naive(result):
        result = timezone.make_aware(result, timezone.get_current_timezone())
    return result


def as_date(value):
    if not value:
        return None
    if hasattr(value, 'year') and not isinstance(value, str):
        return value.date() if hasattr(value, 'date') else value
    parsed = parse_date(str(value))
    if parsed:
        return parsed
    dt = as_datetime(value)
    return dt.date() if dt else None


def synthetic_email(wiw_id):
    return f'wiw-{wiw_id}@sync.invalid'


def employee_number(item, wiw_id):
    return str(first(item, 'employee_code', 'employee_number', 'id', default=f'WIW-{wiw_id}'))[:50]


def address_from(item):
    address = first(item, 'address', 'formatted_address')
    if isinstance(address, dict):
        return ', '.join(str(part) for part in [address.get('street'), address.get('city'), address.get('state'), address.get('zip')] if part)
    return str(address or '')


def calculate_completeness(data):
    if not MASTER_REQUIRED_FIELDS:
        return 100, []
    missing = [name for name in MASTER_REQUIRED_FIELDS if data.get(name) in (None, '', [], {})]
    completeness = round(100 * (len(MASTER_REQUIRED_FIELDS) - len(missing)) / len(MASTER_REQUIRED_FIELDS))
    return completeness, missing


class WhenIWorkSynchronizer:
    def __init__(self, client=None, triggered_by=None):
        self.client = client or WhenIWorkClient()
        self.triggered_by = triggered_by
        self.now = timezone.now()
        self.counts = defaultdict(int)
        self.errors = []
        self.workers = {}
        self.locations = {}
        self.positions = {}
        self.shifts = {}

    @transaction.atomic
    def sync(self, mode='incremental'):
        run = IntegrationSyncRun.objects.create(
            provider='wiw',
            mode=mode,
            status=IntegrationSyncRun.Status.RUNNING,
            triggered_by=self.triggered_by,
        )
        try:
            params = {}
            if mode == 'incremental':
                last = IntegrationSyncRun.objects.filter(
                    provider='wiw', status__in=[IntegrationSyncRun.Status.SUCCESS, IntegrationSyncRun.Status.PARTIAL]
                ).exclude(pk=run.pk).order_by('-finished_at').first()
                if last and last.finished_at:
                    params['updated_since'] = last.finished_at.isoformat()
            self.sync_users(self.client.collection('users', params=params).items)
            self.sync_positions(self.client.collection('positions', params=params, optional=True).items)
            self.sync_locations(self.client.collection('locations', params=params, optional=True).items)
            self.sync_sites(self.client.collection('sites', params=params, optional=True).items)
            self.sync_shifts(self.client.collection('shifts', params=params).items)
            self.sync_times(self.client.collection('times', params=params, optional=True).items)
            self.sync_availabilities(self.client.collection('availabilities', params=params, optional=True).items)
            self.sync_requests(self.client.collection('requests', params=params, optional=True).items)
            run.status = IntegrationSyncRun.Status.PARTIAL if self.errors else IntegrationSyncRun.Status.SUCCESS
        except Exception as exc:
            self.errors.append({'resource': 'sync', 'error': str(exc)})
            run.status = IntegrationSyncRun.Status.FAILED
        run.finished_at = timezone.now()
        run.counts = dict(self.counts)
        run.errors = self.errors
        run.save(update_fields=['status', 'finished_at', 'counts', 'errors', 'updated_at'])
        if run.status == IntegrationSyncRun.Status.FAILED:
            raise WhenIWorkError(self.errors[-1]['error'])
        return run

    def sync_users(self, items):
        for item in items:
            try:
                wiw_id = as_id(first(item, 'id', 'user_id'))
                if not wiw_id:
                    continue
                email = str(first(item, 'email', 'login', default=synthetic_email(wiw_id))).strip().lower()
                first_name = str(first(item, 'first_name', 'firstname', default='')).strip()
                last_name = str(first(item, 'last_name', 'lastname', default='')).strip()
                full_name = str(first(item, 'name', 'full_name', default='')).strip()
                if full_name and not (first_name or last_name):
                    parts = full_name.split(maxsplit=1)
                    first_name = parts[0]
                    last_name = parts[1] if len(parts) > 1 else ''
                user = User.objects.filter(wiw_id=wiw_id).first() or User.objects.filter(email=email).first()
                created = not bool(user)
                if not user:
                    user = User(email=email, username=email, role=User.Role.WORKER)
                    user.set_unusable_password()
                user.email = email
                user.username = email
                user.first_name = first_name
                user.last_name = last_name
                user.phone = str(first(item, 'phone', 'mobile_phone', default='')).strip()
                user.wiw_id = wiw_id
                user.wiw_payload = item
                user.wiw_synced_at = self.now
                user.role = User.Role.WORKER
                user.is_onboarded = True
                user.is_active = not bool(first(item, 'deleted', 'is_deleted', default=False)) and bool(first(item, 'active', default=True))
                user.save()
                defaults = {
                    'employee_number': employee_number(item, wiw_id),
                    'employment_type': WorkerProfile.EmploymentType.MINI,
                    'tariff_hourly_rate': as_decimal(first(item, 'hourly_rate', 'pay_rate', 'rate')),
                    'active': user.is_active,
                    'wiw_user_id': wiw_id,
                    'wiw_payload': item,
                    'wiw_synced_at': self.now,
                }
                worker, worker_created = WorkerProfile.objects.update_or_create(user=user, defaults=defaults)
                self.workers[wiw_id] = worker
                master, _ = EmployeeMasterData.objects.get_or_create(worker=worker)
                data = dict(master.data or {})
                source_map = dict(master.source_map or {})
                wiw_data = {
                    'first_name': first_name,
                    'last_name': last_name,
                    'email': email if not email.endswith('@sync.invalid') else '',
                    'phone': user.phone,
                    'street': first(item, 'address', 'address1', default='') if not isinstance(first(item, 'address'), dict) else nested(item, 'address', 'street', default=''),
                    'postal_code': first(item, 'zip', 'postal_code', default='') or nested(item, 'address', 'zip', default=''),
                    'city': first(item, 'city', default='') or nested(item, 'address', 'city', default=''),
                    'employee_number': worker.employee_number,
                    'employment_type': worker.employment_type,
                    'tariff_hourly_rate': str(worker.tariff_hourly_rate or ''),
                }
                for key, value in wiw_data.items():
                    if value not in (None, ''):
                        data[key] = value
                        source_map[key] = 'wiw'
                data['full_address'] = ' '.join(str(x) for x in [data.get('street'), data.get('postal_code'), data.get('city')] if x).strip()
                completeness, missing = calculate_completeness(data)
                master.data = data
                master.source_map = source_map
                master.completeness = completeness
                master.missing_fields = missing
                master.save()
                self.counts['users_created' if created else 'users_updated'] += 1
                self.counts['workers_created' if worker_created else 'workers_updated'] += 1
            except Exception as exc:
                self.errors.append({'resource': 'users', 'id': item.get('id'), 'error': str(exc)})

    def sync_positions(self, items):
        for item in items:
            try:
                wiw_id = as_id(first(item, 'id', 'position_id'))
                if not wiw_id:
                    continue
                name = str(first(item, 'name', 'label', default=f'WIW Position {wiw_id}')).strip()
                obj = Position.objects.filter(wiw_position_id=wiw_id).first() or Position.objects.filter(name=name).first()
                created = not bool(obj)
                if not obj:
                    obj = Position(name=name)
                obj.name = name
                obj.color = str(first(item, 'color', default=obj.color or '#2457E6'))
                obj.active = bool(first(item, 'active', default=True))
                obj.wiw_position_id = wiw_id
                obj.wiw_payload = item
                obj.wiw_synced_at = self.now
                obj.save()
                self.positions[wiw_id] = obj
                self.counts['positions_created' if created else 'positions_updated'] += 1
            except Exception as exc:
                self.errors.append({'resource': 'positions', 'id': item.get('id'), 'error': str(exc)})

    def _client_for_location(self, item, wiw_id):
        company = first(item, 'company', 'client', 'account')
        if isinstance(company, dict):
            name = str(first(company, 'name', default=f'WIW Kunde {wiw_id}'))
            external = as_id(first(company, 'id', default=wiw_id))
        else:
            name = str(first(item, 'client_name', 'company_name', default=first(item, 'name', default=f'WIW Kunde {wiw_id}')))
            external = as_id(first(item, 'client_id', 'company_id', default=wiw_id))
        number = f'WIW-{external}'[:50]
        client, _ = ClientCompany.objects.get_or_create(customer_number=number, defaults={'name': name, 'address': address_from(item)})
        if not client.name or client.name.startswith('WIW Kunde'):
            client.name = name
        if address_from(item):
            client.address = address_from(item)
        client.save()
        return client

    def sync_locations(self, items):
        for item in items:
            try:
                wiw_id = as_id(first(item, 'id', 'location_id'))
                if not wiw_id:
                    continue
                client = self._client_for_location(item, wiw_id)
                name = str(first(item, 'name', 'label', default=f'WIW Standort {wiw_id}')).strip()
                obj = Location.objects.filter(wiw_location_id=wiw_id).first()
                created = not bool(obj)
                if not obj:
                    obj = Location(client=client, name=name, address=address_from(item) or name)
                obj.client = client
                obj.name = name
                obj.address = address_from(item) or obj.address or name
                obj.latitude = as_decimal(first(item, 'latitude', 'lat'))
                obj.longitude = as_decimal(first(item, 'longitude', 'lng', 'lon'))
                obj.timezone = str(first(item, 'timezone', default='Europe/Berlin'))
                obj.active = bool(first(item, 'active', default=True))
                obj.wiw_location_id = wiw_id
                obj.wiw_payload = item
                obj.wiw_synced_at = self.now
                obj.save()
                self.locations[wiw_id] = obj
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
                parent = self.locations.get(parent_id) or Location.objects.filter(wiw_location_id=parent_id).first()
                if not parent:
                    client = self._client_for_location(item, site_id)
                else:
                    client = parent.client
                name = str(first(item, 'name', 'label', default=f'WIW Einsatzort {site_id}'))
                obj = Location.objects.filter(wiw_site_id=site_id).first()
                created = not bool(obj)
                if not obj:
                    obj = Location(client=client, name=name, address=address_from(item) or (parent.address if parent else name))
                obj.client = client
                obj.name = name
                obj.address = address_from(item) or obj.address or (parent.address if parent else name)
                obj.latitude = as_decimal(first(item, 'latitude', 'lat')) or (parent.latitude if parent else None)
                obj.longitude = as_decimal(first(item, 'longitude', 'lng', 'lon')) or (parent.longitude if parent else None)
                obj.wiw_site_id = site_id
                obj.wiw_payload = item
                obj.wiw_synced_at = self.now
                obj.save()
                self.locations[f'site:{site_id}'] = obj
                self.counts['sites_created' if created else 'sites_updated'] += 1
            except Exception as exc:
                self.errors.append({'resource': 'sites', 'id': item.get('id'), 'error': str(exc)})

    def sync_shifts(self, items):
        default_position, _ = Position.objects.get_or_create(name='WIW Einsatz')
        for item in items:
            try:
                wiw_id = as_id(first(item, 'id', 'shift_id'))
                if not wiw_id:
                    continue
                user_id = as_id(first(item, 'user_id', 'user'))
                location_id = as_id(first(item, 'location_id', 'location'))
                site_id = as_id(first(item, 'site_id', 'site'))
                position_id = as_id(first(item, 'position_id', 'position'))
                worker = self.workers.get(user_id) or WorkerProfile.objects.filter(wiw_user_id=user_id).first()
                location = self.locations.get(f'site:{site_id}') or self.locations.get(location_id)
                location = location or Location.objects.filter(wiw_site_id=site_id).first() or Location.objects.filter(wiw_location_id=location_id).first()
                if not location:
                    client = self._client_for_location(item, location_id or wiw_id)
                    location = Location.objects.create(client=client, name='WIW Einsatzort', address=client.address or 'Aus WIW importiert')
                position = self.positions.get(position_id) or Position.objects.filter(wiw_position_id=position_id).first() or default_position
                starts_at = as_datetime(first(item, 'start_time', 'start', 'starts_at'))
                ends_at = as_datetime(first(item, 'end_time', 'end', 'ends_at'))
                if not starts_at or not ends_at:
                    raise ValueError('Shift start/end missing')
                obj = Shift.objects.filter(wiw_shift_id=wiw_id).first()
                created = not bool(obj)
                if not obj:
                    obj = Shift(client=location.client, location=location, position=position, starts_at=starts_at, ends_at=ends_at)
                obj.client = location.client
                obj.location = location
                obj.position = position
                obj.worker = worker
                obj.starts_at = starts_at
                obj.ends_at = ends_at
                obj.break_minutes = int(first(item, 'break_minutes', 'break', default=0) or 0)
                published = bool(first(item, 'published', default=True))
                obj.status = Shift.Status.CONFIRMED if worker else (Shift.Status.PUBLISHED if published else Shift.Status.DRAFT)
                obj.is_open = not bool(worker)
                obj.notes = str(first(item, 'notes', 'description', default=''))
                obj.wiw_shift_id = wiw_id
                obj.wiw_payload = item
                obj.wiw_synced_at = self.now
                obj.save()
                self.shifts[wiw_id] = obj
                self.counts['shifts_created' if created else 'shifts_updated'] += 1
            except Exception as exc:
                self.errors.append({'resource': 'shifts', 'id': item.get('id'), 'error': str(exc)})

    def sync_times(self, items):
        for item in items:
            try:
                wiw_id = as_id(first(item, 'id', 'time_id'))
                user_id = as_id(first(item, 'user_id', 'user'))
                if not wiw_id or not user_id:
                    continue
                worker = self.workers.get(user_id) or WorkerProfile.objects.filter(wiw_user_id=user_id).first()
                if not worker:
                    continue
                shift_id = as_id(first(item, 'shift_id', 'shift'))
                shift = self.shifts.get(shift_id) or Shift.objects.filter(wiw_shift_id=shift_id).first()
                clock_in = as_datetime(first(item, 'start_time', 'clock_in', 'start'))
                if not clock_in:
                    continue
                obj = TimeEntry.objects.filter(wiw_time_id=wiw_id).first()
                created = not bool(obj)
                if not obj:
                    obj = TimeEntry(worker=worker, clock_in=clock_in)
                obj.worker = worker
                obj.shift = shift
                obj.clock_in = clock_in
                obj.clock_out = as_datetime(first(item, 'end_time', 'clock_out', 'end'))
                obj.approved = bool(first(item, 'approved', 'is_approved', default=False))
                obj.edit_reason = str(first(item, 'notes', 'reason', default=''))
                obj.wiw_time_id = wiw_id
                obj.wiw_payload = item
                obj.wiw_synced_at = self.now
                obj.save()
                self.counts['times_created' if created else 'times_updated'] += 1
            except Exception as exc:
                self.errors.append({'resource': 'times', 'id': item.get('id'), 'error': str(exc)})

    def sync_availabilities(self, items):
        for item in items:
            try:
                user_id = as_id(first(item, 'user_id', 'user'))
                worker = self.workers.get(user_id) or WorkerProfile.objects.filter(wiw_user_id=user_id).first()
                start = as_datetime(first(item, 'start_time', 'start', 'starts_at'))
                end = as_datetime(first(item, 'end_time', 'end', 'ends_at'))
                if not worker or not start or not end:
                    continue
                available = bool(first(item, 'available', 'is_available', default=True))
                _, created = Availability.objects.update_or_create(
                    worker=worker, starts_at=start, ends_at=end,
                    defaults={'available': available, 'note': str(first(item, 'notes', 'reason', default='WIW'))[:250]},
                )
                self.counts['availabilities_created' if created else 'availabilities_updated'] += 1
            except Exception as exc:
                self.errors.append({'resource': 'availabilities', 'id': item.get('id'), 'error': str(exc)})

    def sync_requests(self, items):
        for item in items:
            try:
                user_id = as_id(first(item, 'user_id', 'user'))
                worker = self.workers.get(user_id) or WorkerProfile.objects.filter(wiw_user_id=user_id).first()
                start = as_date(first(item, 'start_date', 'start_time', 'start'))
                end = as_date(first(item, 'end_date', 'end_time', 'end'))
                if not worker or not start or not end:
                    continue
                raw_status = str(first(item, 'status', default='pending')).lower()
                status = {
                    'approved': TimeOffRequest.Status.APPROVED,
                    'accepted': TimeOffRequest.Status.APPROVED,
                    'denied': TimeOffRequest.Status.REJECTED,
                    'rejected': TimeOffRequest.Status.REJECTED,
                }.get(raw_status, TimeOffRequest.Status.PENDING)
                _, created = TimeOffRequest.objects.update_or_create(
                    worker=worker, starts_on=start, ends_on=end,
                    defaults={'status': status, 'reason': str(first(item, 'notes', 'reason', 'type', default='WIW'))},
                )
                self.counts['requests_created' if created else 'requests_updated'] += 1
            except Exception as exc:
                self.errors.append({'resource': 'requests', 'id': item.get('id'), 'error': str(exc)})
