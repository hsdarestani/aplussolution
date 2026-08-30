import hashlib
import logging
import secrets
from datetime import timedelta
from urllib.parse import quote

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from .models import User, WorkerProfile
from .portal_models import PortalInvitation


logger = logging.getLogger(__name__)


def is_real_email(email: str) -> bool:
    value = (email or '').strip().lower()
    return bool(value and '@' in value and not value.endswith('@sync.invalid'))


def invitation_status(worker: WorkerProfile):
    user = worker.user
    pending = PortalInvitation.objects.filter(
        user=user,
        used_at__isnull=True,
        expires_at__gt=timezone.now(),
    ).order_by('-created_at').first()
    if user.has_usable_password() and user.is_onboarded:
        state = 'active'
    elif not is_real_email(user.email):
        state = 'missing_email'
    elif pending:
        state = 'invited'
    else:
        state = 'not_activated'
    return {
        'worker_id': str(worker.id),
        'user_id': str(user.id),
        'email': user.email,
        'name': user.get_full_name() or user.email,
        'state': state,
        'has_usable_password': user.has_usable_password(),
        'is_onboarded': user.is_onboarded,
        'invitation_expires_at': pending.expires_at if pending else None,
    }


def _token_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


@transaction.atomic
def create_portal_invitation(worker: WorkerProfile, created_by=None, lifetime_hours=72):
    user = worker.user
    if user.role != User.Role.WORKER or not worker.active or not user.is_active:
        raise ValueError('Nur aktive Mitarbeiter können eingeladen werden.')
    if not is_real_email(user.email):
        raise ValueError('Für diesen Mitarbeiter fehlt eine echte E-Mail-Adresse.')

    PortalInvitation.objects.filter(user=user, used_at__isnull=True).delete()
    raw = secrets.token_urlsafe(32)
    invitation = PortalInvitation.objects.create(
        user=user,
        token_hash=_token_hash(raw),
        expires_at=timezone.now() + timedelta(hours=lifetime_hours),
        created_by=created_by,
    )
    activation_url = f"{settings.APP_URL.rstrip('/')}/aktivieren?token={quote(raw)}"
    delivered = False
    if settings.EMAIL_HOST and settings.EMAIL_HOST_USER:
        try:
            employee_name = user.get_full_name() or user.first_name or 'Mitarbeiter/in'
            send_mail(
                'A+ Solution App – Zugang aktivieren',
                f'Hallo {employee_name},\n\n'
                'dein Zugang zur A+ Solution Workforce-App ist vorbereitet. Über die App kannst du unter anderem deine Schichten und OpenShifts sehen, Arbeitszeiten erfassen, Verfügbarkeiten verwalten sowie Dokumente und Mitteilungen abrufen.\n\n'
                '1. App installieren\n'
                'iPhone / iPad (App Store):\n'
                'https://apps.apple.com/de/app/a-solution/id6799468007\n\n'
                'Android (Google Play):\n'
                'https://play.google.com/store/apps/details?id=de.aplussolution.workforce\n\n'
                '2. Zugang einmalig aktivieren\n'
                'Öffne diesen persönlichen Aktivierungslink und lege dein Passwort fest:\n'
                f'{activation_url}\n\n'
                '3. Danach in der App anmelden\n'
                f'E-Mail: {user.email}\n'
                'Melde dich mit dieser E-Mail-Adresse und dem gerade festgelegten Passwort an. Bitte erlaube Benachrichtigungen, damit du neue Schichten, Änderungen und Erinnerungen direkt erhältst.\n\n'
                'Der Aktivierungslink ist einmalig und 72 Stunden gültig. Wenn der Link abgelaufen ist oder du Hilfe brauchst, melde dich bitte bei A+ Solution.\n\n'
                'Viele Grüße\nA+ Solution GmbH',
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
                fail_silently=False,
            )
        except Exception:
            # Email delivery is best-effort. The invitation itself must remain
            # usable so an admin can copy the one-time activation URL even when
            # the mailbox/domain is unavailable (for example during QA).
            logger.warning('Portal invitation email delivery failed for user_id=%s', user.id, exc_info=True)
        else:
            invitation.delivered_at = timezone.now()
            invitation.delivery_channel = 'email'
            invitation.save(update_fields=['delivered_at', 'delivery_channel', 'updated_at'])
            delivered = True
    return invitation, activation_url, delivered


def resolve_invitation(raw_token: str):
    raw = (raw_token or '').strip()
    if not raw:
        raise ValueError('Aktivierungslink ist ungültig.')
    invitation = PortalInvitation.objects.select_related('user').filter(token_hash=_token_hash(raw)).first()
    if not invitation or invitation.used_at:
        raise ValueError('Aktivierungslink ist ungültig oder wurde bereits verwendet.')
    if invitation.expires_at <= timezone.now():
        raise ValueError('Aktivierungslink ist abgelaufen.')
    if not invitation.user.is_active or invitation.user.role != User.Role.WORKER:
        raise ValueError('Dieser Mitarbeiterzugang ist nicht aktiv.')
    return invitation


@transaction.atomic
def activate_portal(raw_token: str, password: str):
    if len(password or '') < 10:
        raise ValueError('Das Passwort muss mindestens 10 Zeichen lang sein.')
    invitation = resolve_invitation(raw_token)
    user = invitation.user
    user.set_password(password)
    user.is_onboarded = True
    user.save(update_fields=['password', 'is_onboarded'])
    invitation.used_at = timezone.now()
    invitation.save(update_fields=['used_at', 'updated_at'])
    refresh = RefreshToken.for_user(user)
    return user, str(refresh.access_token), str(refresh)
