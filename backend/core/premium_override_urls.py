from django.urls import path

from . import premium_override_views

urlpatterns = [
    path('premium/auto-schedule/', premium_override_views.auto_schedule_view),
    path('premium/reports/<uuid:pk>/run/', premium_override_views.report_run),
    path('premium/callouts/', premium_override_views.callouts),
    path('premium/webhooks/<uuid:pk>/test/', premium_override_views.webhook_test),
]
