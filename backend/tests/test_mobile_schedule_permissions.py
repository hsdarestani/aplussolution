import pytest


@pytest.mark.django_db
def test_worker_cannot_use_admin_mobile_schedule(auth_worker):
    response = auth_worker.get('/api/admin/mobile-schedule/')
    assert response.status_code == 403
