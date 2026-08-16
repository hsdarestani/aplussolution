from django.utils import timezone
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from .premium_models import PublicApiKey


class PublicApiKeyAuthentication(BaseAuthentication):
    def authenticate(self, request):
        raw = request.headers.get('X-API-Key', '').strip()
        auth = request.headers.get('Authorization', '').strip()
        if not raw and auth.lower().startswith('apikey '):
            raw = auth.split(' ', 1)[1].strip()
        if not raw:
            return None
        parts = raw.split('_', 2)
        if len(parts) != 3 or parts[0] != 'aplus':
            raise AuthenticationFailed('Ungültiger API-Key.')
        try:
            key = PublicApiKey.objects.select_related('created_by').get(prefix=parts[1])
        except PublicApiKey.DoesNotExist as exc:
            raise AuthenticationFailed('Ungültiger API-Key.') from exc
        if not key.accepts(raw):
            raise AuthenticationFailed('API-Key ist ungültig oder abgelaufen.')
        key.last_used_at = timezone.now()
        key.save(update_fields=['last_used_at', 'updated_at'])
        return key.created_by, key


def require_scope(request, scope):
    key = getattr(request, 'auth', None)
    scopes = set(getattr(key, 'scopes', []) or [])
    if '*' not in scopes and scope not in scopes:
        raise AuthenticationFailed(f'API-Key benötigt Scope: {scope}')
