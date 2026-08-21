import hashlib
import json
import re
import unicodedata
import zipfile
from pathlib import Path

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .document_catalog import CATALOG_BY_SLUG, DOCUMENT_CATALOG
from .models import ContractTemplate


MANIFEST_NAME = '.source-manifest.json'
_DJANGO_COLLISION_SUFFIX = re.compile(r'_[A-Za-z0-9]{7}$')
_COPY_SUFFIX = re.compile(
    r'(?:\s*[\(\[]\s*\d+\s*[\)\]]|\s+(?:copy|kopie)(?:\s*\d+)?)$',
    re.IGNORECASE,
)


def _catalog_dir() -> Path:
    return Path(settings.MEDIA_ROOT) / 'contract_templates'


def _manifest_path() -> Path:
    return _catalog_dir() / MANIFEST_NAME


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _normalized_fingerprint(filename: str, *, strip_copy_suffix: bool) -> str:
    stem = Path(filename).stem.strip()
    while True:
        previous = stem
        stem = _DJANGO_COLLISION_SUFFIX.sub('', stem).strip()
        if strip_copy_suffix:
            stem = _COPY_SUFFIX.sub('', stem).strip()
        if stem == previous:
            break
    normalized = unicodedata.normalize('NFKD', stem).casefold()
    return ''.join(char for char in normalized if char.isalnum())


def _fingerprint(filename: str) -> str:
    """Match safe OS/browser copy names such as ``file (1).pdf`` to the canonical source.

    User uploads and browser downloads frequently gain ``(1)``, ``(2)`` or ``(7)``
    before the extension. Those bytes are still the supplied private source and must
    survive a database reset. Django's own seven-character collision suffix is also
    ignored. The stricter fingerprint below is retained so an exact canonical name
    can win over differing copies without guessing between legal documents.
    """
    return _normalized_fingerprint(filename, strip_copy_suffix=True)


def _strict_fingerprint(filename: str) -> str:
    return _normalized_fingerprint(filename, strip_copy_suffix=False)


def _relative_storage_name(path: Path) -> str:
    return path.resolve().relative_to(Path(settings.MEDIA_ROOT).resolve()).as_posix()


def _valid_source(path: Path, catalog: dict) -> bool:
    if not path.is_file() or path.stat().st_size <= 8:
        return False
    expected_suffix = Path(catalog.get('source_name') or '').suffix.lower()
    if expected_suffix and path.suffix.lower() != expected_suffix:
        return False
    try:
        if path.suffix.lower() == '.pdf':
            with path.open('rb') as handle:
                return handle.read(5) == b'%PDF-'
        if path.suffix.lower() == '.docx':
            with zipfile.ZipFile(path) as archive:
                names = set(archive.namelist())
                return '[Content_Types].xml' in names and 'word/document.xml' in names
    except (OSError, zipfile.BadZipFile):
        return False
    return True


def _read_manifest() -> dict:
    path = _manifest_path()
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError, TypeError):
        return {'version': 1, 'templates': {}}
    if not isinstance(payload, dict):
        return {'version': 1, 'templates': {}}
    templates = payload.get('templates')
    if not isinstance(templates, dict):
        templates = {}
    return {'version': 1, 'templates': templates}


def _write_manifest(payload: dict) -> None:
    directory = _catalog_dir()
    directory.mkdir(parents=True, exist_ok=True)
    target = _manifest_path()
    temporary = target.with_suffix('.tmp')
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding='utf-8')
    temporary.replace(target)


def source_exists(template: ContractTemplate) -> bool:
    if not template.source_file or not template.source_file.name:
        return False
    try:
        return bool(template.source_file.storage.exists(template.source_file.name))
    except Exception:
        try:
            return Path(template.source_file.path).is_file()
        except (NotImplementedError, ValueError, OSError):
            return False


def record_source_manifest(template: ContractTemplate) -> bool:
    if not template.slug or not source_exists(template):
        return False
    try:
        path = Path(template.source_file.path)
    except (NotImplementedError, ValueError, OSError):
        return False
    catalog = CATALOG_BY_SLUG.get(template.slug)
    if not catalog or not _valid_source(path, catalog):
        return False
    checksum = template.source_checksum or _sha256(path)
    payload = _read_manifest()
    payload['templates'][template.slug] = {
        'storage_name': template.source_file.name,
        'sha256': checksum,
        'source_name': catalog.get('source_name') or '',
    }
    _write_manifest(payload)
    return True


