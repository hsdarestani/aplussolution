import pytest

from core.models import Contract, ContractTemplate


@pytest.mark.django_db
def test_contract_api_exposes_readiness_for_ui_actions(auth_admin, admin_user, worker_user):
    template = ContractTemplate.objects.create(
        name='UI Lifecycle HTML',
        slug='ui-lifecycle-html',
        kind=ContractTemplate.Kind.EMPLOYMENT,
        source_format=ContractTemplate.SourceFormat.HTML,
        html_template='<p>{{ employee_name }}</p>',
        schema={'fields': [], 'signature_roles': ['employee']},
    )
    contract = Contract.objects.create(
        template=template,
        worker=worker_user.worker_profile,
        title='UI Lifecycle Vertrag',
        created_by=admin_user,
    )

    response = auth_admin.get(f'/api/contracts/{contract.id}/')
    assert response.status_code == 200
    readiness = response.data['readiness']
    assert readiness['generation_allowed'] is True
    assert readiness['send_allowed'] is True
    assert readiness['pending_signature_roles'] == ['employee']
    assert 'employer' not in readiness['pending_signature_roles']

    generated = auth_admin.post(f'/api/contracts/{contract.id}/generate_pdf/', {}, format='json')
    assert generated.status_code == 200
    assert generated.data['readiness']['document_current'] is True
    assert generated.data['readiness']['generation_allowed'] is True

    sent = auth_admin.post(f'/api/contracts/{contract.id}/send/', {}, format='json')
    assert sent.status_code == 200
    assert sent.data['readiness']['generation_allowed'] is False
    assert sent.data['readiness']['send_allowed'] is False
    assert sent.data['readiness']['pending_signature_roles'] == ['employee']
