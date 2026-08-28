from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import ClientCompany, ClientOrder, Contract, Document, EmployeeMasterData, Location, PayrollStatement, Shift, User, WorkerProfile
from .serializers import ClientCompanySerializer, ClientOrderSerializer, ContractSerializer, DocumentSerializer, EmployeeMasterDataSerializer, LocationSerializer, PayrollStatementSerializer, ShiftSerializer, WorkerProfileSerializer
from .shift_slots import ShiftSlot
from .services import audit
from .wiw_sync import calculate_completeness


def _manager(user):
    return user.role in {User.Role.ADMIN, User.Role.MANAGER}


def _document_groups(documents, request):
    labels = dict(Document.Folder.choices)
    groups = []
    for value, _label in Document.Folder.choices:
        rows = documents.filter(folder=value).order_by('-created_at')
        if rows.exists():
            groups.append({'key': value, 'label': labels.get(value, value), 'count': rows.count(), 'items': DocumentSerializer(rows, many=True, context={'request': request}).data})
    return groups


def _worker_shifts(worker):
    return Shift.objects.filter(Q(worker=worker) | Q(slots__worker=worker, slots__status=ShiftSlot.Status.CLAIMED)).exclude(status=Shift.Status.CANCELLED).distinct()


def _worker_contracts(worker):
    shifts = list(_worker_shifts(worker).only('id', 'wiw_shift_id'))
    covered_shift_ids = {str(shift.id) for shift in shifts}
    covered_shift_ids.update(str(shift.wiw_shift_id) for shift in shifts if shift.wiw_shift_id)
    linked_contract_ids = []
    if covered_shift_ids:
        for contract in Contract.objects.filter(client__isnull=False).exclude(variables={}):
            shift_ids = (contract.variables or {}).get('shift_ids') or []
            if covered_shift_ids.intersection(str(value) for value in shift_ids):
                linked_contract_ids.append(contract.id)
    return Contract.objects.filter(Q(worker=worker) | Q(pk__in=linked_contract_ids)).select_related('template', 'worker__user', 'client').prefetch_related('signatures').distinct().order_by('-updated_at')


def _worker_payload(worker, request, own_worker=False):
    contracts = _worker_contracts(worker)
    documents = Document.objects.filter(worker=worker).select_related('worker__user', 'client')
    if own_worker:
        documents = documents.exclude(visibility=Document.Visibility.ADMIN)
    payroll = PayrollStatement.objects.filter(worker=worker).select_related('worker__user').order_by('-period')
    shift_qs = _worker_shifts(worker)
    shifts = shift_qs.select_related('worker__user', 'client', 'location', 'position').order_by('-starts_at')[:100]
    master, _ = EmployeeMasterData.objects.get_or_create(worker=worker)
    return {
        'kind': 'worker', 'title': worker.user.get_full_name() or worker.user.email, 'number': worker.employee_number,
        'profile': WorkerProfileSerializer(worker, context={'request': request}).data,
        'master_data': EmployeeMasterDataSerializer(master).data,
        'summary': {'contracts': contracts.count(), 'documents': documents.count(), 'payroll': payroll.count(), 'shifts': shift_qs.count()},
        'contracts': ContractSerializer(contracts, many=True, context={'request': request}).data,
        'document_folders': _document_groups(documents, request),
        'payroll': PayrollStatementSerializer(payroll, many=True, context={'request': request}).data,
        'shifts': ShiftSerializer(shifts, many=True, context={'request': request}).data,
    }


def _client_payload(client, request, own_client=False):
    contracts = Contract.objects.filter(client=client).select_related('template', 'worker__user', 'client').prefetch_related('signatures').order_by('-updated_at')
    documents = Document.objects.filter(client=client).select_related('worker__user', 'client')
    if own_client:
        if not client.contract_visibility_enabled:
            contracts = contracts.none()
        documents = documents.filter(visibility__in=[Document.Visibility.CLIENT, Document.Visibility.SHARED])
    orders = ClientOrder.objects.filter(client=client).select_related('client', 'location').order_by('-starts_at')
    locations = Location.objects.filter(client=client).order_by('name')
    shift_qs = Shift.objects.filter(client=client)
    shifts = shift_qs.select_related('worker__user', 'client', 'location', 'position').order_by('-starts_at')[:120]
    return {
        'kind': 'client', 'title': client.name, 'number': client.customer_number,
        'profile': ClientCompanySerializer(client, context={'request': request}).data,
        'summary': {'contracts': contracts.count(), 'documents': documents.count(), 'orders': orders.count(), 'locations': locations.count(), 'shifts': shift_qs.count()},
        'contracts': ContractSerializer(contracts, many=True, context={'request': request}).data,
        'document_folders': _document_groups(documents, request),
        'orders': ClientOrderSerializer(orders, many=True, context={'request': request}).data,
        'locations': LocationSerializer(locations, many=True, context={'request': request}).data,
        'shifts': ShiftSerializer(shifts, many=True, context={'request': request}).data,
    }


