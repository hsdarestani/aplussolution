from __future__ import annotations

from datetime import datetime, timedelta

from dateutil.parser import parse as parse_flexible_datetime
from django.conf import settings
from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from . import admin_center_views as admin_base
from .models import IntegrationSyncRun, Location, Position, Shift, ShiftSwapRequest, TimeOffRequest, User
from .premium_approval_models import ShiftPickupRequest
from .shift_slots import ShiftSlot
from .wiw import WhenIWorkClient, WhenIWorkError


CACHE_KEY = 'wiw:admin-home-snapshot:v2'
CACHE_SECONDS = 60
MANAGER_ROLES = {User.Role.ADMIN, User.Role.MANAGER}
WIW_DASHBOARD_FUTURE_DAYS = 370
WIW_PAGE_LIMIT = 200


def _value(item, *keys, default=None):
    for key in keys:
        value = item.get(key)
        if value not in (None, ''):
            return value
    return default


def _as_datetime(value):
    if value in (None, ''):
        return None
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, (int, float)) or str(value).strip().isdigit():
        try:
            result = datetime.fromtimestamp(float(value), tz=timezone.get_current_timezone())
        except (OverflowError, OSError, TypeError, ValueError):
            return None
    else:
        raw = str(value).strip()
        try:
            result = datetime.fromisoformat(raw.replace('Z', '+00:00'))
        except (TypeError, ValueError):
            try:
                result = parse_flexible_datetime(raw)
            except (OverflowError, TypeError, ValueError):
                return None
    if timezone.is_naive(result):
        result = timezone.make_aware(result, timezone.get_current_timezone())
    return result


def _as_bool(value, default=False):
    if value in (None, ''):
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() not in {'0', 'false', 'no', 'off', 'none', 'null'}


def _pending(item):
    # All three WIW request APIs use numeric status 0 for Pending. Older
    # payloads and local fixtures sometimes use text labels, so support both.
    status = _value(item, 'user_status', 'status', 'state', default='pending')
    if isinstance(status, (int, float)) or str(status).strip().lstrip('-').isdigit():
        try:
            return int(status) == 0
        except (TypeError, ValueError):
            pass
    return str(status or 'pending').strip().lower() not in {
        'approved', 'accepted', 'complete', 'completed', 'done',
        'denied', 'rejected', 'cancelled', 'canceled', 'deleted', 'expired',
    }


def _dedupe(items):
    result = []
    seen = set()
    for item in items:
        identifier = _value(item, 'id', 'request_id', 'swap_id', 'shift_id')
        key = str(identifier) if identifier not in (None, '') else repr(sorted(item.items()))
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _paged_get(client, path, collection_name, params, *, page_start=0, max_pages=25):
    rows = []
    page = page_start
    limit = int(params.get('limit') or WIW_PAGE_LIMIT)
    for _ in range(max_pages):
        payload = client.get(path, params={**params, 'page': page})
        batch = client.extract_collection(payload, collection_name)
        rows.extend(batch)
        if isinstance(payload, dict) and payload.get('more') is True:
            page += 1
            continue
        # OpenShift approval responses do not consistently expose `more`.
        # A short page is therefore the safe terminal condition.
        if len(batch) >= limit and batch:
            page += 1
            continue
        break
    return _dedupe(rows)


def _open_shift_instances(item):
    worker_id = _value(item, 'user_id', 'worker_id', 'user', 'worker')
    if isinstance(worker_id, dict):
        worker_id = worker_id.get('id') or worker_id.get('user_id')
    explicitly_open = _as_bool(_value(item, 'is_open', default=False))
    unassigned = worker_id in (None, '', 0, '0', False)
    if not (explicitly_open or unassigned):
        return 0
    if not _as_bool(_value(item, 'published', default=True), default=True):
        return 0
    status = str(_value(item, 'status', default='published') or 'published').strip().lower()
    if status in {'cancelled', 'canceled', 'deleted', 'draft'}:
        return 0
    try:
        return max(1, int(_value(item, 'instances', default=1) or 1))
    except (TypeError, ValueError):
        return 1


def _display_label(value, fallback=''):
    if isinstance(value, dict):
        return str(value.get('name') or value.get('label') or value.get('title') or fallback)
    return str(value or fallback)


