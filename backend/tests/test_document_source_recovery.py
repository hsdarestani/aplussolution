import json
import zipfile
from pathlib import Path

import pytest
from django.test import override_settings

from core.document_catalog_service import ensure_document_catalog
from core.document_source_recovery import MANIFEST_NAME, recover_document_sources, source_exists
from core.models import ContractTemplate


def _write_docx(path: Path, marker='document'):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('[Content_Types].xml', '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        archive.writestr('word/document.xml', f'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>{marker}</w:t></w:r></w:p></w:body></w:document>')


@pytest.mark.django_db
def test_catalog_source_is_recovered_from_persistent_media_and_manifest(tmp_path):
    with override_settings(MEDIA_ROOT=tmp_path):
        ensure_document_catalog(recover_sources=False)
        source = tmp_path / 'contract_templates' / 'AV_Muster_20262027.docx'
        _write_docx(source)

        result = recover_document_sources(slugs=['arbeitsvertrag-dgb-gvp'])

        assert result['complete'] is True
        assert result['recovered'] == 1
        template = ContractTemplate.objects.get(slug='arbeitsvertrag-dgb-gvp')
        assert source_exists(template)
        assert template.source_checksum
        assert template.source_file.name == 'contract_templates/AV_Muster_20262027.docx'

        manifest_path = tmp_path / 'contract_templates' / MANIFEST_NAME
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        assert manifest['templates']['arbeitsvertrag-dgb-gvp']['storage_name'] == template.source_file.name
        assert manifest['templates']['arbeitsvertrag-dgb-gvp']['sha256'] == template.source_checksum

        # Simulate a database reset losing only the pointer. The manifest plus
        # persistent media must reconnect the exact same bytes.
        template.source_file = None
        template.source_checksum = ''
        template.save(update_fields=['source_file', 'source_checksum', 'updated_at'])
        second = recover_document_sources(slugs=['arbeitsvertrag-dgb-gvp'])
        template.refresh_from_db()

        assert second['complete'] is True
        assert second['recovered'] == 1
        assert template.source_file.name == 'contract_templates/AV_Muster_20262027.docx'
        assert source_exists(template)


@pytest.mark.django_db
def test_recovery_refuses_ambiguous_different_private_sources(tmp_path):
    with override_settings(MEDIA_ROOT=tmp_path):
        ensure_document_catalog(recover_sources=False)
        directory = tmp_path / 'contract_templates'
        _write_docx(directory / 'Aufhebungsvertrag_-_Muster_ABC1234.docx', 'first')
        _write_docx(directory / 'Aufhebungsvertrag_-_Muster_XYZ5678.docx', 'second')

        result = recover_document_sources(slugs=['aufhebungsvertrag'])

        assert result['complete'] is False
        assert result['recovered'] == 0
        assert result['ambiguous'][0]['slug'] == 'aufhebungsvertrag'
        template = ContractTemplate.objects.get(slug='aufhebungsvertrag')
        assert not template.source_file


@pytest.mark.django_db
def test_recovery_rejects_fake_pdf_even_when_filename_matches(tmp_path):
    with override_settings(MEDIA_ROOT=tmp_path):
        ensure_document_catalog(recover_sources=False)
        directory = tmp_path / 'contract_templates'
        directory.mkdir(parents=True, exist_ok=True)
        (directory / '1._Datengeheimnis.pdf').write_bytes(b'not-a-real-pdf')

        result = recover_document_sources(slugs=['verpflichtung-datengeheimnis'])

        assert result['complete'] is False
        assert result['missing'][0]['slug'] == 'verpflichtung-datengeheimnis'
        template = ContractTemplate.objects.get(slug='verpflichtung-datengeheimnis')
        assert not template.source_file
