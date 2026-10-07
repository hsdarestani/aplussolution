import hashlib
from difflib import SequenceMatcher
import json
import re
import unicodedata
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .document_catalog import DOCUMENT_CATALOG, WIW_SUPPORTED_MASTER_FIELDS, WIW_UNSUPPORTED_LEGAL_FIELDS
from .document_engine import import_template_bundle, seed_document_catalog
from .models import EmployeeMasterData, IntegrationSyncRun, PayrollStatement, User, WebhookEvent, WorkerProfile, WorkingTimeSetting
from .permissions import IsAdminOrManager
from .serializers import EmployeeMasterDataSerializer, IntegrationSyncRunSerializer
from .services import audit
from .tasks import process_wiw_webhook, sync_when_i_work
from .wiw import WhenIWorkClient, WhenIWorkError, verify_webhook_signature
from .wiw_sync import calculate_completeness


def configured():
    return bool(settings.WIW_DEV_KEY and settings.WIW_EMAIL and settings.WIW_PASSWORD)



def _lexware_name(value):
    normalized = unicodedata.normalize('NFKD', str(value or ''))
    normalized = ''.join(ch for ch in normalized if not unicodedata.combining(ch))
    return re.sub(r'[^a-z0-9]+', ' ', normalized.lower()).strip()


