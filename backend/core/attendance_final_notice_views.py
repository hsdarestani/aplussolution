from .attendance_final_views import FinalAttendanceNoticeViewSet


class RoutedAttendanceNoticeViewSet(FinalAttendanceNoticeViewSet):
    """Router-safe final notice surface.

    Attendance notices are system-generated. Collection POST/PUT/PATCH/DELETE are
    intentionally disabled; only explicit workflow actions declared on the base
    class are writable.
    """

    def create(self, request, *args, **kwargs):
        from rest_framework.response import Response
        return Response({'detail': 'Attendance Notices werden automatisch erzeugt.'}, status=405)

    def update(self, request, *args, **kwargs):
        from rest_framework.response import Response
        return Response({'detail': 'Direkte Änderungen an Attendance Notices sind nicht erlaubt.'}, status=405)

    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        from rest_framework.response import Response
        return Response({'detail': 'Attendance Notices bleiben als Audit-Historie erhalten.'}, status=405)
