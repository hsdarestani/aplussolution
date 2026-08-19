from urllib.parse import quote

from django.conf import settings
from django.http import HttpResponseRedirect
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny

from . import oauth


def _error_redirect(message: str):
    text = (message or 'OAuth-Anmeldung fehlgeschlagen.').strip()
    return HttpResponseRedirect(f"{settings.APP_URL}/?oauth_error={quote(text, safe='')}")


@api_view(['GET'])
@permission_classes([AllowAny])
def oauth_start(request, provider):
    # The callback target is server-controlled. Do not accept arbitrary redirect
    # targets from the browser.
    target = settings.APP_URL + '/auth/callback'
    try:
        return HttpResponseRedirect(oauth.start(provider, target))
    except Exception as exc:
        return _error_redirect(str(exc))


@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
def oauth_callback(request, provider):
    provider_error = request.data.get('error') or request.GET.get('error')
    if provider_error:
        return _error_redirect(f'{provider.capitalize()} hat die Anmeldung abgebrochen oder abgelehnt ({provider_error}).')

    code = request.data.get('code') or request.GET.get('code')
    state_value = request.data.get('state') or request.GET.get('state')
    if not code or not state_value:
        return _error_redirect('OAuth-Callback ist unvollständig. Bitte Anmeldung erneut starten.')

    try:
        return HttpResponseRedirect(oauth.finish(provider, code, state_value))
    except Exception as exc:
        return _error_redirect(str(exc))
