from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Notification, User
from .push_notifications import push_provider_configured, send_notification_push


def _mirror_worker_notification_to_admins(instance: Notification) -> None:
    """Give admins a visible confirmation copy for every worker notification.

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
