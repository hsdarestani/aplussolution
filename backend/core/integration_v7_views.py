import base64

from django.http import HttpResponse, HttpResponseRedirect
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from .integration_v7_models import (
    IntegrationApiKey,
    PayrollConnector,
    PayrollExportRun,
    SamlIdentityProvider,
    WebhookDelivery,
    WebhookSubscription,
)
from .integration_v7_service import (
    API_KEY_SCOPES,
    authenticate_api_key,
    create_api_key,
    deliver_webhook,
    emit_webhook_event,
    encrypt_secret,
    export_payroll,
    rotate_webhook_secret,
)
from .models import Shift, User, WorkerProfile
from .payroll_models import PayPeriod, WorkerTimesheet
from .saml_v7 import build_login_redirect, metadata_xml, resolve_user, validate_response
from .serializers import UserSerializer
from .services import audit
from .workplace_access import has_capability


def _manage(user):
    return user.role == User.Role.ADMIN or user.is_superuser or has_capability(user, 'workplace.manage')


def _require_manage(request):
    if not _manage(request.user):
        raise PermissionDenied('Premium-Integrationen dürfen nur durch berechtigte Administratoren verwaltet werden.')


def _require_payroll_export(request):
    if request.user.role == User.Role.ADMIN or request.user.is_superuser:
        return
    if not has_capability(request.user, 'payroll.export'):
        raise PermissionDenied('Keine Berechtigung für Payroll-Exporte.')


def _api_key_row(row):
    return {
        'id': str(row.id), 'name': row.name, 'prefix': row.prefix, 'scopes': row.scopes,
        'active': row.active, 'expires_at': row.expires_at, 'last_used_at': row.last_used_at,
        'revoked_at': row.revoked_at, 'created_at': row.created_at,
    }


def _webhook_row(row):
    return {
        'id': str(row.id), 'name': row.name, 'url': row.url, 'event_types': row.event_types,
        'active': row.active, 'timeout_seconds': row.timeout_seconds, 'max_attempts': row.max_attempts,
        'last_success_at': row.last_success_at, 'last_failure_at': row.last_failure_at,
    }


def _saml_row(row):
    return {
        'id': str(row.id), 'name': row.name, 'enabled': row.enabled, 'sp_entity_id': row.sp_entity_id,
        'idp_entity_id': row.idp_entity_id, 'sso_url': row.sso_url, 'x509_certificate': row.x509_certificate,
        'allowed_domains': row.allowed_domains, 'auto_provision': row.auto_provision, 'default_role': row.default_role,
        'updated_at': row.updated_at,
    }


def _payroll_row(row):
    return {
        'id': str(row.id), 'name': row.name, 'provider': row.provider, 'configuration': row.configuration,
        'active': row.active, 'has_credentials': bool(row.credentials_encrypted), 'last_export_at': row.last_export_at,
    }


def _external_key(request, scope):
    row = authenticate_api_key(request)
    if not row:
        raise AuthenticationFailed('Invalid or expired API key.')
    if scope not in (row.scopes or []):
        raise PermissionDenied(f'API key is missing scope: {scope}')
    return row


@api_view(['GET', 'POST'])
def api_keys(request):
    _require_manage(request)
    if request.method == 'GET':
        return Response({'scopes': sorted(API_KEY_SCOPES), 'results': [_api_key_row(x) for x in IntegrationApiKey.objects.all()]})
    name = str(request.data.get('name') or '').strip()
    scopes = request.data.get('scopes') or []
    if not name:
        raise ValidationError({'name': 'Name ist erforderlich.'})
    expires_at = request.data.get('expires_at')
    if expires_at:
        from django.utils.dateparse import parse_datetime
        expires_at = parse_datetime(expires_at)
        if not expires_at or expires_at <= timezone.now():
            raise ValidationError({'expires_at': 'Ablaufzeit muss in der Zukunft liegen.'})
    try:
        row, token = create_api_key(name=name, scopes=scopes, created_by=request.user, expires_at=expires_at)
    except ValueError as exc:
        raise ValidationError(str(exc))
    audit(request, 'integration.api_key_created', row)
    payload = _api_key_row(row)
    payload['token'] = token
    payload['token_notice'] = 'Dieser Schlüssel wird nur einmal angezeigt.'
    return Response(payload, status=201)


