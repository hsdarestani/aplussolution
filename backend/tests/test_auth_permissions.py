from urllib.parse import parse_qs, urlparse

import pytest
from django.core import signing

from core.models import ClientCompany, Contract, ContractTemplate, User, WorkerProfile


@pytest.mark.django_db
def test_login_success_and_failure(api_client, worker_user):
    ok = api_client.post('/api/auth/login/', {'email': worker_user.email, 'password': 'StrongPass123!'}, format='json')
    assert ok.status_code == 200
    assert ok.data['user']['role'] == 'worker'
    assert ok.data['access'] and ok.data['refresh']
    bad = api_client.post('/api/auth/login/', {'email': worker_user.email, 'password': 'wrong'}, format='json')
    assert bad.status_code == 400


@pytest.mark.django_db
def test_oauth_start_uses_canonical_app_target(settings, api_client):
    settings.APP_URL = 'https://solution.smarbiz.sbs'
    settings.GOOGLE_OAUTH_CLIENT_ID = 'google-client'
    settings.GOOGLE_OAUTH_REDIRECT_URI = 'https://solution.smarbiz.sbs/api/auth/oauth/google/callback/'

    response = api_client.get('/api/auth/oauth/google/start/?target=https://evil.example/steal')

    assert response.status_code == 302
    location = response['Location']
    assert urlparse(location).netloc == 'accounts.google.com'
    state = parse_qs(urlparse(location).query)['state'][0]
    payload = signing.loads(state, salt='social-oauth', max_age=600)
    assert payload['target'] == 'https://solution.smarbiz.sbs/auth/callback'


@pytest.mark.django_db
def test_password_change_requires_current_password(auth_worker, worker_user):
    response = auth_worker.post('/api/auth/change-password/', {'current_password': 'wrong', 'new_password': 'NewStrongPass123!'}, format='json')
    assert response.status_code == 400
    response = auth_worker.post('/api/auth/change-password/', {'current_password': 'StrongPass123!', 'new_password': 'short'}, format='json')
    assert response.status_code == 400
    response = auth_worker.post('/api/auth/change-password/', {'current_password': 'StrongPass123!', 'new_password': 'NewStrongPass123!'}, format='json')
    assert response.status_code == 200
    worker_user.refresh_from_db()
    assert worker_user.check_password('NewStrongPass123!')


@pytest.mark.django_db
def test_worker_cannot_mutate_master_data_of_other_worker(auth_worker, second_worker):
    response = auth_worker.patch(f'/api/workers/{second_worker.id}/master-data/', {'iban': 'DE00'}, format='json')
    assert response.status_code == 403


@pytest.mark.django_db
def test_contract_queryset_is_scoped(api_client, admin_user, worker_user, second_worker, company):
    template = ContractTemplate.objects.create(name='T', slug='scope-test', kind='employment', schema={}, html_template='x')
    own = Contract.objects.create(template=template, worker=worker_user.worker_profile, title='Own', created_by=admin_user)
    Contract.objects.create(template=template, worker=second_worker, title='Other', created_by=admin_user)
    api_client.force_authenticate(worker_user)
    response = api_client.get('/api/contracts/')
    assert response.status_code == 200
    rows = response.data['results'] if isinstance(response.data, dict) and 'results' in response.data else response.data
    assert [row['id'] for row in rows] == [str(own.id)]


@pytest.mark.django_db
def test_worker_cannot_create_client_or_position(auth_worker, company):
    response = auth_worker.post('/api/clients/', {'name': 'Nope', 'customer_number': 'KD-X'}, format='json')
    assert response.status_code == 403
    response = auth_worker.post('/api/positions/', {'name': 'Nope'}, format='json')
    assert response.status_code == 403


@pytest.mark.django_db
def test_account_deletion_request_is_recorded(auth_worker, worker_user):
    response = auth_worker.post('/api/auth/account-deletion/', {}, format='json')
    assert response.status_code == 200
    worker_user.refresh_from_db()
    assert worker_user.deletion_requested_at is not None
