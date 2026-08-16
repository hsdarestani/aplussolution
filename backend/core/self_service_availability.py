from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db import transaction

from .models import Availability
from .self_service_models import AvailabilityPreferenceSeries, AvailabilitySeriesOccurrence
from .self_service_service import _date_matches_series
from .workplace_models import WorkplaceSettings


def _workplace_zone():
    try:
        return ZoneInfo(WorkplaceSettings.load().timezone or 'Europe/Berlin')
    except Exception:
        return ZoneInfo('Europe/Berlin')


def clear_materialized_availability(series: AvailabilityPreferenceSeries):
    Availability.objects.filter(preference_occurrence__series=series).delete()


@transaction.atomic
def sync_materialized_availability(series: AvailabilityPreferenceSeries):
    """Keep legacy Availability rows in sync so every existing scheduler path
    automatically respects recurring Unavailable preferences.
    """
    clear_materialized_availability(series)
    if not series.active or series.kind != AvailabilityPreferenceSeries.Kind.UNAVAILABLE:
        return 0
    zone = _workplace_zone()
    day = series.starts_on
    created = 0
    while day <= series.ends_on:
        if _date_matches_series(series, day):
            if series.all_day:
                starts_at = datetime.combine(day, time.min, tzinfo=zone)
                ends_at = datetime.combine(day + timedelta(days=1), time.min, tzinfo=zone)
            else:
                starts_at = datetime.combine(day, series.start_time, tzinfo=zone)
                end_day = day if series.end_time > series.start_time else day + timedelta(days=1)
                ends_at = datetime.combine(end_day, series.end_time, tzinfo=zone)
            availability = Availability.objects.create(
                worker=series.worker,
                starts_at=starts_at,
                ends_at=ends_at,
                available=False,
                note=series.note,
            )
            AvailabilitySeriesOccurrence.objects.create(
                series=series,
                availability=availability,
                occurrence_date=day,
            )
            created += 1
        day += timedelta(days=1)
    return created
