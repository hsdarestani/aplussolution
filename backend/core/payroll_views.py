from decimal import Decimal

from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import PayrollStatement, User, WorkerProfile, WorkingTimeSetting
from .permissions import IsAdminOrManager
from .serializers import PayrollStatementSerializer
from .services import audit
from .working_time import dec, settings_rows


class PayrollViewSet(viewsets.ModelViewSet):
    queryset = PayrollStatement.objects.select_related('worker__user').all()
    serializer_class = PayrollStatementSerializer
    permission_classes = [IsAuthenticated]
    manager_mutations = {'create', 'update', 'partial_update', 'destroy'}

    def get_permissions(self):
        if getattr(self, 'action', None) in self.manager_mutations:
            return [IsAdminOrManager()]
        return super().get_permissions()

    def get_queryset(self):
        user = self.request.user
        if user.role in {User.Role.ADMIN, User.Role.MANAGER}:
            return self.queryset
        if user.role == User.Role.WORKER:
            return self.queryset.filter(worker__user=user)
        # Payroll is never client-visible. Returning none also avoids the old
        # generic scope trying to filter PayrollStatement by a non-existent
        # `client` field.
        return self.queryset.none()

    def perform_create(self, serializer):
        obj = serializer.save()
        audit(self.request, 'payrollstatement.created', obj)

    def perform_update(self, serializer):
        obj = serializer.save()
        audit(self.request, 'payrollstatement.updated', obj)


@api_view(['GET', 'POST'])
@permission_classes([IsAdminOrManager])
def worktime_settings(request):
    if request.method == 'GET':
        return Response({
            'default_monthly_limit': str(settings.WORKING_TIME_DEFAULT_MONTHLY_LIMIT),
            'default_hourly_rate': str(settings.WORKING_TIME_DEFAULT_HOURLY_RATE),
            'default_break_minutes': settings.WORKING_TIME_DEFAULT_BREAK_MINUTES,
            'employees': settings_rows(),
        })

    employees = request.data.get('employees') or []
    saved = 0
    for row in employees:
        worker = get_object_or_404(WorkerProfile, pk=row.get('worker_id'))
        monthly_limit = max(Decimal('0'), dec(row.get('monthly_limit')))
        hourly_rate = max(Decimal('0'), dec(row.get('hourly_rate')))

        setting, _ = WorkingTimeSetting.objects.get_or_create(worker=worker)
        setting.monthly_limit = monthly_limit
        setting.hourly_rate = hourly_rate
        setting.active = bool(row.get('active', True))
        setting.excluded = bool(row.get('excluded', False))
        setting.notes = str(row.get('notes') or '')
        setting.save()

        # Keep the master-data values used by labor-cost/overtime forecasts in
        # sync with the payroll-preparation configuration. extra_allowance stays
        # separate and is added by both forecast and payroll calculations.
        worker.monthly_hours = monthly_limit
        worker.tariff_hourly_rate = hourly_rate
        worker.save(update_fields=['monthly_hours', 'tariff_hourly_rate', 'updated_at'])
        saved += 1

    audit(request, 'working_time.settings_saved', request.user, {'saved': saved})
    return Response({'status': 'ok', 'saved': saved, 'employees': settings_rows()})
