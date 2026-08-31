import os
from datetime import timedelta
from pathlib import Path
import dj_database_url
BASE_DIR=Path(__file__).resolve().parent.parent
SECRET_KEY=os.getenv('DJANGO_SECRET_KEY','development-only-key')
DEBUG=os.getenv('DEBUG','0')=='1'
ALLOWED_HOSTS=[x.strip() for x in os.getenv('ALLOWED_HOSTS','localhost,127.0.0.1').split(',') if x.strip()]
INSTALLED_APPS=['django.contrib.admin','django.contrib.auth','django.contrib.contenttypes','django.contrib.sessions','django.contrib.messages','django.contrib.staticfiles','corsheaders','rest_framework','django_filters','core']
MIDDLEWARE=['django.middleware.security.SecurityMiddleware','corsheaders.middleware.CorsMiddleware','django.contrib.sessions.middleware.SessionMiddleware','django.middleware.common.CommonMiddleware','django.middleware.csrf.CsrfViewMiddleware','django.contrib.auth.middleware.AuthenticationMiddleware','django.contrib.messages.middleware.MessageMiddleware','django.middleware.clickjacking.XFrameOptionsMiddleware']
ROOT_URLCONF='config.urls'
TEMPLATES=[{'BACKEND':'django.template.backends.django.DjangoTemplates','DIRS':[BASE_DIR/'templates'],'APP_DIRS':True,'OPTIONS':{'context_processors':['django.template.context_processors.request','django.contrib.auth.context_processors.auth','django.contrib.messages.context_processors.messages']}}]
WSGI_APPLICATION='config.wsgi.application'
DATABASES={'default':dj_database_url.config(default=f'sqlite:///{BASE_DIR/"db.sqlite3"}',conn_max_age=600)}
AUTH_USER_MODEL='core.User'
LANGUAGE_CODE='de-de'; TIME_ZONE='Europe/Berlin'; USE_I18N=True; USE_TZ=True
STATIC_URL='/static/'; STATIC_ROOT=BASE_DIR/'staticfiles'; MEDIA_URL='/media/'; MEDIA_ROOT=BASE_DIR/'media'; DEFAULT_AUTO_FIELD='django.db.models.BigAutoField'
CORS_ALLOWED_ORIGINS=[x.strip() for x in os.getenv('CORS_ALLOWED_ORIGINS','http://localhost:8080').split(',') if x.strip()]
# Current native builds use https://localhost. Older released Capacitor builds can
# still identify as capacitor://localhost (iOS) or http://localhost (Android).
# Keep these exact native origins independent from a persisted production .env so
# installed store builds remain compatible while arbitrary origins stay blocked.
NATIVE_APP_CORS_ORIGINS=[x.strip() for x in os.getenv('NATIVE_APP_CORS_ORIGINS','https://localhost,capacitor://localhost,http://localhost').split(',') if x.strip()]
for origin in NATIVE_APP_CORS_ORIGINS:
    if origin not in CORS_ALLOWED_ORIGINS:
        CORS_ALLOWED_ORIGINS.append(origin)
