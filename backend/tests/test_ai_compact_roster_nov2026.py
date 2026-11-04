"""Offline AI intake regression for compact hotel roster messages."""
from unittest.mock import patch

import pytest

from core.ai_shift_normalizer import deterministic_order_request, normalize_order_request


ROSTER = """Freitag, 20.11.2026: 2x 07:00-13:00
Samstag, 21.11.2026: 1x 08:00-13:00

Alle Schichten Housekeeping
Hotel Spenerhaus"""


def test_compact_roster_keeps_per_date_counts_hotel_and_role():
    parsed = deterministic_order_request(ROSTER)
    assert parsed is not None
    rows = normalize_order_request(ROSTER, parsed)['shifts']
    assert len(rows) == 2
    assert [(row['date'], row['start_time'], row['end_time'], row['count']) for row in rows] == [
        ('2026-11-20', '07:00', '13:00', 2),
        ('2026-11-21', '08:00', '13:00', 1),
    ]
    assert all(row['role'] == 'Housekeeping' for row in rows)
    assert all(row['site_text'] == 'Hotel Spenerhaus' for row in rows)
    assert all(row['location_text'] == 'Hotel Spenerhaus' for row in rows)


@pytest.mark.django_db
def test_compact_roster_endpoint_never_needs_openai(auth_admin):
    with patch('core.semantic_ai_views._call_ai', side_effect=AssertionError('external AI must not be called')):
        response = auth_admin.post('/api/automation/orders/parse/', {'text': ROSTER}, format='json')
    assert response.status_code == 200, response.data
    assert sum(row['count'] for row in response.data['shifts']) == 3
    assert [row['count'] for row in response.data['shifts']] == [2, 1]
