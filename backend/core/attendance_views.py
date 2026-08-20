from datetime import datetime, timedelta

from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .attendance_models import TimeEntryCorrection
from .models import Notification, Shift, TimeEntry, User
from .serializers import TimeEntrySerializer
from .services import audit
from .shift_api import ShiftApiSerializer


SYNTHETIC_MIGRATION_EMAIL_SUFFIX = '@sync.invalid'
ATTENDANCE_LIST_LIMIT = 100
STALE_WORKER_TIMER_HOURS = 16


def _parse_requested_datetime(value):
    if value in (None, ''):
        return None
    if hasattr(value, 'tzinfo'):
        result = value
    else:
        result = parse_datetime(str(value))
    if not result:
        return None
    if timezone.is_naive(result):
        result = timezone.make_aware(result, timezone.get_current_timezone())
    return result


def correction_payload(item):
    entry = item.entry
    return {
        'id': str(item.id),
        'entry_id': str(entry.id),
        'worker_id': str(item.requested_by_id),
        'worker_name': item.requested_by.user.get_full_name() or item.requested_by.user.email,
        'original_clock_in': entry.clock_in,
        'original_clock_out': entry.clock_out,
        'requested_clock_in': item.requested_clock_in,
        'requested_clock_out': item.requested_clock_out,
        'reason': item.reason,
        'status': item.status,
        'decision_note': item.decision_note,
        'created_at': item.created_at,
        'decided_at': item.decided_at,
    }


def _manager_only(request):
    return request.user.role in {User.Role.ADMIN, User.Role.MANAGER}


def _operational_time_entries():
    """Return native A+ time rows only; WIW rows remain available for migration/audit."""
    return TimeEntry.objects.filter(wiw_time_id__isnull=True).exclude(
        worker__user__email__iendswith=SYNTHETIC_MIGRATION_EMAIL_SUFFIX
    )


@api_view(['GET'])
def employee_attendance_home(request):
    if request.user.role != User.Role.WORKER:
        return Response({'detail': 'Diese Ansicht ist nur für Mitarbeiter.'}, status=403)

    worker = request.user.worker_profile
    now = timezone.now()
    month_start = timezone.make_aware(
        datetime(now.year, now.month, 1),
        timezone.get_current_timezone(),
    )

    # A historical WIW timer must never block the native A+ clock.
    open_entry = TimeEntry.objects.select_related('shift__position', 'worker__user').filter(
        worker=worker,
        wiw_time_id__isnull=True,
        clock_out__isnull=True,
    ).order_by('-clock_in').first()
    stale_active = (
        open_entry
        if open_entry and open_entry.clock_in <= now - timedelta(hours=STALE_WORKER_TIMER_HOURS)
        else None
    )
    active = None if stale_active else open_entry

    history_qs = TimeEntry.objects.select_related('shift__position', 'worker__user').filter(
        worker=worker,
        clock_out__isnull=False,
    ).order_by('-clock_in')[:30]

    # Closed historical entries still belong in payroll/history. Forgotten open
    # timers, however, must never inflate the monthly total.
    month_entries = TimeEntry.objects.select_related('shift').filter(
        worker=worker,
        clock_in__gte=month_start,
        clock_out__isnull=False,
    )
    month_worked_minutes = sum(entry.worked_minutes for entry in month_entries)

    ownership = Q(slots__worker=worker, slots__status='claimed') | Q(worker=worker)
    eligible_shift = None
    if stale_active is None:
        eligible_shift = Shift.objects.filter(
            ownership,
            starts_at__lte=now + timedelta(hours=4),
            ends_at__gte=now - timedelta(hours=4),
            status__in=[Shift.Status.PUBLISHED, Shift.Status.CONFIRMED],
        ).select_related('order', 'client', 'location', 'position').distinct().order_by('starts_at').first()

    corrections = TimeEntryCorrection.objects.select_related(
        'entry', 'requested_by__user'
    ).filter(requested_by=worker).order_by('-created_at')[:20]

    return Response({
        'active_entry': TimeEntrySerializer(active, context={'request': request}).data if active else None,
        'stale_active_entry': TimeEntrySerializer(stale_active, context={'request': request}).data if stale_active else None,
        'eligible_shift': ShiftApiSerializer(eligible_shift, context={'request': request}).data if eligible_shift else None,
        'month_worked_minutes': month_worked_minutes,
        'pending_corrections': sum(1 for item in corrections if item.status == TimeEntryCorrection.Status.PENDING),
        'history': TimeEntrySerializer(history_qs, many=True, context={'request': request}).data,
        'corrections': [correction_payload(item) for item in corrections],
    })


