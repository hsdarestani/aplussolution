from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import User
from .premium_models import ReportDefinition, TaskList, WebhookSubscription
from .services import audit


def _manager(user):
    return user.role in {User.Role.ADMIN, User.Role.MANAGER}


@api_view(['DELETE'])
def task_list_delete(request, pk):
    if not _manager(request.user):
        return Response({'detail': 'Keine Berechtigung.'}, status=403)
    task_list = get_object_or_404(TaskList, pk=pk)
    audit(request, 'premium.task_list_deactivated', task_list, {'id': str(task_list.id), 'name': task_list.name})
    # Preserve historic TaskRun rows while removing the list from active planning UI.
    task_list.active = False
    task_list.save(update_fields=['active', 'updated_at'])
    return Response(status=204)


@api_view(['DELETE'])
def report_definition_delete(request, pk):
    if not _manager(request.user):
        return Response({'detail': 'Keine Berechtigung.'}, status=403)
    report = get_object_or_404(ReportDefinition, pk=pk)
    if request.user.role != User.Role.ADMIN and report.owner_id != request.user.id:
        return Response({'detail': 'Nur eigene Berichte dürfen gelöscht werden.'}, status=403)
    audit(request, 'premium.report_deleted', report, {'id': str(report.id), 'name': report.name, 'kind': report.kind})
    report.delete()
    return Response(status=204)


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
