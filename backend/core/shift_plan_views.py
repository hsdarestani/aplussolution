from pathlib import Path

from django.http import FileResponse
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
        'download_url': f'/api/shift-plans/attachments/{attachment.id}/download/',
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
        rows = ShiftPlanAttachment.objects.filter(shift=shift).select_related('document').order_by('-created_at')
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

    document, _ = save_plan_document(payload, request.user, client=shift.client)
    attachment, created = attach_document(
        document,
        shift,
        request.user,
        score=255,
        reason='Manuell direkt dieser Schicht zugeordnet',
        automatic=False,
    )
    audit(request, 'shift_plan.attached', shift, {
        'document_id': str(document.id),
        'attachment_id': str(attachment.id),
        'filename': document.original_name,
        'created': created,
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


@api_view(['GET'])
def download_attachment(request, attachment_id):
    attachment = ShiftPlanAttachment.objects.select_related(
        'shift__client', 'shift__location', 'document'
    ).filter(pk=attachment_id).first()
    if not attachment:
        return Response({'detail': 'Plan wurde nicht gefunden.'}, status=404)
    if not can_view_shift_plan(request.user, attachment.shift):
        raise PermissionDenied('Dieser Plan ist für dein Konto nicht freigegeben.')

    document = attachment.document
    filename = Path(document.original_name or 'Einsatzplan.pdf').name
    try:
        file_handle = document.file.open('rb')
    except Exception:
        return Response({'detail': 'Die PDF-Datei ist aktuell nicht verfügbar.'}, status=404)
    return FileResponse(file_handle, as_attachment=True, filename=filename, content_type='application/pdf')