def _decimal_or_none(value):
    if value in (None, ''):
        return None
    text = str(value).strip().replace('€', '').replace(' ', '')
    if ',' in text:
        text = text.replace('.', '').replace(',', '.')
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def import_lexware_employee_master_data(request):
    """Merge manually exported Lexware employee master data into A+ securely.

    The payload is uploaded directly by an authenticated administrator so
    sensitive employee data never has to live in the source repository.
    """
    upload = request.FILES.get('file')
    if not upload:
        return Response({'detail': 'Bitte eine Lexware Stammdaten JSON Datei auswählen.'}, status=400)
    try:
        raw = upload.read().decode('utf-8-sig')
        payload = json.loads(raw)
    except Exception:
        return Response({'detail': 'Die Stammdaten Datei ist keine gültige JSON Datei.'}, status=400)

    employees = payload.get('employees') if isinstance(payload, dict) else None
    if not isinstance(employees, list):
        return Response({'detail': 'JSON muss eine employees Liste enthalten.'}, status=400)

    workers = list(WorkerProfile.objects.select_related('user').all())
    by_name = {}
    by_number = {}
    by_email = {}
    worker_name_keys = []
    for worker in workers:
        names = {
            worker.user.get_full_name(),
            f'{worker.user.first_name} {worker.user.last_name}',
            f'{worker.user.last_name} {worker.user.first_name}',
        }
        for name in names:
            key = _lexware_name(name)
            if key:
                by_name.setdefault(key, worker)
                worker_name_keys.append((key, worker))
        if worker.employee_number:
            by_number[str(worker.employee_number).strip().lower()] = worker
        if worker.user.email:
            by_email.setdefault(worker.user.email.strip().lower(), worker)

    imported = []
    unmatched = []
    warnings = []

    for item in employees:
        if not isinstance(item, dict):
            continue
        worker = None
        employee_number = str(item.get('employee_number') or '').strip().lower()
        data = dict(item.get('data') or {})
        if employee_number:
            worker = by_number.get(employee_number)
        if not worker:
            worker = by_name.get(_lexware_name(item.get('name')))
        if not worker:
            for candidate_email in (
                item.get('email'),
                data.get('email'),
                data.get('self_service_email'),
            ):
                email_key = str(candidate_email or '').strip().lower()
                if email_key and email_key in by_email:
                    worker = by_email[email_key]
                    break
        if not worker:
            wanted = _lexware_name(item.get('name'))
            if wanted:
                scored = []
                seen_worker_ids = set()
                for candidate_key, candidate_worker in worker_name_keys:
                    if candidate_worker.id in seen_worker_ids:
                        continue
                    score = SequenceMatcher(None, wanted, candidate_key).ratio()
                    scored.append((score, candidate_worker))
                    seen_worker_ids.add(candidate_worker.id)
                scored.sort(key=lambda row: row[0], reverse=True)
                if scored:
                    best_score, best_worker = scored[0]
                    second_score = scored[1][0] if len(scored) > 1 else 0
                    if best_score >= 0.90 and best_score - second_score >= 0.05:
                        worker = best_worker
        if not worker:
            unmatched.append(str(item.get('name') or item.get('employee_number') or 'Unbekannt'))
            continue

        # Reuse payroll evidence that was already imported before the master
        # data upload. This lets one final Stammdaten import also pick up
        # observed Lexware rates and surcharge percentages without requiring
        # the user to upload old payroll PDFs again.
        latest_payslip = None
        for statement in PayrollStatement.objects.filter(worker=worker).order_by('-period'):
            payslips = [
                row for row in (statement.raw_data or [])
                if isinstance(row, dict) and row.get('kind') == 'payslip'
            ]
            if payslips:
                latest_payslip = payslips[-1]
                break
        if latest_payslip:
            if data.get('compensation_type') in (None, ''):
                data['compensation_type'] = latest_payslip.get('compensation_type') or ''
            if data.get('hourly_rate') in (None, '') and latest_payslip.get('hourly_rate') not in (None, ''):
                data['hourly_rate'] = latest_payslip.get('hourly_rate')
            if data.get('monthly_salary') in (None, '') and latest_payslip.get('monthly_salary') not in (None, ''):
                data['monthly_salary'] = latest_payslip.get('monthly_salary')
            if data.get('lexware_personal_number') in (None, '') and latest_payslip.get('personal_number'):
                data['lexware_personal_number'] = latest_payslip.get('personal_number')
            for supplement in latest_payslip.get('supplements') or []:
                label = str(supplement.get('label') or '').lower()
                percent = supplement.get('percent')
                if percent in (None, ''):
                    continue
                if 'nacht' in label and data.get('night_surcharge_percent') in (None, ''):
                    data['night_surcharge_percent'] = percent
                elif 'samstag' in label and data.get('saturday_surcharge_percent') in (None, ''):
                    data['saturday_surcharge_percent'] = percent
                elif 'sonntag' in label and data.get('sunday_surcharge_percent') in (None, ''):
                    data['sunday_surcharge_percent'] = percent

        master, _ = EmployeeMasterData.objects.get_or_create(worker=worker)
        merged = dict(master.data or {})
        sources = dict(master.source_map or {})
        for key, value in data.items():
            if value in (None, ''):
                continue
            merged[key] = value
            sources[key] = 'lexware_stammdaten'
        completeness, missing = calculate_completeness(merged)
        master.data = merged
        master.source_map = sources
        master.completeness = completeness
        master.missing_fields = missing
        master.verified_at = None
        master.verified_by = None
        master.save()

        weekly_hours = _decimal_or_none(data.get('weekly_hours'))
        monthly_hours = _decimal_or_none(data.get('monthly_hours'))
        if monthly_hours is None and weekly_hours is not None:
            monthly_hours = (weekly_hours * Decimal('52') / Decimal('12')).quantize(Decimal('0.01'))

        hourly_rate = _decimal_or_none(data.get('hourly_rate'))
        app_employment_type = str(item.get('app_employment_type') or '').strip()
        allowed_types = {choice[0] for choice in WorkerProfile.EmploymentType.choices}
        update_fields = []
        if app_employment_type in allowed_types and worker.employment_type != app_employment_type:
            worker.employment_type = app_employment_type
            update_fields.append('employment_type')
        elif app_employment_type and app_employment_type not in allowed_types:
            warnings.append(f'{worker.user}: unbekannter A+ Beschäftigungstyp {app_employment_type}')
        if monthly_hours is not None:
            worker.monthly_hours = monthly_hours
            update_fields.append('monthly_hours')
        if hourly_rate is not None:
            worker.tariff_hourly_rate = hourly_rate
            update_fields.append('tariff_hourly_rate')
        if update_fields:
            worker.save(update_fields=list(dict.fromkeys(update_fields)))

        setting, _ = WorkingTimeSetting.objects.get_or_create(worker=worker)
        setting_fields = []
        if monthly_hours is not None:
            setting.monthly_limit = monthly_hours
            setting_fields.append('monthly_limit')
        if hourly_rate is not None:
            setting.hourly_rate = hourly_rate
            setting_fields.append('hourly_rate')
        for source_key, attr in (
            ('night_surcharge_percent', 'night_surcharge_percent'),
            ('saturday_surcharge_percent', 'saturday_surcharge_percent'),
            ('sunday_surcharge_percent', 'sunday_surcharge_percent'),
        ):
            value = _decimal_or_none(data.get(source_key))
            if value is not None:
                setattr(setting, attr, value)
                setting_fields.append(attr)
        if setting_fields:
            setting.save(update_fields=list(dict.fromkeys(setting_fields)))

        imported.append({
            'worker_id': str(worker.id),
            'employee_name': worker.user.get_full_name() or worker.user.email,
            'completeness': master.completeness,
            'monthly_hours': str(monthly_hours) if monthly_hours is not None else None,
            'hourly_rate': str(hourly_rate) if hourly_rate is not None else None,
        })

    audit(request, 'lexware.employee_master_data_imported', request.user, {
        'employees': len(imported),
        'unmatched': unmatched,
        'warnings': warnings,
        'filename': getattr(upload, 'name', ''),
    })
    return Response({
        'status': 'ok',
        'employees': imported,
        'unmatched': unmatched,
        'warnings': warnings,
    })


