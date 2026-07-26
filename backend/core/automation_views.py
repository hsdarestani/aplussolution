from datetime import datetime, timedelta
from decimal import Decimal

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .models import ShiftImportPackage, WorkingTimeAccountRecord, WorkingTimeSetting, WorkerProfile
from .order_automation import (
    approve_order,
    generate_client_contract,
    parse_order_text,
    sync_packages_from_local_shifts,
)
from .permissions import IsAdminOrManager
from .services import audit
from .working_time import (
    create_backup,
    dec,
    export_csv,
    export_xlsx,
    record_dict,
    settings_rows,
    sync_working_time,
    update_record,
    worker_pdf,
)


def _date(value, fallback):
    if not value:
        return fallback
    parsed = parse_date(str(value))
    if not parsed:
        raise ValueError('Datum muss im Format JJJJ-MM-TT angegeben werden.')
    return parsed


def _package_dict(item):
    return {
        'id': str(item.id),
        'request_id': item.request_id,
        'client_id': str(item.client_id) if item.client_id else None,
        'client_name': item.client.name if item.client_id else item.site_name,
        'site_name': item.site_name,
        'site_address': item.site_address,
        'first_shift_time': item.first_shift_time,
        'first_shift_end_time': item.first_shift_end_time,
        'status': item.status,
        'shift_count': len((item.payload or {}).get('shifts', [])),
        'payload': item.payload,
        'contract_id': str(item.contract_id) if item.contract_id else None,
        'pdf_url': item.pdf.url if item.pdf else '',
        'created_at': item.created_at,
        'updated_at': item.updated_at,
    }


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def order_parse(request):
    try:
        result = parse_order_text(request.data.get('text', ''))
    except Exception as exc:
        return Response({'detail': str(exc)}, status=400)
    audit(request, 'order_automation.parsed', request.user, {'request_id': result.get('request_id'), 'shift_count': len(result.get('shifts', []))})
    return Response(result)


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def order_approve(request):
    try:
        result = approve_order(
            request.data.get('parsed') or {},
            request.data.get('raw_text') or '',
            actor=request.user,
            client_id=request.data.get('client_id') or None,
        )
    except Exception as exc:
        return Response({'detail': str(exc)}, status=400)
    audit(request, 'order_automation.approved', request.user, result)
    return Response(result)


@api_view(['GET'])
@permission_classes([IsAdminOrManager])
def order_packages(request):
    queryset = ShiftImportPackage.objects.select_related('client', 'contract').exclude(status=ShiftImportPackage.Status.PLACE)
    status_filter = request.query_params.get('status')
    if status_filter:
        queryset = queryset.filter(status=status_filter)
    return Response({'count': queryset.count(), 'results': [_package_dict(item) for item in queryset[:250]]})


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def order_generate(request, pk):
    package = get_object_or_404(ShiftImportPackage.objects.select_related('client'), pk=pk)
    try:
        contract = generate_client_contract(package, actor=request.user)
    except Exception as exc:
        return Response({'detail': str(exc)}, status=400)
    audit(request, 'client_contract.generated', contract, {'package': str(package.id)})
    return Response({'status': 'ok', 'contract_id': str(contract.id), 'pdf_url': contract.pdf.url if contract.pdf else ''})


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def order_sync_packages(request):
    today = timezone.localdate()
    try:
        start = _date(request.data.get('start'), today.replace(day=1))
        end = _date(request.data.get('end'), today)
        result = sync_packages_from_local_shifts(start, end, actor=request.user)
    except Exception as exc:
        return Response({'detail': str(exc)}, status=400)
    return Response(result)


