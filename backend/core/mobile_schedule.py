from __future__ import annotations

from datetime import datetime, time, timedelta

from django.db.models import Count, Q
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Shift, User
from .shift_api import ShiftApiSerializer
from .shift_slots import ShiftSlot


@api_view(['GET'])
def mobile_schedule(request):
    if getattr(request.user, 'role', '') not in {User.Role.ADMIN, User.Role.MANAGER}:
        return Response({'detail': 'Keine Berechtigung.'}, status=403)

    today = timezone.localdate()
    start = parse_date(str(request.query_params.get('date_from') or '')) or today
    end = parse_date(str(request.query_params.get('date_to') or '')) or (start + timedelta(days=6))
    if end < start:
        start, end = end, start
    if (end - start).days > 31:
        end = start + timedelta(days=31)

    tz = timezone.get_current_timezone()
    start_dt = timezone.make_aware(datetime.combine(start, time.min), tz)
    end_dt = timezone.make_aware(datetime.combine(end + timedelta(days=1), time.min), tz)

    # Week/day rows are tightly bounded. Future published open shifts are included
    # as a small union so the OpenShifts tab stays complete without downloading
    # the whole historical shift table on every mobile open.
    qs = (
        Shift.objects.select_related('order', 'client', 'location', 'position')
        .annotate(
            filled_count=Count('slots', filter=Q(slots__status=ShiftSlot.Status.CLAIMED, slots__worker__isnull=False), distinct=True),
            open_count=Count('slots', filter=Q(slots__status=ShiftSlot.Status.OPEN, slots__worker__isnull=True), distinct=True),
        )
        .filter(
            Q(starts_at__gte=start_dt, starts_at__lt=end_dt)
            | Q(status=Shift.Status.PUBLISHED, starts_at__gte=timezone.now(), slots__status=ShiftSlot.Status.OPEN)
        )
        .distinct()
        .order_by('starts_at')
    )
    return Response({
        'date_from': start.isoformat(),
        'date_to': end.isoformat(),
        'shifts': ShiftApiSerializer(qs, many=True, context={'request': request}).data,
    })
