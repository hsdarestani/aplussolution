from datetime import date, datetime, timedelta
from decimal import Decimal

from django.db.models import Q
from django.http import HttpResponse
from django.core.files.base import ContentFile
from django.shortcuts import get_object_or_404
from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.response import Response
from rest_framework.parsers import FormParser, MultiPartParser

from .document_engine import convert_docx_to_pdf
from .models import AuevExport, AuevSetting, ClientCompany, PayrollStatement, ShiftImportPackage, TimeEntry, WorkingTimeAccountRecord, WorkingTimeSetting, WorkerProfile
from .order_automation import parse_order_text
from .auev_builder import (
    delete_export as delete_auev_export,
    export_dict as auev_export_dict,
    generate_export as generate_auev_export,
    preview as preview_auev,
    update_export as update_auev_export,
)
from .native_cutover import (
    approve_order,
    generate_client_contract,
    sync_packages_from_local_shifts,
    sync_working_time,
)
from .permissions import IsAdminOrManager
from .services import audit
from .working_time import (
    absence_summary_map,
    create_backup,
    dec,
    export_csv,
    export_xlsx,
    record_dict,
    settings_rows,
    update_record,
    worker_pdf,
    worker_docx,
    lexware_reconciliation_docx,
    payroll_audit_docx,
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
        'source_system': (item.payload or {}).get('source_system') or '',
        'contract_id': str(item.contract_id) if item.contract_id else None,
        'contract_status': item.contract.status if item.contract_id else '',
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
    queryset = (
        ShiftImportPackage.objects
        .select_related('client', 'contract')
        .exclude(status=ShiftImportPackage.Status.PLACE)
        .filter(payload__source_system='aplus')
        .order_by('-first_shift_time', '-created_at')
    )
    status_filter = request.query_params.get('status')
    if status_filter:
        queryset = queryset.filter(status=status_filter)
    return Response({'count': queryset.count(), 'results': [_package_dict(item) for item in queryset[:250]]})


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def order_generate(request, pk):
    package = get_object_or_404(ShiftImportPackage.objects.select_related('client', 'contract'), pk=pk)
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


def _auev_setting_dict(item):
    if not item:
        return {
            'permit_date': '',
            'framework_date': '',
            'effective_date': '',
            'required_qualification': '',
            'intended_activity': '',
            'client_contract_text': '',
            'file_label': '',
            'last_sequence_number': 0,
        }
    return {
        'permit_date': item.permit_date.isoformat() if item.permit_date else '',
        'framework_date': item.framework_date.isoformat() if item.framework_date else '',
        'effective_date': item.effective_date.isoformat() if item.effective_date else '',
        'required_qualification': item.required_qualification or '',
        'intended_activity': item.intended_activity or '',
        'client_contract_text': item.client_contract_text or '',
        'file_label': item.file_label or '',
        'last_sequence_number': int(item.last_sequence_number or 0),
    }


def _auev_default_row():
    row = AuevSetting.objects.filter(client__isnull=True).order_by('created_at').first()
    if row:
        return row
    return AuevSetting.objects.create(
        permit_date=date(2024, 4, 15),
        framework_date=date(2024, 8, 26),
        required_qualification='Serviceerfahrung in der Gastronomie',
        intended_activity='Servicetätigkeiten – Eventcatering',
    )


@api_view(['GET', 'PATCH'])
@permission_classes([IsAdminOrManager])
def auev_settings(request):
    client_id = request.query_params.get('client_id') if request.method == 'GET' else request.data.get('client_id')
    defaults = _auev_default_row()
    client = get_object_or_404(ClientCompany, pk=client_id) if client_id else None

    if request.method == 'PATCH':
        target = defaults
        if client:
            target, _ = AuevSetting.objects.get_or_create(client=client)
        for field in ('permit_date', 'framework_date', 'effective_date'):
            if field in request.data:
                raw = str(request.data.get(field) or '').strip()
                if raw:
                    parsed = parse_date(raw)
                    if not parsed:
                        return Response({'detail': f'Ungültiges Datum für {field}.'}, status=400)
                    setattr(target, field, parsed)
                else:
                    setattr(target, field, None)
        for field in ('required_qualification', 'intended_activity', 'client_contract_text', 'file_label'):
            if field in request.data:
                setattr(target, field, str(request.data.get(field) or '').strip())
        if 'last_sequence_number' in request.data and client:
            try:
                target.last_sequence_number = max(0, int(request.data.get('last_sequence_number') or 0))
            except (TypeError, ValueError):
                return Response({'detail': 'Ungültige ANÜ Nummer.'}, status=400)
        target.save()
        audit(
            request,
            'auev.settings_updated',
            target,
            {'scope': str(client.id) if client else 'global'},
        )

    override = AuevSetting.objects.filter(client=client).first() if client else defaults
    override_values = _auev_setting_dict(override)
    default_values = _auev_setting_dict(defaults)
    effective = {}
    for field in default_values:
        effective[field] = override_values.get(field) or default_values.get(field) or ''

    return Response({
        'client_id': str(client.id) if client else None,
        'client_name': client.name if client else 'Standard für alle Kunden',
        'defaults': default_values,
        'overrides': override_values,
        'effective': effective,
    })


@api_view(['GET'])
@permission_classes([IsAdminOrManager])
def auev_builder_preview(request):
    client = get_object_or_404(ClientCompany, pk=request.query_params.get('client_id'))
    try:
        start = _date(request.query_params.get('start'), timezone.localdate())
        end = _date(request.query_params.get('end'), start)
        if end < start:
            raise ValueError('Bis Datum darf nicht vor Von Datum liegen.')
        return Response(preview_auev(client, start, end))
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=400)


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def auev_builder_generate(request):
    client = get_object_or_404(ClientCompany, pk=request.data.get('client_id'))
    try:
        start = _date(request.data.get('start'), timezone.localdate())
        end = _date(request.data.get('end'), start)
        if end < start:
            raise ValueError('Bis Datum darf nicht vor Von Datum liegen.')
        signature_date = _date(request.data.get('signature_date'), start - timedelta(days=2))
        sequence = request.data.get('sequence_number')
        export = generate_auev_export(
            client=client,
            start=start,
            end=end,
            template_key=str(request.data.get('template_key') or AuevExport.Template.CLASSIC),
            signature_date=signature_date,
            actor=request.user,
            sequence_number=int(sequence) if str(sequence or '').strip() else None,
        )
        audit(
            request,
            'auev.export_generated',
            export,
            {
                'client': str(client.id),
                'template': export.template_key,
                'sequence_number': export.sequence_number,
                'weeks': export.calendar_weeks,
            },
        )
        return Response(auev_export_dict(export), status=201)
    except (TypeError, ValueError) as exc:
        return Response({'detail': str(exc)}, status=400)


