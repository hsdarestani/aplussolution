from __future__ import annotations

from datetime import timedelta

from .wiw_sync import WhenIWorkSynchronizer as BaseWhenIWorkSynchronizer


SCHEDULE_LOOKBACK_DAYS = 1
SCHEDULE_LOOKAHEAD_DAYS = 28
SCHEDULE_PAGE_LIMIT = 500


class _ScheduleWindowClient:
    """Keep normal incremental WIW sync, but always refresh the future schedule.

    WIW's plain /shifts response is intentionally short-lived and does not
    include OpenShifts.  That is fine for generic incremental resources, but it
    means a shift already created for next week can be visible in the live
    mobile WIW overlay while never reaching the local Shift table used by PDF
    reports.  For the shifts resource only, use an explicit rolling window and
    include OpenShifts.  Do not carry updated_since into this request: a future
    shift may have been created before the previous incremental run and still
    needs to be backfilled when it enters the schedule horizon.
    """

    def __init__(self, client, now):
        self._client = client
        self._now = now

    def collection(self, name, params=None, optional=False):
        if name != 'shifts':
            return self._client.collection(name, params=params, optional=optional)

        shift_params = dict(params or {})
        shift_params.pop('updated_since', None)
        shift_params.update({
            'start': (self._now - timedelta(days=SCHEDULE_LOOKBACK_DAYS)).isoformat(),
            'end': (self._now + timedelta(days=SCHEDULE_LOOKAHEAD_DAYS)).isoformat(),
            'include_open': 'true',
            'include_allopen': 'true',
            'all_locations': 'true',
            'limit': SCHEDULE_PAGE_LIMIT,
        })
        return self._client.collection(name, params=shift_params, optional=optional)


class WhenIWorkSynchronizer(BaseWhenIWorkSynchronizer):
    """Operational WIW synchronizer with a reliable future schedule window."""

    def __init__(self, client=None, triggered_by=None):
        super().__init__(client=client, triggered_by=triggered_by)
        self.client = _ScheduleWindowClient(self.client, self.now)
