"""Customer maintenance guard readiness probe must distinguish HTTP and DB health."""
from unittest.mock import patch

import pytest

from config import urls


@pytest.mark.django_db
def test_readiness_is_ok_when_database_accepts_simple_read(client):
    response = client.get('/api/status/ready/')
    assert response.status_code == 200
    assert response.json() == {'status': 'ok'}
    assert response.headers.get('Cache-Control') == 'no-store'


@pytest.mark.django_db
def test_readiness_is_unavailable_when_db_connection_fails(client):
    class DownConnection:
        def cursor(self):
            raise OSError('database temporarily unreachable')

    with patch.object(urls, 'connections', {'default': DownConnection()}):
        response = client.get('/api/status/ready/')
    assert response.status_code == 503
    assert response.json() == {'status': 'unavailable'}


@pytest.mark.django_db
def test_readiness_does_not_accept_mutation(client):
    response = client.post('/api/status/ready/')
    assert response.status_code == 405
