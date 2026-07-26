import csv
import io
import os
from collections import defaultdict
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import (
    Availability,
    ClientCompany,
    ClientOrder,
    Contract,
    ContractTemplate,
    Document,
    Notification,
    PayrollStatement,
    Shift,
    ShiftSwapRequest,
    TimeEntry,
    TimeOffRequest,
    User,
    WorkerProfile,
)
from .serializers import (
    AvailabilitySerializer,
    ContractTemplateSerializer,
    NotificationSerializer,
    ShiftSerializer,
)
from .services import audit


MANAGER_ROLES = {User.Role.ADMIN, User.Role.MANAGER}


def _is_manager(user):
    return user.role in MANAGER_ROLES


def _manager_required(request):
    if not _is_manager(request.user):
        return Response({'detail': 'Nur Administration und Disposition dürfen diese Funktion verwenden.'}, status=403)
    return None


def _as_dt(value, field_name):
    parsed = parse_datetime(str(value or ''))
    if not parsed:
        raise ValueError(f'{field_name} ist ungültig.')
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _as_date(value, field_name):
    parsed = parse_date(str(value or ''))
    if not parsed:
        raise ValueError(f'{field_name} ist ungültig.')
    return parsed


def _month_bounds(value=None):
    today = timezone.localdate()
    if value:
        try:
            start = datetime.strptime(value, '%Y-%m').date().replace(day=1)
        except ValueError as exc:
            raise ValueError('Monat muss im Format JJJJ-MM angegeben werden.') from exc
    else:
        start = today.replace(day=1)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start, end


def _aware_start(day):
    return timezone.make_aware(datetime.combine(day, time.min), timezone.get_current_timezone())


def _serialize_swap(obj):
    return {
        'id': str(obj.id),
        'shift': str(obj.shift_id),
        'shift_title': obj.shift.position.name if obj.shift_id else 'Schicht',
        'shift_starts_at': obj.shift.starts_at if obj.shift_id else None,
        'requested_by': str(obj.requested_by_id),
        'requested_by_name': obj.requested_by.user.get_full_name() or obj.requested_by.user.email,
        'offered_to': str(obj.offered_to_id) if obj.offered_to_id else None,
        'offered_to_name': (
            obj.offered_to.user.get_full_name() or obj.offered_to.user.email
            if obj.offered_to_id
            else None
        ),
        'status': obj.status,
        'note': obj.note,
        'created_at': obj.created_at,
    }


