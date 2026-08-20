from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import Contract, Notification, Shift, TimeEntry, User, WorkerProfile
from .portal_service import activate_portal, create_portal_invitation, invitation_status, resolve_invitation
from .serializers import NotificationSerializer, UserSerializer
from .shift_api import ShiftApiSerializer
from .shift_slots import ShiftSlot


SYNTHETIC_MIGRATION_EMAIL_SUFFIX = '@sync.invalid'


def operational_workers():
    """Workers that can participate in the live A+ portal.

    Synthetic @sync.invalid rows are retained for migration/audit only and must
    never be counted as portal users or receive invitations.
    """
    return WorkerProfile.objects.exclude(user__email__iendswith=SYNTHETIC_MIGRATION_EMAIL_SUFFIX)


def shift_queryset():
    return Shift.objects.select_related('order', 'client', 'location', 'position').annotate(
        filled_count=Count('slots', filter=Q(slots__status='claimed', slots__worker__isnull=False), distinct=True),
        open_count=Count('slots', filter=Q(slots__status='open', slots__worker__isnull=True), distinct=True),
    ).order_by('starts_at')


@api_view(['POST'])
@permission_classes([AllowAny])
def activation_validate(request):
    try:
        invitation = resolve_invitation(request.data.get('token', ''))
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=400)
    user = invitation.user
    return Response({'valid': True, 'name': user.get_full_name() or user.email, 'email': user.email, 'expires_at': invitation.expires_at})


@api_view(['POST'])
@permission_classes([AllowAny])
def activation_complete(request):
    password = request.data.get('password', '')
    if password != request.data.get('password_confirm', ''):
        return Response({'detail': 'Die Passwörter stimmen nicht überein.'}, status=400)
    try:
        user, access, refresh = activate_portal(request.data.get('token', ''), password)
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=400)
    return Response({'access': access, 'refresh': refresh, 'user': UserSerializer(user, context={'request': request}).data})


@api_view(['GET'])
def portal_statuses(request):
    if request.user.role not in {User.Role.ADMIN, User.Role.MANAGER}:
        return Response({'detail': 'Keine Berechtigung.'}, status=403)
    workers = operational_workers().filter(active=True).select_related('user').order_by('user__first_name', 'user__last_name')
    search = (request.GET.get('search') or '').strip()
    if search:
        workers = workers.filter(Q(user__first_name__icontains=search) | Q(user__last_name__icontains=search) | Q(user__email__icontains=search) | Q(employee_number__icontains=search))
    return Response([invitation_status(worker) for worker in workers[:200]])


@api_view(['POST'])
def invite_worker(request, pk):
    if request.user.role not in {User.Role.ADMIN, User.Role.MANAGER}:
        return Response({'detail': 'Keine Berechtigung.'}, status=403)
    worker = operational_workers().select_related('user').filter(pk=pk, active=True).first()
    if not worker:
        return Response({'detail': 'Mitarbeiter wurde nicht gefunden oder ist nur als Migrationsdatensatz vorhanden.'}, status=404)
    try:
        invitation, activation_url, delivered = create_portal_invitation(worker, request.user)
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=400)
    payload = {'status': invitation_status(worker), 'delivered': delivered, 'expires_at': invitation.expires_at}
    if not delivered:
        payload['activation_url'] = activation_url
    return Response(payload, status=201)


@api_view(['POST'])
def bulk_invite_workers(request):
    if request.user.role not in {User.Role.ADMIN, User.Role.MANAGER}:
        return Response({'detail': 'Keine Berechtigung.'}, status=403)
    workers = operational_workers().filter(active=True, user__is_active=True).select_related('user')
    ids = request.data.get('worker_ids') or []
    if ids:
        workers = workers.filter(pk__in=ids)
    results = []
    for worker in workers:
        if invitation_status(worker)['state'] == 'active':
            continue
        try:
            invitation, activation_url, delivered = create_portal_invitation(worker, request.user)
            item = {'worker_id': str(worker.id), 'email': worker.user.email, 'delivered': delivered, 'expires_at': invitation.expires_at}
            if not delivered:
                item['activation_url'] = activation_url
            results.append(item)
        except ValueError as exc:
            results.append({'worker_id': str(worker.id), 'email': worker.user.email, 'error': str(exc)})
    return Response({'results': results, 'count': len(results)})


@api_view(['GET'])
def employee_home(request):
    if request.user.role != User.Role.WORKER:
        return Response({'detail': 'Diese Startseite ist nur für Mitarbeiter.'}, status=403)
    worker = request.user.worker_profile
    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    mine = shift_queryset().filter(slots__worker=worker, slots__status=ShiftSlot.Status.CLAIMED, ends_at__gte=now).distinct()
    available = shift_queryset().filter(status=Shift.Status.PUBLISHED, starts_at__gte=now, slots__status=ShiftSlot.Status.OPEN, slots__worker__isnull=True).exclude(slots__worker=worker, slots__status=ShiftSlot.Status.CLAIMED).distinct()
    # The live employee dashboard reflects completed native A+ entries only.
    # Imported WIW time rows remain available for archive/reporting but must not
    # inflate the current monthly total or turn an old open row into worked time.
    worked_minutes = sum(
        entry.worked_minutes
        for entry in TimeEntry.objects.filter(
            worker=worker,
            clock_in__gte=month_start,
            clock_out__isnull=False,
            wiw_time_id__isnull=True,
        )
    )
    contracts = Contract.objects.filter(worker=worker).exclude(status__in=[Contract.Status.CANCELLED, Contract.Status.EXPIRED])
    notifications = Notification.objects.filter(user=request.user).order_by('-created_at')[:8]
    return Response({
        'worker': {'id': str(worker.id), 'name': request.user.get_full_name() or request.user.email, 'employee_number': worker.employee_number, 'employment_type': worker.employment_type},
        'next_shift': ShiftApiSerializer(mine.first(), context={'request': request}).data if mine.exists() else None,
        'upcoming_shifts': ShiftApiSerializer(mine[:5], many=True, context={'request': request}).data,
        'available_shifts': ShiftApiSerializer(available[:5], many=True, context={'request': request}).data,
        'available_count': available.count(),
        'month_worked_minutes': worked_minutes,
        'contract_actions': contracts.filter(status__in=[Contract.Status.READY, Contract.Status.SENT]).count(),
        'contracts_expiring_30': contracts.filter(ends_on__gte=timezone.localdate(), ends_on__lte=timezone.localdate() + timedelta(days=30)).count(),
        'unread_notifications': Notification.objects.filter(user=request.user, read_at__isnull=True).count(),
        'notifications': NotificationSerializer(notifications, many=True).data,
    })