@api_view(['GET'])
@permission_classes([IsAdminOrManager])
def auev_exports(request):
    queryset = AuevExport.objects.select_related('client').order_by('-created_at')
    client_id = request.query_params.get('client_id')
    if client_id:
        queryset = queryset.filter(client_id=client_id)
    return Response({'count': queryset.count(), 'results': [auev_export_dict(item) for item in queryset[:150]]})


@api_view(['PATCH', 'DELETE'])
@permission_classes([IsAdminOrManager])
def auev_export_detail(request, pk):
    export = get_object_or_404(AuevExport.objects.select_related('client'), pk=pk)

    if request.method == 'DELETE':
        payload = {
            'client': str(export.client_id),
            'file_stem': export.file_stem,
            'sequence_number': export.sequence_number,
        }
        audit(request, 'auev.export_deleted', export, payload)
        delete_auev_export(export)
        return Response(status=204)

    client = get_object_or_404(ClientCompany, pk=request.data.get('client_id') or export.client_id)
    try:
        start = _date(request.data.get('start'), export.date_from)
        end = _date(request.data.get('end'), export.date_to)
        if end < start:
            raise ValueError('Bis Datum darf nicht vor Von Datum liegen.')
        signature_date = _date(request.data.get('signature_date'), export.signature_date)
        sequence = request.data.get('sequence_number')
        updated = update_auev_export(
            export=export,
            client=client,
            start=start,
            end=end,
            template_key=str(request.data.get('template_key') or export.template_key),
            signature_date=signature_date,
            actor=request.user,
            sequence_number=int(sequence) if str(sequence or '').strip() else export.sequence_number,
        )
        audit(
            request,
            'auev.export_updated',
            updated,
            {
                'client': str(updated.client_id),
                'template': updated.template_key,
                'sequence_number': updated.sequence_number,
                'weeks': updated.calendar_weeks,
            },
        )
        return Response(auev_export_dict(updated))
    except (TypeError, ValueError) as exc:
        return Response({'detail': str(exc)}, status=400)


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
@parser_classes([MultiPartParser, FormParser])
def auev_export_replace_docx(request, pk):
    export = get_object_or_404(AuevExport.objects.select_related('client'), pk=pk)
    uploaded = request.FILES.get('file')
    if not uploaded:
        return Response({'detail': 'Bitte eine DOCX Datei auswählen.'}, status=400)

    filename = str(uploaded.name or '').strip()
    if not filename.lower().endswith('.docx'):
        return Response({'detail': 'Es können nur DOCX Dateien hochgeladen werden.'}, status=400)
    if uploaded.size and uploaded.size > 15 * 1024 * 1024:
        return Response({'detail': 'Die DOCX Datei darf maximal 15 MB groß sein.'}, status=400)

    docx_bytes = uploaded.read()
    if not docx_bytes.startswith(b'PK'):
        return Response({'detail': 'Die hochgeladene Datei ist keine gültige DOCX Datei.'}, status=400)

    try:
        pdf_bytes = convert_docx_to_pdf(docx_bytes)
    except Exception:
        return Response(
            {'detail': 'Die DOCX Datei konnte nicht in PDF umgewandelt werden. Bitte die Datei prüfen und erneut versuchen.'},
            status=400,
        )

    old_docx = export.docx.name if export.docx else ''
    old_pdf = export.pdf.name if export.pdf else ''

    export.docx.save(f'{export.file_stem}.docx', ContentFile(docx_bytes), save=False)
    export.pdf.save(f'{export.file_stem}.pdf', ContentFile(pdf_bytes), save=False)
    export.save(update_fields=['docx', 'pdf', 'updated_at'])

    storage = export.docx.storage
    for old_name, new_name in ((old_docx, export.docx.name), (old_pdf, export.pdf.name)):
        if old_name and old_name != new_name:
            try:
                storage.delete(old_name)
            except Exception:
                pass

    audit(
        request,
        'auev.export_docx_replaced',
        export,
        {
            'file_stem': export.file_stem,
            'uploaded_name': filename,
        },
    )
    return Response(auev_export_dict(export))


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
        if 'night_surcharge_percent' in row:
            setting.night_surcharge_percent = max(Decimal('0'), dec(row.get('night_surcharge_percent')))
        if 'saturday_surcharge_percent' in row:
            setting.saturday_surcharge_percent = max(Decimal('0'), dec(row.get('saturday_surcharge_percent')))
        if 'sunday_surcharge_percent' in row:
            setting.sunday_surcharge_percent = max(Decimal('0'), dec(row.get('sunday_surcharge_percent')))
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


