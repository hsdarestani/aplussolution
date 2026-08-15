import base64
import hashlib
import hmac
import urllib.parse
import zlib
from datetime import timedelta

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from django.utils import timezone
from lxml import etree
from rest_framework.test import APIClient
from signxml import XMLSigner, methods

from core.integration_v7_models import PayrollConnector, SamlIdentityProvider, WebhookDelivery, WebhookSubscription
from core.integration_v7_service import deliver_webhook, encrypt_secret
from core.payroll_models import PayPeriod, WorkerTimesheet


@pytest.mark.django_db
def test_api_key_is_shown_once_scoped_and_revocable(auth_admin, worker_user):
    created = auth_admin.post('/api/integrations/api-keys/', {'name': 'BI Export', 'scopes': ['workers.read']}, format='json')
    assert created.status_code == 201
    token = created.data['token']
    key_id = created.data['id']
    assert token.startswith('awf_')

    listed = auth_admin.get('/api/integrations/api-keys/')
    assert listed.status_code == 200
    assert 'token' not in listed.data['results'][0]
    assert 'secret_hash' not in listed.data['results'][0]

    external = APIClient()
    workers = external.get('/api/external/v1/workers/', HTTP_X_API_KEY=token)
    assert workers.status_code == 200
    assert workers.data['results'][0]['employee_number'] == worker_user.worker_profile.employee_number
    denied = external.get('/api/external/v1/shifts/', HTTP_X_API_KEY=token)
    assert denied.status_code == 403

    revoked = auth_admin.post(f'/api/integrations/api-keys/{key_id}/revoke/')
    assert revoked.status_code == 200
    rejected = external.get('/api/external/v1/workers/', HTTP_X_API_KEY=token)
    assert rejected.status_code in {401, 403}


@pytest.mark.django_db
def test_manager_without_workplace_manage_cannot_manage_integrations(api_client, manager_user):
    api_client.force_authenticate(manager_user)
    response = api_client.post('/api/integrations/api-keys/', {'name': 'Nope', 'scopes': ['workers.read']}, format='json')
    assert response.status_code == 403


@pytest.mark.django_db
def test_webhook_hmac_signature_and_success(monkeypatch, admin_user):
    secret = 'webhook-secret-value'
    subscription = WebhookSubscription.objects.create(
        name='ERP', url='https://example.test/hooks', event_types=['shift.updated'],
        secret_encrypted=encrypt_secret({'secret': secret}), created_by=admin_user,
    )
    delivery = WebhookDelivery.objects.create(
        subscription=subscription, event_type='shift.updated', payload={'id': 'shift-1', 'status': 'confirmed'}
    )
    captured = {}

    class Response:
        status_code = 204

    def fake_post(url, data, headers, timeout):
        captured.update(url=url, data=data, headers=headers, timeout=timeout)
        return Response()

    monkeypatch.setattr('core.integration_v7_service.requests.post', fake_post)
    deliver_webhook(delivery)
    delivery.refresh_from_db()
    assert delivery.status == WebhookDelivery.Status.DELIVERED
    timestamp = captured['headers']['X-APlus-Timestamp']
    expected = 'sha256=' + hmac.new(secret.encode(), f'{timestamp}.'.encode() + captured['data'], hashlib.sha256).hexdigest()
    assert hmac.compare_digest(captured['headers']['X-APlus-Signature'], expected)
    assert captured['headers']['X-APlus-Delivery'] == str(delivery.event_id)


@pytest.mark.django_db
def test_webhook_retries_then_dead_letters(monkeypatch, admin_user):
    subscription = WebhookSubscription.objects.create(
        name='Broken ERP', url='https://example.test/hooks', event_types=['*'], max_attempts=2,
        secret_encrypted=encrypt_secret({'secret': 'secret'}), created_by=admin_user,
    )
    delivery = WebhookDelivery.objects.create(subscription=subscription, event_type='shift.updated', payload={'id': 'x'})

    def fail(*args, **kwargs):
        raise TimeoutError('provider timeout')

    monkeypatch.setattr('core.integration_v7_service.requests.post', fail)
    deliver_webhook(delivery)
    delivery.refresh_from_db()
    assert delivery.status == WebhookDelivery.Status.RETRY
    assert delivery.attempts == 1
    deliver_webhook(delivery)
    delivery.refresh_from_db()
    assert delivery.status == WebhookDelivery.Status.DEAD
    assert delivery.attempts == 2
    assert 'provider timeout' in delivery.last_error


