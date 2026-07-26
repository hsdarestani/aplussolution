import hashlib
import json

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .document_catalog import DOCUMENT_CATALOG, WIW_SUPPORTED_MASTER_FIELDS, WIW_UNSUPPORTED_LEGAL_FIELDS
from .document_engine import import_template_bundle, seed_document_catalog
from .models import EmployeeMasterData, IntegrationSyncRun, User, WebhookEvent, WorkerProfile
from .permissions import IsAdminOrManager
from .serializers import EmployeeMasterDataSerializer, IntegrationSyncRunSerializer
from .services import audit
from .tasks import process_wiw_webhook, sync_when_i_work
from .wiw import WhenIWorkClient, WhenIWorkError, verify_webhook_signature
from .wiw_sync import calculate_completeness


def configured():
    return bool(settings.WIW_DEV_KEY and settings.WIW_EMAIL and settings.WIW_PASSWORD)


@api_view(['GET'])
@permission_classes([IsAdminOrManager])
def wiw_status(request):
    latest = IntegrationSyncRun.objects.filter(provider='wiw').order_by('-started_at').first()
    return Response({
        'configured': configured(),
        'user_id_configured': bool(settings.WIW_USER_ID),
        'webhook_secret_configured': bool(settings.WIW_WEBHOOK_SECRET),
        'sync_enabled': settings.WIW_SYNC_ENABLED,
        'latest_sync': IntegrationSyncRunSerializer(latest).data if latest else None,
        'supported_resources': list(WhenIWorkClient.RESOURCE_PATHS),
        'wiw_supported_employee_fields': sorted(WIW_SUPPORTED_MASTER_FIELDS),
        'not_available_from_wiw': sorted(WIW_UNSUPPORTED_LEGAL_FIELDS),
        'note': 'Steuer-, Bank-, Sozialversicherungs- und Signaturdaten sind nicht Bestandteil des normalen WIW-Benutzerprofils und müssen aus Personalakten, Mitarbeiterangaben oder einer weiteren Integration stammen.',
    })


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def wiw_discover(request):
    try:
        result = WhenIWorkClient().discover()
    except WhenIWorkError as exc:
        return Response({'detail': str(exc)}, status=400)
    audit(request, 'wiw.discovered', request.user, {'resources': list(result)})
    return Response(result)


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def wiw_sync(request):
    if not configured():
        return Response({'detail': 'WIW-Secrets fehlen.'}, status=400)
    mode = str(request.data.get('mode') or 'incremental')
    if mode not in {'incremental', 'full'}:
        return Response({'detail': 'Modus muss incremental oder full sein.'}, status=400)
    task = sync_when_i_work.delay(mode=mode, triggered_by_id=str(request.user.id))
    audit(request, 'wiw.sync_queued', request.user, {'mode': mode, 'task_id': task.id})
    return Response({'queued': True, 'task_id': task.id, 'mode': mode}, status=202)


@api_view(['GET', 'PATCH'])
def worker_master_data(request, pk):
    try:
        worker = WorkerProfile.objects.select_related('user').get(pk=pk)
    except WorkerProfile.DoesNotExist:
        return Response({'detail': 'Mitarbeiter wurde nicht gefunden.'}, status=404)
    if request.user.role not in {User.Role.ADMIN, User.Role.MANAGER} and worker.user_id != request.user.id:
        return Response({'detail': 'Keine Berechtigung.'}, status=403)
    master, _ = EmployeeMasterData.objects.get_or_create(worker=worker)
    if request.method == 'PATCH':
        incoming = request.data.get('data') if isinstance(request.data.get('data'), dict) else request.data
        data = dict(master.data or {})
        sources = dict(master.source_map or {})
        for key, value in incoming.items():
            if key in {'worker', 'completeness', 'missing_fields', 'verified_at', 'verified_by'}:
                continue
            data[key] = value
            sources[key] = 'employee' if request.user.role == User.Role.WORKER else 'administration'
        completeness, missing = calculate_completeness(data)
        master.data = data
        master.source_map = sources
        master.completeness = completeness
        master.missing_fields = missing
        master.verified_at = None
        master.verified_by = None
        master.save()
        audit(request, 'worker_master_data.updated', master, {'fields': sorted(incoming)})
    return Response(EmployeeMasterDataSerializer(master).data)


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def verify_worker_master_data(request, pk):
    try:
        master = EmployeeMasterData.objects.get(worker_id=pk)
    except EmployeeMasterData.DoesNotExist:
        return Response({'detail': 'Personalstammdaten wurden nicht gefunden.'}, status=404)
    master.verified_at = timezone.now()
    master.verified_by = request.user
    master.save(update_fields=['verified_at', 'verified_by', 'updated_at'])
    audit(request, 'worker_master_data.verified', master)
    return Response(EmployeeMasterDataSerializer(master).data)


@api_view(['GET'])
def document_catalog(request):
    seed_document_catalog()
    from .models import ContractTemplate
    templates = {item.slug: item for item in ContractTemplate.objects.all()}
    rows = []
    for item in DOCUMENT_CATALOG:
        template = templates.get(item['slug'])
        rows.append({
            'slug': item['slug'],
            'name': item['name'],
            'kind': item['kind'],
            'audience': item['audience'],
            'version': template.version if template else item['version'],
            'source_format': item['source_format'],
            'source_installed': bool(template and template.source_file),
            'source_checksum': template.source_checksum if template else '',
            'requires_signature': item['requires_signature'],
            'signature_roles': item.get('signature_roles', []),
            'fields': item.get('fields', []),
        })
    return Response({'count': len(rows), 'documents': rows, 'complete': all(row['source_installed'] for row in rows)})


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def seed_catalog(request):
    result = seed_document_catalog()
    audit(request, 'document_catalog.seeded', request.user, result)
    return Response(result)


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def import_bundle(request):
    upload = request.FILES.get('file')
    if not upload:
        return Response({'detail': 'ZIP-Vorlagenpaket fehlt.'}, status=400)
    if not upload.name.lower().endswith('.zip'):
        return Response({'detail': 'Nur ZIP-Vorlagenpakete werden unterstützt.'}, status=400)
    try:
        result = import_template_bundle(upload)
    except Exception as exc:
        return Response({'detail': str(exc)}, status=400)
    audit(request, 'document_catalog.bundle_imported', request.user, {'name': upload.name, **result})
    return Response(result)


@api_view(['POST'])
@permission_classes([AllowAny])
def wiw_webhook(request):
    raw = request.body
    signature = request.headers.get('X-WIW-Signature') or request.headers.get('X-Webhook-Signature') or request.headers.get('X-Signature') or ''
    valid = verify_webhook_signature(raw, signature)
    if settings.WIW_WEBHOOK_SECRET and not valid:
        return Response({'detail': 'Ungültige Webhook-Signatur.'}, status=403)
    try:
        payload = json.loads(raw.decode('utf-8')) if raw else {}
    except (ValueError, UnicodeDecodeError):
        return Response({'detail': 'Ungültiges JSON.'}, status=400)
    external_id = str(payload.get('id') or payload.get('event_id') or hashlib.sha256(raw).hexdigest())
    event_type = str(payload.get('event') or payload.get('type') or payload.get('action') or '')
    event, created = WebhookEvent.objects.get_or_create(
        provider='wiw',
        external_id=external_id,
        defaults={'event_type': event_type, 'payload': payload, 'signature_valid': valid or not bool(settings.WIW_WEBHOOK_SECRET)},
    )
    if created:
        process_wiw_webhook.delay(str(event.id))
    return Response({'accepted': True, 'duplicate': not created}, status=202)
