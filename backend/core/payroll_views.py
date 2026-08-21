from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from .models import PayrollStatement, User
from .permissions import IsAdminOrManager
from .serializers import PayrollStatementSerializer
from .services import audit


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
