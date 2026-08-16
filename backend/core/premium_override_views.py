from datetime import timedelta

from dateutil.parser import isoparse
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .permissions import IsAdmin, IsAdminOrManager
from .premium_models import WebhookDelivery, WebhookSubscription
from .premium_services import auto_schedule
from .premium_tasks import deliver_premium_webhook
from .services import audit
from .shift_service import refresh_shift_state
from .models import Shift


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
