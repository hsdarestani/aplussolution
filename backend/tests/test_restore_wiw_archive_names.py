import csv
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from core.models import User, WorkerProfile


def mapping_file(tmp_path, rows):
    filename = tmp_path / 'private-wiw-names.csv'
    with filename.open('w', newline='', encoding='utf-8') as output:
        writer = csv.writer(output)
        writer.writerow(['wiw_user_id', 'first_name', 'last_name'])
        writer.writerows(rows)
    return str(filename)


@pytest.mark.django_db
def test_restore_historical_names_only_with_apply(tmp_path):
    user = User.objects.create_user(
        'wiw-48430862@sync.invalid', password=None,
        wiw_id='48430862', is_active=False, is_onboarded=False,
    )
    worker = WorkerProfile.objects.create(
        user=user, employee_number='WIW-HIST-48430862',
        wiw_user_id='48430862', active=False,
    )
    path = mapping_file(tmp_path, [('48430862', 'Ioana', 'Paius')])
    dry = StringIO()
    call_command('restore_wiw_archive_names', path, stdout=dry)
    user.refresh_from_db()
    assert user.get_full_name() == ''
    assert '"would_update": 1' in dry.getvalue()

    applied = StringIO()
    call_command('restore_wiw_archive_names', path, '--apply', stdout=applied)
    user.refresh_from_db()
    worker.refresh_from_db()
    assert user.get_full_name() == 'Ioana Paius'
    assert not user.is_active
    assert not user.is_onboarded
    assert not user.has_usable_password()
    assert not worker.active
    assert worker.employee_number == 'WIW-HIST-48430862'
    assert worker.wiw_user_id == '48430862'
    assert '"updated": 1' in applied.getvalue()

    rerun = StringIO()
    call_command('restore_wiw_archive_names', path, '--apply', stdout=rerun)
    assert '"already_named": 1' in rerun.getvalue()


@pytest.mark.django_db
def test_restore_does_not_modify_active_or_non_placeholder_workers(tmp_path):
    active = User.objects.create_user(
        'wiw-50509164@sync.invalid', password=None,
        wiw_id='50509164', is_active=True,
    )
    WorkerProfile.objects.create(
        user=active, employee_number='WIW-HIST-50509164',
        wiw_user_id='50509164', active=True,
    )
    regular = User.objects.create_user(
        'archive@example.com', password=None,
        wiw_id='50431492', is_active=False,
    )
    WorkerProfile.objects.create(
        user=regular, employee_number='WIW-HIST-50431492',
        wiw_user_id='50431492', active=False,
    )
    path = mapping_file(tmp_path, [
        ('50509164', 'Isra', 'Bouzayen'),
        ('50431492', 'Saaid', 'Aldarwish'),
    ])
    log = StringIO()
    call_command('restore_wiw_archive_names', path, '--apply', stdout=log)
    active.refresh_from_db()
    regular.refresh_from_db()
    assert not active.get_full_name()
    assert not regular.get_full_name()
    assert '"skipped_active": 1' in log.getvalue()
    assert '"skipped_not_archival": 1' in log.getvalue()


@pytest.mark.django_db
def test_restore_rejects_bad_csv_and_conflicts(tmp_path):
    path = mapping_file(tmp_path, [('0', 'Unknown', 'Person')])
    with pytest.raises(CommandError):
        call_command('restore_wiw_archive_names', path, '--apply')
    path = mapping_file(tmp_path, [
        ('48430862', 'Ioana', 'Paius'),
        ('48430862', 'Other', 'Person'),
    ])
    with pytest.raises(CommandError):
        call_command('restore_wiw_archive_names', path, '--apply')
