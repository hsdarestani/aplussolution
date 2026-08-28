from pathlib import Path

path = Path('backend/core/signature_pdf.py')
text = path.read_text(encoding='utf-8')
old = """            if placement.get('source') == 'legacy-fallback':\n                role_label = _ROLE_LABELS.get(signature.role, role)\n                label_y = max(7.0, rect.y0 - 8.0)\n                page.insert_text((rect.x0, label_y), role_label, fontsize=7, color=(0.35, 0.39, 0.45), overlay=True)\n\n            # Keep signer identity as searchable/auditable text for every placement.\n            name_y = min(page.rect.height - 5.0, rect.y1 + 9.0)\n            page.insert_text((rect.x0, name_y), signature.signer_name[:70], fontsize=7, color=(0.15, 0.18, 0.22), overlay=True)\n"""
new = """            # Preserve the canonical signer role and identity as searchable/auditable\n            # text for every placement. Avoid duplicating a role label that the form\n            # already prints itself.\n            role_label = _ROLE_LABELS.get(signature.role, role)\n            existing_text = (page.get_text('text') or '').lower()\n            if role_label.lower() not in existing_text:\n                label_y = max(7.0, rect.y0 - 8.0)\n                page.insert_text((rect.x0, label_y), role_label, fontsize=7, color=(0.35, 0.39, 0.45), overlay=True)\n\n            name_y = min(page.rect.height - 5.0, rect.y1 + 9.0)\n            page.insert_text((rect.x0, name_y), signature.signer_name[:70], fontsize=7, color=(0.15, 0.18, 0.22), overlay=True)\n"""
if old not in text:
    raise SystemExit('Expected signature audit block not found')
path.write_text(text.replace(old, new, 1), encoding='utf-8')
print('Phase 8 signature audit labels fixed.')
