from datetime import timedelta

from django.db.models import Q
from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Shift, TimeEntry
from .services import audit
from .views import TimeEntryViewSet as LegacyTimeEntryViewSet, geofence_error


class TimeEntryViewSet(LegacyTimeEntryViewSet):
    """Attendance for both new self-service slots and legacy assigned shifts."""

    @action(detail=False, methods=['post'])
    def clock_in(self, request):
        if request.user.role != 'worker':
            return Response({'detail': 'Zeiterfassung ist nur im Mitarbeiterportal möglich.'}, status=403)
        worker = request.user.worker_profile
        if TimeEntry.objects.filter(worker=worker, clock_out__isnull=True).exists():
            return Response({'detail': 'Du bist bereits eingestempelt.'}, status=400)

        ownership = Q(slots__worker=worker, slots__status='claimed') | Q(worker=worker)
        now = timezone.now()
        if request.data.get('shift'):
            shift = Shift.objects.filter(ownership, pk=request.data.get('shift')).select_related('location').distinct().first()
            if not shift:
                return Response({'detail': 'Die ausgewählte Schicht gehört nicht zu deinem Profil.'}, status=403)
        else:
            shift = Shift.objects.filter(
                ownership,
                starts_at__lte=now + timedelta(hours=4),
                ends_at__gte=now - timedelta(hours=4),
                status__in=[Shift.Status.PUBLISHED, Shift.Status.CONFIRMED],
            ).select_related('location').distinct().order_by('starts_at').first()

        if not shift:
            return Response({'detail': 'Aktuell gibt es keine passende bestätigte Schicht zum Einstempeln.'}, status=400)
        if shift.location.latitude is None or shift.location.longitude is None:
            return Response({
                'detail': 'Für diesen Einsatzort ist noch keine GPS-Position hinterlegt. Bitte in Personal & Kunden → Einsatzorte den Standort per Karte oder „Mein Standort“ festlegen.'
            }, status=400)
        error = geofence_error(shift, request.data.get('lat'), request.data.get('lng'))
        if error:
            return Response({'detail': error}, status=400)
        entry = TimeEntry.objects.create(
            worker=worker,
            shift=shift,
            clock_in=now,
            clock_in_lat=request.data.get('lat'),
            clock_in_lng=request.data.get('lng'),
        )
        audit(request, 'time.clock_in', entry)
        return Response(self.get_serializer(entry).data, status=201)
