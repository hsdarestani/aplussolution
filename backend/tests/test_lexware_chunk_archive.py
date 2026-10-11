"""Large annual PDF uploads must be safe, authenticated and repeatable."""
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from core.models import Document

import pytest


@pytest.mark.django_db
def test_large_pdf_chunk_archive_does_not_modify_payroll(auth_admin, auth_worker, tmp_path, monkeypatch):
    monkeypatch.setattr('core.lexware_chunk_archive.STAGING_DIR', tmp_path)
    name = 'Lohnkonto(1).pdf'
    data = b'%PDF-1.4\n' + b'X' * 70 + b'\n%%EOF'
    url = '/api/working-time/lexware-archive/'
    assert auth_worker.post(url + 'begin/', {
        'filename': name, 'period': '2025-12', 'size': len(data)
    }, format='json').status_code == 403
    started = auth_admin.post(url + 'begin/', {
        'filename': name, 'period': '2025-12', 'size': len(data)
    }, format='json')
    assert started.status_code == 200, started.data
    token = started.data['upload_token']
    wrong = auth_admin.post(url + 'chunk/', {
        'upload_token': token, 'index': 0,
        'chunk': SimpleUploadedFile(name, b'wrong'),
    }, format='multipart')
    assert wrong.status_code == 400
    chunk = SimpleUploadedFile(name, data, content_type='application/pdf')
    good = auth_admin.post(url + 'chunk/', {
        'upload_token': token, 'index': 0, 'chunk': chunk,
    }, format='multipart')
    assert good.status_code == 200, good.data
    finished = auth_admin.post(url + 'finish/', {'upload_token': token}, format='json')
    assert finished.status_code == 200, finished.data
    assert finished.data['status'] == 'archived'
    assert finished.data['payroll_records_modified'] is False
    assert Document.objects.filter(
        title='Lexware 2025-12 · Lohnkonto(1).pdf'
    ).count() == 1


@pytest.mark.django_db
def test_reject_unsupported_or_unsafe_annual_upload(auth_admin, tmp_path, monkeypatch):
    monkeypatch.setattr('core.lexware_chunk_archive.STAGING_DIR', tmp_path)
    url = '/api/working-time/lexware-archive/begin/'
    for filename in ('../secret.pdf', 'Lohnabrechnungen.pdf', 'Lohnkonto.zip'):
        response = auth_admin.post(url, {
            'filename': filename, 'size': 123, 'period': '2025-12',
        }, format='json')
        assert response.status_code == 400, (filename, response.data)
    assert auth_admin.post(url, {
        'filename': 'Lohnkonto(1).pdf', 'size': 123, 'period': '2025-13',
    }, format='json').status_code == 400
    assert auth_admin.post(url, {
        'filename': 'Lohnkonto(1).pdf', 'size': 200 * 1024 * 1024, 'period': '2025-12',
    }, format='json').status_code == 400
