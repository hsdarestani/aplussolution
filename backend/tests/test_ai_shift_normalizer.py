from django.test import SimpleTestCase

from core.ai_shift_normalizer import deterministic_order_request, normalize_order_request
from core.automation_ai_views import _assignment_rules, _is_night_shift


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

    def test_total_roster_count_preserves_all_individual_rows(self):
        text = """Die Nachtdienste werden von Simret Solomon übernommen und alle anderen Dienste werden von Marie Krass übernommen.
Die Nachtdienste gehen von 22:45 Uhr bis 6:45 Uhr.
Es sind insgesamt 3 Schichten."""
        llm_result = {
            'shifts': [
                {
                    'date': '2026-10-03',
                    'start_time': '22:45',
                    'end_time': '06:45',
                    'count': 1,
                    'role': 'Front Office',
                    'site_text': 'Hotel Spenerhaus',
                    'location_text': 'Front Office',
                    'notes': 'Übernommen von Simret Solomon',
                },
                {
                    'date': '2026-10-04',
                    'start_time': '06:45',
                    'end_time': '14:45',
                    'count': 1,
                    'role': 'Front Office',
                    'site_text': 'Hotel Spenerhaus',
                    'location_text': 'Front Office',
                    'notes': 'Übernommen von Marie Krass',
                },
                {
                    'date': '2026-10-05',
                    'start_time': '22:45',
                    'end_time': '06:45',
                    'count': 1,
                    'role': 'Front Office',
                    'site_text': 'Hotel Spenerhaus',
                    'location_text': 'Front Office',
                    'notes': 'Übernommen von Simret Solomon',
                },
            ]
        }
        normalized = normalize_order_request(text, llm_result)
        self.assertEqual(len(normalized['shifts']), 3)
        self.assertFalse(normalized['shift_count_mismatch'])
        self.assertEqual([row['date'] for row in normalized['shifts']], ['2026-10-03', '2026-10-04', '2026-10-05'])
        self.assertEqual([row['count'] for row in normalized['shifts']], [1, 1, 1])

    def test_total_roster_count_rejects_collapsed_ai_result(self):
        text = 'Es sind insgesamt 15 Schichten.'
        llm_result = {
            'shifts': [{
                'date': '2026-10-03',
                'start_time': '22:45',
                'end_time': '06:45',
                'count': 15,
                'role': 'Front Office',
            }]
        }
        normalized = normalize_order_request(text, llm_result)
        self.assertTrue(normalized['shift_count_mismatch'])
        self.assertEqual(normalized['expected_shift_count'], 15)
        self.assertEqual(len(normalized['shifts']), 1)

    def test_named_assignment_rules_distinguish_night_and_other_shifts(self):
        text = 'Die Nachtdienste werden von Simret Solomon übernommen und alle anderen Dienste werden von Marie Krass übernommen.'
        self.assertEqual(_assignment_rules(text), ('Simret Solomon', 'Marie Krass'))
        self.assertTrue(_is_night_shift({'start_time': '22:45', 'end_time': '06:45'}))
        self.assertFalse(_is_night_shift({'start_time': '06:45', 'end_time': '14:45'}))
