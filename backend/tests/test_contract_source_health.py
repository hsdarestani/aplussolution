from pathlib import Path

import pytest
from django.test import override_settings

from core.document_catalog_service import ensure_document_catalog


@pytest.mark.django_db
def test_contract_source_health_exposes_counts_without_private_paths(client, tmp_path):
    with override_settings(MEDIA_ROOT=tmp_path):
        ensure_document_catalog(recover_sources=False)
        response = client.get('/health/contracts/')

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        'status': 'ok',
        'document_sources': {
            'installed': 0,
            'expected': 8,
            'complete': False,
        },
    }
    rendered = response.content.decode('utf-8')
    assert 'contract_templates/' not in rendered
    assert str(Path(tmp_path)) not in rendered
