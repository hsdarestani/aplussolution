import pytest

from core.document_catalog import CATALOG_BY_SLUG
from core.document_catalog_service import ensure_document_catalog
from core.document_center import contract_readiness, document_center_overview, template_readiness
from core.models import Contract, ContractTemplate


@pytest.mark.django_db
def test_catalog_repair_normalizes_legacy_fields_without_touching_installed_metadata():
    catalog = CATALOG_BY_SLUG['arbeitsvertrag-dgb-gvp']
    template = ContractTemplate.objects.create(
        name='Legacy Arbeitsvertrag',
        slug='arbeitsvertrag-dgb-gvp',
        kind=ContractTemplate.Kind.EMPLOYMENT,
        audience=ContractTemplate.Audience.WORKER,
        version='installed-2026',
        schema={
            'fields': ['employee_name', 'start_date'],
            'signature_roles': 'employee',
            'custom_private_mapping': {'keep': True},
        },
        source_format=ContractTemplate.SourceFormat.DOCX,
        source_checksum='installed-checksum',
        requires_signature=True,
        required_document=True,
        active=True,
    )

    result = ensure_document_catalog()

    template.refresh_from_db()
    assert result['repaired'] == 1
    assert template.version == 'installed-2026'
    assert template.source_checksum == 'installed-checksum'
    assert template.schema['custom_private_mapping'] == {'keep': True}
    assert template.schema['fields'] == catalog['fields']
    assert template.schema['signature_roles'] == catalog['signature_roles']


@pytest.mark.django_db
def test_unknown_legacy_template_is_reported_as_blocked_instead_of_crashing(admin_user):
    template = ContractTemplate.objects.create(
        name='Legacy Fremdvorlage',
        slug='legacy-fremdvorlage',
        kind=ContractTemplate.Kind.EMPLOYMENT,
        audience=ContractTemplate.Audience.WORKER,
        schema={'fields': ['employee_name'], 'signature_roles': ['employee']},
        source_format=ContractTemplate.SourceFormat.HTML,
        html_template='<p>{{ employee_name }}</p>',
        requires_signature=True,
        required_document=False,
        active=True,
    )
    contract = Contract.objects.create(
        template=template,
        title='Legacy Vertrag',
        created_by=admin_user,
    )

    template_state = template_readiness(template)
    contract_state = contract_readiness(contract)
    overview = document_center_overview()

    assert template_state['ready'] is False
    assert template_state['issues'][0]['code'] == 'schema_invalid'
    assert contract_state['state'] == 'blocked'
    assert contract_state['generation_allowed'] is False
    assert any(item['id'] == str(template.id) for item in overview['templates'])