def _live_open_shift_rows(items, now):
    candidates = []
    external_ids = []
    location_ids = set()
    site_ids = set()
    position_ids = set()

    for item in items:
        instances = _open_shift_instances(item)
        if not instances:
            continue
        starts_at = _as_datetime(_value(item, 'start_time', 'start', 'starts_at'))
        ends_at = _as_datetime(_value(item, 'end_time', 'end', 'ends_at'))
        if not starts_at or not ends_at or ends_at < now:
            continue
        external_id = str(_value(item, 'id', 'shift_id', default='') or '').strip()
        location_id = str(_value(item, 'location_id', default='') or '').strip()
        site_id = str(_value(item, 'site_id', default='') or '').strip()
        position_id = str(_value(item, 'position_id', default='') or '').strip()
        if external_id:
            external_ids.append(external_id)
        if location_id:
            location_ids.add(location_id)
        if site_id:
            site_ids.add(site_id)
        if position_id:
            position_ids.add(position_id)
        candidates.append((item, external_id, location_id, site_id, position_id, starts_at, ends_at, instances))

    local_by_external = {
        str(row.wiw_shift_id): row
        for row in Shift.objects.filter(wiw_shift_id__in=external_ids).select_related('client', 'location', 'position')
        if row.wiw_shift_id
    }
    locations = Location.objects.filter(Q(wiw_location_id__in=location_ids) | Q(wiw_site_id__in=site_ids)).select_related('client')
    location_by_id = {}
    for row in locations:
        if row.wiw_location_id:
            location_by_id[f'location:{row.wiw_location_id}'] = row
        if row.wiw_site_id:
            location_by_id[f'site:{row.wiw_site_id}'] = row
    position_by_id = {str(row.wiw_position_id): row for row in Position.objects.filter(wiw_position_id__in=position_ids)}

    rows = []
    for item, external_id, location_id, site_id, position_id, starts_at, ends_at, instances in candidates:
        local = local_by_external.get(external_id)
        location = (local.location if local else None) or location_by_id.get(f'site:{site_id}') or location_by_id.get(f'location:{location_id}')
        position = (local.position if local else None) or position_by_id.get(position_id)
        client_name = (local.client.name if local and local.client_id else '') or (location.client.name if location and location.client_id else '')
        if not client_name:
            client_name = _display_label(_value(item, 'client_name', 'company_name', 'company', 'client', 'site'), 'WIW')
        location_name = (local.location.name if local and local.location_id else '') or (location.name if location else '')
        if not location_name:
            location_name = _display_label(_value(item, 'site_name', 'location_name', 'site', 'location'), 'WIW')
        position_name = (local.position.name if local and local.position_id else '') or (position.name if position else '')
        if not position_name:
            position_name = _display_label(_value(item, 'position_name', 'position'), 'Schicht')
        rows.append({
            'id': f'wiw-live-{external_id or len(rows)}',
            'wiw_shift_id': external_id,
            'local_shift_id': str(local.id) if local else '',
            'starts_at': starts_at.isoformat(),
            'ends_at': ends_at.isoformat(),
            'status': 'published',
            'open_count': instances,
            'filled_count': 0,
            'assigned_workers': [],
            'client_name': client_name,
            'location_name': location_name,
            'position_name': position_name,
            'break_minutes': int(_value(item, 'break_minutes', 'break', default=0) or 0),
            'color_hue': None,
            'source': 'wiw-live',
            'read_only': True,
        })
    return rows


def _local_open_shift_count(now, *, native_only=False):
    # Open capacity is represented by ShiftSlot. Counting slots keeps native
    # multi-person needs accurate and lets the dashboard react immediately to
    # a local assignment/release without waiting for the read-only WIW cache.
    rows = ShiftSlot.objects.filter(
        shift__status__in=[Shift.Status.PUBLISHED, Shift.Status.CONFIRMED],
        shift__ends_at__gte=now,
        status=ShiftSlot.Status.OPEN,
        worker__isnull=True,
    )
    if native_only:
        rows = rows.filter(Q(shift__wiw_shift_id__isnull=True) | Q(shift__wiw_shift_id=''))
    return rows.count()


def _local_snapshot(now):
    exceptions = admin_base._exception_center_items(now)
    attendance_notices = sum(item.get('category') == 'attendance' for item in exceptions)
    return {
        'attendance_notices': attendance_notices,
        'time_off_requests': TimeOffRequest.objects.filter(status=TimeOffRequest.Status.PENDING).count(),
        'shift_requests': ShiftSwapRequest.objects.filter(status=ShiftSwapRequest.Status.PENDING).count(),
        'open_shift_requests': ShiftPickupRequest.objects.filter(status=ShiftPickupRequest.Status.PENDING).count(),
        'open_shifts_available': _local_open_shift_count(now),
        'source': 'aplus-local',
    }


