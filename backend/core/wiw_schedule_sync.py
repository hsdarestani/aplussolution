from __future__ import annotations

from datetime import timedelta

from .wiw import ResourceResult, WhenIWorkError
from .wiw_sync import WhenIWorkSynchronizer as BaseWhenIWorkSynchronizer


# The five-minute operational sync intentionally covers a generous rolling
# window so a temporary WIW/API failure cannot permanently strand a shift once
# it moves into the past. Complete all-time reconciliation is handled by the
# background history task in core.tasks.
SCHEDULE_LOOKBACK_DAYS = 30
SCHEDULE_LOOKAHEAD_DAYS = 180
SCHEDULE_PAGE_LIMIT = 500
SCHEDULE_SPLIT_MAX_DEPTH = 16


def _shift_identity(item):
    value = item.get('id') or item.get('shift_id')
    return str(value) if value not in (None, '') else None


def _dedupe_shifts(rows):
    result = []
    seen = set()
    for item in rows:
        key = _shift_identity(item)
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        result.append(item)
    return result


class _ScheduleWindowClient:
    """Keep incremental master-data sync while making shift refresh self-healing.

    WIW's plain /shifts response is intentionally short-lived and does not
    include OpenShifts. For shifts we therefore refresh an explicit rolling
    window, include OpenShifts, and never carry ``updated_since`` into that
    request. If WIW returns the configured safety limit, the date range is
    recursively split so a dense schedule cannot be silently truncated at 500
    rows.
    """

    def __init__(self, client, now):
        self._client = client
        self._now = now

    def _shift_collection(self, params, optional, start, end, depth=0):
        shift_params = dict(params or {})
        shift_params.pop('updated_since', None)
        shift_params.update({
            'start': start.isoformat(),
            'end': end.isoformat(),
            'include_open': 'true',
            'include_allopen': 'true',
            'all_locations': 'true',
            'limit': SCHEDULE_PAGE_LIMIT,
        })
        result = self._client.collection('shifts', params=shift_params, optional=optional)
        rows = list(result.items)

        # Hitting the limit means completeness cannot be proven. Split the
        # window until every response is below the cap; refuse to silently
        # accept a still-truncated one-day window.
        if len(rows) >= SCHEDULE_PAGE_LIMIT:
            span = end - start
            if depth >= SCHEDULE_SPLIT_MAX_DEPTH or span <= timedelta(days=1):
                raise WhenIWorkError(
                    'WIW shift window still reaches the 500-row safety limit; '
                    'schedule completeness cannot be guaranteed.'
                )
            midpoint = start + (span / 2)
            left = self._shift_collection(params, optional, start, midpoint, depth + 1)
            right = self._shift_collection(params, optional, midpoint, end, depth + 1)
            return ResourceResult(
                'shifts',
                _dedupe_shifts(left.items + right.items),
                200,
            )

        return ResourceResult('shifts', rows, getattr(result, 'status_code', 200))

    def collection(self, name, params=None, optional=False):
        if name != 'shifts':
            return self._client.collection(name, params=params, optional=optional)

        start = self._now - timedelta(days=SCHEDULE_LOOKBACK_DAYS)
        end = self._now + timedelta(days=SCHEDULE_LOOKAHEAD_DAYS)
        return self._shift_collection(params, optional, start, end)


class WhenIWorkSynchronizer(BaseWhenIWorkSynchronizer):
    """Operational WIW synchronizer with a reliable rolling schedule window."""

    def __init__(self, client=None, triggered_by=None):
        super().__init__(client=client, triggered_by=triggered_by)
        self.client = _ScheduleWindowClient(self.client, self.now)
