from pathlib import Path

sync_path = Path('backend/core/wiw_sync.py')
text = sync_path.read_text(encoding='utf-8')

old_import = "from decimal import Decimal, InvalidOperation\n\nfrom django.db import transaction"
new_import = "from decimal import Decimal, InvalidOperation\n\nfrom dateutil.parser import parse as parse_flexible_datetime\nfrom django.db import transaction"
if old_import not in text:
    raise SystemExit('Import patch target was not found.')
text = text.replace(old_import, new_import, 1)

old_function = '''def as_datetime(value):
    if not value:
        return None
    if isinstance(value, datetime):
        result = value
    else:
        result = parse_datetime(str(value))
    if not result:
        return None
    if timezone.is_naive(result):
        result = timezone.make_aware(result, timezone.get_current_timezone())
    return result
'''
new_function = '''def as_datetime(value):
    if not value:
        return None
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, (int, float)) or str(value).strip().isdigit():
        try:
            result = datetime.fromtimestamp(float(value), tz=timezone.get_current_timezone())
        except (OverflowError, OSError, TypeError, ValueError):
            return None
    else:
        raw = str(value).strip()
        result = parse_datetime(raw)
        if not result:
            try:
                result = parse_flexible_datetime(raw)
            except (OverflowError, TypeError, ValueError):
                return None
    if timezone.is_naive(result):
        result = timezone.make_aware(result, timezone.get_current_timezone())
    return result
'''
if old_function not in text:
    raise SystemExit('Datetime function patch target was not found.')
text = text.replace(old_function, new_function, 1)
sync_path.write_text(text, encoding='utf-8')

test_path = Path('backend/tests/test_wiw.py')
tests = test_path.read_text(encoding='utf-8')
test_block = '''

@pytest.mark.django_db
def test_wiw_datetime_parser_accepts_rfc_2822_and_unix_values():
    from core.wiw_sync import as_datetime

    rfc_value = as_datetime('Tue, 28 Jul 2026 16:00:00 +0200')
    unix_value = as_datetime(1785254400)

    assert rfc_value is not None
    assert rfc_value.isoformat() == '2026-07-28T16:00:00+02:00'
    assert unix_value is not None
    assert timezone.is_aware(unix_value)
'''
if 'test_wiw_datetime_parser_accepts_rfc_2822_and_unix_values' not in tests:
    test_path.write_text(tests.rstrip() + test_block + '\n', encoding='utf-8')

print('Applied WIW RFC/unix datetime parsing fix and regression test.')
