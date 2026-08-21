from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path
from typing import Any, Callable

from lxml import etree


W_NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
XML_NS = 'http://www.w3.org/XML/1998/namespace'
W = f'{{{W_NS}}}'
PLACEHOLDER_RE = re.compile(
    r'\{\{\s*(?:(checkbox)\s*:\s*)?([A-Za-z0-9_.-]+)\s*\}\}',
    re.IGNORECASE,
)


class SmartDocxError(ValueError):
    pass


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value).strip().lower()
    if text in {'', '0', 'false', 'nein', 'no', 'off', 'none', 'null'}:
        return False
    if text in {'1', 'true', 'ja', 'yes', 'on', 'x', 'checked'}:
        return True
    return bool(text)


def _set_text(node: etree._Element, value: str) -> None:
    node.text = value
    space_key = f'{{{XML_NS}}}space'
    if value[:1].isspace() or value[-1:].isspace():
        node.set(space_key, 'preserve')
    elif space_key in node.attrib:
        del node.attrib[space_key]


def _replace_match(nodes: list[etree._Element], start: int, end: int, replacement: str) -> None:
    ranges: list[tuple[int, int, etree._Element]] = []
    cursor = 0
    for node in nodes:
        text = node.text or ''
        node_start = cursor
        node_end = cursor + len(text)
        ranges.append((node_start, node_end, node))
        cursor = node_end

    affected = [item for item in ranges if item[0] < end and item[1] > start]
    if not affected:
        return

    first_start, _, first = affected[0]
    last_start, _, last = affected[-1]
    first_text = first.text or ''
    last_text = last.text or ''
    local_start = max(0, start - first_start)
    local_end = max(0, end - last_start)

    if first is last:
        _set_text(first, first_text[:local_start] + replacement + first_text[local_end:])
        return

    _set_text(first, first_text[:local_start] + replacement)
    for _, _, node in affected[1:-1]:
        _set_text(node, '')
    _set_text(last, last_text[local_end:])


def _expand_line_breaks(text_node: etree._Element) -> None:
    text = text_node.text or ''
    normalized = text.replace('\r\n', '\n').replace('\r', '\n')
    if '\n' not in normalized:
        return
    parent = text_node.getparent()
    if parent is None or parent.tag != f'{W}r':
        _set_text(text_node, normalized.replace('\n', ' '))
        return

    parts = normalized.split('\n')
    _set_text(text_node, parts[0])
    insert_at = parent.index(text_node) + 1
    for part in parts[1:]:
        br = etree.Element(f'{W}br')
        parent.insert(insert_at, br)
        insert_at += 1
        new_text = etree.Element(f'{W}t')
        _set_text(new_text, part)
        parent.insert(insert_at, new_text)
        insert_at += 1


def _render_paragraph(paragraph: etree._Element, values: dict[str, Any], formatter: Callable[[Any], str]) -> int:
    nodes = list(paragraph.iter(f'{W}t'))
    if not nodes:
        return 0
    combined = ''.join(node.text or '' for node in nodes)
    matches = list(PLACEHOLDER_RE.finditer(combined))
    replaced = 0
    for match in reversed(matches):
        checkbox, key = match.groups()
        if key not in values:
            continue
        if checkbox:
            replacement = '☒' if _truthy(values.get(key)) else '☐'
        else:
            replacement = formatter(values.get(key))
        _replace_match(nodes, match.start(), match.end(), replacement)
        replaced += 1

    for node in list(paragraph.iter(f'{W}t')):
        _expand_line_breaks(node)
    return replaced


def _is_word_xml_part(name: str) -> bool:
    if name == 'word/document.xml':
        return True
    if re.fullmatch(r'word/(?:header|footer)\d+\.xml', name):
        return True
    return name in {'word/footnotes.xml', 'word/endnotes.xml'}


def render_docx_bytes(source_bytes: bytes, values: dict[str, Any], formatter: Callable[[Any], str]) -> tuple[bytes, dict[str, Any]]:
    if not source_bytes:
        raise SmartDocxError('Die DOCX-Vorlage ist leer.')

    try:
        source_zip = zipfile.ZipFile(io.BytesIO(source_bytes), 'r')
    except zipfile.BadZipFile as exc:
        raise SmartDocxError('Die Vorlage ist kein gültiges DOCX-Dokument.') from exc

    output = io.BytesIO()
    replaced_total = 0
    processed_parts: list[str] = []
    unresolved: set[str] = set()

    with source_zip, zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as target_zip:
        for info in source_zip.infolist():
            content = source_zip.read(info.filename)
            if not _is_word_xml_part(info.filename):
                target_zip.writestr(info, content)
                continue
            try:
                root = etree.fromstring(content)
            except etree.XMLSyntaxError as exc:
                raise SmartDocxError(f'DOCX-XML konnte nicht gelesen werden: {info.filename}') from exc

            before = ''.join(root.itertext())
            for match in PLACEHOLDER_RE.finditer(before):
                if match.group(2) not in values:
                    unresolved.add(match.group(2))

            part_replacements = 0
            for paragraph in root.iter(f'{W}p'):
                part_replacements += _render_paragraph(paragraph, values, formatter)
            replaced_total += part_replacements
            if part_replacements:
                processed_parts.append(info.filename)
            rendered = etree.tostring(root, encoding='UTF-8', xml_declaration=True, standalone=True)
            target_zip.writestr(info, rendered)

    return output.getvalue(), {
        'replacements': replaced_total,
        'processed_parts': processed_parts,
        'unresolved_keys': sorted(unresolved),
    }


def render_docx_template(source_path: str | Path, values: dict[str, Any], formatter: Callable[[Any], str]) -> tuple[bytes, dict[str, Any]]:
    path = Path(source_path)
    if not path.exists():
        raise SmartDocxError('Die DOCX-Quelldatei wurde nicht gefunden.')
    return render_docx_bytes(path.read_bytes(), values, formatter)


__all__ = ['SmartDocxError', 'render_docx_bytes', 'render_docx_template']
