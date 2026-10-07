import base64
from html import escape
from pathlib import Path

import fitz
from django.http import FileResponse, HttpResponse
from rest_framework.decorators import api_view
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from .client_portal_access import get_client_portal_access
from .models import Shift, User
from .services import audit
from .shift_plan_models import ShiftPlanAttachment, ShiftPlanDocument
from .shift_plan_service import (
    MAX_BULK_FILES,
    attach_document,
    can_upload_shift_plan,
    can_view_plan_attachment,
    can_view_shift_plan,
    candidate_shifts_for_upload,
    document_payload,
    extract_pdf_payload,
    process_bulk_pdf,
    save_plan_document,
    shift_summary,
)


def attachment_payload(request, attachment):
    document = attachment.document
    return {
        'id': str(attachment.id),
        'document_id': str(document.id),
        'name': document.original_name,
        'event_numbers': document.extracted_event_numbers,
        'event_dates': document.extracted_event_dates,
        'created_at': attachment.created_at,
        'matched_automatically': attachment.matched_automatically,
        'match_score': attachment.match_score,
        'match_reason': attachment.match_reason,
        'visibility': attachment.visibility,
        'target_worker_id': str(attachment.target_worker_id) if attachment.target_worker_id else None,
        'target_worker_name': (
            attachment.target_worker.user.get_full_name() or attachment.target_worker.user.email
            if attachment.target_worker_id else ''
        ),
        'view_url': f'/api/shift-plans/attachments/{attachment.id}/view/',
        'download_url': f'/api/shift-plans/attachments/{attachment.id}/download/',
        'delete_url': f'/api/shift-plans/attachments/{attachment.id}/',
    }


def _shift_or_404(pk):
    return Shift.objects.select_related('client', 'location', 'position', 'order').filter(pk=pk).first()


@api_view(['GET', 'POST'])
def shift_plans(request, shift_id):
    shift = _shift_or_404(shift_id)
    if not shift:
        return Response({'detail': 'Schicht wurde nicht gefunden.'}, status=404)

    if request.method == 'GET':
        if not can_view_shift_plan(request.user, shift):
            raise PermissionDenied('Für diese Schicht dürfen keine Pläne angezeigt werden.')
        rows = ShiftPlanAttachment.objects.filter(shift=shift).select_related(
            'document', 'target_worker__user'
        ).order_by('-created_at')
        if request.user.role == User.Role.WORKER:
            rows = [item for item in rows if can_view_plan_attachment(request.user, item)]
        return Response([attachment_payload(request, item) for item in rows])

    if not can_upload_shift_plan(request.user, shift):
        raise PermissionDenied('Für diese Schicht dürfen keine Pläne hochgeladen werden.')

    upload = request.FILES.get('file')
    if not upload:
        return Response({'detail': 'Bitte eine PDF-Datei auswählen.'}, status=400)
    try:
        payload = extract_pdf_payload(upload)
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=400)

    visibility = str(request.data.get('visibility') or ShiftPlanAttachment.Visibility.ALL).strip().lower()
    target_worker = None
    if visibility == ShiftPlanAttachment.Visibility.WORKER:
        worker_id = str(request.data.get('target_worker') or '').strip()
        slot = shift.slots.select_related('worker__user').filter(
            worker_id=worker_id,
            status='claimed',
            worker__isnull=False,
        ).first()
        if not slot:
            return Response({'detail': 'Bitte einen zugewiesenen Mitarbeiter auswählen.'}, status=400)
        target_worker = slot.worker
    else:
        visibility = ShiftPlanAttachment.Visibility.ALL

    document, _ = save_plan_document(payload, request.user, client=shift.client)
    attachment, created = attach_document(
        document,
        shift,
        request.user,
        score=255,
        reason='Manuell direkt dieser Schicht zugeordnet',
        automatic=False,
        visibility=visibility,
        target_worker=target_worker,
    )
    audit(request, 'shift_plan.attached', shift, {
        'document_id': str(document.id),
        'attachment_id': str(attachment.id),
        'filename': document.original_name,
        'created': created,
        'visibility': attachment.visibility,
        'target_worker': str(attachment.target_worker_id) if attachment.target_worker_id else None,
    })
    return Response(attachment_payload(request, attachment), status=201 if created else 200)


