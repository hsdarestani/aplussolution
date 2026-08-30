from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Notification, User
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


def _mirror_worker_notification_to_admins(instance: Notification) -> None:
    """Give admins a visible confirmation copy for every worker push.

    The original notification remains addressed to the worker. The admin copy is
    a separate Notification, so it reaches every registered admin device through
    the same FCM/APNs pipeline and also remains visible in the notification list.
    """
    if instance.user.role != User.Role.WORKER:
        return
    worker_name = instance.user.get_full_name() or instance.user.email
    for admin in User.objects.filter(role=User.Role.ADMIN, is_active=True):
        Notification.objects.get_or_create(
            user=admin,
            kind=f'admin-worker-copy-{instance.id}',
            defaults={
                'title': f'Push an Mitarbeiter · {worker_name}',
                'body': f'{instance.title} · {instance.body}',
                'action_url': instance.action_url,
            },
        )


@receiver(post_save, sender=Notification, dispatch_uid='aplus_native_push_notification')
def dispatch_native_push(sender, instance: Notification, created: bool, **kwargs):
    if not created:
        return

    # These events stay in the in-app history but Ashkan explicitly does not want
    # a native push (or an admin verification push) for them.
    if native_push_suppressed(instance):
        return

    # Create the admin verification copy inside the same DB transaction. Because
    # the copy belongs to an admin, this signal does not mirror it again.
    _mirror_worker_notification_to_admins(instance)

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