def _payroll_statement_map(rows):
    worker_ids = {row.worker_id for row in rows}
    periods = {row.year_month for row in rows}
    if not worker_ids or not periods:
        return {}
    queryset = PayrollStatement.objects.filter(worker_id__in=worker_ids, period__in=periods)
    return {(str(item.worker_id), item.period): item for item in queryset}


@api_view(['GET'])
@permission_classes([IsAdminOrManager])
def worktime_records(request):
    queryset = WorkingTimeAccountRecord.objects.select_related(
        'worker__user',
        'worker__master_data',
    ).order_by('-year_month', 'worker__user__last_name')
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
    statements = _payroll_statement_map(rows)
    absences = absence_summary_map(rows)
    return Response({
        'count': len(rows),
        'results': [
            record_dict(
                row,
                statements.get((str(row.worker_id), row.year_month)),
                absence_summary=absences.get((str(row.worker_id), row.year_month)),
            )
            for row in rows
        ],
    })


@api_view(['GET'])
@permission_classes([IsAdminOrManager])
def worktime_record_detail(request, pk):
    record = get_object_or_404(
        WorkingTimeAccountRecord.objects.select_related('worker__user', 'worker__master_data'),
        pk=pk,
    )
    statement = PayrollStatement.objects.filter(
        worker=record.worker,
        period=record.year_month,
    ).first()
    absences = absence_summary_map([record])
    return Response(record_dict(
        record,
        statement,
        include_entries=True,
        absence_summary=absences.get((str(record.worker_id), record.year_month)),
    ))


