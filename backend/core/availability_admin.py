from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Availability, User, WorkerProfile
from .serializers import AvailabilitySerializer
from .services import audit
from .advanced_views import _as_dt, _is_manager


SYNTHETIC_MIGRATION_EMAIL_SUFFIX = '@sync.invalid'


def _serialize(item):
    data = AvailabilitySerializer(item).data
    data['worker_name'] = item.worker.user.get_full_name() or item.worker.employee_number
    return data


def _visible_queryset(request):
    qs = Availability.objects.select_related('worker__user').exclude(
        worker__user__email__iendswith=SYNTHETIC_MIGRATION_EMAIL_SUFFIX
    )
    if _is_manager(request.user):
        return qs
    if request.user.role == User.Role.WORKER:
        return qs.filter(worker=request.user.worker_profile)
    return qs.none()


def _requested_worker(request):
    if request.user.role == User.Role.WORKER:
        return request.user.worker_profile
    if not _is_manager(request.user):
        return None
    worker_id = request.data.get('worker')
    if not worker_id:
        return None
    return WorkerProfile.objects.filter(
        pk=worker_id,
        active=True,
        user__is_active=True,
    ).exclude(user__email__iendswith=SYNTHETIC_MIGRATION_EMAIL_SUFFIX).select_related('user').first()


def _parse_window(data, current=None):
    raw_start = data.get('starts_at') if 'starts_at' in data else getattr(current, 'starts_at', None)
    raw_end = data.get('ends_at') if 'ends_at' in data else getattr(current, 'ends_at', None)
    try:
        starts_at = _as_dt(raw_start, 'Beginn') if not hasattr(raw_start, 'tzinfo') else raw_start
        ends_at = _as_dt(raw_end, 'Ende') if not hasattr(raw_end, 'tzinfo') else raw_end
    except ValueError as exc:
        return None, None, Response({'detail': str(exc)}, status=400)
    if timezone.is_naive(starts_at):
        starts_at = timezone.make_aware(starts_at, timezone.get_current_timezone())
    if timezone.is_naive(ends_at):
        ends_at = timezone.make_aware(ends_at, timezone.get_current_timezone())
    if ends_at <= starts_at:
        return None, None, Response({'detail': 'Ende muss nach dem Beginn liegen.'}, status=400)
    return starts_at, ends_at, None


@api_view(['GET', 'POST'])
def availability_collection(request):
    if request.method == 'GET':
        if not (_is_manager(request.user) or request.user.role == User.Role.WORKER):
            return Response({'detail': 'Keine Berechtigung.'}, status=403)
        rows = _visible_queryset(request).order_by('-starts_at')[:200]
        return Response([_serialize(item) for item in rows])

    worker = _requested_worker(request)
    if not worker:
        if _is_manager(request.user):
            return Response({'detail': 'Bitte einen aktiven Mitarbeiter auswählen.'}, status=400)
        return Response({'detail': 'Verfügbarkeit kann nur von Mitarbeitern oder der Disposition erfasst werden.'}, status=403)

    starts_at, ends_at, error = _parse_window(request.data)
    if error:
        return error
    item = Availability.objects.create(
        worker=worker,
        starts_at=starts_at,
        ends_at=ends_at,
        available=request.data.get('available', True) not in (False, 'false', '0', 0),
        note=str(request.data.get('note', '')).strip(),
    )
    audit(request, 'availability.created', item, {'worker': str(worker.id), 'by_manager': _is_manager(request.user)})
    return Response(_serialize(item), status=201)


@api_view(['PATCH', 'DELETE'])
def availability_detail(request, pk):
    item = Availability.objects.select_related('worker__user').filter(pk=pk).first()
    if not item:
        return Response({'detail': 'Eintrag wurde nicht gefunden.'}, status=404)
    if not _is_manager(request.user) and not (
        request.user.role == User.Role.WORKER and item.worker.user_id == request.user.id
    ):
        return Response({'detail': 'Keine Berechtigung.'}, status=403)

    if request.method == 'DELETE':
        audit(request, 'availability.deleted', item, {'worker': str(item.worker_id), 'by_manager': _is_manager(request.user)})
        item.delete()
        return Response(status=204)

    starts_at, ends_at, error = _parse_window(request.data, item)
    if error:
        return error
    if _is_manager(request.user) and 'worker' in request.data:
        worker = _requested_worker(request)
        if not worker:
            return Response({'detail': 'Bitte einen aktiven Mitarbeiter auswählen.'}, status=400)
        item.worker = worker
    item.starts_at = starts_at
    item.ends_at = ends_at
    if 'available' in request.data:
        item.available = request.data.get('available') not in (False, 'false', '0', 0)
    if 'note' in request.data:
        item.note = str(request.data.get('note', '')).strip()
    item.save()
    audit(request, 'availability.updated', item, {'worker': str(item.worker_id), 'by_manager': _is_manager(request.user)})
    return Response(_serialize(item))
