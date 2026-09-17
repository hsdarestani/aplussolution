from core.ai_shift_normalizer import deterministic_order_request, normalize_order_request


RAW_MULTI_SHIFT = """Bitte 3 Schichten für das Hotel Spenerhaus erstellen.

20.10.2028 Frühdienst von 06:30 bis 14:30 – Front Office
21.10.2028 Spätdienst von 14:30 bis 22:30 – Front Office
22.10.2028 Nachtdienst von 22:30 bis 06:30 – Front Office

Alle drei Schichten sind im Hotel Spenerhaus und werden von Store Reviewer übernommen.

Notiz: AI-Test 3 Schichten
"""


def test_front_office_tail_is_position_not_employee_and_global_worker_applies():
    parsed = {
        'shifts': [
            {
                'date': '2028-10-20',
                'start_time': '06:30',
                'end_time': '14:30',
                'count': 1,
                'role': 'Front Office',
                'site_text': 'Hotel Spenerhaus',
                'location_text': 'Hotel Spenerhaus',
                'site_address': '',
                'notes': 'AI-Test 3 Schichten',
            },
            {
                'date': '2028-10-21',
                'start_time': '14:30',
                'end_time': '22:30',
                'count': 1,
                'role': 'Front Office',
                'site_text': 'Hotel Spenerhaus',
                'location_text': 'Hotel Spenerhaus',
                'site_address': '',
                'notes': 'AI-Test 3 Schichten',
            },
            {
                'date': '2028-10-22',
                'start_time': '22:30',
                'end_time': '06:30',
                'count': 1,
                'role': 'Front Office',
                'site_text': 'Hotel Spenerhaus',
                'location_text': 'Hotel Spenerhaus',
                'site_address': '',
                'notes': 'AI-Test 3 Schichten',
            },
        ]
    }

    result = normalize_order_request(RAW_MULTI_SHIFT, parsed)

    assert len(result['shifts']) == 3
    assert [row['role'] for row in result['shifts']] == ['Front Office'] * 3
    assert [row.get('assignment_worker_name') for row in result['shifts']] == ['Store Reviewer'] * 3
    assert all(row.get('assignment_worker_name') != 'Front Office' for row in result['shifts'])


def test_multi_shift_request_has_deterministic_three_row_fallback():
    fallback = deterministic_order_request(RAW_MULTI_SHIFT)
    assert fallback is not None

    result = normalize_order_request(RAW_MULTI_SHIFT, fallback)

    assert len(result['shifts']) == 3
    assert [row['date'] for row in result['shifts']] == ['2028-10-20', '2028-10-21', '2028-10-22']
    assert [row['start_time'] for row in result['shifts']] == ['06:30', '14:30', '22:30']
    assert [row['end_time'] for row in result['shifts']] == ['14:30', '22:30', '06:30']
    assert [row['role'] for row in result['shifts']] == ['Front Office'] * 3
    assert [row.get('assignment_worker_name') for row in result['shifts']] == ['Store Reviewer'] * 3
