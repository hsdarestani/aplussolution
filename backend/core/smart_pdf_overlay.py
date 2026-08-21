from __future__ import annotations

import copy
import re
import unicodedata
from pathlib import Path
from typing import Any

import fitz


class SmartPdfOverlayError(ValueError):
    pass


_SYNONYMS = {
    'employee': 'arbeitnehmer', 'worker': 'arbeitnehmer', 'staff': 'arbeitnehmer',
    'mitarbeiter': 'arbeitnehmer', 'employer': 'arbeitgeber', 'company': 'arbeitgeber',
    'unternehmen': 'arbeitgeber', 'address': 'anschrift', 'adresse': 'anschrift',
    'street': 'anschrift', 'strasse': 'anschrift', 'signature': 'unterschrift',
    'signatur': 'unterschrift', 'date': 'datum', 'place': 'ort', 'city': 'ort',
    'firstname': 'vorname', 'lastname': 'nachname',
}
_STOP = {
    'der', 'die', 'das', 'den', 'dem', 'des', 'ein', 'eine', 'einer', 'eines',
    'von', 'fur', 'für', 'the', 'of', 'field', 'feld', 'bitte', 'angabe', 'angaben',
}


def _norm(value: Any) -> str:
    text = unicodedata.normalize('NFKD', str(value or '').lower())
    text = ''.join(ch for ch in text if not unicodedata.combining(ch)).replace('ß', 'ss')
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9]+', ' ', text)).strip()


def _tokens(value: Any) -> set[str]:
    return {
        _SYNONYMS.get(token, token)
        for token in _norm(value).split()
        if token and token not in _STOP
    }


def _dimensions(value: Any) -> tuple[str, str]:
    tokens = _tokens(value)
    actor = 'arbeitnehmer' if 'arbeitnehmer' in tokens else ('arbeitgeber' if 'arbeitgeber' in tokens else '')
    kind = ''
    if 'anschrift' in tokens:
        kind = 'anschrift'
    elif 'datum' in tokens or any(token in tokens for token in {'beginn', 'ende', 'beendigung'}):
        kind = 'datum'
    elif 'ort' in tokens:
        kind = 'ort'
    elif any(token in tokens for token in {'iban', 'konto', 'bank'}):
        kind = 'bank'
    elif any(token in tokens for token in {'name', 'vorname', 'nachname', 'firma'}):
        kind = 'name'
    elif 'unterschrift' in tokens:
        kind = 'unterschrift'
    return actor, kind


def _position(rect: fitz.Rect, page: fitz.Page) -> dict[str, float]:
    width = max(1.0, float(page.rect.width)); height = max(1.0, float(page.rect.height))
    x = max(0.0, min(0.99, rect.x0 / width)); y = max(0.0, min(0.99, rect.y0 / height))
    return {
        'x': round(x, 6), 'y': round(y, 6),
        'width': round(max(0.015, min(1.0 - x, rect.width / width)), 6),
        'height': round(max(0.010, min(1.0 - y, rect.height / height)), 6),
    }


def _rect(position: dict[str, Any], page: fitz.Page) -> fitz.Rect:
    x = float(position.get('x', 0) or 0); y = float(position.get('y', 0) or 0)
    width = float(position.get('width', position.get('breite', 0.2)) or 0.2)
    height = float(position.get('height', position.get('hoehe', 0.03)) or 0.03)
    if max(abs(x), abs(y), abs(width), abs(height)) <= 1.001:
        return fitz.Rect(x * page.rect.width, y * page.rect.height,
                         (x + width) * page.rect.width, (y + height) * page.rect.height)
    return fitz.Rect(x, y, x + width, y + height)


def _text_lines(page: fitz.Page) -> list[dict[str, Any]]:
    result = []
    for block in page.get_text('dict').get('blocks', []):
        if block.get('type') != 0:
            continue
        for line in block.get('lines', []):
            texts, sizes, fonts = [], [], []
            rect = None
            for span in line.get('spans', []):
                text = str(span.get('text') or '').strip()
                span_rect = fitz.Rect(span.get('bbox', (0, 0, 0, 0)))
                if not text or span_rect.is_empty:
                    continue
                texts.append(text); sizes.append(float(span.get('size') or 9)); fonts.append(str(span.get('font') or ''))
                rect = span_rect if rect is None else rect | span_rect
            if texts and rect is not None:
                result.append({'text': ' '.join(texts), 'rect': rect, 'font_size': max(sizes or [9]), 'font_name': fonts[0] if fonts else ''})
    return result


