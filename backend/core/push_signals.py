from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Notification
from .notification_settings import render_push_notification
from .push_notifications import (
    PUSH_AGGREGATION_WINDOW_SECONDS,
    push_provider_configured,
    send_coalesced_notification_push,
    send_notification_push,
    should_aggregate_push,
)


def native_push_suppressed(instance: Notification) -> bool:
    """Compatibility helper: settings now decide which native events are muted."""
    enabled, _title, _body, _key = render_push_notification(instance)
    return not enabled


@receiver(post_save, sender=Notification, dispatch_uid='aplus_native_push_notification')
def dispatch_native_push(sender, instance: Notification, created: bool, **kwargs):
    if not created:
        return

    # notification_dedup runs first and removes repeated identical shift-update
    # rows. Never enqueue a native alert for a row that was coalesced away.
    if getattr(instance, '_aplus_duplicate_shift_update', False):
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
    aggregate = should_aggregate_push(instance)

    def enqueue():
        try:
            if aggregate:
                send_coalesced_notification_push.apply_async(
                    args=[notification_id],
                    countdown=PUSH_AGGREGATION_WINDOW_SECONDS,
                )
            else:
                send_notification_push.delay(notification_id)
        except Exception:
            # Native push is an enhancement. A temporary broker/provider issue must
            # never roll back the operational action that created the notification.
            return

    transaction.on_commit(enqueue)
