# Run through manage.py shell in production; read-only and no personal data logs.
from io import BytesIO
from pypdf import PdfReader
from rest_framework.test import APIRequestFactory, force_authenticate
from core.models import User, TimeEntry
from core.stundenzettel import BERLIN, GROUPS, TEMPLATE, export_stundenzettel, _attendance_group
from django.urls import resolve
assert resolve('/api/reports/stundenzettel.pdf').func == export_stundenzettel
assert TEMPLATE.is_file()
assert not PdfReader(TEMPLATE).get_fields()
admin = User.objects.filter(role=User.Role.ADMIN, is_active=True).first()
assert admin is not None
factory = APIRequestFactory()
checked = set()
for entry in TimeEntry.objects.filter(clock_out__isnull=False).select_related('shift__position').order_by('-clock_in')[:3000]:
    group = _attendance_group(entry)
    if group not in GROUPS or group in checked:
        continue
    iso = entry.clock_in.astimezone(BERLIN).isocalendar()
    request = factory.get('/api/reports/stundenzettel.pdf', {'week': f'{iso.year}-W{iso.week:02}', 'group': group})
    force_authenticate(request, user=admin)
    response = export_stundenzettel(request)
    if response.status_code == 404:
        continue
    assert response.status_code == 200
    pdf = PdfReader(BytesIO(response.content))
    assert pdf.pages and pdf.get_fields()
    print('LIVE_STUNDENZETTEL_OK', group, 'pages', len(pdf.pages), 'fields', len(pdf.get_fields()))
    checked.add(group)
    if len(checked) == 2:
        break
assert checked == set(GROUPS), 'No completed, approved/imported production records found for both departments'
print('LIVE_STUNDENZETTEL_BOTH_DEPARTMENTS_VERIFIED')
