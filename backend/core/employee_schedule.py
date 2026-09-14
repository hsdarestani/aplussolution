from __future__ import annotations

from django.db.models import Count, Q
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Shift, User, WorkerProfile
from .shift_api import ShiftApiSerializer
from .shift_rules import normalized_groups
from .shift_slots import ShiftSlot


def _is_service_worker(worker: WorkerProfile) -> bool:
    return 'service' in set(normalized_groups(worker.schedule_groups))


def _service_worker_ids() -> list:
    """Return active workers that are explicitly assigned to Service Zeitplan.

    Normalize in Python instead of relying on database-specific JSON operators so
    the rule behaves the same on PostgreSQL production and SQLite tests.
    """
    workers = WorkerProfile.objects.filter(active=True, user__is_active=True).only('id', 'schedule_groups')
    return [worker.id for worker in workers if _is_service_worker(worker)]


@api_view(['GET'])
def employee_schedule(request):
    """Worker Dienstplan with Service-peer visibility.

    Every worker always sees their own claimed shifts. Workers assigned to the
    Service Zeitplan additionally see claimed shifts of every other active worker
    assigned to that same Service Zeitplan. OpenShifts remain on the existing
    /shifts/available/ endpoint and keep their existing eligibility rules.
    """
    if getattr(request.user, 'role', '') != User.Role.WORKER:
        return Response({'detail': 'Nur Mitarbeiter können den Dienstplan abrufen.'}, status=403)

    worker = request.user.worker_profile
    visible_worker_ids = [worker.id]
    service_schedule = _is_service_worker(worker)
    if service_schedule:
        visible_worker_ids = _service_worker_ids()
        if worker.id not in visible_worker_ids:
            visible_worker_ids.append(worker.id)

    qs = (
        Shift.objects.select_related('order', 'client', 'location', 'position')
        .annotate(
            filled_count=Count(
                'slots',
                filter=Q(slots__status=ShiftSlot.Status.CLAIMED, slots__worker__isnull=False),
                distinct=True,
            ),
            open_count=Count(
                'slots',
                filter=Q(slots__status=ShiftSlot.Status.OPEN, slots__worker__isnull=True),
                distinct=True,
            ),
        )
        .filter(slots__worker_id__in=visible_worker_ids, slots__status=ShiftSlot.Status.CLAIMED)
        .distinct()
        .order_by('starts_at')
    )

    data = ShiftApiSerializer(qs, many=True, context={'request': request}).data
    return Response({
        'service_schedule': service_schedule,
        'shifts': data,
    })
