from __future__ import annotations

import copy
import io
import re
import unicodedata
from pathlib import Path
from typing import Any

import fitz


class SmartPdfOverlayError(ValueError):
    pass


_SYNONYMS = {
    'employee': 'arbeitnehmer',
    'worker': 'arbeitnehmer',
    'staff': 'arbeitnehmer',
    'mitarbeiter': 'arbeitnehmer',
    'employer': 'arbeitgeber',
    'company': 'arbeitgeber',
    'unternehmen': 'arbeitgeber',
    'address': 'anschrift',
    'adresse': 'anschrift',
    'street': 'anschrift',
    'strasse': 'anschrift',
    'signature': 'unterschrift',
    'signatur': 'unterschrift',
    'date': 'datum',
    'place': 'ort',
    'city': 'ort',
    'firstname': 'vorname',
    'lastname': 'nachname',
}

_STOP_WORDS = {
    'der', 'die', 'das', 'den', 'dem', 'des', 'ein', 'eine', 'einer', 'eines',
    'von', 'fur', 'für', 'the', 'of', 'field', 'feld', 'bitte', 'angabe', 'angaben',
}


def _norm(value: Any) -> str:
    text = unicodedata.normalize('NFKD', str(value or '').lower())
    text = ''.join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace('ß', 'ss')
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9]+', ' ', text)).strip()


def _tokens(value: Any) -> set[str]:
    result = set()
    for token in _norm(value).split():
        if token and token not in _STOP_WORDS:
            result.add(_SYNONYMS.get(token, token))
    return result


def _dimensions(value: Any) -> tuple[str, str]:
    tokens = _tokens(value)
    actor = ''
    if 'arbeitnehmer' in tokens:
        actor = 'arbeitnehmer'
    elif 'arbeitgeber' in tokens:
        actor = 'arbeitgeber'

    kind = ''
    if 'anschrift' in tokens:
        kind = 'anschrift'
    elif 'unterschrift' in tokens:
        kind = 'unterschrift'
    elif 'datum' in tokens or any(token in tokens for token in {'beginn', 'ende', 'beendigung'}):
        kind = 'datum'
    elif any(token in tokens for token in {'iban', 'konto', 'bank'}):
        kind = 'bank'
    elif any(token in tokens for token in {'name', 'vorname', 'nachname', 'firma'}):
        kind = 'name'
    elif 'ort' in tokens:
        kind = 'ort'
    return actor, kind


def _position(rect: fitz.Rect, page: fitz.Page) -> dict[str, float]:
    width = max(1.0, float(page.rect.width))
    height = max(1.0, float(page.rect.height))
    x = max(0.0, min(0.99, rect.x0 / width))
    y = max(0.0, min(0.99, rect.y0 / height))
    return {
        'x': round(x, 6),
        'y': round(y, 6),
        'width': round(max(0.015, min(1.0 - x, rect.width / width)), 6),
        'height': round(max(0.010, min(1.0 - y, rect.height / height)), 6),
    }


def _rect_from_position(position: dict[str, Any], page: fitz.Page) -> fitz.Rect:
    x = float(position.get('x', 0) or 0)
    y = float(position.get('y', 0) or 0)
    width = float(position.get('width', position.get('breite', 0.2)) or 0.2)
    height = float(position.get('height', position.get('hoehe', 0.03)) or 0.03)
    # Coordinates below 1 are normalized; larger values are PDF points.
    if max(abs(x), abs(y), abs(width), abs(height)) <= 1.001:
        return fitz.Rect(
            x * page.rect.width,
            y * page.rect.height,
            (x + width) * page.rect.width,
            (y + height) * page.rect.height,
        )
    return fitz.Rect(x, y, x + width, y + height)


def _text_lines(page: fitz.Page) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for block in page.get_text('dict').get('blocks', []):
        if block.get('type') != 0:
            continue
        for line in block.get('lines', []):
            texts: list[str] = []
            sizes: list[float] = []
            fonts: list[str] = []
            rect: fitz.Rect | None = None
            for span in line.get('spans', []):
                text = str(span.get('text') or '').strip()
                if not text:
                    continue
                span_rect = fitz.Rect(span.get('bbox', (0, 0, 0, 0)))
                if span_rect.is_empty:
                    continue
                texts.append(text)
                sizes.append(float(span.get('size') or 9))
                fonts.append(str(span.get('font') or ''))
                rect = span_rect if rect is None else rect | span_rect
            if texts and rect is not None:
                result.append({
                    'text': ' '.join(texts).strip(),
                    'rect': rect,
                    'font_size': max(sizes or [9]),
                    'font_name': fonts[0] if fonts else '',
                })
    return result