def _schedule_findings(date_from=None, date_to=None):
    now = timezone.now()
    start = date_from or now - timedelta(days=7)
    end = date_to or now + timedelta(days=90)
    shifts = list(
        Shift.objects.filter(starts_at__lt=end, ends_at__gt=start)
        .select_related('worker__user', 'client', 'location', 'position', 'order')
        .order_by('worker_id', 'starts_at')
    )

    conflicts = []
    by_worker = defaultdict(list)
    for shift in shifts:
        if shift.worker_id:
            by_worker[shift.worker_id].append(shift)
    for worker_shifts in by_worker.values():
        for previous, current in zip(worker_shifts, worker_shifts[1:]):
            if current.starts_at < previous.ends_at:
                conflicts.append({
                    'worker': str(current.worker_id),
                    'worker_name': current.worker.user.get_full_name() or current.worker.user.email,
                    'first_shift': str(previous.id),
                    'second_shift': str(current.id),
                    'first_window': [previous.starts_at, previous.ends_at],
                    'second_window': [current.starts_at, current.ends_at],
                    'severity': 'error',
                    'message': 'Zwei Schichten überschneiden sich.',
                })

    unavailable = []
    unavailable_rows = Availability.objects.filter(
        available=False,
        starts_at__lt=end,
        ends_at__gt=start,
    ).select_related('worker__user')
    for availability in unavailable_rows:
        matches = [
            shift for shift in by_worker.get(availability.worker_id, [])
            if shift.starts_at < availability.ends_at and shift.ends_at > availability.starts_at
        ]
        for shift in matches:
            unavailable.append({
                'worker': str(availability.worker_id),
                'worker_name': availability.worker.user.get_full_name() or availability.worker.user.email,
                'shift': str(shift.id),
                'starts_at': shift.starts_at,
                'ends_at': shift.ends_at,
                'message': 'Mitarbeiter ist in diesem Zeitraum als nicht verfügbar eingetragen.',
                'severity': 'warning',
            })

    coverage = []
    orders = ClientOrder.objects.filter(
        starts_at__lt=end,
        ends_at__gt=start,
        status__in=[ClientOrder.Status.NEW, ClientOrder.Status.PLANNING, ClientOrder.Status.CONFIRMED],
    ).select_related('client', 'location')
    for order in orders:
        assigned = Shift.objects.filter(order=order, worker__isnull=False).count()
        open_count = Shift.objects.filter(order=order, is_open=True).count()
        gap = max(0, order.requested_staff - assigned)
        if gap:
            coverage.append({
                'order': str(order.id),
                'client': str(order.client_id),
                'title': order.title,
                'client_name': order.client.name,
                'requested': order.requested_staff,
                'assigned': assigned,
                'open_shifts': open_count,
                'gap': gap,
                'starts_at': order.starts_at,
                'severity': 'warning',
                'message': f'{gap} Position(en) sind noch nicht fest besetzt.',
            })

    month_start, month_end = _month_bounds()
    month_start_dt = _aware_start(month_start)
    month_end_dt = _aware_start(month_end)
    overtime = []
    for worker in WorkerProfile.objects.filter(active=True, monthly_hours__isnull=False).select_related('user'):
        minutes = 0
        for shift in Shift.objects.filter(
            worker=worker,
            starts_at__lt=month_end_dt,
            ends_at__gte=month_start_dt,
        ).exclude(status=Shift.Status.CANCELLED):
            minutes += max(0, int((shift.ends_at - shift.starts_at).total_seconds() // 60) - shift.break_minutes)
        target = int(Decimal(worker.monthly_hours) * 60)
        if minutes > target:
            overtime.append({
                'worker': str(worker.id),
                'worker_name': worker.user.get_full_name() or worker.user.email,
                'scheduled_minutes': minutes,
                'target_minutes': target,
                'difference_minutes': minutes - target,
                'severity': 'warning',
                'message': 'Geplante Monatsstunden überschreiten das hinterlegte Stundenkonto.',
            })

    return {
        'conflicts': conflicts,
        'unavailable_assignments': unavailable,
        'coverage_gaps': coverage,
        'overtime_risks': overtime,
    }


def _readiness():
    template_counts = {
        kind: ContractTemplate.objects.filter(kind=kind, active=True).count()
        for kind, _ in ContractTemplate.Kind.choices
    }
    return {
        'google_login': bool(settings.GOOGLE_OAUTH_CLIENT_ID and settings.GOOGLE_OAUTH_CLIENT_SECRET and settings.GOOGLE_OAUTH_REDIRECT_URI),
        'apple_login': bool(
            settings.APPLE_SERVICE_ID
            and settings.APPLE_TEAM_ID
            and settings.APPLE_KEY_ID
            and (settings.APPLE_PRIVATE_KEY or settings.APPLE_PRIVATE_KEY_PATH)
            and settings.APPLE_OAUTH_REDIRECT_URI
        ),
        'email_delivery': bool(settings.EMAIL_HOST and settings.EMAIL_HOST_USER),
        'company_legal_data': bool(settings.COMPANY_NAME and settings.COMPANY_ADDRESS),
        'aueg_data': bool(settings.AUEG_LICENSE_AUTHORITY and settings.AUEG_LICENSE_DATE),
        'contract_templates': template_counts,
        'final_contract_set_complete': ContractTemplate.objects.filter(active=True, required_document=True).exclude(source_file='').count() >= 8,
        'wiw_configured': bool(settings.WIW_DEV_KEY and settings.WIW_EMAIL and settings.WIW_PASSWORD),
        'android_signing_configured': bool(os.getenv('ANDROID_KEYSTORE_BASE64') and os.getenv('ANDROID_KEY_ALIAS')),
        'ios_signing_configured': bool(os.getenv('IOS_CERTIFICATE_BASE64') and os.getenv('IOS_PROVISIONING_PROFILE_BASE64')),
        'store_api_credentials_configured': bool(
            os.getenv('APPLE_ISSUER_ID')
            and os.getenv('APPLE_API_KEY_ID')
            and os.getenv('GOOGLE_PLAY_SERVICE_ACCOUNT_JSON')
        ),
    }


@api_view(['GET'])
def operations_overview(request):
    user = request.user
    now = timezone.now()
    notifications = Notification.objects.filter(user=user).order_by('-created_at')[:30]
    data = {
        'role': user.role,
        'notifications': NotificationSerializer(notifications, many=True).data,
        'unread_notifications': Notification.objects.filter(user=user, read_at__isnull=True).count(),
        'readiness': _readiness() if _is_manager(user) else None,
    }

    if _is_manager(user):
        findings = _schedule_findings()
        current_month_start, current_month_end = _month_bounds()
        month_start_dt = _aware_start(current_month_start)
        month_end_dt = _aware_start(current_month_end)
        estimated_cost = Decimal('0')
        for shift in Shift.objects.filter(
            worker__isnull=False,
            starts_at__lt=month_end_dt,
            ends_at__gte=month_start_dt,
        ).exclude(status=Shift.Status.CANCELLED).select_related('worker'):
            minutes = max(0, int((shift.ends_at - shift.starts_at).total_seconds() // 60) - shift.break_minutes)
            rate = shift.worker.tariff_hourly_rate or Decimal('0')
            allowance = shift.worker.extra_allowance or Decimal('0')
            estimated_cost += (Decimal(minutes) / Decimal(60)) * (rate + allowance)
        data.update({
            **findings,
            'estimated_monthly_labor_cost': str(estimated_cost.quantize(Decimal('0.01'))),
            'pending_swaps': ShiftSwapRequest.objects.filter(status=ShiftSwapRequest.Status.PENDING).count(),
            'swaps': [
                _serialize_swap(item)
                for item in ShiftSwapRequest.objects.select_related(
                    'shift__position', 'requested_by__user', 'offered_to__user'
                ).order_by('-created_at')[:50]
            ],
            'swap_candidates': [
                {'id': str(worker.id), 'name': worker.user.get_full_name() or worker.user.email}
                for worker in WorkerProfile.objects.filter(active=True).select_related('user').order_by('user__first_name')
            ],
            'pending_time_off': TimeOffRequest.objects.filter(status=TimeOffRequest.Status.PENDING).count(),
            'unapproved_time_entries': TimeEntry.objects.filter(approved=False, clock_out__isnull=False).count(),
            'missing_clock_outs': TimeEntry.objects.filter(clock_out__isnull=True, clock_in__lt=now - timedelta(hours=16)).count(),
            'contracts_due_30': Contract.objects.filter(
                ends_on__range=(timezone.localdate(), timezone.localdate() + timedelta(days=30)),
                status__in=[Contract.Status.READY, Contract.Status.SENT, Contract.Status.SIGNED],
            ).count(),
            'active_workers': WorkerProfile.objects.filter(active=True).count(),
            'active_clients': ClientCompany.objects.filter(active=True).count(),
        })
    elif user.role == User.Role.WORKER:
        worker = user.worker_profile
        data.update({
            'current_worker_id': str(worker.id),
            'swap_candidates': [
                {'id': str(candidate.id), 'name': candidate.user.get_full_name() or candidate.user.email}
                for candidate in WorkerProfile.objects.filter(active=True).exclude(pk=worker.pk).select_related('user').order_by('user__first_name')
            ],
            'availabilities': AvailabilitySerializer(
                Availability.objects.filter(worker=worker).order_by('-starts_at')[:30], many=True
            ).data,
            'swaps': [
                _serialize_swap(item)
                for item in ShiftSwapRequest.objects.filter(
                    Q(requested_by=worker) | Q(offered_to=worker)
                ).select_related('shift__position', 'requested_by__user', 'offered_to__user').order_by('-created_at')[:30]
            ],
            'upcoming_shifts': ShiftSerializer(
                Shift.objects.filter(worker=worker, starts_at__gte=now).order_by('starts_at')[:20], many=True
            ).data,
        })
    else:
        companies = user.client_companies.all()
        company_ids = {str(pk) for pk in companies.values_list('pk', flat=True)}
        client_findings = _schedule_findings()['coverage_gaps']
        data.update({
            'coverage_gaps': [item for item in client_findings if item.get('client') in company_ids],
            'contracts_due': Contract.objects.filter(
                client__in=companies,
                ends_on__range=(timezone.localdate(), timezone.localdate() + timedelta(days=30)),
            ).count(),
            'documents': Document.objects.filter(client__in=companies).count(),
            'open_orders': ClientOrder.objects.filter(
                client__in=companies,
                status__in=[ClientOrder.Status.NEW, ClientOrder.Status.PLANNING, ClientOrder.Status.CONFIRMED],
            ).count(),
        })
    return Response(data)


@api_view(['GET'])
def schedule_quality(request):
    denied = _manager_required(request)
    if denied:
        return denied
    try:
        date_from = _as_dt(request.GET.get('date_from'), 'Von') if request.GET.get('date_from') else None
        date_to = _as_dt(request.GET.get('date_to'), 'Bis') if request.GET.get('date_to') else None
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=400)
    return Response(_schedule_findings(date_from, date_to))


@api_view(['POST'])
def availability_create(request):
    if request.user.role != User.Role.WORKER:
        return Response({'detail': 'Verfügbarkeit kann nur im Mitarbeiterportal erfasst werden.'}, status=403)
    try:
        starts_at = _as_dt(request.data.get('starts_at'), 'Beginn')
        ends_at = _as_dt(request.data.get('ends_at'), 'Ende')
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=400)
    if ends_at <= starts_at:
        return Response({'detail': 'Ende muss nach dem Beginn liegen.'}, status=400)
    item = Availability.objects.create(
        worker=request.user.worker_profile,
        starts_at=starts_at,
        ends_at=ends_at,
        available=bool(request.data.get('available', True)),
        note=str(request.data.get('note', '')).strip(),
    )
    audit(request, 'availability.created', item)
    return Response(AvailabilitySerializer(item).data, status=201)


@api_view(['DELETE'])
def availability_delete(request, pk):
    try:
        item = Availability.objects.get(pk=pk)
    except Availability.DoesNotExist:
        return Response({'detail': 'Eintrag wurde nicht gefunden.'}, status=404)
    if not _is_manager(request.user) and item.worker.user_id != request.user.id:
        return Response({'detail': 'Keine Berechtigung.'}, status=403)
    audit(request, 'availability.deleted', item)
    item.delete()
    return Response(status=204)


@api_view(['POST'])
def swap_create(request):
    if request.user.role != User.Role.WORKER:
        return Response({'detail': 'Schichttausch kann nur von Mitarbeitern angefragt werden.'}, status=403)
    try:
        shift = Shift.objects.select_related('worker__user', 'position').get(pk=request.data.get('shift'))
    except Shift.DoesNotExist:
        return Response({'detail': 'Schicht wurde nicht gefunden.'}, status=404)
    worker = request.user.worker_profile
    if shift.worker_id != worker.id:
        return Response({'detail': 'Du kannst nur eine eigene Schicht tauschen.'}, status=403)
    offered_to = None
    if request.data.get('offered_to'):
        try:
            offered_to = WorkerProfile.objects.get(pk=request.data.get('offered_to'), active=True)
        except WorkerProfile.DoesNotExist:
            return Response({'detail': 'Zielmitarbeiter wurde nicht gefunden.'}, status=404)
        if offered_to.id == worker.id:
            return Response({'detail': 'Eine Schicht kann nicht mit dir selbst getauscht werden.'}, status=400)
    obj = ShiftSwapRequest.objects.create(
        shift=shift,
        requested_by=worker,
        offered_to=offered_to,
        note=str(request.data.get('note', '')).strip(),
    )
    recipients = User.objects.filter(role__in=MANAGER_ROLES, is_active=True)
    if offered_to:
        recipients = recipients | User.objects.filter(pk=offered_to.user_id)
    for recipient in recipients.distinct():
        Notification.objects.create(
            user=recipient,
            kind='shift-swap',
            title='Neue Schichttauschanfrage',
            body=f'{worker.user.get_full_name() or worker.user.email}: {shift.position.name}',
            action_url='/operations',
        )
    audit(request, 'shift_swap.created', obj)
    return Response(_serialize_swap(obj), status=201)


@api_view(['POST'])
def swap_decide(request, pk):
    try:
        obj = ShiftSwapRequest.objects.select_related(
            'shift__worker__user', 'shift__position', 'requested_by__user', 'offered_to__user'
        ).get(pk=pk)
    except ShiftSwapRequest.DoesNotExist:
        return Response({'detail': 'Tauschanfrage wurde nicht gefunden.'}, status=404)
    decision = str(request.data.get('status', '')).lower()
    user = request.user
    if _is_manager(user) and request.data.get('offered_to'):
        try:
            obj.offered_to = WorkerProfile.objects.get(pk=request.data.get('offered_to'), active=True)
            obj.save(update_fields=['offered_to'])
        except WorkerProfile.DoesNotExist:
            return Response({'detail': 'Zielmitarbeiter wurde nicht gefunden.'}, status=404)
    if decision == ShiftSwapRequest.Status.CANCELLED:
        if obj.requested_by.user_id != user.id and not _is_manager(user):
            return Response({'detail': 'Keine Berechtigung.'}, status=403)
        obj.status = ShiftSwapRequest.Status.CANCELLED
        obj.save(update_fields=['status'])
    elif decision in {ShiftSwapRequest.Status.APPROVED, ShiftSwapRequest.Status.REJECTED}:
        can_decide = _is_manager(user) or (obj.offered_to_id and obj.offered_to.user_id == user.id)
        if not can_decide:
            return Response({'detail': 'Keine Berechtigung.'}, status=403)
        if decision == ShiftSwapRequest.Status.APPROVED and not obj.offered_to_id:
            return Response({'detail': 'Für die Freigabe muss ein Zielmitarbeiter ausgewählt sein.'}, status=400)
        with transaction.atomic():
            if decision == ShiftSwapRequest.Status.APPROVED:
                overlap = Shift.objects.filter(
                    worker=obj.offered_to,
                    starts_at__lt=obj.shift.ends_at,
                    ends_at__gt=obj.shift.starts_at,
                ).exclude(pk=obj.shift_id).exists()
                if overlap:
                    return Response({'detail': 'Der Zielmitarbeiter hat in diesem Zeitraum bereits eine Schicht.'}, status=400)
                obj.shift.worker = obj.offered_to
                obj.shift.is_open = False
                obj.shift.status = Shift.Status.CONFIRMED
                obj.shift.save(update_fields=['worker', 'is_open', 'status'])
            obj.status = decision
            obj.save(update_fields=['status'])
    else:
        return Response({'detail': 'Ungültige Entscheidung.'}, status=400)
    Notification.objects.create(
        user=obj.requested_by.user,
        kind='shift-swap-decision',
        title='Schichttausch aktualisiert',
        body=f'Status: {obj.get_status_display()}',
        action_url='/operations',
    )
    audit(request, 'shift_swap.decided', obj, {'status': obj.status})
    return Response(_serialize_swap(obj))


@api_view(['POST'])
def copy_week(request):
    denied = _manager_required(request)
    if denied:
        return denied
    try:
        source_start = _as_date(request.data.get('source_start'), 'Quellwoche')
        target_start = _as_date(request.data.get('target_start'), 'Zielwoche')
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=400)
    source_start -= timedelta(days=source_start.weekday())
    target_start -= timedelta(days=target_start.weekday())
    source_end = source_start + timedelta(days=7)
    delta = target_start - source_start
    source_qs = Shift.objects.filter(
        starts_at__gte=_aware_start(source_start),
        starts_at__lt=_aware_start(source_end),
    ).select_related('worker')
    created = []
    warnings = []
    with transaction.atomic():
        for original in source_qs:
            starts_at = original.starts_at + delta
            ends_at = original.ends_at + delta
            worker = original.worker
            if worker and Shift.objects.filter(
                worker=worker,
                starts_at__lt=ends_at,
                ends_at__gt=starts_at,
            ).exists():
                warnings.append({
                    'shift': str(original.id),
                    'message': f'{worker.user}: Zielzeit kollidiert; Kopie wurde als OpenShift angelegt.',
                })
                worker = None
            clone = Shift.objects.create(
                order=original.order,
                client=original.client,
                location=original.location,
                position=original.position,
                worker=worker,
                starts_at=starts_at,
                ends_at=ends_at,
                break_minutes=original.break_minutes,
                status=Shift.Status.DRAFT,
                is_open=worker is None,
                notes=original.notes,
                required_count=original.required_count,
            )
            created.append(str(clone.id))
    audit(request, 'schedule.week_copied', request.user, {'created': len(created)})
    return Response({'created': created, 'warnings': warnings}, status=201)


@api_view(['POST'])
def bulk_publish(request):
    denied = _manager_required(request)
    if denied:
        return denied
    ids = request.data.get('ids') or []
    queryset = Shift.objects.filter(pk__in=ids) if ids else Shift.objects.none()
    count = queryset.update(status=Shift.Status.PUBLISHED, published_at=timezone.now())
    for shift in queryset.select_related('worker__user'):
        if shift.worker_id:
            Notification.objects.get_or_create(
                user=shift.worker.user,
                kind=f'shift-published-{shift.id}',
                defaults={
                    'title': 'Neue Schicht veröffentlicht',
                    'body': f'{shift.starts_at:%d.%m.%Y %H:%M}',
                    'action_url': '/schedule',
                },
            )
    audit(request, 'schedule.bulk_published', request.user, {'count': count})
    return Response({'published': count})


@api_view(['POST'])
def notifications_read_all(request):
    count = Notification.objects.filter(user=request.user, read_at__isnull=True).update(read_at=timezone.now())
    return Response({'updated': count})


def _csv_response(filename, headers, rows):
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response.write('\ufeff')
    writer = csv.writer(response, delimiter=';')
    writer.writerow(headers)
    writer.writerows(rows)
    return response


@api_view(['GET'])
def export_timesheets(request):
    denied = _manager_required(request)
    if denied:
        return denied
    try:
        month_start, month_end = _month_bounds(request.GET.get('month'))
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=400)
    qs = TimeEntry.objects.filter(
        clock_in__gte=_aware_start(month_start),
        clock_in__lt=_aware_start(month_end),
    ).select_related('worker__user', 'shift__position').order_by('worker__employee_number', 'clock_in')
    if request.GET.get('worker'):
        qs = qs.filter(worker_id=request.GET['worker'])
    rows = []
    for entry in qs:
        rows.append([
            entry.worker.employee_number,
            entry.worker.user.get_full_name() or entry.worker.user.email,
            entry.clock_in.astimezone().strftime('%d.%m.%Y %H:%M'),
            entry.clock_out.astimezone().strftime('%d.%m.%Y %H:%M') if entry.clock_out else '',
            entry.worked_minutes,
            'Ja' if entry.approved else 'Nein',
            entry.shift.position.name if entry.shift_id else '',
            entry.edit_reason,
        ])
    return _csv_response(
        f'zeiterfassung-{month_start:%Y-%m}.csv',
        ['Personalnummer', 'Mitarbeiter', 'Beginn', 'Ende', 'Arbeitsminuten', 'Freigegeben', 'Position', 'Korrekturgrund'],
        rows,
    )


