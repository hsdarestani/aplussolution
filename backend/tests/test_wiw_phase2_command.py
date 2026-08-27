from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError


@pytest.mark.django_db
def test_phase2_command_refuses_partial_history_import():
    migration = {
        'sync': {'status': 'partial'},
        'cutover_ready': True,
        'resources': {},
    }
    with patch('core.management.commands.reconcile_wiw_history.build_wiw_migration_report', return_value=migration), patch(
        'core.management.commands.reconcile_wiw_history.reconcile_wiw_history_scope'
    ) as reconcile:
        with pytest.raises(CommandError, match='expected success'):
            call_command('reconcile_wiw_history', '--compact')
    reconcile.assert_not_called()


@pytest.mark.django_db
def test_phase2_command_requires_complete_remote_reconciliation():
    migration = {
        'sync': {'status': 'success'},
        'cutover_ready': False,
        'resources': {'times': {'complete': False}, 'shifts': {'complete': True}},
    }
    with patch('core.management.commands.reconcile_wiw_history.build_wiw_migration_report', return_value=migration), patch(
        'core.management.commands.reconcile_wiw_history.reconcile_wiw_history_scope'
    ) as reconcile:
        with pytest.raises(CommandError, match='times'):
            call_command('reconcile_wiw_history', '--compact')
    reconcile.assert_not_called()


@pytest.mark.django_db
def test_phase2_command_accepts_complete_history_and_valid_scope(capsys):
    migration = {
        'sync': {'status': 'success'},
        'cutover_ready': True,
        'resources': {'times': {'complete': True}, 'shifts': {'complete': True}},
    }
    scope = {'valid': True, 'history': {'shifts_before': 4, 'shifts_after': 4, 'time_entries_before': 3, 'time_entries_after': 3}}
    with patch('core.management.commands.reconcile_wiw_history.build_wiw_migration_report', return_value=migration), patch(
        'core.management.commands.reconcile_wiw_history.reconcile_wiw_history_scope', return_value=scope
    ):
        call_command('reconcile_wiw_history', '--compact')
    output = capsys.readouterr().out
    assert '"success": true' in output
    assert 'canonical workforce scope verified' in output