def _horizontal_lines(page: fitz.Page) -> list[tuple[float, float, float]]:
    candidates: list[tuple[float, float, float]] = []
    try:
        drawings = page.get_drawings()
    except Exception:
        drawings = []
    for drawing in drawings:
        for item in drawing.get('items', []):
            kind = item[0]
            if kind == 'l':
                p1, p2 = item[1], item[2]
                if abs(p1.y - p2.y) <= 1.6 and abs(p2.x - p1.x) >= 38:
                    candidates.append((min(p1.x, p2.x), max(p1.x, p2.x), (p1.y + p2.y) / 2))
            elif kind == 're':
                rect = fitz.Rect(item[1])
                if rect.width >= 38 and 5 <= rect.height <= 45:
                    candidates.append((rect.x0, rect.x1, rect.y1))
    candidates.sort(key=lambda row: (round(row[2], 1), row[0]))
    deduped: list[tuple[float, float, float]] = []
    for candidate in candidates:
        if any(
            abs(candidate[2] - other[2]) < 2
            and abs(candidate[0] - other[0]) < 4
            and abs(candidate[1] - other[1]) < 4
            for other in deduped
        ):
            continue
        deduped.append(candidate)
    return deduped


def _nearest_label(
    text_lines: list[dict[str, Any]], x0: float, x1: float, y: float
) -> dict[str, Any] | None:
    width = max(1.0, x1 - x0)
    candidates: list[tuple[float, float, dict[str, Any]]] = []
    for line in text_lines:
        rect: fitz.Rect = line['rect']
        text = str(line['text']).strip().strip(':')
        if len(_norm(text)) < 2 or len(text) > 100 or float(line['font_size']) >= 13:
            continue
        overlap = max(0.0, min(x1, rect.x1) - max(x0, rect.x0))
        x_near = abs(rect.x0 - x0) <= max(20.0, width * 0.20)
        if overlap <= 0 and not x_near:
            continue
        distance_above = y - rect.y1
        if -2 <= distance_above <= 28:
            candidates.append((abs(distance_above), abs(rect.x0 - x0), line))
        # Some forms place the label immediately to the left of the input line.
        same_row = abs(((rect.y0 + rect.y1) / 2) - y) <= max(8.0, rect.height)
        if same_row and rect.x1 <= x0 + 4 and x0 - rect.x1 <= 95:
            candidates.append((0.5, x0 - rect.x1, line))
    candidates.sort(key=lambda row: (row[0], row[1]))
    return candidates[0][2] if candidates else None


def _line_candidates(page: fitz.Page, page_number: int) -> list[dict[str, Any]]:
    text_lines = _text_lines(page)
    candidates: list[dict[str, Any]] = []
    for x0, x1, y in _horizontal_lines(page):
        label = _nearest_label(text_lines, x0, x1, y)
        if not label:
            continue
        top = max(label['rect'].y1 + 1, y - max(15.0, float(label['font_size']) * 1.45))
        bottom = max(top + 7, y - 1)
        rect = fitz.Rect(x0 + 2, top, x1 - 2, bottom)
        if rect.width < 25 or rect.height < 6:
            continue
        candidates.append({
            'label': str(label['text']).strip().strip(':'),
            'page': page_number,
            'position': _position(rect, page),
            'font_size': max(6.5, min(12.0, float(label['font_size']) * 0.92)),
            'source': 'smartdocs-line',
        })
    return candidates


def _widget_candidates(page: fitz.Page, page_number: int) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    try:
        widgets = list(page.widgets() or [])
    except Exception:
        widgets = []
    for widget in widgets:
        label = str(widget.field_label or widget.field_name or '').strip()
        if not label:
            continue
        result.append({
            'label': label,
            'page': page_number,
            'position': _position(widget.rect, page),
            'font_size': 9.0,
            'source': 'pdf-widget',
            'field_name': str(widget.field_name or ''),
        })
    return result


