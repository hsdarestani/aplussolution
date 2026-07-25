from django.contrib import admin
from django.urls import include,path
from django.http import JsonResponse
from django.conf import settings
from django.conf.urls.static import static
urlpatterns=[path('admin/',admin.site.urls),path('api/',include('core.urls')),path('health/',lambda request:JsonResponse({'status':'ok'}))]+static(settings.MEDIA_URL,document_root=settings.MEDIA_ROOT)
