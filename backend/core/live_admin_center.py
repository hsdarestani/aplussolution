from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from . import admin_center_views as base


@api_view(['GET'])
def admin_exception_center(request):
    """Serve the live post-cutover exception inbox.

    WIW IDs remain on real workers and shifts for audit/traceability after the
    cutover, so the mere presence of a WIW ID must not hide an otherwise native
    operational exception. The base collector owns the narrow exclusions that
    are actually historical-only: imported WIW time rows, migration-only
    ``@sync.invalid`` worker shells, and disabled-WIW integration noise.
    """
    denied = base._manager_required(request)
    if denied:
        return denied

    items = base._exception_center_items(timezone.now())

    category = str(request.GET.get('category') or '').strip()
    severity = str(request.GET.get('severity') or '').strip()
    query = str(request.GET.get('q') or '').strip().lower()
    if category and category != 'all':
        allowed = {part.strip() for part in category.split(',') if part.strip()}
        items = [item for item in items if item['category'] in allowed]
    if severity and severity != 'all':
        allowed = {part.strip() for part in severity.split(',') if part.strip()}
        items = [item for item in items if item['severity'] in allowed]
    if query:
        items = [
            item for item in items
            if query in f"{item['title']} {item['message']} {item['category']}".lower()
        ]

    summary = {
        'total': len(items),
        'critical': sum(item['severity'] == 'critical' for item in items),
        'warning': sum(item['severity'] == 'warning' for item in items),
        'info': sum(item['severity'] == 'info' for item in items),
        'by_category': {
            category_name: sum(item['category'] == category_name for item in items)
            for category_name in ['staffing', 'attendance', 'contracts', 'documents', 'integrations', 'requests']
        },
    }
    try:
        limit = min(200, max(1, int(request.GET.get('limit') or 80)))
    except (TypeError, ValueError):
        limit = 80
    items.sort(key=base._sort_value)
    return Response({
        'generated_at': timezone.now(),
        'summary': summary,
        'results': items[:limit],
        'returned': min(len(items), limit),
    })
