"""Safe, read-only preview of fillable Lexware Personalfragebogen PDFs.

No uploaded PDF is written to disk.  Only an already-authenticated admin
may preview fields for an existing worker.  Persisting remains an explicit
Akte PATCH, never a side effect of opening/importing a document.
"""
from datetime import datetime
from io import BytesIO

from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from pypdf import PdfReader

from .models import User, WorkerProfile


_FIELD_MAP = {
    'Straße und Hausnummer': 'street',
    'Postleitzahl': 'postal_code',
    'Ort': 'city',
    'Staatsangehörigkeit': 'nationality',
    'Geburtsname': 'birth_name',
    'Geburtsort': 'birth_place',
    'Geburtsland': 'birth_country',
    'Sozial-/Rentenversicherungsnummer': 'social_insurance_number',
    'Krankenkasse': 'health_insurance_name',
    'Steueridentifikationsnummer': 'tax_identification_number',
    'Steuerklasse/Faktor': 'tax_class',
    'Kinderfreibetrag': 'child_allowance',
    'Freibeträge': 'tax_allowance',
    'Konfession': 'religion',
    'Konfession des Ehepartners': 'spouse_religion',
    'IBAN': 'iban',
    'Kontoinhaber': 'bank_account_holder',
    'Name des Kreditinstitus': 'bank_name',
}


def parse_personalfragebogen_fields(pdf_bytes):
    reader = PdfReader(BytesIO(pdf_bytes), strict=False)
    if reader.is_encrypted:
        raise ValueError('Verschlüsselte PDFs werden nicht unterstützt.')
    fields = reader.get_fields() or {}
    if not fields:
        raise ValueError('Das PDF enthält keine auslesbaren Formularfelder.')
    values = {}
    for key, field in fields.items():
        value = field.get('/V')
        if value is None or isinstance(value, (list, dict)):
            continue
        value = str(value).strip()
        if value and value != '/':
            values[str(key)] = value

    first = values.get('Vorname', '').strip()
    last = values.get('Nachname', '').strip()
    if not first or not last:
        raise ValueError('Vorname und Nachname fehlen im PDF.')

    master = {}
    for source, target in _FIELD_MAP.items():
        value = values.get(source, '').strip()
        if value:
            master[target] = value

    birth = values.get('Geburtsdatum', '').strip()
    if birth:
        try:
            master['birth_date'] = datetime.strptime(birth, '%d.%m.%Y').date().isoformat()
        except ValueError:
            raise ValueError('Geburtsdatum hat ein ungültiges Format (TT.MM.JJJJ).')

    if {'street', 'postal_code', 'city'} <= master.keys():
        master['full_address'] = f"{master['street']}, {master['postal_code']} {master['city']}"

    employers = []
    for i in (1, 2):
        name = values.get(f'Name des Unternehmens/Arbeitgebers der weiteren Tätigkeit {i}', '').strip()
        if name:
            employers.append({
                'employer_name': name,
                'start_date': values.get(f'Beginn der Beschäftigung {i}') or None,
                'gross_monthly_salary': values.get(f'Verdienst in Euro pro Monat {i}') or None,
                'employment_type': None,  # Handwritten checkbox, not a PDF form value.
            })
    if employers:
        master['other_employments'] = employers

    signature = values.get('Ort, Datum 1. Seite', '')
    if signature:
        master['signature_place_and_date_as_written'] = signature

    phone = values.get('Telefonnummer', '').strip()
    profile = {'phone': phone} if phone else {}
    warnings = [
        'Handschriftlich markierte Kästchen (Anrede, gesetzlich/privat, Kinder, Minijob) können nicht zuverlässig automatisch gelesen werden. Bitte anhand des Originals prüfen.',
    ]

    email = values.get('E-Mail-Adresse', '').strip()
    if email and '@' not in email:
        warnings.append('Das E-Mail-Feld enthält keine gültige E-Mail-Adresse. Bestehende E-Mail bleibt unverändert.')
    elif email:
        # Never change a login identity as part of a personnel-document import.
        warnings.append('E-Mail im PDF erkannt. Die bestehende Login-E-Mail wird aus Sicherheitsgründen nicht geändert.')

    if master.get('religion', '').isdigit():
        warnings.append('Konfession enthält eine Zahl. Bitte die Angabe fachlich prüfen, nicht als bestätigte Konfession behandeln.')

    if employers:
        warnings.append('Beginn, Bruttoverdienst und Beschäftigungsart der weiteren Tätigkeiten bitte prüfen; leere Felder werden nicht erfunden.')

    return {'first_name': first, 'last_name': last, 'profile': profile,
            'master_data': master, 'warnings': warnings}


@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser])
def preview_personalfragebogen(request, pk):
    if not request.user.is_authenticated or request.user.role not in (User.Role.ADMIN, User.Role.MANAGER):
        return Response({'detail': 'Keine Berechtigung.'}, status=403)

    worker = get_object_or_404(WorkerProfile.objects.select_related('user'), pk=pk)
    uploaded = request.FILES.get('file')
    if not uploaded or not uploaded.name.lower().endswith('.pdf'):
        return Response({'detail': 'Bitte ein PDF hochladen.'}, status=400)
    if uploaded.size > 5 * 1024 * 1024:
        return Response({'detail': 'PDF ist größer als 5 MB.'}, status=400)

    try:
        incoming = parse_personalfragebogen_fields(uploaded.read())
    except Exception:
        # Avoid including parser internals or sensitive PDF contents in errors.
        return Response({'detail': 'PDF konnte nicht als ausfüllbarer Personalfragebogen gelesen werden.'}, status=400)

    def norm(text):
        return ' '.join(str(text or '').split()).casefold()

    if (norm(worker.user.first_name) != norm(incoming['first_name'])
            or norm(worker.user.last_name) != norm(incoming['last_name'])):
        return Response({'detail': 'Der Name im PDF stimmt nicht mit dieser bestehenden Mitarbeiterakte überein. Es wurde nichts geändert.'}, status=409)

    response = Response({
        'matched_worker': str(worker.pk),
        'profile': incoming['profile'],
        'master_data': incoming['master_data'],
        'warnings': incoming['warnings'],
    })
    response['Cache-Control'] = 'no-store'
    return response
