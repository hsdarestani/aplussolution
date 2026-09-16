from core.schedule_reports import _cell_html


def test_schedule_pdf_cell_renders_notes_below_shift_and_never_pause_label():
    html = _cell_html(
        [{
            'time': '08:30–17:00',
            'client': 'Marthas',
            'location': 'Evangelische Akademie',
            'groups': 'Service',
            'notes': 'Bitte 15 Min früher da sein\nSchwarze Schuhe & Hemd',
        }],
        show_client=True,
        show_group=True,
    )

    assert '<i>Notiz: Bitte 15 Min früher da sein<br/>Schwarze Schuhe &amp; Hemd</i>' in html
    assert 'Pause' not in html
    assert '08:30–17:00' in html


def test_schedule_pdf_cell_without_note_stays_compact_and_pause_free():
    html = _cell_html(
        [{
            'time': '19:00–00:00',
            'client': 'Marthas',
            'location': 'Stadthaus',
            'groups': 'Service',
            'notes': '',
        }],
        show_client=False,
        show_group=False,
    )

    assert 'Notiz:' not in html
    assert 'Pause' not in html
