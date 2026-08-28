import base64
import re
import tempfile
from pathlib import Path

import fitz
from django.core.files.base import ContentFile

from .models import ContractSignature
from .smart_pdf_overlay import analyse_pdf_template


_DATA_URL = re.compile(r'^data:image/(?:png|jpeg|jpg);base64,(.+)$', re.IGNORECASE | re.DOTALL)
_SIGNATURE_WORDS = re.compile(r'\b(unterschrift|signatur|signature)\b', re.IGNORECASE)
_ROLE_LABELS = {
    ContractSignature.Role.EMPLOYEE: 'Mitarbeiter',
    ContractSignature.Role.EMPLOYER: 'Arbeitgeber',
    ContractSignature.Role.CLIENT: 'Kunde',
}
_ROLE_FIELD_LABELS = {
    ContractSignature.Role.EMPLOYEE: 'Arbeitnehmer Mitarbeiter Unterschrift',
    ContractSignature.Role.EMPLOYER: 'Arbeitgeber Unternehmen Unterschrift',
    ContractSignature.Role.CLIENT: 'Kunde Auftraggeber Unterschrift',
}
_ROLE_CONTEXT_WORDS = {
    ContractSignature.Role.EMPLOYEE: ('arbeitnehmer', 'mitarbeiter', 'beschäftigte', 'beschaeftigte'),
    ContractSignature.Role.EMPLOYER: ('arbeitgeber', 'unternehmen', 'firma', 'vertreter'),
    ContractSignature.Role.CLIENT: ('kunde', 'auftraggeber', 'entleiher'),
}


def _image_bytes(value):
    if not isinstance(value, str):
        return None
    match = _DATA_URL.match(value.strip())
    if not match:
        return None
    try:
        return base64.b64decode(match.group(1), validate=True)
    except Exception:
        return None


def _normalise_placement(raw, *, source='template'):
    if not isinstance(raw, dict):
        return None
    try:
        page = max(1, int(raw.get('page', 1)))
        x = float(raw.get('x', 0))
        y = float(raw.get('y', 0))
        width = float(raw.get('width', raw.get('breite', 0.24)))
        height = float(raw.get('height', raw.get('hoehe', 0.055)))
    except (TypeError, ValueError):
        return None
    if width <= 0 or height <= 0:
        return None
    return {
        'page': page,
        'position': {'x': x, 'y': y, 'width': width, 'height': height},
        'source': source,
        'confidence': float(raw.get('confidence', 1.0) or 1.0),
    }


def _template_placements(template):
    schema = getattr(template, 'schema', None) or {}
    raw = schema.get('signature_placements') or schema.get('signaturePlacements') or {}
    result = {}
    if not isinstance(raw, dict):
        return result
    for role, placement in raw.items():
        parsed = _normalise_placement(placement, source='template')
        if parsed:
            result[str(role)] = parsed
    return result


def _smartdocs_placements(source, roles):
    fields = [
        {'name': f'signature_{role}', 'label': _ROLE_FIELD_LABELS.get(role, f'{role} Unterschrift')}
        for role in roles
    ]
    if not fields:
        return {}
    try:
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as handle:
            handle.write(source)
            path = Path(handle.name)
        try:
            analysed = analyse_pdf_template(path, fields)
        finally:
            path.unlink(missing_ok=True)
    except Exception:
        return {}

    resolved = analysed.get('resolved_coordinates') or {}
    result = {}
    for role in roles:
        value = resolved.get(f'signature_{role}')
        if not value:
            continue
        parsed = _normalise_placement(
            {
                'page': value.get('page', 1),
                **(value.get('position') or {}),
                'confidence': value.get('confidence', 0.8),
            },
            source=value.get('source') or 'smartdocs',
        )
        if parsed and parsed['confidence'] >= 0.52:
            result[role] = parsed
    return result


def _text_lines(page):
    words = page.get_text('words') or []
    grouped = {}
    for word in words:
        if len(word) < 8:
            continue
        x0, y0, x1, y1, text, block, line, _ = word[:8]
        key = (block, line)
        row = grouped.setdefault(key, {'words': [], 'rect': fitz.Rect(x0, y0, x1, y1)})
        row['words'].append((x0, str(text)))
        row['rect'] |= fitz.Rect(x0, y0, x1, y1)
    result = []
    for row in grouped.values():
        row['words'].sort(key=lambda item: item[0])
        row['text'] = ' '.join(item[1] for item in row['words'])
        result.append(row)
    return result