CSRF_TRUSTED_ORIGINS=[x.strip() for x in os.getenv('CSRF_TRUSTED_ORIGINS','http://localhost:8080').split(',') if x.strip()]
CORS_ALLOW_CREDENTIALS=True; SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO','https'); SESSION_COOKIE_SECURE=not DEBUG; CSRF_COOKIE_SECURE=not DEBUG
REST_FRAMEWORK={'DEFAULT_AUTHENTICATION_CLASSES':('rest_framework_simplejwt.authentication.JWTAuthentication',),'DEFAULT_PERMISSION_CLASSES':('rest_framework.permissions.IsAuthenticated',),'DEFAULT_FILTER_BACKENDS':('django_filters.rest_framework.DjangoFilterBackend','rest_framework.filters.SearchFilter','rest_framework.filters.OrderingFilter'),'DEFAULT_PAGINATION_CLASS':'core.pagination.PathAwarePagination','PAGE_SIZE':50,'DEFAULT_RENDERER_CLASSES':('rest_framework.renderers.JSONRenderer',) if not DEBUG else ('rest_framework.renderers.JSONRenderer','rest_framework.renderers.BrowsableAPIRenderer')}
SIMPLE_JWT={'ACCESS_TOKEN_LIFETIME':timedelta(minutes=30),'REFRESH_TOKEN_LIFETIME':timedelta(days=30),'ROTATE_REFRESH_TOKENS':True,'BLACKLIST_AFTER_ROTATION':False}
CELERY_BROKER_URL=os.getenv('REDIS_URL','redis://localhost:6379/0'); CELERY_RESULT_BACKEND=CELERY_BROKER_URL
ATTENDANCE_REMINDER_MINUTES=int(os.getenv('ATTENDANCE_REMINDER_MINUTES','15'))
CELERY_BEAT_SCHEDULE={'attendance-reminders-5min':{'task':'core.tasks.send_attendance_reminders','schedule':300},'contract-reminders-daily':{'task':'core.tasks.send_contract_reminders','schedule':86400},'shift-reminders-hourly':{'task':'core.tasks.send_shift_reminders','schedule':3600},'client-contract-generation-hourly':{'task':'core.tasks.generate_due_client_contracts','schedule':3600},'working-time-sync-daily':{'task':'core.tasks.sync_working_time_current_year','schedule':86400},'working-time-backup-weekly':{'task':'core.tasks.backup_working_time','schedule':604800},'wiw-readonly-sync-5min':{'task':'core.tasks.sync_when_i_work','schedule':300,'args':['incremental']}}
WORKER_EMAILS_ENABLED=os.getenv('WORKER_EMAILS_ENABLED','0')=='1'
EMAIL_BACKEND='core.email_backend.WorkerAwareSMTPEmailBackend' if os.getenv('EMAIL_HOST') else 'django.core.mail.backends.console.EmailBackend'
EMAIL_HOST=os.getenv('EMAIL_HOST',''); EMAIL_PORT=int(os.getenv('EMAIL_PORT','587')); EMAIL_HOST_USER=os.getenv('EMAIL_HOST_USER',''); EMAIL_HOST_PASSWORD=os.getenv('EMAIL_HOST_PASSWORD',''); EMAIL_USE_TLS=os.getenv('EMAIL_USE_TLS','1')=='1'
DEFAULT_FROM_EMAIL=os.getenv('DEFAULT_FROM_EMAIL','A+ Solution <noreply@aplus-solution.de>'); ADMIN_NOTIFICATION_EMAIL=os.getenv('ADMIN_NOTIFICATION_EMAIL','info@aplus-solution.de'); APP_URL=os.getenv('APP_URL','http://localhost:8080')
GOOGLE_OAUTH_CLIENT_ID=os.getenv('GOOGLE_OAUTH_CLIENT_ID',''); GOOGLE_OAUTH_CLIENT_SECRET=os.getenv('GOOGLE_OAUTH_CLIENT_SECRET',''); GOOGLE_OAUTH_REDIRECT_URI=os.getenv('GOOGLE_OAUTH_REDIRECT_URI','')
APPLE_SERVICE_ID=os.getenv('APPLE_SERVICE_ID',''); APPLE_TEAM_ID=os.getenv('APPLE_TEAM_ID',''); APPLE_KEY_ID=os.getenv('APPLE_KEY_ID',''); APPLE_PRIVATE_KEY=os.getenv('APPLE_PRIVATE_KEY','').replace('\\n','\n'); APPLE_PRIVATE_KEY_PATH=os.getenv('APPLE_PRIVATE_KEY_PATH',''); APPLE_OAUTH_REDIRECT_URI=os.getenv('APPLE_OAUTH_REDIRECT_URI','')
COMPANY_NAME=os.getenv('COMPANY_NAME','A+ Solution GmbH'); COMPANY_ADDRESS=os.getenv('COMPANY_ADDRESS',''); AUEG_LICENSE_AUTHORITY=os.getenv('AUEG_LICENSE_AUTHORITY',''); AUEG_LICENSE_DATE=os.getenv('AUEG_LICENSE_DATE','')

# During the migration window WIW is a read-only upstream feed. A+ never writes back.
OPENAI_API_KEY=os.getenv('OPENAI_API_KEY',os.getenv('WIW_OPENAI_KEY',''))
OPENAI_MODEL=os.getenv('OPENAI_MODEL',os.getenv('WIW_OPENAI_MODEL','gpt-4o-mini'))
OPENAI_HTTP_TIMEOUT=int(os.getenv('OPENAI_HTTP_TIMEOUT','30'))
WIW_DEV_KEY=os.getenv('WIW_DEV_KEY','')
WIW_EMAIL=os.getenv('WIW_EMAIL','')
WIW_PASSWORD=os.getenv('WIW_PASSWORD','')
WIW_USER_ID=os.getenv('WIW_USER_ID','')
WIW_WEBHOOK_SECRET=os.getenv('WIW_WEBHOOK_SECRET','')
WIW_OPENAI_KEY=OPENAI_API_KEY
WIW_HTTP_TIMEOUT=int(os.getenv('WIW_HTTP_TIMEOUT',str(OPENAI_HTTP_TIMEOUT)))
WIW_TOKEN_CACHE_SECONDS=int(os.getenv('WIW_TOKEN_CACHE_SECONDS','3300'))
WIW_SYNC_ENABLED=os.getenv('WIW_SYNC_ENABLED','0')=='1'
WIW_READ_ONLY=os.getenv('WIW_READ_ONLY','1')=='1'
LIBREOFFICE_BINARY=os.getenv('LIBREOFFICE_BINARY','libreoffice')
COMPANY_BUSINESS_NUMBER=os.getenv('COMPANY_BUSINESS_NUMBER','')

WIW_DEFAULT_LOCATION_ID=os.getenv('WIW_DEFAULT_LOCATION_ID','')
WIW_OPENAI_MODEL=OPENAI_MODEL
WORKING_TIME_DEFAULT_BREAK_MINUTES=int(os.getenv('WORKING_TIME_DEFAULT_BREAK_MINUTES','0'))
WORKING_TIME_DEFAULT_MONTHLY_LIMIT=os.getenv('WORKING_TIME_DEFAULT_MONTHLY_LIMIT','0')
WORKING_TIME_DEFAULT_HOURLY_RATE=os.getenv('WORKING_TIME_DEFAULT_HOURLY_RATE','0')

# Premium enterprise settings (SAML/SSO). Kept in a separate module so IdP secrets remain environment-only.
from .premium_settings import *  # noqa: F401,F403,E402
