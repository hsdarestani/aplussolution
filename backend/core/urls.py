from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from . import advanced_views, views

router = DefaultRouter()
for prefix, view in [
    ('users', views.UserViewSet),
    ('clients', views.ClientCompanyViewSet),
    ('workers', views.WorkerViewSet),
    ('locations', views.LocationViewSet),
    ('positions', views.PositionViewSet),
    ('orders', views.OrderViewSet),
    ('availabilities', views.AvailabilityViewSet),
    ('shifts', views.ShiftViewSet),
    ('time-entries', views.TimeEntryViewSet),
    ('time-off', views.TimeOffViewSet),
    ('shift-swaps', views.ShiftSwapViewSet),
    ('contract-templates', views.ContractTemplateViewSet),
    ('contracts', views.ContractViewSet),
    ('documents', views.DocumentViewSet),
    ('payroll', views.PayrollViewSet),
    ('ratings', views.RatingViewSet),
    ('conversations', views.ConversationViewSet),
]:
    router.register(prefix, view)
router.register('notifications', views.NotificationViewSet, basename='notification')

urlpatterns = [
    path('', include(router.urls)),
    path('auth/login/', views.login),
    path('auth/refresh/', TokenRefreshView.as_view()),
    path('auth/me/', views.me),
    path('auth/change-password/', views.change_password),
    path('auth/account-deletion/', views.request_account_deletion),
    path('auth/oauth/<str:provider>/start/', views.oauth_start),
    path('auth/oauth/<str:provider>/callback/', views.oauth_callback),
    path('setup/demo/', views.setup_demo),
    path('dashboard/', views.dashboard),
    path('operations/', advanced_views.operations_overview),
    path('operations/schedule-quality/', advanced_views.schedule_quality),
    path('operations/availability/', advanced_views.availability_create),
    path('operations/availability/<uuid:pk>/', advanced_views.availability_delete),
    path('operations/swaps/', advanced_views.swap_create),
    path('operations/swaps/<uuid:pk>/decide/', advanced_views.swap_decide),
    path('operations/copy-week/', advanced_views.copy_week),
    path('operations/bulk-publish/', advanced_views.bulk_publish),
    path('operations/notifications/read-all/', advanced_views.notifications_read_all),
    path('operations/folders/', advanced_views.folder_summary),
    path('operations/readiness/', advanced_views.readiness),
    path('operations/templates/import/', advanced_views.import_contract_templates),
    path('reports/timesheets.csv', advanced_views.export_timesheets),
    path('reports/schedule.csv', advanced_views.export_schedule),
    path('reports/payroll-estimate.csv', advanced_views.export_payroll_estimate),
]
