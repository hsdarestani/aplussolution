from datetime import timedelta

from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Notification, Shift, TimeEntry, User
from .operational_notifications import notify_managers_attendance
from .permissions import IsAdminOrManager
from .services import audit
from .views import TimeEntryViewSet as LegacyTimeEntryViewSet, geofence_error


OUTSIDE_GEOFENCE_PREFIX = 'OUTSIDE_GEOFENCE:'
SELF_REPORTED_REASON = 'SELF_REPORTED_AFTER_SHIFT'
MAX_SELF_REPORTED_HOURS = 24


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
        # A location without configured GPS coordinates has no geofence. In that
        # case geofence_error() returns None and attendance is allowed without
        # requiring the employee's device location.
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
        notify_managers_attendance(entry, 'check_in')
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

        notify_managers_attendance(entry, 'check_out')

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

    @action(detail=False, methods=['post'])
    def report_shift(self, request):
        """Let a worker report actual hours after a completed scheduled shift.

        This flow intentionally does not request or store GPS coordinates. The
        submitted row always enters the existing admin review queue.
        """
        if request.user.role != User.Role.WORKER:
            return Response({'detail': 'Arbeitszeiten können hier nur Mitarbeiter melden.'}, status=403)

        worker = request.user.worker_profile
        legal_acknowledged = request.data.get('legal_acknowledged') in (True, 'true', '1', 1)
        if not legal_acknowledged:
            return Response({'detail': 'Bitte bestätige zuerst die Erklärung zur Richtigkeit deiner Arbeitszeit.'}, status=400)
        shift_id = request.data.get('shift')
        if not shift_id:
            return Response({'detail': 'Schicht fehlt.'}, status=400)

        ownership = Q(worker=worker) | Q(slots__worker=worker, slots__status='claimed')
        shift = Shift.objects.filter(ownership, pk=shift_id).select_related(
            'location', 'position'
        ).distinct().first()
        if not shift:
            return Response({'detail': 'Diese Schicht gehört nicht zu deinem Profil.'}, status=403)
        if shift.status in {Shift.Status.DRAFT, Shift.Status.CANCELLED}:
            return Response({'detail': 'Für diese Schicht kann keine Arbeitszeit gemeldet werden.'}, status=400)

        now = timezone.now()
        if shift.ends_at > now:
            return Response({'detail': 'Die Schicht ist noch nicht beendet.'}, status=400)
        if TimeEntry.objects.filter(worker=worker, shift=shift).exists():
            return Response({'detail': 'Für diese Schicht wurde bereits Arbeitszeit erfasst.'}, status=400)

        clock_in = _parse_admin_datetime(request.data.get('clock_in'))
        clock_out = _parse_admin_datetime(request.data.get('clock_out'))
        if not clock_in or not clock_out:
            return Response({'detail': 'Bitte Beginn und Ende vollständig angeben.'}, status=400)
        if clock_out <= clock_in:
            return Response({'detail': 'Arbeitsende muss nach Arbeitsbeginn liegen.'}, status=400)
        if clock_out > now + timedelta(minutes=15):
            return Response({'detail': 'Arbeitsende darf nicht in der Zukunft liegen.'}, status=400)
        if clock_out - clock_in > timedelta(hours=MAX_SELF_REPORTED_HOURS):
            return Response({'detail': 'Eine gemeldete Arbeitszeit darf maximal 24 Stunden umfassen.'}, status=400)
        if clock_in < shift.starts_at - timedelta(hours=12) or clock_out > shift.ends_at + timedelta(hours=12):
            return Response({'detail': 'Die gemeldete Zeit liegt zu weit außerhalb der geplanten Schicht.'}, status=400)

        entry = TimeEntry.objects.create(
            worker=worker,
            shift=shift,
            clock_in=clock_in,
            clock_out=clock_out,
            approved=False,
            break_minutes=shift.break_minutes,
            edit_reason=f'{SELF_REPORTED_REASON}\nLEGAL_ACKNOWLEDGED',
        )
        worker_name = request.user.get_full_name() or request.user.email
        for recipient in User.objects.filter(role__in=[User.Role.ADMIN, User.Role.MANAGER], is_active=True):
            Notification.objects.get_or_create(
                user=recipient,
                kind=f'shift-time-report-review-{entry.id}',
                defaults={
                    'title': 'Arbeitszeit wartet auf Freigabe',
                    'body': f'{worker_name}: {timezone.localtime(clock_in):%d.%m.%Y %H:%M}–{timezone.localtime(clock_out):%H:%M}',
                    'action_url': '/time',
                },
            )
        Notification.objects.filter(
            user=request.user,
            kind=f'shift-time-report-{shift.id}-{worker.id}',
            read_at__isnull=True,
        ).update(read_at=timezone.now())
        audit(request, 'time.shift_reported', entry, {'shift': str(shift.id)})
        payload = self.get_serializer(entry).data
        payload['review_required'] = True
        return Response(payload, status=201)

    @action(detail=True, methods=['post'], permission_classes=[IsAdminOrManager])
    def approve(self, request, pk=None):
        entry = self.get_object()
        if entry.wiw_time_id:
            return Response({'detail': 'Importierte WIW-Arbeitszeiten sind historische, schreibgeschützte Nachweise.'}, status=400)

        requested_clock_in = request.data.get('clock_in')
        requested_clock_out = request.data.get('clock_out')
        requested_break = request.data.get('break_minutes')
        subtract_minutes = request.data.get('subtract_minutes')
        changed = False

        if requested_clock_in not in (None, ''):
            parsed_in = _parse_admin_datetime(requested_clock_in)
            if not parsed_in:
                return Response({'detail': 'Die angepasste Beginnzeit ist ungültig.'}, status=400)
            entry.clock_in = parsed_in
            changed = True

        if requested_clock_out not in (None, ''):
            parsed_out = _parse_admin_datetime(requested_clock_out)
            if not parsed_out:
                return Response({'detail': 'Die angepasste Endzeit ist ungültig.'}, status=400)
            entry.clock_out = parsed_out
            changed = True
        elif subtract_minutes not in (None, ''):
            try:
                minutes = max(0, int(subtract_minutes))
            except (TypeError, ValueError):
                return Response({'detail': 'Minutenwert ist ungültig.'}, status=400)
            if not entry.clock_out:
                return Response({'detail': 'Es gibt noch keine Check-out-Zeit zum Anpassen.'}, status=400)
            entry.clock_out = entry.clock_out - timedelta(minutes=minutes)
            changed = changed or minutes > 0

        if not entry.clock_out or entry.clock_out <= entry.clock_in:
            return Response({'detail': 'Arbeitsende muss nach dem Arbeitsbeginn liegen.'}, status=400)

        if requested_break not in (None, ''):
            try:
                pause = max(0, min(24 * 60, int(requested_break)))
            except (TypeError, ValueError):
                return Response({'detail': 'Pausenminuten sind ungültig.'}, status=400)
            if pause >= int((entry.clock_out - entry.clock_in).total_seconds() // 60):
                return Response({'detail': 'Die Pause muss kürzer als die gesamte Arbeitszeit sein.'}, status=400)
            entry.break_minutes = pause
            changed = True

        reason = str(request.data.get('reason') or '').strip()
        previous_reason = entry.edit_reason or ''
        if changed or previous_reason.startswith(OUTSIDE_GEOFENCE_PREFIX):
            review_note = reason or 'Durch Administration geprüft und freigegeben.'
            entry.edit_reason = f'{previous_reason}\nADMIN_REVIEW: {review_note}'.strip()

        entry.approved = True
        entry.approved_by = request.user
        update_fields = ['approved', 'approved_by', 'edit_reason', 'updated_at']
        if changed:
            update_fields.extend(['clock_in', 'clock_out', 'break_minutes'])
        entry.save(update_fields=update_fields)
        audit(request, 'time.approved', entry, {
            'time_or_pause_changed': changed,
            'break_minutes': entry.effective_break_minutes,
            'reason': reason,
        })
        return Response(self.get_serializer(entry).data)