@api_view(['POST'])
def bulk_upload(request):
    if request.user.role not in {User.Role.ADMIN, User.Role.MANAGER, User.Role.CLIENT}:
        raise PermissionDenied('Nur Administration und Kunden dürfen Einsatzpläne hochladen.')
    if request.user.role == User.Role.CLIENT:
        access, _ = get_client_portal_access(request.user)
        if access and access.read_only:
            raise PermissionDenied('Dieser Kundenzugang ist schreibgeschützt.')

    uploads = request.FILES.getlist('files')
    if not uploads:
        single = request.FILES.get('file')
        uploads = [single] if single else []
    if not uploads:
        return Response({'detail': 'Bitte mindestens eine PDF-Datei auswählen.'}, status=400)
    if len(uploads) > MAX_BULK_FILES:
        return Response({'detail': f'Pro Upload sind maximal {MAX_BULK_FILES} PDF-Dateien erlaubt.'}, status=400)

    results = []
    for upload in uploads:
        try:
            item = process_bulk_pdf(upload, request.user)
            results.append({'name': getattr(upload, 'name', 'Einsatzplan.pdf'), **item})
        except ValueError as exc:
            results.append({
                'name': getattr(upload, 'name', 'Einsatzplan.pdf'),
                'status': 'error',
                'detail': str(exc),
                'matched': [],
                'candidates': [],
            })
        except Exception:
            results.append({
                'name': getattr(upload, 'name', 'Einsatzplan.pdf'),
                'status': 'error',
                'detail': 'Die Datei konnte nicht verarbeitet werden.',
                'matched': [],
                'candidates': [],
            })

    matched_count = sum(len(item.get('matched') or []) for item in results)
    audit(request, 'shift_plan.bulk_uploaded', request.user, {
        'files': len(results),
        'matched_attachments': matched_count,
    })
    return Response({
        'files': results,
        'matched_attachments': matched_count,
        'needs_review': sum(1 for item in results if item.get('status') == 'needs_review'),
        'errors': sum(1 for item in results if item.get('status') == 'error'),
    })


@api_view(['POST'])
def manual_attach_document(request, document_id):
    if request.user.role not in {User.Role.ADMIN, User.Role.MANAGER, User.Role.CLIENT}:
        raise PermissionDenied('Diese Funktion ist nicht verfügbar.')

    document = ShiftPlanDocument.objects.filter(pk=document_id).first()
    if not document:
        return Response({'detail': 'Plan wurde nicht gefunden.'}, status=404)
    shift = _shift_or_404(request.data.get('shift'))
    if not shift:
        return Response({'detail': 'Schicht wurde nicht gefunden.'}, status=404)
    if not can_upload_shift_plan(request.user, shift):
        raise PermissionDenied('Der Plan darf dieser Schicht nicht zugeordnet werden.')

    # A client may only use documents they uploaded or documents already linked
    # to their own company. This prevents cross-customer document discovery.
    if request.user.role == User.Role.CLIENT:
        _, company = get_client_portal_access(request.user)
        if document.client_id and document.client_id != company.id:
            raise PermissionDenied('Dieser Plan gehört zu einem anderen Kunden.')
        if document.uploaded_by_id and document.uploaded_by_id != request.user.id and not document.attachments.filter(shift__client=company).exists():
            raise PermissionDenied('Dieser Plan kann nicht verwendet werden.')

    attachment, created = attach_document(
        document,
        shift,
        request.user,
        score=0,
        reason='Nach Bulk-Upload manuell geprüft und zugeordnet',
        automatic=False,
    )
    audit(request, 'shift_plan.manually_matched', shift, {
        'document_id': str(document.id),
        'attachment_id': str(attachment.id),
    })
    return Response(attachment_payload(request, attachment), status=201 if created else 200)


def _attachment_or_404(attachment_id):
    return ShiftPlanAttachment.objects.select_related(
        'shift__client',
        'shift__location',
        'shift__position',
        'document',
        'target_worker__user',
    ).filter(pk=attachment_id).first()


