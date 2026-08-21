from .document_catalog import DOCUMENT_CATALOG
from .models import ContractTemplate


def _schema_needs_repair(schema):
    if not isinstance(schema, dict):
        return True
    fields = schema.get('fields')
    if not isinstance(fields, list):
        return True
    if any(not isinstance(item, dict) or not item.get('name') for item in fields):
        return True
    roles = schema.get('signature_roles', [])
    if not isinstance(roles, list) or any(not isinstance(role, str) for role in roles):
        return True
    return False


def _repaired_schema(existing_schema, item):
    schema = dict(existing_schema) if isinstance(existing_schema, dict) else {}
    schema['fields'] = item.get('fields', [])
    schema['signature_roles'] = item.get('signature_roles', [])
    if not schema.get('source_name'):
        schema['source_name'] = item.get('source_name', '')
    return schema


def ensure_document_catalog(recover_sources=True):
    """Create missing catalog templates and repair malformed structural metadata.

    Private legal source files live on the persistent media volume rather than in Git.
    After a database reset their FileField pointers can disappear while the files remain.
    When requested, recover those pointers deterministically from the persistent manifest
    or from an unambiguous catalog filename match.
    """
    created = 0
    repaired = 0
    for item in DOCUMENT_CATALOG:
        template, was_created = ContractTemplate.objects.get_or_create(
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
        if not was_created and _schema_needs_repair(template.schema):
            template.schema = _repaired_schema(template.schema, item)
            template.save(update_fields=['schema', 'updated_at'])
            repaired += 1

    result = {'created': created, 'repaired': repaired, 'total': len(DOCUMENT_CATALOG)}
    if recover_sources:
        from .document_source_recovery import recover_document_sources

        result['sources'] = recover_document_sources()
    return result
