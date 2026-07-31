from . import views


class ClientCompanyViewSet(views.ClientCompanyViewSet):
    search_fields = ['name', 'customer_number', 'address', 'vat_id', 'contacts__email', 'contacts__first_name', 'contacts__last_name']
    ordering_fields = ['name', 'customer_number', 'created_at', 'updated_at']


class WorkerViewSet(views.WorkerViewSet):
    search_fields = ['user__first_name', 'user__last_name', 'user__email', 'employee_number', 'employment_type']
    ordering_fields = ['employee_number', 'user__first_name', 'user__last_name', 'created_at', 'updated_at']


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
