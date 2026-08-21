from rest_framework.decorators import api_view
from rest_framework.response import Response

from .document_catalog import DOCUMENT_CATALOG
from .document_catalog_service import ensure_document_catalog
from .document_source_recovery import source_exists
from .models import ContractTemplate


@api_view(['GET'])
def document_catalog(request):
    bootstrap = ensure_document_catalog()
    templates = {item.slug: item for item in ContractTemplate.objects.all()}
    rows = []
    for item in DOCUMENT_CATALOG:
        template = templates.get(item['slug'])
        installed = bool(template and source_exists(template))
        rows.append({
            'slug': item['slug'],
            'name': item['name'],
            'kind': item['kind'],
            'audience': item['audience'],
            'version': template.version if template else item['version'],
            'source_format': item['source_format'],
            'source_installed': installed,
            'source_checksum': template.source_checksum if installed and template else '',
            'requires_signature': item['requires_signature'],
            'signature_roles': item.get('signature_roles', []),
            'fields': item.get('fields', []),
        })
    return Response({
        'count': len(rows),
        'documents': rows,
        'complete': all(row['source_installed'] for row in rows),
        'recovery': bootstrap.get('sources', {}),
    })
