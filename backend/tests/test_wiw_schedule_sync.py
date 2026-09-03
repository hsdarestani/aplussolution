from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest

from core.wiw_schedule_sync import SCHEDULE_LOOKAHEAD_DAYS, WhenIWorkSynchronizer


@pytest.mark.django_db
def test_operational_sync_refreshes_future_and_open_shifts_without_incremental_cutoff():
    client = Mock()
    client.collection.side_effect = lambda name, params=None, optional=False: type('Result', (), {'items': []})()

    # Seed a previous successful run so the base incremental synchronizer would
    # normally send updated_since. Future schedule synchronization must not use
    # that cutoff, otherwise already-created shifts for next week can be missed.
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
    assert params['limit'] == 500

    start = datetime.fromisoformat(params['start'])
    end = datetime.fromisoformat(params['end'])
    assert start <= second_sync.now
    assert end - second_sync.now >= timedelta(days=SCHEDULE_LOOKAHEAD_DAYS) - timedelta(seconds=1)
