import jwt
from django.db import transaction
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import AuditLog, User, WorkerProfile


GITHUB_OIDC_ISSUER = 'https://token.actions.githubusercontent.com'
GITHUB_OIDC_JWKS = 'https://token.actions.githubusercontent.com/.well-known/jwks'
GITHUB_OIDC_AUDIENCE = 'aplus-store-review-sync'
EXPECTED_REPOSITORY = 'hsdarestani/publisher'
EXPECTED_REF = 'refs/heads/main'
EXPECTED_WORKFLOW_REF = (
    'hsdarestani/publisher/.github/workflows/'
    'aplus-solution-review-account-repair.yml@refs/heads/main'
)
STORE_REVIEW_EMAIL = 'store-review@aplus-solution.de'


def _github_oidc_claims(request):
    header = request.headers.get('Authorization', '')
    if not header.startswith('Bearer '):
        return None
    token = header[7:].strip()
    if not token:
        return None
    try:
        signing_key = jwt.PyJWKClient(GITHUB_OIDC_JWKS).get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token,
            signing_key,
            algorithms=['RS256'],
            audience=GITHUB_OIDC_AUDIENCE,
            issuer=GITHUB_OIDC_ISSUER,
            options={'require': ['exp', 'iat', 'iss', 'aud', 'sub']},
        )
    except Exception:
        return None
    if claims.get('repository') != EXPECTED_REPOSITORY:
        return None
    if claims.get('ref') != EXPECTED_REF:
        return None
    if claims.get('workflow_ref') != EXPECTED_WORKFLOW_REF:
        return None
    if claims.get('event_name') not in {'push', 'workflow_dispatch'}:
        return None
    return claims


@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def sync_store_review_credential(request):
    # This endpoint deliberately bypasses the app's normal JWT authentication:
    # its bearer token is a GitHub Actions OIDC token and is fully verified here.
    claims = _github_oidc_claims(request)
    if not claims:
        return Response({'detail': 'Forbidden.'}, status=403)

    password = str(request.data.get('password') or '')
    if len(password) < 24:
        return Response({'detail': 'Review credential is invalid.'}, status=400)

    with transaction.atomic():
        user = User.objects.select_for_update().filter(email=STORE_REVIEW_EMAIL).first()
        if not user:
            user = User(
                email=STORE_REVIEW_EMAIL,
                username=STORE_REVIEW_EMAIL,
                first_name='Store',
                last_name='Reviewer',
                role=User.Role.WORKER,
                is_active=True,
                is_staff=False,
                is_superuser=False,
            )
        user.username = STORE_REVIEW_EMAIL
        user.first_name = 'Store'
        user.last_name = 'Reviewer'
        user.role = User.Role.WORKER
        user.is_active = True
        user.is_staff = False
        user.is_superuser = False
        user.set_password(password)
        user.save()

        worker, _ = WorkerProfile.objects.get_or_create(
            user=user,
            defaults={
                'employee_number': 'STORE-REVIEW-001',
                'employment_type': WorkerProfile.EmploymentType.MINI,
                'monthly_hours': 0,
                'tariff_hourly_rate': 0,
                'extra_allowance': 0,
                'ranking_points': 0,
                'skills': [],
                'active': True,
            },
        )
        if not worker.active:
            worker.active = True
            worker.save(update_fields=['active'])

        AuditLog.objects.create(
            actor=None,
            action='store_review.credential_synced',
            object_type='User',
            object_id=str(user.pk),
            metadata={
                'source': 'github_oidc',
                'repository': claims.get('repository'),
                'workflow_ref': claims.get('workflow_ref'),
                'run_id': claims.get('run_id'),
                'sha': claims.get('sha'),
            },
        )

    if not user.check_password(password):
        return Response({'detail': 'Credential verification failed.'}, status=500)
    return Response({
        'detail': 'Store review credential synchronized.',
        'email': user.email,
        'role': user.role,
        'active': user.is_active,
    })
