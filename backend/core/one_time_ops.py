import hashlib
import hmac

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import User
from .views import create_worker_account


_PROVISION_TOKEN_SHA256 = '08713fe95c9f004cd56f2182fea1e8c3b6e315d26c99a4da6a0955e49f4c3398'


def _authorized(raw_token: str) -> bool:
    digest = hashlib.sha256(str(raw_token or '').encode('utf-8')).hexdigest()
    return hmac.compare_digest(digest, _PROVISION_TOKEN_SHA256)


@api_view(['GET'])
@permission_classes([AllowAny])
def provision_housekeeping_worker(request):
    """One-shot operational bridge. Remove immediately after provisioning."""
    if not _authorized(request.query_params.get('token')):
        return Response({'detail': 'Not found.'}, status=404)

    email = str(request.query_params.get('email') or '').strip().lower()
    if not email:
        return Response({'detail': 'email is required'}, status=400)
    if User.objects.filter(email=email).exists():
        return Response({'detail': 'employee already exists', 'email': email}, status=409)

    payload = {
        'email': email,
        'first_name': str(request.query_params.get('first_name') or '').strip(),
        'last_name': str(request.query_params.get('last_name') or '').strip(),
        'phone': str(request.query_params.get('phone') or '').strip(),
    }
    try:
        worker, temporary_password = create_worker_account(payload)
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=400)

    worker.schedule_groups = ['housekeeping']
    if 'Housekeeping' not in (worker.skills or []):
        worker.skills = [*(worker.skills or []), 'Housekeeping']
    worker.save(update_fields=['schedule_groups', 'skills', 'updated_at'])

    return Response({
        'status': 'created',
        'email': worker.user.email,
        'employee_number': worker.employee_number,
        'schedule_groups': worker.schedule_groups,
        'temporary_password': temporary_password,
    }, status=201)
