from django.test import SimpleTestCase

from core.ai_shift_normalizer import deterministic_order_request, normalize_order_request


class AiShiftNormalizerTests(SimpleTestCase):
    def test_explicit_german_shift_request_extracts_all_fields(self):
        text = """Erstelle 5 Schichten für den 10.10.2026 von 10-18 Uhr
Servicekräfte für Marthas in der Akademie als Standort.

Notiz 12345"""

        parsed = deterministic_order_request(text)
        self.assertIsNotNone(parsed)
        normalized = normalize_order_request(text, parsed)
        self.assertEqual(len(normalized['shifts']), 1)
        shift = normalized['shifts'][0]
        self.assertEqual(shift['count'], 5)
        self.assertEqual(shift['date'], '2026-10-10')
        self.assertEqual(shift['start_time'], '10:00')
        self.assertEqual(shift['end_time'], '18:00')
        self.assertEqual(shift['role'], 'Servicekraft')
        self.assertEqual(shift['site_text'], 'Marthas')
        self.assertEqual(shift['location_text'], 'Akademie')
        self.assertEqual(shift['notes'], '12345')

    def test_explicit_count_does_not_multiply_llm_rows(self):
        text = 'Erstelle 5 Schichten für den 10.10.2026 von 10-18 Uhr Servicekräfte für Marthas in der Akademie als Standort.'
        llm_result = {
            'shifts': [
                {'date': '2026-10-10', 'start_time': '10:00', 'end_time': '18:00', 'count': 1, 'role': 'Servicekraft'}
                for _ in range(5)
            ]
        }
        normalized = normalize_order_request(text, llm_result)
        self.assertEqual(len(normalized['shifts']), 1)
        self.assertEqual(normalized['shifts'][0]['count'], 5)
