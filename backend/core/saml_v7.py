import base64
import uuid
import zlib
from datetime import datetime, timedelta, timezone as dt_timezone
from urllib.parse import urlencode

from django.core import signing
from django.db import transaction
from django.utils import timezone
from lxml import etree
from signxml import SignatureConfiguration, XMLVerifier

from .integration_v7_models import SamlIdentityProvider, SamlLoginRequest
from .models import User


NS = {
    'saml': 'urn:oasis:names:tc:SAML:2.0:assertion',
    'samlp': 'urn:oasis:names:tc:SAML:2.0:protocol',
    'ds': 'http://www.w3.org/2000/09/xmldsig#',
}
STATE_SALT = 'aplus-workforce-saml-v7'


def _instant(value):
    if not value:
        return None
    value = value.replace('Z', '+00:00')
    return datetime.fromisoformat(value).astimezone(dt_timezone.utc)


def _safe_target(value):
    value = str(value or '/').strip()
    return value if value.startswith('/') and not value.startswith('//') else '/'


def sp_entity_id(provider, request):
    return provider.sp_entity_id or request.build_absolute_uri('/api/auth/saml/metadata/')


def acs_url(request):
    return request.build_absolute_uri('/api/auth/saml/acs/')


def build_login_redirect(provider, request, target='/'):
    if not provider.enabled:
        raise ValueError('SAML provider is disabled.')
    request_id = '_' + uuid.uuid4().hex
    target = _safe_target(target)
    now = timezone.now()
    SamlLoginRequest.objects.create(
        provider=provider,
        request_id=request_id,
        target=target,
        expires_at=now + timedelta(minutes=10),
    )
    issue_instant = now.astimezone(dt_timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    root = etree.Element('{urn:oasis:names:tc:SAML:2.0:protocol}AuthnRequest', nsmap={'samlp': NS['samlp'], 'saml': NS['saml']})
    root.set('ID', request_id)
    root.set('Version', '2.0')
    root.set('IssueInstant', issue_instant)
    root.set('Destination', provider.sso_url)
    root.set('AssertionConsumerServiceURL', acs_url(request))
    issuer = etree.SubElement(root, '{urn:oasis:names:tc:SAML:2.0:assertion}Issuer')
    issuer.text = sp_entity_id(provider, request)
    xml = etree.tostring(root, xml_declaration=False, encoding='utf-8')
    compressor = zlib.compressobj(wbits=-15)
    encoded = base64.b64encode(compressor.compress(xml) + compressor.flush()).decode('ascii')
    state = signing.dumps({'provider': str(provider.id), 'request_id': request_id}, salt=STATE_SALT, compress=True)
    return provider.sso_url + ('&' if '?' in provider.sso_url else '?') + urlencode({'SAMLRequest': encoded, 'RelayState': state})


def _signed_xml(provider, saml_response):
    raw = base64.b64decode(saml_response, validate=True)
    parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False, remove_comments=True)
    root = etree.fromstring(raw, parser=parser)
    if etree.QName(root).namespace != NS['samlp'] or etree.QName(root).localname != 'Response':
        raise ValueError('SAML payload must contain a protocol Response.')

    assertions = root.xpath('./saml:Assertion', namespaces=NS)
    if len(assertions) != 1:
        raise ValueError('SAML response must contain exactly one assertion.')
    assertion = assertions[0]
    assertion_signatures = assertion.xpath('./ds:Signature', namespaces=NS)
    response_signatures = root.xpath('./ds:Signature', namespaces=NS)
    config = SignatureConfiguration(location='./')

    if len(assertion_signatures) == 1:
        verified = XMLVerifier().verify(assertion, x509_cert=provider.x509_certificate, expect_config=config)
        signed = verified.signed_xml
        if etree.QName(signed).namespace != NS['saml'] or etree.QName(signed).localname != 'Assertion':
            raise ValueError('SAML signature did not cover the assertion.')
        return signed

    if len(assertion_signatures) > 1 or len(response_signatures) != 1:
        raise ValueError('SAML response must contain one unambiguous assertion or response signature.')
    verified = XMLVerifier().verify(root, x509_cert=provider.x509_certificate, expect_config=config)
    signed_root = verified.signed_xml
    signed_assertions = signed_root.xpath('./saml:Assertion', namespaces=NS)
    if len(signed_assertions) != 1:
        raise ValueError('Signed SAML response must contain exactly one assertion.')
    return signed_assertions[0]


def _first_text(node, xpath):
    found = node.xpath(xpath, namespaces=NS)
    if not found:
        return ''
    item = found[0]
    return (item.text or '').strip() if hasattr(item, 'text') else str(item).strip()


def _attribute(node, *names):
    for name in names:
        values = node.xpath(f'.//saml:Attribute[@Name="{name}"]/saml:AttributeValue', namespaces=NS)
        if values:
            return (values[0].text or '').strip()
    return ''


def _consume_login_request(provider, request_id):
    now = timezone.now()
    with transaction.atomic():
        row = SamlLoginRequest.objects.select_for_update().filter(provider=provider, request_id=request_id).first()
        if not row:
            raise ValueError('Unknown SAML request state.')
        if row.used_at:
            raise ValueError('SAML response has already been used.')
        if row.expires_at <= now:
            raise ValueError('SAML request state expired.')
        row.used_at = now
        row.save(update_fields=['used_at', 'updated_at'])
        return row.target


