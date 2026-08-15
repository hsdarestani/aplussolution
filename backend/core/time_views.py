from rest_framework.decorators import action
from rest_framework.response import Response

from .attendance_v4_models import AttendanceClockEvent
from .attendance_v4_service import clock_in_worker, clock_out_worker
from .services import audit
from .views import TimeEntryViewSet as LegacyTimeEntryViewSet


class TimeEntryViewSet(LegacyTimeEntryViewSet):
    """A+ Attendance source of truth for self-service clock-in and clock-out."""

    @action(detail=False, methods=['post'])
    def clock_in(self, request):
        if request.user.role != 'worker':
            return Response({'detail': 'Zeiterfassung ist nur im Mitarbeiterportal möglich.'}, status=403)
        try:
            entry = clock_in_worker(
                worker=request.user.worker_profile,
                shift_id=request.data.get('shift'),
                lat=request.data.get('lat'),
                lng=request.data.get('lng'),
                request=request,
                method=AttendanceClockEvent.Method.MOBILE,
                photo=request.FILES.get('photo'),
            )
        except Exception as exc:
            detail = getattr(exc, 'detail', exc)
            if isinstance(detail, list) and detail:
                detail = detail[0]
            return Response({'detail': str(detail)}, status=getattr(exc, 'status_code', 400))
        audit(request, 'time.clock_in', entry, {'source': 'attendance_v4'})
        return Response(self.get_serializer(entry).data, status=201)

    @action(detail=False, methods=['post'])
    def clock_out(self, request):
        if request.user.role != 'worker':
            return Response({'detail': 'Zeiterfassung ist nur im Mitarbeiterportal möglich.'}, status=403)
        try:
            entry, policy = clock_out_worker(
                worker=request.user.worker_profile,
                lat=request.data.get('lat'),
                lng=request.data.get('lng'),
                request=request,
                method=AttendanceClockEvent.Method.MOBILE,
                photo=request.FILES.get('photo'),
                note=request.data.get('note', ''),
            )
        except Exception as exc:
            detail = getattr(exc, 'detail', exc)
            if isinstance(detail, list) and detail:
                detail = detail[0]
            return Response({'detail': str(detail)}, status=getattr(exc, 'status_code', 400))
        audit(request, 'time.clock_out', entry, {'source': 'attendance_v4'})
        data = self.get_serializer(entry).data
        data['attestation_required'] = {
            'break': bool(policy.break_attestation_required),
            'end_of_shift': bool(policy.end_of_shift_attestation_required),
        }
        return Response(data)
