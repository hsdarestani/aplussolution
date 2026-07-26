import hashlib
import hmac
import logging
import time
from dataclasses import dataclass
from typing import Any

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


class WhenIWorkError(RuntimeError):
    pass


@dataclass
class ResourceResult:
    name: str
    items: list[dict[str, Any]]
    status_code: int
    supported: bool = True
    error: str = ''


class WhenIWorkClient:
    LOGIN_URL = 'https://api.login.wheniwork.com/login'
    API_BASE = 'https://api.wheniwork.com/2'
    TOKEN_CACHE_KEY = 'wiw:token:v3'
    USER_CONTEXT_CACHE_KEY = 'wiw:user-context:v2'
    RESOURCE_PATHS = {
        'users': '/users',
        'locations': '/locations',
        'positions': '/positions',
        'sites': '/sites',
        'shifts': '/shifts',
        'times': '/times',
        'requests': '/requests',
        'availabilities': '/availabilities',
    }

    def __init__(self, session=None):
        self.session = session or requests.Session()
        self.dev_key = settings.WIW_DEV_KEY
        self.email = settings.WIW_EMAIL
        self.password = settings.WIW_PASSWORD
        self.configured_user_id = str(settings.WIW_USER_ID or '').strip()
        self.user_id = self.configured_user_id
        self.timeout = settings.WIW_HTTP_TIMEOUT
        if not self.dev_key or not self.email or not self.password:
            raise WhenIWorkError('When-I-Work-Zugangsdaten sind nicht vollständig konfiguriert.')

    def login(self, force=False):
        if not force:
            cached = cache.get(self.TOKEN_CACHE_KEY)
            if cached:
                return cached
        response = self.session.post(
            self.LOGIN_URL,
            headers={'W-Key': self.dev_key, 'Content-Type': 'application/json'},
            json={'email': self.email, 'password': self.password},
            timeout=self.timeout,
        )
        self._raise_for_status(response, 'WIW login')
        payload = response.json()
        person = payload.get('person') if isinstance(payload.get('person'), dict) else {}
        token = (
            payload.get('token')
            or payload.get('access_token')
            or (payload.get('login') or {}).get('token')
            or person.get('token')
        )
        if not token:
            raise WhenIWorkError('When I Work hat keinen Login-Token zurückgegeben.')
        cache.set(self.TOKEN_CACHE_KEY, token, settings.WIW_TOKEN_CACHE_SECONDS)
        return token

    def _base_headers(self, token):
        return {
            'W-Key': self.dev_key,
            'W-Token': token,
            'Authorization': f'Bearer {token}',
            'Accept': 'application/json',
        }

    @staticmethod
    def _context_candidates(payload):
        candidates = []

        def collect(value):
            if isinstance(value, list):
                for item in value:
                    collect(item)
                return
            if not isinstance(value, dict):
                return
            if value.get('id') is not None and value.get('account_id') is not None:
                candidates.append(value)
            for key in ('users', 'user', 'logins', 'data', 'items', 'results'):
                if key in value:
                    collect(value[key])

        collect(payload)
        if candidates:
            return candidates

        # Defensive fallback for older WIW response shapes that omit account_id.
        def collect_fallback(value):
            if isinstance(value, list):
                for item in value:
                    collect_fallback(item)
                return
            if not isinstance(value, dict):
                return
            if value.get('id') is not None and any(
                key in value for key in ('email', 'first_name', 'last_name', 'role', 'type', 'is_admin', 'is_manager')
            ):
                candidates.append(value)
            for key in ('users', 'user', 'logins', 'data', 'items', 'results'):
                if key in value:
                    collect_fallback(value[key])

        collect_fallback(payload)
        return candidates

    def resolve_user_context(self, token, force=False):
        if not force:
            cached = cache.get(self.USER_CONTEXT_CACHE_KEY)
            if cached:
                self.user_id = str(cached)
                return self.user_id

        response = self.session.get(
            f'{self.API_BASE}/login',
            headers=self._base_headers(token),
            params={'show_pending': 'true'},
            timeout=self.timeout,
        )
        self._raise_for_status(response, 'WIW Benutzerkontext')
        payload = response.json() if response.content else {}
        candidates = self._context_candidates(payload)
        if not candidates:
            raise WhenIWorkError('When I Work hat keinen verwendbaren Benutzerkontext zurückgegeben.')

        configured = self.configured_user_id
        selected = None
        if configured:
            selected = next((item for item in candidates if str(item.get('id')) == configured), None)
            if selected is None:
                selected = next((item for item in candidates if str(item.get('account_id')) == configured), None)

        if selected is None:
            active = [
                item
                for item in candidates
                if item.get('active', True) is not False and item.get('pending', False) is not True
            ]
            selected = (active or candidates)[0]

        user_id = str(selected.get('id') or '').strip()
        if not user_id:
            raise WhenIWorkError('When I Work hat keinen gültigen W-UserId-Kontext zurückgegeben.')
        self.user_id = user_id
        cache.set(self.USER_CONTEXT_CACHE_KEY, user_id, settings.WIW_TOKEN_CACHE_SECONDS)
        return user_id

    def _headers(self, force_login=False, force_context=False):
        token = self.login(force=force_login)
        user_id = self.resolve_user_context(token, force=force_context)
        headers = self._base_headers(token)
        headers['W-UserId'] = str(user_id)
        return headers

    def request(self, method, path, params=None, json=None, retry=True):
        url = path if path.startswith('http') else f'{self.API_BASE}/{path.lstrip("/")}'
        response = self.session.request(
            method,
            url,
            headers=self._headers(),
            params=params,
            json=json,
            timeout=self.timeout,
        )
        if response.status_code == 401 and retry:
            cache.delete(self.TOKEN_CACHE_KEY)
            cache.delete(self.USER_CONTEXT_CACHE_KEY)
            self.user_id = self.configured_user_id
            response = self.session.request(
                method,
                url,
                headers=self._headers(force_login=True, force_context=True),
                params=params,
                json=json,
                timeout=self.timeout,
            )
        if response.status_code == 429 and retry:
            delay = min(int(response.headers.get('Retry-After', '2') or 2), 30)
            time.sleep(delay)
            return self.request(method, path, params=params, json=json, retry=False)
        self._raise_for_status(response, f'WIW {method} {path}')
        if not response.content:
            return {}
        return response.json()

    def get(self, path, params=None):
        return self.request('GET', path, params=params)

    def post(self, path, payload=None, params=None):
        return self.request('POST', path, params=params, json=payload or {})

    def delete(self, path, params=None):
        return self.request('DELETE', path, params=params)

    def discover(self):
        results = {}
        for name, path in self.RESOURCE_PATHS.items():
            try:
                payload = self.get(path, params={'limit': 1})
                results[name] = {
                    'supported': True,
                    'count': len(self.extract_collection(payload, name)),
                    'keys': sorted(payload.keys()) if isinstance(payload, dict) else [],
                }
            except WhenIWorkError as exc:
                results[name] = {'supported': False, 'error': str(exc)}
        return results

    def collection(self, name, params=None, optional=False):
        path = self.RESOURCE_PATHS[name]
        try:
            payload = self.get(path, params=params or {})
            return ResourceResult(name, self.extract_collection(payload, name), 200)
        except WhenIWorkError as exc:
            if optional:
                logger.warning('Optional WIW resource %s unavailable: %s', name, exc)
                return ResourceResult(name, [], 0, supported=False, error=str(exc))
            raise

    @staticmethod
    def extract_collection(payload, name='items'):
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if not isinstance(payload, dict):
            return []
        candidates = [name, 'items', 'data', 'results', 'records']
        singular = name[:-1] if name.endswith('s') else name
        candidates.extend([singular, f'{singular}s'])
        for key in candidates:
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        for value in payload.values():
            if isinstance(value, list) and all(isinstance(item, dict) for item in value):
                return value
        return []

    @staticmethod
    def _raise_for_status(response, context):
        if response.ok:
            return
        try:
            payload = response.json()
            detail = payload.get('error') or payload.get('message') or payload.get('detail') or str(payload)[:300]
        except Exception:
            detail = (response.text or '')[:300]
        raise WhenIWorkError(f'{context} fehlgeschlagen ({response.status_code}): {detail}')


def verify_webhook_signature(raw_body: bytes, signature: str) -> bool:
    secret = settings.WIW_WEBHOOK_SECRET
    if not secret:
        return False
    supplied = (signature or '').strip()
    if supplied.startswith('sha256='):
        supplied = supplied.split('=', 1)[1]
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, supplied)
