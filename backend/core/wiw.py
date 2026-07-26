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
    TOKEN_CACHE_KEY = 'wiw:token:v2'
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
        self.user_id = settings.WIW_USER_ID
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
        token = payload.get('token') or payload.get('access_token') or (payload.get('login') or {}).get('token')
        if not token:
            raise WhenIWorkError('When I Work hat keinen Login-Token zurückgegeben.')
        cache.set(self.TOKEN_CACHE_KEY, token, settings.WIW_TOKEN_CACHE_SECONDS)
        if not self.user_id:
            user_id = payload.get('user_id') or (payload.get('user') or {}).get('id')
            if user_id:
                self.user_id = str(user_id)
        return token

    def _headers(self, force_login=False):
        token = self.login(force=force_login)
        headers = {
            'W-Key': self.dev_key,
            'W-Token': token,
            'Authorization': f'Bearer {token}',
            'Accept': 'application/json',
        }
        if self.user_id:
            headers['W-UserID'] = str(self.user_id)
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
            response = self.session.request(
                method,
                url,
                headers=self._headers(force_login=True),
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
                results[name] = {'supported': True, 'count': len(self.extract_collection(payload, name)), 'keys': sorted(payload.keys()) if isinstance(payload, dict) else []}
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
