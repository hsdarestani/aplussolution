import io
from datetime import timedelta

import pytest
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from docx import Document as DocxDocument
from rest_framework.test import APIClient

from core.document_center import contract_readiness, dispatch_contract_reminders, document_center_overview
from core.document_engine import seed_document_catalog
from core.models import Contract, ContractSignature, ContractTemplate, EmployeeMasterData, Notification, User


def docx_bytes(text='A+ Originalvorlage {{ employee_name }}'):
    doc = DocxDocument()
    doc.add_paragraph(text)
    output = io.BytesIO()
    doc.save(output)
    return output.getvalue()


@pytest.mark.django_db
def test_document_center_reports_missing_private_sources(auth_admin):
    seed_document_catalog()
    response = auth_admin.get('/api/document-center/')
    assert response.status_code == 200
    assert response.data['summary']['templates_total'] == 8
    assert response.data['summary']['templates_missing_source'] == 8
    assert any(item['action'] == 'install_source' for item in response.data['actions'])


@pytest.mark.django_db
def test_admin_can_install_real_template_source_and_worker_cannot(auth_admin, worker_user):
    seed_document_catalog()
    upload = SimpleUploadedFile(
        'AV Muster 2026.docx',
        docx_bytes(),
        content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    )
    response = auth_admin.post(
        '/api/document-center/templates/arbeitsvertrag-dgb-gvp/source/',
        {'file': upload, 'version': '12.2026'},
        format='multipart',
    )
    assert response.status_code == 200
    assert response.data['source_installed'] is True
    assert response.data['source_checksum']
    assert response.data['version'] == '12.2026'

    worker = APIClient(); worker.force_authenticate(worker_user)
    denied = worker.post(
        '/api/document-center/templates/arbeitsvertrag-dgb-gvp/source/',
        {'file': SimpleUploadedFile('other.docx', docx_bytes())},
        format='multipart',
    )
    assert denied.status_code == 403


@pytest.mark.django_db
def test_contract_readiness_exposes_missing_required_data_to_owner(worker_user, admin_user):
    template = ContractTemplate.objects.create(
        name='Readiness HTML',
        slug='readiness-html',
        kind=ContractTemplate.Kind.EMPLOYMENT,
        source_format=ContractTemplate.SourceFormat.HTML,
        html_template='<h1>{{ employee_name }}</h1>',
        schema={'fields': [{'name': 'iban', 'label': 'IBAN', 'required': True, 'source': 'master.iban'}], 'signature_roles': ['employee', 'employer']},
    )
    contract = Contract.objects.create(
        template=template,
        worker=worker_user.worker_profile,
        title='Readiness Vertrag',
        created_by=admin_user,
    )
    state = contract_readiness(contract)
    assert state['state'] == 'blocked'
    assert state['missing_fields'][0]['label'] == 'IBAN'
    assert state['generation_allowed'] is False

    worker = APIClient(); worker.force_authenticate(worker_user)
    response = worker.get(f'/api/contracts/{contract.id}/readiness/')
    assert response.status_code == 200
    assert response.data['missing_fields'][0]['label'] == 'IBAN'


@pytest.mark.django_db
def test_generated_document_is_invalidated_on_edit_then_locked_after_send(auth_admin, admin_user, worker_user):
    template = ContractTemplate.objects.create(
        name='Lifecycle HTML',
        slug='lifecycle-html',
        kind=ContractTemplate.Kind.EMPLOYMENT,
        source_format=ContractTemplate.SourceFormat.HTML,
        html_template='<h1>{{ employee_name }}</h1>',
        schema={'fields': [], 'signature_roles': ['employee', 'employer']},
    )
    contract = Contract.objects.create(
        template=template,
        worker=worker_user.worker_profile,
        title='Lifecycle Vertrag',
        created_by=admin_user,
    )

    generated = auth_admin.post(f'/api/contracts/{contract.id}/generate_pdf/', {}, format='json')
    assert generated.status_code == 200
    contract.refresh_from_db()
    assert contract.status == Contract.Status.READY and contract.pdf and contract.generated_at

    changed = auth_admin.patch(f'/api/contracts/{contract.id}/', {'title': 'Lifecycle Vertrag geändert'}, format='json')
    assert changed.status_code == 200
    contract.refresh_from_db()
    assert contract.status == Contract.Status.DRAFT
    assert not contract.pdf and not contract.generated_at and contract.data_snapshot == {}

    sent = auth_admin.post(f'/api/contracts/{contract.id}/send/', {}, format='json')
    assert sent.status_code == 200
    contract.refresh_from_db()
    assert contract.status == Contract.Status.SENT and contract.pdf and contract.sent_at

    assert auth_admin.patch(f'/api/contracts/{contract.id}/', {'title': 'Nicht erlaubt'}, format='json').status_code == 400
    assert auth_admin.post(f'/api/contracts/{contract.id}/generate_pdf/', {}, format='json').status_code == 400
    assert auth_admin.delete(f'/api/contracts/{contract.id}/').status_code == 400

    worker = APIClient(); worker.force_authenticate(worker_user)
    first = worker.post(f'/api/contracts/{contract.id}/sign/', {'name': 'Anna Becker', 'signature': 'Anna'}, format='json')
    assert first.status_code == 200
    second = auth_admin.post(f'/api/contracts/{contract.id}/sign/', {'name': 'A+ Solution GmbH', 'signature': 'Admin'}, format='json')
    assert second.status_code == 200
    contract.refresh_from_db()
    assert contract.status == Contract.Status.SIGNED
    assert auth_admin.post(f'/api/contracts/{contract.id}/sign/', {'name': 'A+ Solution GmbH', 'signature': 'Overwrite'}, format='json').status_code == 400
    assert auth_admin.post(f'/api/contracts/{contract.id}/cancel/', {'reason': 'Soll nicht möglich sein'}, format='json').status_code == 400


