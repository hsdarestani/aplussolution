from urllib.parse import parse_qs, urlparse

import pytest
from django.core import signing
from django.test import override_settings

from core import oauth


@pytest.mark.django_db
@override_settings(APP_URL='https://solution.smarbiz.sbs')
def test_oauth_state_rejects_external_callback_target():
    state = oauth._state('google', 'https://evil.example/steal')
    payload = signing.loads(state, salt='social-oauth', max_age=600)
    assert payload['target'] == 'https://solution.smarbiz.sbs/auth/callback'


@pytest.mark.django_db
@override_settings(APP_URL='https://solution.smarbiz.sbs')
def test_oauth_state_keeps_same_origin_callback_target():
    target = 'https://solution.smarbiz.sbs/auth/callback'
    state = oauth._state('google', target)
    payload = signing.loads(state, salt='social-oauth', max_age=600)
    assert payload['target'] == target


@override_settings(
    APP_URL='https://solution.smarbiz.sbs',
    GOOGLE_OAUTH_CLIENT_ID='client-id.apps.googleusercontent.com',
    GOOGLE_OAUTH_CLIENT_SECRET='server-secret',
    GOOGLE_OAUTH_REDIRECT_URI='https://solution.smarbiz.sbs/api/auth/oauth/google/callback/',
)
def test_google_start_builds_expected_authorization_url_without_secret():
    url = oauth.start('google', 'https://solution.smarbiz.sbs/auth/callback')
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    assert parsed.scheme == 'https'
    assert parsed.netloc == 'accounts.google.com'
    assert query['client_id'] == ['client-id.apps.googleusercontent.com']
    assert query['redirect_uri'] == ['https://solution.smarbiz.sbs/api/auth/oauth/google/callback/']
    assert query['scope'] == ['openid email profile']
    assert 'server-secret' not in url


@override_settings(
    GOOGLE_OAUTH_CLIENT_ID='',
    GOOGLE_OAUTH_CLIENT_SECRET='',
    GOOGLE_OAUTH_REDIRECT_URI='https://solution.smarbiz.sbs/api/auth/oauth/google/callback/',
)
def test_google_start_fails_clearly_when_credentials_are_missing():
    with pytest.raises(ValueError, match='noch nicht vollständig konfiguriert'):
        oauth.start('google', 'https://solution.smarbiz.sbs/auth/callback')
