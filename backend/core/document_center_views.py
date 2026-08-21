from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .document_catalog import CATALOG_BY_SLUG
from .document_center import (
    DocumentCenterError,
    contract_readiness,
    dispatch_contract_reminders,
    document_center_overview,
    install_template_source,
)
from .document_source import InvalidTemplateSource, validate_template_source
from .models import Contract, ContractTemplate, User
from .permissions import IsAdminOrManager
from .services import audit
from .smart_pdf_overlay import analyse_pdf_template


def _visible_contract(request, pk):
    queryset = Contract.objects.select_related(
        'template', 'worker__user', 'client'
    ).prefetch_related('client__contacts', 'signatures')
    if request.user.role in {User.Role.ADMIN, User.Role.MANAGER}:
        return queryset.filter(pk=pk).first()
    if request.user.role == User.Role.WORKER:
        return queryset.filter(pk=pk, worker__user=request.user).first()
    if request.user.role == User.Role.CLIENT:
        return queryset.filter(pk=pk, client__contacts=request.user, client__contract_visibility_enabled=True).first()
    return None


@api_view(['GET'])
@permission_classes([IsAdminOrManager])
def document_center(request):
    return Response(document_center_overview())


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def contract_readiness_view(request, pk):
    contract = _visible_contract(request, pk)
    if not contract:
        return Response({'detail': 'Vertrag wurde nicht gefunden.'}, status=404)
    return Response(contract_readiness(contract))


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def upload_template_source(request, slug):
    upload = request.FILES.get('file')
    if not upload:
        return Response({'detail': 'Quelldatei fehlt.'}, status=400)
    catalog = CATALOG_BY_SLUG.get(slug)
    if not catalog:
        return Response({'detail': 'Unbekannte Dokumentvorlage.'}, status=404)
    try:
        validate_template_source(upload, catalog['source_format'])
        state = install_template_source(slug, upload, request.data.get('version'))
        if catalog['source_format'] == ContractTemplate.SourceFormat.PDF_OVERLAY:
            template = ContractTemplate.objects.get(slug=slug)
            schema = dict(template.schema or {})
            overlay = dict(schema.get('overlay') or {})
            analysis = analyse_pdf_template(template.source_file.path, list(schema.get('fields') or []))
            analysis['source_checksum'] = template.source_checksum
            overlay['smart_layout'] = analysis
            schema['overlay'] = overlay
            template.schema = schema
            template.save(update_fields=['schema', 'updated_at'])
            state['smart_layout'] = {
                'engine': analysis.get('engine'),
                'matched_count': analysis.get('matched_count', 0),
                'field_count': analysis.get('field_count', 0),
                'candidate_count': analysis.get('candidate_count', 0),
                'unmatched_fields': [
                    row.get('field') for row in analysis.get('diagnostics', [])
                    if row.get('status') == 'unmatched'
                ],
            }
    except (DocumentCenterError, InvalidTemplateSource) as exc:
        return Response({'detail': str(exc)}, status=400)
    audit(request, 'document_template.source_installed', request.user, {
        'slug': slug,
        'filename': upload.name,
        'checksum': state['source_checksum'],
        'version': state['version'],
        'smart_layout': state.get('smart_layout'),
    })
    return Response(state)


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def run_contract_reminders(request):
    result = dispatch_contract_reminders()
    audit(request, 'contract.reminders_dispatched', request.user, result)
    return Response(result)