@pytest.mark.django_db
def test_sent_unsigned_contract_can_be_cancelled_but_not_deleted(auth_admin, admin_user):
    template = ContractTemplate.objects.create(
        name='Cancelable HTML', slug='cancelable-html', kind=ContractTemplate.Kind.EMPLOYMENT,
        source_format=ContractTemplate.SourceFormat.HTML, html_template='<p>Test</p>',
        requires_signature=False, schema={'fields': [], 'signature_roles': []},
    )
    contract = Contract.objects.create(template=template, title='Storno Test', created_by=admin_user)
    assert auth_admin.post(f'/api/contracts/{contract.id}/send/', {}, format='json').status_code == 200
    response = auth_admin.post(f'/api/contracts/{contract.id}/cancel/', {'reason': 'Falsche Vertragsversion gewählt.'}, format='json')
    assert response.status_code == 200
    contract.refresh_from_db()
    assert contract.status == Contract.Status.CANCELLED
    assert Contract.objects.filter(pk=contract.id).exists()


@pytest.mark.django_db
def test_signature_reminders_are_role_aware_and_deduplicated(admin_user, worker_user):
    template = ContractTemplate.objects.create(
        name='Reminder HTML', slug='phase5-reminder-html', kind=ContractTemplate.Kind.EMPLOYMENT,
        source_format=ContractTemplate.SourceFormat.HTML, html_template='<p>Reminder</p>',
        schema={'fields': [], 'signature_roles': ['employee', 'employer']},
    )
    sent_at = timezone.now() - timedelta(days=3)
    contract = Contract.objects.create(
        template=template,
        worker=worker_user.worker_profile,
        title='Signatur Reminder',
        status=Contract.Status.SENT,
        sent_at=sent_at,
        created_by=admin_user,
    )
    first = dispatch_contract_reminders(today=timezone.localdate())
    assert first['notifications'] >= 2
    kind = f'contract-signature-3d-{contract.id}'
    assert Notification.objects.filter(kind=kind, user=worker_user).exists()
    assert Notification.objects.filter(kind=kind, user=admin_user).exists()
    mail_count = len(mail.outbox)

    second = dispatch_contract_reminders(today=timezone.localdate())
    assert second['notifications'] == 0
    assert second['emails'] == 0
    assert len(mail.outbox) == mail_count


@pytest.mark.django_db
def test_employer_only_signature_reminder_does_not_ping_worker(admin_user, worker_user):
    template = ContractTemplate.objects.create(
        name='Role Reminder', slug='phase5-role-reminder', kind=ContractTemplate.Kind.EMPLOYMENT,
        source_format=ContractTemplate.SourceFormat.HTML, html_template='<p>Reminder</p>',
        schema={'fields': [], 'signature_roles': ['employee', 'employer']},
    )
    contract = Contract.objects.create(
        template=template,
        worker=worker_user.worker_profile,
        title='Nur Arbeitgeber offen',
        status=Contract.Status.SENT,
        sent_at=timezone.now() - timedelta(days=7),
        created_by=admin_user,
    )
    ContractSignature.objects.create(
        contract=contract,
        role=ContractSignature.Role.EMPLOYEE,
        signer=worker_user,
        signer_name='Anna Becker',
        signature_data='Anna',
        signature_hash='hash-employee',
    )
    result = dispatch_contract_reminders(today=timezone.localdate())
    assert result['notifications'] >= 1
    kind = f'contract-signature-7d-{contract.id}'
    assert Notification.objects.filter(kind=kind, user=admin_user).exists()
    assert not Notification.objects.filter(kind=kind, user=worker_user).exists()


@pytest.mark.django_db
def test_manual_reminder_endpoint_and_document_center_are_manager_only(auth_admin, worker_user):
    response = auth_admin.post('/api/document-center/reminders/run/', {}, format='json')
    assert response.status_code == 200
    assert set(response.data) == {'events', 'notifications', 'emails'}

    worker = APIClient(); worker.force_authenticate(worker_user)
    assert worker.get('/api/document-center/').status_code == 403
    assert worker.post('/api/document-center/reminders/run/', {}, format='json').status_code == 403
