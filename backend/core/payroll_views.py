import csv
from io import BytesIO

from django.http import HttpResponse
from django.utils import timezone
from openpyxl import Workbook
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .payroll_models import PayPeriod, TimesheetEntry, TimesheetException, WorkerTimesheet
from .payroll_service import (
    approve_all_entries,
    approve_timesheet,
    close_period,
    lock_period,
    reopen_period,
    review_entry,
    submit_timesheet,
    sync_period,
    unapprove_timesheet,
    unlock_period,
)
from .permissions import IsAdminOrManager
from .services import audit


class TimesheetEntrySerializer(serializers.ModelSerializer):
    shift_title = serializers.SerializerMethodField()
    location_name = serializers.SerializerMethodField()

    class Meta:
        model = TimesheetEntry
        fields = [
            'id', 'time_entry', 'clock_in', 'clock_out', 'gross_minutes', 'paid_break_minutes',
            'unpaid_break_minutes', 'net_minutes', 'hourly_rate', 'amount_estimate', 'review_status',
            'reviewed_by', 'reviewed_at', 'review_note', 'locked', 'shift_title', 'location_name',
        ]
        read_only_fields = fields

    def get_shift_title(self, obj):
        shift = obj.time_entry.shift
        return shift.position.name if shift and shift.position_id else 'Arbeitszeit'

    def get_location_name(self, obj):
        shift = obj.time_entry.shift
        return shift.location.name if shift and shift.location_id else ''


class TimesheetExceptionSerializer(serializers.ModelSerializer):
    shift_title = serializers.SerializerMethodField()

    class Meta:
        model = TimesheetException
        fields = [
            'id', 'exception_type', 'severity', 'status', 'shift', 'time_entry', 'attendance_notice',
            'details', 'resolved_by', 'resolved_at', 'resolution_note', 'shift_title', 'created_at',
        ]
        read_only_fields = fields

    def get_shift_title(self, obj):
        return obj.shift.position.name if obj.shift_id and obj.shift.position_id else ''


class WorkerTimesheetSerializer(serializers.ModelSerializer):
    worker_name = serializers.SerializerMethodField()
    employee_number = serializers.CharField(source='worker.employee_number', read_only=True)
    period_name = serializers.CharField(source='pay_period.name', read_only=True)
    entries = TimesheetEntrySerializer(many=True, read_only=True)
    exceptions = TimesheetExceptionSerializer(many=True, read_only=True)

    class Meta:
        model = WorkerTimesheet
        fields = [
            'id', 'pay_period', 'period_name', 'worker', 'worker_name', 'employee_number', 'status',
            'gross_minutes', 'paid_break_minutes', 'unpaid_break_minutes', 'net_minutes', 'gross_estimate',
            'entry_count', 'exception_count', 'blocking_exception_count', 'submitted_at', 'approved_at',
            'approved_by', 'locked_at', 'review_note', 'revision', 'entries', 'exceptions', 'updated_at',
        ]
        read_only_fields = fields

    def get_worker_name(self, obj):
        return obj.worker.user.get_full_name() or obj.worker.user.email


class PayPeriodSerializer(serializers.ModelSerializer):
    timesheet_count = serializers.SerializerMethodField()
    approved_count = serializers.SerializerMethodField()
    blocking_count = serializers.SerializerMethodField()
    net_minutes = serializers.SerializerMethodField()
    gross_estimate = serializers.SerializerMethodField()

    class Meta:
        model = PayPeriod
        fields = [
            'id', 'name', 'starts_on', 'ends_on', 'status', 'currency', 'notes', 'created_by',
            'closed_by', 'closed_at', 'locked_by', 'locked_at', 'reopen_count', 'timesheet_count',
            'approved_count', 'blocking_count', 'net_minutes', 'gross_estimate', 'created_at', 'updated_at',
        ]
        read_only_fields = ['status', 'created_by', 'closed_by', 'closed_at', 'locked_by', 'locked_at', 'reopen_count', 'created_at', 'updated_at']

    def validate(self, attrs):
        starts_on = attrs.get('starts_on', getattr(self.instance, 'starts_on', None))
        ends_on = attrs.get('ends_on', getattr(self.instance, 'ends_on', None))
        if starts_on and ends_on and ends_on < starts_on:
            raise serializers.ValidationError('Das Enddatum darf nicht vor dem Startdatum liegen.')
        if starts_on and ends_on:
            overlap = PayPeriod.objects.filter(starts_on__lte=ends_on, ends_on__gte=starts_on)
            if self.instance:
                overlap = overlap.exclude(pk=self.instance.pk)
            if overlap.exists():
                raise serializers.ValidationError('Der Zeitraum überschneidet sich mit einem bestehenden Pay Period.')
        return attrs

    def get_timesheet_count(self, obj):
        return obj.timesheets.count()

    def get_approved_count(self, obj):
        return obj.timesheets.filter(status__in=[WorkerTimesheet.Status.APPROVED, WorkerTimesheet.Status.LOCKED]).count()

    def get_blocking_count(self, obj):
        return TimesheetException.objects.filter(timesheet__pay_period=obj, status=TimesheetException.Status.OPEN, severity=TimesheetException.Severity.BLOCKING).count()

    def get_net_minutes(self, obj):
        return sum(obj.timesheets.values_list('net_minutes', flat=True))

    def get_gross_estimate(self, obj):
        return sum(obj.timesheets.values_list('gross_estimate', flat=True))


