from __future__ import annotations

from django.db.models import Q

from . import wiw_sync
from .models import Location, Position, Shift, WorkerProfile


_INSTALLED_ATTR = '_aplus_exact_shift_dedup_installed'


def _effective_worker_matches(shift: Shift, worker: WorkerProfile | None) -> bool:
    claimed_ids = set(
        shift.slots.filter(status='claimed', worker__isnull=False)
        .values_list('worker_id', flat=True)
    )
    if worker is None:
        return (
            shift.worker_id is None
            and not claimed_ids
            and shift.slots.filter(status='open', worker__isnull=True).exists()
        )
    if claimed_ids:
        return claimed_ids == {worker.pk}
    return shift.worker_id == worker.pk


def _bind_exact_local_shift(self, item, default_position) -> bool:
    """Attach an incoming WIW id to one identical unlinked A+ shift.

    A shift is identical by operational schedule identity: canonical client/location,
    position, start/end, break, status and effective worker/OpenShift assignment.
    Free-form notes are deliberately not identity: a harmless WIW description must
    not create a second card for the same actual shift.
    """
    wiw_id = wiw_sync.as_id(wiw_sync.first(item, 'id', 'shift_id'))
    if not wiw_id or Shift.objects.filter(wiw_shift_id=wiw_id).exists():
        return False

    user_id = wiw_sync.as_id(wiw_sync.first(item, 'user_id', 'user'))
    location_id = wiw_sync.as_id(wiw_sync.first(item, 'location_id', 'location'))
    site_id = wiw_sync.as_id(wiw_sync.first(item, 'site_id', 'site'))
    position_id = wiw_sync.as_id(wiw_sync.first(item, 'position_id', 'position'))

    worker = self.workers.get(user_id) or WorkerProfile.objects.filter(wiw_user_id=user_id).first()
    location = self.locations.get(f'site:{site_id}') or self.locations.get(location_id)
    location = (
        location
        or Location.objects.filter(wiw_site_id=site_id).first()
        or Location.objects.filter(wiw_location_id=location_id).first()
    )
    if not location:
        return False

    position = (
        self.positions.get(position_id)
        or Position.objects.filter(wiw_position_id=position_id).first()
        or default_position
    )
    starts_at = wiw_sync.as_datetime(wiw_sync.first(item, 'start_time', 'start', 'starts_at'))
    ends_at = wiw_sync.as_datetime(wiw_sync.first(item, 'end_time', 'end', 'ends_at'))
    if not starts_at or not ends_at:
        return False

    break_minutes = int(wiw_sync.first(item, 'break_minutes', 'break', default=0) or 0)
    published = bool(wiw_sync.first(item, 'published', default=True))
    desired_status = (
        Shift.Status.CONFIRMED
        if worker
        else (Shift.Status.PUBLISHED if published else Shift.Status.DRAFT)
    )

    candidates = (
        Shift.objects.filter(
            Q(wiw_shift_id__isnull=True) | Q(wiw_shift_id=''),
            client=location.client,
            location=location,
            position=position,
            starts_at=starts_at,
            ends_at=ends_at,
            break_minutes=break_minutes,
            status=desired_status,
            required_count=1,
        )
        .exclude(status=Shift.Status.CANCELLED)
        .prefetch_related('slots')
        .order_by('created_at', 'pk')
    )
    exact = next((shift for shift in candidates if _effective_worker_matches(shift, worker)), None)
    if not exact:
        return False

    # Binding before the normal importer runs makes its existing update path reuse
    # this row. The Shift post-save capacity signal also moves the WIW identity to
    # the already-existing slot instead of creating another card.
    exact.wiw_shift_id = wiw_id
    exact.save(update_fields=['wiw_shift_id', 'updated_at'])
    self.counts['shifts_deduplicated'] += 1
    return True


def install_wiw_shift_dedup() -> None:
    """Prevent WIW from duplicating an identical A+-owned shift."""
    synchronizer = wiw_sync.WhenIWorkSynchronizer
    if getattr(synchronizer, _INSTALLED_ATTR, False):
        return

    original = synchronizer.sync_shifts

    def sync_shifts_without_exact_duplicates(self, items):
        rows = list(items)
        default_position, _ = Position.objects.get_or_create(name='WIW Einsatz')
        for item in rows:
            _bind_exact_local_shift(self, item, default_position)
        return original(self, rows)

    synchronizer.sync_shifts = sync_shifts_without_exact_duplicates
    setattr(synchronizer, _INSTALLED_ATTR, True)
