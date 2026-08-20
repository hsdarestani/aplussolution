from django.urls import path

from . import live_operations, native_operations, premium_override_views

urlpatterns = [
    # Native operational overrides must be registered before core.urls. The
    # same canonical native_operations functions are also wired in core.urls,
    # so URL ordering can no longer fall back to legacy Shift.worker logic.
    path('operations/', live_operations.operations_overview),
    path('operations/schedule-quality/', native_operations.schedule_quality),
    path('operations/swaps/', native_operations.swap_create),
    path('operations/swaps/<uuid:pk>/decide/', native_operations.swap_decide),
    path('premium/auto-schedule/', premium_override_views.auto_schedule_view),
    path('premium/reports/<uuid:pk>/run/', premium_override_views.report_run),
    path('premium/callouts/', premium_override_views.callouts),
    path('premium/webhooks/<uuid:pk>/test/', premium_override_views.webhook_test),
]
