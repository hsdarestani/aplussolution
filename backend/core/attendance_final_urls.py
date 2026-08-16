from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import attendance_final_views
from .attendance_final_notice_views import RoutedAttendanceNoticeViewSet


router = DefaultRouter()
router.register('attendance-policies', attendance_final_views.FinalAttendancePolicyViewSet, basename='final-attendance-policy')
router.register('attendance-notices', RoutedAttendanceNoticeViewSet, basename='final-attendance-notice')
router.register('attendance-terminals', attendance_final_views.FinalAttendanceTerminalViewSet, basename='final-attendance-terminal')

urlpatterns = [
    path('', include(router.urls)),
    path('attendance/exceptions/', attendance_final_views.attendance_exceptions),
    path('attendance/notices/scan/', attendance_final_views.attendance_scan),
    path('attendance/terminal/<uuid:public_id>/clock/', attendance_final_views.terminal_clock),
]
