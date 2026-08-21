from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from core.models import ClientCompany, ClientOrder, Contract, ContractTemplate, Document, PayrollStatement, User


@pytest.mark.django_db
def test_worker_akte_groups_contracts_documents_and_payroll(auth_admin, worker_user, admin_user):
    template = ContractTemplate.objects.create(
        name='Arbeitsvertrag',
        slug='akte-worker-contract',
        kind='employment',
        source_format='html',
        html_template='<p>Test</p>',
        schema={'fields': [], 'signature_roles': ['employee', 'employer']},
    )
    Contract.objects.create(template=template, worker=worker_user.worker_profile, title='AV Anna', created_by=admin_user)
    Document.objects.create(
        title='Nachweis',
        file=SimpleUploadedFile('nachweis.pdf', b'%PDF-1.4 test', content_type='application/pdf'),
        folder=Document.Folder.CERTIFICATES,
        visibility=Document.Visibility.WORKER,
        worker=worker_user.worker_profile,
        uploaded_by=admin_user,
    )
    PayrollStatement.objects.create(
        worker=worker_user.worker_profile,
        period=timezone.localdate().replace(day=1),
        document=SimpleUploadedFile('lohn.pdf', b'%PDF-1.4 payroll', content_type='application/pdf'),
    )

    response = auth_admin.get(f'/api/workers/{worker_user.worker_profile.id}/akte/')
    assert response.status_code == 200
    assert response.data['kind'] == 'worker'
    assert response.data['summary']['contracts'] == 1
    assert response.data['summary']['documents'] == 1
    assert response.data['summary']['payroll'] == 1
    assert response.data['contracts'][0]['title'] == 'AV Anna'
    assert response.data['document_folders'][0]['label'] == 'Nachweise'
    assert response.data['payroll'][0]['worker_name'] == 'Anna Becker'


@pytest.mark.django_db
def test_client_can_open_own_akte_with_orders_locations_and_documents(auth_client, client_user, company, location):
    now = timezone.now() + timedelta(days=2)
    order = ClientOrder.objects.create(
        client=company,
        title='Sommerfest',
        starts_at=now,
        ends_at=now + timedelta(hours=6),
        requested_staff=4,
        created_by=client_user,
    )
    Document.objects.create(
        title='Function Sheet',
        file=SimpleUploadedFile('functions.pdf', b'%PDF-1.4 functions', content_type='application/pdf'),
        folder=Document.Folder.ORDERS,
        visibility=Document.Visibility.CLIENT,
        client=company,
        uploaded_by=client_user,
    )

    response = auth_client.get(f'/api/clients/{company.id}/akte/')
    assert response.status_code == 200
    assert response.data['kind'] == 'client'
    assert response.data['summary']['orders'] == 1
    assert response.data['summary']['locations'] == 1
    assert response.data['orders'][0]['id'] == str(order.id)
    assert response.data['locations'][0]['name'] == location.name
    assert response.data['document_folders'][0]['label'] == 'Aufträge'


@pytest.mark.django_db
def test_client_cannot_open_another_company_akte(auth_client):
    other = ClientCompany.objects.create(name='Fremd GmbH', customer_number='KD-999')
    response = auth_client.get(f'/api/clients/{other.id}/akte/')
    assert response.status_code == 403


@pytest.mark.django_db
def test_client_uploads_functions_file_to_own_order(auth_client, client_user, company):
    now = timezone.now() + timedelta(days=1)
    order = ClientOrder.objects.create(
        client=company,
        title='Messeauftrag',
        description='Bestehend',
        starts_at=now,
        ends_at=now + timedelta(hours=8),
        requested_staff=6,
        created_by=client_user,
    )
    upload = SimpleUploadedFile('functions.pdf', b'%PDF-1.4 function sheet', content_type='application/pdf')
    response = auth_client.patch(
        f'/api/orders/{order.id}/',
        {'attachment': upload, 'description': 'Bestehend\n\n4 Service, 2 Runner'},
        format='multipart',
    )
    assert response.status_code == 200
    order.refresh_from_db()
    assert order.attachment.name.endswith('functions.pdf')
    assert '4 Service, 2 Runner' in order.description


@pytest.mark.django_db
def test_client_order_upload_rejects_unsafe_extension(auth_client, client_user, company):
    now = timezone.now() + timedelta(days=1)
    order = ClientOrder.objects.create(
        client=company,
        title='Messeauftrag',
        starts_at=now,
        ends_at=now + timedelta(hours=8),
        requested_staff=2,
        created_by=client_user,
    )
    upload = SimpleUploadedFile('payload.exe', b'MZ fake', content_type='application/octet-stream')
    response = auth_client.patch(f'/api/orders/{order.id}/', {'attachment': upload}, format='multipart')
    assert response.status_code == 400
    assert 'Erlaubt sind' in str(response.data)
