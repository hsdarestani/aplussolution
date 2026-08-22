from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from . import views
from .client_order_planning import plan_client_order
from .models import ClientOrder, User
from .permissions import IsAdminOrManager


SYNTHETIC_MIGRATION_EMAIL_SUFFIX = '@sync.invalid'


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

    def get_queryset(self):
        # Synthetic rows are retained for migration/audit but are not real A+
        # workforce profiles. Filtering here keeps pagination counts, searches,
        # CSV-facing lists and every frontend consumer consistent.
        return super().get_queryset().exclude(user__email__iendswith=SYNTHETIC_MIGRATION_EMAIL_SUFFIX)

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

    def _client_company(self):
        company = self.request.user.client_companies.filter(active=True).first()
        if not company:
            raise ValidationError('Dem Benutzer ist kein aktiver Kunde zugeordnet.')
        return company

    def _validate_client_relations(self, validated_data):
        if self.request.user.role != User.Role.CLIENT:
            return None
        company = self._client_company()
        requested_client = validated_data.get('client')
        if requested_client is not None and requested_client.pk != company.pk:
            raise ValidationError({'client': 'Aufträge dürfen nur für das eigene Kundenkonto angelegt oder geändert werden.'})
        location = validated_data.get('location')
        if location is not None and location.client_id != company.pk:
            raise ValidationError({'location': 'Der Einsatzort gehört nicht zu deinem Kundenkonto.'})
        return company

    def perform_create(self, serializer):
        if self.request.user.role == User.Role.CLIENT:
            company = self._validate_client_relations(serializer.validated_data)
            obj = serializer.save(created_by=self.request.user, client=company)
            views.audit(self.request, 'order.created', obj)
            return
        super().perform_create(serializer)

    def perform_update(self, serializer):
        if self.request.user.role == User.Role.CLIENT:
            company = self._validate_client_relations(serializer.validated_data)
            obj = serializer.save(client=company)
            views.audit(self.request, 'order.updated', obj)
            return
        super().perform_update(serializer)

    def update(self, request, *args, **kwargs):
        if request.user.role == User.Role.CLIENT and 'status' in request.data:
            raise ValidationError('Der Auftragsstatus wird durch die Disposition verwaltet.')
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        requested_status = request.data.get('status')
        if request.user.role == User.Role.CLIENT and requested_status is not None:
            raise ValidationError('Der Auftragsstatus wird durch die Disposition verwaltet.')

        if request.user.role in {'admin', 'manager'} and requested_status == ClientOrder.Status.CONFIRMED:
            order = self.get_object()
            try:
                planned_order, shift, created = plan_client_order(
                    order.pk,
                    request,
                    request.data.get('position'),
                )
            except ValueError as exc:
                raise ValidationError(str(exc)) from exc
            payload = self.get_serializer(planned_order).data
            payload['planning'] = {
                'created': created,
                'shift_id': str(shift.id),
                'required_count': shift.required_count,
                'is_open': shift.is_open,
            }
            return Response(payload)

        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        if request.user.role == User.Role.CLIENT:
            raise ValidationError('Übermittelte Aufträge werden aus Nachvollziehbarkeitsgründen nicht gelöscht. Bitte die Disposition kontaktieren.')
        return super().destroy(request, *args, **kwargs)


class ContractViewSet(views.ContractViewSet):
    search_fields = [
        'title', 'template__name', 'template__slug', 'worker__user__first_name',
        'worker__user__last_name', 'worker__user__email', 'client__name', 'client__customer_number',
    ]
    ordering_fields = ['created_at', 'updated_at', 'starts_on', 'ends_on', 'reminder_date', 'status']


class DocumentViewSet(views.DocumentViewSet):
    search_fields = ['title', 'folder', 'worker__user__first_name', 'worker__user__last_name', 'worker__user__email', 'client__name']
    ordering_fields = ['created_at', 'updated_at', 'title', 'folder']