@api_view(['PATCH'])
@permission_classes([IsAdminOrManager])
def worktime_record_update(request, pk):
    record = get_object_or_404(
        WorkingTimeAccountRecord.objects.select_related('worker__user', 'worker__master_data'),
        pk=pk,
    )
    record = update_record(
        record,
        paid_total_hours=request.data.get('paid_total_hours'),
        paid_hours=request.data.get('paid_hours'),
        manual_adjustment=request.data.get('manual_adjustment'),
    )
    statement = PayrollStatement.objects.filter(
        worker=record.worker,
        period=record.year_month,
    ).first()
    audit(request, 'working_time.record_adjusted', record, {
        'paid_total_hours': str(record.paid_total_hours) if record.paid_total_hours is not None else None,
        'legacy_paid_hours': str(record.paid_hours),
        'manual_adjustment': str(record.manual_adjustment),
    })
    return Response(record_dict(record, statement))


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def worktime_rebuild_all(request):
    # Any closed attendance row establishes that an employee has a work month.
    # Approval controls whether its minutes count toward IST, not whether the
    # monthly account itself exists. Optional year scoping is used by the
    # payroll workspace so a 2026 review does not inherit experimental or
    # incomplete balances from older years.
    closed = TimeEntry.objects.filter(clock_out__isnull=False).order_by('clock_in')
    first = closed.first()
    if not first:
        return Response({'status': 'ok', 'records_count': 0, 'detail': 'Keine abgeschlossenen Arbeitszeiten vorhanden.'})

    requested_year = str(request.data.get('year') or '').strip()
    reset_carry = False
    if requested_year:
        try:
            year = int(requested_year)
            if year < 2000 or year > 2100:
                raise ValueError
        except ValueError:
            return Response({'detail': 'Jahr muss im Format JJJJ angegeben werden.'}, status=400)
        start = date(year, 1, 1)
        end = min(timezone.localdate(), date(year, 12, 31))
        reset_carry = True
    else:
        start = timezone.localtime(first.clock_in).date().replace(day=1)
        end = timezone.localdate()

    refresh_contract_terms = bool(request.data.get('refresh_contract_terms'))
    log = sync_working_time(
        start,
        end,
        include_inactive_workers=True,
        refresh_contract_terms=refresh_contract_terms,
        reset_carry=reset_carry,
    )
    audit(request, 'working_time.rebuilt_all', log, {
        'start': start.isoformat(),
        'end': end.isoformat(),
        'records': log.records_count,
        'refresh_contract_terms': refresh_contract_terms,
        'year': requested_year or None,
        'reset_carry': reset_carry,
    })
    return Response({
        'status': log.status,
        'message': log.message,
        'records_count': log.records_count,
        'start': start.isoformat(),
        'end': end.isoformat(),
        'year': requested_year or None,
        'metadata': log.metadata,
    })


