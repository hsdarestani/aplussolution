import json
from datetime import datetime, time, timedelta
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from core.forecast_models import ForecastDayBudget, ForecastPositionRequirement, ForecastUnitDay, ForecastUnitDefinition
from core.models import Shift
from core.scheduling_models import ScheduleGroup
from core.shift_slots import ShiftSlot


def aware(day, hour, minute=0):
    return timezone.make_aware(datetime.combine(day, time(hour, minute)), timezone.get_current_timezone())


@pytest.mark.django_db
def test_forecast_splits_overnight_shift_and_break_between_days(auth_admin, worker_user, company, location, position):
    today = timezone.localdate() + timedelta(days=10)
    schedule = ScheduleGroup.objects.create(name='Forecast Frankfurt')
    schedule.locations.add(location)
    shift = Shift.objects.create(
        client=company,
        location=location,
        position=position,
        starts_at=aware(today, 22),
        ends_at=aware(today + timedelta(days=1), 2),
        required_count=2,
        break_minutes=60,
        status=Shift.Status.PUBLISHED,
        is_open=True,
    )
    slot = shift.slots.first()
    slot.worker = worker_user.worker_profile
    slot.status = ShiftSlot.Status.CLAIMED
    slot.save(update_fields=['worker', 'status', 'updated_at'])

    ForecastDayBudget.objects.create(
        schedule=schedule,
        date=today,
        sales_budget=Decimal('1000'),
        labor_percent_target=Decimal('20'),
        hours_budget=Decimal('4'),
    )
    unit = ForecastUnitDefinition.objects.create(schedule=schedule, name='Gäste', unit_label='Gäste', mode='hours')
    ForecastPositionRequirement.objects.create(
        definition=unit,
        position=position,
        units_basis=Decimal('100'),
        required_value=Decimal('2'),
    )
    ForecastUnitDay.objects.create(definition=unit, date=today, projected_units=Decimal('200'))

    response = auth_admin.get(
        f'/api/scheduling/forecast/?schedule={schedule.id}&start={today.isoformat()}&end={(today + timedelta(days=2)).isoformat()}'
    )
    assert response.status_code == 200
    first, second = response.data['days']
    assert Decimal(first['combined_hours']) == Decimal('3.00')
    assert Decimal(first['assigned_hours']) == Decimal('1.50')
    assert Decimal(first['assigned_labor_cost']) == Decimal('21.75')
    assert Decimal(first['labor_budget']) == Decimal('200.00')
    assert Decimal(first['hours_variance']) == Decimal('1.00')
    custom = first['custom_units'][0]['requirements'][0]
    assert Decimal(custom['required']) == Decimal('4.00')
    assert Decimal(custom['scheduled']) == Decimal('3.00')
    assert Decimal(custom['variance']) == Decimal('-1.00')
    assert Decimal(second['combined_hours']) == Decimal('3.00')
    assert Decimal(second['assigned_hours']) == Decimal('1.50')


@pytest.mark.django_db
def test_forecast_csv_import_accepts_german_decimal_format(auth_admin, location):
    schedule = ScheduleGroup.objects.create(name='Import Schedule')
    schedule.locations.add(location)
    content = 'Datum;Umsatz;Stunden;Labor\n18.08.2026;1.234,56;40,5;22,75\n'
    upload = SimpleUploadedFile('forecast.csv', content.encode('utf-8'), content_type='text/csv')
    mapping = {
        'date': 'Datum',
        'sales_budget': 'Umsatz',
        'hours_budget': 'Stunden',
        'labor_percent_target': 'Labor',
    }
    response = auth_admin.post(
        '/api/scheduling/forecast/import/apply/',
        {'file': upload, 'schedule': str(schedule.id), 'mapping': json.dumps(mapping)},
        format='multipart',
    )
    assert response.status_code == 200
    assert response.data['created'] == 1
    assert response.data['errors'] == []
    row = ForecastDayBudget.objects.get(schedule=schedule)
    assert row.sales_budget == Decimal('1234.56')
    assert row.hours_budget == Decimal('40.50')
    assert row.labor_percent_target == Decimal('22.75')


@pytest.mark.django_db
def test_forecast_import_preview_rejects_unsupported_file(auth_admin):
    upload = SimpleUploadedFile('forecast.txt', b'hello', content_type='text/plain')
    response = auth_admin.post('/api/scheduling/forecast/import/preview/', {'file': upload}, format='multipart')
    assert response.status_code == 400
    assert 'CSV' in response.data['detail']


@pytest.mark.django_db
def test_forecast_unit_requirements_can_be_updated_without_recreating_definition(auth_admin, location, position):
    schedule = ScheduleGroup.objects.create(name='Units Schedule')
    schedule.locations.add(location)
    unit = ForecastUnitDefinition.objects.create(schedule=schedule, name='Tickets', unit_label='Tickets', mode='shifts')
    response = auth_admin.patch(
        f'/api/forecast-units/{unit.id}/',
        {
            'requirements': [
                {'position': str(position.id), 'units_basis': '250', 'required_value': '1'},
            ]
        },
        format='json',
    )
    assert response.status_code == 200
    unit.refresh_from_db()
    requirement = unit.requirements.get()
    assert requirement.position == position
    assert requirement.units_basis == Decimal('250')
    assert requirement.required_value == Decimal('1')