@api_view(['GET'])
def export_schedule(request):
    denied = _manager_required(request)
    if denied:
        return denied
    try:
        date_from = _as_date(request.GET.get('date_from') or timezone.localdate().isoformat(), 'Von')
        date_to = _as_date(request.GET.get('date_to') or (date_from + timedelta(days=30)).isoformat(), 'Bis')
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=400)
    qs = Shift.objects.filter(
        starts_at__gte=_aware_start(date_from),
        starts_at__lt=_aware_start(date_to + timedelta(days=1)),
    ).select_related('worker__user', 'client', 'location', 'position').order_by('starts_at')
    rows = [[
        shift.starts_at.astimezone().strftime('%d.%m.%Y %H:%M'),
        shift.ends_at.astimezone().strftime('%d.%m.%Y %H:%M'),
        shift.client.name,
        shift.location.name,
        shift.position.name,
        shift.worker.user.get_full_name() if shift.worker_id else 'OpenShift',
        shift.get_status_display(),
        shift.break_minutes,
    ] for shift in qs]
    return _csv_response(
        f'dienstplan-{date_from:%Y%m%d}-{date_to:%Y%m%d}.csv',
        ['Beginn', 'Ende', 'Kunde', 'Einsatzort', 'Position', 'Mitarbeiter', 'Status', 'Pause (Min.)'],
        rows,
    )


