from datetime import date, datetime
from unittest.mock import Mock

import pytest

from core.wiw import WhenIWorkError
from core.wiw_migration import (
    MAX_DYNAMIC_WINDOW_DAYS,
    _assert_dynamic_probe_is_in_snapshot,
    _fetch_dynamic_range,
)


def test_dynamic_history_is_proactively_split_into_bounded_datetime_windows():
    client = Mock()
    calls = []
    target = date(2026, 8, 21)

    def collection(resource, params=None, optional=False):
        assert resource == 'shifts'
        calls.append(dict(params or {}))
        start = datetime.fromisoformat(params['start'].replace('Z', '+00:00')).date()
        end = datetime.fromisoformat(params['end'].replace('Z', '+00:00')).date()
        rows = [{'id': 'live-shift'}] if start <= target <= end else []
        return type('Result', (), {'items': rows})()

    client.collection.side_effect = collection
    rows = _fetch_dynamic_range(client, 'shifts', date(2024, 1, 1), date(2028, 1, 1))

    assert rows == [{'id': 'live-shift'}]
    assert len(calls) > 1
    for params in calls:
        start = datetime.fromisoformat(params['start'].replace('Z', '+00:00')).date()
        end = datetime.fromisoformat(params['end'].replace('Z', '+00:00')).date()
        assert (end - start).days <= MAX_DYNAMIC_WINDOW_DAYS
        assert params['start'].endswith('Z')
        assert params['end'].endswith('Z')


def test_dynamic_probe_rejects_silent_empty_history_response():
    client = Mock()
    client.collection.return_value = type('Result', (), {'items': [{'id': 'current-shift'}]})()

    with pytest.raises(WhenIWorkError, match='absent from the bounded history fetch'):
        _assert_dynamic_probe_is_in_snapshot(client, 'shifts', [])


def test_dynamic_probe_accepts_current_row_already_in_history_snapshot():
    client = Mock()
    client.collection.return_value = type('Result', (), {'items': [{'id': 'current-shift'}]})()

    _assert_dynamic_probe_is_in_snapshot(client, 'shifts', [{'id': 'current-shift'}])
