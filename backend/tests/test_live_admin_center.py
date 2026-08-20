from datetime import timedelta

import pytest
from django.utils import timezone

from core.models import EmployeeMasterData, IntegrationSyncRun, Shift, TimeEntry


@pytest.mark.django_db
def test_live_admin_center_excludes_imported_wiw_noise(auth_admin, worker_user, company, location, position):
    now = timezone.now()
    worker = worker_user.worker_profile
    worker.wiw_user_id = 'legacy-worker-42'
    worker.save(update_fields=['wiw_user_id', 'updated_at'])

    EmployeeMasterData.objects.create(
        worker=worker,
        completeness=20,
        missing_fields=['iban', 'tax_identification_number'],
    )
    shift = Shift.objects.create(
        client=company,
        location=location,
        position=position,
        starts_at=now - timedelta(hours=2),
        ends_at=now - timedelta(hours=1),
        status=Shift.Status.COMPLETED,
        required_count=1,
        wiw_shift_id='legacy-shift-42',
    )
    TimeEntry.objects.create(
        worker=worker,
        shift=shift,
        clock_in=now - timedelta(hours=2),
        clock_out=now - timedelta(hours=1),
        approved=False,
        wiw_time_id='legacy-time-42',
    )
    IntegrationSyncRun.objects.create(
        provider='wiw',
        status=IntegrationSyncRun.Status.FAILED,
        mode='final_full',
        errors=[{'error': 'historical import issue'}],
    )

    response = auth_admin.get('/api/admin/exceptions/')
    assert response.status_code == 200
    assert response.data['summary']['by_category']['attendance'] == 0
    assert response.data['summary']['by_category']['documents'] == 0
    assert response.data['summary']['by_category']['integrations'] == 0
    assert not response.data['results']