@api_view(['GET'])
def export_payroll_estimate(request):
    denied = _manager_required(request)
    if denied:
        return denied
    try:
        month_start, month_end = _month_bounds(request.GET.get('month'))
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=400)
    rows = []
    for worker in WorkerProfile.objects.filter(active=True).select_related('user').order_by('employee_number'):
        entries = TimeEntry.objects.filter(
            worker=worker,
            approved=True,
            clock_in__gte=_aware_start(month_start),
            clock_in__lt=_aware_start(month_end),
        )
        minutes = sum(entry.worked_minutes for entry in entries)
        hours = Decimal(minutes) / Decimal(60)
        rate = worker.tariff_hourly_rate or Decimal('0')
        allowance = worker.extra_allowance or Decimal('0')
        base = hours * rate
        allowance_total = hours * allowance
        estimate = base + allowance_total
        rows.append([
            worker.employee_number,
            worker.user.get_full_name() or worker.user.email,
            f'{hours.quantize(Decimal("0.01"))}',
            f'{rate.quantize(Decimal("0.01"))}',
            f'{allowance.quantize(Decimal("0.01"))}',
            f'{estimate.quantize(Decimal("0.01"))}',
            'Schätzung – keine steuerliche Lohnabrechnung',
        ])
    return _csv_response(
        f'lohn-schaetzung-{month_start:%Y-%m}.csv',
        ['Personalnummer', 'Mitarbeiter', 'Freigegebene Stunden', 'Stundenlohn', 'Zulage je Stunde', 'Geschätztes Brutto', 'Hinweis'],
        rows,
    )


