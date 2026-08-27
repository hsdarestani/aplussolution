from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Notification, TimeEntry, User
from .serializers import TimeEntrySerializer
from .services import audit


def _parse_end(value):
    if not value:
        return timezone.now()
    result = parse_datetime(str(value))
    if not result:
        return None
    if timezone.is_naive(result):
        result = timezone.make_aware(result, timezone.get_current_timezone())
    return result


@api_view(['POST'])
def close_running_entry(request, pk):
    if request.user.role not in {User.Role.ADMIN, User.Role.MANAGER}:
        return Response({'detail': 'Keine Berechtigung.'}, status=403)
    entry = TimeEntry.objects.select_related('worker__user', 'shift').filter(pk=pk, clock_out__isnull=True).first()
    if not entry:
        return Response({'detail': 'Laufende Zeiterfassung wurde nicht gefunden.'}, status=404)
    if entry.wiw_time_id:
        return Response({'detail': 'Importierte WIW-Arbeitszeiten sind historische, schreibgeschützte Nachweise.'}, status=400)
    reason = str(request.data.get('reason') or '').strip()
    if len(reason) < 5:
        return Response({'detail': 'Bitte dokumentiere kurz, warum der laufende Eintrag beendet wird.'}, status=400)
    clock_out = _parse_end(request.data.get('clock_out'))
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
