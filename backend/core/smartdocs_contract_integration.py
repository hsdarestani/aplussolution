from __future__ import annotations

import copy
import re
import tempfile
import unicodedata
from pathlib import Path
from typing import Any

import fitz
from django.core.files.base import ContentFile
from django.utils import timezone

from .models import Contract, ContractTemplate
from .smart_pdf_overlay import (
    SmartPdfOverlayError,
    _inline_candidates,
    _line_candidates,
    _norm,
    _score,
    _widget_candidates,
    analyse_pdf_template,
    render_smart_pdf_overlay,
)


# These values identify the legal parties on the first page. A contract PDF must
# never be marked as generated while these values are absent from the visible PDF.
CRITICAL_DOCX_FIELDS = {
    'company_name',
    'company_address',
    'employee_name',
    'employee_address',
}

_SKIP_TYPES = {'boolean', 'list', 'image', 'signature', 'unterschrift', 'kontrollfeld'}


def _normalise(value: Any) -> str:
    text = unicodedata.normalize('NFKD', str(value or '').casefold())
    text = ''.join(char for char in text if not unicodedata.combining(char)).replace('ß', 'ss')
    return re.sub(r'[^a-z0-9]+', '', text)


def _pdf_text(pdf_bytes: bytes) -> str:
    document = fitz.open(stream=pdf_bytes, filetype='pdf')
    try:
        return '\n'.join(page.get_text('text') for page in document)
    finally:
        document.close()


def _value_is_visible(pdf_text: str, value: Any, formatter) -> bool:
    expected = _normalise(formatter(value))
    if len(expected) < 2:
        return True
    return expected in _normalise(pdf_text)


def _missing_visible_fields(pdf_bytes: bytes, fields: list[dict[str, Any]], data: dict[str, Any], formatter) -> list[dict[str, Any]]:
    text = _pdf_text(pdf_bytes)
    missing: list[dict[str, Any]] = []
    for field in fields:
        name = str(field.get('name') or '').strip()
        if not name:
            continue
        field_type = str(field.get('type') or field.get('kind') or 'text').strip().lower()
        if field_type in _SKIP_TYPES:
            continue
        value = data.get(name)
        if value in (None, '', [], {}):
            continue
        if not _value_is_visible(text, value, formatter):
            missing.append(field)
    return missing


def _candidate_key(candidate: dict[str, Any]) -> tuple[Any, ...]:
    position = candidate.get('position') or {}
    return (
        int(candidate.get('page') or 1),
        str(candidate.get('source') or ''),
        _norm(candidate.get('label') or candidate.get('field_name') or ''),
        round(float(position.get('x') or 0), 4),
        round(float(position.get('y') or 0), 4),
    )


def _candidate_order(candidate: dict[str, Any]) -> tuple[float, float, float]:
    position = candidate.get('position') or {}
    return (
        float(candidate.get('page') or 1),
        float(position.get('y') or 0),
        float(position.get('x') or 0),
    )


def _collect_candidates(pdf_path: Path) -> list[dict[str, Any]]:
    document = fitz.open(pdf_path)
    candidates: list[dict[str, Any]] = []
    try:
        for page_number, page in enumerate(document, start=1):
            candidates.extend(_widget_candidates(page, page_number))
            candidates.extend(_line_candidates(page, page_number))
            candidates.extend(_inline_candidates(page, page_number))
    finally:
        document.close()
    return candidates


def _augment_ambiguous_layout(pdf_path: Path, fields: list[dict[str, Any]], analysis: dict[str, Any]) -> dict[str, Any]:
    """Resolve repeated generic German labels by document order.

    The supplied employment contract has e.g. two separate ``Anschrift`` lines.
    A label-only matcher correctly considers those ambiguous. SmartDocs resolves
    that ambiguity by keeping the schema order and the physical form order aligned:
    Firma -> Anschrift -> Name/Mitarbeiter -> Anschrift.
    """
    layout = copy.deepcopy(analysis)
    resolved = dict(layout.get('resolved_coordinates') or {})
    candidates = _collect_candidates(pdf_path)
    used = {_candidate_key(target) for target in resolved.values()}
    last_order: tuple[float, float, float] | None = None

    for field in fields:
        name = str(field.get('name') or '').strip()
        if not name:
            continue
        current = resolved.get(name)
        if current:
            current_order = _candidate_order(current)
            if last_order is None or current_order > last_order:
                last_order = current_order
            continue

        ranked: list[tuple[float, dict[str, Any]]] = []
        for candidate in candidates:
            if _candidate_key(candidate) in used:
                continue
            score = _score(field, candidate)
            if score >= 0.42:
                ranked.append((score, candidate))
        if not ranked:
            continue

        best_score = max(score for score, _ in ranked)
        near_best = [candidate for score, candidate in ranked if score >= best_score - 0.08]
        after = [candidate for candidate in near_best if last_order is None or _candidate_order(candidate) > last_order]
        pool = after or near_best
        chosen = min(pool, key=_candidate_order)
        confidence = round(min(1.0, best_score), 3)
        resolved[name] = {**copy.deepcopy(chosen), 'confidence': confidence, 'resolved_by': 'smartdocs-document-order'}
        used.add(_candidate_key(chosen))
        last_order = _candidate_order(chosen)

    diagnostics = []
    for field in fields:
        name = str(field.get('name') or '').strip()
        if not name:
            continue
        target = resolved.get(name)
        diagnostics.append({
            'field': name,
            'label': field.get('label') or name,
            'status': 'matched' if target else 'unmatched',
            'candidate': target.get('label') if target else None,
            'source': target.get('source') if target else None,
            'confidence': target.get('confidence') if target else 0,
            'resolved_by': target.get('resolved_by') if target else None,
        })
    layout['resolved_coordinates'] = resolved
    layout['diagnostics'] = diagnostics
    layout['matched_count'] = len(resolved)
    layout['field_count'] = len([field for field in fields if field.get('name')])
    layout['engine'] = 'smartdocs-layout-v2-docx-guard'
    return layout


