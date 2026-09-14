from __future__ import annotations

from datetime import timedelta

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Notification


DUPLICATE_WINDOW_SECONDS = 45
SHIFT_UPDATE_PREFIX = 'shift-event-updated-'


@receiver(post_save, sender=Notification, dispatch_uid='aplus_dedupe_shift_update_notifications')
def coalesce_duplicate_shift_update(sender, instance: Notification, created: bool, **kwargs):
    """Remove duplicate worker shift-update rows before native push is queued.

    Some installed app versions can repeat an otherwise identical card PATCH
    while saving. The operational notification helper intentionally used a
    random suffix for every event, so those retries became multiple identical
    in-app rows and multiple native pushes. Keep distinct real updates, but
    collapse an identical update for the same worker inside a short save window.
    """
    if not created or not str(instance.kind or '').startswith(SHIFT_UPDATE_PREFIX):
        return

    created_at = instance.created_at
    cutoff = created_at - timedelta(seconds=DUPLICATE_WINDOW_SECONDS)
    duplicate_exists = (
        Notification.objects.filter(
            user_id=instance.user_id,
            title=instance.title,
            body=instance.body,
            action_url=instance.action_url,
            kind__startswith=SHIFT_UPDATE_PREFIX,
            created_at__gte=cutoff,
            created_at__lt=created_at,
        )
        .exclude(pk=instance.pk)
        .exists()
    )
    if not duplicate_exists:
        return

    # push_signals is registered after this module in CoreConfig.ready(). Mark
    # this in-memory instance so the later receiver cannot enqueue a push for a
    # row we are about to remove.
    instance._aplus_duplicate_shift_update = True
    Notification.objects.filter(pk=instance.pk).delete()
