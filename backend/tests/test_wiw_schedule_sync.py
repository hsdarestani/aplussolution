from datetime import datetime, timedelta, timezone as datetime_timezone
from unittest.mock import Mock

import pytest

from core.wiw_schedule_sync import (
    SCHEDULE_LOOKAHEAD_DAYS,
    SCHEDULE_LOOKBACK_DAYS,
    SCHEDULE_PAGE_LIMIT,
    WhenIWorkSynchronizer,
    _ScheduleWindowClient,
)


@pytest.mark.django_db
def test_operational_sync_refreshes_future_and_open_shifts_without_incremental_cutoff():
    client = Mock()
    client.collection.side_effect = lambda name, params=None, optional=False: type('Result', (), {'items': []})()

    # Seed a previous successful run so the base incremental synchronizer would
    # normally send updated_since. Schedule synchronization must not use that
    # cutoff, otherwise already-created shifts can be permanently stranded.
    first = WhenIWorkSynchronizer(client=client).sync('incremental')
    assert first.status == 'success'

    second_sync = WhenIWorkSynchronizer(client=client)
    second = second_sync.sync('incremental')
    assert second.status == 'success'

    shift_calls = [call for call in client.collection.call_args_list if call.args[0] == 'shifts']
    params = shift_calls[-1].kwargs['params']

    assert 'updated_since' not in params
    assert params['include_open'] == 'true'
    assert params['include_allopen'] == 'true'
    assert params['all_locations'] == 'true'
    assert params['limit'] == SCHEDULE_PAGE_LIMIT

    start = datetime.fromisoformat(params['start'])
    end = datetime.fromisoformat(params['end'])
    assert second_sync.now - start >= timedelta(days=SCHEDULE_LOOKBACK_DAYS) - timedelta(seconds=1)
    assert end - second_sync.now >= timedelta(days=SCHEDULE_LOOKAHEAD_DAYS) - timedelta(seconds=1)


def test_dense_shift_window_is_split_instead_of_silently_accepting_limit():
    client = Mock()
    shift_calls = []

    def collection(name, params=None, optional=False):
        assert name == 'shifts'
        shift_calls.append(dict(params or {}))
        if len(shift_calls) == 1:
            rows = [{'id': str(index)} for index in range(SCHEDULE_PAGE_LIMIT)]
        else:
            rows = [{'id': f'child-{len(shift_calls)}'}]
        return type('Result', (), {'items': rows, 'status_code': 200})()

    client.collection.side_effect = collection
    wrapper = _ScheduleWindowClient(
        client,
        datetime(2026, 9, 5, 12, 0, tzinfo=datetime_timezone.utc),
    )

    result = wrapper.collection('shifts', params={'updated_since': 'must-be-removed'})

    assert len(shift_calls) == 3
    assert [item['id'] for item in result.items] == ['child-2', 'child-3']
    for params in shift_calls:
        assert 'updated_since' not in params
        assert params['include_open'] == 'true'
        assert params['include_allopen'] == 'true'
        assert params['all_locations'] == 'true'
        assert params['limit'] == SCHEDULE_PAGE_LIMIT
