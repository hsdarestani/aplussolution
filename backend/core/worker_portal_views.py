from rest_framework.decorators import api_view
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from .models import User, WorkerProfile


@api_view(['GET'])
def employee_ranking(request):
    """Return only the small, non-sensitive dataset needed by the worker ranking UI.

    The normal /workers/ endpoint intentionally scopes a worker to their own profile.
    Ranking is the one worker-facing feature that needs a cross-worker view, so keep
    that exception isolated and never serialize full WorkerProfile/User records here.
    """
    if request.user.role not in {User.Role.WORKER, User.Role.ADMIN, User.Role.MANAGER}:
        raise PermissionDenied('Ranking ist nur für Mitarbeiter und die Administration verfügbar.')

    workers = (
        WorkerProfile.objects.select_related('user')
        .filter(active=True, user__is_active=True)
        .exclude(user__email__iendswith='@sync.invalid')
        .order_by('-ranking_points', 'user__last_name', 'user__first_name', 'employee_number')
    )

    rows = []
    for worker in workers:
        full_name = worker.user.get_full_name().strip() or worker.employee_number
        rows.append({
            'id': str(worker.id),
            'employee_number': worker.employee_number,
            'ranking_points': worker.ranking_points,
            'active': True,
            'is_current_user': worker.user_id == request.user.id,
            'user_detail': {'name': full_name},
        })
    return Response(rows)


@api_view(['GET'])
def message_recipients(request):
    """Safe recipient picker for worker/client initiated conversations.

    Non-manager portals may start a conversation with disposition/admin only.  Do not
    expose e-mail addresses, phone numbers or the global user directory.
    """
    if request.user.role in {User.Role.ADMIN, User.Role.MANAGER}:
        recipients = User.objects.filter(is_active=True).exclude(pk=request.user.pk)
    elif request.user.role in {User.Role.WORKER, User.Role.CLIENT}:
        recipients = User.objects.filter(
            is_active=True,
            role__in=[User.Role.ADMIN, User.Role.MANAGER],
        )
    else:
        recipients = User.objects.none()

    return Response([
        {
            'id': str(user.id),
            'name': user.get_full_name().strip() or 'A+ Disposition',
            'role': user.role,
        }
        for user in recipients.order_by('first_name', 'last_name', 'id')
    ])
