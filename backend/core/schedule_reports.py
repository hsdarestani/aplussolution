from __future__ import annotations

from datetime import datetime, time, timedelta
from io import BytesIO
from uuid import UUID

from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_date
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from rest_framework.decorators import api_view

from .models import ClientCompany, Shift, User, WorkerProfile
from .shift_rules import normalized_groups
from .shift_slots import ShiftSlot


ALLOWED_GROUPS = {'service', 'front_office', 'housekeeping'}
GROUP_LABELS = {
    'service': 'Service',
    'front_office': 'Front Office',
    'housekeeping': 'Housekeeping',
}


def _manager_required(request):
    return getattr(request.user, 'role', '') in {User.Role.ADMIN, User.Role.MANAGER}


def _uuid_list(raw: str) -> list[UUID]:
    values = []
    for value in str(raw or '').split(','):
        value = value.strip()
        if not value:
            continue
        try:
            values.append(UUID(value))
        except (TypeError, ValueError, AttributeError):
            continue
    return values


def _group_list(raw: str) -> list[str]:
    return [value for value in normalized_groups(str(raw or '').split(',')) if value in ALLOWED_GROUPS]


def _shift_groups(shift: Shift) -> list[str]:
    groups = normalized_groups(shift.schedule_groups or [])
    if groups:
        return groups
    label = str(getattr(shift.position, 'name', '') or '').lower().replace('-', ' ').replace('_', ' ')
    if 'house' in label or 'zimmer' in label:
        return ['housekeeping']
    if 'front' in label or 'rezeption' in label or 'reception' in label:
        return ['front_office']
    return ['service']


def _worker_label(worker: WorkerProfile) -> str:
    return worker.user.get_full_name() or worker.user.email or worker.employee_number


def _report_filters(request):
    today = timezone.localdate()
    start = parse_date(str(request.query_params.get('date_from') or '')) or today
    end = parse_date(str(request.query_params.get('date_to') or '')) or (start + timedelta(days=31))
    if end < start:
        start, end = end, start
    if (end - start).days > 366:
        end = start + timedelta(days=366)
    return {
        'start': start,
        'end': end,
        'workers': _uuid_list(request.query_params.get('workers', '')),
        'clients': _uuid_list(request.query_params.get('clients', '')),
        'groups': _group_list(request.query_params.get('groups', '')),
    }


def _report_rows(filters):
    start_dt = timezone.make_aware(
        datetime.combine(filters['start'], time.min),
        timezone.get_current_timezone(),
    )
    end_dt = timezone.make_aware(
        datetime.combine(filters['end'] + timedelta(days=1), time.min),
        timezone.get_current_timezone(),
    )
    qs = (
        Shift.objects.filter(starts_at__gte=start_dt, starts_at__lt=end_dt)
        .exclude(status=Shift.Status.CANCELLED)
        .select_related('client', 'location', 'position', 'worker__user')
        .prefetch_related('slots__worker__user')
        .order_by('starts_at', 'client__name', 'location__name')
    )
    if filters['clients']:
        qs = qs.filter(client_id__in=filters['clients'])

    selected_workers = {str(value) for value in filters['workers']}
    selected_groups = set(filters['groups'])
    result = []
    for shift in qs:
        groups = _shift_groups(shift)
        if selected_groups and not selected_groups.intersection(groups):
            continue
        workers = []
        seen = set()
        for slot in shift.slots.all():
            if slot.status == ShiftSlot.Status.CANCELLED or not slot.worker_id:
                continue
            if str(slot.worker_id) in seen:
                continue
            seen.add(str(slot.worker_id))
            workers.append(slot.worker)
        if shift.worker_id and str(shift.worker_id) not in seen:
            workers.append(shift.worker)
            seen.add(str(shift.worker_id))
        if selected_workers and not selected_workers.intersection(seen):
            continue
        start = timezone.localtime(shift.starts_at)
        end = timezone.localtime(shift.ends_at)
        result.append({
            'date': start.strftime('%d.%m.%Y'),
            'time': f'{start:%H:%M}–{end:%H:%M}',
            'client': shift.client.name,
            'location': shift.location.name,
            'groups': ', '.join(GROUP_LABELS.get(group, group) for group in groups),
            'workers': ', '.join(_worker_label(worker) for worker in workers) or 'OpenShift',
            'pause': f'{int(shift.break_minutes or 0)} Min',
        })
    return result


