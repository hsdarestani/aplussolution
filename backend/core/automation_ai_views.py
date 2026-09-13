from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .ai_shift_normalizer import deterministic_order_request, normalize_order_request
from .native_cutover import approve_order
from .order_automation import extract_request_id, fallback_request_id, parse_order_text
from .permissions import IsAdminOrManager
from .services import audit


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def order_parse(request):
    raw_text = str(request.data.get('text') or '').strip()
    if not raw_text:
        return Response({'detail': 'Kein Auftragstext übergeben.'}, status=400)

    try:
        result = normalize_order_request(raw_text, parse_order_text(raw_text))
    except Exception as exc:
        # Explicit German shift instructions do not need to fail just because the
        # external AI provider is temporarily unavailable or interpreted fields
        # inconsistently. Deterministic parsing covers the common create-shift flow.
        result = deterministic_order_request(raw_text)
        if not result:
            return Response({'detail': str(exc)}, status=400)
        result = normalize_order_request(raw_text, result)

    if not result.get('shifts'):
        return Response({'detail': 'Im Text wurde keine vollständige Schicht erkannt.'}, status=400)

    contract_no = extract_request_id(raw_text, result)
    result['contract_no'] = contract_no
    result['request_id'] = contract_no or fallback_request_id(result, (result['shifts'][0].get('site_text') or ''))
    audit(request, 'order_automation.parsed', request.user, {
        'request_id': result.get('request_id'),
        'shift_count': sum(max(1, int(item.get('count') or 1)) for item in result.get('shifts', [])),
    })
    return Response(result)


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def order_approve(request):
    raw_text = str(request.data.get('raw_text') or '').strip()
    parsed = normalize_order_request(raw_text, request.data.get('parsed') or {})
    if not parsed.get('shifts'):
        fallback = deterministic_order_request(raw_text)
        if fallback:
            parsed = normalize_order_request(raw_text, fallback)
    try:
        result = approve_order(
            parsed,
            raw_text,
            actor=request.user,
            client_id=request.data.get('client_id') or None,
        )
    except Exception as exc:
        return Response({'detail': str(exc)}, status=400)
    audit(request, 'order_automation.approved', request.user, result)
    return Response(result)
