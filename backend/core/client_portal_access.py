from rest_framework.exceptions import PermissionDenied

from .models import User
from .portal_models import ClientPortalAccess


def get_client_portal_access(user):
    if not user or not getattr(user, 'is_authenticated', False) or user.role != User.Role.CLIENT:
        raise PermissionDenied('Diese Funktion ist nur im Kundenportal verfügbar.')

    access = ClientPortalAccess.objects.select_related('client', 'location_scope').filter(user=user).first()
    if access and access.client.active:
        company = access.client
    else:
        company = user.client_companies.filter(active=True).order_by('created_at').first()
        access = None

    if not company:
        raise PermissionDenied('Dem Benutzer ist kein aktiver Kunde zugeordnet.')
    return access, company


def is_read_only_client(user):
    if not user or not getattr(user, 'is_authenticated', False) or user.role != User.Role.CLIENT:
        return False
    try:
        access = ClientPortalAccess.objects.only('read_only').filter(user=user).first()
    except Exception:
        return False
    return bool(access and access.read_only)


def client_access_payload(user):
    access, company = get_client_portal_access(user)
    read_only = bool(access and access.read_only)
    location = access.location_scope if access else None
    capabilities = {
        'schedule': True,
        'orders': not read_only,
        'documents': not read_only,
        'ratings': not read_only,
        'messages': not read_only,
        'profile': not read_only,
        'shift_requests': not read_only,
    }
    if access and isinstance(access.capabilities, dict):
        capabilities.update({key: bool(value) for key, value in access.capabilities.items()})
        if read_only:
            capabilities = {key: (key == 'schedule') for key in capabilities}
    return {
        'client_id': str(company.id),
        'client_name': company.name,
        'account_id': str(user.id),
        'account_name': user.get_full_name() or access.label if access else user.get_full_name() or user.email,
        'first_name': user.first_name or (user.get_full_name().split(' ')[0] if user.get_full_name() else ''),
        'email': user.email,
        'username': user.username,
        'read_only': read_only,
        'location_scope_id': str(location.id) if location else None,
        'location_scope_name': location.name if location else None,
        'capabilities': capabilities,
    }
