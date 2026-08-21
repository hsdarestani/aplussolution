from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


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
    path('admin/', admin.site.urls),
    path('api/', include('core.premium_override_urls')),
    path('api/', include('core.premium_extra_urls')),
    path('api/', include('core.premium_urls')),
    path('api/', include('core.urls')),
    path('health/', lambda request: JsonResponse({'status': 'ok'})),
    path('health/contracts/', contract_source_health),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