@api_view(['GET'])
@permission_classes([IsAdminOrManager])
def wiw_status(request):
    latest = IntegrationSyncRun.objects.filter(provider='wiw').order_by('-started_at').first()
    return Response({
        'configured': configured(),
        'user_id_configured': bool(settings.WIW_USER_ID),
        'webhook_secret_configured': bool(settings.WIW_WEBHOOK_SECRET),
        'sync_enabled': settings.WIW_SYNC_ENABLED,
        'operational_source': 'aplus',
        'migration_only': True,
        'latest_sync': IntegrationSyncRunSerializer(latest).data if latest else None,
        'supported_resources': list(WhenIWorkClient.RESOURCE_PATHS),
        'wiw_supported_employee_fields': sorted(WIW_SUPPORTED_MASTER_FIELDS),
        'not_available_from_wiw': sorted(WIW_UNSUPPORTED_LEGAL_FIELDS),
        'note': 'A+ Workforce ist die operative Datenquelle. WIW-Zugangsdaten werden nur noch für einen kontrollierten finalen Import/Audit aufbewahrt.',
    })


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def wiw_discover(request):
    if not settings.WIW_SYNC_ENABLED:
        return Response({'detail': 'WIW ist im normalen Betrieb deaktiviert. API-Prüfungen erfolgen nur im finalen Migrationslauf.'}, status=409)
    try:
        result = WhenIWorkClient().discover()
    except WhenIWorkError as exc:
        return Response({'detail': str(exc)}, status=400)
    audit(request, 'wiw.discovered', request.user, {'resources': list(result)})
    return Response(result)


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def wiw_sync(request):
    if not settings.WIW_SYNC_ENABLED:
        return Response({
            'detail': 'Die laufende WIW-Synchronisierung ist deaktiviert. Für den einmaligen Abschlussimport bitte migrate_wiw_final --apply --strict verwenden.'
        }, status=409)
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
    if not settings.WIW_SYNC_ENABLED:
        return Response({'accepted': False, 'ignored': True, 'detail': 'WIW-Synchronisierung ist deaktiviert; A+ Workforce ist die Datenquelle.'}, status=202)
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