@api_view(['GET'])
def folder_summary(request):
    user = request.user
    if _is_manager(user):
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
            'documents': Document.objects.filter(worker=worker).count(),
            'contracts': Contract.objects.filter(worker=worker).count(),
            'payroll': PayrollStatement.objects.filter(worker=worker).count(),
        }], 'clients': []})
    clients = [{
        'id': str(client.id),
        'name': client.name,
        'customer_number': client.customer_number,
        'documents': Document.objects.filter(client=client).count(),
        'contracts': Contract.objects.filter(client=client).count(),
        'orders': ClientOrder.objects.filter(client=client).count(),
    } for client in user.client_companies.filter(active=True)]
    return Response({'workers': [], 'clients': clients})


@api_view(['POST'])
def import_contract_templates(request):
    denied = _manager_required(request)
    if denied:
        return denied
    payload = request.data
    if request.FILES.get('file'):
        try:
            import json
            payload = json.loads(request.FILES['file'].read().decode('utf-8-sig'))
        except Exception as exc:
            return Response({'detail': f'Datei konnte nicht gelesen werden: {exc}'}, status=400)
    templates = payload if isinstance(payload, list) else payload.get('templates', [payload])
    valid_kinds = {value for value, _ in ContractTemplate.Kind.choices}
    created, updated, errors = 0, 0, []
    for index, item in enumerate(templates, start=1):
        try:
            name = str(item.get('name', '')).strip()
            kind = str(item.get('kind', '')).strip()
            version = str(item.get('version') or '1.0').strip()
            html_template = str(item.get('html_template', '')).strip()
            if not name or kind not in valid_kinds or not html_template:
                raise ValueError('name, gültiger kind und html_template sind erforderlich.')
            obj, was_created = ContractTemplate.objects.update_or_create(
                name=name,
                version=version,
                defaults={
                    'kind': kind,
                    'schema': item.get('schema') or {},
                    'html_template': html_template,
                    'active': bool(item.get('active', True)),
                },
            )
            created += int(was_created)
            updated += int(not was_created)
            audit(request, 'contract_template.imported', obj)
        except Exception as exc:
            errors.append({'index': index, 'error': str(exc)})
    return Response({'created': created, 'updated': updated, 'errors': errors})


@api_view(['GET'])
def readiness(request):
    if not _is_manager(request.user):
        return Response({'detail': 'Keine Berechtigung.'}, status=403)
    return Response(_readiness())