def _inline_candidates(page: fitz.Page, page_number: int) -> list[dict[str, Any]]:
    lines = _text_lines(page)
    result: list[dict[str, Any]] = []
    right_margin = float(page.rect.width) - 24
    for index, line in enumerate(lines):
        rect: fitz.Rect = line['rect']
        if len(str(line['text'])) > 85 or float(line['font_size']) >= 13:
            continue
        next_x = right_margin
        for other in lines:
            other_rect: fitz.Rect = other['rect']
            same_row = abs(other_rect.y0 - rect.y0) <= max(4, rect.height * 0.7)
            if same_row and other_rect.x0 > rect.x1 + 3:
                next_x = min(next_x, other_rect.x0 - 3)
        x0 = rect.x1 + 6
        if next_x - x0 < 45:
            continue
        field_rect = fitz.Rect(x0, rect.y0 - 1, next_x, rect.y1 + 1)
        result.append({
            'label': str(line['text']).strip().strip(':'),
            'page': page_number,
            'position': _position(field_rect, page),
            'font_size': max(6.5, min(12.0, float(line['font_size']))),
            'source': 'smartdocs-inline',
        })
    return result


def _field_text(field: dict[str, Any]) -> str:
    return ' '.join(str(field.get(key) or '') for key in ('label', 'name', 'source'))


def _match_score(field: dict[str, Any], candidate: dict[str, Any]) -> float:
    wanted_text = _field_text(field)
    candidate_text = str(candidate.get('label') or candidate.get('field_name') or '')
    wanted = _tokens(wanted_text)
    found = _tokens(candidate_text)
    if not wanted or not found:
        return 0.0
    wanted_actor, wanted_kind = _dimensions(wanted_text)
    found_actor, found_kind = _dimensions(candidate_text)
    if wanted_actor and found_actor and wanted_actor != found_actor:
        return 0.0
    if wanted_kind and found_kind and wanted_kind != found_kind:
        return 0.0
    common = len(wanted & found)
    score = common / max(1, len(wanted | found))
    wanted_norm = _norm(wanted_text)
    candidate_norm = _norm(candidate_text)
    if candidate_norm and (candidate_norm in wanted_norm or wanted_norm in candidate_norm):
        score += 0.45
    if wanted_actor and wanted_actor == found_actor:
        score += 0.25
    if wanted_kind and wanted_kind == found_kind:
        score += 0.30
    # Real form widgets and detected input lines are safer than arbitrary inline whitespace.
    if candidate.get('source') == 'pdf-widget':
        score += 0.20
    elif candidate.get('source') == 'smartdocs-line':
        score += 0.12
    return score


def analyse_pdf_template(source_path: str | Path, schema_fields: list[dict[str, Any]]) -> dict[str, Any]:
    path = Path(source_path)
    document = fitz.open(path)
    candidates: list[dict[str, Any]] = []
    try:
        for index, page in enumerate(document, start=1):
            candidates.extend(_widget_candidates(page, index))
            candidates.extend(_line_candidates(page, index))
            candidates.extend(_inline_candidates(page, index))
    finally:
        document.close()

    resolved: dict[str, Any] = {}
    used: set[int] = set()
    diagnostics: list[dict[str, Any]] = []
    for field in schema_fields:
        name = str(field.get('name') or '').strip()
        if not name:
            continue
        ranked = sorted(
            [(_match_score(field, candidate), index, candidate) for index, candidate in enumerate(candidates) if index not in used],
            key=lambda row: row[0],
            reverse=True,
        )
        best = ranked[0] if ranked else None
        runner_up = ranked[1] if len(ranked) > 1 else None
        if not best or best[0] < 0.52 or (runner_up and best[0] - runner_up[0] < 0.07 and best[0] < 0.95):
            diagnostics.append({
                'field': name,
                'label': field.get('label') or name,
                'status': 'unmatched',
                'best_score': round(best[0], 3) if best else 0,
            })
            continue
        score, index, candidate = best
        used.add(index)
        resolved[name] = {
            **copy.deepcopy(candidate),
            'confidence': round(min(1.0, score), 3),
        }
        diagnostics.append({
            'field': name,
            'label': field.get('label') or name,
            'status': 'matched',
            'candidate': candidate.get('label'),
            'source': candidate.get('source'),
            'confidence': round(min(1.0, score), 3),
        })

    return {
        'engine': 'smartdocs-layout-v1',
        'resolved_coordinates': resolved,
        'diagnostics': diagnostics,
        'candidate_count': len(candidates),
        'matched_count': len(resolved),
        'field_count': len([field for field in schema_fields if field.get('name')]),
    }