def _horizontal_lines(page):
    lines = []
    try:
        drawings = page.get_drawings()
    except Exception:
        drawings = []
    for drawing in drawings:
        for item in drawing.get('items', []):
            if item[0] == 'l':
                p1, p2 = item[1], item[2]
                if abs(p1.y - p2.y) <= 1.8 and abs(p2.x - p1.x) >= 65:
                    lines.append((min(p1.x, p2.x), max(p1.x, p2.x), (p1.y + p2.y) / 2))
            elif item[0] == 're':
                rect = fitz.Rect(item[1])
                if rect.width >= 65 and rect.height <= 45:
                    lines.append((rect.x0, rect.x1, rect.y1))
    return lines


def _role_score(text, role):
    lowered = str(text or '').casefold().replace('ä', 'ae').replace('ö', 'oe').replace('ü', 'ue').replace('ß', 'ss')
    score = 0
    for word in _ROLE_CONTEXT_WORDS.get(role, ()):
        normal = word.casefold().replace('ä', 'ae').replace('ö', 'oe').replace('ü', 'ue').replace('ß', 'ss')
        if normal in lowered:
            score += 3
    if _SIGNATURE_WORDS.search(str(text or '')):
        score += 1
    return score


def _candidate_rect(page, label_rect):
    best = None
    for x0, x1, y in _horizontal_lines(page):
        overlap = max(0.0, min(x1, label_rect.x1 + 170) - max(x0, label_rect.x0 - 80))
        vertical = abs(y - label_rect.y0)
        if vertical > 80 or (overlap <= 0 and abs(x0 - label_rect.x0) > 140):
            continue
        rank = (vertical, -overlap)
        if best is None or rank < best[0]:
            best = (rank, x0, x1, y)
    if best:
        _, x0, x1, y = best
        top = max(8.0, y - 42.0)
        bottom = max(top + 20.0, y - 2.0)
        return fitz.Rect(x0 + 2, top, x1 - 2, bottom)

    width = min(190.0, max(105.0, page.rect.width * 0.30))
    if label_rect.x0 > page.rect.width * 0.55:
        x0 = max(8.0, min(page.rect.width - width - 8, label_rect.x0 - 8))
    else:
        x0 = max(8.0, min(page.rect.width - width - 8, label_rect.x0))
    y1 = max(50.0, label_rect.y0 - 4)
    y0 = max(8.0, y1 - 42.0)
    return fitz.Rect(x0, y0, x0 + width, y1)


def _fallback_detected_placements(source, roles, already=None):
    already = already or {}
    unresolved = [role for role in roles if role not in already]
    if not unresolved:
        return {}
    try:
        document = fitz.open(stream=source, filetype='pdf')
    except Exception:
        return {}
    candidates = []
    try:
        for page_index, page in enumerate(document):
            for row in _text_lines(page):
                if not _SIGNATURE_WORDS.search(row['text']):
                    continue
                label_rect = row['rect']
                context = fitz.Rect(
                    max(0, label_rect.x0 - 180), max(0, label_rect.y0 - 95),
                    min(page.rect.width, label_rect.x1 + 180), min(page.rect.height, label_rect.y1 + 95),
                )
                context_text = f"{row['text']} {page.get_textbox(context)}"
                rect = _candidate_rect(page, label_rect)
                candidates.append({
                    'page': page_index + 1,
                    'rect': rect,
                    'text': context_text,
                    'label': row['text'],
                })

        used = set()
        result = {}
        for role in unresolved:
            ranked = sorted(
                [(_role_score(item['text'], role), index, item) for index, item in enumerate(candidates) if index not in used],
                key=lambda item: item[0], reverse=True,
            )
            if not ranked:
                continue
            score, index, item = ranked[0]
            # A generic "Unterschrift" is still useful when there is only one unresolved
            # signature target. With multiple targets, require role context to avoid swaps.
            if score < 3 and len(unresolved) > 1:
                continue
            used.add(index)
            page = document[item['page'] - 1]
            rect = item['rect']
            result[role] = {
                'page': item['page'],
                'position': {
                    'x': rect.x0 / page.rect.width,
                    'y': rect.y0 / page.rect.height,
                    'width': rect.width / page.rect.width,
                    'height': rect.height / page.rect.height,
                },
                'source': 'pdf-signature-label',
                'confidence': 0.82 if score >= 4 else 0.62,
            }
        return result
    finally:
        document.close()