@api_view(['POST'])
def api_key_revoke(request, pk):
    _require_manage(request)
    row = IntegrationApiKey.objects.filter(pk=pk).first()
    if not row:
        return Response({'detail': 'API key not found.'}, status=404)
    row.active = False
    row.revoked_at = timezone.now()
    row.save(update_fields=['active', 'revoked_at', 'updated_at'])
    audit(request, 'integration.api_key_revoked', row)
    return Response(_api_key_row(row))


@api_view(['GET', 'POST'])
def webhook_subscriptions(request):
    _require_manage(request)
    if request.method == 'GET':
        return Response({'results': [_webhook_row(x) for x in WebhookSubscription.objects.all()]})
    name = str(request.data.get('name') or '').strip()
    url = str(request.data.get('url') or '').strip()
    event_types = request.data.get('event_types') or []
    if not name or not url:
        raise ValidationError('Name und URL sind erforderlich.')
    row = WebhookSubscription.objects.create(
        name=name,
        url=url,
        event_types=event_types,
        timeout_seconds=max(1, min(30, int(request.data.get('timeout_seconds') or 10))),
        max_attempts=max(1, min(10, int(request.data.get('max_attempts') or 6))),
        active=bool(request.data.get('active', True)),
        created_by=request.user,
        secret_encrypted=encrypt_secret({'secret': 'pending'}),
    )
    secret = rotate_webhook_secret(row)
    audit(request, 'integration.webhook_created', row)
    payload = _webhook_row(row)
    payload['secret'] = secret
    payload['secret_notice'] = 'Dieses Secret wird nur einmal angezeigt.'
    return Response(payload, status=201)


@api_view(['PATCH', 'DELETE'])
def webhook_subscription_detail(request, pk):
    _require_manage(request)
    row = WebhookSubscription.objects.filter(pk=pk).first()
    if not row:
        return Response({'detail': 'Webhook not found.'}, status=404)
    if request.method == 'DELETE':
        row.active = False
        row.save(update_fields=['active', 'updated_at'])
        audit(request, 'integration.webhook_disabled', row)
        return Response(status=204)
    for field in ['name', 'url', 'event_types', 'active', 'timeout_seconds', 'max_attempts']:
        if field in request.data:
            setattr(row, field, request.data[field])
    row.timeout_seconds = max(1, min(30, int(row.timeout_seconds)))
    row.max_attempts = max(1, min(10, int(row.max_attempts)))
    row.save()
    audit(request, 'integration.webhook_updated', row)
    return Response(_webhook_row(row))


@api_view(['POST'])
def webhook_rotate(request, pk):
    _require_manage(request)
    row = WebhookSubscription.objects.filter(pk=pk).first()
    if not row:
        return Response({'detail': 'Webhook not found.'}, status=404)
    secret = rotate_webhook_secret(row)
    audit(request, 'integration.webhook_secret_rotated', row)
    return Response({'id': str(row.id), 'secret': secret, 'secret_notice': 'Dieses Secret wird nur einmal angezeigt.'})


@api_view(['POST'])
def webhook_test(request, pk):
    _require_manage(request)
    row = WebhookSubscription.objects.filter(pk=pk, active=True).first()
    if not row:
        return Response({'detail': 'Active webhook not found.'}, status=404)
    import uuid
    event_id = uuid.uuid4()
    delivery = WebhookDelivery.objects.create(
        subscription=row, event_id=event_id, event_type='integration.test',
        payload={'event': 'integration.test', 'message': 'A+ Workforce webhook test'},
    )
    deliver_webhook(delivery)
    return Response({'delivery_id': str(delivery.id), 'status': delivery.status, 'attempts': delivery.attempts, 'http_status': delivery.last_http_status})


@api_view(['GET'])
def webhook_deliveries(request):
    _require_manage(request)
    rows = WebhookDelivery.objects.select_related('subscription').all()[:200]
    return Response({'results': [{
        'id': str(x.id), 'subscription': x.subscription.name, 'event_id': str(x.event_id), 'event_type': x.event_type,
        'status': x.status, 'attempts': x.attempts, 'last_http_status': x.last_http_status,
        'last_error': x.last_error, 'created_at': x.created_at, 'delivered_at': x.delivered_at,
    } for x in rows]})


