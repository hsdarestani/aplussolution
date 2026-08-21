from decimal import Decimal

import pytest

from core.models import WorkingTimeSetting


@pytest.mark.django_db
def test_working_time_settings_update_master_data_used_by_forecast(auth_admin, worker_user):
    worker = worker_user.worker_profile
    worker.extra_allowance = Decimal('2.00')
    worker.save(update_fields=['extra_allowance', 'updated_at'])

    response = auth_admin.post(
        '/api/working-time/settings/',
        {
            'employees': [{
                'worker_id': str(worker.id),
                'monthly_limit': '90.00',
                'hourly_rate': '18.00',
                'active': True,
                'excluded': False,
            }],
        },
        format='json',
    )
    assert response.status_code == 200

    worker.refresh_from_db()
    setting = WorkingTimeSetting.objects.get(worker=worker)
    assert worker.monthly_hours == Decimal('90.00')
    assert worker.tariff_hourly_rate == Decimal('18.00')
    assert setting.monthly_limit == Decimal('90.00')
    assert setting.hourly_rate == Decimal('18.00')
    assert worker.tariff_hourly_rate + worker.extra_allowance == Decimal('20.00')
