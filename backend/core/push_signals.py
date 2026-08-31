from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Notification
from .push_notifications import push_provider_configured, send_notification_push


_SUPPRESSED_NATIVE_TITLES = {
    'Schichtübernahme abgelehnt',
    'Schicht bestätigt',
    'Schicht abgelehnt',
    'Schichtbestätigung aktualisiert',
    'Zeiterfassung wurde beendet',
}


def native_push_suppressed(instance: Notification) -> bool:
    """Return True for events explicitly approved as in-app-only/no-push."""
    kind = str(instance.kind or '')
    if kind.startswith('shift-confirmation-response-') or kind.startswith('shift-confirmation-admin-'):
        return True
    if kind.startswith('pickup-') and kind.endswith('-rejected'):
        return True
    return str(instance.title or '').strip() in _SUPPRESSED_NATIVE_TITLES


@receiver(post_save, sender=Notification, dispatch_uid='aplus_native_push_notification')
def dispatch_native_push(sender, instance: Notification, created: bool, **kwargs):
    if not created:
        return

    # These events stay in the in-app history but Ashkan explicitly does not want
    # a native push for them.
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
