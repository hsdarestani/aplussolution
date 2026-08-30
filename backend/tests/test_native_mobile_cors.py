def _preflight(client, origin: str):
    return client.options(
        '/api/auth/login/',
        HTTP_ORIGIN=origin,
        HTTP_ACCESS_CONTROL_REQUEST_METHOD='POST',
        HTTP_ACCESS_CONTROL_REQUEST_HEADERS='content-type',
    )


def test_current_capacitor_https_origin_is_allowed(client):
    response = _preflight(client, 'https://localhost')

    assert response.status_code == 200
    assert response.headers.get('Access-Control-Allow-Origin') == 'https://localhost'
    assert 'POST' in response.headers.get('Access-Control-Allow-Methods', '')


def test_legacy_capacitor_ios_origin_is_allowed(client):
    response = _preflight(client, 'capacitor://localhost')

    assert response.status_code == 200
    assert response.headers.get('Access-Control-Allow-Origin') == 'capacitor://localhost'
    assert 'POST' in response.headers.get('Access-Control-Allow-Methods', '')


def test_legacy_capacitor_android_origin_is_allowed(client):
    response = _preflight(client, 'http://localhost')

    assert response.status_code == 200
    assert response.headers.get('Access-Control-Allow-Origin') == 'http://localhost'
    assert 'POST' in response.headers.get('Access-Control-Allow-Methods', '')


def test_untrusted_origin_is_not_allowed(client):
    response = _preflight(client, 'https://evil.example')

    assert response.status_code == 200
    assert response.headers.get('Access-Control-Allow-Origin') is None
