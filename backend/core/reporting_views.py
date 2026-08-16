from django.db.models import Q
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Location, Position, User, WorkerProfile
from .reporting_models import ReportDefinition, ReportRun, ReportSchedule
from .reporting_service import DEFAULT_COLUMNS, FIELD_CATALOG, _next_run, build_report, execute_definition, field_catalog
from .scheduling_models import ScheduleGroup
from .services import audit
from .workplace_access import has_capability, visible_locations, visible_schedule_groups, visible_workers


def _require(user, capability='reports.view'):
    if not has_capability(user, capability):
        raise PermissionDenied('Keine Berechtigung für Berichte.')


def _can_manage(user):
    return has_capability(user, 'reports.manage')


def _definitions(user):
    qs = ReportDefinition.objects.filter(active=True).select_related('created_by')
    if user.role == User.Role.ADMIN or user.is_superuser or _can_manage(user):
        return qs
    return qs.filter(Q(created_by=user) | Q(shared=True)).distinct()


def _definition_row(row):
    return {
        'id': str(row.id), 'name': row.name, 'data_source': row.data_source,
        'columns': row.columns, 'filters': row.filters, 'sort': row.sort,
        'group_by': row.group_by, 'aggregates': row.aggregates, 'shared': row.shared,
        'active': row.active, 'created_by': str(row.created_by_id),
        'created_by_name': row.created_by.get_full_name() or row.created_by.email,
        'last_run_at': row.last_run_at, 'created_at': row.created_at, 'updated_at': row.updated_at,
    }


def _schedule_row(row):
    return {
        'id': str(row.id), 'report': str(row.report_id), 'report_name': row.report.name,
        'frequency': row.frequency, 'file_format': row.file_format, 'recipients': row.recipients,
        'local_hour': row.local_hour, 'weekday': row.weekday, 'day_of_month': row.day_of_month,
        'timezone': row.timezone, 'active': row.active, 'next_run_at': row.next_run_at,
        'last_run_at': row.last_run_at, 'created_by': str(row.created_by_id),
    }


def _run_row(row):
    return {
        'id': str(row.id), 'report': str(row.report_id) if row.report_id else None,
        'report_name': row.report.name if row.report_id else '', 'trigger': row.trigger,
        'file_format': row.file_format, 'status': row.status, 'row_count': row.row_count,
        'checksum': row.checksum, 'filters_snapshot': row.filters_snapshot, 'error': row.error,
        'created_at': row.created_at, 'completed_at': row.completed_at,
    }


