"""Personalfragebogen importing never creates or changes worker records on preview."""
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from core.models import EmployeeMasterData, User, WorkerProfile
from core.personnel_import import parse_personalfragebogen_fields


def test_parser_normalizes_fields_without_changing_login_email():
    pdf_fields = {
        'Vorname': {'/V': 'Example'},
        'Nachname': {'/V': 'Worker'},
        'Geburtsdatum': {'/V': '02.06.2000'},
        'Telefonnummer': {'/V': '0176 000000'},
        'IBAN': {'/V': 'DE00500000000000000000'},
        'E-Mail-Adresse': {'/V': 'not an email'},
        'Konfession': {'/V': '36'},
        'Name des Unternehmens/Arbeitgebers der weiteren Tätigkeit 1': {'/V': 'Test Employer'},
    }
    marks = {'salutation': 'Frau', 'insurance_type': 'gesetzlich',
             'has_children': 'nein', 'employment_types': ['minijob', None]}
    with patch('core.personnel_import.PdfReader') as reader, patch(
        'core.personnel_import._marked_options', return_value=marks
    ):
        reader.return_value.is_encrypted = False
        reader.return_value.get_fields.return_value = pdf_fields
        result = parse_personalfragebogen_fields(b'%PDF-mocked')

    assert result['first_name'] == 'Example'
    assert result['master_data']['birth_date'] == '2000-06-02'
    assert result['master_data']['salutation'] == 'Frau'
    assert result['master_data']['has_children'] is False
    assert result['master_data']['other_employments'][0]['employment_type'] == 'minijob'
    assert 'email' not in result['profile']
    assert any('E-Mail' in warning for warning in result['warnings'])
    assert any('Konfession' in warning for warning in result['warnings'])


@pytest.mark.django_db
def test_preview_refuses_different_employee_without_writing():
    admin = User.objects.create_user(email='admin@example.test', password='pass',
                                     first_name='Admin', role=User.Role.ADMIN)
    worker_user = User.objects.create_user(email='worker@example.test', password='pass',
                                           first_name='Example', last_name='Worker',
                                           role=User.Role.WORKER)
    worker = WorkerProfile.objects.create(user=worker_user, employee_number='TEST-001')
    client = APIClient()
    client.force_authenticate(user=admin)
    pdf = SimpleUploadedFile('Personalfragebogen.pdf', b'%PDF-mocked', content_type='application/pdf')
    with patch('core.personnel_import.parse_personalfragebogen_fields', return_value={
        'first_name': 'Different', 'last_name': 'Worker',
        'profile': {}, 'master_data': {'iban': 'DE123'}, 'warnings': [],
    }):
        response = client.post(
            f'/api/workers/{worker.pk}/personalfragebogen/preview/',
            {'file': pdf}, format='multipart',
        )
    assert response.status_code == 409
    assert not EmployeeMasterData.objects.filter(worker=worker).exists()