def _horizontal_lines(page: fitz.Page) -> list[tuple[float, float, float]]:
    candidates = []
    try:
        drawings = page.get_drawings()
    except Exception:
        drawings = []
    for drawing in drawings:
        for item in drawing.get('items', []):
            if item[0] == 'l':
                p1, p2 = item[1], item[2]
                if abs(p1.y - p2.y) <= 1.6 and abs(p2.x - p1.x) >= 38:
                    candidates.append((min(p1.x, p2.x), max(p1.x, p2.x), (p1.y + p2.y) / 2))
            elif item[0] == 're':
                rect = fitz.Rect(item[1])
                if rect.width >= 38 and 5 <= rect.height <= 45:
                    candidates.append((rect.x0, rect.x1, rect.y1))
    candidates.sort(key=lambda row: (round(row[2], 1), row[0]))
    result = []
    for candidate in candidates:
        if any(abs(candidate[2]-other[2]) < 2 and abs(candidate[0]-other[0]) < 4 and abs(candidate[1]-other[1]) < 4 for other in result):
            continue
        result.append(candidate)
    return result


def _nearest_label(lines: list[dict[str, Any]], x0: float, x1: float, y: float) -> dict[str, Any] | None:
    width = max(1.0, x1 - x0); candidates = []
    for line in lines:
        rect: fitz.Rect = line['rect']; text = str(line['text']).strip().strip(':')
        if len(_norm(text)) < 2 or len(text) > 100 or float(line['font_size']) >= 13:
            continue
        overlap = max(0.0, min(x1, rect.x1) - max(x0, rect.x0))
        x_near = abs(rect.x0 - x0) <= max(20.0, width * 0.20)
        if overlap > 0 or x_near:
            distance = y - rect.y1
            if -2 <= distance <= 28:
                candidates.append((abs(distance), abs(rect.x0-x0), line))
        same_row = abs(((rect.y0 + rect.y1) / 2) - y) <= max(8.0, rect.height)
        if same_row and rect.x1 <= x0 + 4 and x0 - rect.x1 <= 95:
            candidates.append((0.5, x0 - rect.x1, line))
    candidates.sort(key=lambda row: (row[0], row[1]))
    return candidates[0][2] if candidates else None


def _line_candidates(page: fitz.Page, page_number: int) -> list[dict[str, Any]]:
    lines = _text_lines(page); result = []
    for x0, x1, y in _horizontal_lines(page):
        label = _nearest_label(lines, x0, x1, y)
        if not label:
            continue
        # SmartDocs principle: write on the original field baseline, never below the input line.
        top = min(y - 5, max(label['rect'].y1 + 1, y - max(18.0, float(label['font_size']) * 1.55)))
        bottom = max(top + 7, y - 1)
        rect = fitz.Rect(x0 + 2, top, x1 - 2, bottom)
        if rect.width < 25 or rect.height < 6:
            continue
        result.append({
            'label': str(label['text']).strip().strip(':'), 'page': page_number,
            'position': _position(rect, page), 'font_size': max(6.5, min(12.0, float(label['font_size']) * 0.92)),
            'font_name': label.get('font_name') or '', 'source': 'smartdocs-line',
        })
    return result


def _widget_candidates(page: fitz.Page, page_number: int) -> list[dict[str, Any]]:
    result = []
    try:
        widgets = list(page.widgets() or [])
    except Exception:
        widgets = []
    for widget in widgets:
        label = str(widget.field_label or widget.field_name or '').strip()
        if label:
            result.append({'label': label, 'page': page_number, 'position': _position(widget.rect, page), 'font_size': 9.0, 'source': 'pdf-widget', 'field_name': str(widget.field_name or '')})
    return result


