from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import User
from .premium_models import WebhookSubscription
from .services import audit


@api_view(['DELETE'])
def webhook_delete(request, pk):
    if request.user.role != User.Role.ADMIN:
        return Response({'detail': 'Nur Administratoren dürfen Webhooks löschen.'}, status=403)
    webhook = get_object_or_404(WebhookSubscription, pk=pk)
    snapshot = {
        'id': str(webhook.id),
        'name': webhook.name,
        'endpoint_url': webhook.endpoint_url,
        'events': webhook.events,
    }
    audit(request, 'premium.webhook_deleted', webhook, snapshot)
    webhook.delete()
    return Response(status=204)