def _base14_font(font_name: str) -> str:
    name = str(font_name or '').lower()
    if any(token in name for token in ('times', 'serif', 'georgia', 'garamond')):
        return 'tiro'
    if any(token in name for token in ('courier', 'mono', 'typewriter')):
        return 'cour'
    return 'helv'


def _fit_font_size(text: str, width: float, requested: float, font_name: str = 'helv') -> float:
    size = max(6.0, min(18.0, float(requested or 9)))
    try:
        length = fitz.get_text_length(text, fontname=font_name, fontsize=size)
    except Exception:
        length = len(text) * size * 0.52
    if length <= width:
        return size
    return max(6.0, size * (width / max(1.0, length)) * 0.96)


def _insert_value(page: fitz.Page, rect: fitz.Rect, value: str, font_size: float, font_name: str = '') -> None:
    text = str(value or '').strip()
    if not text:
        return
    font = _base14_font(font_name)
    size = _fit_font_size(text, max(8.0, rect.width), font_size, font)
    baseline = min(rect.y1 - 0.6, rect.y0 + max(size, rect.height * 0.82))
    try:
        page.insert_text(
            fitz.Point(rect.x0, baseline),
            text[:800],
            fontname=font,
            fontsize=size,
            color=(0, 0, 0),
            overlay=True,
        )
    except Exception:
        page.insert_textbox(
            fitz.Rect(rect.x0, rect.y0 - 1, rect.x1, rect.y1 + max(3, rect.height * 0.45)),
            text[:800],
            fontname='helv',
            fontsize=size,
            color=(0, 0, 0),
            overlay=True,
        )


def render_smart_pdf_overlay(
    source_path: str | Path,
    schema_fields: list[dict[str, Any]],
    data: dict[str, Any],
    analysis: dict[str, Any] | None = None,
    format_value=lambda value: '' if value is None else str(value),
) -> tuple[bytes, dict[str, Any]]:
    layout = copy.deepcopy(analysis or analyse_pdf_template(source_path, schema_fields))
    resolved = dict(layout.get('resolved_coordinates') or {})
    required_missing: list[str] = []
    placed: list[str] = []

    document = fitz.open(source_path)
    try:
        # Special-case common German signature line: combine Ort + Datum if a template
        # exposes only one physical field for both values.
        handled: set[str] = set()
        for field in schema_fields:
            name = str(field.get('name') or '')
            if not name or name in handled:
                continue
            value = data.get(name)
            if value in (None, '', [], {}):
                continue
            target = resolved.get(name)
            if target:
                page_number = max(1, int(target.get('page') or 1))
                if page_number > len(document):
                    if field.get('required'):
                        required_missing.append(name)
                    continue
                page = document[page_number - 1]
                rect = _rect_from_position(target.get('position') or {}, page)
                _insert_value(page, rect, format_value(value), float(target.get('font_size') or 9), target.get('font_name') or '')
                placed.append(name)
                handled.add(name)
                continue

            if name in {'signature_place', 'place'}:
                date_name = 'signature_date' if 'signature_date' in data else 'date'
                date_value = data.get(date_name)
                # Try an explicit shared field detected as "Ort, Datum".
                shared_field = {'name': '__place_date__', 'label': 'Ort, Datum', 'source': 'signature_place signature_date'}
                shared = analyse_pdf_template(source_path, [shared_field]).get('resolved_coordinates', {}).get('__place_date__')
                if shared:
                    page = document[max(1, int(shared.get('page') or 1)) - 1]
                    rect = _rect_from_position(shared.get('position') or {}, page)
                    combined = f'{format_value(value)}, {format_value(date_value)}'.strip(', ')
                    _insert_value(page, rect, combined, float(shared.get('font_size') or 9), shared.get('font_name') or '')
                    placed.extend([name] + ([date_name] if date_value else []))
                    handled.add(name)
                    if date_value:
                        handled.add(date_name)
                    continue

            if field.get('required'):
                required_missing.append(name)

        if required_missing:
            labels = []
            for name in required_missing:
                field = next((item for item in schema_fields if item.get('name') == name), {})
                labels.append(str(field.get('label') or name))
            raise SmartPdfOverlayError(
                'PDF-Feldposition konnte nicht sicher erkannt werden: ' + ', '.join(labels)
            )
        output = document.tobytes(garbage=4, deflate=True, clean=True)
    finally:
        document.close()

    layout['placed_fields'] = placed
    layout['unplaced_required'] = required_missing
    return output, layout
