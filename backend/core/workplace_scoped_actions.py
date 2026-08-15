from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from . import attendance_actions, attendance_views
from .attendance_models import TimeEntryCorrection
from .models import Notification, TimeEntry
from .payroll_service import assert_time_entry_editable
from .permissions import IsAdminOrManager
from .serializers import TimeEntrySerializer
from .services import audit
from .workplace_access import has_capability, visible_workers


def _require_attendance_edit(user):
    return has_capability(user, 'attendance.edit')


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def decide_time_correction(request, pk):
    if not _require_attendance_edit(request.user):
        return Response({'detail': 'Keine Berechtigung.'}, status=403)
    correction = TimeEntryCorrection.objects.select_related('entry', 'requested_by__user').filter(
        pk=pk,
        requested_by__in=visible_workers(request.user),
        status=TimeEntryCorrection.Status.PENDING,
    ).first()
    if not correction:
        return Response({'detail': 'Offene Korrekturanfrage wurde nicht gefunden.'}, status=404)

    decision = request.data.get('status')
    if decision not in {TimeEntryCorrection.Status.APPROVED, TimeEntryCorrection.Status.REJECTED}:
        return Response({'detail': 'Ungültige Entscheidung.'}, status=400)

    entry = correction.entry
    locked = attendance_views._locked_response(entry)
    if locked:
        return locked
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
    return Response(attendance_views.correction_payload(correction))


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def close_running_entry(request, pk):
    if not _require_attendance_edit(request.user):
        return Response({'detail': 'Keine Berechtigung.'}, status=403)
    entry = TimeEntry.objects.select_related('worker__user', 'shift').filter(
        pk=pk,
        worker__in=visible_workers(request.user),
        clock_out__isnull=True,
    ).first()
    if not entry:
        return Response({'detail': 'Laufende Zeiterfassung wurde nicht gefunden.'}, status=404)
    try:
        assert_time_entry_editable(entry)
    except Exception as exc:
        return Response({'detail': str(getattr(exc, 'detail', exc))}, status=getattr(exc, 'status_code', 400))
    reason = str(request.data.get('reason') or '').strip()
    if len(reason) < 5:
        return Response({'detail': 'Bitte dokumentiere kurz, warum der laufende Eintrag beendet wird.'}, status=400)
    clock_out = attendance_actions._parse_end(request.data.get('clock_out'))
    if not clock_out or clock_out <= entry.clock_in:
        return Response({'detail': 'Das Arbeitsende ist ungültig.'}, status=400)
    entry.clock_out = clock_out
    entry.edit_reason = reason
    entry.approved = False
    entry.approved_by = None
    entry.save(update_fields=['clock_out', 'edit_reason', 'approved', 'approved_by', 'updated_at'])
    Notification.objects.create(
        user=entry.worker.user,
        kind=f'time-entry-admin-closed-{entry.id}',
        title='Zeiterfassung wurde beendet',
        body=reason[:180],
        action_url='/time',
    )
    audit(request, 'time.admin_closed_running_entry', entry, {'reason': reason})
    return Response(TimeEntrySerializer(entry, context={'request': request}).data)
