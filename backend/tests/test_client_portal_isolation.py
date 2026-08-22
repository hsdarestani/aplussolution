from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from core.models import (
    ClientCompany,
    ClientOrder,
    Contract,
    ContractTemplate,
    Conversation,
    Document,
    Location,
    Message,
    Shift,
    User,
    WorkerRating,
)

pytestmark = pytest.mark.django_db


def foreign_tenant(position, second_worker):
    user = User.objects.create_user(
        'isolation-foreign@example.com', 'StrongPass123!',
        first_name='Fremd', last_name='Kunde', role=User.Role.CLIENT, is_onboarded=True,
    )
    company = ClientCompany.objects.create(
        name='Fremdmandant GmbH', customer_number='KD-ISO-2', address='Fremdstraße 2',
    )
    company.contacts.add(user)
    location = Location.objects.create(client=company, name='Fremdmandant Halle', address='Fremdstraße 3')
    start = timezone.now() + timedelta(days=2)
    order = ClientOrder.objects.create(
        client=company, location=location, title='Fremdauftrag', starts_at=start,
        ends_at=start + timedelta(hours=5), requested_staff=1, created_by=user,
    )
    shift = Shift.objects.create(
        order=order, client=company, location=location, position=position, worker=second_worker,
        starts_at=start, ends_at=start + timedelta(hours=5), status=Shift.Status.CONFIRMED,
    )
    template = ContractTemplate.objects.create(
        name='Fremdmandant Vertrag', slug='fremdmandant-vertrag', kind=ContractTemplate.Kind.CLIENT_AUEV,
        audience=ContractTemplate.Audience.CLIENT, version='1.0', schema={'signature_roles': ['client']},
        source_format=ContractTemplate.SourceFormat.STATIC_PDF, requires_signature=True, active=True,
    )
    contract = Contract.objects.create(
        template=template, client=company, title='Fremdvertrag', status=Contract.Status.READY, created_by=user,
    )
    document = Document.objects.create(
        client=company, title='Fremddokument', visibility=Document.Visibility.CLIENT,
        file=SimpleUploadedFile('foreign.txt', b'foreign'), uploaded_by=user,
    )
    rating = WorkerRating.objects.create(
        client=company, worker=second_worker, shift=shift, score=5, punctuality=5,
        quality=5, teamwork=5, comment='Fremdbewertung', created_by=user,
    )
    conversation = Conversation.objects.create(title='Fremde Unterhaltung')
    conversation.participants.add(user)
    Message.objects.create(conversation=conversation, sender=user, body='Private Fremdnachricht')
    return {
        'user': user, 'company': company, 'location': location, 'order': order, 'shift': shift,
        'contract': contract, 'document': document, 'rating': rating, 'conversation': conversation,
    }


def rows(response):
    data = response.data
    return data.get('results', data) if hasattr(data, 'get') else data


def test_client_list_and_detail_endpoints_hide_foreign_tenant(
    auth_client, company, location, position, second_worker, client_user
):
    foreign = foreign_tenant(position, second_worker)
    now = timezone.now() + timedelta(days=1)
    own_order = ClientOrder.objects.create(
        client=company, location=location, title='Eigener Auftrag', starts_at=now,
        ends_at=now + timedelta(hours=3), created_by=client_user,
    )

    endpoint_and_foreign = [
        ('orders', foreign['order']),
        ('shifts', foreign['shift']),
        ('contracts', foreign['contract']),
        ('documents', foreign['document']),
        ('ratings', foreign['rating']),
        ('conversations', foreign['conversation']),
    ]
    for endpoint, obj in endpoint_and_foreign:
        listing = auth_client.get(f'/api/{endpoint}/')
        assert listing.status_code == 200
        serialized = str(rows(listing))
        assert str(obj.id) not in serialized
        detail = auth_client.get(f'/api/{endpoint}/{obj.id}/')
        assert detail.status_code == 404

    own = auth_client.get('/api/orders/')
    assert own.status_code == 200
    assert any(str(item['id']) == str(own_order.id) for item in rows(own))


def test_client_message_recipient_picker_exposes_only_disposition(auth_client, admin_user, manager_user, worker_user):
    response = auth_client.get('/api/portal/message-recipients/')
    assert response.status_code == 200
    assert response.data
    assert {item['role'] for item in response.data}.issubset({User.Role.ADMIN, User.Role.MANAGER})
    assert all(set(item.keys()) == {'id', 'name', 'role'} for item in response.data)
    ids = {item['id'] for item in response.data}
    assert str(worker_user.id) not in ids
    assert str(admin_user.id) in ids
    assert str(manager_user.id) in ids


def test_client_contract_can_only_sign_own_client_role(auth_client, company, client_user):
    template = ContractTemplate.objects.create(
        name='Eigener Kundenvertrag', slug='eigener-kundenvertrag', kind=ContractTemplate.Kind.CLIENT_AUEV,
        audience=ContractTemplate.Audience.CLIENT, version='1.0', schema={'signature_roles': ['client']},
        source_format=ContractTemplate.SourceFormat.STATIC_PDF, requires_signature=True, active=True,
    )
    contract = Contract.objects.create(
        template=template, client=company, title='Eigener Kundenvertrag', status=Contract.Status.READY,
        created_by=client_user,
    )

    wrong_role = auth_client.post(
        f'/api/contracts/{contract.id}/sign/',
        {'name': 'Klara Kunde', 'signature': 'data:image/png;base64,ZmFrZQ==', 'role': 'employer'},
        format='json',
    )
    assert wrong_role.status_code == 400

    valid = auth_client.post(
        f'/api/contracts/{contract.id}/sign/',
        {'name': 'Klara Kunde', 'signature': 'data:image/png;base64,ZmFrZQ==', 'role': 'client'},
        format='json',
    )
    assert valid.status_code == 200, valid.data
    contract.refresh_from_db()
    assert contract.signatures.filter(role='client', signer=client_user).count() == 1
    assert contract.status == Contract.Status.SIGNED
