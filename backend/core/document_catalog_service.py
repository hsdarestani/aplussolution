from .document_catalog import DOCUMENT_CATALOG
from .models import ContractTemplate


def ensure_document_catalog():
    """Create missing catalog templates without overwriting installed source/version metadata."""
    created = 0
    for item in DOCUMENT_CATALOG:
        _, was_created = ContractTemplate.objects.get_or_create(
            slug=item['slug'],
            defaults={
                'name': item['name'],
                'kind': item['kind'],
                'audience': item['audience'],
                'version': item['version'],
                'schema': {
                    'fields': item.get('fields', []),
                    'signature_roles': item.get('signature_roles', []),
                    'source_name': item.get('source_name', ''),
                },
                'source_format': item['source_format'],
                'requires_signature': item.get('requires_signature', True),
                'required_document': item.get('required_document', True),
                'active': True,
            },
        )
        created += int(was_created)
    return {'created': created, 'total': len(DOCUMENT_CATALOG)}
