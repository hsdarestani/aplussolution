from urllib.parse import parse_qs, urlparse

import pytest
from django.test import override_settings


@pytest.mark.django_db
@override_settings(
    APP_URL='https://solution.smarbiz.sbs',
    GOOGLE_OAUTH_CLIENT_ID='client-id',
    GOOGLE_OAUTH_CLIENT_SECRET='client-secret',
    GOOGLE_OAUTH_REDIRECT_URI='https://solution.smarbiz.sbs/api/auth/oauth/google/callback/',
)
def test_google_oauth_start_uses_canonical_server_target(api_client):
    response = api_client.get('/api/auth/oauth/google/start/?target=https://evil.example/')
    assert response.status_code == 302
    location = urlparse(response['Location'])
    assert location.netloc == 'accounts.google.com'
    query = parse_qs(location.query)
    assert query['redirect_uri'] == ['https://solution.smarbiz.sbs/api/auth/oauth/google/callback/']
    assert 'state' in query


@pytest.mark.django_db
@override_settings(APP_URL='https://solution.smarbiz.sbs')
def test_oauth_callback_provider_error_is_visible(api_client):
    response = api_client.get('/api/auth/oauth/google/callback/?error=access_denied')
    assert response.status_code == 302
    location = urlparse(response['Location'])
    assert location.path == '/'
    assert 'oauth_error' in parse_qs(location.query)


@pytest.mark.django_db
@override_settings(APP_URL='https://solution.smarbiz.sbs')
def test_oauth_callback_missing_params_is_visible(api_client):
    response = api_client.get('/api/auth/oauth/google/callback/')
    assert response.status_code == 302
    query = parse_qs(urlparse(response['Location']).query)
    assert 'OAuth-Callback ist unvollständig' in query['oauth_error'][0]


@pytest.mark.django_db
@override_settings(APP_URL='https://solution.smarbiz.sbs')
def test_oauth_callback_finish_error_is_visible(api_client, monkeypatch):
    from core import oauth_views

    def fail(*args, **kwargs):
        raise ValueError('Portalzugang fehlt')

    monkeypatch.setattr(oauth_views.oauth, 'finish', fail)
    response = api_client.get('/api/auth/oauth/google/callback/?code=x&state=y')
    assert response.status_code == 302
    query = parse_qs(urlparse(response['Location']).query)
    assert query['oauth_error'] == ['Portalzugang fehlt']
