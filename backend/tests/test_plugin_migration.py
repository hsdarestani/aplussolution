from datetime import date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from django.utils import timezone

from core.models import (
    Contract,
    EmployeeMasterData,
    Shift,
    ShiftImportPackage,
    ShiftImportRevision,
    WorkingTimeAccountRecord,
    WorkingTimeSetting,
)
from core.order_automation import (
    approve_order,
    extract_request_id,
    fallback_request_id,
    generate_client_contract,
    parse_order_text,
)
from core.working_time import entry_hours, sync_working_time, update_record


class FakeWIW:
    def __init__(self):
        self.created = []
        self.deleted = []

    def collection(self, name, params=None, optional=False):
        rows = {
            'locations': [{'id': 30, 'name': 'Frankfurt'}],
            'positions': [{'id': 20, 'name': 'Servicekraft'}],
            'sites': [{'id': 10, 'name': 'Kunde GmbH'}],
            'shifts': [],
        }.get(name, [])
        return SimpleNamespace(items=rows)

    def post(self, path, payload=None, params=None):
        if path == '/shifts':
            identifier = 100 + len(self.created)
            self.created.append((identifier, payload))
            return {'shift': {'id': identifier}}
        return {}

    def delete(self, path, params=None):
        self.deleted.append(path)
        return {}


@pytest.mark.django_db
def test_order_number_extraction_and_fallback_are_stable():
    assert extract_request_id('Auftragsnummer: EVT-2026/77') == 'EVT-2026/77'
    parsed = {'shifts': [{'site_text': 'Kunde', 'location_text': 'Frankfurt', 'date': '2026-08-01', 'notes': 'Gala'}]}
    assert fallback_request_id(parsed) == fallback_request_id(parsed)
    assert fallback_request_id(parsed).startswith('AUTO-')


@pytest.mark.django_db
def test_ai_order_parser_validates_json(settings):
    settings.WIW_OPENAI_KEY = 'secret'
    settings.WIW_OPENAI_MODEL = 'gpt-test'
    response = Mock(ok=True)
    response.json.return_value = {'choices': [{'message': {'content': '{"contract_no":"A-9","shifts":[{"role":"Servicekraft","date":"2026-08-01","start_time":"18:00","end_time":"02:00","count":2,"location_text":"Frankfurt","site_text":"Kunde GmbH","site_address":"Main 1","notes":"Gala"}]}'}}]}
    session = Mock()
    session.post.return_value = response
    result = parse_order_text('Auftrag A-9', session=session)
    assert result['contract_no'] == 'A-9'
    assert result['shifts'][0]['count'] == 2
    assert result['shifts'][0]['end_time'] == '02:00'
    assert session.post.call_args.kwargs['headers']['Authorization'] == 'Bearer secret'


@pytest.mark.django_db
def test_approve_order_creates_biddable_wiw_shifts_and_revision(admin_user, company, position, location, settings):
    location.wiw_location_id = '30'
    location.save()
    position.wiw_position_id = '20'
    position.save()
    fake = FakeWIW()
    parsed = {'contract_no': 'EVT-77', 'shifts': [{'role': 'Servicekraft', 'date': '2026-08-01', 'start_time': '18:00', 'end_time': '23:00', 'count': 2, 'location_text': 'Frankfurt', 'site_text': 'Kunde GmbH', 'site_address': company.address, 'notes': 'Gala'}]}
    result = approve_order(parsed, 'Auftragsnummer EVT-77', actor=admin_user, client_id=company.id, wiw_client=fake)
    assert result['created_count'] == 2
    assert ShiftImportPackage.objects.filter(request_id='EVT-77').exists()
    assert ShiftImportRevision.objects.filter(package__request_id='EVT-77', version=1).exists()
    assert Shift.objects.filter(wiw_shift_id__in=['100', '101'], is_open=True).count() == 2
    assert all(payload['is_biddable'] is True and payload['published'] is True for _, payload in fake.created)
    unchanged = approve_order(parsed, 'Auftragsnummer EVT-77', actor=admin_user, client_id=company.id, wiw_client=fake)
    assert unchanged['status'] == 'unchanged'
    assert len(fake.created) == 2


@pytest.mark.django_db
def test_client_contract_requires_assigned_worker(admin_user, worker_user, company, position, location):
    location.wiw_location_id = '30'
    location.save()
    position.wiw_position_id = '20'
    position.save()
    fake = FakeWIW()
    parsed = {'contract_no': 'EVT-88', 'shifts': [{'role': 'Servicekraft', 'date': '2026-08-01', 'start_time': '18:00', 'end_time': '23:00', 'count': 1, 'location_text': 'Frankfurt', 'site_text': 'Kunde GmbH', 'site_address': company.address, 'notes': 'Gala'}]}
    approve_order(parsed, 'Auftragsnummer EVT-88', actor=admin_user, client_id=company.id, wiw_client=fake)
    package = ShiftImportPackage.objects.get(request_id='EVT-88')
    with pytest.raises(ValueError):
        generate_client_contract(package, actor=admin_user)
    shift = Shift.objects.get(wiw_shift_id='100')
    shift.worker = worker_user.worker_profile
    shift.save()
    EmployeeMasterData.objects.create(worker=worker_user.worker_profile, data={'birth_date': '1990-01-01'})
    contract = generate_client_contract(package, actor=admin_user)
    assert contract.status == Contract.Status.READY
    assert contract.pdf.name.endswith('.pdf')
    package.refresh_from_db()
    assert package.status == ShiftImportPackage.Status.GENERATED


@pytest.mark.django_db
def test_working_time_hours_deduct_unpaid_break():
    hours, start, end = entry_hours({
        'start_time': '2026-01-10T08:00:00+01:00',
        'end_time': '2026-01-10T16:30:00+01:00',
        'breaks': [{'paid': False, 'length': 30}],
    })
    assert hours == Decimal('8.00')
    assert start and end


@pytest.mark.django_db
def test_working_time_sync_preserves_manual_values(worker_user, settings):
    worker = worker_user.worker_profile
    worker.wiw_user_id = '10'
    worker.save()
    WorkingTimeSetting.objects.create(worker=worker, monthly_limit='10', hourly_rate='15')
    client = Mock()
    client.get.return_value = {'times': [{'id': 1, 'user_id': 10, 'start_time': '2026-01-05T08:00:00+01:00', 'end_time': '2026-01-05T20:00:00+01:00'}]}
    first = sync_working_time(date(2026, 1, 1), date(2026, 1, 31), client=client)
    assert first.records_count == 1
    row = WorkingTimeAccountRecord.objects.get(worker=worker, year_month=date(2026, 1, 1))
    assert row.ist_hours == Decimal('12.00')
    assert row.difference_hours == Decimal('2.00')
    assert row.saldo_cumulative == Decimal('2.00')
    update_record(row, paid_hours='1', manual_adjustment='0.5')
    second = sync_working_time(date(2026, 1, 1), date(2026, 1, 31), client=client)
    row.refresh_from_db()
    assert second.records_count == 1
    assert row.paid_hours == Decimal('1.00')
    assert row.manual_adjustment == Decimal('0.50')
    assert row.saldo_cumulative == Decimal('1.50')


@pytest.mark.django_db
def test_migrated_endpoints_require_manager(auth_worker, auth_admin):
    assert auth_worker.get('/api/automation/orders/packages/').status_code == 403
    assert auth_worker.get('/api/working-time/settings/').status_code == 403
    assert auth_admin.get('/api/automation/orders/packages/').status_code == 200
    assert auth_admin.get('/api/working-time/settings/').status_code == 200
