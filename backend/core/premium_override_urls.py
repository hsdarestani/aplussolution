from django.urls import path

from . import premium_override_views, slot_compat_views

urlpatterns = [
    # Slot-aware overrides must be registered before core.urls so partially
    # filled multi-person shifts use ShiftSlot as the source of truth.
    path('operations/', slot_compat_views.operations_overview),
    path('operations/schedule-quality/', slot_compat_views.schedule_quality),
    path('operations/swaps/', slot_compat_views.swap_create),
    path('operations/swaps/<uuid:pk>/decide/', slot_compat_views.swap_decide),
    path('premium/auto-schedule/', premium_override_views.auto_schedule_view),
    path('premium/reports/<uuid:pk>/run/', premium_override_views.report_run),
    path('premium/callouts/', premium_override_views.callouts),
    path('premium/webhooks/<uuid:pk>/test/', premium_override_views.webhook_test),
]
