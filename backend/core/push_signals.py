from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Notification
from .notification_settings import render_push_notification
from .push_notifications import push_provider_configured, send_notification_push


def native_push_suppressed(instance: Notification) -> bool:
    """Compatibility helper: settings now decide which native events are muted."""
    enabled, _title, _body, _key = render_push_notification(instance)
    return not enabled


@receiver(post_save, sender=Notification, dispatch_uid='aplus_native_push_notification')
def dispatch_native_push(sender, instance: Notification, created: bool, **kwargs):
    if not created:
        return

    # Every family is now configurable in Settings. Disabled types still remain
    # in the in-app history, they simply do not produce an Android/iOS alert.
    if native_push_suppressed(instance):
        return

    # Do not mirror every worker notification to admins. That behavior caused one
    # admin device to receive N extra pushes whenever an event targeted N workers.
    # Event-specific admin summaries are created explicitly by the operational
    # notification helpers instead.
    if not push_provider_configured():
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
