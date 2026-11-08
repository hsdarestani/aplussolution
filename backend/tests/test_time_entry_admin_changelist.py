from datetime import datetime, timedelta

import pytest
from django.contrib import admin
from django.utils import timezone

from core.admin import TimeEntryAdmin, WorkerProfileAdmin
from core.models import TimeEntry, User, WorkerProfile


@pytest.mark.django_db
def test_time_entry_admin_shows_names_hours_and_filters_wiw_and_inactive_workers(
    client, admin_user, worker_user, second_worker, shift,
):
    admin_user.is_superuser = True
    admin_user.save(update_fields=['is_superuser'])
    client.force_login(admin_user)

    worker_user.first_name = 'Julius'
    worker_user.last_name = 'Degen'
    worker_user.save(update_fields=['first_name', 'last_name'])
    worker_user.worker_profile.active = False
    worker_user.worker_profile.save(update_fields=['active'])

    start = timezone.make_aware(datetime(2026, 9, 9, 7, 30))
    historical = TimeEntry.objects.create(
        worker=worker_user.worker_profile,
        shift=shift,
        clock_in=start,
        clock_out=start + timedelta(hours=7, minutes=30),
        break_minutes=0,
        wiw_time_id='wiw-julius-0909',
        approved=False,
    )
    other = TimeEntry.objects.create(
        worker=second_worker,
        clock_in=start + timedelta(days=2),
        clock_out=start + timedelta(days=2, hours=2),
        break_minutes=0,
        approved=True,
    )

    path = '/admin/core/timeentry/'
    result = client.get(path, {'q': 'Julius Degen'})
    assert result.status_code == 200
    page = result.content.decode()
    assert str(historical.pk) in page
    assert str(other.pk) not in page
    assert 'Julius Degen' in page
    assert 'MA-001' in page
    assert '09.09.2026' in page
    assert '07:30' in page
    assert '15:00' in page
    assert '0 Min.' in page
    assert '7,50 Std.' in page
    assert 'WIW' in page

    historical_only = client.get(path, {'source': 'wiw'})
    assert historical_only.status_code == 200
    assert str(historical.pk) in historical_only.content.decode()
    assert str(other.pk) not in historical_only.content.decode()

    native_only = client.get(path, {'source': 'aplus'})
    assert native_only.status_code == 200
    assert str(other.pk) in native_only.content.decode()
    assert str(historical.pk) not in native_only.content.decode()


@pytest.mark.django_db
def test_worker_admin_search_supports_inactive_staff(client, admin_user, worker_user):
    admin_user.is_superuser = True
    admin_user.save(update_fields=['is_superuser'])
    client.force_login(admin_user)

    worker_user.first_name = 'Julius'
    worker_user.last_name = 'Degen'
    worker_user.save(update_fields=['first_name', 'last_name'])
    worker_user.worker_profile.active = False
    worker_user.worker_profile.save(update_fields=['active'])

    response = client.get('/admin/core/workerprofile/', {'q': 'Julius Degen'})
    assert response.status_code == 200
    assert 'MA-001' in response.content.decode()
    assert isinstance(admin.site._registry[TimeEntry], TimeEntryAdmin)
    assert isinstance(admin.site._registry[WorkerProfile], WorkerProfileAdmin)
