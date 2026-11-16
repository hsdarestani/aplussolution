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


def test_parser_recovers_safe_fields_from_incomplete_lexware_form():
    """A misaligned PDF is previewable, but questionable payroll fields stay out."""
    pdf_fields = {
        'Vorname': {'/V': 'Lina'},
        'Nachname': {'/V': ''},
        'Geburtsname': {'/V': 'Lina Meyer'},
        'E-Mail-Adresse': {'/V': 'lina@example.test'},
        'Straße und Hausnummer': {'/V': 'Musterstraße 5 63454 Hanau'},
        'Postleitzahl': {'/V': 'Hanau'},
        'Ort': {'/V': '63454'},
        'Geburtsdatum': {'/V': '03.03.1999'},
        'Geburtsort': {'/V': '03.03.199'},
        'Sozial-/Rentenversicherungsnummer': {'/V': 'A860839798'},
        'Steueridentifikationsnummer': {'/V': ''},
        'Kinderfreibetrag': {'/V': '26783594042'},
        'Freibeträge': {'/V': '1'},
        'Kontoinhaber': {'/V': '5374280553336855'},
        'Name des Kreditinstitus': {'/V': 'Lina Meyer (Sparkasse Dieburg)'},
        'Falls ja: Wie viele Kinder?': {'/V': 'Nein'},
    }
    marks = {'salutation': None, 'insurance_type': 'gesetzlich',
             'has_children': 'nein', 'employment_types': [None, None]}
    with patch('core.personnel_import.PdfReader') as reader, patch(
        'core.personnel_import._marked_options', return_value=marks
    ):
        reader.return_value.is_encrypted = False
        reader.return_value.pages = [object()]
        reader.return_value.get_fields.return_value = pdf_fields
        result = parse_personalfragebogen_fields(b'%PDF-mocked')

    master = result['master_data']
    assert result['last_name'] == ''
    assert result['identity_name_hint'] == 'Lina Meyer'
    assert result['source_email'] == 'lina@example.test'
    assert master['street'] == 'Musterstraße 5'
    assert master['postal_code'] == '63454'
    assert master['city'] == 'Hanau'
    assert master['full_address'] == 'Musterstraße 5, 63454 Hanau'
    assert master['bank_account_holder'] == 'Lina Meyer'
    assert master['bank_name'] == 'Sparkasse Dieburg'
    assert master['has_children'] is False
    assert master['children_under_25'] == 0
    for forbidden in ('child_allowance', 'tax_allowance', 'tax_class', 'tax_identification_number',
                      'birth_place', 'social_insurance_number'):
        assert forbidden not in master
    assert any('Steuer-ID' in warning for warning in result['warnings'])


@pytest.mark.django_db
def test_preview_accepts_missing_surname_only_with_matching_email_and_birth_name():
    admin = User.objects.create_user(email='admin2@example.test', password='pass',
                                     first_name='Admin', role=User.Role.ADMIN)
    worker_user = User.objects.create_user(email='lina@example.test', password='pass',
                                           first_name='Lina', last_name='Meyer',
                                           role=User.Role.WORKER)
    worker = WorkerProfile.objects.create(user=worker_user, employee_number='TEST-002')
    client = APIClient()
    client.force_authenticate(user=admin)
    pdf = SimpleUploadedFile('Personalfragebogen.pdf', b'%PDF-mocked', content_type='application/pdf')
    preview = {
        'first_name': 'Lina', 'last_name': '', 'identity_name_hint': 'Lina Meyer',
        'source_email': 'lina@example.test', 'profile': {'phone': '012345'},
        'master_data': {'city': 'Hanau'}, 'warnings': ['Nachname fehlt'],
    }
    with patch('core.personnel_import.parse_personalfragebogen_fields', return_value=preview):
        response = client.post(f'/api/workers/{worker.pk}/personalfragebogen/preview/',
                               {'file': pdf}, format='multipart')
    assert response.status_code == 200
    assert response.data['matched_worker'] == str(worker.pk)
    assert response.data['master_data']['city'] == 'Hanau'
    assert not EmployeeMasterData.objects.filter(worker=worker).exists()


@pytest.mark.django_db
@pytest.mark.parametrize('email,birth_name', [
    ('someone-else@example.test', 'Lina Meyer'),
    ('lina@example.test', 'Lina Schmidt'),
])
def test_preview_blocks_incomplete_identity_without_mutation(email, birth_name):
    admin = User.objects.create_user(email='admin3@example.test', password='pass',
                                     first_name='Admin', role=User.Role.ADMIN)
    worker_user = User.objects.create_user(email='lina@example.test', password='pass',
                                           first_name='Lina', last_name='Meyer',
                                           role=User.Role.WORKER)
    worker = WorkerProfile.objects.create(user=worker_user, employee_number='TEST-003')
    client = APIClient()
    client.force_authenticate(user=admin)
    pdf = SimpleUploadedFile('Personalfragebogen.pdf', b'%PDF-mocked', content_type='application/pdf')
    preview = {
        'first_name': 'Lina', 'last_name': '', 'identity_name_hint': birth_name,
        'source_email': email, 'profile': {'phone': '012345'},
        'master_data': {'iban': 'DE111'}, 'warnings': [],
    }
    with patch('core.personnel_import.parse_personalfragebogen_fields', return_value=preview):
        response = client.post(f'/api/workers/{worker.pk}/personalfragebogen/preview/',
                               {'file': pdf}, format='multipart')
    assert response.status_code == 409
    assert not EmployeeMasterData.objects.filter(worker=worker).exists()
