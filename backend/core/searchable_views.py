from . import views
from .permissions import IsAdminOrManager
from .workplace_access import assignment_for, visible_locations, visible_workers


class ScopedManagerReadMixin:
    read_capability = 'manager.access'

    def get_permissions(self):
        if self.request.user.is_authenticated and self.request.user.role == 'manager' and getattr(self, 'action', None) in {'list', 'retrieve'}:
            self.required_capability = self.read_capability
            return [IsAdminOrManager()]
        return super().get_permissions()


class ClientCompanyViewSet(ScopedManagerReadMixin, views.ClientCompanyViewSet):
    read_capability = 'clients.view'
    search_fields = ['name', 'customer_number', 'address', 'vat_id', 'contacts__email', 'contacts__first_name', 'contacts__last_name']
    ordering_fields = ['name', 'customer_number', 'created_at', 'updated_at']

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.user.role == 'manager':
            assignment = assignment_for(self.request.user)
            if assignment and assignment.scope_mode == 'scoped':
                location_clients = visible_locations(self.request.user).exclude(client__isnull=True).values_list('client_id', flat=True)
                return qs.filter(id__in=location_clients).distinct()
        return qs


class WorkerViewSet(ScopedManagerReadMixin, views.WorkerViewSet):
    read_capability = 'people.view'
    search_fields = ['user__first_name', 'user__last_name', 'user__email', 'employee_number', 'employment_type']
    ordering_fields = ['employee_number', 'user__first_name', 'user__last_name', 'created_at', 'updated_at']

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.user.role == 'manager':
            return visible_workers(self.request.user, qs)
        return qs


class OrderViewSet(ScopedManagerReadMixin, views.OrderViewSet):
    read_capability = 'clients.view'
    search_fields = ['title', 'description', 'client__name', 'client__customer_number', 'location__name', 'location__address']
    ordering_fields = ['starts_at', 'ends_at', 'created_at', 'updated_at', 'requested_staff', 'status']

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.user.role == 'manager':
            assignment = assignment_for(self.request.user)
            if assignment and assignment.scope_mode == 'scoped':
                return qs.filter(location__in=visible_locations(self.request.user)).distinct()
        return qs


class ContractViewSet(ScopedManagerReadMixin, views.ContractViewSet):
    read_capability = 'manager.access'
    search_fields = [
        'title', 'template__name', 'template__slug', 'worker__user__first_name',
        'worker__user__last_name', 'worker__user__email', 'client__name', 'client__customer_number',
    ]
    ordering_fields = ['created_at', 'updated_at', 'starts_on', 'ends_on', 'reminder_date', 'status']


class DocumentViewSet(ScopedManagerReadMixin, views.DocumentViewSet):
    read_capability = 'manager.access'
    search_fields = ['title', 'folder', 'worker__user__first_name', 'worker__user__last_name', 'worker__user__email', 'client__name']
    ordering_fields = ['created_at', 'updated_at', 'title', 'folder']
