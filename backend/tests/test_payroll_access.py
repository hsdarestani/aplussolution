import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from core.models import PayrollStatement


@pytest.mark.django_db
def test_client_cannot_see_or_create_payroll_statements(auth_client, worker_user):
    PayrollStatement.objects.create(
        worker=worker_user.worker_profile,
        period='2026-08-01',
        gross_amount='1200.00',
        net_amount='980.00',
        document=SimpleUploadedFile('payroll.pdf', b'%PDF-test', content_type='application/pdf'),
    )

    response = auth_client.get('/api/payroll/')
    assert response.status_code == 200
    rows = response.data.get('results', response.data)
    assert rows == []

    create = auth_client.post(
        '/api/payroll/',
        {
            'worker': str(worker_user.worker_profile.id),
            'period': '2026-09-01',
            'document': SimpleUploadedFile('payroll.pdf', b'%PDF-test', content_type='application/pdf'),
        },
        format='multipart',
    )
    assert create.status_code == 403
