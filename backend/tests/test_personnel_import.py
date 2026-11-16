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


def test_parser_allows_missing_surname_with_email_and_quarantines_misplaced_fields():
    # Synthetic fields reproduce a badly completed form; no real employee PII.
    pdf_fields = {
        'Vorname': {'/V': 'Example'},
        'Nachname': {'/V': ''},
        'E-Mail-Adresse': {'/V': 'worker@example.test'},
        'Straße und Hausnummer': {'/V': 'Teststraße 53 A 63454 Hanau'},
        'Postleitzahl': {'/V': 'Hanau'},
        'Ort': {'/V': '63454'},
        'Kinderfreibetrag': {'/V': '12345678901'},
        'Freibeträge': {'/V': '1'},
        'Geburtsort': {'/V': '03.03.199'},
        'Sozial-/Rentenversicherungsnummer': {'/V': 'A860839798'},
        'Kontoinhaber': {'/V': '1234567890123456'},
        'Name des Kreditinstitus': {'/V': 'Example Worker (Sparkasse Dieburg)'},
    }
    marks = {'salutation': None, 'insurance_type': None,
             'has_children': None, 'employment_types': [None, None]}
    with patch('core.personnel_import.PdfReader') as reader, patch(
        'core.personnel_import._marked_options', return_value=marks
    ):
        reader.return_value.is_encrypted = False
        reader.return_value.pages = [object()]
        reader.return_value.get_fields.return_value = pdf_fields
        result = parse_personalfragebogen_fields(b'%PDF-mocked')

    master = result['master_data']
    assert result['first_name'] == 'Example'
    assert result['last_name'] == ''
    assert result['source_email'] == 'worker@example.test'
    assert master['street'] == 'Teststraße 53 A'
    assert master['postal_code'] == '63454'
    assert master['city'] == 'Hanau'
    assert master['bank_name'] == 'Sparkasse Dieburg'
    for unsafe in ('birth_place', 'social_insurance_number', 'child_allowance',
                   'tax_allowance', 'tax_identification_number', 'tax_class',
                   'bank_account_holder'):
        assert unsafe not in master
    assert any('Nachname fehlt' in message for message in result['warnings'])


@pytest.mark.django_db
def test_preview_missing_surname_requires_exact_worker_email_and_does_not_save():
    admin = User.objects.create_user(email='admin@example.test', password='pass',
                                     first_name='Admin', role=User.Role.ADMIN)
    worker_user = User.objects.create_user(email='worker@example.test', password='pass',
                                           first_name='Example', last_name='Worker',
                                           role=User.Role.WORKER)
    worker = WorkerProfile.objects.create(user=worker_user, employee_number='TEST-002')
    master, _ = EmployeeMasterData.objects.get_or_create(worker=worker)
    master.data = {'street': 'Originalstraße'}
    master.save()
    client = APIClient()
    client.force_authenticate(user=admin)

    def preview(email):
        file = SimpleUploadedFile('Personalfragebogen.pdf', b'%PDF-mocked',
                                  content_type='application/pdf')
        with patch('core.personnel_import.parse_personalfragebogen_fields', return_value={
            'first_name': 'Example', 'last_name': '', 'source_email': email,
            'profile': {'phone': '030 123456'},
            'master_data': {'iban': 'DE00500000000000000000'}, 'warnings': [],
        }):
            return client.post(f'/api/workers/{worker.pk}/personalfragebogen/preview/',
                               {'file': file}, format='multipart')

    matching = preview('worker@example.test')
    assert matching.status_code == 200
    assert matching.data['master_data']['iban'] == 'DE00500000000000000000'
    assert preview('another@example.test').status_code == 409
    master.refresh_from_db()
    worker_user.refresh_from_db()
    assert master.data == {'street': 'Originalstraße'}
    assert worker_user.phone != '030 123456'
