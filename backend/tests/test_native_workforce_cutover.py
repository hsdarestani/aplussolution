from datetime import datetime, time, timedelta
from types import SimpleNamespace

import pytest
from django.utils import timezone

from core.models import Contract, Shift, ShiftImportPackage, TimeEntry, User, WorkingTimeAccountRecord
from core.native_cutover import approve_order, sync_working_time
from core.order_automation import seed_client_contract_template
from core.shift_slots import ShiftSlot
from core.wiw_migration import build_wiw_migration_report


def parsed_order(*, count=3, start='09:00', end='17:00'):
    day = (timezone.localdate() + timedelta(days=2)).isoformat()
    return {
        'contract_no': 'EVT-2026-001',
        'shifts': [{
            'role': 'Servicekraft',
            'date': day,
            'start_time': start,
            'end_time': end,
            'count': count,
            'location_text': 'Messe Frankfurt',
            'site_text': 'Kunde GmbH',
            'site_address': 'Messeplatz 1, Frankfurt',
            'notes': 'Schwarze Hose',
        }],
    }


@pytest.mark.django_db
def test_order_approval_creates_native_capacity_without_wiw(monkeypatch, admin_user, company, location, position):
    class ForbiddenWiwClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError('Operational order flow must not instantiate When I Work.')

    monkeypatch.setattr('core.order_automation.WhenIWorkClient', ForbiddenWiwClient)

    result = approve_order(
        parsed_order(count=3),
        'Vertragsnummer EVT-2026-001\n3 Servicekräfte für die Messe Frankfurt',
        actor=admin_user,
        client_id=str(company.id),
    )

    assert result['source'] == 'aplus'
    assert result['created_count'] == 3
    shift = Shift.objects.get(order_id=result['order_id'])
    assert shift.required_count == 3
    assert shift.wiw_shift_id is None
    assert shift.status == Shift.Status.PUBLISHED
    assert shift.slots.filter(status=ShiftSlot.Status.OPEN, worker__isnull=True).count() == 3
    package = ShiftImportPackage.objects.get(pk=result['package_id'])
    assert package.payload['source_system'] == 'aplus'
    assert package.payload['shifts'][0]['local_shift_id'] == str(shift.id)
    assert package.payload['shifts'][0]['required_count'] == 3


@pytest.mark.django_db
def test_sent_contract_blocks_automatic_order_replacement(admin_user, company, location, position):
    first = approve_order(
        parsed_order(count=2),
        'Vertragsnummer EVT-2026-001\n2 Servicekräfte',
        actor=admin_user,
        client_id=str(company.id),
    )
    package = ShiftImportPackage.objects.get(pk=first['package_id'])
    template = seed_client_contract_template()
    contract = Contract.objects.create(
        template=template,
        client=company,
        title='Rechtsstand EVT-2026-001',
        status=Contract.Status.SENT,
        source_system='aplus',
        created_by=admin_user,
    )
    package.contract = contract
    package.save(update_fields=['contract', 'updated_at'])

    with pytest.raises(ValueError, match='versendeten oder unterzeichneten Vertrag'):
        approve_order(
            parsed_order(count=4, start='10:00', end='18:00'),
            'Vertragsnummer EVT-2026-001\n4 Servicekräfte, geänderte Zeit',
            actor=admin_user,
            client_id=str(company.id),
        )

    assert Shift.objects.filter(order_id=first['order_id']).count() == 1
    assert Shift.objects.get(order_id=first['order_id']).required_count == 2


@pytest.mark.django_db
def test_working_time_uses_local_entries_for_worker_without_wiw_id(worker_user, company, location, position):
    worker = worker_user.worker_profile
    assert not worker.wiw_user_id
    today = timezone.localdate()
    start = timezone.make_aware(datetime.combine(today, time(8, 0)), timezone.get_current_timezone())
    shift = Shift.objects.create(
        client=company,
        location=location,
        position=position,
        starts_at=start,
        ends_at=start + timedelta(hours=4),
        break_minutes=30,
        status=Shift.Status.CONFIRMED,
    )
    TimeEntry.objects.create(
        worker=worker,
        shift=shift,
        clock_in=start,
        clock_out=start + timedelta(hours=4),
        approved=True,
    )

    log = sync_working_time(today, today)
    record = WorkingTimeAccountRecord.objects.get(worker=worker, year_month=today.replace(day=1))
    assert log.metadata['source'] == 'aplus_time_entries'
    assert record.source == 'aplus_time_entries'
    assert record.ist_hours == pytest.approx(3.5)

    record.manual_adjustment = 2
    record.paid_hours = 1
    record.save(update_fields=['manual_adjustment', 'paid_hours', 'updated_at'])
    sync_working_time(today, today)
    record.refresh_from_db()
    assert record.manual_adjustment == 2
    assert record.paid_hours == 1


class FakeWiwClient:
    def __init__(self, resources):
        self.resources = resources

    def collection(self, resource, optional=False, params=None):
        return SimpleNamespace(items=self.resources.get(resource, []))


@pytest.mark.django_db
def test_final_wiw_report_reconciles_external_ids(worker_user):
    worker_user.wiw_id = '101'
    worker_user.save(update_fields=['wiw_id'])
    worker_user.worker_profile.wiw_user_id = '101'
    worker_user.worker_profile.save(update_fields=['wiw_user_id'])
    resources = {
        'users': [{'id': 101}],
        'positions': [],
        'locations': [],
        'sites': [],
        'shifts': [],
        'times': [],
        'availabilities': [],
        'requests': [],
    }
    report = build_wiw_migration_report(client=FakeWiwClient(resources))
    assert report['resources']['users']['matched_count'] == 1
    assert report['resources']['users']['missing_local_count'] == 0
    assert report['cutover_ready'] is True
