from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import ClientCompany, ClientOrder, Contract, Document, Location, PayrollStatement, Shift, User, WorkerProfile
from .serializers import ClientCompanySerializer, ClientOrderSerializer, ContractSerializer, DocumentSerializer, LocationSerializer, PayrollStatementSerializer, ShiftSerializer, WorkerProfileSerializer
from .shift_slots import ShiftSlot


def _manager(user):
    return user.role in {User.Role.ADMIN, User.Role.MANAGER}


def _document_groups(documents, request):
    labels = dict(Document.Folder.choices)
    groups = []
    for value, _label in Document.Folder.choices:
        rows = documents.filter(folder=value).order_by('-created_at')
        if rows.exists():
            groups.append({
                'key': value,
                'label': labels.get(value, value),
                'count': rows.count(),
                'items': DocumentSerializer(rows, many=True, context={'request': request}).data,
            })
    return groups


def _worker_shifts(worker):
    """Return native slot assignments plus legacy Shift.worker rows without duplicates."""
    return (
        Shift.objects.filter(
            Q(worker=worker) |
            Q(slots__worker=worker, slots__status=ShiftSlot.Status.CLAIMED)
        )
        .exclude(status=Shift.Status.CANCELLED)
        .distinct()
    )


def _worker_contracts(worker):
    """Include direct worker contracts and client ANÜ documents covering assigned shifts.

    A client ANÜ can cover multiple employees, so Contract.worker cannot express all participants.
    Native A+ contracts store local Shift UUIDs in variables.shift_ids while historical migrated
    contracts may contain WIW IDs. Match both identifiers so the same immutable signed ANÜ appears
    in every affected employee Akte as well as the client Akte.
    """
    shifts = list(_worker_shifts(worker).only('id', 'wiw_shift_id'))
    covered_shift_ids = {str(shift.id) for shift in shifts}
    covered_shift_ids.update(str(shift.wiw_shift_id) for shift in shifts if shift.wiw_shift_id)
    linked_contract_ids = []
    if covered_shift_ids:
        for contract in Contract.objects.filter(client__isnull=False).exclude(variables={}):
            shift_ids = (contract.variables or {}).get('shift_ids') or []
            if covered_shift_ids.intersection(str(value) for value in shift_ids):
                linked_contract_ids.append(contract.id)
    return (
        Contract.objects.filter(Q(worker=worker) | Q(pk__in=linked_contract_ids))
        .select_related('template', 'worker__user', 'client')
        .prefetch_related('signatures')
        .distinct()
        .order_by('-updated_at')
    )


@api_view(['GET'])
def worker_akte(request, pk):
    worker = get_object_or_404(WorkerProfile.objects.select_related('user'), pk=pk)
    own_worker = request.user.role == User.Role.WORKER and worker.user_id == request.user.id
    if not _manager(request.user) and not own_worker:
        return Response({'detail': 'Keine Berechtigung für diese Mitarbeiterakte.'}, status=403)

    contracts = _worker_contracts(worker)
    documents = Document.objects.filter(worker=worker).select_related('worker__user', 'client')
    if own_worker:
        documents = documents.exclude(visibility=Document.Visibility.ADMIN)
    payroll = PayrollStatement.objects.filter(worker=worker).select_related('worker__user').order_by('-period')
    shift_qs = _worker_shifts(worker)
    shifts = shift_qs.select_related('worker__user', 'client', 'location', 'position').order_by('-starts_at')[:50]

    return Response({
        'kind': 'worker',
        'title': worker.user.get_full_name() or worker.user.email,
        'number': worker.employee_number,
        'profile': WorkerProfileSerializer(worker, context={'request': request}).data,
        'summary': {
            'contracts': contracts.count(),
            'documents': documents.count(),
            'payroll': payroll.count(),
            'shifts': shift_qs.count(),
        },
        'contracts': ContractSerializer(contracts, many=True, context={'request': request}).data,
        'document_folders': _document_groups(documents, request),
        'payroll': PayrollStatementSerializer(payroll, many=True, context={'request': request}).data,
        'shifts': ShiftSerializer(shifts, many=True, context={'request': request}).data,
    })


@api_view(['GET'])
def client_akte(request, pk):
    client = get_object_or_404(ClientCompany.objects.prefetch_related('contacts'), pk=pk)
    own_client = request.user.role == User.Role.CLIENT and client.contacts.filter(pk=request.user.pk).exists()
    if not _manager(request.user) and not own_client:
        return Response({'detail': 'Keine Berechtigung für diese Kundenakte.'}, status=403)

    contracts = Contract.objects.filter(client=client).select_related('template', 'worker__user', 'client').prefetch_related('signatures').order_by('-updated_at')
    documents = Document.objects.filter(client=client).select_related('worker__user', 'client')
    if own_client:
        if not client.contract_visibility_enabled:
            contracts = contracts.none()
        documents = documents.filter(visibility__in=[Document.Visibility.CLIENT, Document.Visibility.SHARED])
    orders = ClientOrder.objects.filter(client=client).select_related('client', 'location').order_by('-starts_at')
    locations = Location.objects.filter(client=client).order_by('name')
    shifts = Shift.objects.filter(client=client).select_related('worker__user', 'client', 'location', 'position').order_by('-starts_at')[:80]

    return Response({
        'kind': 'client',
        'title': client.name,
        'number': client.customer_number,
        'profile': ClientCompanySerializer(client, context={'request': request}).data,
        'summary': {
            'contracts': contracts.count(),
            'documents': documents.count(),
            'orders': orders.count(),
            'locations': locations.count(),
            'shifts': Shift.objects.filter(client=client).count(),
        },
        'contracts': ContractSerializer(contracts, many=True, context={'request': request}).data,
        'document_folders': _document_groups(documents, request),
        'orders': ClientOrderSerializer(orders, many=True, context={'request': request}).data,
        'locations': LocationSerializer(locations, many=True, context={'request': request}).data,
        'shifts': ShiftSerializer(shifts, many=True, context={'request': request}).data,
    })