@receiver(post_save, sender=ContractTemplate)
def keep_private_source_manifest(sender, instance, **kwargs):
    if instance.source_file:
        record_source_manifest(instance)


def _candidate_files(catalog: dict) -> list[Path]:
    directory = _catalog_dir()
    if not directory.is_dir():
        return []
    expected = _fingerprint(catalog.get('source_name') or '')
    suffix = Path(catalog.get('source_name') or '').suffix.lower()
    candidates = []
    for path in directory.rglob('*'):
        if path.name == MANIFEST_NAME or not path.is_file():
            continue
        if suffix and path.suffix.lower() != suffix:
            continue
        if _fingerprint(path.name) != expected:
            continue
        if _valid_source(path, catalog):
            candidates.append(path)
    return sorted(candidates, key=lambda path: (path.stat().st_mtime_ns, path.name), reverse=True)


def _preferred_candidates(catalog: dict, candidates: list[Path]) -> list[Path]:
    """Prefer the canonical filename when copies with different bytes also exist.

    A canonical/sanitized source name is stronger evidence than ``(1)``/``(2)``
    copies. If no strict canonical candidate exists, all copy candidates remain in
    the pool and the checksum ambiguity guard below decides whether recovery is safe.
    """
    expected = _strict_fingerprint(catalog.get('source_name') or '')
    exact = [path for path in candidates if _strict_fingerprint(path.name) == expected]
    return exact or candidates


def _manifest_candidate(slug: str, catalog: dict, manifest: dict) -> Path | None:
    entry = manifest.get('templates', {}).get(slug)
    if not isinstance(entry, dict) or not entry.get('storage_name'):
        return None
    path = Path(settings.MEDIA_ROOT) / str(entry['storage_name'])
    if not _valid_source(path, catalog):
        return None
    expected_checksum = str(entry.get('sha256') or '').lower()
    if expected_checksum and _sha256(path).lower() != expected_checksum:
        return None
    return path


def _attach_existing_file(template: ContractTemplate, path: Path) -> None:
    template.source_file.name = _relative_storage_name(path)
    template.source_checksum = _sha256(path)
    template.save(update_fields=['source_file', 'source_checksum', 'updated_at'])


def recover_document_sources(slugs=None) -> dict:
    selected = set(slugs or [item['slug'] for item in DOCUMENT_CATALOG])
    manifest = _read_manifest()
    result = {
        'installed': 0,
        'recovered': 0,
        'missing': [],
        'ambiguous': [],
        'invalid': [],
    }

    for catalog in DOCUMENT_CATALOG:
        slug = catalog['slug']
        if slug not in selected:
            continue
        template = ContractTemplate.objects.filter(slug=slug).first()
        if template is None:
            result['missing'].append({'slug': slug, 'reason': 'catalog_record_missing'})
            continue

        if source_exists(template):
            try:
                current_path = Path(template.source_file.path)
            except (NotImplementedError, ValueError, OSError):
                current_path = None
            if current_path and _valid_source(current_path, catalog):
                checksum = _sha256(current_path)
                if template.source_checksum != checksum:
                    template.source_checksum = checksum
                    template.save(update_fields=['source_checksum', 'updated_at'])
                record_source_manifest(template)
                result['installed'] += 1
                continue
            result['invalid'].append({'slug': slug, 'file': template.source_file.name})

        # A stale FileField pointer is safe to detach, but its checksum is valuable
        # installed metadata and must not be destroyed just because the database no
        # longer knows where the persistent file lives. Successful recovery replaces
        # it with the checksum of the bytes that were actually reconnected.
        if template.source_file:
            template.source_file = None
            template.save(update_fields=['source_file', 'updated_at'])

        manifest_path = _manifest_candidate(slug, catalog, manifest)
        if manifest_path is not None:
            _attach_existing_file(template, manifest_path)
            result['recovered'] += 1
            continue

        candidates = _candidate_files(catalog)
        if not candidates:
            result['missing'].append({'slug': slug, 'source_name': catalog.get('source_name') or ''})
            continue

        preferred = _preferred_candidates(catalog, candidates)
        checksums = {_sha256(path) for path in preferred}
        if len(preferred) > 1 and len(checksums) > 1:
            result['ambiguous'].append({
                'slug': slug,
                'files': [_relative_storage_name(path) for path in preferred],
            })
            continue

        _attach_existing_file(template, preferred[0])
        result['recovered'] += 1

    expected_count = len(selected & set(CATALOG_BY_SLUG))
    result['complete'] = result['installed'] + result['recovered'] == expected_count
    result['expected'] = expected_count
    return result
