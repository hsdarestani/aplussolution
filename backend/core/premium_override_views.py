from datetime import timedelta

from dateutil.parser import isoparse
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Shift, User, WorkerProfile
from .permissions import IsAdmin, IsAdminOrManager
from .premium_models import ReportDefinition, StaffCallout, WebhookDelivery, WebhookSubscription
from .premium_report_service import run_report
from .premium_services import auto_schedule, rows_to_csv
from .premium_tasks import deliver_premium_webhook
from .services import audit
from .shift_service import refresh_shift_state
from .shift_slots import ShiftSlot


def _dt(value, fallback=None):
    if not value:
        return fallback
    parsed = isoparse(str(value))
    return timezone.make_aware(parsed) if timezone.is_naive(parsed) else parsed


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def auto_schedule_view(request):
    start = _dt(request.data.get('start'), timezone.now())
    end = _dt(request.data.get('end'), start + timedelta(days=14))
    try:
        result = auto_schedule(
            start, end, bool(request.data.get('apply')),
            request.data.get('location_id'), request.data.get('worker_ids'),
        )
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=409)
    if result['apply']:
        shift_ids = {row['shift_id'] for row in result['results'] if row.get('worker_id')}
        for shift in Shift.objects.filter(id__in=shift_ids):
            refresh_shift_state(shift)
    audit(
        request,
        'premium.auto_schedule.applied' if result['apply'] else 'premium.auto_schedule.preview',
        request.user,
        {'assigned': result['assigned'], 'unfilled': result['unfilled']},
    )
    return Response(result)


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def report_run(request, pk):
    definition = get_object_or_404(ReportDefinition, pk=pk)
    start = _dt(request.data.get('start'), timezone.now() - timedelta(days=90))
    end = _dt(request.data.get('end'), timezone.now() + timedelta(days=90))
    columns, rows = run_report(definition, start, end)
    if request.data.get('format') == 'csv':
        response = HttpResponse(rows_to_csv(columns, rows), content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="{definition.kind}.csv"'
        return response
    return Response({'columns': columns, 'rows': rows, 'count': len(rows)})


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def callouts(request):
    if request.method == 'GET':
        qs = StaffCallout.objects.select_related('shift__location', 'worker__user', 'covered_by__user')
        if request.user.role == User.Role.WORKER:
            qs = qs.filter(worker__user=request.user)
        elif request.user.role not in {User.Role.ADMIN, User.Role.MANAGER}:
            return Response({'detail': 'Keine Berechtigung.'}, status=403)
        return Response([{
            'id': str(row.id), 'shift_id': str(row.shift_id),
            'worker': row.worker.user.get_full_name() or row.worker.user.email,
            'starts_at': row.shift.starts_at.isoformat(), 'location': row.shift.location.name,
            'reason': row.reason, 'status': row.status,
            'covered_by': row.covered_by.user.email if row.covered_by else None,
        } for row in qs[:200]])

    if request.user.role == User.Role.WORKER:
        worker = get_object_or_404(WorkerProfile, user=request.user)
    elif request.user.role in {User.Role.ADMIN, User.Role.MANAGER} and request.data.get('worker_id'):
        worker = get_object_or_404(WorkerProfile, pk=request.data['worker_id'])
    else:
        return Response({'detail': 'Mitarbeiter fehlt.'}, status=400)

    shift = get_object_or_404(Shift.objects.select_related('location'), pk=request.data.get('shift_id'))
    now = timezone.now()
    if shift.starts_at < now or shift.starts_at > now + timedelta(hours=24):
        return Response({'detail': 'Callouts sind nur innerhalb von 24 Stunden vor Schichtbeginn möglich.'}, status=400)

    with transaction.atomic():
        slot = shift.slots.select_for_update().filter(worker=worker, status=ShiftSlot.Status.CLAIMED).first()
        legacy_assignment = not slot and shift.worker_id == worker.id
        if not slot and not legacy_assignment:
            return Response({'detail': 'Keine übernommene Schicht.'}, status=400)
        if legacy_assignment:
            slot = shift.slots.select_for_update().filter(status=ShiftSlot.Status.OPEN).order_by('created_at').first()
        row = StaffCallout.objects.create(
            shift=shift, worker=worker, slot=slot,
            reason=request.data.get('reason') or '',
        )
        if slot and slot.status == ShiftSlot.Status.CLAIMED:
            slot.worker = None
            slot.status = ShiftSlot.Status.OPEN
            slot.source = 'callout'
            slot.released_at = timezone.now()
            slot.save(update_fields=['worker', 'status', 'source', 'released_at', 'updated_at'])
        if shift.status not in {Shift.Status.CANCELLED, Shift.Status.COMPLETED}:
            shift.status = Shift.Status.PUBLISHED
            shift.worker = None
            shift.published_at = shift.published_at or timezone.now()
            shift.save(update_fields=['status', 'worker', 'published_at', 'updated_at'])
        refresh_shift_state(shift)
    audit(request, 'premium.callout.created', shift, {'worker_id': str(worker.id), 'callout_id': str(row.id)})
    return Response({'id': str(row.id), 'status': row.status}, status=201)


@api_view(['POST'])
@permission_classes([IsAdmin])
def webhook_test(request, pk):
    subscription = get_object_or_404(WebhookSubscription, pk=pk, active=True)
    delivery = WebhookDelivery.objects.create(
        subscription=subscription,
        event_type='system.test',
        payload={'subscription_id': str(subscription.id), 'message': 'A+ Solution webhook test'},
    )
    transaction.on_commit(lambda: deliver_premium_webhook.delay(str(delivery.id)))
    return Response({'queued': True, 'delivery_id': str(delivery.id)})