@api_view(['GET'])
def export_schedule_pdf(request):
    if not _manager_required(request):
        return JsonResponse({'detail': 'Keine Berechtigung.'}, status=403)

    filters = _report_filters(request)
    rows = _report_rows(filters)
    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=landscape(A4),
        leftMargin=10 * mm,
        rightMargin=10 * mm,
        topMargin=10 * mm,
        bottomMargin=10 * mm,
        title='Dienstplan',
        author='A+ Solution GmbH',
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'ReportTitle', parent=styles['Heading1'], alignment=TA_CENTER, fontName='Helvetica-Bold', fontSize=15, leading=18
    )
    meta_style = ParagraphStyle(
        'ReportMeta', parent=styles['Normal'], alignment=TA_CENTER, fontName='Helvetica', fontSize=8, textColor=colors.HexColor('#475467')
    )
    cell_style = ParagraphStyle('ReportCell', parent=styles['Normal'], fontName='Helvetica', fontSize=7, leading=9)
    head_style = ParagraphStyle('ReportHead', parent=cell_style, fontName='Helvetica-Bold', textColor=colors.white)

    client_names = list(ClientCompany.objects.filter(pk__in=filters['clients']).order_by('name').values_list('name', flat=True))
    worker_names = [
        _worker_label(worker)
        for worker in WorkerProfile.objects.filter(pk__in=filters['workers']).select_related('user').order_by('user__last_name', 'user__first_name')
    ]
    group_names = [GROUP_LABELS.get(value, value) for value in filters['groups']]
    meta = f"{filters['start']:%d.%m.%Y} – {filters['end']:%d.%m.%Y}"
    details = []
    if client_names:
        details.append('Kunden: ' + ', '.join(client_names))
    if worker_names:
        details.append('Mitarbeiter: ' + ', '.join(worker_names))
    if group_names:
        details.append('Bereiche: ' + ', '.join(group_names))

    story = [Paragraph('Dienstplan', title_style), Paragraph(meta, meta_style)]
    if details:
        story.append(Paragraph(' · '.join(details), meta_style))
    story.append(Spacer(1, 5 * mm))

    table_data = [[
        Paragraph('Datum', head_style),
        Paragraph('Zeit', head_style),
        Paragraph('Kunde', head_style),
        Paragraph('Einsatzort', head_style),
        Paragraph('Bereich', head_style),
        Paragraph('Mitarbeiter', head_style),
        Paragraph('Pause', head_style),
    ]]
    for row in rows:
        table_data.append([
            Paragraph(row['date'], cell_style),
            Paragraph(row['time'], cell_style),
            Paragraph(row['client'], cell_style),
            Paragraph(row['location'], cell_style),
            Paragraph(row['groups'], cell_style),
            Paragraph(row['workers'], cell_style),
            Paragraph(row['pause'], cell_style),
        ])
    if not rows:
        table_data.append(['', '', '', Paragraph('Keine Schichten für diese Filter.', cell_style), '', '', ''])

    table = Table(
        table_data,
        repeatRows=1,
        colWidths=[22 * mm, 27 * mm, 42 * mm, 48 * mm, 35 * mm, 74 * mm, 20 * mm],
        hAlign='CENTER',
    )
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#162A46')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('GRID', (0, 0), (-1, -1), 0.35, colors.HexColor('#D0D5DD')),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')]),
    ]))
    story.append(table)
    document.build(story)

    response = HttpResponse(output.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = (
        f'attachment; filename="dienstplan-{filters["start"]:%Y%m%d}-{filters["end"]:%Y%m%d}.pdf"'
    )
    return response
