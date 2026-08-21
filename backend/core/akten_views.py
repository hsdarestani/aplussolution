from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import ClientCompany, ClientOrder, Contract, Document, Location, PayrollStatement, Shift, User, WorkerProfile
from .serializers import ClientCompanySerializer, ClientOrderSerializer, ContractSerializer, DocumentSerializer, LocationSerializer, PayrollStatementSerializer, ShiftSerializer, WorkerProfileSerializer


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


@api_view(['GET'])
def worker_akte(request, pk):
    worker = get_object_or_404(WorkerProfile.objects.select_related('user'), pk=pk)
    if not _manager(request.user) and not (request.user.role == User.Role.WORKER and worker.user_id == request.user.id):
        return Response({'detail': 'Keine Berechtigung für diese Mitarbeiterakte.'}, status=403)

    contracts = Contract.objects.filter(worker=worker).select_related('template', 'worker__user', 'client').prefetch_related('signatures').order_by('-updated_at')
    documents = Document.objects.filter(worker=worker).select_related('worker__user', 'client')
    payroll = PayrollStatement.objects.filter(worker=worker).select_related('worker__user').order_by('-period')
    shifts = Shift.objects.filter(worker=worker).select_related('worker__user', 'client', 'location', 'position').order_by('-starts_at')[:50]

    return Response({
        'kind': 'worker',
        'title': worker.user.get_full_name() or worker.user.email,
        'number': worker.employee_number,
        'profile': WorkerProfileSerializer(worker, context={'request': request}).data,
        'summary': {
            'contracts': contracts.count(),
            'documents': documents.count(),
            'payroll': payroll.count(),
            'shifts': Shift.objects.filter(worker=worker).count(),
        },
        'contracts': ContractSerializer(contracts, many=True, context={'request': request}).data,
        'document_folders': _document_groups(documents, request),
        'payroll': PayrollStatementSerializer(payroll, many=True, context={'request': request}).data,
        'shifts': ShiftSerializer(shifts, many=True, context={'request': request}).data,
    })


@api_view(['GET'])
def client_akte(request, pk):
    client = get_object_or_404(ClientCompany.objects.prefetch_related('contacts'), pk=pk)
    if not _manager(request.user) and not (request.user.role == User.Role.CLIENT and client.contacts.filter(pk=request.user.pk).exists()):
        return Response({'detail': 'Keine Berechtigung für diese Kundenakte.'}, status=403)

    contracts = Contract.objects.filter(client=client).select_related('template', 'worker__user', 'client').prefetch_related('signatures').order_by('-updated_at')
    documents = Document.objects.filter(client=client).select_related('worker__user', 'client')
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