def _smartdocs_fill_missing(pdf_bytes: bytes, missing_fields: list[dict[str, Any]], data: dict[str, Any], formatter) -> tuple[bytes, dict[str, Any]]:
    render_fields: list[dict[str, Any]] = []
    for field in missing_fields:
        cloned = copy.deepcopy(field)
        cloned['required'] = str(cloned.get('name') or '') in CRITICAL_DOCX_FIELDS
        render_fields.append(cloned)

    with tempfile.TemporaryDirectory() as tmp:
        pdf_path = Path(tmp) / 'smartdocs-contract.pdf'
        pdf_path.write_bytes(pdf_bytes)
        analysis = analyse_pdf_template(pdf_path, render_fields)
        analysis = _augment_ambiguous_layout(pdf_path, render_fields, analysis)
        try:
            return render_smart_pdf_overlay(
                pdf_path,
                render_fields,
                data,
                analysis=analysis,
                format_value=formatter,
            )
        except SmartPdfOverlayError as exc:
            raise ValueError(str(exc)) from exc


def _critical_missing(pdf_bytes: bytes, fields: list[dict[str, Any]], data: dict[str, Any], formatter) -> list[dict[str, Any]]:
    critical = [field for field in fields if str(field.get('name') or '') in CRITICAL_DOCX_FIELDS]
    return _missing_visible_fields(pdf_bytes, critical, data, formatter)


def install_smartdocs_contract_renderer() -> None:
    """Use SmartDocs as the DOCX contract safety net without changing API routes.

    Modern templates with ``{{field}}`` placeholders are still rendered by the
    formatting-safe DOCX renderer. Legacy legal templates containing printed blank
    lines are converted first and then populated on their real PDF baselines. This
    fixes the previous false-positive state where a visually empty PDF was saved as
    ``ready`` merely because LibreOffice successfully converted the file.
    """
    from . import document_engine

    current = document_engine.generate_contract_files
    if getattr(current, '_smartdocs_contract_renderer', False):
        return

    def generate_contract_files(contract, validate=True):
        if contract.template.source_format != ContractTemplate.SourceFormat.DOCX:
            return current(contract, validate=validate)

        data = document_engine.contract_data(contract)
        if validate:
            document_engine.validate_required_fields(contract.template, data)
        if not contract.template.source_file:
            raise document_engine.DocumentGenerationError(
                f'Quelldatei für „{contract.template.name}“ ist noch nicht installiert.'
            )

        source_path = contract.template.source_file.path
        docx_bytes = document_engine.render_docx(source_path, data)
        pdf_bytes = document_engine.convert_docx_to_pdf(docx_bytes)
        fields = list((contract.template.schema or {}).get('fields') or [])
        missing = _missing_visible_fields(pdf_bytes, fields, data, document_engine.format_value)

        if missing:
            try:
                pdf_bytes, layout = _smartdocs_fill_missing(pdf_bytes, missing, data, document_engine.format_value)
            except ValueError as exc:
                raise document_engine.DocumentGenerationError(f'SmartDocs: {exc}') from exc

            # Keep lightweight diagnostics in the immutable data snapshot; this is
            # enough to diagnose production templates without storing source files.
            data['_smartdocs_pdf'] = {
                'engine': layout.get('engine'),
                'matched_count': layout.get('matched_count'),
                'field_count': layout.get('field_count'),
                'placed_fields': layout.get('placed_fields') or [],
            }

        still_missing = _critical_missing(pdf_bytes, fields, data, document_engine.format_value)
        if still_missing:
            labels = ', '.join(str(field.get('label') or field.get('name')) for field in still_missing)
            raise document_engine.DocumentGenerationError(
                'SmartDocs konnte die Vertragsparteien nicht sicher in die PDF-Vorlage einsetzen: ' + labels
            )

        previous_status = contract.status
        contract.docx.save(
            f'{contract.template.slug}-{contract.id}.docx',
            ContentFile(docx_bytes),
            save=False,
        )
        contract.pdf.save(
            f'{contract.template.slug}-{contract.id}.pdf',
            ContentFile(pdf_bytes),
            save=False,
        )
        contract.data_snapshot = {key: document_engine.format_value(value) for key, value in data.items()}
        contract.generated_at = timezone.now()
        if previous_status == Contract.Status.SIGNED:
            contract.status = Contract.Status.SIGNED
        elif previous_status == Contract.Status.SENT:
            contract.status = Contract.Status.SENT
        else:
            contract.status = Contract.Status.READY
        contract.save()
        return contract

    generate_contract_files._smartdocs_contract_renderer = True  # type: ignore[attr-defined]
    generate_contract_files._wrapped_renderer = current  # type: ignore[attr-defined]
    document_engine.generate_contract_files = generate_contract_files


__all__ = ['CRITICAL_DOCX_FIELDS', 'install_smartdocs_contract_renderer']
