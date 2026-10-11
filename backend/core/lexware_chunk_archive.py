"""Authenticated resumable chunk upload for large annual Lexware PDF evidence.

Small requests prevent large PDFs from exhausting Gunicorn request workers.
Only archive-only payroll PDFs are accepted; no pay calculations or shifts
are touched. Staging files are outside MEDIA_ROOT and not web-served.
"""
import fcntl
import math
import re
import tempfile
import time
import uuid
from pathlib import Path

from django.core import signing
from django.core.files import File
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from .models import Document
from .payroll_views import _archive_lexware_upload, _lexware_document_kind
from .permissions import IsAdminOrManager


CHUNK_SIZE = 2 * 1024 * 1024
MAX_FILE_SIZE = 150 * 1024 * 1024
SIGN_SALT = 'lexware-large-pdf-v1'
STAGING_DIR = Path(tempfile.gettempdir()) / 'aplus-private-lexware-uploads'
ALLOWED_KINDS = {
    'lohnkonto', 'lohnkonto_uv', 'lohnsteuerbescheinigungen',
    'lohnjournal', 'meldebescheinigungen',
}


def _payload(request):
    try:
        data = signing.loads(str(request.data.get('upload_token') or ''), salt=SIGN_SALT, max_age=7200)
        if str(data.get('user_id')) != str(request.user.pk):
            return None
        uuid.UUID(str(data['id']))
        return data
    except (signing.BadSignature, ValueError, KeyError, TypeError):
        return None


def _staging_path(session_id):
    return STAGING_DIR / f'{session_id}.part'


def _cleanup_old_parts():
    STAGING_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    cutoff = time.time() - 3 * 3600
    for path in STAGING_DIR.glob('*.part'):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
        except OSError:
            pass


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def lexware_archive_begin(request):
    filename = str(request.data.get('filename') or '').strip()
    period = str(request.data.get('period') or '').strip()
    try:
        size = int(request.data.get('size') or 0)
    except (ValueError, TypeError):
        size = 0
    if (
        not re.fullmatch(r'20\d{2}-(0[1-9]|1[0-2])', period)
        or not filename or len(filename) > 200
        or Path(filename).name != filename or '\\' in filename
        or not filename.lower().endswith('.pdf')
        or _lexware_document_kind(filename) not in ALLOWED_KINDS
        or not 0 < size <= MAX_FILE_SIZE
    ):
        return Response({'detail': 'Nur große Lexware Jahresnachweise als PDF (maximal 150 MB) sind erlaubt.'}, status=400)
    _cleanup_old_parts()
    session_id = str(uuid.uuid4())
    path = _staging_path(session_id)
    with path.open('xb') as handle:
        handle.write(b'')
    data = {
        'id': session_id, 'filename': filename, 'period': period,
        'size': size, 'user_id': str(request.user.pk),
    }
    return Response({
        'upload_token': signing.dumps(data, salt=SIGN_SALT),
        'chunk_size': CHUNK_SIZE,
        'chunks': math.ceil(size / CHUNK_SIZE),
    })


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
@parser_classes([MultiPartParser, FormParser])
def lexware_archive_chunk(request):
    data = _payload(request)
    if not data:
        return Response({'detail': 'Upload Sitzung ungültig oder abgelaufen.'}, status=400)
    try:
        index = int(request.data.get('index', -1))
    except (TypeError, ValueError):
        index = -1
    total = int(data['size'])
    count = math.ceil(total / CHUNK_SIZE)
    if index < 0 or index >= count:
        return Response({'detail': 'Ungültiger Teilindex.'}, status=400)
    part = request.FILES.get('chunk')
    expected = min(CHUNK_SIZE, total - index * CHUNK_SIZE)
    if part is None or part.size != expected:
        return Response({'detail': 'Ein Dateiteil fehlt oder hat die falsche Größe.'}, status=400)
    path = _staging_path(data['id'])
    try:
        with path.open('r+b') as dest:
            fcntl.flock(dest.fileno(), fcntl.LOCK_EX)
            offset = index * CHUNK_SIZE
            dest.seek(0, 2)
            current = dest.tell()
            if current == offset:
                dest.seek(offset)
                for fragment in part.chunks():
                    dest.write(fragment)
            elif current == offset + expected:
                dest.seek(offset)
                if dest.read(expected) != part.read():
                    return Response({'detail': 'Dieser Dateiteil widerspricht einem bereits gespeicherten Teil.'}, status=409)
            else:
                return Response({'detail': 'Dateiteile müssen in der richtigen Reihenfolge gesendet werden.'}, status=409)
            dest.flush()
    except (OSError, ValueError):
        return Response({'detail': 'Zwischenspeicherung fehlgeschlagen. Erneut versuchen.'}, status=503)
    return Response({'received': index + 1, 'chunks': count})


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def lexware_archive_finish(request):
    data = _payload(request)
    if not data:
        return Response({'detail': 'Upload Sitzung ungültig oder abgelaufen.'}, status=400)
    path = _staging_path(data['id'])
    try:
        if path.stat().st_size != int(data['size']):
            return Response({'detail': 'PDF ist noch nicht vollständig hochgeladen.'}, status=409)
        with path.open('rb') as file:
            if file.read(5) != b'%PDF-':
                return Response({'detail': 'Datei ist kein gültiger PDF Upload.'}, status=400)
            file.seek(0)
            archived_title = _archive_lexware_upload(
                File(file, name=data['filename']), data['period'], request.user
            )
    except (OSError, ValueError):
        return Response({'detail': 'Jahresnachweis konnte nicht gespeichert werden. Es wurden keine Lohndaten verändert.'}, status=503)
    if archived_title is None:
        title = f"Lexware {data['period']} · {data['filename']}"[:250]
        if not Document.objects.filter(folder=Document.Folder.PAYROLL, title=title).exists():
            return Response({'detail': 'Archivierung konnte nicht bestätigt werden.'}, status=503)
    try:
        path.unlink()
    except OSError:
        pass
    return Response({
        'status': 'archived' if archived_title else 'already_archived',
        'filename': data['filename'],
        'period': data['period'],
        'payroll_records_modified': False,
    })