@api_view(['POST'])
def request_time_correction(request, entry_id):
    if request.user.role != User.Role.WORKER:
        return Response({'detail': 'Nur Mitarbeiter können Korrekturen anfragen.'}, status=403)
    worker = request.user.worker_profile
    entry = TimeEntry.objects.select_related('worker__user').filter(pk=entry_id, worker=worker).first()
    if not entry:
        return Response({'detail': 'Zeiteintrag wurde nicht gefunden.'}, status=404)
    if entry.clock_out is None:
        return Response({'detail': 'Eine laufende Zeiterfassung kann noch nicht korrigiert werden.'}, status=400)
    if TimeEntryCorrection.objects.filter(entry=entry, status=TimeEntryCorrection.Status.PENDING).exists():
        return Response({'detail': 'Für diesen Zeiteintrag ist bereits eine Korrektur offen.'}, status=400)

    reason = str(request.data.get('reason') or '').strip()
    if len(reason) < 5:
        return Response({'detail': 'Bitte gib einen kurzen Grund für die Korrektur an.'}, status=400)

    raw_in = request.data.get('clock_in')
    raw_out = request.data.get('clock_out')
    requested_in = _parse_requested_datetime(raw_in)
    requested_out = _parse_requested_datetime(raw_out)
    if raw_in not in (None, '') and requested_in is None:
        return Response({'detail': 'Der gewünschte Arbeitsbeginn ist ungültig.'}, status=400)
    if raw_out not in (None, '') and requested_out is None:
        return Response({'detail': 'Das gewünschte Arbeitsende ist ungültig.'}, status=400)
    if requested_in is None and requested_out is None:
        return Response({'detail': 'Bitte ändere mindestens Beginn oder Ende.'}, status=400)

    final_in = requested_in or entry.clock_in
    final_out = requested_out or entry.clock_out
    if not final_out or final_out <= final_in:
        return Response({'detail': 'Arbeitsende muss nach Arbeitsbeginn liegen.'}, status=400)

    correction = TimeEntryCorrection.objects.create(
        entry=entry,
        requested_by=worker,
        requested_clock_in=requested_in,
        requested_clock_out=requested_out,
        reason=reason,
    )
    for recipient in User.objects.filter(role__in=[User.Role.ADMIN, User.Role.MANAGER], is_active=True):
        Notification.objects.create(
            user=recipient,
            kind=f'time-correction-{correction.id}',
            title='Arbeitszeit-Korrektur wartet',
            body=f'{request.user.get_full_name() or request.user.email}: {reason[:120]}',
            action_url='/time',
        )
    audit(request, 'time.correction_requested', correction, {'entry': str(entry.id)})
    return Response(correction_payload(correction), status=201)


@api_view(['POST'])
def cancel_time_correction(request, pk):
    if request.user.role != User.Role.WORKER:
        return Response({'detail': 'Keine Berechtigung.'}, status=403)
    correction = TimeEntryCorrection.objects.select_related('entry', 'requested_by__user').filter(
        pk=pk,
        requested_by=request.user.worker_profile,
        status=TimeEntryCorrection.Status.PENDING,
    ).first()
    if not correction:
        return Response({'detail': 'Offene Korrekturanfrage wurde nicht gefunden.'}, status=404)
    correction.status = TimeEntryCorrection.Status.CANCELLED
    correction.save(update_fields=['status', 'updated_at'])
    audit(request, 'time.correction_cancelled', correction)
    return Response(correction_payload(correction))


