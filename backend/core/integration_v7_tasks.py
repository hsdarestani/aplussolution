from celery import shared_task

from .integration_v7_models import WebhookDelivery
from .integration_v7_service import deliver_webhook, due_webhook_deliveries


@shared_task(name='core.integration_v7_tasks.dispatch_pending_webhooks')
def dispatch_pending_webhooks(limit=100):
    delivered = 0
    dead = 0
    retried = 0
    for row in list(due_webhook_deliveries(limit=limit)):
        deliver_webhook(row)
        if row.status == WebhookDelivery.Status.DELIVERED:
            delivered += 1
        elif row.status == WebhookDelivery.Status.DEAD:
            dead += 1
        else:
            retried += 1
    return {'processed': delivered + dead + retried, 'delivered': delivered, 'retry': retried, 'dead': dead}
