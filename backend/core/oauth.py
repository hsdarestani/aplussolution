import time
from pathlib import Path
from urllib.parse import urlencode
import jwt,requests
from django.conf import settings
from django.core import signing
from django.utils.crypto import get_random_string
from rest_framework_simplejwt.tokens import RefreshToken
from .models import User

def _state(provider,target): return signing.dumps({'provider':provider,'target':target,'nonce':get_random_string(24)},salt='social-oauth')
def start(provider,target):
    state=_state(provider,target)
    if provider=='google':
        params={'client_id':settings.GOOGLE_OAUTH_CLIENT_ID,'redirect_uri':settings.GOOGLE_OAUTH_REDIRECT_URI,'response_type':'code','scope':'openid email profile','access_type':'offline','prompt':'select_account','state':state}
        return 'https://accounts.google.com/o/oauth2/v2/auth?'+urlencode(params)
    if provider=='apple':
        params={'client_id':settings.APPLE_SERVICE_ID,'redirect_uri':settings.APPLE_OAUTH_REDIRECT_URI,'response_type':'code id_token','response_mode':'form_post','scope':'name email','state':state}
        return 'https://appleid.apple.com/auth/authorize?'+urlencode(params)
    raise ValueError('Unbekannter Anbieter')
def apple_client_secret():
    key=settings.APPLE_PRIVATE_KEY
    if not key and settings.APPLE_PRIVATE_KEY_PATH: key=Path(settings.APPLE_PRIVATE_KEY_PATH).read_text(encoding='utf-8')
    if not key: raise ValueError('Apple Private Key fehlt.')
    now=int(time.time())
    return jwt.encode({'iss':settings.APPLE_TEAM_ID,'iat':now,'exp':now+86400*180,'aud':'https://appleid.apple.com','sub':settings.APPLE_SERVICE_ID},key,algorithm='ES256',headers={'kid':settings.APPLE_KEY_ID})
def exchange(provider,code):
    if provider=='google':
        response=requests.post('https://oauth2.googleapis.com/token',timeout=15,data={'code':code,'client_id':settings.GOOGLE_OAUTH_CLIENT_ID,'client_secret':settings.GOOGLE_OAUTH_CLIENT_SECRET,'redirect_uri':settings.GOOGLE_OAUTH_REDIRECT_URI,'grant_type':'authorization_code'}); response.raise_for_status(); token=response.json()
        info=requests.get('https://openidconnect.googleapis.com/v1/userinfo',headers={'Authorization':f"Bearer {token['access_token']}"},timeout=15); info.raise_for_status(); return info.json()
    response=requests.post('https://appleid.apple.com/auth/token',timeout=15,data={'code':code,'client_id':settings.APPLE_SERVICE_ID,'client_secret':apple_client_secret(),'redirect_uri':settings.APPLE_OAUTH_REDIRECT_URI,'grant_type':'authorization_code'}); response.raise_for_status(); token=response.json()
    key=jwt.PyJWKClient('https://appleid.apple.com/auth/keys').get_signing_key_from_jwt(token['id_token']).key
    return jwt.decode(token['id_token'],key,algorithms=['RS256'],audience=settings.APPLE_SERVICE_ID,issuer='https://appleid.apple.com')
def finish(provider,code,state):
    data=signing.loads(state,salt='social-oauth',max_age=600)
    if data['provider']!=provider: raise ValueError('Ungültiger OAuth-Status')
    profile=exchange(provider,code); email=profile.get('email')
    if not email: raise ValueError('Der Anbieter hat keine E-Mail-Adresse geliefert.')
    try:
        user=User.objects.get(email=email.lower())
    except User.DoesNotExist as exc:
        raise ValueError('Für diese E-Mail-Adresse wurde noch kein Portalzugang durch die Administration angelegt.') from exc
    if not user.is_active:
        raise ValueError('Dieser Portalzugang ist deaktiviert.')
    changed=[]
    if not user.first_name and profile.get('given_name'):
        user.first_name=profile.get('given_name',''); changed.append('first_name')
    if not user.last_name and profile.get('family_name'):
        user.last_name=profile.get('family_name',''); changed.append('last_name')
    if changed: user.save(update_fields=changed)
    refresh=RefreshToken.for_user(user); target=data['target']; separator='&' if '?' in target else '?'
    return f"{target}{separator}access={refresh.access_token}&refresh={refresh}"
