from django.urls import path

from . import live_operations, premium_override_views, slot_compat_views_v2

urlpatterns = [
    # Slot-aware overrides must be registered before core.urls so partially
    # filled multi-person shifts use ShiftSlot as the source of truth. The
    # operations overview composes that slot-aware logic with migration-safe
    # live counters so imported WIW history cannot pollute day-to-day KPIs.
    path('operations/', live_operations.operations_overview),
    path('operations/schedule-quality/', slot_compat_views_v2.schedule_quality),
    path('operations/swaps/', slot_compat_views_v2.swap_create),
    path('operations/swaps/<uuid:pk>/decide/', slot_compat_views_v2.swap_decide),
    path('premium/auto-schedule/', premium_override_views.auto_schedule_view),
    path('premium/reports/<uuid:pk>/run/', premium_override_views.report_run),
    path('premium/callouts/', premium_override_views.callouts),
    path('premium/webhooks/<uuid:pk>/test/', premium_override_views.webhook_test),
]
