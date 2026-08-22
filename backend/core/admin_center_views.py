from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .attendance_models import TimeEntryCorrection
from .models import (
    ClientCompany,
    ClientOrder,
    Contract,
    EmployeeMasterData,
    IntegrationSyncRun,
    Shift,
    ShiftSwapRequest,
    TimeEntry,
    TimeOffRequest,
    User,
    WorkerProfile,
)
from .shift_slots import ShiftSlot


MANAGER_ROLES = {User.Role.ADMIN, User.Role.MANAGER}
SEVERITY_ORDER = {'critical': 0, 'warning': 1, 'info': 2}


def _manager_required(request):
    if request.user.role not in MANAGER_ROLES:
        return Response({'detail': 'Nur Administration und Disposition dürfen diese Ansicht verwenden.'}, status=403)
    return None


def _exception(category, severity, title, message, view, object_id=None, *, due_at=None, meta=None):
    return {
        'category': category,
        'severity': severity,
        'title': title,
        'message': message,
        'view': view,
        'object_id': str(object_id) if object_id else None,
        'due_at': due_at,
        'meta': meta or {},
    }


def _exception_center_items(now):
    items = []

    # Staffing demand: published/confirmed future shifts with open capacity.
    staffing = list(
        Shift.objects.filter(
            status__in=[Shift.Status.PUBLISHED, Shift.Status.CONFIRMED],
            ends_at__gte=now,
        ).select_related('client', 'location', 'position').annotate(
            slot_open_count=Count(
                'slots',
                filter=Q(slots__status=ShiftSlot.Status.OPEN, slots__worker__isnull=True),
                distinct=True,
            ),
            slot_filled_count=Count(
                'slots',
                filter=Q(slots__status=ShiftSlot.Status.CLAIMED, slots__worker__isnull=False),
                distinct=True,
            ),
        ).order_by('starts_at')[:120]
    )
    for shift in staffing:
        legacy_filled = 1 if shift.worker_id and shift.slot_filled_count == 0 else 0
        effective_filled = min(shift.required_count, shift.slot_filled_count + legacy_filled)
        effective_open = max(0, shift.required_count - effective_filled)
        if not effective_open:
            continue
        hours_until = (shift.starts_at - now).total_seconds() / 3600
        severity = 'critical' if hours_until <= 24 else 'warning'
        items.append(_exception(
            'staffing',
            severity,
            f'{effective_open} Platz/Plätze noch offen',
            f'{shift.position.name} · {shift.client.name} · {shift.location.name}',
            'schedule',
            shift.id,
            due_at=shift.starts_at,
            meta={
                'open_count': effective_open,
                'filled_count': effective_filled,
                'required_count': shift.required_count,
                'starts_at': shift.starts_at,
            },
        ))

    # Attendance: a claimed worker has no check-in after the shift has started.
    late_slots = list(
        ShiftSlot.objects.filter(
            status=ShiftSlot.Status.CLAIMED,
            worker__isnull=False,
            shift__status__in=[Shift.Status.PUBLISHED, Shift.Status.CONFIRMED],
            shift__starts_at__lte=now - timedelta(minutes=15),
            shift__ends_at__gte=now - timedelta(hours=12),
        ).select_related(
            'worker__user', 'shift__client', 'shift__location', 'shift__position'
        ).order_by('-shift__starts_at')[:120]
    )
    shift_ids = {slot.shift_id for slot in late_slots}
    entry_pairs = set(
        TimeEntry.objects.filter(shift_id__in=shift_ids).values_list('shift_id', 'worker_id')
    ) if shift_ids else set()
    for slot in late_slots:
        if (slot.shift_id, slot.worker_id) in entry_pairs:
            continue
        minutes_late = max(15, int((now - slot.shift.starts_at).total_seconds() // 60))
        items.append(_exception(
            'attendance',
            'critical' if minutes_late >= 60 else 'warning',
            'Kein Check-in erfasst',
            f'{slot.worker.user.get_full_name() or slot.worker.user.email} · {slot.shift.position.name} · seit {minutes_late} Min.',
            'time',
            slot.shift_id,
            due_at=slot.shift.starts_at,
            meta={
                'worker_id': str(slot.worker_id),
                'worker_name': slot.worker.user.get_full_name() or slot.worker.user.email,
                'minutes_late': minutes_late,
                'location': slot.shift.location.name,
            },
        ))

    # Legacy directly-assigned shifts remain visible during the transition even if a claimed slot is missing.
    late_legacy = Shift.objects.filter(
        worker__isnull=False,
        status__in=[Shift.Status.PUBLISHED, Shift.Status.CONFIRMED],
        starts_at__lte=now - timedelta(minutes=15),
        ends_at__gte=now - timedelta(hours=12),
    ).exclude(
        slots__status=ShiftSlot.Status.CLAIMED,
        slots__worker__isnull=False,
    ).select_related('worker__user', 'client', 'location', 'position').distinct().order_by('-starts_at')[:80]
    legacy_pairs = set(
        TimeEntry.objects.filter(shift_id__in=[shift.id for shift in late_legacy]).values_list('shift_id', 'worker_id')
    )
    for shift in late_legacy:
        if (shift.id, shift.worker_id) in legacy_pairs:
            continue
        minutes_late = max(15, int((now - shift.starts_at).total_seconds() // 60))
        items.append(_exception(
            'attendance',
            'critical' if minutes_late >= 60 else 'warning',
            'Kein Check-in erfasst',
            f'{shift.worker.user.get_full_name() or shift.worker.user.email} · {shift.position.name} · seit {minutes_late} Min.',
            'time',
            shift.id,
            due_at=shift.starts_at,
            meta={
                'worker_id': str(shift.worker_id),
                'worker_name': shift.worker.user.get_full_name() or shift.worker.user.email,
                'minutes_late': minutes_late,
                'location': shift.location.name,
                'legacy_assignment': True,
            },
        ))

    for correction in TimeEntryCorrection.objects.filter(
        status=TimeEntryCorrection.Status.PENDING
    ).select_related('requested_by__user', 'entry').order_by('created_at')[:60]:
        items.append(_exception(
            'attendance',
            'warning',
            'Arbeitszeit-Korrektur wartet',
            f'{correction.requested_by.user.get_full_name() or correction.requested_by.user.email} · {correction.reason[:140]}',
            'time',
            correction.id,
            due_at=correction.created_at,
            meta={'entry_id': str(correction.entry_id), 'worker_id': str(correction.requested_by_id)},
        ))

    for entry in TimeEntry.objects.filter(
        approved=False,
        clock_out__isnull=False,
    ).select_related('worker__user', 'shift__position').order_by('clock_out')[:60]:
        age_hours = (now - entry.clock_out).total_seconds() / 3600 if entry.clock_out else 0
        items.append(_exception(
            'attendance',
            'warning' if age_hours >= 24 else 'info',
            'Arbeitszeit noch nicht freigegeben',
            f'{entry.worker.user.get_full_name() or entry.worker.user.email} · {entry.shift.position.name if entry.shift_id else "Arbeitszeit"}',
            'time',
            entry.id,
            due_at=entry.clock_out,
            meta={'worker_id': str(entry.worker_id), 'worked_minutes': entry.worked_minutes},
        ))

    # Contracts: signature/action and deadlines.
    today = timezone.localdate()
    due_date = today + timedelta(days=30)
    contracts = Contract.objects.filter(
        Q(status__in=[Contract.Status.READY, Contract.Status.SENT])
        | Q(
            ends_on__range=(today, due_date),
            status__in=[Contract.Status.READY, Contract.Status.SENT, Contract.Status.SIGNED],
        )
    ).select_related('worker__user', 'client', 'template').order_by('ends_on', 'created_at')[:100]
    for contract in contracts:
        subject = (
            contract.worker.user.get_full_name() or contract.worker.user.email
            if contract.worker_id
            else contract.client.name if contract.client_id else contract.title
        )
        if contract.status in [Contract.Status.READY, Contract.Status.SENT]:
            items.append(_exception(
                'contracts',
                'warning',
                'Vertrag wartet auf Aktion',
                f'{contract.title} · {subject}',
                'contracts',
                contract.id,
                due_at=contract.reminder_date or contract.ends_on,
                meta={'status': contract.status, 'template': contract.template.name},
            ))
        if contract.ends_on and today <= contract.ends_on <= due_date:
            days = (contract.ends_on - today).days
            items.append(_exception(
                'contracts',
                'critical' if days <= 7 else 'warning',
                'Vertragsfrist nähert sich',
                f'{contract.title} · {subject} · noch {days} Tag(e)',
                'contracts',
                contract.id,
                due_at=contract.ends_on,
                meta={'days_remaining': days, 'status': contract.status},
            ))

    # Personnel/document readiness: incomplete digital employee files.
    workers = list(WorkerProfile.objects.filter(active=True).select_related('user').order_by('user__last_name')[:250])
    master_by_worker = {
        row.worker_id: row
        for row in EmployeeMasterData.objects.filter(worker__in=workers)
    }
    for worker in workers:
        master = master_by_worker.get(worker.id)
        completeness = master.completeness if master else 0
        if completeness >= 100:
            continue
        missing = list(master.missing_fields or []) if master else []
        items.append(_exception(
            'documents',
            'warning' if completeness < 70 else 'info',
            'Personalakte unvollständig',
            f'{worker.user.get_full_name() or worker.user.email} · {completeness}% vollständig',
            'people',
            worker.id,
            meta={
                'completeness': completeness,
                'missing_count': len(missing),
                'employee_number': worker.employee_number,
            },
        ))

    # Integration failures should be actionable, but not dominate the screen forever.
    for run in IntegrationSyncRun.objects.filter(
        status=IntegrationSyncRun.Status.FAILED,
        started_at__gte=now - timedelta(days=14),
    ).order_by('-started_at')[:20]:
        error = ''
        if run.errors:
            last = run.errors[-1]
            error = last.get('error', '') if isinstance(last, dict) else str(last)
        items.append(_exception(
            'integrations',
            'critical' if run.started_at >= now - timedelta(hours=24) else 'warning',
            'Synchronisierung fehlgeschlagen',
            f'{run.provider.upper()} · {error[:160] or "Fehler im letzten Synchronisierungslauf"}',
            'operations',
            run.id,
            due_at=run.started_at,
            meta={'provider': run.provider, 'mode': run.mode},
        ))

    for request in TimeOffRequest.objects.filter(status=TimeOffRequest.Status.PENDING).select_related(
        'worker__user'
    ).order_by('created_at')[:40]:
        items.append(_exception(
            'requests',
            'info',
            'Abwesenheitsantrag wartet',
            f'{request.worker.user.get_full_name() or request.worker.user.email} · {request.starts_on:%d.%m.%Y}–{request.ends_on:%d.%m.%Y}',
            'time',
            request.id,
            due_at=request.starts_on,
            meta={'worker_id': str(request.worker_id)},
        ))

    for swap in ShiftSwapRequest.objects.filter(status=ShiftSwapRequest.Status.PENDING).select_related(
        'requested_by__user', 'shift__position'
    ).order_by('created_at')[:40]:
        items.append(_exception(
            'requests',
            'info',
            'Schichttausch wartet',
            f'{swap.requested_by.user.get_full_name() or swap.requested_by.user.email} · {swap.shift.position.name}',
            'operations',
            swap.id,
            due_at=swap.shift.starts_at,
            meta={'shift_id': str(swap.shift_id), 'worker_id': str(swap.requested_by_id)},
        ))

    return items


def _sort_value(item):
    due = item.get('due_at')
    if hasattr(due, 'isoformat'):
        due_value = due.isoformat()
    else:
        due_value = str(due or '9999-12-31')
    return (SEVERITY_ORDER.get(item['severity'], 9), due_value, item['title'])


@api_view(['GET'])
def admin_exception_center(request):
    denied = _manager_required(request)
    if denied:
        return denied

    items = _exception_center_items(timezone.now())
    category = str(request.GET.get('category') or '').strip()
    severity = str(request.GET.get('severity') or '').strip()
    query = str(request.GET.get('q') or '').strip().lower()
    if category and category != 'all':
        allowed = {part.strip() for part in category.split(',') if part.strip()}
        items = [item for item in items if item['category'] in allowed]
    if severity and severity != 'all':
        allowed = {part.strip() for part in severity.split(',') if part.strip()}
        items = [item for item in items if item['severity'] in allowed]
    if query:
        items = [
            item for item in items
            if query in f"{item['title']} {item['message']} {item['category']}".lower()
        ]

    summary = {
        'total': len(items),
        'critical': sum(item['severity'] == 'critical' for item in items),
        'warning': sum(item['severity'] == 'warning' for item in items),
        'info': sum(item['severity'] == 'info' for item in items),
        'by_category': {
            category_name: sum(item['category'] == category_name for item in items)
            for category_name in ['staffing', 'attendance', 'contracts', 'documents', 'integrations', 'requests']
        },
    }
    try:
        limit = min(200, max(1, int(request.GET.get('limit') or 80)))
    except (TypeError, ValueError):
        limit = 80
    items.sort(key=_sort_value)
    return Response({
        'generated_at': timezone.now(),
        'summary': summary,
        'results': items[:limit],
        'returned': min(len(items), limit),
    })


def _search_result(kind, obj, label, subtitle, view, *, status=None, meta=None):
    return {
        'type': kind,
        'id': str(obj.id),
        'label': label,
        'subtitle': subtitle,
        'view': view,
        'status': status,
        'meta': meta or {},
    }


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

    worker_q = Q(user__first_name__icontains=query) | Q(user__last_name__icontains=query) | Q(user__email__icontains=query) | Q(employee_number__icontains=query)
    workers = WorkerProfile.objects.filter(worker_q).select_related('user').order_by('-active', 'user__last_name')[:per_group]
    worker_results = [
        _search_result(
            'worker', worker,
            worker.user.get_full_name() or worker.user.email,
            f'{worker.employee_number} · {worker.user.email}',
            'people',
            status='active' if worker.active else 'inactive',
            meta={'employee_number': worker.employee_number},
        ) for worker in workers
    ]

    client_q = Q(name__icontains=query) | Q(customer_number__icontains=query) | Q(address__icontains=query)
    clients = ClientCompany.objects.filter(client_q).order_by('-active', 'name')[:per_group]
    client_results = [
        _search_result('client', client, client.name, client.customer_number, 'people', status='active' if client.active else 'inactive')
        for client in clients
    ]

    order_q = Q(title__icontains=query) | Q(description__icontains=query) | Q(client__name__icontains=query) | Q(location__name__icontains=query)
    orders = ClientOrder.objects.filter(order_q).select_related('client', 'location').order_by('-starts_at')[:per_group]
    order_results = [
        _search_result(
            'order', order, order.title,
            f'{order.client.name} · {timezone.localtime(order.starts_at):%d.%m.%Y %H:%M}',
            'orders', status=order.status,
            meta={'client': order.client.name, 'starts_at': order.starts_at},
        ) for order in orders
    ]

    shift_q = Q(client__name__icontains=query) | Q(location__name__icontains=query) | Q(location__address__icontains=query) | Q(position__name__icontains=query) | Q(order__title__icontains=query) | Q(notes__icontains=query)
    parsed_day = parse_date(query)
    if parsed_day:
        shift_q |= Q(starts_at__date=parsed_day)
    shifts = Shift.objects.filter(shift_q).select_related('client', 'location', 'position').annotate(
        open_count=Count('slots', filter=Q(slots__status=ShiftSlot.Status.OPEN), distinct=True),
        filled_count=Count('slots', filter=Q(slots__status=ShiftSlot.Status.CLAIMED), distinct=True),
    ).order_by('-starts_at')[:per_group]
    shift_results = [
        _search_result(
            'shift', shift,
            f'{shift.position.name} · {shift.client.name}',
            f'{shift.location.name} · {timezone.localtime(shift.starts_at):%d.%m.%Y %H:%M}',
            'schedule', status=shift.status,
            meta={'open_count': shift.open_count, 'filled_count': shift.filled_count, 'starts_at': shift.starts_at},
        ) for shift in shifts
    ]

    contract_q = Q(title__icontains=query) | Q(worker__user__first_name__icontains=query) | Q(worker__user__last_name__icontains=query) | Q(worker__user__email__icontains=query) | Q(client__name__icontains=query) | Q(template__name__icontains=query)
    contracts = Contract.objects.filter(contract_q).select_related('worker__user', 'client', 'template').order_by('-created_at')[:per_group]
    contract_results = []
    for contract in contracts:
        subject = (
            contract.worker.user.get_full_name() or contract.worker.user.email
            if contract.worker_id else contract.client.name if contract.client_id else contract.template.name
        )
        contract_results.append(_search_result(
            'contract', contract, contract.title,
            f'{subject} · {contract.template.name}',
            'contracts', status=contract.status,
            meta={'ends_on': contract.ends_on},
        ))

    groups = {
        'workers': worker_results,
        'clients': client_results,
        'orders': order_results,
        'shifts': shift_results,
        'contracts': contract_results,
    }
    results = [item for group in groups.values() for item in group]
    return Response({'query': query, 'results': results, 'groups': groups, 'total': len(results)})