@api_view(['GET', 'PATCH'])
def worker_akte(request, pk):
    worker = get_object_or_404(WorkerProfile.objects.select_related('user'), pk=pk)
    own_worker = request.user.role == User.Role.WORKER and worker.user_id == request.user.id
    if not _manager(request.user) and not own_worker:
        return Response({'detail': 'Keine Berechtigung für diese Mitarbeiterakte.'}, status=403)
    if request.method == 'PATCH':
        if not _manager(request.user):
            return Response({'detail': 'Nur Administration oder Disposition darf Mitarbeiterakten bearbeiten.'}, status=403)
        payload = request.data.get('profile') if isinstance(request.data.get('profile'), dict) else request.data
        master_payload = request.data.get('master_data') if isinstance(request.data.get('master_data'), dict) else {}
        with transaction.atomic():
            user_fields = {'first_name', 'last_name', 'email', 'phone'}
            worker_fields = {'employee_number', 'employment_type', 'monthly_hours', 'tariff_hourly_rate', 'extra_allowance', 'ranking_points', 'active', 'skills', 'open_shift_client_ids', 'schedule_groups'}
            for key in user_fields:
                if key in payload:
                    setattr(worker.user, key, payload[key])
            if 'email' in payload:
                email = str(payload['email'] or '').strip().lower()
                if not email:
                    return Response({'detail': 'E-Mail-Adresse darf nicht leer sein.'}, status=400)
                if User.objects.exclude(pk=worker.user_id).filter(email=email).exists():
                    return Response({'detail': 'Diese E-Mail-Adresse ist bereits vergeben.'}, status=400)
                worker.user.email = email
                worker.user.username = email
            worker.user.save()
            for key in worker_fields:
                if key in payload:
                    setattr(worker, key, payload[key] if payload[key] != '' else None)
            worker.save()
            if master_payload:
                master, _ = EmployeeMasterData.objects.get_or_create(worker=worker)
                data = dict(master.data or {})
                sources = dict(master.source_map or {})
                for key, value in master_payload.items():
                    data[key] = value
                    sources[key] = 'administration'
                completeness, missing = calculate_completeness(data)
                master.data, master.source_map, master.completeness, master.missing_fields = data, sources, completeness, missing
                master.verified_at = None
                master.verified_by = None
                master.save()
            audit(request, 'worker_akte.updated', worker, {'fields': sorted(payload.keys()), 'master_fields': sorted(master_payload.keys())})
        worker.refresh_from_db()
    return Response(_worker_payload(worker, request, own_worker=own_worker))


@api_view(['GET', 'PATCH'])
def client_akte(request, pk):
    client = get_object_or_404(ClientCompany.objects.prefetch_related('contacts'), pk=pk)
    own_client = request.user.role == User.Role.CLIENT and client.contacts.filter(pk=request.user.pk).exists()
    if not _manager(request.user) and not own_client:
        return Response({'detail': 'Keine Berechtigung für diese Kundenakte.'}, status=403)
    if request.method == 'PATCH':
        if not _manager(request.user):
            return Response({'detail': 'Nur Administration oder Disposition darf Kundenakten bearbeiten.'}, status=403)
        payload = request.data.get('profile') if isinstance(request.data.get('profile'), dict) else request.data
        with transaction.atomic():
            client_fields = {'name', 'customer_number', 'address', 'vat_id', 'notes', 'active', 'contract_visibility_enabled'}
            for key in client_fields:
                if key in payload:
                    setattr(client, key, payload[key])
            if 'customer_number' in payload and ClientCompany.objects.exclude(pk=client.pk).filter(customer_number=payload['customer_number']).exists():
                return Response({'detail': 'Diese Kundennummer ist bereits vergeben.'}, status=400)
            client.save()
            contact = client.contacts.order_by('date_joined').first()
            if contact:
                mapping = {'contact_first_name': 'first_name', 'contact_last_name': 'last_name', 'contact_email': 'email', 'contact_phone': 'phone'}
                for incoming, field in mapping.items():
                    if incoming in payload:
                        setattr(contact, field, payload[incoming])
                if 'contact_email' in payload:
                    email = str(payload['contact_email'] or '').strip().lower()
                    if email and User.objects.exclude(pk=contact.pk).filter(email=email).exists():
                        return Response({'detail': 'Diese Kontakt-E-Mail ist bereits vergeben.'}, status=400)
                    contact.email = email
                    contact.username = email
                contact.save()
            audit(request, 'client_akte.updated', client, {'fields': sorted(payload.keys())})
        client.refresh_from_db()
    return Response(_client_payload(client, request, own_client=own_client))
