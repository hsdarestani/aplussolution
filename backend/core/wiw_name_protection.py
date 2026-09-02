from __future__ import annotations

from django.db.models.signals import pre_save
from django.dispatch import receiver

from .models import Location


def _placeholder(value: str) -> bool:
    text = str(value or '').strip().casefold()
    return not text or text.startswith('wiw location') or text.startswith('wiw standort') or text.startswith('wiw site')


@receiver(pre_save, sender=Location, dispatch_uid='aplus_preserve_local_wiw_location_name')
def preserve_local_wiw_location_name(sender, instance: Location, **kwargs):
    """Treat a local location rename as authoritative over later WIW refreshes.

    WIW imports update ``wiw_synced_at``/``wiw_payload``. Once a real local name
    exists we keep it while still accepting address, geo and payload refreshes.
    New/placeholder rows can still receive their initial WIW name.
    """
    if not instance.pk or not instance.wiw_synced_at:
        return
    current = Location.objects.filter(pk=instance.pk).only('name', 'wiw_synced_at').first()
    if not current or _placeholder(current.name):
        return
    # Only guard sync-shaped saves. Ordinary admin/API edits do not advance
    # ``wiw_synced_at`` and therefore remain fully editable.
    incoming_sync = current.wiw_synced_at is None or instance.wiw_synced_at != current.wiw_synced_at
    if incoming_sync and instance.name != current.name:
        instance.name = current.name
