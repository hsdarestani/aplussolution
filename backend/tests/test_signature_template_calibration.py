from django.core.management import call_command

import pytest

from core.management.commands.calibrate_signature_templates import DGB_SIGNATURE_PLACEMENTS
from core.models import ContractTemplate


@pytest.mark.django_db
def test_dgb_signature_calibration_preserves_schema_and_pins_both_roles():
    template, _ = ContractTemplate.objects.update_or_create(
        slug='arbeitsvertrag-dgb-gvp',
        defaults={
            'name': 'Arbeitsvertrag DGB/GVP',
            'kind': ContractTemplate.Kind.EMPLOYMENT,
            'audience': ContractTemplate.Audience.WORKER,
            'version': 'test',
            'schema': {
                'fields': [{'name': 'employee_name', 'label': 'Name'}],
                'signature_roles': ['employee', 'employer'],
                'overlay': {'keep': 'me'},
            },
            'source_format': ContractTemplate.SourceFormat.DOCX,
            'requires_signature': True,
            'required_document': True,
            'active': True,
        },
    )

    call_command('calibrate_signature_templates')
    template.refresh_from_db()

    assert template.schema['signature_placements'] == DGB_SIGNATURE_PLACEMENTS
    assert template.schema['fields'] == [{'name': 'employee_name', 'label': 'Name'}]
    assert template.schema['signature_roles'] == ['employee', 'employer']
    assert template.schema['overlay'] == {'keep': 'me'}
    assert template.schema['signature_placements']['employee']['page'] == 6
    assert template.schema['signature_placements']['employer']['page'] == 6
    assert template.schema['signature_placements']['employee']['x'] < 0.1
    assert template.schema['signature_placements']['employer']['x'] < 0.1