@api_view(['GET', 'POST'])
def saml_providers(request):
    _require_manage(request)
    if request.method == 'GET':
        return Response({'results': [_saml_row(x) for x in SamlIdentityProvider.objects.all()]})
    role = request.data.get('default_role') or User.Role.WORKER
    if role == User.Role.ADMIN:
        raise ValidationError({'default_role': 'SAML darf keine Administratoren automatisch anlegen.'})
    row = SamlIdentityProvider.objects.create(
        name=request.data.get('name') or 'Company SSO',
        enabled=bool(request.data.get('enabled', False)),
        sp_entity_id=request.data.get('sp_entity_id') or '',
        idp_entity_id=request.data.get('idp_entity_id') or '',
        sso_url=request.data.get('sso_url') or '',
        x509_certificate=request.data.get('x509_certificate') or '',
        allowed_domains=request.data.get('allowed_domains') or [],
        auto_provision=bool(request.data.get('auto_provision', False)),
        default_role=role,
        updated_by=request.user,
    )
    if not row.idp_entity_id or not row.sso_url or not row.x509_certificate:
        row.delete()
        raise ValidationError('IdP Entity ID, SSO URL und X.509-Zertifikat sind erforderlich.')
    audit(request, 'integration.saml_created', row)
    return Response(_saml_row(row), status=201)


@api_view(['PATCH'])
def saml_provider_detail(request, pk):
    _require_manage(request)
    row = SamlIdentityProvider.objects.filter(pk=pk).first()
    if not row:
        return Response({'detail': 'SAML provider not found.'}, status=404)
    if request.data.get('default_role') == User.Role.ADMIN:
        raise ValidationError({'default_role': 'SAML darf keine Administratoren automatisch anlegen.'})
    fields = ['name', 'enabled', 'sp_entity_id', 'idp_entity_id', 'sso_url', 'x509_certificate', 'allowed_domains', 'auto_provision', 'default_role']
    for field in fields:
        if field in request.data:
            setattr(row, field, request.data[field])
    row.updated_by = request.user
    row.save()
    audit(request, 'integration.saml_updated', row)
    return Response(_saml_row(row))


@api_view(['GET'])
@permission_classes([AllowAny])
def saml_metadata(request):
    provider = SamlIdentityProvider.objects.filter(enabled=True).order_by('created_at').first()
    if not provider:
        return Response({'detail': 'SAML is not configured.'}, status=404)
    return HttpResponse(metadata_xml(provider, request), content_type='application/samlmetadata+xml')


@api_view(['GET'])
@permission_classes([AllowAny])
def saml_login(request, pk):
    provider = SamlIdentityProvider.objects.filter(pk=pk, enabled=True).first()
    if not provider:
        return Response({'detail': 'SAML provider not found.'}, status=404)
    target = request.GET.get('target') or '/'
    try:
        return HttpResponseRedirect(build_login_redirect(provider, request, target=target))
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=400)


@api_view(['POST'])
@permission_classes([AllowAny])
def saml_acs(request):
    saml_response = request.data.get('SAMLResponse')
    relay_state = request.data.get('RelayState')
    if not saml_response or not relay_state:
        return Response({'detail': 'SAMLResponse and RelayState are required.'}, status=400)
    from django.core import signing
    try:
        state = signing.loads(relay_state, salt='aplus-workforce-saml-v7', max_age=600)
        provider = SamlIdentityProvider.objects.get(pk=state.get('provider'), enabled=True)
        identity = validate_response(provider, request, saml_response, relay_state)
        user, created = resolve_user(provider, identity)
        refresh = RefreshToken.for_user(user)
        return Response({
            'access': str(refresh.access_token), 'refresh': str(refresh),
            'user': UserSerializer(user, context={'request': request}).data,
            'target': identity['target'], 'provisioned': created,
        })
    except Exception as exc:
        return Response({'detail': f'SAML authentication failed: {exc}'}, status=400)


