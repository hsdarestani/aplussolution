import io
import re
from decimal import Decimal

from pypdf import PdfReader


_MONEY = r'-?[0-9][0-9.]*,[0-9]{2}'


def _money(value: str | None) -> Decimal | None:
    text = str(value or '').replace('\xa0', '').replace('€', '').replace(' ', '').strip()
    if not text:
        return None
    if ',' in text:
        text = text.replace('.', '').replace(',', '.')
    try:
        return Decimal(text)
    except Exception:
        return None


def _pages(payload: bytes) -> list[str]:
    reader = PdfReader(io.BytesIO(payload))
    return [(page.extract_text() or '') for page in reader.pages]


def _employee_name_from_payslip(text: str) -> str:
    match = re.search(
        r'Abrechnung\s+für\s+.+?\s+\d{4}\s*-\s*(.+?)\s*\nerstellt\s+mit\s+Lexware',
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return ''
    return ' '.join(match.group(1).split())


_GERMAN_MONTHS = {
    'januar': '01',
    'februar': '02',
    'märz': '03',
    'maerz': '03',
    'april': '04',
    'mai': '05',
    'juni': '06',
    'juli': '07',
    'august': '08',
    'september': '09',
    'oktober': '10',
    'november': '11',
    'dezember': '12',
}


def _payslip_period(text: str) -> str:
    match = re.search(
        r'(?:Korrekturabrechnung|Abrechnung)\s+für\s+([A-Za-zÄÖÜäöüß]+)\s+(20\d{2})',
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return ''
    month_name = match.group(1).lower().replace('ä', 'ae')
    month = _GERMAN_MONTHS.get(month_name) or _GERMAN_MONTHS.get(match.group(1).lower())
    return f'{match.group(2)}-{month}' if month else ''


def _personal_adjustments(text: str) -> list[dict]:
    match = re.search(
        r'Persönliche\s+Be-/Abzüge\s+(.*?)\s+Auszahlungsbetrag',
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return []
    results = []
    for raw_line in match.group(1).splitlines():
        clean = ' '.join(raw_line.split())
        if not clean:
            continue
        amount_match = re.search(rf'({_MONEY})\s*€?\s*    match = re.search(r'Personal-Nr\.[^\n]*\n\s*([^\s]+)', text, flags=re.IGNORECASE)
    return match.group(1).strip() if match else ''


def _first_money_after(label: str, text: str) -> Decimal | None:
    match = re.search(rf'{label}\s+({_MONEY})\s*€', text, flags=re.IGNORECASE)
    return _money(match.group(1)) if match else None


def parse_payslips(payload: bytes) -> list[dict]:
    results = []
    for page_number, text in enumerate(_pages(payload), start=1):
        if 'Abrechnung für' not in text:
            continue
        employee_name = _employee_name_from_payslip(text)
        if not employee_name:
            continue

        compensation = re.search(
            rf'(?m)^(Lohn|Gehalt)\s+LSG\s+({_MONEY})\s+({_MONEY})\s*€\s+({_MONEY})\s*€\s*$',
            text,
            flags=re.IGNORECASE,
        )
        compensation_type = ''
        quantity = None
        factor = None
        base_amount = None
        if compensation:
            compensation_type = 'hourly' if compensation.group(1).lower() == 'lohn' else 'salary'
            quantity = _money(compensation.group(2))
            factor = _money(compensation.group(3))
            base_amount = _money(compensation.group(4))

        supplements = []
        supplement_pattern = re.compile(
            rf'(?mi)^([^\n]*(?:Nacht|Sonntag|Samstag)[^\n]*?)\s+([A-Z]{{2,4}})\s+'
            rf'({_MONEY})\s+({_MONEY})\s*€\s+([0-9]+(?:,[0-9]+)?)\s*%\s+({_MONEY})\s*€\s*$'
        )
        for match in supplement_pattern.finditer(text):
            supplements.append({
                'label': ' '.join(match.group(1).split()),
                'code': match.group(2),
                'hours': str(_money(match.group(3)) or Decimal('0')),
                'hourly_rate': str(_money(match.group(4)) or Decimal('0')),
                'percent': str(_money(match.group(5)) or Decimal('0')),
                'amount': str(_money(match.group(6)) or Decimal('0')),
            })

        net_amount = _first_money_after(r'(?m)^Netto', text)
        payout_amount = _first_money_after(r'(?m)^Auszahlungsbetrag', text)
        gross_amount = _first_money_after(r'(?m)^Gesamtbrutto', text)

        results.append({
            'kind': 'payslip',
            'employee_name': employee_name,
            'personal_number': _personal_number(text),
            'period': _payslip_period(text),
            'is_correction': bool(re.search(r'Korrekturabrechnung\s+für', text, flags=re.IGNORECASE)),
            'compensation_type': compensation_type,
            'quantity': str(quantity) if quantity is not None else None,
            'hourly_rate': str(factor) if compensation_type == 'hourly' and factor is not None else None,
            'monthly_salary': str(factor) if compensation_type == 'salary' and factor is not None else None,
            'base_amount': str(base_amount) if base_amount is not None else None,
            'gross_amount': str(gross_amount) if gross_amount is not None else None,
            'net_amount': str(net_amount) if net_amount is not None else None,
            'payout_amount': str(payout_amount) if payout_amount is not None else None,
            'personal_adjustments': _personal_adjustments(text),
            'supplements': supplements,
            'page': page_number,
        })
    return results


def parse_payment_list(payload: bytes) -> list[dict]:
    results = []
    for page_number, text in enumerate(_pages(payload), start=1):
        for line in text.splitlines():
            clean = ' '.join(line.split())
            if 'Lohn & Gehalt' not in clean:
                continue
            parts = re.split(r'\s+Lohn\s*&\s*Gehalt\s+', clean, maxsplit=1, flags=re.IGNORECASE)
            if len(parts) != 2:
                continue
            employee_name = parts[0].strip()
            tail = parts[1]

            amount_match = re.search(rf'({_MONEY})\s*$', tail)
            if not amount_match:
                continue
            amount = _money(amount_match.group(1))
            if amount is None:
                continue

            iban_match = re.search(r'\bDE(?:\s*\d){20}\b', tail, flags=re.IGNORECASE)
            iban = ' '.join(iban_match.group(0).split()) if iban_match else ''
            results.append({
                'kind': 'payment',
                'employee_name': employee_name,
                'amount': str(amount),
                'iban': iban,
                'payment_method': 'bank' if iban else 'cash',
                'page': page_number,
            })
    return results


def parse_lexware_pdf(payload: bytes) -> tuple[str, list[dict]]:
    pages = _pages(payload)
    text = '\n'.join(pages)
    normalized = text.lower()
    if 'zahlungsliste' in normalized:
        return 'zahlungsliste', parse_payment_list(payload)
    if 'abrechnung für' in normalized:
        return 'lohnabrechnungen', parse_payslips(payload)
    return 'unknown', []
, clean)
        if not amount_match:
            continue
        label = clean[:amount_match.start()].strip()
        amount = _money(amount_match.group(1))
        if label and amount is not None:
            results.append({'label': label, 'amount': str(amount)})
    return results


def _personal_number(text: str) -> str:
    match = re.search(r'Personal-Nr\.[^\n]*\n\s*([^\s]+)', text, flags=re.IGNORECASE)
    return match.group(1).strip() if match else ''


def _first_money_after(label: str, text: str) -> Decimal | None:
    match = re.search(rf'{label}\s+({_MONEY})\s*€', text, flags=re.IGNORECASE)
    return _money(match.group(1)) if match else None


def parse_payslips(payload: bytes) -> list[dict]:
    results = []
    for page_number, text in enumerate(_pages(payload), start=1):
        if 'Abrechnung für' not in text:
            continue
        employee_name = _employee_name_from_payslip(text)
        if not employee_name:
            continue

        compensation = re.search(
            rf'(?m)^(Lohn|Gehalt)\s+LSG\s+({_MONEY})\s+({_MONEY})\s*€\s+({_MONEY})\s*€\s*$',
            text,
            flags=re.IGNORECASE,
        )
        compensation_type = ''
        quantity = None
        factor = None
        base_amount = None
        if compensation:
            compensation_type = 'hourly' if compensation.group(1).lower() == 'lohn' else 'salary'
            quantity = _money(compensation.group(2))
            factor = _money(compensation.group(3))
            base_amount = _money(compensation.group(4))

        supplements = []
        supplement_pattern = re.compile(
            rf'(?mi)^([^\n]*(?:Nacht|Sonntag|Samstag)[^\n]*?)\s+([A-Z]{{2,4}})\s+'
            rf'({_MONEY})\s+({_MONEY})\s*€\s+([0-9]+(?:,[0-9]+)?)\s*%\s+({_MONEY})\s*€\s*$'
        )
        for match in supplement_pattern.finditer(text):
            supplements.append({
                'label': ' '.join(match.group(1).split()),
                'code': match.group(2),
                'hours': str(_money(match.group(3)) or Decimal('0')),
                'hourly_rate': str(_money(match.group(4)) or Decimal('0')),
                'percent': str(_money(match.group(5)) or Decimal('0')),
                'amount': str(_money(match.group(6)) or Decimal('0')),
            })

        net_amount = _first_money_after(r'(?m)^Netto', text)
        payout_amount = _first_money_after(r'(?m)^Auszahlungsbetrag', text)
        gross_amount = _first_money_after(r'(?m)^Gesamtbrutto', text)

        results.append({
            'kind': 'payslip',
            'employee_name': employee_name,
            'personal_number': _personal_number(text),
            'compensation_type': compensation_type,
            'quantity': str(quantity) if quantity is not None else None,
            'hourly_rate': str(factor) if compensation_type == 'hourly' and factor is not None else None,
            'monthly_salary': str(factor) if compensation_type == 'salary' and factor is not None else None,
            'base_amount': str(base_amount) if base_amount is not None else None,
            'gross_amount': str(gross_amount) if gross_amount is not None else None,
            'net_amount': str(net_amount) if net_amount is not None else None,
            'payout_amount': str(payout_amount) if payout_amount is not None else None,
            'supplements': supplements,
            'page': page_number,
        })
    return results


def parse_payment_list(payload: bytes) -> list[dict]:
    results = []
    for page_number, text in enumerate(_pages(payload), start=1):
        for line in text.splitlines():
            clean = ' '.join(line.split())
            if 'Lohn & Gehalt' not in clean:
                continue
            parts = re.split(r'\s+Lohn\s*&\s*Gehalt\s+', clean, maxsplit=1, flags=re.IGNORECASE)
            if len(parts) != 2:
                continue
            employee_name = parts[0].strip()
            tail = parts[1]

            amount_match = re.search(rf'({_MONEY})\s*$', tail)
            if not amount_match:
                continue
            amount = _money(amount_match.group(1))
            if amount is None:
                continue

            iban_match = re.search(r'\bDE(?:\s*\d){20}\b', tail, flags=re.IGNORECASE)
            iban = ' '.join(iban_match.group(0).split()) if iban_match else ''
            results.append({
                'kind': 'payment',
                'employee_name': employee_name,
                'amount': str(amount),
                'iban': iban,
                'payment_method': 'bank' if iban else 'cash',
                'page': page_number,
            })
    return results


def parse_lexware_pdf(payload: bytes) -> tuple[str, list[dict]]:
    pages = _pages(payload)
    text = '\n'.join(pages)
    normalized = text.lower()
    if 'zahlungsliste' in normalized:
        return 'zahlungsliste', parse_payment_list(payload)
    if 'abrechnung für' in normalized:
        return 'lohnabrechnungen', parse_payslips(payload)
    return 'unknown', []
