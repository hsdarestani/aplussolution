from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from io import BytesIO
from uuid import UUID
from xml.sax.saxutils import escape

from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_date
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
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
WEEKDAY_LABELS = ['MO', 'DI', 'MI', 'DO', 'FR', 'SA', 'SO']


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
        'locations': _uuid_list(request.query_params.get('locations', '')),
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
    if filters['locations']:
        qs = qs.filter(location_id__in=filters['locations'])

    selected_workers = {str(value) for value in filters['workers']}
    selected_groups = set(filters['groups'])
    result = []
    for shift in qs:
        groups = _shift_groups(shift)
        if selected_groups and not selected_groups.intersection(groups):
            continue

        workers = []
        seen = set()
        active_slots = [slot for slot in shift.slots.all() if slot.status != ShiftSlot.Status.CANCELLED]
        has_open_slot = any(slot.status == ShiftSlot.Status.OPEN and not slot.worker_id for slot in active_slots)
        for slot in active_slots:
            if not slot.worker_id:
                continue
            if str(slot.worker_id) in seen:
                continue
            seen.add(str(slot.worker_id))
            workers.append(slot.worker)
        if shift.worker_id and str(shift.worker_id) not in seen:
            workers.append(shift.worker)
            seen.add(str(shift.worker_id))

        # Historical/direct assignments can have fewer active slot rows than the
        # requested capacity. Treat the remaining capacity as OpenShift as well.
        has_open_capacity = has_open_slot or max(1, int(shift.required_count or 1)) > len(seen)

        if selected_workers and not selected_workers.intersection(seen):
            continue
        if selected_workers:
            workers = [worker for worker in workers if str(worker.pk) in selected_workers]

        worker_labels = [_worker_label(worker) for worker in workers]
        # "Alle Mitarbeiter" is represented by an empty worker filter. In that
        # mode the PDF must also contain open capacity, including partially
        # staffed shifts. With explicit employee filters OpenShift stays hidden.
        if not selected_workers and has_open_capacity:
            worker_labels.append('OpenShift')

        start = timezone.localtime(shift.starts_at)
        end = timezone.localtime(shift.ends_at)
        result.append({
            'date': start.date(),
            'time': f'{start:%H:%M}–{end:%H:%M}',
            'client': shift.client.name,
            'location': shift.location.name,
            'groups': ', '.join(GROUP_LABELS.get(group, group) for group in groups),
            'worker_labels': worker_labels,
            'pause_minutes': int(shift.break_minutes or 0),
        })
    return result


def _week_chunks(start: date, end: date):
    current = start
    while current <= end:
        chunk_end = min(end, current + timedelta(days=6))
        yield [current + timedelta(days=offset) for offset in range((chunk_end - current).days + 1)]
        current = chunk_end + timedelta(days=1)


