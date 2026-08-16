from rest_framework.decorators import action

from .attendance_final_views import FinalAttendanceTerminalViewSet, _require


class RoutedAttendanceTerminalViewSet(FinalAttendanceTerminalViewSet):
    @action(detail=True, methods=['post'], url_path='rotate-token')
    def rotate_token(self, request, pk=None):
        _require(request.user, 'attendance.edit')
        return super().rotate_token(request, pk=pk)