def _resolve_signature_placements(source, template, roles):
    """Resolve one signature rectangle per role, with template overrides first."""
    roles = [str(role) for role in roles]
    result = {role: value for role, value in _template_placements(template).items() if role in roles}
    unresolved = [role for role in roles if role not in result]
    if unresolved:
        result.update({role: value for role, value in _smartdocs_placements(source, unresolved).items() if role not in result})
    if any(role not in result for role in roles):
        detected = _fallback_detected_placements(source, roles, result)
        result.update({role: value for role, value in detected.items() if role not in result})
    return result


def _rect_from_placement(page, placement):
    position = placement.get('position') or {}
    x = float(position.get('x', 0) or 0)
    y = float(position.get('y', 0) or 0)
    width = float(position.get('width', 0.24) or 0.24)
    height = float(position.get('height', 0.055) or 0.055)
    if max(abs(x), abs(y), abs(width), abs(height)) <= 1.001:
        x *= page.rect.width
        y *= page.rect.height
        width *= page.rect.width
        height *= page.rect.height
    rect = fitz.Rect(x, y, x + width, y + height)
    return rect & page.rect


def _fallback_slots(document, signatures):
    page = document[-1]
    count = max(1, len(signatures))
    margin = 42.0
    gap = 18.0
    usable = max(120.0, page.rect.width - (2 * margin) - (gap * max(0, count - 1)))
    slot = usable / count
    top = max(8.0, page.rect.height - 92.0)
    result = {}
    for index, (signature, _) in enumerate(signatures):
        result[str(signature.role)] = {
            'page': len(document),
            'position': {
                'x': margin + index * (slot + gap), 'y': top,
                'width': max(70.0, slot - 8), 'height': 36.0,
            },
            'source': 'legacy-fallback',
            'confidence': 0.0,
        }
    return result


def stamp_drawn_signatures(contract):
    """Stamp drawn signatures at the real signature field for each document template.

    Placement order: explicit per-template schema coordinates, SmartDocs PDF layout
    detection, role-aware signature-label detection, then a last-resort legacy slot.
    Typed/legacy signatures remain untouched and signature hashes are unchanged.
    """
    if not contract.pdf:
        return False

    signatures = []
    for signature in contract.signatures.order_by('signed_at'):
        image = _image_bytes(signature.signature_data)
        if image:
            signatures.append((signature, image))
    if not signatures:
        return False

    contract.pdf.open('rb')
    try:
        source = contract.pdf.read()
    finally:
        contract.pdf.close()

    try:
        document = fitz.open(stream=source, filetype='pdf')
    except Exception:
        return False
    if document.page_count < 1:
        document.close()
        return False

    try:
        roles = [str(signature.role) for signature, _ in signatures]
        placements = _resolve_signature_placements(source, contract.template, roles)
        fallbacks = _fallback_slots(document, signatures)

        stamped = False
        for signature, image_bytes in signatures:
            role = str(signature.role)
            placement = placements.get(role) or fallbacks[role]
            page_index = max(0, min(document.page_count - 1, int(placement.get('page', 1)) - 1))
            page = document[page_index]
            rect = _rect_from_placement(page, placement)
            if rect.is_empty or rect.width < 12 or rect.height < 10:
                placement = fallbacks[role]
                page = document[-1]
                rect = _rect_from_placement(page, placement)
            try:
                page.insert_image(rect, stream=image_bytes, keep_proportion=True, overlay=True)
                stamped = True
            except Exception:
                continue

            if placement.get('source') == 'legacy-fallback':
                role_label = _ROLE_LABELS.get(signature.role, role)
                label_y = max(7.0, rect.y0 - 8.0)
                page.insert_text((rect.x0, label_y), role_label, fontsize=7, color=(0.35, 0.39, 0.45), overlay=True)

            # Keep signer identity as searchable/auditable text for every placement.
            name_y = min(page.rect.height - 5.0, rect.y1 + 9.0)
            page.insert_text((rect.x0, name_y), signature.signer_name[:70], fontsize=7, color=(0.15, 0.18, 0.22), overlay=True)

        if not stamped:
            return False
        output = document.tobytes(garbage=4, deflate=True)
    finally:
        document.close()

    filename = contract.pdf.name.rsplit('/', 1)[-1]
    contract.pdf.save(filename, ContentFile(output), save=False)
    contract.save(update_fields=['pdf', 'updated_at'])
    return True
