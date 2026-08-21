from __future__ import annotations


def install_smart_docx_renderer() -> None:
    """Install the formatting-safe DOCX renderer without changing contract APIs.

    The bridge is installed during Django app startup so every existing caller of
    document_engine.render_docx / generate_contract_files gets the upgraded
    renderer while the public function signatures stay backward-compatible.
    """
    from . import document_engine
    from .smart_docx import SmartDocxError, render_docx_template

    def render_docx(source_path, data):
        try:
            rendered, diagnostics = render_docx_template(source_path, data, document_engine.format_value)
        except SmartDocxError as exc:
            raise document_engine.DocumentGenerationError(str(exc)) from exc
        unresolved = diagnostics.get('unresolved_keys') or []
        if unresolved:
            labels = ', '.join(unresolved[:12])
            suffix = ' …' if len(unresolved) > 12 else ''
            raise document_engine.DocumentGenerationError(
                f'DOCX-Vorlage enthält unbekannte Platzhalter: {labels}{suffix}'
            )
        return rendered

    render_docx._smart_docx_renderer = True  # type: ignore[attr-defined]
    document_engine.render_docx = render_docx


__all__ = ['install_smart_docx_renderer']