def _pdf_preview_html(document, filename):
    """Render an authenticated PDF as self-contained HTML for mobile WebViews.

    iOS WKWebView promotes raw PDFs to its native PDF controller. That controller
    sits above the app UI, which is why our own close and zoom controls cannot
    reliably receive touches. Rendering the preview to page images keeps the
    document inside the app's iframe while the download endpoint still returns
    the untouched original PDF.
    """
    file_handle = document.file.open('rb')
    try:
        pdf_bytes = file_handle.read()
    finally:
        file_handle.close()

    pages = []
    with fitz.open(stream=pdf_bytes, filetype='pdf') as pdf:
        for page_number, page in enumerate(pdf, start=1):
            pixmap = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0), alpha=False)
            encoded = base64.b64encode(pixmap.tobytes('png')).decode('ascii')
            pages.append(
                f'<section class="page"><img alt="Seite {page_number}" '
                f'src="data:image/png;base64,{encoded}"></section>'
            )

    safe_name = escape(filename)
    pages_html = ''.join(pages) or '<p class="empty">Keine Seiten gefunden.</p>'
    html = f"""<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=5,user-scalable=yes,viewport-fit=cover">
<title>{safe_name}</title>
<style>
html,body{{margin:0;width:100%;height:100%;background:#e9edf2;color:#173f74;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
body{{display:grid;grid-template-rows:auto minmax(0,1fr);overflow:hidden}}
.toolbar{{position:relative;z-index:5;display:flex;align-items:center;justify-content:space-between;gap:8px;padding:max(8px,env(safe-area-inset-top)) 10px 8px;background:#fff;border-bottom:1px solid rgba(23,63,116,.12)}}
.name{{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:13px;font-weight:700}}
.zoom{{display:flex;align-items:center;gap:5px;flex:0 0 auto}}
.zoom button{{border:1px solid rgba(23,63,116,.12);background:#f5f7fa;color:#173f74;border-radius:9px;min-width:40px;height:40px;font:inherit;font-weight:800;font-size:16px}}
.zoom button.value{{min-width:58px;font-size:12px}}
.viewer{{overflow:auto;-webkit-overflow-scrolling:touch;overscroll-behavior:contain;padding:12px;touch-action:pan-x pan-y pinch-zoom}}
.page{{display:flex;justify-content:center;margin:0 auto 12px;min-width:100%}}
.page img{{display:block;width:100%;height:auto;max-width:none;background:#fff;box-shadow:0 3px 14px rgba(0,0,0,.16);transform-origin:top left}}
.empty{{padding:20px}}
</style>
</head>
<body>
<header class="toolbar">
  <div class="name">{safe_name}</div>
  <div class="zoom" aria-label="PDF Zoom">
    <button type="button" id="minus" aria-label="Verkleinern">−</button>
    <button type="button" id="reset" class="value" aria-label="Zoom zurücksetzen">100%</button>
    <button type="button" id="plus" aria-label="Vergrößern">+</button>
  </div>
</header>
<main class="viewer" id="viewer">{pages_html}</main>
<script>
(() => {{
  let zoom = 1;
  const images = Array.from(document.querySelectorAll('.page img'));
  const value = document.getElementById('reset');
  const apply = () => {{
    images.forEach((image) => image.style.width = Math.round(zoom * 100) + '%');
    value.textContent = Math.round(zoom * 100) + '%';
    document.getElementById('minus').disabled = zoom <= .75;
    document.getElementById('plus').disabled = zoom >= 3;
  }};
  document.getElementById('minus').addEventListener('click', () => {{ zoom = Math.max(.75, zoom - .25); apply(); }});
  document.getElementById('plus').addEventListener('click', () => {{ zoom = Math.min(3, zoom + .25); apply(); }});
  value.addEventListener('click', () => {{ zoom = 1; apply(); }});
  apply();
}})();
</script>
</body>
</html>"""
    response = HttpResponse(html, content_type='text/html; charset=utf-8')
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    return response


def _pdf_response(request, attachment_id, as_attachment):
    attachment = _attachment_or_404(attachment_id)
    if not attachment:
        return Response({'detail': 'Plan wurde nicht gefunden.'}, status=404)
    if not can_view_plan_attachment(request.user, attachment):
        raise PermissionDenied('Dieser Plan ist für dein Konto nicht freigegeben.')

    document = attachment.document
    filename = Path(document.original_name or 'Einsatzplan.pdf').name

    if not as_attachment:
        try:
            return _pdf_preview_html(document, filename)
        except Exception:
            return Response({'detail': 'Die PDF Vorschau konnte nicht erstellt werden.'}, status=500)

    try:
        file_handle = document.file.open('rb')
    except Exception:
        return Response({'detail': 'Die PDF Datei ist aktuell nicht verfügbar.'}, status=404)
    return FileResponse(
        file_handle,
        as_attachment=True,
        filename=filename,
        content_type='application/pdf',
    )


@api_view(['GET'])
def view_attachment(request, attachment_id):
    return _pdf_response(request, attachment_id, as_attachment=False)


@api_view(['GET'])
def download_attachment(request, attachment_id):
    return _pdf_response(request, attachment_id, as_attachment=True)


@api_view(['DELETE'])
def delete_attachment(request, attachment_id):
    attachment = _attachment_or_404(attachment_id)
    if not attachment:
        return Response({'detail': 'Plan wurde nicht gefunden.'}, status=404)
    if not can_upload_shift_plan(request.user, attachment.shift):
        raise PermissionDenied('Dieser Plan darf nicht gelöscht werden.')

    document = attachment.document
    shift = attachment.shift
    document_id = str(document.id)
    filename = document.original_name
    attachment.delete()
    if not document.attachments.exists():
        try:
            document.file.delete(save=False)
        except Exception:
            pass
        document.delete()

    audit(request, 'shift_plan.deleted', shift, {
        'document_id': document_id,
        'filename': filename,
    })
    return Response(status=204)
