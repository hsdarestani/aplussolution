from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import self_service_views


router = DefaultRouter()
router.register('availability', self_service_views.AvailabilityPreferenceSeriesViewSet, basename='self-service-availability')
router.register('time-off-types', self_service_views.TimeOffTypeViewSet, basename='self-service-time-off-type')

urlpatterns = [
    path('', include(router.urls)),
    path('snapshot/', self_service_views.self_service_snapshot),
    path('settings/', self_service_views.self_service_settings),
    path('preference/', self_service_views.self_service_preference),
    path('coworkers/', self_service_views.coworkers),
    path('team-schedule/', self_service_views.team_schedule),
    path('open-shifts/<uuid:shift_id>/policy/', self_service_views.open_shift_policy),
    path('open-shift-requests/', self_service_views.open_shift_requests),
    path('open-shift-requests/<uuid:pk>/decide/', self_service_views.open_shift_request_decide),
    path('open-shift-requests/<uuid:pk>/cancel/', self_service_views.open_shift_request_cancel),
    path('coverage/', self_service_views.coverage_requests),
    path('coverage/<uuid:pk>/review/', self_service_views.coverage_review),
    path('coverage/<uuid:pk>/accept/', self_service_views.coverage_accept),
    path('coverage/<uuid:pk>/decline/', self_service_views.coverage_decline),
    path('coverage/<uuid:pk>/cancel/', self_service_views.coverage_cancel),
    path('time-off/', self_service_views.detailed_time_off),
]