def validate_response(provider, request, saml_response, relay_state):
    state = signing.loads(relay_state, salt=STATE_SALT, max_age=600)
    if state.get('provider') != str(provider.id):
        raise ValueError('SAML state/provider mismatch.')
    request_id = state.get('request_id')
    if not request_id:
        raise ValueError('SAML state is missing request ID.')
    state_row = SamlLoginRequest.objects.filter(provider=provider, request_id=request_id).first()
    if not state_row or state_row.used_at or state_row.expires_at <= timezone.now():
        raise ValueError('SAML request state is invalid or expired.')

    signed = _signed_xml(provider, saml_response)
    confirmation = signed.xpath('.//saml:SubjectConfirmationData', namespaces=NS)
    if not confirmation:
        raise ValueError('SAML assertion is missing SubjectConfirmationData.')
    if len(confirmation) != 1:
        raise ValueError('SAML assertion contains ambiguous subject confirmations.')
    data = confirmation[0]
    if data.get('InResponseTo') != request_id:
        raise ValueError('SAML InResponseTo mismatch.')
    if data.get('Recipient') != acs_url(request):
        raise ValueError('SAML recipient mismatch.')
    expiry = _instant(data.get('NotOnOrAfter'))
    if not expiry or timezone.now() >= expiry:
        raise ValueError('SAML assertion expired or has no expiry.')

    conditions = signed.xpath('./saml:Conditions', namespaces=NS)
    if len(conditions) != 1:
        raise ValueError('SAML assertion must contain exactly one Conditions element.')
    cond = conditions[0]
    now = timezone.now()
    not_before = _instant(cond.get('NotBefore'))
    not_after = _instant(cond.get('NotOnOrAfter'))
    if not not_after:
        raise ValueError('SAML conditions require NotOnOrAfter.')
    if not_before and now < not_before:
        raise ValueError('SAML assertion not active yet.')
    if now >= not_after:
        raise ValueError('SAML assertion expired.')

    audiences = [str(value).strip() for value in signed.xpath('./saml:Conditions/saml:AudienceRestriction/saml:Audience/text()', namespaces=NS)]
    expected_audience = sp_entity_id(provider, request)
    if audiences != [expected_audience]:
        raise ValueError('SAML audience mismatch.')

    issuer = _first_text(signed, './saml:Issuer')
    if issuer != provider.idp_entity_id:
        raise ValueError('SAML issuer mismatch.')

    email = _attribute(signed, 'email', 'mail', 'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress')
    email = email or _first_text(signed, './saml:Subject/saml:NameID')
    email = email.strip().lower()
    if '@' not in email:
        raise ValueError('SAML response does not contain a valid email address.')
    domain = email.rsplit('@', 1)[1]
    allowed = {str(item).lower().strip() for item in (provider.allowed_domains or []) if str(item).strip()}
    if allowed and domain not in allowed:
        raise ValueError('SAML email domain is not allowed.')

    first_name = _attribute(signed, 'first_name', 'givenName', 'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname')
    last_name = _attribute(signed, 'last_name', 'surname', 'sn', 'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname')
    target = _consume_login_request(provider, request_id)
    return {'email': email, 'first_name': first_name, 'last_name': last_name, 'target': target}


def resolve_user(provider, identity):
    user = User.objects.filter(email__iexact=identity['email']).first()
    if user:
        if not user.is_active:
            raise ValueError('User account is disabled.')
        return user, False
    if not provider.auto_provision:
        raise ValueError('No local user exists and SAML auto-provisioning is disabled.')
    role = provider.default_role
    if role == User.Role.ADMIN:
        raise ValueError('SAML auto-provisioning cannot create administrator accounts.')
    user = User.objects.create_user(
        email=identity['email'],
        password=None,
        first_name=identity.get('first_name', ''),
        last_name=identity.get('last_name', ''),
        role=role,
        is_onboarded=True,
    )
    user.set_unusable_password()
    user.save(update_fields=['password'])
    return user, True


def metadata_xml(provider, request):
    entity = sp_entity_id(provider, request)
    acs = acs_url(request)
    root = etree.Element('{urn:oasis:names:tc:SAML:2.0:metadata}EntityDescriptor', nsmap={'md': 'urn:oasis:names:tc:SAML:2.0:metadata'})
    root.set('entityID', entity)
    descriptor = etree.SubElement(root, '{urn:oasis:names:tc:SAML:2.0:metadata}SPSSODescriptor')
    descriptor.set('protocolSupportEnumeration', NS['samlp'])
    descriptor.set('AuthnRequestsSigned', 'false')
    descriptor.set('WantAssertionsSigned', 'true')
    acs_node = etree.SubElement(descriptor, '{urn:oasis:names:tc:SAML:2.0:metadata}AssertionConsumerService')
    acs_node.set('Binding', 'urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST')
    acs_node.set('Location', acs)
    acs_node.set('index', '0')
    acs_node.set('isDefault', 'true')
    return etree.tostring(root, xml_declaration=True, encoding='utf-8')
