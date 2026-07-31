import hashlib
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
        send_mail(
            'A+ Solution – Mitarbeiterportal aktivieren',
            'Hallo,\n\nbitte aktiviere dein A+ Solution Mitarbeiterportal über diesen Link:\n'
            f'{activation_url}\n\nDer Link ist einmalig und 72 Stunden gültig.',
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
        )
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
