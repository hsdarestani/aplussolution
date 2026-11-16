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
        reader.return_value.pages = [object()]
        reader.return_value.get_fields.return_value = pdf_fields
        result = parse_personalfragebogen_fields(b'%PDF-mocked')

    assert result['first_name'] == 'Example'
    assert result['master_data']['birth_date'] == '2000-06-02'
    assert result['master_data']['salutation'] == 'Frau'
    assert result['master_data']['has_children'] is False
    assert result['master_data']['children_under_25'] == 0
    assert 'religion' not in result['master_data']
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
    master, _ = EmployeeMasterData.objects.get_or_create(worker=worker)
    master.data = {'street': 'Existing address'}
    master.save()
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
    master.refresh_from_db()
    assert master.data == {'street': 'Existing address'}

def test_parser_accepts_blank_surname_only_with_email_and_quarantines_misplaced_values():
    pdf_fields = {
        'Vorname': {'/V': 'Sample'},
        'Nachname': {'/V': ''},
        'E-Mail-Adresse': {'/V': 'sample@example.test'},
        'Straße und Hausnummer': {'/V': 'Musterweg 9 12345 Beispielstadt'},
        'Postleitzahl': {'/V': 'Beispielstadt'},
        'Ort': {'/V': '12345'},
        'Kontoinhaber': {'/V': '1111222233334444'},
        'Name des Kreditinstitus': {'/V': 'Sample Worker (Sparkasse Test)'},
        'Kinderfreibetrag': {'/V': '12345678901'},
        'Freibeträge': {'/V': '1'},
        'Geburtsort': {'/V': '01.01.200'},
        'Sozial-/Rentenversicherungsnummer': {'/V': 'A860839798'},
        'IBAN': {'/V': 'DE00000000000000000000'},
    }
    with patch('core.personnel_import.PdfReader') as reader, patch(
        'core.personnel_import._marked_options', return_value={
            'salutation': None, 'insurance_type': None,
            'has_children': None, 'employment_types': [None, None],
        }
    ):
        reader.return_value.is_encrypted = False
        reader.return_value.pages = [object()]
        reader.return_value.get_fields.return_value = pdf_fields
        result = parse_personalfragebogen_fields(b'%PDF-mocked')
    master = result['master_data']
    assert result['last_name'] == ''
    assert result['identity_email'] == 'sample@example.test'
    assert master['postal_code'] == '12345'
    assert master['city'] == 'Beispielstadt'
    assert master['street'] == 'Musterweg 9'
    assert master['iban'] == 'DE00000000000000000000'
    assert master['bank_name'] == 'Sparkasse Test'
    assert 'bank_account_holder' not in master
    assert 'child_allowance' not in master
    assert 'tax_allowance' not in master
    assert 'tax_identification_number' not in master
    assert 'tax_class' not in master
    assert 'birth_place' not in master
    assert 'social_insurance_number' not in master
    assert any('Nachname' in w for w in result['warnings'])
    assert any('Steuer-ID' in w for w in result['warnings'])


@pytest.mark.django_db
@pytest.mark.parametrize('email,expect_code', [
    ('sample@example.test', 200),
    ('other@example.test', 409),
])
def test_preview_matches_blank_surname_only_by_existing_worker_email(email, expect_code):
    admin = User.objects.create_user(email='admin@example.test', password='pass',
                                     first_name='Admin', role=User.Role.ADMIN)
    worker_user = User.objects.create_user(email='sample@example.test', password='pass',
                                           first_name='Sample', last_name='Worker',
                                           role=User.Role.WORKER)
    worker = WorkerProfile.objects.create(user=worker_user, employee_number='TEST-222')
    client = APIClient()
    client.force_authenticate(user=admin)
    pdf = SimpleUploadedFile('Personalfragebogen.pdf', b'%PDF-mocked', content_type='application/pdf')
    with patch('core.personnel_import.parse_personalfragebogen_fields', return_value={
        'first_name': 'Sample', 'last_name': '', 'identity_email': email,
        'profile': {'phone': '+491111'}, 'master_data': {'iban': 'DE123'}, 'warnings': [],
    }):
        response = client.post(
            f'/api/workers/{worker.pk}/personalfragebogen/preview/',
            {'file': pdf}, format='multipart',
        )
    assert response.status_code == expect_code
    assert not EmployeeMasterData.objects.filter(worker=worker).exists()
    worker_user.refresh_from_db()
    assert worker_user.phone == ''
