from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from . import views
from .permissions import IsAdminOrManager


def _mark_worker_pending_activation(worker):
    """New workers must activate their own portal instead of receiving an admin password."""
    user = worker.user
    user.set_unusable_password()
    user.is_onboarded = False
    user.save(update_fields=['password', 'is_onboarded'])
    return worker


class ClientCompanyViewSet(views.ClientCompanyViewSet):
    search_fields = ['name', 'customer_number', 'address', 'vat_id', 'contacts__email', 'contacts__first_name', 'contacts__last_name']
    ordering_fields = ['name', 'customer_number', 'created_at', 'updated_at']


class WorkerViewSet(views.WorkerViewSet):
    search_fields = ['user__first_name', 'user__last_name', 'user__email', 'employee_number', 'employment_type']
    ordering_fields = ['employee_number', 'user__first_name', 'user__last_name', 'created_at', 'updated_at']

    @action(detail=False, methods=['post'], permission_classes=[IsAdminOrManager])
    def onboard(self, request):
        try:
            worker, _temporary_password = views.create_worker_account(request.data)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=400)

        _mark_worker_pending_activation(worker)
        views.audit(request, 'worker.onboarded', worker)
        return Response({
            'worker': self.get_serializer(worker).data,
            'temporary_password': None,
            'requires_activation': True,
        }, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], permission_classes=[IsAdminOrManager])
    def import_csv(self, request):
        upload = request.FILES.get('file')
        if not upload:
            return Response({'detail': 'CSV-Datei fehlt.'}, status=400)

        created, errors = 0, []
        for index, row in enumerate(views.parse_csv_file(upload), start=2):
            try:
                worker, _temporary_password = views.create_worker_account(row)
                _mark_worker_pending_activation(worker)
                created += 1
            except Exception as exc:
                errors.append({'line': index, 'error': str(exc)})

        return Response({
            'created': created,
            'errors': errors,
            'credentials': [],
            'requires_activation': True,
        })


class OrderViewSet(views.OrderViewSet):
    search_fields = ['title', 'description', 'client__name', 'client__customer_number', 'location__name', 'location__address']
    ordering_fields = ['starts_at', 'ends_at', 'created_at', 'updated_at', 'requested_staff', 'status']


class ContractViewSet(views.ContractViewSet):
    search_fields = [
        'title', 'template__name', 'template__slug', 'worker__user__first_name',
        'worker__user__last_name', 'worker__user__email', 'client__name', 'client__customer_number',
    ]
    ordering_fields = ['created_at', 'updated_at', 'starts_on', 'ends_on', 'reminder_date', 'status']


class DocumentViewSet(views.DocumentViewSet):
    search_fields = ['title', 'folder', 'worker__user__first_name', 'worker__user__last_name', 'worker__user__email', 'client__name']
    ordering_fields = ['created_at', 'updated_at', 'title', 'folder']