@api_view(['GET', 'POST'])
@permission_classes([IsAdminOrManager])
def worktime_settings(request):
    if request.method == 'GET':
        return Response({
            'default_monthly_limit': str(settings.WORKING_TIME_DEFAULT_MONTHLY_LIMIT),
            'default_hourly_rate': str(settings.WORKING_TIME_DEFAULT_HOURLY_RATE),
            'default_break_minutes': settings.WORKING_TIME_DEFAULT_BREAK_MINUTES,
            'employees': settings_rows(),
        })
    employees = request.data.get('employees') or []
    saved = 0
    for row in employees:
        worker = get_object_or_404(WorkerProfile, pk=row.get('worker_id'))
        setting, _ = WorkingTimeSetting.objects.get_or_create(worker=worker)
        setting.monthly_limit = max(Decimal('0'), dec(row.get('monthly_limit')))
        setting.hourly_rate = max(Decimal('0'), dec(row.get('hourly_rate')))
        setting.active = bool(row.get('active', True))
        setting.excluded = bool(row.get('excluded', False))
        setting.notes = str(row.get('notes') or '')
        setting.save()
        saved += 1
    audit(request, 'working_time.settings_saved', request.user, {'saved': saved})
    return Response({'status': 'ok', 'saved': saved, 'employees': settings_rows()})


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def worktime_sync(request):
    today = timezone.localdate()
    try:
        start = _date(request.data.get('start'), today.replace(month=1, day=1))
        end = _date(request.data.get('end'), today)
        log = sync_working_time(start, end)
    except Exception as exc:
        return Response({'detail': str(exc)}, status=400)
    audit(request, 'working_time.synced', log, {'records': log.records_count})
    return Response({'status': log.status, 'message': log.message, 'records_count': log.records_count, 'metadata': log.metadata})


@api_view(['GET'])
@permission_classes([IsAdminOrManager])
def worktime_records(request):
    queryset = WorkingTimeAccountRecord.objects.select_related('worker__user').order_by('-year_month', 'worker__user__last_name')
    worker = request.query_params.get('worker')
    if worker:
        queryset = queryset.filter(worker_id=worker)
    month_from = request.query_params.get('from')
    month_to = request.query_params.get('to')
    if month_from:
        queryset = queryset.filter(year_month__gte=datetime.strptime(month_from[:7], '%Y-%m').date())
    if month_to:
        queryset = queryset.filter(year_month__lt=(datetime.strptime(month_to[:7], '%Y-%m').date().replace(day=28) + timedelta(days=4)).replace(day=1))
    rows = list(queryset[:2000])
    return Response({'count': len(rows), 'results': [record_dict(row) for row in rows]})


@api_view(['PATCH'])
@permission_classes([IsAdminOrManager])
def worktime_record_update(request, pk):
    record = get_object_or_404(WorkingTimeAccountRecord, pk=pk)
    record = update_record(record, paid_hours=request.data.get('paid_hours'), manual_adjustment=request.data.get('manual_adjustment'))
    audit(request, 'working_time.record_adjusted', record, {'paid_hours': str(record.paid_hours), 'manual_adjustment': str(record.manual_adjustment)})
    return Response(record_dict(record))


@api_view(['GET'])
@permission_classes([IsAdminOrManager])
def worktime_export(request, file_format):
    queryset = WorkingTimeAccountRecord.objects.order_by('worker__employee_number', 'year_month')
    worker = request.query_params.get('worker')
    if worker:
        queryset = queryset.filter(worker_id=worker)
    if file_format == 'csv':
        return export_csv(queryset)
    if file_format == 'xlsx':
        return export_xlsx(queryset)
    return Response({'detail': 'Unbekanntes Exportformat.'}, status=400)


@api_view(['GET'])
@permission_classes([IsAdminOrManager])
def worktime_pdf(request, worker_id):
    worker = get_object_or_404(WorkerProfile.objects.select_related('user'), pk=worker_id)
    queryset = WorkingTimeAccountRecord.objects.filter(worker=worker).order_by('year_month')
    response = HttpResponse(worker_pdf(worker, queryset), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="arbeitszeitkonto-{worker.employee_number}.pdf"'
    return response


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def worktime_backup(request):
    result = create_backup('manual')
    audit(request, 'working_time.backup_created', request.user, result)
    return Response({'status': 'ok', **result})
