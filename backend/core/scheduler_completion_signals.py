from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Shift
from .scheduler_completion_models import ShiftConfirmation
from .scheduler_completion_service import sync_shift_confirmations
from .shift_slots import ShiftSlot


@receiver(post_save, sender=Shift)
def sync_confirmations_after_shift_change(sender, instance, **kwargs):
    if instance.status in {Shift.Status.PUBLISHED, Shift.Status.CONFIRMED}:
        sync_shift_confirmations(instance)
    elif instance.status in {Shift.Status.DRAFT, Shift.Status.CANCELLED, Shift.Status.COMPLETED}:
        ShiftConfirmation.objects.filter(shift=instance).delete()


@receiver(post_save, sender=ShiftSlot)
def sync_confirmation_after_slot_change(sender, instance, **kwargs):
    if instance.status == ShiftSlot.Status.CLAIMED and instance.worker_id:
        sync_shift_confirmations(instance.shift)
    else:
        ShiftConfirmation.objects.filter(slot=instance).delete()
