from __future__ import annotations

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import ClientOrder, Location, Shift


@receiver(post_save, sender=Location, dispatch_uid='aplus_align_location_client_relations')
def align_location_client_relations(sender, instance: Location, **kwargs):
    """Keep denormalized client links consistent after a location is reassigned.

    A+ treats Location.client as the canonical owner. Historical WIW imports can
    leave Shift.client / ClientOrder.client pointing at an old imported client
    after an administrator merges or reassigns a location. Those stale ids make
    the mobile edit form unable to resolve the active customer/location pair.
    """
    if not instance.client_id:
        return

    Shift.objects.filter(location_id=instance.pk).exclude(client_id=instance.client_id).update(
        client_id=instance.client_id
    )
    ClientOrder.objects.filter(location_id=instance.pk).exclude(client_id=instance.client_id).update(
        client_id=instance.client_id
    )
