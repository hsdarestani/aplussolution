from urllib.parse import urlencode

from django.conf import settings
from django.http import HttpResponse, HttpResponseRedirect
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from .models import User
from .premium_models import SamlIdentity


def _enabled():
    return bool(settings.SAML_ENABLED and settings.SAML_SP_ENTITY_ID and settings.SAML_IDP_ENTITY_ID and settings.SAML_IDP_SSO_URL and settings.SAML_IDP_X509_CERT)


def _request_data(request):
    scheme = request.headers.get('X-Forwarded-Proto', request.scheme)
    host = request.get_host()
    return {'https': 'on' if scheme == 'https' else 'off', 'http_host': host, 'server_port': '443' if scheme == 'https' else '80', 'script_name': request.path, 'get_data': request.GET.copy(), 'post_data': request.POST.copy()}


def _config():
    return {
        'strict': True,
        'debug': settings.DEBUG,
        'sp': {
            'entityId': settings.SAML_SP_ENTITY_ID,
            'assertionConsumerService': {'url': settings.SAML_SP_ACS_URL, 'binding': 'urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST'},
            'singleLogoutService': {'url': settings.SAML_SP_SLS_URL, 'binding': 'urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect'},
            'x509cert': settings.SAML_SP_X509_CERT,
            'privateKey': settings.SAML_SP_PRIVATE_KEY,
        },
        'idp': {
            'entityId': settings.SAML_IDP_ENTITY_ID,
            'singleSignOnService': {'url': settings.SAML_IDP_SSO_URL, 'binding': 'urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect'},
            'singleLogoutService': {'url': settings.SAML_IDP_SLO_URL, 'binding': 'urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect'},
            'x509cert': settings.SAML_IDP_X509_CERT,
        },
        'security': {
            'authnRequestsSigned': bool(settings.SAML_SP_PRIVATE_KEY), 'logoutRequestSigned': bool(settings.SAML_SP_PRIVATE_KEY), 'logoutResponseSigned': bool(settings.SAML_SP_PRIVATE_KEY), 'signMetadata': bool(settings.SAML_SP_PRIVATE_KEY),
            'wantMessagesSigned': False, 'wantAssertionsSigned': True, 'wantNameId': True, 'wantNameIdEncrypted': False, 'wantAssertionsEncrypted': False, 'wantAttributeStatement': True, 'requestedAuthnContext': False,
        },
    }


def _auth(request):
    from onelogin.saml2.auth import OneLogin_Saml2_Auth
    return OneLogin_Saml2_Auth(_request_data(request), _config())


@api_view(['GET'])
@permission_classes([AllowAny])
def saml_status(request):
    return Response({'enabled': _enabled(), 'entity_id': settings.SAML_SP_ENTITY_ID if settings.SAML_ENABLED else ''})


@api_view(['GET'])
@permission_classes([AllowAny])
def saml_metadata(request):
    if not _enabled():
        return Response({'detail': 'SAML/SSO ist nicht konfiguriert.'}, status=404)
    from onelogin.saml2.settings import OneLogin_Saml2_Settings
    saml_settings = OneLogin_Saml2_Settings(settings=_config(), sp_validation_only=True)
    metadata = saml_settings.get_sp_metadata()
    errors = saml_settings.validate_metadata(metadata)
    if errors:
        return Response({'detail': 'Ungültige SAML-Metadaten.', 'errors': errors}, status=500)
    return HttpResponse(metadata, content_type='application/samlmetadata+xml')


@api_view(['GET'])
@permission_classes([AllowAny])
def saml_login(request):
    if not _enabled():
        return Response({'detail': 'SAML/SSO ist nicht konfiguriert.'}, status=404)
    return HttpResponseRedirect(_auth(request).login(return_to=settings.APP_URL))


@api_view(['POST'])
@permission_classes([AllowAny])
def saml_acs(request):
    if not _enabled():
        return Response({'detail': 'SAML/SSO ist nicht konfiguriert.'}, status=404)
    auth = _auth(request)
    auth.process_response()
    errors = auth.get_errors()
    if errors or not auth.is_authenticated():
        return Response({'detail': auth.get_last_error_reason() or 'SAML-Anmeldung fehlgeschlagen.', 'errors': errors}, status=401)
    attrs = auth.get_attributes() or {}
    email_values = attrs.get(settings.SAML_EMAIL_ATTRIBUTE) or attrs.get('email') or attrs.get('mail') or []
    email = str(email_values[0]).strip().lower() if email_values else ''
    name_id = str(auth.get_nameid() or '').strip()
    if not email and '@' in name_id:
        email = name_id.lower()
    if not email:
        return Response({'detail': 'Der Identity Provider hat keine E-Mail-Adresse geliefert.'}, status=400)
    try:
        user = User.objects.get(email__iexact=email, is_active=True)
    except User.DoesNotExist:
        return Response({'detail': 'Für diese E-Mail-Adresse wurde noch kein Portalzugang angelegt.'}, status=403)
    SamlIdentity.objects.update_or_create(idp_entity_id=settings.SAML_IDP_ENTITY_ID, name_id=name_id or email, defaults={'user': user})
    refresh = RefreshToken.for_user(user)
    params = urlencode({'access': str(refresh.access_token), 'refresh': str(refresh), 'sso': 'saml'})
    separator = '&' if '?' in settings.APP_URL else '?'
    return HttpResponseRedirect(f'{settings.APP_URL}{separator}{params}')


@api_view(['GET'])
@permission_classes([AllowAny])
def saml_logout(request):
    if not _enabled():
        return HttpResponseRedirect(settings.APP_URL)
    return HttpResponseRedirect(_auth(request).logout(return_to=settings.APP_URL))
