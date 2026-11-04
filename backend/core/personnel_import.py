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


def _marked_options(pdf_bytes):
    """Read handwritten X marks only when one choice is unambiguous.

    Rectangles are anchored to Lexware's printed option labels, not to
    absolute screenshot pixels.  Unclear or changed layouts return None.
    """
    import fitz

    selected = {'salutation': None, 'insurance_type': None, 'has_children': None,
                'employment_types': [None, None]}
    with fitz.open(stream=pdf_bytes, filetype='pdf') as doc:
        if not doc.page_count:
            return selected
        page = doc[0]

        def candidate(label, low=None, high=None, index=0):
            found = page.search_for(label)
            found = [rect for rect in found if (low is None or rect.y0 >= low)
                     and (high is None or rect.y0 <= high)]
            return found[index] if index < len(found) else None

        def ink(rect):
            if rect is None:
                return 0
            area = fitz.Rect(rect.x0 - 19, rect.y0 - 6, rect.x0 - 0.7, rect.y1 + 3)
            image = page.get_pixmap(matrix=fitz.Matrix(3, 3), clip=area,
                                    colorspace=fitz.csGRAY, alpha=False)
            return sum(pixel < 110 for pixel in image.samples)

        def choose(options):
            if any(rect is None for _, rect in options):
                return None
            ranks = sorted(((label, ink(rect)) for label, rect in options),
                           key=lambda item: item[1], reverse=True)
            if len(ranks) < 2 or ranks[0][1] < 150 or ranks[0][1] < 2 * max(1, ranks[1][1]):
                return None
            return ranks[0][0]

        selected['salutation'] = choose([
            (name, candidate(name, 50, 150))
            for name in ('Herr', 'Frau', 'Divers', 'Unbestimmt')
        ])
        selected['insurance_type'] = choose([
            (name, candidate(name, 350, 500)) for name in ('gesetzlich', 'privat')
        ])
        selected['has_children'] = choose([
            (name, candidate(name, 490, 580)) for name in ('ja', 'nein')
        ])
        for i in (0, 1):
            selected['employment_types'][i] = choose([
                ('minijob', candidate('geringfügig (Minijob)', index=i)),
                ('sozialversicherungspflichtig',
                 candidate('sozialversicherungspflichtig', index=i)),
            ])
    return selected


def parse_personalfragebogen_fields(pdf_bytes):
    reader = PdfReader(BytesIO(pdf_bytes), strict=False)
    if reader.is_encrypted:
        raise ValueError('Verschlüsselte PDFs werden nicht unterstützt.')
    if len(reader.pages) != 1:
        raise ValueError('Nur einseitige Personalfragebogen werden unterstützt.')
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

    # Free-text numerical entries in Konfession may be codes or misplaced
    # values.  Never insert an unverified religion into a personnel record.
    if master.get('religion', '').isdigit():
        master.pop('religion')
        religion_needs_review = True
    else:
        religion_needs_review = False

    if {'street', 'postal_code', 'city'} <= master.keys():
        master['full_address'] = f"{master['street']}, {master['postal_code']} {master['city']}"

    try:
        marks = _marked_options(pdf_bytes)
    except Exception:
        marks = {'salutation': None, 'insurance_type': None,
                 'has_children': None, 'employment_types': [None, None]}
    if marks.get('salutation'):
        master['salutation'] = marks['salutation']
    if marks.get('insurance_type'):
        master['insurance_type'] = marks['insurance_type']
    if marks.get('has_children') in ('ja', 'nein'):
        master['has_children'] = marks['has_children'] == 'ja'
        if marks['has_children'] == 'nein':
            master['children_under_25'] = 0
    count_under_25 = values.get('Falls ja: Wie viele Kinder?', '').strip()
    if count_under_25.isdecimal():
        master['children_under_25'] = int(count_under_25)

    employers = []
    for i in (1, 2):
        name = values.get(f'Name des Unternehmens/Arbeitgebers der weiteren Tätigkeit {i}', '').strip()
        if name:
            employers.append({
                'employer_name': name,
                'start_date': values.get(f'Beginn der Beschäftigung {i}') or None,
                'gross_monthly_salary': values.get(f'Verdienst in Euro pro Monat {i}') or None,
                'employment_type': marks.get('employment_types', [None, None])[i - 1],
            })
    if employers:
        master['other_employments'] = employers

    signature = values.get('Ort, Datum 1. Seite', '').strip()
    if signature:
        master['signature_place_and_date_as_written'] = signature
        # This is a typed place/date, NOT an electronic signature.
        import re
        match = re.fullmatch(r'(.+?)\s+(?:der,?\s*|,\s*)(\d{2}\.\d{2}\.\d{2,4})', signature, flags=re.IGNORECASE)
        if match:
            master['signature_place'] = match.group(1).strip(' ,')


    phone = values.get('Telefonnummer', '').strip()
    profile = {'phone': phone} if phone else {}
    unresolved = [
        label for label, value in (
            ('Anrede', marks.get('salutation')),
            ('Versicherungsart', marks.get('insurance_type')),
            ('Kinder', marks.get('has_children')),
        ) if value is None
    ]
    if any(entry['employment_type'] is None for entry in employers):
        unresolved.append('weitere Beschäftigungsart')
    warnings = [
        'Markierungen im PDF automatisch erkannt. Bitte Kästchen im Original prüfen.'
    ]
    if unresolved:
        warnings.append('Nicht eindeutig lesbare Kästchen: ' + ', '.join(unresolved) + '.')

    email = values.get('E-Mail-Adresse', '').strip()
    if email and '@' not in email:
        warnings.append('Das E-Mail-Feld enthält keine gültige E-Mail-Adresse. Bestehende E-Mail bleibt unverändert.')
    elif email:
        # Never change a login identity as part of a personnel-document import.
        warnings.append('E-Mail im PDF erkannt. Die bestehende Login-E-Mail wird aus Sicherheitsgründen nicht geändert.')

    if religion_needs_review:
        warnings.append('Konfession enthält einen ungeklärten Zahlenwert und wurde vorsichtshalber nicht übernommen.')

    if employers and any(not item['start_date'] or not item['gross_monthly_salary'] or not item['employment_type'] for item in employers):
        warnings.append('Bei weiteren Beschäftigungen fehlen einzelne Angaben (Beginn, Bruttoverdienst oder Beschäftigungsart). Leere Felder bleiben offen.')

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