@api_view(['POST'])
def decide_time_correction(request, pk):
    if not _manager_only(request):
        return Response({'detail': 'Keine Berechtigung.'}, status=403)
    correction = TimeEntryCorrection.objects.select_related('entry', 'requested_by__user').filter(
        pk=pk,
        status=TimeEntryCorrection.Status.PENDING,
    ).first()
    if not correction:
        return Response({'detail': 'Offene Korrekturanfrage wurde nicht gefunden.'}, status=404)

    decision = request.data.get('status')
    if decision not in {TimeEntryCorrection.Status.APPROVED, TimeEntryCorrection.Status.REJECTED}:
        return Response({'detail': 'Ungültige Entscheidung.'}, status=400)

    entry = correction.entry
    if decision == TimeEntryCorrection.Status.APPROVED:
        if correction.requested_clock_in is not None:
            entry.clock_in = correction.requested_clock_in
        if correction.requested_clock_out is not None:
            entry.clock_out = correction.requested_clock_out
        if not entry.clock_out or entry.clock_out <= entry.clock_in:
            return Response({'detail': 'Die angefragte Zeitspanne ist ungültig.'}, status=400)
        entry.edit_reason = correction.reason
        entry.approved = True
        entry.approved_by = request.user
        entry.save(update_fields=['clock_in', 'clock_out', 'edit_reason', 'approved', 'approved_by', 'updated_at'])

    correction.status = decision
    correction.decided_by = request.user
    correction.decided_at = timezone.now()
    correction.decision_note = str(request.data.get('note') or '').strip()
    correction.save(update_fields=['status', 'decided_by', 'decided_at', 'decision_note', 'updated_at'])

    Notification.objects.create(
        user=correction.requested_by.user,
        kind=f'time-correction-decision-{correction.id}',
        title='Arbeitszeit-Korrektur entschieden',
        body='Deine Korrektur wurde genehmigt.' if decision == TimeEntryCorrection.Status.APPROVED else 'Deine Korrektur wurde abgelehnt.',
        action_url='/time',
    )
    audit(request, 'time.correction_decided', correction, {'status': decision})
    return Response(correction_payload(correction))


@api_view(['GET'])
def attendance_exceptions(request):
    if not _manager_only(request):
        return Response({'detail': 'Keine Berechtigung.'}, status=403)

    now = timezone.now()
    operational_entries = _operational_time_entries().select_related('worker__user', 'shift__position')
    unapproved_qs = operational_entries.filter(
        clock_out__isnull=False,
        approved=False,
    ).order_by('-clock_in')
    long_running_qs = operational_entries.filter(
        clock_out__isnull=True,
        clock_in__lte=now - timedelta(hours=12),
    ).order_by('clock_in')
    corrections_qs = TimeEntryCorrection.objects.select_related(
        'entry', 'requested_by__user'
    ).filter(
        status=TimeEntryCorrection.Status.PENDING,
        entry__wiw_time_id__isnull=True,
    ).exclude(
        requested_by__user__email__iendswith=SYNTHETIC_MIGRATION_EMAIL_SUFFIX
    ).order_by('created_at')

    unapproved_count = unapproved_qs.count()
    long_running_count = long_running_qs.count()
    corrections_count = corrections_qs.count()
    unapproved = list(unapproved_qs[:ATTENDANCE_LIST_LIMIT])
    long_running = list(long_running_qs[:ATTENDANCE_LIST_LIMIT])
    corrections = list(corrections_qs[:ATTENDANCE_LIST_LIMIT])

    return Response({
        'counts': {
            'pending_corrections': corrections_count,
            'unapproved_entries': unapproved_count,
            'long_running_entries': long_running_count,
            'total': corrections_count + unapproved_count + long_running_count,
        },
        'list_limit': ATTENDANCE_LIST_LIMIT,
        'pending_corrections': [correction_payload(item) for item in corrections],
        'unapproved_entries': TimeEntrySerializer(unapproved, many=True, context={'request': request}).data,
        'long_running_entries': TimeEntrySerializer(long_running, many=True, context={'request': request}).data,
    })
