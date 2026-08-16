from celery import shared_task


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={'max_retries': 6})
def deliver_premium_webhook(self, delivery_id):
    from .premium_models import WebhookDelivery
    from .premium_services import deliver_webhook

    delivery = WebhookDelivery.objects.select_related('subscription').get(pk=delivery_id)
    status = deliver_webhook(delivery)
    if status == WebhookDelivery.Status.FAILED and delivery.attempts < 6:
        raise RuntimeError(f'Webhook delivery failed with status {delivery.response_status or "network"}')
    return {'id': str(delivery.id), 'status': status, 'attempts': delivery.attempts}
