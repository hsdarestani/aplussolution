import os

from django.core.management.base import BaseCommand

from core.document_engine import seed_document_catalog
from core.models import Position, User


class Command(BaseCommand):
    help = 'Erstellt Grunddaten, Dokumentkatalog und den ersten Administrator.'

    def handle(self, *args, **kwargs):
        email = (os.getenv('DJANGO_SUPERUSER_EMAIL') or '').strip().lower()
        configured_password = os.getenv('DJANGO_SUPERUSER_PASSWORD') or ''

        if email:
            user = User.objects.filter(email__iexact=email).first()
            if not user:
                user = User.objects.create_superuser(
                    email=email,
                    password=configured_password or None,
                    first_name=os.getenv('DJANGO_SUPERUSER_FIRST_NAME', 'A+'),
                    last_name=os.getenv('DJANGO_SUPERUSER_LAST_NAME', 'Admin'),
                )
                self.stdout.write(self.style.SUCCESS(f'Administrator erstellt: {email}'))
            else:
                changed_fields = []
                expected = {
                    'email': email,
                    'username': email,
                    'role': User.Role.ADMIN,
                    'is_active': True,
                    'is_staff': True,
                    'is_superuser': True,
                }
                for field, value in expected.items():
                    if getattr(user, field) != value:
                        setattr(user, field, value)
                        changed_fields.append(field)

                password_repaired = False
                if configured_password and not user.check_password(configured_password):
                    user.set_password(configured_password)
                    changed_fields.append('password')
                    password_repaired = True

                if changed_fields:
                    user.save(update_fields=sorted(set(changed_fields)))

                configured_password_matches = bool(
                    configured_password and user.check_password(configured_password)
                )
                self.stdout.write(
                    self.style.SUCCESS(
                        'Administrator geprüft: '
                        f'email={email}, active={user.is_active}, role={user.role}, '
                        f'staff={user.is_staff}, superuser={user.is_superuser}, '
                        f'usable_password={user.has_usable_password()}, '
                        f'configured_password_matches={configured_password_matches}, '
                        f'password_repaired={password_repaired}, '
                        f'fields_repaired={",".join(changed_fields) or "none"}'
                    )
                )

        for name in ['Servicekraft', 'Hostess', 'Eventhelfer', 'Lagerhelfer', 'Inventurhelfer', 'Promoter', 'Logistiker']:
            Position.objects.get_or_create(name=name)
        result = seed_document_catalog()
        self.stdout.write(self.style.SUCCESS(f'Grunddaten sind bereit. Dokumentkatalog: {result}'))