@api_view(['GET', 'POST'])
def payroll_connectors(request):
    if request.method == 'GET':
        _require_payroll_export(request)
        return Response({'results': [_payroll_row(x) for x in PayrollConnector.objects.all()]})
    _require_manage(request)
    provider = request.data.get('provider')
    if provider not in PayrollConnector.Provider.values:
        raise ValidationError({'provider': 'Unsupported payroll provider.'})
    row = PayrollConnector.objects.create(
        name=request.data.get('name') or dict(PayrollConnector.Provider.choices)[provider],
        provider=provider,
        configuration=request.data.get('configuration') or {},
        credentials_encrypted=encrypt_secret(request.data.get('credentials') or {}),
        active=bool(request.data.get('active', True)),
        created_by=request.user,
    )
    audit(request, 'integration.payroll_connector_created', row)
    return Response(_payroll_row(row), status=201)


@api_view(['PATCH'])
def payroll_connector_detail(request, pk):
    _require_manage(request)
    row = PayrollConnector.objects.filter(pk=pk).first()
    if not row:
        return Response({'detail': 'Payroll connector not found.'}, status=404)
    for field in ['name', 'configuration', 'active']:
        if field in request.data:
            setattr(row, field, request.data[field])
    if 'credentials' in request.data:
        row.credentials_encrypted = encrypt_secret(request.data.get('credentials') or {})
    row.save()
    audit(request, 'integration.payroll_connector_updated', row)
    return Response(_payroll_row(row))


@api_view(['POST'])
def payroll_export(request, pk, period_id):
    _require_payroll_export(request)
    connector = PayrollConnector.objects.filter(pk=pk, active=True).first()
    period = PayPeriod.objects.filter(pk=period_id).first()
    if not connector or not period:
        return Response({'detail': 'Connector or pay period not found.'}, status=404)
    try:
        run, result = export_payroll(connector, period, request.user)
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=400)
    except Exception as exc:
        return Response({'detail': str(exc)}, status=502)
    audit(request, 'integration.payroll_exported', run)
    if result.get('mode') == 'download':
        content = base64.b64decode(result['content_b64'])
        response = HttpResponse(content, content_type=result['content_type'])
        response['Content-Disposition'] = f'attachment; filename="{result["filename"]}"'
        response['X-APlus-Export-Run'] = str(run.id)
        return response
    return Response({'run_id': str(run.id), **result})


@api_view(['GET'])
def payroll_export_runs(request):
    _require_payroll_export(request)
    rows = PayrollExportRun.objects.select_related('connector', 'pay_period').all()[:200]
    return Response({'results': [{
        'id': str(x.id), 'connector': x.connector.name, 'pay_period': x.pay_period.name,
        'status': x.status, 'record_count': x.record_count, 'checksum': x.checksum,
        'result': x.result, 'error': x.error, 'created_at': x.created_at, 'completed_at': x.completed_at,
    } for x in rows]})


@api_view(['GET'])
@permission_classes([AllowAny])
def external_workers(request):
    _external_key(request, 'workers.read')
    rows = WorkerProfile.objects.filter(active=True).select_related('user').order_by('employee_number')
    return Response({'results': [{
        'id': str(x.id), 'employee_number': x.employee_number, 'name': x.user.get_full_name() or x.user.email,
        'email': x.user.email, 'employment_type': x.employment_type, 'skills': x.skills,
    } for x in rows]})


@api_view(['GET'])
@permission_classes([AllowAny])
def external_shifts(request):
    _external_key(request, 'shifts.read')
    rows = Shift.objects.select_related('location', 'position', 'worker__user').order_by('-starts_at')[:500]
    return Response({'results': [{
        'id': str(x.id), 'starts_at': x.starts_at, 'ends_at': x.ends_at, 'status': x.status,
        'location': x.location.name, 'position': x.position.name,
        'worker_id': str(x.worker_id) if x.worker_id else None, 'is_open': x.is_open,
    } for x in rows]})


@api_view(['GET'])
@permission_classes([AllowAny])
def external_timesheets(request):
    _external_key(request, 'timesheets.read')
    rows = WorkerTimesheet.objects.filter(pay_period__status__in=[PayPeriod.Status.CLOSED, PayPeriod.Status.LOCKED]).select_related('pay_period', 'worker__user').order_by('-pay_period__starts_on')[:1000]
    return Response({'results': [{
        'id': str(x.id), 'pay_period_id': str(x.pay_period_id), 'employee_number': x.worker.employee_number,
        'employee_name': x.worker.user.get_full_name() or x.worker.user.email, 'status': x.status,
        'net_minutes': x.net_minutes, 'gross_minutes': x.gross_minutes,
    } for x in rows]})
