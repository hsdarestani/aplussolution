from __future__ import annotations

from .models import Position
from . import wiw_sync


_INSTALLED_ATTR = '_aplus_local_position_state_protection_installed'


def install_wiw_position_protection() -> None:
    """Keep A+ position activation state authoritative over WIW.

    WIW is allowed to provide the initial active/inactive state for a position
    that does not exist locally yet. Once a Position exists in A+, its active
    flag is business-owned and Settings changes must survive every later WIW
    synchronization.
    """
    synchronizer = wiw_sync.WhenIWorkSynchronizer
    if getattr(synchronizer, _INSTALLED_ATTR, False):
        return

    original = synchronizer.sync_positions

    def sync_positions_preserving_local_state(self, items):
        local_state = dict(Position.objects.values_list('pk', 'active'))

        original(self, items)

        if not local_state:
            return

        active_ids = [pk for pk, active in local_state.items() if active]
        inactive_ids = [pk for pk, active in local_state.items() if not active]

        if active_ids:
            Position.objects.filter(pk__in=active_ids).exclude(active=True).update(active=True)
        if inactive_ids:
            Position.objects.filter(pk__in=inactive_ids).exclude(active=False).update(active=False)

        # Keep the synchronizer's in-memory cache consistent with the restored
        # database state for the remainder of the same sync transaction.
        for position in self.positions.values():
            if position.pk in local_state:
                position.active = local_state[position.pk]

    synchronizer.sync_positions = sync_positions_preserving_local_state
    setattr(synchronizer, _INSTALLED_ATTR, True)
