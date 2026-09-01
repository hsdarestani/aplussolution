from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from .order_file_import import approve_document_orders, extract_order_document, parse_order_document
from .permissions import IsAdminOrManager
from .services import audit


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
@parser_classes([MultiPartParser, FormParser])
def parse_order_file(request):
    try:
        document = extract_order_document(request.FILES.get('file'))
        result = parse_order_document(document)
    except Exception as exc:
        return Response({'detail': str(exc)}, status=400)
    audit(request, 'order_automation.file_parsed', request.user, {
        'file_name': result.get('file_name'),
        'page_count': result.get('page_count'),
        'order_count': result.get('order_count'),
        'shift_count': result.get('shift_count'),
        'staff_slots': result.get('staff_slots'),
    })
    return Response(result)


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def approve_order_file(request):
    orders = request.data.get('orders') or []
    if not isinstance(orders, list) or not orders:
        return Response({'detail': 'Bitte mindestens einen erkannten Auftrag auswählen.'}, status=400)
    try:
        result = approve_document_orders(
            orders,
            actor=request.user,
            client_id=request.data.get('client_id') or None,
        )
    except Exception as exc:
        return Response({'detail': str(exc)}, status=400)
    audit(request, 'order_automation.file_approved', request.user, {
        'status': result.get('status'),
        'imported_orders': result.get('imported_orders'),
        'published_orders': result.get('published_orders'),
        'draft_orders': result.get('draft_orders'),
        'created_staff_slots': result.get('created_staff_slots'),
        'errors': result.get('errors'),
    })
    status_code = 200 if result.get('results') else 400
    return Response(result, status=status_code)