def _inline_candidates(page: fitz.Page, page_number: int) -> list[dict[str, Any]]:
    lines = _text_lines(page); result = []; right_margin = float(page.rect.width) - 24
    for line in lines:
        rect: fitz.Rect = line['rect']
        if len(str(line['text'])) > 85 or float(line['font_size']) >= 13:
            continue
        next_x = right_margin
        for other in lines:
            other_rect: fitz.Rect = other['rect']
            if abs(other_rect.y0 - rect.y0) <= max(4, rect.height * 0.7) and other_rect.x0 > rect.x1 + 3:
                next_x = min(next_x, other_rect.x0 - 3)
        x0 = rect.x1 + 6
        if next_x - x0 >= 45:
            result.append({
                'label': str(line['text']).strip().strip(':'), 'page': page_number,
                'position': _position(fitz.Rect(x0, rect.y0 - 1, next_x, rect.y1 + 1), page),
                'font_size': max(6.5, min(12.0, float(line['font_size']))), 'font_name': line.get('font_name') or '',
                'source': 'smartdocs-inline',
            })
    return result


def _field_text(field: dict[str, Any]) -> str:
    return ' '.join(str(field.get(key) or '') for key in ('label', 'name', 'source'))


def _score(field: dict[str, Any], candidate: dict[str, Any]) -> float:
    wanted_text = _field_text(field); candidate_text = str(candidate.get('label') or candidate.get('field_name') or '')
    wanted, found = _tokens(wanted_text), _tokens(candidate_text)
    if not wanted or not found:
        return 0.0
    wanted_actor, wanted_kind = _dimensions(wanted_text); found_actor, found_kind = _dimensions(candidate_text)
    if wanted_actor and found_actor and wanted_actor != found_actor:
        return 0.0
    if wanted_kind and found_kind and wanted_kind != found_kind:
        return 0.0
    score = len(wanted & found) / max(1, len(wanted | found))
    wn, cn = _norm(wanted_text), _norm(candidate_text)
    if cn and (cn in wn or wn in cn): score += 0.45
    if wanted_actor and wanted_actor == found_actor: score += 0.25
    if wanted_kind and wanted_kind == found_kind: score += 0.30
    if candidate.get('source') == 'pdf-widget': score += 0.20
    elif candidate.get('source') == 'smartdocs-line': score += 0.12
    return score


def analyse_pdf_template(source_path: str | Path, schema_fields: list[dict[str, Any]]) -> dict[str, Any]:
    document = fitz.open(Path(source_path)); candidates = []
    try:
        for number, page in enumerate(document, start=1):
            candidates.extend(_widget_candidates(page, number)); candidates.extend(_line_candidates(page, number)); candidates.extend(_inline_candidates(page, number))
    finally:
        document.close()
    resolved, diagnostics, used = {}, [], set()
    for field in schema_fields:
        name = str(field.get('name') or '').strip()
        if not name: continue
        ranked = sorted([(_score(field, candidate), idx, candidate) for idx, candidate in enumerate(candidates) if idx not in used], key=lambda row: row[0], reverse=True)
        best = ranked[0] if ranked else None; runner = ranked[1] if len(ranked) > 1 else None
        if not best or best[0] < 0.52 or (runner and best[0]-runner[0] < 0.07 and best[0] < 0.95):
            diagnostics.append({'field': name, 'label': field.get('label') or name, 'status': 'unmatched', 'best_score': round(best[0], 3) if best else 0})
            continue
        confidence, idx, candidate = best; used.add(idx)
        resolved[name] = {**copy.deepcopy(candidate), 'confidence': round(min(1.0, confidence), 3)}
        diagnostics.append({'field': name, 'label': field.get('label') or name, 'status': 'matched', 'candidate': candidate.get('label'), 'source': candidate.get('source'), 'confidence': round(min(1.0, confidence), 3)})
    return {'engine': 'smartdocs-layout-v1', 'resolved_coordinates': resolved, 'diagnostics': diagnostics, 'candidate_count': len(candidates), 'matched_count': len(resolved), 'field_count': len([f for f in schema_fields if f.get('name')])}


