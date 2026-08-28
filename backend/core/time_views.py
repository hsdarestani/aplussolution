from datetime import timedelta

from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Notification, Shift, TimeEntry, User
from .permissions import IsAdminOrManager
from .services import audit
from .views import TimeEntryViewSet as LegacyTimeEntryViewSet, geofence_error


OUTSIDE_GEOFENCE_PREFIX = 'OUTSIDE_GEOFENCE:'


def _parse_admin_datetime(value):
    if value in (None, ''):
        return None
    parsed = parse_datetime(str(value))
    if not parsed:
        return None
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


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

        # Checkout must never be trapped by the geofence. If the employee is
        # outside, close the timer immediately and route that exact entry to the
        # admin review queue instead of forcing the timer to keep running.
        geofence_issue = geofence_error(entry.shift, request.data.get('lat'), request.data.get('lng'))
        entry.clock_out = timezone.now()
        entry.clock_out_lat = request.data.get('lat')
        entry.clock_out_lng = request.data.get('lng')
        entry.approved = not bool(geofence_issue)
        entry.approved_by = None
        entry.edit_reason = f'{OUTSIDE_GEOFENCE_PREFIX} {geofence_issue}' if geofence_issue else ''
        entry.save(update_fields=[
            'clock_out', 'clock_out_lat', 'clock_out_lng', 'approved', 'approved_by',
            'edit_reason', 'updated_at',
        ])

        if geofence_issue:
            worker_name = entry.worker.user.get_full_name() or entry.worker.user.email
            for recipient in User.objects.filter(role__in=[User.Role.ADMIN, User.Role.MANAGER], is_active=True):
                Notification.objects.create(
                    user=recipient,
                    kind=f'offsite-checkout-{entry.id}',
                    title='Check-out außerhalb des Einsatzortes',
                    body=f'{worker_name}: Zeit prüfen und freigeben.',
                    action_url='/time',
                )

        audit(request, 'time.clock_out', entry, {
            'review_required': bool(geofence_issue),
            'geofence_issue': geofence_issue or '',
        })
        payload = self.get_serializer(entry).data
        payload['review_required'] = bool(geofence_issue)
        payload['review_reason'] = geofence_issue or ''
        return Response(payload)

    @action(detail=True, methods=['post'], permission_classes=[IsAdminOrManager])
    def approve(self, request, pk=None):
        entry = self.get_object()
        if entry.wiw_time_id:
            return Response({'detail': 'Importierte WIW-Arbeitszeiten sind historische, schreibgeschützte Nachweise.'}, status=400)

        requested_clock_out = request.data.get('clock_out')
        subtract_minutes = request.data.get('subtract_minutes')
        changed = False
        if requested_clock_out not in (None, ''):
            parsed = _parse_admin_datetime(requested_clock_out)
            if not parsed:
                return Response({'detail': 'Die angepasste Check-out-Zeit ist ungültig.'}, status=400)
            if parsed <= entry.clock_in:
                return Response({'detail': 'Check-out muss nach dem Check-in liegen.'}, status=400)
            entry.clock_out = parsed
            changed = True
        elif subtract_minutes not in (None, ''):
            try:
                minutes = max(0, int(subtract_minutes))
            except (TypeError, ValueError):
                return Response({'detail': 'Minutenwert ist ungültig.'}, status=400)
            if not entry.clock_out:
                return Response({'detail': 'Es gibt noch keine Check-out-Zeit zum Anpassen.'}, status=400)
            adjusted = entry.clock_out - timedelta(minutes=minutes)
            if adjusted <= entry.clock_in:
                return Response({'detail': 'Die angepasste Check-out-Zeit liegt vor dem Check-in.'}, status=400)
            entry.clock_out = adjusted
            changed = minutes > 0

        reason = str(request.data.get('reason') or '').strip()
        previous_reason = entry.edit_reason or ''
        if changed or previous_reason.startswith(OUTSIDE_GEOFENCE_PREFIX):
            review_note = reason or 'Durch Administration geprüft und freigegeben.'
            entry.edit_reason = f'{previous_reason}\nADMIN_REVIEW: {review_note}'.strip()

        entry.approved = True
        entry.approved_by = request.user
        update_fields = ['approved', 'approved_by', 'edit_reason', 'updated_at']
        if changed:
            update_fields.append('clock_out')
        entry.save(update_fields=update_fields)
        audit(request, 'time.approved', entry, {
            'clock_out_changed': changed,
            'reason': reason,
        })
        return Response(self.get_serializer(entry).data)
