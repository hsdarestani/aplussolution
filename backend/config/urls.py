from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import JsonResponse
from django.db import connections
from django.urls import include, path

from core import calendar_sync, order_file_import_views


def application_ready(request):
    """Read-only readiness: alive HTTP alone is insufficient if PostgreSQL is down.

    Leave /health/ as the legacy process liveness endpoint for deployments.
    Only use this DB-aware endpoint for the customer-facing availability guard.
    """
    if request.method not in {'GET', 'HEAD'}:
        return JsonResponse({'status': 'method_not_allowed'}, status=405)
    try:
        with connections['default'].cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
    except Exception:
        return JsonResponse({'status': 'unavailable'}, status=503)
    response = JsonResponse({'status': 'ok'})
    response['Cache-Control'] = 'no-store'
    return response


def contract_source_health(request):
    """Public, non-sensitive readiness for the eight private legal source files."""
    from core.document_catalog import DOCUMENT_CATALOG
    from core.document_source_recovery import source_exists
    from core.models import ContractTemplate

    templates = {item.slug: item for item in ContractTemplate.objects.filter(slug__in=[entry['slug'] for entry in DOCUMENT_CATALOG])}
    installed = sum(1 for entry in DOCUMENT_CATALOG if entry['slug'] in templates and source_exists(templates[entry['slug']]))
    expected = len(DOCUMENT_CATALOG)
    return JsonResponse({
        'status': 'ok',
        'document_sources': {
            'installed': installed,
            'expected': expected,
            'complete': installed == expected,
        },
    })


urlpatterns = [
    path('calendar-compatibility-test.ics', calendar_sync.calendar_compatibility_test),
    path('calendar/subscribe/<str:token>', calendar_sync.calendar_subscribe_page),
    path('calendar/<str:token>.ics', calendar_sync.calendar_feed),
    path('admin/', admin.site.urls),
    path('api/status/ready/', application_ready),
    path('api/automation/orders/parse-file/', order_file_import_views.parse_order_file),
    path('api/automation/orders/approve-file/', order_file_import_views.approve_order_file),
    path('api/', include('core.premium_override_urls')),
    path('api/', include('core.premium_extra_urls')),
    path('api/', include('core.premium_urls')),
    path('api/', include('core.urls')),
    path('health/', lambda request: JsonResponse({'status': 'ok'})),
    path('health/contracts/', contract_source_health),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
