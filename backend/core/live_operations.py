from datetime import timedelta
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from . import advanced_views as base
from . import slot_compat_views_v2 as slots
from .models import (
    Availability,
    ClientCompany,
    ClientOrder,
    Contract,
    Document,
    Notification,
    Shift,
    ShiftSwapRequest,
    TimeEntry,
    TimeOffRequest,
    User,
    WorkerProfile,
)
from .serializers import AvailabilitySerializer, NotificationSerializer, ShiftSerializer
from .shift_slots import ShiftSlot


SYNTHETIC_MIGRATION_EMAIL_SUFFIX = '@sync.invalid'


def _operational_workers():
    return WorkerProfile.objects.filter(active=True, user__is_active=True).exclude(
        user__email__iendswith=SYNTHETIC_MIGRATION_EMAIL_SUFFIX
    )


def _operational_time_entries():
    """Native A+ time rows used for live action counts.

    Imported WIW history remains available in reports/archive, but it must not
    inflate today's Steuerzentrale counters or missing-clock-out warnings.
    """
    return TimeEntry.objects.filter(
        Q(wiw_time_id__isnull=True) | Q(wiw_time_id='')
    ).exclude(worker__user__email__iendswith=SYNTHETIC_MIGRATION_EMAIL_SUFFIX)


@api_view(['GET'])
def operations_overview(request):
    user = request.user
    now = timezone.now()
    notifications = Notification.objects.filter(user=user).order_by('-created_at')[:30]
    data = {
        'role': user.role,
        'notifications': NotificationSerializer(notifications, many=True).data,
        'unread_notifications': Notification.objects.filter(user=user, read_at__isnull=True).count(),
        'readiness': base._readiness() if base._is_manager(user) else None,
    }

    if base._is_manager(user):
        # Use the slot-aware staffing implementation so multi-person demand remains
        # accurate while live counters below exclude migration-only history.
        findings = slots._schedule_findings()
        current_month_start, current_month_end = base._month_bounds()
        estimated_cost = Decimal('0')
        for worker, shift in slots._assignment_pairs(
            base._aware_start(current_month_start),
            base._aware_start(current_month_end),
        ):
            if str(worker.user.email or '').lower().endswith(SYNTHETIC_MIGRATION_EMAIL_SUFFIX):
                continue
            minutes = max(0, int((shift.ends_at - shift.starts_at).total_seconds() // 60) - shift.break_minutes)
            rate = worker.tariff_hourly_rate or Decimal('0')
            allowance = worker.extra_allowance or Decimal('0')
            estimated_cost += (Decimal(minutes) / Decimal(60)) * (rate + allowance)

        operational_entries = _operational_time_entries()
        data.update({
            **findings,
            'estimated_monthly_labor_cost': str(estimated_cost.quantize(Decimal('0.01'))),
            'pending_swaps': ShiftSwapRequest.objects.filter(status=ShiftSwapRequest.Status.PENDING).count(),
            'swaps': [
                base._serialize_swap(item)
                for item in ShiftSwapRequest.objects.select_related(
                    'shift__position', 'requested_by__user', 'offered_to__user'
                ).order_by('-created_at')[:50]
            ],
            'swap_candidates': [
                {'id': str(worker.id), 'name': worker.user.get_full_name() or worker.user.email}
                for worker in _operational_workers().select_related('user').order_by('user__first_name')
            ],
            'pending_time_off': TimeOffRequest.objects.filter(status=TimeOffRequest.Status.PENDING).exclude(
                worker__user__email__iendswith=SYNTHETIC_MIGRATION_EMAIL_SUFFIX
            ).count(),
            'unapproved_time_entries': operational_entries.filter(approved=False, clock_out__isnull=False).count(),
            'missing_clock_outs': operational_entries.filter(
                clock_out__isnull=True,
                clock_in__lt=now - timedelta(hours=16),
            ).count(),
            'contracts_due_30': Contract.objects.filter(
                ends_on__range=(timezone.localdate(), timezone.localdate() + timedelta(days=30)),
                status__in=[Contract.Status.READY, Contract.Status.SENT, Contract.Status.SIGNED],
            ).count(),
            'active_workers': _operational_workers().count(),
            'active_clients': ClientCompany.objects.filter(active=True).count(),
        })
    elif user.role == User.Role.WORKER:
        worker = user.worker_profile
        upcoming = Shift.objects.filter(
            Q(slots__worker=worker, slots__status=ShiftSlot.Status.CLAIMED) | Q(worker=worker),
            starts_at__gte=now,
        ).exclude(status=Shift.Status.CANCELLED).distinct().order_by('starts_at')[:20]
        data.update({
            'current_worker_id': str(worker.id),
            'swap_candidates': [
                {'id': str(candidate.id), 'name': candidate.user.get_full_name() or candidate.user.email}
                for candidate in _operational_workers().exclude(pk=worker.pk).select_related('user').order_by('user__first_name')
            ],
            'availabilities': AvailabilitySerializer(
                Availability.objects.filter(worker=worker).order_by('-starts_at')[:30], many=True
            ).data,
            'swaps': [
                base._serialize_swap(item)
                for item in ShiftSwapRequest.objects.filter(
                    Q(requested_by=worker) | Q(offered_to=worker)
                ).select_related('shift__position', 'requested_by__user', 'offered_to__user').order_by('-created_at')[:30]
            ],
            'upcoming_shifts': ShiftSerializer(upcoming, many=True).data,
        })
    else:
        companies = user.client_companies.all()
        company_ids = {str(pk) for pk in companies.values_list('pk', flat=True)}
        client_findings = slots._schedule_findings()['coverage_gaps']
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
