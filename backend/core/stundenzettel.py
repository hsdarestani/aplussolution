"""Weekly actual-hours export using the original emailed A+ Stundenzettel form."""
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone as dt_timezone
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo
import re

from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from rest_framework.decorators import api_view

from .models import TimeEntry, User
from .schedule_reports import _attendance_group, _manager_required

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
    # Assign an entire overnight entry to its Berlin start date, as in the email.
    entries = TimeEntry.objects.filter(
        Q(approved=True) | Q(wiw_time_id__isnull=False),
        clock_in__gte=start, clock_in__lt=end, clock_out__isnull=False,
    ).exclude(worker__user__email__iendswith='@sync.invalid').select_related(
        'worker__user', 'shift__position', 'shift__location', 'shift__client', 'approved_by',
    ).order_by('clock_in', 'worker__user__last_name', 'worker__user__first_name', 'id')
    hotels = defaultdict(list)
    for entry in entries:
        if _attendance_group(entry) != group or entry.clock_out <= entry.clock_in:
            continue
        shift = entry.shift
        location = shift.location if shift else None
        client = shift.client if shift else None
        # Group by IDs too: equal display names must not mix distinct hotels/clients.
        key = (str(client.pk) if client else '', str(location.pk) if location else '',
               location.name if location else (client.name if client else 'Ohne Hotelzuordnung'))
        first = entry.clock_in.astimezone(BERLIN)
        last = entry.clock_out.astimezone(BERLIN)
        gross = int((entry.clock_out.astimezone(dt_timezone.utc) - entry.clock_in.astimezone(dt_timezone.utc)).total_seconds() // 60)
        minutes = max(0, gross - entry.effective_break_minutes)
        # A+ admin approval and WIW import do not constitute hotel confirmation.
        confirmed = bool(entry.approved and entry.approved_by and entry.approved_by.role == User.Role.CLIENT)
        hotels[key].append({
            'datum': first.strftime('%d.%m.%Y'), 'vorname': entry.worker.user.first_name,
            'nachname': entry.worker.user.last_name, 'start': first.strftime('%H:%M'),
            'ende': last.strftime('%H:%M'), 'stunden': decimal_hours(minutes),
            'bestaetigung': 'bestätigt' if confirmed else '', 'minutes': minutes,
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
            c.drawRightString(807, 446, f'KW {monday.isocalendar().week:02}/{monday.isocalendar().year} | {monday:%d.%m.%Y} - {monday + timedelta(days=6):%d.%m.%Y}')
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
            # Label the sum explicitly; keep the original 15-row print form.
            y = 381.3543 - 24 * len(chunk)
            c.setFont('Helvetica-Bold', 8)
            c.drawString(368.79, y + 6, 'Summe Seite')
            c.drawString(506.23, y + 6, decimal_hours(sum(row['minutes'] for row in chunk)))
            c.setFont('Helvetica', 7)
            c.drawRightString(807, 460, f'Gesamt Hotel: {decimal_hours(sum(row["minutes"] for row in rows))} Std. | Seite {offset // 14 + 1}/{(len(rows) + 13) // 14}')
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
        return JsonResponse({'detail': 'Keine freigegebenen oder importierten Arbeitszeiten für diesen Bereich in dieser Woche vorhanden.'}, status=404)
    response = HttpResponse(render_pdf(monday, group, hotels), content_type='application/pdf')
    iso = monday.isocalendar()
    response['Content-Disposition'] = f'attachment; filename="Stundenzettel - {GROUPS[group][0]} - KW{iso.week:02} - {iso.year}.pdf"'
    response['Cache-Control'] = 'private, no-store'
    return response
