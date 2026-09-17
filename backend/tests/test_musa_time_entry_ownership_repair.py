import importlib
from datetime import timedelta

import pytest
from django.apps import apps as django_apps
from django.utils import timezone

from core.models import AuditLog, ClientCompany, Location, Position, Shift, TimeEntry, User, WorkerProfile
from core.shift_slots import ShiftSlot


@pytest.mark.django_db
def test_musa_repair_restores_only_entries_with_positive_original_worker_evidence():
    musa_user = User.objects.create_user(
        'mussajamali@hotmail.de',
        'StrongPass123!',
        first_name='Musa',
        last_name='Jamali',
        role=User.Role.WORKER,
        is_onboarded=True,
    )
    musa = WorkerProfile.objects.create(
        user=musa_user,
        employee_number='53560424',
        wiw_user_id='wiw-musa',
    )

    coworker_user = User.objects.create_user(
        'coworker@example.com',
        'StrongPass123!',
        first_name='Anna',
        last_name='Becker',
        role=User.Role.WORKER,
        is_onboarded=True,
    )
    coworker = WorkerProfile.objects.create(
        user=coworker_user,
        employee_number='MA-COWORKER',
        wiw_user_id='wiw-coworker',
    )

    client = ClientCompany.objects.create(name='Shared Shift Client', customer_number='KD-MUSA-REPAIR')
    location = Location.objects.create(client=client, name='Shared Location', address='Frankfurt')
    position = Position.objects.create(name='Shared Repair Position')
    start = timezone.now() - timedelta(days=2)
    shift = Shift.objects.create(
        client=client,
        location=location,
        position=position,
        starts_at=start,
        ends_at=start + timedelta(hours=6),
        status=Shift.Status.CONFIRMED,
        required_count=2,
    )
    slots = list(ShiftSlot.objects.filter(shift=shift).order_by('created_at'))
    slots[0].worker = musa
    slots[0].status = ShiftSlot.Status.CLAIMED
    slots[0].save(update_fields=['worker', 'status', 'updated_at'])
    slots[1].worker = coworker
    slots[1].status = ShiftSlot.Status.CLAIMED
    slots[1].save(update_fields=['worker', 'status', 'updated_at'])

    # Simulate the production contamination pattern from the old 0037 code: a
    # coworker's native attendance row on a shared shift was reassigned to Musa.
    native_entry = TimeEntry.objects.create(
        worker=musa,
        shift=shift,
        clock_in=start,
        clock_out=start + timedelta(hours=6),
    )
    AuditLog.objects.create(
        actor=coworker_user,
        action='time.clock_in',
        object_type='TimeEntry',
        object_id=str(native_entry.pk),
    )

    # Imported WIW rows carry the external user id, which is also positive
    # identity evidence and must restore the correct coworker independently.
    imported_entry = TimeEntry.objects.create(
        worker=musa,
        shift=shift,
        clock_in=start - timedelta(days=1),
        clock_out=start - timedelta(days=1) + timedelta(hours=5),
        wiw_time_id='wiw-time-coworker',
        wiw_payload={'user_id': 'wiw-coworker'},
    )

    legitimate_musa_entry = TimeEntry.objects.create(
        worker=musa,
        shift=shift,
        clock_in=start + timedelta(minutes=15),
        clock_out=start + timedelta(hours=5),
    )
    AuditLog.objects.create(
        actor=musa_user,
        action='time.clock_in',
        object_type='TimeEntry',
        object_id=str(legitimate_musa_entry.pk),
    )

    migration = importlib.import_module('core.migrations.0039_repair_musa_time_entry_ownership')
    migration.repair_musa_time_entry_ownership(django_apps, None)

    native_entry.refresh_from_db()
    imported_entry.refresh_from_db()
    legitimate_musa_entry.refresh_from_db()

    assert native_entry.worker_id == coworker.id
    assert imported_entry.worker_id == coworker.id
    assert legitimate_musa_entry.worker_id == musa.id

    repair_audit = AuditLog.objects.filter(action='repair_musa_time_entry_ownership').latest('created_at')
    assert repair_audit.metadata['repaired_count'] == 2
    assert repair_audit.metadata['ambiguous_count'] == 0
