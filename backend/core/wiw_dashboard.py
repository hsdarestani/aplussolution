from __future__ import annotations

from datetime import datetime

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


CACHE_KEY = 'wiw:admin-home-snapshot:v1'
CACHE_SECONDS = 60
MANAGER_ROLES = {User.Role.ADMIN, User.Role.MANAGER}


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


def _pending(item):
    status = str(_value(item, 'status', 'state', default='pending') or 'pending').strip().lower()
    return status not in {
        'approved', 'accepted', 'complete', 'completed', 'done',
        'denied', 'rejected', 'cancelled', 'canceled', 'deleted', 'expired',
    }


def _request_bucket(item):
    fields = [
        _value(item, 'type', 'request_type', 'kind', 'category', 'action', 'request_subtype', 'name', default=''),
    ]
    shift = item.get('shift')
    if isinstance(shift, dict):
        fields.extend([
            _value(shift, 'type', 'kind', 'name', default=''),
            _value(shift, 'status', default=''),
        ])
    haystack = ' '.join(str(value or '').strip().lower() for value in fields)
    normalized = haystack.replace('-', '_').replace(' ', '_')

    if any(token in normalized for token in (
        'time_off', 'timeoff', 'pto', 'absence', 'vacation', 'unavailable', 'availability',
    )):
        return 'time_off_requests'
    if any(token in normalized for token in (
        'open_shift', 'openshift', 'pickup', 'pick_up', 'claim', 'take_open',
    )):
        return 'open_shift_requests'
    if any(token in normalized for token in (
        'shift_swap', 'swap', 'trade', 'drop_shift', 'release_shift', 'shift_request',
    )):
        return 'shift_requests'

    # WIW has used more than one request payload shape over time. If the type
    # string is absent but the object points at a shift, keep it in the generic
    # shift-request bucket instead of silently showing zero on the dashboard.
    if _value(item, 'shift_id', 'shiftid') not in (None, '', 0, '0') or isinstance(shift, dict):
        return 'shift_requests'
    return None


def _local_snapshot(now):
    exceptions = admin_base._exception_center_items(now)
    attendance_notices = sum(item.get('category') == 'attendance' for item in exceptions)
    open_shifts = Shift.objects.filter(
        is_open=True,
        worker__isnull=True,
        status__in=[Shift.Status.PUBLISHED, Shift.Status.CONFIRMED],
        ends_at__gte=now,
    ).count()
    return {
        'attendance_notices': attendance_notices,
        'time_off_requests': TimeOffRequest.objects.filter(status=TimeOffRequest.Status.PENDING).count(),
        'shift_requests': ShiftSwapRequest.objects.filter(status=ShiftSwapRequest.Status.PENDING).count(),
        'open_shift_requests': ShiftPickupRequest.objects.filter(status=ShiftPickupRequest.Status.PENDING).count(),
        'open_shifts_available': open_shifts,
        'source': 'aplus-local',
    }


def _live_wiw_snapshot(now):
    cached = cache.get(CACHE_KEY)
    if cached:
        return cached

    client = WhenIWorkClient()
    shifts = client.collection('shifts', optional=False).items
    requests = client.collection('requests', optional=True).items

    open_shifts = 0
    for item in shifts:
        worker_id = _value(item, 'user_id', 'worker_id', 'user', 'worker')
        if isinstance(worker_id, dict):
            worker_id = worker_id.get('id') or worker_id.get('user_id')
        if worker_id not in (None, '', 0, '0', False):
            continue
        status = str(_value(item, 'status', default='published') or 'published').lower()
        if status in {'cancelled', 'canceled', 'deleted', 'draft'}:
            continue
        end = _as_datetime(_value(item, 'end_time', 'end', 'ends_at'))
        if end and end < now:
            continue
        open_shifts += 1

    request_counts = {
        'time_off_requests': 0,
        'shift_requests': 0,
        'open_shift_requests': 0,
    }
    unknown_requests = 0
    for item in requests:
        if not _pending(item):
            continue
        bucket = _request_bucket(item)
        if bucket:
            request_counts[bucket] += 1
        else:
            unknown_requests += 1

    snapshot = {
        **request_counts,
        'open_shifts_available': open_shifts,
        'wiw_open_requests_unclassified': unknown_requests,
        'source': 'wiw-live-readonly',
        'fetched_at': now.isoformat(),
    }
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