@pytest.mark.django_db
def test_domain_shift_creates_matching_webhook_delivery(auth_admin, shift, django_capture_on_commit_callbacks):
    subscription = WebhookSubscription.objects.create(
        name='Ops', url='https://example.test/hooks', event_types=['shift.updated'],
        secret_encrypted=encrypt_secret({'secret': 'secret'}), created_by=auth_admin.handler._force_user,
    )
    with django_capture_on_commit_callbacks(execute=True):
        shift.notes = 'updated'
        shift.save(update_fields=['notes', 'updated_at'])
    assert WebhookDelivery.objects.filter(subscription=subscription, event_type='shift.updated').exists()


@pytest.mark.django_db
def test_payroll_export_requires_closed_period_and_uses_snapshot(auth_admin, worker_user):
    period = PayPeriod.objects.create(
        name='August 2026', starts_on=timezone.localdate().replace(day=1), ends_on=timezone.localdate(),
        status=PayPeriod.Status.OPEN, created_by=auth_admin.handler._force_user,
    )
    WorkerTimesheet.objects.create(
        pay_period=period, worker=worker_user.worker_profile, status=WorkerTimesheet.Status.APPROVED,
        gross_minutes=480, net_minutes=450, gross_estimate='108.75', entry_count=1,
    )
    connector = PayrollConnector.objects.create(name='DATEV', provider=PayrollConnector.Provider.DATEV_CSV, created_by=auth_admin.handler._force_user)

    blocked = auth_admin.post(f'/api/integrations/payroll/connectors/{connector.id}/export/{period.id}/')
    assert blocked.status_code == 400
    period.status = PayPeriod.Status.CLOSED
    period.save(update_fields=['status', 'updated_at'])
    exported = auth_admin.post(f'/api/integrations/payroll/connectors/{connector.id}/export/{period.id}/')
    assert exported.status_code == 200
    assert exported['Content-Type'].startswith('text/csv')
    body = exported.content.decode('utf-8-sig')
    assert 'Personalnummer;Name;Von;Bis;Netto_Minuten;Brutto_EUR' in body
    assert worker_user.worker_profile.employee_number in body
    assert exported['X-APlus-Export-Run']


@pytest.mark.django_db
def test_external_timesheets_never_expose_wages(auth_admin, worker_user):
    period = PayPeriod.objects.create(
        name='Locked', starts_on=timezone.localdate() - timedelta(days=7), ends_on=timezone.localdate(),
        status=PayPeriod.Status.LOCKED, created_by=auth_admin.handler._force_user,
    )
    WorkerTimesheet.objects.create(pay_period=period, worker=worker_user.worker_profile, net_minutes=300, gross_estimate='999.99')
    key = auth_admin.post('/api/integrations/api-keys/', {'name': 'Timesheets', 'scopes': ['timesheets.read']}, format='json').data['token']
    response = APIClient().get('/api/external/v1/timesheets/', HTTP_X_API_KEY=key)
    assert response.status_code == 200
    row = response.data['results'][0]
    assert row['net_minutes'] == 300
    assert 'gross_estimate' not in row
    assert 'hourly_rate' not in row


def _certificate():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'A+ Test IdP')])
    cert = (
        x509.CertificateBuilder().subject_name(subject).issuer_name(issuer).public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(timezone.now() - timedelta(days=1)).not_valid_after(timezone.now() + timedelta(days=30))
        .sign(key, hashes.SHA256())
    )
    key_pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    return key_pem, cert_pem


