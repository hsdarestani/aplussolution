from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from . import views
from .models import (
    ClientCompany,
    ClientOrder,
    Contract,
    Document,
    PayrollStatement,
    Shift,
    User,
    WorkerProfile,
    WorkerRating,
)
from .shift_slots import ShiftSlot


class ClientSafeRatingViewSet(views.RatingViewSet):
    """Keep ratings tenant-scoped and tied to a real completed client assignment."""

    def perform_create(self, serializer):
        if self.request.user.role != User.Role.CLIENT:
            return super().perform_create(serializer)

        company = self.request.user.client_companies.filter(active=True).first()
        if not company:
            raise ValidationError('Dem Benutzer ist kein aktiver Kunde zugeordnet.')

        worker = serializer.validated_data.get('worker')
        shift = serializer.validated_data.get('shift')
        if not shift:
            raise ValidationError({'shift': 'Bitte wähle den abgeschlossenen Einsatz aus.'})
        if not worker:
            raise ValidationError({'worker': 'Bitte wähle den eingesetzten Mitarbeiter aus.'})
        if shift.client_id != company.pk:
            raise ValidationError({'shift': 'Dieser Einsatz gehört nicht zu deinem Kundenkonto.'})
        if shift.status == Shift.Status.CANCELLED or shift.ends_at > timezone.now():
            raise ValidationError({'shift': 'Bewertungen sind erst nach einem tatsächlich durchgeführten Einsatz möglich.'})

        assigned = shift.worker_id == worker.pk or ShiftSlot.objects.filter(
            shift=shift,
            worker=worker,
            status=ShiftSlot.Status.CLAIMED,
        ).exists()
        if not assigned:
            raise ValidationError({'worker': 'Dieser Mitarbeiter war diesem Einsatz nicht zugeordnet.'})

        if WorkerRating.objects.filter(client=company, worker=worker, shift=shift).exists():
            raise ValidationError('Dieser Mitarbeitereinsatz wurde bereits bewertet.')

        obj = serializer.save(created_by=self.request.user, client=company)
        obj.worker.ranking_points += obj.score * 10
        obj.worker.save(update_fields=['ranking_points'])
        views.audit(self.request, 'rating.created', obj)


@api_view(['GET'])
def client_dashboard(request):
    """Client dashboard counters follow the same tenant and visibility rules as detail lists."""
    if request.user.role != User.Role.CLIENT:
        raise PermissionDenied('Diese Übersicht ist nur im Kundenportal verfügbar.')
    companies = request.user.client_companies.filter(active=True)
    now = timezone.now()
    return Response({
        'role': request.user.role,
        'active_orders': ClientOrder.objects.filter(
            client__in=companies,
            status__in=[ClientOrder.Status.NEW, ClientOrder.Status.PLANNING, ClientOrder.Status.CONFIRMED],
        ).count(),
        'upcoming_shifts': Shift.objects.filter(
            client__in=companies,
            starts_at__gte=now,
        ).exclude(status=Shift.Status.CANCELLED).count(),
        'contracts_to_sign': Contract.objects.filter(
            client__in=companies,
            client__contract_visibility_enabled=True,
            status__in=[Contract.Status.READY, Contract.Status.SENT],
        ).count(),
    })


@api_view(['GET'])
def client_rating_candidates(request):
    """Minimal worker data for ratings: only people assigned to this client's past shifts."""
    if request.user.role != User.Role.CLIENT:
        raise PermissionDenied('Diese Liste ist nur im Kundenportal verfügbar.')

    companies = request.user.client_companies.filter(active=True)
    shifts = (
        Shift.objects.filter(client__in=companies, ends_at__lte=timezone.now())
        .exclude(status=Shift.Status.CANCELLED)
        .select_related('client', 'location', 'position', 'worker__user')
        .prefetch_related('slots__worker__user')
        .order_by('-ends_at')[:150]
    )

    rows = []
    seen = set()
    for shift in shifts:
        workers = []
        if shift.worker_id:
            workers.append(shift.worker)
        workers.extend(
            slot.worker
            for slot in shift.slots.all()
            if slot.status == ShiftSlot.Status.CLAIMED and slot.worker_id
        )
        for worker in workers:
            key = (shift.pk, worker.pk)
            if key in seen:
                continue
            seen.add(key)
            if WorkerRating.objects.filter(client=shift.client, worker=worker, shift=shift).exists():
                continue
            rows.append({
                'shift_id': str(shift.id),
                'worker_id': str(worker.id),
                'worker_name': worker.user.get_full_name().strip() or worker.employee_number,
                'position_name': shift.position.name,
                'location_name': shift.location.name,
                'starts_at': shift.starts_at,
                'ends_at': shift.ends_at,
            })
    return Response(rows)


@api_view(['GET'])
def folder_summary(request):
    """Servicecenter counters must obey the same visibility rules as the actual lists."""
    user = request.user
    if user.role in {User.Role.ADMIN, User.Role.MANAGER}:
        workers = [{
            'id': str(worker.id),
            'name': worker.user.get_full_name() or worker.user.email,
            'employee_number': worker.employee_number,
            'documents': Document.objects.filter(worker=worker).count(),
            'contracts': Contract.objects.filter(worker=worker).count(),
            'payroll': PayrollStatement.objects.filter(worker=worker).count(),
        } for worker in WorkerProfile.objects.filter(active=True).select_related('user')]
        clients = [{
            'id': str(client.id),
            'name': client.name,
            'customer_number': client.customer_number,
            'documents': Document.objects.filter(client=client).count(),
            'contracts': Contract.objects.filter(client=client).count(),
            'orders': ClientOrder.objects.filter(client=client).count(),
        } for client in ClientCompany.objects.filter(active=True)]
        return Response({'workers': workers, 'clients': clients})

    if user.role == User.Role.WORKER:
        worker = user.worker_profile
        return Response({'workers': [{
            'id': str(worker.id),
            'name': worker.user.get_full_name() or worker.user.email,
            'employee_number': worker.employee_number,
            'documents': Document.objects.filter(worker=worker).exclude(visibility=Document.Visibility.ADMIN).count(),
            'contracts': Contract.objects.filter(worker=worker).count(),
            'payroll': PayrollStatement.objects.filter(worker=worker).count(),
        }], 'clients': []})

    clients = [{
        'id': str(client.id),
        'name': client.name,
        'customer_number': client.customer_number,
        'documents': Document.objects.filter(
            client=client,
            visibility__in=[Document.Visibility.CLIENT, Document.Visibility.SHARED],
        ).count(),
        'contracts': (
            Contract.objects.filter(client=client).count()
            if client.contract_visibility_enabled
            else 0
        ),
        'orders': ClientOrder.objects.filter(client=client).count(),
    } for client in user.client_companies.filter(active=True)]
    return Response({'workers': [], 'clients': clients})
