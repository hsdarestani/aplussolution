from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

from .self_service_availability import clear_materialized_availability, sync_materialized_availability
from .self_service_models import AvailabilityPreferenceSeries


@receiver(post_save, sender=AvailabilityPreferenceSeries)
def sync_series_occurrences(sender, instance, raw=False, **kwargs):
    if raw:
        return
    sync_materialized_availability(instance)


@receiver(pre_delete, sender=AvailabilityPreferenceSeries)
def remove_series_occurrences(sender, instance, **kwargs):
    clear_materialized_availability(instance)