def _live_wiw_snapshot(now):
    cached = cache.get(CACHE_KEY)
    if cached:
        return cached

    client = WhenIWorkClient()
    local_now = timezone.localtime(now)
    start_date = (local_now - timedelta(days=1)).date()
    end_date = (local_now + timedelta(days=WIW_DASHBOARD_FUTURE_DAYS)).date()
    end_at = now + timedelta(days=WIW_DASHBOARD_FUTURE_DAYS)

    snapshot = {}
    errors = []

    # WIW does NOT return OpenShifts from a plain /shifts call. Its default
    # window is only now..+3 days and open shifts require the include_* flags.
    # Count `instances`, because a single OpenShift object can represent more
    # than one available slot in the WIW dashboard.
    try:
        shift_payload = client.get('/shifts', params={
            'start': now.isoformat(),
            'end': end_at.isoformat(),
            'include_open': 'true',
            'include_onlyopen': 'true',
            'include_allopen': 'true',
            'all_locations': 'true',
            'unpublished': 'false',
            'limit': 500,
        })
        shifts = client.extract_collection(shift_payload, 'shifts')
        open_shift_rows = _live_open_shift_rows(shifts, now)
        snapshot['open_shift_rows'] = open_shift_rows
        snapshot['open_shifts_available'] = sum(int(row.get('open_count') or 0) for row in open_shift_rows)
    except Exception as exc:
        errors.append(f'OpenShifts: {exc}')

    # Time Off Requests live at /requests. Ask WIW for pending requests in a
    # real date window; the endpoint requires start/end and otherwise the old
    # implementation could silently fall back to zero.
    try:
        time_off = _paged_get(client, '/requests', 'requests', {
            'start': start_date.isoformat(),
            'end': end_date.isoformat(),
            'status': 0,
            'limit': WIW_PAGE_LIMIT,
        }, page_start=0)
        snapshot['time_off_requests'] = sum(1 for item in time_off if _pending(item))
    except Exception as exc:
        errors.append(f'TimeOff: {exc}')

    # Shift Requests are a separate WIW resource (/swaps). They are not mixed
    # into /requests.
    try:
        swaps = _paged_get(client, '/swaps', 'swaps', {
            'start': now.isoformat(),
            'end': end_at.isoformat(),
            'status': 0,
            'open_only': 'true',
            'limit': WIW_PAGE_LIMIT,
        }, page_start=1)
        snapshot['shift_requests'] = sum(1 for item in swaps if _pending(item))
    except Exception as exc:
        errors.append(f'ShiftRequests: {exc}')

    # Shift Bidding / OpenShift Requests has its own approval-request API.
    # Count pending approval requests, not Time Off rows that happen to point to
    # a shift.
    try:
        approvals = _paged_get(client, '/openshiftapprovalrequests', 'openshiftapprovalrequests', {
            'start': start_date.isoformat(),
            'end': end_date.isoformat(),
            'limit': WIW_PAGE_LIMIT,
        }, page_start=0)
        snapshot['open_shift_requests'] = sum(1 for item in approvals if _pending(item))
    except Exception as exc:
        errors.append(f'OpenShiftRequests: {exc}')

    snapshot.update({
        'source': 'wiw-live-partial' if errors else 'wiw-live-readonly',
        'fetched_at': now.isoformat(),
        'live_error': ' | '.join(errors),
    })
    cache.set(CACHE_KEY, snapshot, CACHE_SECONDS)
    return snapshot


@api_view(['GET'])
def mobile_dashboard(request):
    if request.user.role not in MANAGER_ROLES:
        return Response({'detail': 'Nur Administration und Disposition dürfen diese Ansicht verwenden.'}, status=403)

    now = timezone.now()
    snapshot = _local_snapshot(now)
    # The dashboard total is the combined availability from WIW plus native
    # A+ OpenShifts. Imported WIW shifts also exist locally, so only add local
    # shifts that do not carry a WIW id to avoid double-counting.
    native_open_shifts = _local_open_shift_count(now, native_only=True)
    live_error = ''

    if settings.WIW_SYNC_ENABLED and settings.WIW_DEV_KEY and settings.WIW_EMAIL and settings.WIW_PASSWORD:
        try:
            live = dict(_live_wiw_snapshot(now))
            live_error = str(live.get('live_error') or '')
            if 'open_shifts_available' in live:
                live['open_shifts_available'] = int(live.get('open_shifts_available') or 0) + native_open_shifts
            snapshot.update(live)
        except WhenIWorkError as exc:
            live_error = str(exc)
        except Exception as exc:  # dashboard must still work if WIW is temporarily unavailable
            live_error = str(exc)

    latest = IntegrationSyncRun.objects.filter(provider='wiw').order_by('-started_at').first()
    snapshot.update({
        'generated_at': now,
        'sync_enabled': settings.WIW_SYNC_ENABLED,
        'read_only': getattr(settings, 'WIW_READ_ONLY', True),
        'latest_sync_at': latest.finished_at if latest else None,
        'latest_sync_status': latest.status if latest else None,
        'live_error': live_error,
    })
    return Response(snapshot)
