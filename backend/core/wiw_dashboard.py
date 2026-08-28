from __future__ import annotations

from datetime import datetime, timedelta

from dateutil.parser import parse as parse_flexible_datetime
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from . import admin_center_views as admin_base
from .models import IntegrationSyncRun, Shift, ShiftSwapRequest, TimeOffRequest, User
from .premium_approval_models import ShiftPickupRequest
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


def _local_open_shift_count(now):
    rows = Shift.objects.filter(
        is_open=True,
        worker__isnull=True,
        status__in=[Shift.Status.PUBLISHED, Shift.Status.CONFIRMED],
        ends_at__gte=now,
    ).values('wiw_payload')
    total = 0
    for row in rows:
        payload = row.get('wiw_payload') or {}
        try:
            total += max(1, int(payload.get('instances') or 1))
        except (TypeError, ValueError):
            total += 1
    return total


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
        open_shifts = 0
        for item in shifts:
            end = _as_datetime(_value(item, 'end_time', 'end', 'ends_at'))
            if end and end < now:
                continue
            open_shifts += _open_shift_instances(item)
        snapshot['open_shifts_available'] = open_shifts
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
    live_error = ''

    if settings.WIW_SYNC_ENABLED and settings.WIW_DEV_KEY and settings.WIW_EMAIL and settings.WIW_PASSWORD:
        try:
            live = _live_wiw_snapshot(now)
            live_error = str(live.get('live_error') or '')
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