def _validate_definition(user, payload, instance=None):
    source = payload.get('data_source', getattr(instance, 'data_source', None))
    if source not in FIELD_CATALOG:
        raise ValidationError({'data_source': 'Unbekannte Datenquelle.'})
    allowed = {item['key'] for item in field_catalog(user, source)}
    columns = payload.get('columns', getattr(instance, 'columns', None)) or DEFAULT_COLUMNS[source]
    if not columns or any(item not in allowed for item in columns):
        raise ValidationError({'columns': 'Mindestens eine Spalte ist ungültig oder nicht freigegeben.'})
    group_by = payload.get('group_by', getattr(instance, 'group_by', [])) or []
    if any(item not in allowed for item in group_by):
        raise ValidationError({'group_by': 'Ungültige Gruppierung.'})
    aggregates = payload.get('aggregates', getattr(instance, 'aggregates', [])) or []
    valid_ops = {'count', 'sum', 'avg', 'min', 'max'}
    for item in aggregates:
        if item.get('field') not in allowed or item.get('op') not in valid_ops:
            raise ValidationError({'aggregates': 'Ungültige Aggregation.'})
    return source, columns, group_by, aggregates


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def report_catalog(request):
    _require(request.user)
    return Response({
        'sources': [{
            'key': source, 'label': dict(ReportDefinition.DataSource.choices)[source],
            'fields': field_catalog(request.user, source), 'default_columns': DEFAULT_COLUMNS[source],
        } for source in ReportDefinition.DataSource.values],
        'can_manage': _can_manage(request.user),
        'formats': [{'key': key, 'label': label} for key, label in ReportSchedule.FileFormat.choices],
        'frequencies': [{'key': key, 'label': label} for key, label in ReportSchedule.Frequency.choices],
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def report_options(request):
    _require(request.user)
    workers = visible_workers(request.user, WorkerProfile.objects.filter(active=True)).select_related('user').order_by('employee_number')
    locations = visible_locations(request.user, Location.objects.filter(active=True)).order_by('name')
    schedules = visible_schedule_groups(request.user, ScheduleGroup.objects.filter(active=True)).order_by('name')
    return Response({
        'workers': [{'id': str(x.id), 'name': x.user.get_full_name() or x.user.email, 'number': x.employee_number} for x in workers],
        'locations': [{'id': str(x.id), 'name': x.name} for x in locations],
        'positions': [{'id': str(x.id), 'name': x.name} for x in Position.objects.filter(active=True).order_by('name')],
        'schedules': [{'id': str(x.id), 'name': x.name} for x in schedules],
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def report_preview(request):
    _require(request.user)
    try:
        result = build_report(
            request.user, request.data.get('data_source'), request.data.get('columns'), request.data.get('filters'),
            request.data.get('sort'), request.data.get('group_by'), request.data.get('aggregates'), limit=200,
        )
        return Response(result)
    except (ValueError, PermissionError) as exc:
        return Response({'detail': str(exc)}, status=400 if isinstance(exc, ValueError) else 403)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def report_definitions(request):
    _require(request.user)
    if request.method == 'GET':
        return Response({'results': [_definition_row(row) for row in _definitions(request.user)]})
    source, columns, group_by, aggregates = _validate_definition(request.user, request.data)
    shared = bool(request.data.get('shared', False))
    if shared and not _can_manage(request.user):
        raise PermissionDenied('Nur Report-Manager dürfen Berichte teilen.')
    name = str(request.data.get('name') or '').strip()
    if not name:
        raise ValidationError({'name': 'Name ist erforderlich.'})
    row = ReportDefinition.objects.create(
        name=name, data_source=source, columns=columns, filters=request.data.get('filters') or {},
        sort=request.data.get('sort') or [], group_by=group_by, aggregates=aggregates,
        shared=shared, created_by=request.user,
    )
    audit(request, 'report.created', row)
    return Response(_definition_row(row), status=201)


@api_view(['PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
def report_definition_detail(request, pk):
    _require(request.user)
    row = ReportDefinition.objects.filter(pk=pk).select_related('created_by').first()
    if not row:
        return Response({'detail': 'Bericht nicht gefunden.'}, status=404)
    if row.created_by_id != request.user.id and not _can_manage(request.user):
        raise PermissionDenied('Dieser Bericht gehört einem anderen Benutzer.')
    if request.method == 'DELETE':
        audit(request, 'report.deleted', row)
        row.active = False
        row.save(update_fields=['active', 'updated_at'])
        return Response(status=204)
    source, columns, group_by, aggregates = _validate_definition(request.user, request.data, row)
    if 'shared' in request.data and bool(request.data['shared']) and not _can_manage(request.user):
        raise PermissionDenied('Nur Report-Manager dürfen Berichte teilen.')
    for field in ['name', 'filters', 'sort', 'shared', 'active']:
        if field in request.data:
            setattr(row, field, request.data[field])
    row.data_source = source
    row.columns = columns
    row.group_by = group_by
    row.aggregates = aggregates
    row.save()
    audit(request, 'report.updated', row)
    return Response(_definition_row(row))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def report_run(request, pk):
    _require(request.user)
    row = _definitions(request.user).filter(pk=pk).first()
    if not row:
        return Response({'detail': 'Bericht nicht gefunden.'}, status=404)
    file_format = request.data.get('file_format') or request.GET.get('format') or 'csv'
    if file_format not in ReportSchedule.FileFormat.values:
        return Response({'detail': 'Format muss csv oder xlsx sein.'}, status=400)
    try:
        run, data, content_type = execute_definition(row, request.user, file_format, request.data.get('filters') or {})
    except (ValueError, PermissionError) as exc:
        return Response({'detail': str(exc)}, status=400 if isinstance(exc, ValueError) else 403)
    audit(request, 'report.executed', row, {'run': str(run.id), 'rows': run.row_count, 'format': file_format})
    response = HttpResponse(data, content_type=content_type)
    response['Content-Disposition'] = f'attachment; filename="{row.name}.{file_format}"'
    response['X-APlus-Report-Run'] = str(run.id)
    response['X-APlus-Report-Rows'] = str(run.row_count)
    return response


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def report_schedules(request):
    _require(request.user)
    if request.method == 'GET':
        qs = ReportSchedule.objects.select_related('report', 'created_by')
        if not _can_manage(request.user):
            qs = qs.filter(created_by=request.user)
        return Response({'results': [_schedule_row(row) for row in qs]})
    _require(request.user, 'reports.manage')
    report = _definitions(request.user).filter(pk=request.data.get('report')).first()
    if not report:
        raise ValidationError({'report': 'Bericht nicht gefunden.'})
    recipients = [str(x).strip() for x in (request.data.get('recipients') or []) if str(x).strip()]
    if not recipients or any('@' not in item for item in recipients):
        raise ValidationError({'recipients': 'Mindestens eine gültige E-Mail-Adresse ist erforderlich.'})
    frequency = request.data.get('frequency')
    file_format = request.data.get('file_format') or ReportSchedule.FileFormat.CSV
    if frequency not in ReportSchedule.Frequency.values:
        raise ValidationError({'frequency': 'Ungültige Frequenz.'})
    if file_format not in ReportSchedule.FileFormat.values:
        raise ValidationError({'file_format': 'Ungültiges Format.'})
    row = ReportSchedule.objects.create(
        report=report, frequency=frequency, file_format=file_format, recipients=recipients,
        local_hour=min(max(int(request.data.get('local_hour', 8)), 0), 23),
        weekday=min(max(int(request.data.get('weekday', 0)), 0), 6),
        day_of_month=min(max(int(request.data.get('day_of_month', 1)), 1), 28),
        timezone=request.data.get('timezone') or 'Europe/Berlin', active=bool(request.data.get('active', True)),
        created_by=request.user,
    )
    row.next_run_at = _next_run(row, timezone.now() - timezone.timedelta(seconds=1))
    row.save(update_fields=['next_run_at', 'updated_at'])
    audit(request, 'report.schedule_created', row)
    return Response(_schedule_row(row), status=201)


@api_view(['PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
def report_schedule_detail(request, pk):
    _require(request.user, 'reports.manage')
    row = ReportSchedule.objects.filter(pk=pk).select_related('report').first()
    if not row:
        return Response({'detail': 'Zeitplan nicht gefunden.'}, status=404)
    if request.method == 'DELETE':
        audit(request, 'report.schedule_deleted', row)
        row.delete()
        return Response(status=204)
    for field in ['frequency', 'file_format', 'recipients', 'local_hour', 'weekday', 'day_of_month', 'timezone', 'active']:
        if field in request.data:
            setattr(row, field, request.data[field])
    if row.frequency not in ReportSchedule.Frequency.values or row.file_format not in ReportSchedule.FileFormat.values:
        raise ValidationError('Ungültige Frequenz oder Exportformat.')
    row.local_hour = min(max(int(row.local_hour), 0), 23)
    row.weekday = min(max(int(row.weekday), 0), 6)
    row.day_of_month = min(max(int(row.day_of_month), 1), 28)
    row.next_run_at = _next_run(row)
    row.save()
    audit(request, 'report.schedule_updated', row)
    return Response(_schedule_row(row))


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def report_runs(request):
    _require(request.user)
    qs = ReportRun.objects.select_related('report', 'requested_by')
    if not _can_manage(request.user):
        qs = qs.filter(Q(requested_by=request.user) | Q(report__created_by=request.user))
    return Response({'results': [_run_row(row) for row in qs[:200]]})
