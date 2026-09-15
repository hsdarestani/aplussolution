from io import StringIO
from unittest.mock import patch

from django.conf import settings
from django.core.management import call_command


def test_wiw_sync_is_hard_disabled_and_not_scheduled():
    assert settings.WIW_SYNC_ENABLED is False

    retired_tasks = {
        'core.tasks.sync_when_i_work',
        'core.tasks.reconcile_when_i_work_schedule',
        'core.tasks.reconcile_when_i_work_full',
    }
    scheduled_tasks = {
        entry.get('task')
        for entry in settings.CELERY_BEAT_SCHEDULE.values()
        if isinstance(entry, dict)
    }
    assert retired_tasks.isdisjoint(scheduled_tasks)


def test_sync_wiw_management_command_is_a_noop_after_cutover():
    output = StringIO()
    with patch('core.management.commands.sync_wiw.WhenIWorkSynchronizer') as synchronizer:
        call_command('sync_wiw', stdout=output)

    synchronizer.assert_not_called()
    assert 'dauerhaft deaktiviert' in output.getvalue()
