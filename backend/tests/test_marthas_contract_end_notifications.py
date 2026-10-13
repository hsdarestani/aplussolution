"""Regression coverage: Marthas contacts must never see contract-end alerts."""
from datetime import timedelta
from uuid import uuid4

import pytest
from django.core import mail
from django.utils import timezone
from rest_framework.test import APIClient

from core.contract_notification_policy import (
    is_contract_end_notice,
    suppress_contract_end_notice,
)
from core.document_center import _create_notice, dispatch_contract_reminders
from core.models import ClientCompany, Contract, ContractTemplate, Notification, User
from core.notification_settings import render_push_notification
from core.push_models import PushDevice
from core.push_notifications import deliver_notification


@pytest.fixture
def marthas_contact(db):
    user = User.objects.create_user(
        email='julia.stahl@example.com',
        password='StrongPass123!',
        first_name='Julia',
        last_name='Stahl',
        role=User.Role.CLIENT,
    )
    marthas = ClientCompany.objects.create(
        name='Marthas Finest GmbH',
        customer_number='KD-MARTHAS-NOTIF',
    )
    marthas.contacts.add(user)
    return user


@pytest.fixture
def marthas_contract(marthas_contact, admin_user):
    company = marthas_contact.client_companies.first()
    template = ContractTemplate.objects.create(
        name='Expiry visibility test',
        slug='marthas-expiry-visibility-test',
        kind=ContractTemplate.Kind.CLIENT_AUEV,
        source_format=ContractTemplate.SourceFormat.HTML,
        html_template='<p>Test</p>',
        schema={'fields': [], 'signature_roles': []},
    )
    return Contract.objects.create(
        template=template,
        client=company,
        title='Marthas Vertrag',
        status=Contract.Status.SENT,
        ends_on=timezone.localdate() + timedelta(days=7),
        created_by=admin_user,
    )


@pytest.mark.django_db
def test_deadline_kind_only_covers_end_dates(marthas_contact):
    for kind in ('contract-30-id', 'contract-7-id', 'contract-end-14d-id',
                 'contract-end-1d-id', 'contract-end-0d-id'):
        assert is_contract_end_notice(kind)
        assert suppress_contract_end_notice(marthas_contact, kind)
    for kind in ('contract-sent-id', 'contract-signature-3d-id',
                 'contract-explicit-reminder-id', 'shift-event-deleted-id'):
        assert not is_contract_end_notice(kind)
        assert not suppress_contract_end_notice(marthas_contact, kind)


@pytest.mark.django_db
def test_contract_expiration_dispatch_skips_marthas_but_not_admins(
    marthas_contact, marthas_contract, admin_user, monkeypatch
):
    monkeypatch.setattr('core.push_signals.push_provider_configured', lambda: False)
    today = marthas_contract.ends_on - timedelta(days=7)
    result = dispatch_contract_reminders(today=today)
    assert result['notifications'] >= 1
    assert not Notification.objects.filter(
        user=marthas_contact, kind=f'contract-7-{marthas_contract.id}'
    ).exists()
    assert Notification.objects.filter(
        user=admin_user, kind=f'contract-7-{marthas_contract.id}'
    ).exists()
    assert not any(marthas_contact.email in message.to for message in mail.outbox)
    assert any(admin_user.email in message.to for message in mail.outbox)


@pytest.mark.django_db
def test_existing_contract_end_notifications_are_invisible_to_marthas(
    marthas_contact, client_user, admin_user, monkeypatch
):
    monkeypatch.setattr('core.push_signals.push_provider_configured', lambda: False)
    hidden = Notification.objects.create(
        user=marthas_contact, kind=f'contract-end-14d-{uuid4()}',
        title='Vertragsende', body='Vertrag endet in 14 Tagen',
    )
    Notification.objects.create(
        user=marthas_contact, kind=f'contract-30-{uuid4()}',
        title='Vertragsende', body='Vertrag endet in 30 Tagen',
    )
    visible = Notification.objects.create(
        user=marthas_contact, kind=f'contract-signature-3d-{uuid4()}',
        title='Unterschrift ausstehend', body='Unterschrift erforderlich',
    )
    shift = Notification.objects.create(
        user=marthas_contact, kind='shift-event-updated-test',
        title='Schicht geändert', body='Neue Uhrzeit',
    )
    ordinary_client_notice = Notification.objects.create(
        user=client_user, kind=f'contract-end-14d-{uuid4()}',
        title='Vertragsende', body='Vertrag endet in 14 Tagen',
    )
    admin_notice = Notification.objects.create(
        user=admin_user, kind=f'contract-end-14d-{uuid4()}',
        title='Vertragsende', body='Vertrag endet in 14 Tagen',
    )

    def ids_for(user):
        client = APIClient()
        client.force_authenticate(user)
        response = client.get('/api/notifications/')
        assert response.status_code == 200
        data = response.data
        rows = data.get('results', []) if isinstance(data, dict) else data
        return {str(item['id']) for item in rows}

    marthas_ids = ids_for(marthas_contact)
    assert str(hidden.id) not in marthas_ids
    assert str(visible.id) in marthas_ids
    assert str(shift.id) in marthas_ids
    assert str(ordinary_client_notice.id) in ids_for(client_user)
    assert str(admin_notice.id) in ids_for(admin_user)


@pytest.mark.django_db
def test_delayed_push_for_marthas_expiry_is_suppressed(
    marthas_contact, client_user, monkeypatch
):
    monkeypatch.setattr('core.push_signals.push_provider_configured', lambda: False)
    device = PushDevice.objects.create(
        user=marthas_contact, platform=PushDevice.Platform.ANDROID, token='e' * 64,
    )
    old = Notification.objects.create(
        user=marthas_contact, kind=f'contract-7-{uuid4()}',
        title='Vertragsende', body='Vertrag endet in 7 Tagen',
    )
    enabled, *_ = render_push_notification(old)
    assert enabled is False
    result = deliver_notification(old)
    assert result['sent'] == 0
    assert result['skipped'] == 1
    assert PushDevice.objects.get(pk=device.pk).active is True

    normal = Notification.objects.create(
        user=client_user, kind=f'contract-7-{uuid4()}',
        title='Vertragsende', body='Vertrag endet in 7 Tagen',
    )
    assert render_push_notification(normal)[0] is True


@pytest.mark.django_db
def test_manual_notice_still_delivered_to_marthas(
    marthas_contact, marthas_contract, monkeypatch
):
    monkeypatch.setattr('core.push_signals.push_provider_configured', lambda: False)
    count, emails = _create_notice(
        marthas_contract, 'contract-signature-3d',
        'Unterschrift ausstehend', 'Bitte unterschreiben', [marthas_contact],
    )
    assert (count, emails) == (1, 1)
    assert Notification.objects.filter(
        user=marthas_contact, kind=f'contract-signature-3d-{marthas_contract.id}'
    ).exists()