class PayPeriodViewSet(viewsets.ModelViewSet):
    queryset = PayPeriod.objects.all()
    serializer_class = PayPeriodSerializer
    permission_classes = [IsAdminOrManager]
    filterset_fields = ['status']
    ordering_fields = ['starts_on', 'ends_on', 'created_at', 'updated_at']

    def perform_create(self, serializer):
        obj = serializer.save(created_by=self.request.user)
        audit(self.request, 'pay_period.created', obj)

    def perform_update(self, serializer):
        if serializer.instance.status in {PayPeriod.Status.CLOSED, PayPeriod.Status.LOCKED}:
            raise ValidationError('Geschlossene oder gesperrte Abrechnungszeiträume können nicht direkt bearbeitet werden.')
        obj = serializer.save()
        audit(self.request, 'pay_period.updated', obj)

    def perform_destroy(self, instance):
        if instance.status != PayPeriod.Status.OPEN or instance.timesheets.exists():
            raise ValidationError('Nur leere offene Pay Periods können gelöscht werden.')
        audit(self.request, 'pay_period.deleted', instance)
        instance.delete()

    @action(detail=True, methods=['post'])
    def sync(self, request, pk=None):
        period = self.get_object()
        sheets = sync_period(period)
        audit(request, 'pay_period.synced', period, {'timesheets': len(sheets)})
        period.refresh_from_db()
        return Response(self.get_serializer(period).data)

    @action(detail=True, methods=['post'])
    def close(self, request, pk=None):
        period = close_period(self.get_object(), request.user)
        audit(request, 'pay_period.closed', period)
        return Response(self.get_serializer(period).data)

    @action(detail=True, methods=['post'])
    def reopen(self, request, pk=None):
        period = reopen_period(self.get_object(), request.user, str(request.data.get('reason', '')).strip())
        audit(request, 'pay_period.reopened', period, {'reason': request.data.get('reason', '')})
        return Response(self.get_serializer(period).data)

    @action(detail=True, methods=['post'])
    def lock(self, request, pk=None):
        period = lock_period(self.get_object(), request.user)
        audit(request, 'pay_period.locked', period)
        return Response(self.get_serializer(period).data)

    @action(detail=True, methods=['post'])
    def unlock(self, request, pk=None):
        if request.user.role != 'admin':
            return Response({'detail': 'Nur die Administration darf einen final gesperrten Zeitraum entsperren.'}, status=403)
        reason = str(request.data.get('reason', '')).strip()
        if not reason:
            return Response({'detail': 'Ein Grund ist erforderlich.'}, status=400)
        period = unlock_period(self.get_object(), request.user, reason)
        audit(request, 'pay_period.unlocked', period, {'reason': reason})
        return Response(self.get_serializer(period).data)

    @action(detail=True, methods=['get'], url_path='export-csv')
    def export_csv(self, request, pk=None):
        period = self.get_object()
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="pay-period-{period.starts_on}-{period.ends_on}.csv"'
        response.write('\ufeff')
        writer = csv.writer(response, delimiter=';')
        writer.writerow(['Personalnummer', 'Mitarbeiter', 'Status', 'Netto Minuten', 'Netto Stunden', 'Unbezahlte Pause', 'Brutto Schätzung', 'Währung', 'Ausnahmen'])
        for sheet in period.timesheets.select_related('worker__user').order_by('worker__employee_number'):
            writer.writerow([
                sheet.worker.employee_number,
                sheet.worker.user.get_full_name() or sheet.worker.user.email,
                sheet.status,
                sheet.net_minutes,
                f'{sheet.net_minutes / 60:.2f}',
                sheet.unpaid_break_minutes,
                sheet.gross_estimate,
                period.currency,
                sheet.exception_count,
            ])
        return response

    @action(detail=True, methods=['get'], url_path='export-xlsx')
    def export_xlsx(self, request, pk=None):
        period = self.get_object()
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = 'Timesheets'
        sheet.append(['Personalnummer', 'Mitarbeiter', 'Status', 'Netto Minuten', 'Netto Stunden', 'Unbezahlte Pause', 'Brutto Schätzung', 'Währung', 'Ausnahmen'])
        for item in period.timesheets.select_related('worker__user').order_by('worker__employee_number'):
            sheet.append([
                item.worker.employee_number,
                item.worker.user.get_full_name() or item.worker.user.email,
                item.status,
                item.net_minutes,
                round(item.net_minutes / 60, 2),
                item.unpaid_break_minutes,
                float(item.gross_estimate),
                period.currency,
                item.exception_count,
            ])
        detail = workbook.create_sheet('Entries')
        detail.append(['Personalnummer', 'Mitarbeiter', 'Beginn', 'Ende', 'Netto Minuten', 'Stundensatz', 'Betrag', 'Review'])
        for item in TimesheetEntry.objects.filter(timesheet__pay_period=period).select_related('timesheet__worker__user').order_by('clock_in'):
            worker = item.timesheet.worker
            detail.append([
                worker.employee_number,
                worker.user.get_full_name() or worker.user.email,
                item.clock_in.replace(tzinfo=None) if timezone.is_aware(item.clock_in) else item.clock_in,
                item.clock_out.replace(tzinfo=None) if item.clock_out and timezone.is_aware(item.clock_out) else item.clock_out,
                item.net_minutes,
                float(item.hourly_rate),
                float(item.amount_estimate),
                item.review_status,
            ])
        payload = BytesIO()
        workbook.save(payload)
        response = HttpResponse(payload.getvalue(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = f'attachment; filename="pay-period-{period.starts_on}-{period.ends_on}.xlsx"'
        return response


class WorkerTimesheetViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = WorkerTimesheet.objects.select_related('pay_period', 'worker__user', 'approved_by').prefetch_related(
        'entries__time_entry__shift__position', 'entries__time_entry__shift__location', 'exceptions__shift__position'
    )
    serializer_class = WorkerTimesheetSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['pay_period', 'worker', 'status']

    def get_queryset(self):
        qs = self.queryset
        if self.request.user.role == 'worker':
            return qs.filter(worker__user=self.request.user)
        if self.request.user.role in {'admin', 'manager'}:
            return qs
        return qs.none()

    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        sheet = self.get_object()
        if request.user.role == 'worker' and sheet.worker.user_id != request.user.id:
            return Response({'detail': 'Nicht berechtigt.'}, status=403)
        if request.user.role not in {'worker', 'admin', 'manager'}:
            return Response({'detail': 'Nicht berechtigt.'}, status=403)
        submit_timesheet(sheet)
        audit(request, 'timesheet.submitted', sheet)
        return Response(self.get_serializer(sheet).data)

    @action(detail=True, methods=['post'], permission_classes=[IsAdminOrManager], url_path='approve-all-entries')
    def approve_all_entries_action(self, request, pk=None):
        sheet = approve_all_entries(self.get_object(), request.user)
        audit(request, 'timesheet.entries_approved', sheet)
        return Response(self.get_serializer(sheet).data)

    @action(detail=True, methods=['post'], permission_classes=[IsAdminOrManager])
    def approve(self, request, pk=None):
        sheet = approve_timesheet(self.get_object(), request.user, str(request.data.get('note', '')).strip())
        audit(request, 'timesheet.approved', sheet)
        return Response(self.get_serializer(sheet).data)

    @action(detail=True, methods=['post'], permission_classes=[IsAdminOrManager])
    def unapprove(self, request, pk=None):
        sheet = unapprove_timesheet(self.get_object(), request.user, str(request.data.get('reason', '')).strip())
        audit(request, 'timesheet.unapproved', sheet, {'reason': request.data.get('reason', '')})
        return Response(self.get_serializer(sheet).data)


class TimesheetEntryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = TimesheetEntry.objects.select_related('timesheet__pay_period', 'timesheet__worker__user', 'time_entry__shift__position', 'time_entry__shift__location')
    serializer_class = TimesheetEntrySerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['timesheet', 'review_status']

    def get_queryset(self):
        qs = self.queryset
        if self.request.user.role == 'worker':
            return qs.filter(timesheet__worker__user=self.request.user)
        if self.request.user.role in {'admin', 'manager'}:
            return qs
        return qs.none()

    @action(detail=True, methods=['post'], permission_classes=[IsAdminOrManager])
    def review(self, request, pk=None):
        item = review_entry(self.get_object(), request.user, request.data.get('decision'), str(request.data.get('note', '')).strip())
        audit(request, 'timesheet.entry_reviewed', item, {'decision': item.review_status})
        return Response(self.get_serializer(item).data)


class TimesheetExceptionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = TimesheetException.objects.select_related('timesheet__pay_period', 'timesheet__worker__user', 'shift__position', 'time_entry')
    serializer_class = TimesheetExceptionSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['timesheet', 'status', 'severity', 'exception_type']

    def get_queryset(self):
        qs = self.queryset
        if self.request.user.role == 'worker':
            return qs.filter(timesheet__worker__user=self.request.user)
        if self.request.user.role in {'admin', 'manager'}:
            return qs
        return qs.none()

    def _decide(self, request, dismissed=False):
        if request.user.role not in {'admin', 'manager'}:
            return Response({'detail': 'Nicht berechtigt.'}, status=403)
        obj = self.get_object()
        if obj.timesheet.pay_period.status in {PayPeriod.Status.CLOSED, PayPeriod.Status.LOCKED}:
            return Response({'detail': 'Der Abrechnungszeitraum ist geschlossen.'}, status=400)
        obj.resolve(request.user, str(request.data.get('note', '')).strip(), dismissed=dismissed)
        audit(request, 'timesheet.exception_dismissed' if dismissed else 'timesheet.exception_resolved', obj)
        return Response(self.get_serializer(obj).data)

    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        return self._decide(request)

    @action(detail=True, methods=['post'])
    def dismiss(self, request, pk=None):
        return self._decide(request, dismissed=True)