def _font(font_name: str) -> str:
    name = str(font_name or '').lower()
    if any(token in name for token in ('times', 'serif', 'georgia', 'garamond')): return 'tiro'
    if any(token in name for token in ('courier', 'mono', 'typewriter')): return 'cour'
    return 'helv'


def _fit_size(text: str, width: float, requested: float, font_name: str) -> float:
    size = max(5.5, min(18.0, float(requested or 9)))
    try: length = fitz.get_text_length(text, fontname=font_name, fontsize=size)
    except Exception: length = len(text) * size * 0.52
    return size if length <= width else max(5.5, size * width / max(1.0, length) * 0.96)


def _insert(page: fitz.Page, rect: fitz.Rect, value: str, font_size: float, font_name: str = '') -> None:
    text = str(value or '').strip()
    if not text: return
    base_font = _font(font_name); size = _fit_size(text, max(8.0, rect.width), font_size, base_font)
    baseline = min(rect.y1 - 0.6, rect.y0 + max(size, rect.height * 0.82))
    try:
        page.insert_text(fitz.Point(rect.x0, baseline), text[:800], fontname=base_font, fontsize=size, color=(0, 0, 0), overlay=True)
    except Exception:
        page.insert_textbox(fitz.Rect(rect.x0, max(0, rect.y0 - rect.height), rect.x1, rect.y1 + 2), text[:800], fontname='helv', fontsize=size, color=(0, 0, 0), overlay=True)


def render_smart_pdf_overlay(source_path: str | Path, schema_fields: list[dict[str, Any]], data: dict[str, Any], analysis: dict[str, Any] | None = None, format_value=lambda value: '' if value is None else str(value)) -> tuple[bytes, dict[str, Any]]:
    layout = copy.deepcopy(analysis or analyse_pdf_template(source_path, schema_fields)); resolved = dict(layout.get('resolved_coordinates') or {})
    required_missing, placed, handled = [], [], set(); document = fitz.open(source_path)
    try:
        # German forms often provide one physical line labelled "Ort, Datum".
        place_name = next((name for name in ('signature_place', 'place') if data.get(name) not in (None, '')), None)
        date_name = next((name for name in ('signature_date', 'date') if data.get(name) not in (None, '')), None)
        if place_name and date_name:
            shared = next((target for key, target in resolved.items() if key in {place_name, date_name} and {'ort', 'datum'} <= _tokens(target.get('label'))), None)
            if not shared:
                synthetic = analyse_pdf_template(source_path, [{'name': '__place_date__', 'label': 'Ort, Datum'}])
                shared = synthetic.get('resolved_coordinates', {}).get('__place_date__')
            if shared:
                page = document[max(1, int(shared.get('page') or 1)) - 1]; rect = _rect(shared.get('position') or {}, page)
                _insert(page, rect, f"{format_value(data[place_name])}, {format_value(data[date_name])}", float(shared.get('font_size') or 9), shared.get('font_name') or '')
                handled.update({place_name, date_name}); placed.extend([place_name, date_name])

        for field in schema_fields:
            name = str(field.get('name') or '')
            if not name or name in handled: continue
            value = data.get(name)
            if value in (None, '', [], {}): continue
            target = resolved.get(name)
            if not target:
                if field.get('required'): required_missing.append(name)
                continue
            page_number = max(1, int(target.get('page') or 1))
            if page_number > len(document):
                if field.get('required'): required_missing.append(name)
                continue
            page = document[page_number - 1]; rect = _rect(target.get('position') or {}, page)
            _insert(page, rect, format_value(value), float(target.get('font_size') or 9), target.get('font_name') or '')
            placed.append(name); handled.add(name)
        if required_missing:
            labels = [str(next((f.get('label') or name for f in schema_fields if f.get('name') == name), name)) for name in required_missing]
            raise SmartPdfOverlayError('PDF-Feldposition konnte nicht sicher erkannt werden: ' + ', '.join(labels))
        output = document.tobytes(garbage=4, deflate=True, clean=True)
    finally:
        document.close()
    layout['placed_fields'] = placed; layout['unplaced_required'] = required_missing
    return output, layout
