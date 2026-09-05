import os

from django.core.management.base import BaseCommand

from core.document_engine import seed_document_catalog
from core.models import Position, User, WorkerProfile


STORE_REVIEW_EMAIL = 'store-review@aplus-solution.de'
# Safe fallback used only when the reviewer account is first created or somehow
# has no usable password. Publisher owns the live App Store review credential
# and synchronizes it immediately before a store submission.
STORE_REVIEW_PASSWORD_HASH = (
    'pbkdf2_sha256$1000000$uknDBax_fCIHUJqYLqLtyA$'
    '26a+GsJZD5rnNRxW85Tj7CBkjwrGhUZayS/VwCz2QZA='
)


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
                if not user.has_usable_password() and configured_password:
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

        reviewer, reviewer_created = User.objects.get_or_create(
            email=STORE_REVIEW_EMAIL,
            defaults={
                'username': STORE_REVIEW_EMAIL,
                'first_name': 'Store',
                'last_name': 'Reviewer',
                'role': User.Role.WORKER,
                'is_active': True,
                'is_staff': False,
                'is_superuser': False,
                'password': STORE_REVIEW_PASSWORD_HASH,
            },
        )
        reviewer_changes = []
        reviewer_expected = {
            'username': STORE_REVIEW_EMAIL,
            'first_name': 'Store',
            'last_name': 'Reviewer',
            'role': User.Role.WORKER,
            'is_active': True,
            'is_staff': False,
            'is_superuser': False,
        }
        for field, value in reviewer_expected.items():
            if getattr(reviewer, field) != value:
                setattr(reviewer, field, value)
                reviewer_changes.append(field)

        # Do not overwrite a valid password on deploy. Publisher is the single
        # source of truth for the credential sent to App Store Connect and syncs
        # that secret into this account immediately before submission.
        password_repaired = False
        if not reviewer.has_usable_password():
            reviewer.password = STORE_REVIEW_PASSWORD_HASH
            reviewer_changes.append('password')
            password_repaired = True
        if reviewer_changes:
            reviewer.save(update_fields=sorted(set(reviewer_changes)))

        worker, worker_created = WorkerProfile.objects.get_or_create(
            user=reviewer,
            defaults={
                'employee_number': 'STORE-REVIEW-001',
                'employment_type': WorkerProfile.EmploymentType.MINI,
                'monthly_hours': 0,
                'tariff_hourly_rate': 0,
                'extra_allowance': 0,
                'ranking_points': 0,
                'skills': [],
                'active': True,
            },
        )
        worker_changes = []
        if not worker.active:
            worker.active = True
            worker_changes.append('active')
        if worker.employee_number != 'STORE-REVIEW-001':
            if not WorkerProfile.objects.filter(employee_number='STORE-REVIEW-001').exclude(pk=worker.pk).exists():
                worker.employee_number = 'STORE-REVIEW-001'
                worker_changes.append('employee_number')
        if worker_changes:
            worker.save(update_fields=worker_changes)

        self.stdout.write(
            self.style.SUCCESS(
                'App-Store-Reviewer geprüft: '
                f'email={STORE_REVIEW_EMAIL}, created={reviewer_created}, '
                f'active={reviewer.is_active}, role={reviewer.role}, '
                f'usable_password={reviewer.has_usable_password()}, '
                f'password_repaired={password_repaired}, '
                f'worker_profile_created={worker_created}, worker_active={worker.active}, '
                f'fields_repaired={",".join(reviewer_changes + worker_changes) or "none"}'
            )
        )

        # Seed missing standard positions, but never overwrite the locally managed
        # active/inactive choice for an existing position during a deployment.
        for name in ['Servicekraft', 'Serviceleitung', 'Front Office', 'Housekeeping', 'Bar-Support']:
            Position.objects.get_or_create(name=name, defaults={'active': True})
        result = seed_document_catalog()
        self.stdout.write(self.style.SUCCESS(f'Grunddaten sind bereit. Dokumentkatalog: {result}'))
