# Run through manage.py shell in production. Read-only; log counts/hours only.
from collections import Counter
from datetime import datetime, timedelta
from io import BytesIO
from pypdf import PdfReader
from rest_framework.test import APIRequestFactory, force_authenticate
from core.models import User, Shift
from core.mobile_schedule import mobile_schedule
from core.stundenzettel import BERLIN, GROUPS, TEMPLATE, export_stundenzettel, parse_week, decimal_hours, _shift_groups
from django.urls import resolve
assert resolve('/api/reports/stundenzettel.pdf').func == export_stundenzettel
assert TEMPLATE.is_file() and not PdfReader(TEMPLATE).get_fields()
admin = User.objects.filter(role=User.Role.ADMIN, is_active=True).first()
assert admin is not None
factory = APIRequestFactory()
week = '2026-W46'
monday = parse_week(week)
request = factory.get('/api/mobile/schedule/', {'date_from': str(monday), 'date_to': str(monday + timedelta(days=6))}, HTTP_HOST='app.aplus-solution.de', secure=True)
force_authenticate(request, user=admin)
schedule = mobile_schedule(request)
assert schedule.status_code == 200
models = {str(s.pk): s for s in Shift.objects.select_related('position').filter(pk__in=[s['id'] for s in schedule.data['shifts']])}
expected = {group: [] for group in GROUPS}
for raw in schedule.data['shifts']:
    model = models[str(raw['id'])]
    start = datetime.fromisoformat(str(raw['starts_at']).replace('Z', '+00:00')).astimezone(BERLIN)
    end = datetime.fromisoformat(str(raw['ends_at']).replace('Z', '+00:00')).astimezone(BERLIN)
    if model.status == Shift.Status.CANCELLED or not monday <= start.date() <= monday + timedelta(days=6):
        continue
    minutes = max(0, int((model.ends_at - model.starts_at).total_seconds() // 60))
    cards = raw['slot_cards']
    if not cards and not model.slots.exists():
        cards = [{}] * max(1, int(model.required_count or 1))
    for group in set(_shift_groups(model)).intersection(GROUPS):
        for card in cards:
            expected[group].append((start.strftime('%d.%m.%Y'), start.strftime('%H:%M'), end.strftime('%H:%M'), decimal_hours(minutes)))
for group in GROUPS:
    assert expected[group], f'No planned cards for {group} in the screenshot week'
    request = factory.get('/api/reports/stundenzettel.pdf', {'week': week, 'group': group})
    force_authenticate(request, user=admin)
    response = export_stundenzettel(request)
    assert response.status_code == 200, (group, response.status_code)
    pdf = PdfReader(BytesIO(response.content)); fields = pdf.get_fields()
    assert pdf.pages and fields
    actual = []
    for name, field in fields.items():
        if '_datum_' in name:
            prefix, index = name.split('_datum_')
            actual.append(tuple(fields[f'{prefix}_{field}_{index}']['/V'] for field in ['datum', 'start', 'ende', 'stunden']))
    assert Counter(actual) == Counter(expected[group]), (group, 'PDF rows differ from visible Dienstplan cards')
    for page_no, page in enumerate(pdf.pages, 1):
        ids = [name for name in fields if name.startswith(f'p{page_no}_stunden_')]
        from decimal import Decimal
        expected_page_sum = sum((Decimal(str(fields[name]['/V'])) for name in ids), Decimal('0'))
        assert Decimal(str(fields[f'p{page_no}_gesamt']['/V'])) == expected_page_sum
        assert fields[f'p{page_no}_hotel']['/V']
        assert fields[f'p{page_no}_bereich']['/V'] == GROUPS[group][1]
        text = page.extract_text()
        assert all(value not in text for value in ['Summe Seite', 'Gesamt Hotel', 'KW ', 'Seite 1/'])
        assert 'Bestätigung Hotel' in text and '(Unterschrift)' in text
    assert all(field['/V'] == 'bestätigt' for name, field in fields.items() if '_bestaetigung_' in name)
    from decimal import Decimal
    total = sum(Decimal(row[3]) for row in actual)
    print('LIVE_PLANNED_STUNDENZETTEL_MATCHES_DIENSTPLAN', group, 'week', week, 'rows', len(actual), 'hours', str(total), 'pages', len(pdf.pages))
print('LIVE_PLANNED_STUNDENZETTEL_BOTH_DEPARTMENTS_VERIFIED')
