from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from core.models import Contract, ContractTemplate, Document

pytestmark = pytest.mark.django_db


def test_client_servicecenter_counts_only_visible_documents_and_contracts(
    auth_client, company, client_user
):
    Document.objects.create(
        client=company,
        title='Sichtbar für Kunde',
        folder=Document.Folder.GENERAL,
        visibility=Document.Visibility.CLIENT,
        file=SimpleUploadedFile('visible.txt', b'visible'),
        uploaded_by=client_user,
    )
    Document.objects.create(
        client=company,
        title='Nur Administration',
        folder=Document.Folder.GENERAL,
        visibility=Document.Visibility.ADMIN,
        file=SimpleUploadedFile('private.txt', b'private'),
        uploaded_by=client_user,
    )

    template = ContractTemplate.objects.create(
        name='Client QA Vertrag',
        slug='client-qa-vertrag',
        kind=ContractTemplate.Kind.CLIENT_AUEV,
        audience=ContractTemplate.Audience.CLIENT,
        version='1.0',
        schema={},
        html_template='<p>QA</p>',
        active=True,
    )
    Contract.objects.create(
        template=template,
        client=company,
        title='Verdeckter Client Vertrag',
        status=Contract.Status.READY,
        ends_on=timezone.localdate() + timedelta(days=10),
        created_by=client_user,
    )
    company.contract_visibility_enabled = False
    company.save(update_fields=['contract_visibility_enabled'])

    operations = auth_client.get('/api/operations/')
    assert operations.status_code == 200
    assert operations.data['documents'] == 1
    assert operations.data['contracts_due'] == 0

    folders = auth_client.get('/api/operations/folders/')
    assert folders.status_code == 200
    assert folders.data['workers'] == []
    assert len(folders.data['clients']) == 1
    assert folders.data['clients'][0]['documents'] == 1
    assert folders.data['clients'][0]['contracts'] == 0

    documents = auth_client.get('/api/documents/')
    assert documents.status_code == 200
    rows = documents.data.get('results', documents.data) if hasattr(documents.data, 'get') else documents.data
    assert [row['title'] for row in rows] == ['Sichtbar für Kunde']

    contracts = auth_client.get('/api/contracts/')
    assert contracts.status_code == 200
    contract_rows = contracts.data.get('results', contracts.data) if hasattr(contracts.data, 'get') else contracts.data
    assert contract_rows == []
