import base64
import uuid
import zlib
from datetime import datetime, timezone as dt_timezone
from urllib.parse import urlencode

from django.core import signing
from django.utils import timezone
from lxml import etree
from signxml import XMLVerifier

from .integration_v7_models import SamlIdentityProvider
from .models import User


NS = {'saml': 'urn:oasis:names:tc:SAML:2.0:assertion', 'samlp': 'urn:oasis:names:tc:SAML:2.0:protocol'}
STATE_SALT = 'aplus-workforce-saml-v7'


def _instant(value):
    if not value:
        return None
    value = value.replace('Z', '+00:00')
    return datetime.fromisoformat(value).astimezone(dt_timezone.utc)


def sp_entity_id(provider, request):
    return provider.sp_entity_id or request.build_absolute_uri('/api/auth/saml/metadata/')


def acs_url(request):
    return request.build_absolute_uri('/api/auth/saml/acs/')


def build_login_redirect(provider, request, target='/'):
    if not provider.enabled:
        raise ValueError('SAML provider is disabled.')
    request_id = '_' + uuid.uuid4().hex
    issue_instant = timezone.now().astimezone(dt_timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
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
    state = signing.dumps({'provider': str(provider.id), 'request_id': request_id, 'target': target}, salt=STATE_SALT, compress=True)
    return provider.sso_url + ('&' if '?' in provider.sso_url else '?') + urlencode({'SAMLRequest': encoded, 'RelayState': state})


def _signed_xml(provider, saml_response):
    raw = base64.b64decode(saml_response, validate=True)
    parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False, remove_comments=True)
    etree.fromstring(raw, parser=parser)  # reject malformed/unsafe XML before signature validation
    verified = XMLVerifier().verify(raw, x509_cert=provider.x509_certificate)
    return verified.signed_xml


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


def validate_response(provider, request, saml_response, relay_state):
    state = signing.loads(relay_state, salt=STATE_SALT, max_age=600)
    if state.get('provider') != str(provider.id):
        raise ValueError('SAML state/provider mismatch.')
    signed = _signed_xml(provider, saml_response)
    request_id = state.get('request_id')

    confirmation = signed.xpath('.//saml:SubjectConfirmationData', namespaces=NS)
    if confirmation:
        data = confirmation[0]
        if data.get('InResponseTo') != request_id:
            raise ValueError('SAML InResponseTo mismatch.')
        if data.get('Recipient') and data.get('Recipient') != acs_url(request):
            raise ValueError('SAML recipient mismatch.')
        expiry = _instant(data.get('NotOnOrAfter'))
        if expiry and timezone.now() >= expiry:
            raise ValueError('SAML assertion expired.')

    conditions = signed.xpath('.//saml:Conditions', namespaces=NS)
    if conditions:
        cond = conditions[0]
        now = timezone.now()
        not_before = _instant(cond.get('NotBefore'))
        not_after = _instant(cond.get('NotOnOrAfter'))
        if not_before and now < not_before:
            raise ValueError('SAML assertion not active yet.')
        if not_after and now >= not_after:
            raise ValueError('SAML assertion expired.')

    audiences = [str(value).strip() for value in signed.xpath('.//saml:Audience/text()', namespaces=NS)]
    expected_audience = sp_entity_id(provider, request)
    if not audiences or expected_audience not in audiences:
        raise ValueError('SAML audience mismatch.')

    issuer = _first_text(signed, './/saml:Issuer')
    if issuer != provider.idp_entity_id:
        raise ValueError('SAML issuer mismatch.')

    email = _attribute(signed, 'email', 'mail', 'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress')
    email = email or _first_text(signed, './/saml:NameID')
    email = email.strip().lower()
    if '@' not in email:
        raise ValueError('SAML response does not contain a valid email address.')
    domain = email.rsplit('@', 1)[1]
    allowed = {str(item).lower().strip() for item in (provider.allowed_domains or []) if str(item).strip()}
    if allowed and domain not in allowed:
        raise ValueError('SAML email domain is not allowed.')

    first_name = _attribute(signed, 'first_name', 'givenName', 'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname')
    last_name = _attribute(signed, 'last_name', 'surname', 'sn', 'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname')
    return {'email': email, 'first_name': first_name, 'last_name': last_name, 'target': state.get('target') or '/'}


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