@pytest.mark.django_db
def test_saml_signed_assertion_logs_in_and_tampering_is_rejected(auth_admin):
    key_pem, cert_pem = _certificate()
    provider = SamlIdentityProvider.objects.create(
        name='Test SSO', enabled=True, idp_entity_id='https://idp.example.test/entity',
        sso_url='https://idp.example.test/sso', x509_certificate=cert_pem.decode(),
        sp_entity_id='https://workforce.example.test/saml', allowed_domains=['example.com'], auto_provision=True,
    )
    client = APIClient()
    start = client.get(f'/api/auth/saml/{provider.id}/login/?target=%2Fschedule')
    assert start.status_code == 302
    query = urllib.parse.parse_qs(urllib.parse.urlparse(start['Location']).query)
    relay_state = query['RelayState'][0]
    compressed = base64.b64decode(query['SAMLRequest'][0])
    request_xml = zlib.decompress(compressed, -15)
    request_id = etree.fromstring(request_xml).get('ID')

    now = timezone.now()
    assertion_id = '_' + 'a' * 32
    assertion = etree.Element('{urn:oasis:names:tc:SAML:2.0:assertion}Assertion', nsmap={'saml': 'urn:oasis:names:tc:SAML:2.0:assertion'}, ID=assertion_id, Version='2.0', IssueInstant=now.strftime('%Y-%m-%dT%H:%M:%SZ'))
    etree.SubElement(assertion, '{urn:oasis:names:tc:SAML:2.0:assertion}Issuer').text = provider.idp_entity_id
    subject = etree.SubElement(assertion, '{urn:oasis:names:tc:SAML:2.0:assertion}Subject')
    etree.SubElement(subject, '{urn:oasis:names:tc:SAML:2.0:assertion}NameID').text = 'sso.user@example.com'
    confirmation = etree.SubElement(subject, '{urn:oasis:names:tc:SAML:2.0:assertion}SubjectConfirmation')
    etree.SubElement(confirmation, '{urn:oasis:names:tc:SAML:2.0:assertion}SubjectConfirmationData', InResponseTo=request_id, Recipient='http://testserver/api/auth/saml/acs/', NotOnOrAfter=(now + timedelta(minutes=5)).strftime('%Y-%m-%dT%H:%M:%SZ'))
    conditions = etree.SubElement(assertion, '{urn:oasis:names:tc:SAML:2.0:assertion}Conditions', NotBefore=(now - timedelta(minutes=1)).strftime('%Y-%m-%dT%H:%M:%SZ'), NotOnOrAfter=(now + timedelta(minutes=5)).strftime('%Y-%m-%dT%H:%M:%SZ'))
    restriction = etree.SubElement(conditions, '{urn:oasis:names:tc:SAML:2.0:assertion}AudienceRestriction')
    etree.SubElement(restriction, '{urn:oasis:names:tc:SAML:2.0:assertion}Audience').text = provider.sp_entity_id
    signed = XMLSigner(method=methods.enveloped, signature_algorithm='rsa-sha256', digest_algorithm='sha256').sign(assertion, key=key_pem, cert=cert_pem, reference_uri=assertion_id)
    response_xml = etree.Element('{urn:oasis:names:tc:SAML:2.0:protocol}Response', nsmap={'samlp': 'urn:oasis:names:tc:SAML:2.0:protocol'})
    response_xml.append(signed)
    encoded = base64.b64encode(etree.tostring(response_xml)).decode()

    accepted = client.post('/api/auth/saml/acs/', {'SAMLResponse': encoded, 'RelayState': relay_state}, format='multipart')
    assert accepted.status_code == 200
    assert accepted.data['user']['email'] == 'sso.user@example.com'
    assert accepted.data['target'] == '/schedule'
    assert accepted.data['provisioned'] is True

    tampered_xml = etree.fromstring(base64.b64decode(encoded))
    tampered_xml.xpath('.//*[local-name()="NameID"]')[0].text = 'attacker@example.com'
    tampered = base64.b64encode(etree.tostring(tampered_xml)).decode()
    rejected = client.post('/api/auth/saml/acs/', {'SAMLResponse': tampered, 'RelayState': relay_state}, format='multipart')
    assert rejected.status_code == 400
