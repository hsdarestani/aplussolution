from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.core.management import call_command


ROOT = Path(__file__).resolve().parents[2]


def test_wiw_sync_is_hard_disabled_in_production_config_and_not_scheduled():
    # The shared legacy test fixture intentionally enables WIW for historical
    # synchronizer tests, so verify the production source of truth directly.
    config = (ROOT / 'backend' / 'config' / 'settings.py').read_text(encoding='utf-8')
    assert 'WIW_SYNC_ENABLED=False' in config
    assert 'WIW_READ_ONLY=True' in config
    assert "os.getenv('WIW_SYNC_ENABLED'" not in config

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


def test_sync_wiw_management_command_is_unconditional_noop_after_cutover():
    output = StringIO()
    # Guard against regressions even if a stale environment/test fixture says
    # WIW is enabled: the retired command must never instantiate a synchronizer.
    with patch('core.wiw_schedule_sync.WhenIWorkSynchronizer') as synchronizer:
        call_command('sync_wiw', stdout=output)
        call_command('sync_wiw', '--full', stdout=output)

    synchronizer.assert_not_called()
    assert 'dauerhaft deaktiviert' in output.getvalue()


def test_production_deploy_never_queues_wiw_work_after_cutover():
    workflow = (ROOT / '.github' / 'workflows' / 'deploy.yml').read_text(encoding='utf-8')
    forbidden = (
        'core.tasks.sync_when_i_work',
        'core.tasks.reconcile_when_i_work_schedule',
        'core.tasks.reconcile_when_i_work_full',
        'WIW_RECONCILIATION_LOCK_KEY',
    )
    assert all(token not in workflow for token in forbidden)
