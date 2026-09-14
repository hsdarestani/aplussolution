from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import Shift, TimestampedModel, WorkerProfile


class ShiftSlot(TimestampedModel):
    class Status(models.TextChoices):
        OPEN = 'open', 'Offen'
        CLAIMED = 'claimed', 'Übernommen'
        CANCELLED = 'cancelled', 'Storniert'

    class ConfirmationStatus(models.TextChoices):
        PENDING = 'pending', 'Ausstehend'
        CONFIRMED = 'confirmed', 'Bestätigt'
        REJECTED = 'rejected', 'Abgelehnt'

    shift = models.ForeignKey(Shift, on_delete=models.CASCADE, related_name='slots')
    worker = models.ForeignKey(WorkerProfile, on_delete=models.SET_NULL, related_name='shift_slots', blank=True, null=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    source = models.CharField(max_length=30, default='system')
    wiw_shift_id = models.CharField(max_length=80, unique=True, blank=True, null=True)
    claimed_at = models.DateTimeField(blank=True, null=True)
    released_at = models.DateTimeField(blank=True, null=True)
    confirmation_status = models.CharField(max_length=20, choices=ConfirmationStatus.choices, default=ConfirmationStatus.CONFIRMED)
    confirmation_requested_at = models.DateTimeField(blank=True, null=True)
    confirmation_decided_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        app_label = 'core'
        ordering = ['shift__starts_at', 'created_at']


def _reserve_wiw_slot_identity(instance: Shift, target_slot=None) -> None:
    """Keep the external WIW id on exactly one authoritative active slot.

    Historic imports can leave a cancelled/stale ShiftSlot carrying the same
    ``wiw_shift_id``. Editing the current shift then re-runs this post-save
    signal; assigning the id to the active slot used to hit the database unique
    constraint and surface as an opaque HTTP 500 in the mobile editor.

    The Shift row is the authoritative owner of the external id. Before moving
    that id to its current active card, release any stale slot-level mapping.
    """
    if not instance.wiw_shift_id:
        return
    duplicates = ShiftSlot.objects.filter(wiw_shift_id=instance.wiw_shift_id)
    if target_slot is not None and getattr(target_slot, 'pk', None):
        duplicates = duplicates.exclude(pk=target_slot.pk)
    duplicates.update(wiw_shift_id=None)


def _restore_locally_managed_slot_state(instance: Shift, slot: ShiftSlot) -> bool:
    """Keep an explicit A+ assignment/release authoritative over later WIW syncs.

    A WIW-imported one-person shift starts with a ``source='wiw'`` slot. Once an
    admin reassigns or releases that card (or a worker claims it), the slot source
    changes to a native A+ source such as ``admin_assignment``. A later WIW sync
    still saves the legacy ``Shift.worker`` value from WIW. Previously this signal
    then copied that old worker back into the slot, undoing the admin's change.

    For a locally managed card the slot is the source of truth. Repair the legacy
    Shift mirror with a queryset update (so this post-save signal does not recurse)
    and leave the slot untouched.
    """
    if slot.source in {'wiw', 'migration', 'system'}:
        return False

    claimed = slot.status == ShiftSlot.Status.CLAIMED and slot.worker_id is not None
    expected_worker_id = slot.worker_id if claimed else None
    expected_status = instance.status
    if instance.status not in {Shift.Status.CANCELLED, Shift.Status.COMPLETED, Shift.Status.DRAFT}:
        expected_status = Shift.Status.CONFIRMED if claimed else Shift.Status.PUBLISHED
    expected_is_open = expected_status == Shift.Status.PUBLISHED and not claimed

    updates = {}
    if instance.worker_id != expected_worker_id:
        updates['worker_id'] = expected_worker_id
    if instance.status != expected_status:
        updates['status'] = expected_status
    if instance.is_open != expected_is_open:
        updates['is_open'] = expected_is_open
    if updates:
        updates['updated_at'] = timezone.now()
        Shift.objects.filter(pk=instance.pk).update(**updates)

    # The WIW synchronizer keeps the just-saved ORM object in its dependency
    # cache. Align that in-memory mirror too, not only the database row.
    instance.worker_id = expected_worker_id
    instance.status = expected_status
    instance.is_open = expected_is_open
    return True


@receiver(post_save, sender=Shift)
def ensure_shift_capacity(sender, instance, raw=False, **kwargs):
    if raw:
        return
    requested = max(1, int(instance.required_count or 1))
    active = list(instance.slots.exclude(status=ShiftSlot.Status.CANCELLED).order_by('created_at'))
    source = 'wiw' if instance.wiw_shift_id else 'system'
    if len(active) < requested:
        for index in range(requested - len(active)):
            external_id = None
            if instance.wiw_shift_id and not active and index == 0:
                _reserve_wiw_slot_identity(instance)
                external_id = instance.wiw_shift_id
            slot = ShiftSlot.objects.create(
                shift=instance,
                source=source,
                wiw_shift_id=external_id,
            )
            active.append(slot)
    elif len(active) > requested:
        extras = [slot for slot in reversed(active) if slot.status == ShiftSlot.Status.OPEN][: len(active) - requested]
        if extras:
            ShiftSlot.objects.filter(pk__in=[slot.pk for slot in extras]).update(status=ShiftSlot.Status.CANCELLED)
            active = list(instance.slots.exclude(status=ShiftSlot.Status.CANCELLED).order_by('created_at'))

    if instance.wiw_shift_id and requested == 1 and active:
        slot = active[0]
        _reserve_wiw_slot_identity(instance, slot)

        # Once A+ explicitly manages this card, WIW may continue refreshing
        # schedule metadata but must never take the assignment back.
        if _restore_locally_managed_slot_state(instance, slot):
            return

        if instance.worker_id:
            changed = (
                slot.worker_id != instance.worker_id
                or slot.status != ShiftSlot.Status.CLAIMED
                or slot.wiw_shift_id != instance.wiw_shift_id
                or slot.source != 'wiw'
            )
            if changed:
                slot.worker_id = instance.worker_id
                slot.status = ShiftSlot.Status.CLAIMED
                slot.source = 'wiw'
                slot.wiw_shift_id = instance.wiw_shift_id
                slot.claimed_at = slot.claimed_at or timezone.now()
                slot.save(update_fields=['worker', 'status', 'source', 'wiw_shift_id', 'claimed_at', 'updated_at'])
        elif slot.source in {'wiw', 'migration', 'system'}:
            changed = (
                slot.worker_id is not None
                or slot.status != ShiftSlot.Status.OPEN
                or slot.wiw_shift_id != instance.wiw_shift_id
                or slot.source != 'wiw'
            )
            if changed:
                slot.worker = None
                slot.status = ShiftSlot.Status.OPEN
                slot.source = 'wiw'
                slot.wiw_shift_id = instance.wiw_shift_id
                slot.released_at = timezone.now()
                slot.save(update_fields=['worker', 'status', 'source', 'wiw_shift_id', 'released_at', 'updated_at'])