def _cell_html(entries, *, show_client: bool, show_group: bool) -> str:
    if not entries:
        return ''

    blocks = []
    for entry in entries:
        lines = [f'<b>{escape(entry["time"])}</b>']
        if show_client:
            lines.append(escape(entry['client']))
        if entry['location']:
            lines.append(escape(entry['location']))
        if show_group and entry['groups']:
            lines.append(f'<font color="#667085">{escape(entry["groups"])}</font>')
        if entry['pause_minutes']:
            lines.append(f'<font color="#98A2B3">Pause {entry["pause_minutes"]} Min</font>')
        blocks.append('<br/>'.join(lines))
    return '<br/><br/>'.join(blocks)


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
        leftMargin=9 * mm,
        rightMargin=9 * mm,
        topMargin=8 * mm,
        bottomMargin=8 * mm,
        title='Dienstplan',
        author='A+ Solution GmbH',
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'ReportTitle',
        parent=styles['Heading1'],
        alignment=TA_CENTER,
        fontName='Helvetica-Bold',
        fontSize=14,
        leading=17,
        textColor=colors.HexColor('#1F2937'),
        spaceAfter=2,
    )
    meta_style = ParagraphStyle(
        'ReportMeta',
        parent=styles['Normal'],
        alignment=TA_CENTER,
        fontName='Helvetica',
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor('#667085'),
    )
    head_style = ParagraphStyle(
        'ReportHead',
        parent=styles['Normal'],
        alignment=TA_CENTER,
        fontName='Helvetica-Bold',
        fontSize=7.2,
        leading=9,
        textColor=colors.white,
    )
    name_style = ParagraphStyle(
        'ReportName',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=7.2,
        leading=9,
        textColor=colors.HexColor('#263238'),
    )
    cell_style = ParagraphStyle(
        'ReportCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=6.2,
        leading=7.5,
        textColor=colors.HexColor('#344054'),
    )
    empty_style = ParagraphStyle(
        'ReportEmpty',
        parent=styles['Normal'],
        alignment=TA_CENTER,
        fontName='Helvetica',
        fontSize=8,
        textColor=colors.HexColor('#98A2B3'),
    )

    client_names = list(
        ClientCompany.objects.filter(pk__in=filters['clients']).order_by('name').values_list('name', flat=True)
    )
    selected_workers = list(
        WorkerProfile.objects.filter(pk__in=filters['workers'])
        .select_related('user')
        .order_by('user__last_name', 'user__first_name')
    )
    selected_worker_names = [_worker_label(worker) for worker in selected_workers]
    group_names = [GROUP_LABELS.get(value, value) for value in filters['groups']]
    location_names = sorted({row['location'] for row in rows}) if filters['locations'] else []

    # A filtered customer or area belongs in the compact report heading instead
    # of being repeated in every shift cell. Worker names always live in the
    # fixed left column, matching the familiar weekly planning grid.
    show_client_in_cells = len(client_names) != 1
    show_group_in_cells = len(group_names) != 1

    all_worker_names = []
    seen_names = set()
    for name in selected_worker_names:
        if name not in seen_names:
            seen_names.add(name)
            all_worker_names.append(name)
    for row in rows:
        labels = row['worker_labels'] or ['OpenShift']
        for name in labels:
            if name not in seen_names:
                seen_names.add(name)
                all_worker_names.append(name)
    all_worker_names.sort(key=lambda value: (value == 'OpenShift', value.lower()))

    entries_by_name_and_day = defaultdict(list)
    for row in rows:
        labels = row['worker_labels'] or ['OpenShift']
        for name in labels:
            entries_by_name_and_day[(name, row['date'])].append(row)

    story = []
    chunks = list(_week_chunks(filters['start'], filters['end']))
    if not chunks:
        chunks = [[filters['start']]]

    for chunk_index, days in enumerate(chunks):
        range_label = f'{days[0]:%d.%m.%Y} – {days[-1]:%d.%m.%Y}' if len(days) > 1 else f'{days[0]:%d.%m.%Y}'
        story.append(Paragraph('Dienstplan', title_style))
        story.append(Paragraph(range_label, meta_style))

        heading_bits = []
        if client_names:
            heading_bits.append('Kunde: ' + ', '.join(client_names))
        if location_names:
            heading_bits.append('Standort: ' + ', '.join(location_names))
        if group_names:
            heading_bits.append('Bereich: ' + ', '.join(group_names))
        if heading_bits:
            story.append(Paragraph(escape(' · '.join(heading_bits)), meta_style))
        story.append(Spacer(1, 3.5 * mm))

        if not all_worker_names:
            story.append(Paragraph('Keine Schichten für diese Filter.', empty_style))
        else:
            header = [Paragraph('Name', head_style)]
            for day in days:
                weekday = WEEKDAY_LABELS[day.weekday()]
                header.append(Paragraph(f'{weekday}<br/>{day:%d.%m.}', head_style))

            table_data = [header]
            for name in all_worker_names:
                row_cells = [Paragraph(escape(name), name_style)]
                for day in days:
                    html = _cell_html(
                        entries_by_name_and_day.get((name, day), []),
                        show_client=show_client_in_cells,
                        show_group=show_group_in_cells,
                    )
                    row_cells.append(Paragraph(html, cell_style) if html else '')
                table_data.append(row_cells)

            available_width = landscape(A4)[0] - document.leftMargin - document.rightMargin
            name_width = 42 * mm
            day_width = (available_width - name_width) / max(1, len(days))
            table = Table(
                table_data,
                repeatRows=1,
                colWidths=[name_width] + [day_width] * len(days),
                hAlign='CENTER',
            )
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#242424')),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('GRID', (0, 0), (-1, -1), 0.45, colors.HexColor('#D0D5DD')),
                ('LEFTPADDING', (0, 0), (-1, -1), 4),
                ('RIGHTPADDING', (0, 0), (-1, -1), 4),
                ('TOPPADDING', (0, 0), (-1, -1), 5),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                ('BACKGROUND', (0, 1), (0, -1), colors.HexColor('#F8FAFC')),
                ('ROWBACKGROUNDS', (1, 1), (-1, -1), [colors.white, colors.HexColor('#FCFCFD')]),
            ]))
            story.append(table)

        if chunk_index < len(chunks) - 1:
            story.append(PageBreak())

    document.build(story)

    response = HttpResponse(output.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = (
        f'attachment; filename="dienstplan-{filters["start"]:%Y%m%d}-{filters["end"]:%Y%m%d}.pdf"'
    )
    return response
