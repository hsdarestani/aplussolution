from django.urls import path

from . import premium_extra_views

urlpatterns = [
    path('premium/schedule-templates/<uuid:pk>/apply/', premium_extra_views.apply_schedule_template),
    path('premium/pickup-requests/', premium_extra_views.pickup_requests),
    path('premium/pickup-requests/<uuid:pk>/decide/', premium_extra_views.decide_pickup_request),
    path('premium/worker-locations/', premium_extra_views.worker_location_memberships),
    path('premium/schedule-timezone/', premium_extra_views.schedule_timezone),
]
