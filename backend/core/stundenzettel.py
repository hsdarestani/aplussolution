"""Weekly planned-shift export using the original emailed A+ Stundenzettel form."""
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone as dt_timezone
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo
import re

from django.http import HttpResponse, JsonResponse
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from rest_framework.decorators import api_view

from .models import Shift
from .schedule_reports import _shift_groups, _manager_required
from .shift_slots import ShiftSlot

BERLIN = ZoneInfo('Europe/Berlin')
GROUPS = {'housekeeping': ('HK', 'HOUSEKEEPING'), 'front_office': ('FO', 'FRONT OFFICE')}
TEMPLATE = Path(__file__).parent / 'assets' / 'stundenzettel-blank.pdf'
# Original form's field positions; 15 rows, with the last available row for totals.
COLUMNS = [(67.01, 68.46), (141.71, 107.30), (255.25, 107.30),
           (368.79, 62.48), (437.51, 62.48), (506.23, 77.42), (589.89, 214.86)]
FIELDS = ['datum', 'vorname', 'nachname', 'start', 'ende', 'stunden', 'bestaetigung']


def parse_week(value):
    if not re.fullmatch(r'\d{4}-W\d{2}', value or ''):
        raise ValueError('Bitte eine gültige Kalenderwoche wählen (JJJJ-Www).')
    return date.fromisocalendar(int(value[:4]), int(value[6:]), 1)


def decimal_hours(minutes):
    return format((Decimal(minutes) / 60).quantize(Decimal('0.01')), 'f').rstrip('0').rstrip('.') or '0'


def weekly_rows(monday, group):
    start = datetime.combine(monday, time.min, BERLIN)
    end = datetime.combine(monday + timedelta(days=7), time.min, BERLIN)
    # The Dienstplan is authoritative: attendance/approval must never filter,
    # override, or duplicate scheduled rows in this export.
    shifts = Shift.objects.filter(starts_at__gte=start, starts_at__lt=end).exclude(
        status=Shift.Status.CANCELLED,
    ).select_related('worker__user', 'position', 'location', 'client').prefetch_related(
        'slots__worker__user',
    ).order_by('starts_at', 'client__name', 'location__name', 'id')
    hotels = defaultdict(list)
    for shift in shifts:
        if group not in _shift_groups(shift) or shift.ends_at <= shift.starts_at:
            continue
        all_slots = list(shift.slots.all())
        active_slots = [slot for slot in all_slots if slot.status != ShiftSlot.Status.CANCELLED]
        if all_slots:
            # Slot cards are the same authoritative assignments used by Dienstplan.
            # Do not resurrect a released/cancelled worker from the legacy mirror.
            assignments = [(slot.worker, str(slot.pk)) for slot in active_slots]
        else:
            # Historical direct assignment without slot rows.
            assignments = [(shift.worker, '')]
            assignments += [(None, '')] * max(0, int(shift.required_count or 1) - 1)
        first = shift.starts_at.astimezone(BERLIN)
        last = shift.ends_at.astimezone(BERLIN)
        gross = int((shift.ends_at.astimezone(dt_timezone.utc) - shift.starts_at.astimezone(dt_timezone.utc)).total_seconds() // 60)
        minutes = max(0, gross - max(0, int(shift.break_minutes or 0)))
        key = (str(shift.client_id), str(shift.location_id), shift.location.name)
        for worker, slot_id in assignments:
            hotels[key].append({
                'datum': first.strftime('%d.%m.%Y'),
                'vorname': worker.user.first_name if worker else 'OpenShift',
                'nachname': worker.user.last_name if worker else '',
                'start': first.strftime('%H:%M'), 'ende': last.strftime('%H:%M'),
                'stunden': decimal_hours(minutes), 'bestaetigung': 'bestätigt',
                'minutes': minutes, 'shift_id': str(shift.pk), 'slot_id': slot_id,
                'worker_id': str(worker.pk) if worker else '',
            })
    return hotels


def render_pdf(monday, group, hotels):
    output = BytesIO()
    c = canvas.Canvas(output, pagesize=(841.8898, 595.2756))
    c.setTitle(f'Stundenzettel - {GROUPS[group][0]} - KW{monday.isocalendar().week:02}')
    c.setAuthor('A+ Solution GmbH')
    page_number = 0
    for key, rows in sorted(hotels.items(), key=lambda item: (item[0][2].casefold(), item[0][:2])):
        for offset in range(0, len(rows), 14):
            page_number += 1
            c.setFont('Helvetica-Bold', 10)
            c.setFillColorRGB(.72, .54, .08)
            c.drawString(167.24, 519, GROUPS[group][1])
            c.setFillColorRGB(0, 0, 0)
            c.setFont('Helvetica', 8)
            hotel_size = 8
            while c.stringWidth(key[2], 'Helvetica', hotel_size) > 285 and hotel_size > 5:
                hotel_size -= .25
            c.setFont('Helvetica', hotel_size)
            c.drawString(85, 446, key[2])
            c.setFont('Helvetica', 8)
            chunk = rows[offset:offset + 14]
            for index, row in enumerate(chunk):
                for field, (x, width) in zip(FIELDS, COLUMNS):
                    value = str(row[field])
                    # Shrink long names to fit rather than clip or abbreviate them.
                    size = 8
                    while c.stringWidth(value, 'Helvetica', size) > width - 3 and size > 5:
                        size -= .25
                    c.acroForm.textfield(name=f'p{page_number}_{field}_{index+1:02}',
                        value=value, x=x, y=381.3543 - 24 * index, width=width, height=18.33,
                        fontName='Helvetica', fontSize=size, borderWidth=0,
                        fillColor=colors.white, textColor=colors.black, forceBorder=False)
            # Preserve the emailed form: only the numeric sum, without a caption.
            y = 381.3543 - 24 * len(chunk)
            c.setFont('Helvetica', 8)
            c.drawString(506.23, y + 6, decimal_hours(sum(row['minutes'] for row in chunk)))
            c.showPage()
    c.save()
    writer = PdfWriter()
    writer.clone_document_from_reader(PdfReader(output))
    background = PdfReader(TEMPLATE).pages[0]
    for page in writer.pages:
        page.merge_page(background, over=False)
    result = BytesIO()
    writer.write(result)
    return result.getvalue()


@api_view(['GET'])
def export_stundenzettel(request):
    if not _manager_required(request):
        return JsonResponse({'detail': 'Keine Berechtigung.'}, status=403)
    try:
        monday = parse_week(str(request.query_params.get('week', '')))
    except ValueError:
        return JsonResponse({'detail': 'Bitte eine gültige Kalenderwoche wählen (JJJJ-Www).'}, status=400)
    group = request.query_params.get('group')
    if group not in GROUPS:
        return JsonResponse({'detail': 'Bitte Housekeeping oder Front Office wählen.'}, status=400)
    hotels = weekly_rows(monday, group)
    if not hotels:
        return JsonResponse({'detail': 'Keine geplanten Schichten für diesen Bereich in dieser Woche vorhanden.'}, status=404)
    response = HttpResponse(render_pdf(monday, group, hotels), content_type='application/pdf')
    iso = monday.isocalendar()
    response['Content-Disposition'] = f'attachment; filename="Stundenzettel - {GROUPS[group][0]} - KW{iso.week:02} - {iso.year}.pdf"'
    response['Cache-Control'] = 'private, no-store'
    return response
