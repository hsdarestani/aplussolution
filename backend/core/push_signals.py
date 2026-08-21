from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Notification
from .push_notifications import push_provider_configured, send_notification_push


@receiver(post_save, sender=Notification, dispatch_uid='aplus_native_push_notification')
def dispatch_native_push(sender, instance: Notification, created: bool, **kwargs):
    if not created or not push_provider_configured():
        return

    notification_id = str(instance.id)

    def enqueue():
        try:
            send_notification_push.delay(notification_id)
        except Exception:
            # Native push is an enhancement. A temporary broker/provider issue must
            # never roll back the operational action that created the notification.
            return

    transaction.on_commit(enqueue)
