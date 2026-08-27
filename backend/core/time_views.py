from datetime import timedelta

from django.db.models import Q
from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Shift, TimeEntry
from .permissions import IsAdminOrManager
from .services import audit
from .views import TimeEntryViewSet as LegacyTimeEntryViewSet, geofence_error


class TimeEntryViewSet(LegacyTimeEntryViewSet):
    """Attendance for both new self-service slots and legacy assigned shifts."""

    @action(detail=False, methods=['post'])
    def clock_in(self, request):
        if request.user.role != 'worker':
            return Response({'detail': 'Zeiterfassung ist nur im Mitarbeiterportal möglich.'}, status=403)
        worker = request.user.worker_profile
        if TimeEntry.objects.filter(worker=worker, wiw_time_id__isnull=True, clock_out__isnull=True).exists():
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

    @action(detail=False, methods=['post'])
    def clock_out(self, request):
        if request.user.role != 'worker':
            return Response({'detail': 'Zeiterfassung ist nur im Mitarbeiterportal möglich.'}, status=403)
        entry = TimeEntry.objects.filter(
            worker=request.user.worker_profile,
            wiw_time_id__isnull=True,
            clock_out__isnull=True,
        ).order_by('-clock_in').first()
        if not entry:
            return Response({'detail': 'Keine laufende A+ Zeiterfassung gefunden.'}, status=400)
        if entry.shift_id:
            entry.shift = Shift.objects.select_related('location').get(pk=entry.shift_id)
        error = geofence_error(entry.shift, request.data.get('lat'), request.data.get('lng'))
        if error:
            return Response({'detail': error}, status=400)
        entry.clock_out = timezone.now()
        entry.clock_out_lat = request.data.get('lat')
        entry.clock_out_lng = request.data.get('lng')
        entry.save(update_fields=['clock_out', 'clock_out_lat', 'clock_out_lng', 'updated_at'])
        audit(request, 'time.clock_out', entry)
        return Response(self.get_serializer(entry).data)

    @action(detail=True, methods=['post'], permission_classes=[IsAdminOrManager])
    def approve(self, request, pk=None):
        entry = self.get_object()
        if entry.wiw_time_id:
            return Response({'detail': 'Importierte WIW-Arbeitszeiten sind historische, schreibgeschützte Nachweise.'}, status=400)
        entry.approved = True
        entry.approved_by = request.user
        entry.save(update_fields=['approved', 'approved_by', 'updated_at'])
        audit(request, 'time.approved', entry)
        return Response(self.get_serializer(entry).data)
