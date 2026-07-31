import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from docx import Document as DocxDocument

from core.document_engine import seed_document_catalog


def valid_docx_bytes():
    doc = DocxDocument()
    doc.add_paragraph('A+ Originalvorlage')
    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


@pytest.mark.django_db
def test_catalog_reads_do_not_reset_installed_template_version(auth_admin):
    seed_document_catalog()
    response = auth_admin.post(
        '/api/document-center/templates/arbeitsvertrag-dgb-gvp/source/',
        {'file': SimpleUploadedFile('approved.docx', valid_docx_bytes()), 'version': '12.2026'},
        format='multipart',
    )
    assert response.status_code == 200
    assert response.data['version'] == '12.2026'

    center = auth_admin.get('/api/document-center/')
    assert center.status_code == 200
    center_template = next(item for item in center.data['templates'] if item['slug'] == 'arbeitsvertrag-dgb-gvp')
    assert center_template['version'] == '12.2026'
    assert center_template['source_installed'] is True

    catalog = auth_admin.get('/api/document-catalog/')
    assert catalog.status_code == 200
    catalog_template = next(item for item in catalog.data['documents'] if item['slug'] == 'arbeitsvertrag-dgb-gvp')
    assert catalog_template['version'] == '12.2026'
    assert catalog_template['source_installed'] is True


@pytest.mark.django_db
def test_fake_docx_is_rejected(auth_admin):
    seed_document_catalog()
    response = auth_admin.post(
        '/api/document-center/templates/arbeitsvertrag-dgb-gvp/source/',
        {'file': SimpleUploadedFile('fake.docx', b'not-a-real-docx')},
        format='multipart',
    )
    assert response.status_code == 400
    assert 'gültiges DOCX' in str(response.data)