@api_view(['GET'])
@permission_classes([IsAdminOrManager])
def worktime_export(request, file_format):
    queryset = WorkingTimeAccountRecord.objects.order_by('worker__employee_number', 'year_month')
    worker = request.query_params.get('worker')
    if worker:
        queryset = queryset.filter(worker_id=worker)
    year = str(request.query_params.get('year') or '').strip()
    month = str(request.query_params.get('month') or '').strip()
    if year:
        try:
            queryset = queryset.filter(year_month__year=int(year))
        except ValueError:
            return Response({'detail': 'Jahr muss im Format JJJJ angegeben werden.'}, status=400)
    if month:
        try:
            period = datetime.strptime(month[:7], '%Y-%m').date().replace(day=1)
        except ValueError:
            return Response({'detail': 'Monat muss im Format JJJJ-MM angegeben werden.'}, status=400)
        queryset = queryset.filter(year_month=period)
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
    year = str(request.query_params.get('year') or '').strip()
    if year:
        try:
            queryset = queryset.filter(year_month__year=int(year))
        except ValueError:
            return Response({'detail': 'Jahr muss im Format JJJJ angegeben werden.'}, status=400)
    response = HttpResponse(worker_pdf(worker, queryset), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="arbeitszeit-lohnkonto-{worker.employee_number}.pdf"'
    return response


@api_view(['GET'])
@permission_classes([IsAdminOrManager])
def worktime_docx(request, worker_id):
    worker = get_object_or_404(WorkerProfile.objects.select_related('user'), pk=worker_id)
    queryset = WorkingTimeAccountRecord.objects.filter(worker=worker).order_by('year_month')
    year = str(request.query_params.get('year') or '').strip()
    if year:
        try:
            queryset = queryset.filter(year_month__year=int(year))
        except ValueError:
            return Response({'detail': 'Jahr muss im Format JJJJ angegeben werden.'}, status=400)
    response = HttpResponse(
        worker_docx(worker, queryset),
        content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    )
    response['Content-Disposition'] = f'attachment; filename="01_Arbeitszeitnachweis_{worker.employee_number}.docx"'
    return response


@api_view(['GET'])
@permission_classes([IsAdminOrManager])
def worktime_lexware_docx(request):
    period_text = str(request.query_params.get('month') or '').strip()
    try:
        period = datetime.strptime(period_text, '%Y-%m').date().replace(day=1)
    except ValueError:
        return Response({'detail': 'Bitte einen Monat im Format JJJJ-MM auswählen.'}, status=400)
    queryset = WorkingTimeAccountRecord.objects.filter(year_month=period).order_by(
        'worker__user__last_name', 'worker__user__first_name'
    )
    worker_id = request.query_params.get('worker')
    if worker_id:
        queryset = queryset.filter(worker_id=worker_id)
    response = HttpResponse(
        lexware_reconciliation_docx(queryset, period),
        content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    )
    response['Content-Disposition'] = f'attachment; filename="03_Lexware_Abgleich_{period.strftime("%Y-%m")}.docx"'
    return response


@api_view(['GET'])
@permission_classes([IsAdminOrManager])
def worktime_audit_docx(request):
    raw_year = str(request.query_params.get('year') or timezone.localdate().year)
    try:
        year = int(raw_year)
        if year < 2000 or year > 2100:
            raise ValueError
    except ValueError:
        return Response({'detail': 'Jahr muss im Format JJJJ angegeben werden.'}, status=400)

    queryset = WorkingTimeAccountRecord.objects.filter(
        year_month__year=year,
    ).order_by('worker__user__last_name', 'worker__user__first_name', 'year_month')
    worker_id = request.query_params.get('worker')
    if worker_id:
        queryset = queryset.filter(worker_id=worker_id)

    from .payroll_views import lexware_readiness_payload
    readiness = lexware_readiness_payload(year)
    payload = payroll_audit_docx(queryset, year, readiness)
    response = HttpResponse(
        payload,
        content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    )
    suffix = f'_{worker_id}' if worker_id else ''
    response['Content-Disposition'] = f'attachment; filename="05_Pruefbericht_Arbeitszeit_Lexware_{year}{suffix}.docx"'
    return response


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def worktime_backup(request):
    result = create_backup('manual')
    audit(request, 'working_time.backup_created', request.user, result)
    return Response({'status': 'ok', **result})
