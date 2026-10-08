"""Manager-only endpoints for independently scoped customer portal identities.

Never reset the first customer contact implicitly: every operation names one account.
A restricted account can only read the schedule for its customer, location and
(optional) positions. Fully privileged accounts cannot carry narrower scopes.
"""
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.db import transaction
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .credential_reset import generated_worker_password
from .models import ClientCompany, Location, Position, User
from .permissions import IsAdminOrManager
from .portal_models import ClientPortalAccess
from .services import audit


def _client(pk):
    return ClientCompany.objects.filter(pk=pk, active=True).first()


def _payload(user, client):
    access = ClientPortalAccess.objects.filter(user=user, client=client).select_related('location_scope').first()
    capabilities = access.capabilities if access and isinstance(access.capabilities, dict) else {}
    return {
        'id': str(user.id),
        'email': user.email,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'is_active': user.is_active,
        'read_only': bool(access.read_only) if access else False,
        'location_scope_id': str(access.location_scope_id) if access and access.location_scope_id else '',
        'location_scope_name': access.location_scope.name if access and access.location_scope_id else '',
        'position_ids': [str(item) for item in capabilities.get('position_ids', [])]
        if isinstance(capabilities.get('position_ids', []), list) else [],
    }


def _scope(request, client):
    data = request.data
    read_only = data.get('read_only', True)
    if not isinstance(read_only, bool):
        raise ValueError('Ungültige Zugriffsart.')
    location_id = str(data.get('location_scope_id') or '').strip()
    positions = data.get('position_ids', [])
    if not isinstance(positions, list) or any(not isinstance(i, str) for i in positions):
        raise ValueError('Bitte gültige Bereiche auswählen.')
    position_ids = list(dict.fromkeys(positions))
    if read_only:
        location = Location.objects.filter(pk=location_id, client=client, active=True).first() if location_id else None
        if not location:
            raise ValueError('Für einen eingeschränkten Zugang ist ein Standort dieses Kunden erforderlich.')
        if len(position_ids) > 30 or Position.objects.filter(pk__in=position_ids, active=True).count() != len(position_ids):
            raise ValueError('Mindestens ein ausgewählter Bereich ist ungültig.')
        return True, location, {'schedule': True, 'position_ids': position_ids}
    if location_id or position_ids:
        raise ValueError('Vollzugriff ist nur ohne Standort- und Bereichseinschränkung möglich.')
    return False, None, {}


@api_view(['GET', 'POST'])
@permission_classes([IsAdminOrManager])
def client_portal_users(request, pk):
    client = _client(pk)
    if not client:
        return Response({'detail': 'Aktiver Kunde nicht gefunden.'}, status=404)
    if request.method == 'GET':
        contacts = client.contacts.filter(role=User.Role.CLIENT).order_by('first_name', 'last_name', 'email')
        return Response({'client': client.name, 'accounts': [_payload(u, client) for u in contacts]})

    email = str(request.data.get('email') or '').strip().lower()
    first_name = str(request.data.get('first_name') or '').strip()
    last_name = str(request.data.get('last_name') or '').strip()
    try:
        validate_email(email)
        if not first_name or not last_name:
            raise ValueError('Bitte Vorname und Nachname angeben.')
        read_only, location, capabilities = _scope(request, client)
    except (DjangoValidationError, ValueError) as exc:
        return Response({'detail': str(exc)}, status=400)

    with transaction.atomic():
        # Do not attach an existing identity belonging to another customer.
        if User.objects.filter(email__iexact=email).exists():
            return Response({'detail': 'Diese E-Mail-Adresse ist bereits registriert. Bitte den bestehenden Zugang prüfen.'}, status=400)
        password = generated_worker_password(14)
        user = User.objects.create_user(
            email=email, password=password, first_name=first_name, last_name=last_name,
            role=User.Role.CLIENT, is_onboarded=True, is_active=True, locale='de',
        )
        client.contacts.add(user)
        ClientPortalAccess.objects.create(
            user=user, client=client, label=f'{first_name} {last_name}',
            read_only=read_only, location_scope=location, capabilities=capabilities,
        )
        audit(request, 'client.portal_user.created', client, {'account_id': str(user.id), 'read_only': read_only})
    return Response({'account': _payload(user, client), 'temporary_password': password}, status=201)


@api_view(['PATCH'])
@permission_classes([IsAdminOrManager])
def client_portal_user_detail(request, pk, user_pk):
    client = _client(pk)
    if not client:
        return Response({'detail': 'Aktiver Kunde nicht gefunden.'}, status=404)
    user = client.contacts.filter(pk=user_pk, role=User.Role.CLIENT).first()
    if not user:
        return Response({'detail': 'Kundenzugang nicht gefunden.'}, status=404)

    try:
        read_only, location, capabilities = _scope(request, client)
        first_name = str(request.data.get('first_name', user.first_name) or '').strip()
        last_name = str(request.data.get('last_name', user.last_name) or '').strip()
        if not first_name or not last_name:
            raise ValueError('Bitte Vorname und Nachname angeben.')
        active = request.data.get('is_active', user.is_active)
        if not isinstance(active, bool):
            raise ValueError('Ungültiger Kontostatus.')
    except (DjangoValidationError, ValueError) as exc:
        return Response({'detail': str(exc)}, status=400)

    existing_access = ClientPortalAccess.objects.filter(user=user).first()
    if existing_access and existing_access.client_id != client.id:
        return Response({'detail': 'Dieser Zugang ist einem anderen Kunden zugeordnet.'}, status=409)

    with transaction.atomic():
        user.first_name, user.last_name, user.is_active = first_name, last_name, active
        user.save(update_fields=['first_name', 'last_name', 'is_active'])
        # Never transfer the identity between customer accounts.
        ClientPortalAccess.objects.update_or_create(
            user=user, defaults={
                'client': client, 'label': f'{first_name} {last_name}', 'read_only': read_only,
                'location_scope': location, 'capabilities': capabilities,
            },
        )
        audit(request, 'client.portal_user.updated', client, {
            'account_id': str(user.id), 'read_only': read_only, 'active': active,
        })
    return Response({'account': _payload(user, client)})


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def client_portal_user_reset_password(request, pk, user_pk):
    client = _client(pk)
    if not client:
        return Response({'detail': 'Aktiver Kunde nicht gefunden.'}, status=404)
    user = client.contacts.filter(pk=user_pk, role=User.Role.CLIENT).first()
    if not user:
        return Response({'detail': 'Kundenzugang nicht gefunden.'}, status=404)
    password = generated_worker_password(14)
    with transaction.atomic():
        user.set_password(password)
        user.save(update_fields=['password'])
        audit(request, 'client.portal_user.password_reset', client, {'account_id': str(user.id)})
    return Response({'email': user.email, 'temporary_password': password})
