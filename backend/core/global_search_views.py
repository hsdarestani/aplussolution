from django.db.models import Count, Q
from django.utils.dateparse import parse_date
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .admin_center_views import _manager_required, _search_result
from .models import ClientCompany, ClientOrder, Contract, Shift, WorkerProfile
from .shift_slots import ShiftSlot


SYNTHETIC_MIGRATION_EMAIL_SUFFIX = '@sync.invalid'


@api_view(['GET'])
def global_search(request):
    denied = _manager_required(request)
    if denied:
        return denied

    query = str(request.GET.get('q') or '').strip()
    if len(query) < 2:
        return Response({'query': query, 'results': [], 'groups': {}, 'total': 0})

    try:
        per_group = min(10, max(1, int(request.GET.get('limit') or 5)))
    except (TypeError, ValueError):
        per_group = 5

    worker_q = (
        Q(user__first_name__icontains=query)
        | Q(user__last_name__icontains=query)
        | Q(user__email__icontains=query)
        | Q(employee_number__icontains=query)
    )
    workers = (
        WorkerProfile.objects.filter(worker_q)
        .exclude(user__email__iendswith=SYNTHETIC_MIGRATION_EMAIL_SUFFIX)
        .select_related('user')
        .order_by('-active', 'user__last_name')[:per_group]
    )
    worker_results = [
        _search_result(
            'worker',
            worker,
            worker.user.get_full_name() or worker.user.email,
            f'{worker.employee_number} · {worker.user.email}',
            'people',
            status='active' if worker.active else 'inactive',
            meta={'employee_number': worker.employee_number},
        )
        for worker in workers
    ]

    client_q = (
        Q(name__icontains=query)
        | Q(customer_number__icontains=query)
        | Q(address__icontains=query)
    )
    clients = ClientCompany.objects.filter(client_q).order_by('-active', 'name')[:per_group]
    client_results = [
        _search_result(
            'client',
            client,
            client.name,
            client.customer_number,
            'people',
            status='active' if client.active else 'inactive',
        )
        for client in clients
    ]

    order_q = (
        Q(title__icontains=query)
        | Q(description__icontains=query)
        | Q(client__name__icontains=query)
        | Q(location__name__icontains=query)
    )
    orders = (
        ClientOrder.objects.filter(order_q)
        .select_related('client', 'location')
        .order_by('-starts_at')[:per_group]
    )
    order_results = [
        _search_result(
            'order',
            order,
            order.title,
            f'{order.client.name} · {order.starts_at:%d.%m.%Y %H:%M}',
            'orders',
            status=order.status,
            meta={'client': order.client.name, 'starts_at': order.starts_at},
        )
        for order in orders
    ]

    shift_q = (
        Q(client__name__icontains=query)
        | Q(location__name__icontains=query)
        | Q(location__address__icontains=query)
        | Q(position__name__icontains=query)
        | Q(order__title__icontains=query)
        | Q(notes__icontains=query)
    )
    parsed_day = parse_date(query)
    if parsed_day:
        shift_q |= Q(starts_at__date=parsed_day)

    shifts = (
        Shift.objects.filter(shift_q)
        .select_related('client', 'location', 'position')
        .annotate(
            open_count=Count(
                'slots',
                filter=Q(slots__status=ShiftSlot.Status.OPEN),
                distinct=True,
            ),
            filled_count=Count(
                'slots',
                filter=Q(slots__status=ShiftSlot.Status.CLAIMED),
                distinct=True,
            ),
        )
        .order_by('-starts_at')[:per_group]
    )
    shift_results = [
        _search_result(
            'shift',
            shift,
            f'{shift.position.name} · {shift.client.name}',
            f'{shift.location.name} · {shift.starts_at:%d.%m.%Y %H:%M}',
            'schedule',
            status=shift.status,
            meta={
                'open_count': shift.open_count,
                'filled_count': shift.filled_count,
                'starts_at': shift.starts_at,
            },
        )
        for shift in shifts
    ]

    contract_q = (
        Q(title__icontains=query)
        | Q(worker__user__first_name__icontains=query)
        | Q(worker__user__last_name__icontains=query)
        | Q(worker__user__email__icontains=query)
        | Q(client__name__icontains=query)
        | Q(template__name__icontains=query)
    )
    contracts = (
        Contract.objects.filter(contract_q)
        .exclude(worker__user__email__iendswith=SYNTHETIC_MIGRATION_EMAIL_SUFFIX)
        .select_related('worker__user', 'client', 'template')
        .order_by('-created_at')[:per_group]
    )
    contract_results = []
    for contract in contracts:
        subject = (
            contract.worker.user.get_full_name() or contract.worker.user.email
            if contract.worker_id
            else contract.client.name
            if contract.client_id
            else contract.template.name
        )
        contract_results.append(
            _search_result(
                'contract',
                contract,
                contract.title,
                f'{subject} · {contract.template.name}',
                'contracts',
                status=contract.status,
                meta={'ends_on': contract.ends_on},
            )
        )

    groups = {
        'workers': worker_results,
        'clients': client_results,
        'orders': order_results,
        'shifts': shift_results,
        'contracts': contract_results,
    }
    results = [item for group in groups.values() for item in group]
    return Response({'query': query, 'results': results, 'groups': groups, 'total': len(results)})
