from __future__ import annotations

import re
import unicodedata

from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import User, WorkerProfile, EmployeeMasterData
from core.shift_rules import normalized_groups


WORKER_CONFIG = {
    'Tooba Amjad': ['service'],
    'Shahrzad Bagheri': ['service'],
    'Michelle Brettschneider': ['service', 'front_office'],
    'Michele Corrado': ['service'],
    'Loreen G.': ['service'],
    'Katerina Gentsou': ['service', 'front_office'],
    'Yohannes Kiffle': ['service'],
    'Ksenia Marszalek': ['service'],
    'Arina Martynko': ['service'],
    'Claire Odinius': ['service'],
    'Ilhan Omerovic': ['service'],
    'Ilayda Tarhan': ['service', 'front_office'],
    'Francesco Trulli': ['service'],
    'Akeel Zafar': ['service'],
    'Izabella Somodi': ['housekeeping'],
    'Musa Jamali': ['service', 'housekeeping', 'front_office'],
    'Max Najmudinov': ['service'],
}

# Historic data used the spelling "Somodo" in a few local configuration files,
# while the approved employee email and the existing account use "Somodi".
# Treat both spellings as the same employee instead of creating/renaming accounts.
WORKER_NAME_ALIASES = {
    'Izabella Somodi': {'Izabella Somodo'},
}

# Explicitly requested on 2026-09-02. Pending addresses are reserved, non-routable
# identifiers required by the unique email login schema; no invitations are sent.
APPROVED_NEW_WORKERS = {
    'Izabella Somodi': ('izabellasomodi21@yahoo.com', 'LOCAL-IZABELLA-SOMODI'),
    'Musa Jamali': ('musa.jamali@pending.invalid', 'LOCAL-MUSA-JAMALI'),
    'Max Najmudinov': ('max.najmudinov@pending.invalid', 'LOCAL-MAX-NAJMUDINOV'),
}


DELETE_FROM_WORKFORCE = {'Lara Mohieddine', 'Julia Stahl'}


def normalize_name(value: str) -> str:
    text = unicodedata.normalize('NFKD', str(value or ''))
    text = ''.join(char for char in text if not unicodedata.combining(char))
    text = text.casefold()
    return re.sub(r'[^a-z0-9]+', ' ', text).strip()


def accepted_names(target: str) -> set[str]:
    values = {target, *WORKER_NAME_ALIASES.get(target, set())}
    return {normalize_name(value) for value in values}


def worker_name(worker: WorkerProfile) -> str:
    return (worker.user.get_full_name() or worker.user.email or '').strip()


def _find_worker(workers: list[WorkerProfile], target: str):
    wanted_names = accepted_names(target)
    exact = [worker for worker in workers if normalize_name(worker_name(worker)) in wanted_names]
    if len(exact) == 1:
        return exact[0]

    wanted_parts = [value.split() for value in wanted_names if value]
    fuzzy = []
    for worker in workers:
        current = normalize_name(worker_name(worker))
        parts = current.split()
        if not parts:
            continue
        for target_parts in wanted_parts:
            if not target_parts:
                continue
            target_text = ' '.join(target_parts)
            if current.startswith(target_text) or target_text.startswith(current):
                fuzzy.append(worker)
                break
            if parts[0] == target_parts[0] and parts[-1] == target_parts[-1]:
                fuzzy.append(worker)
                break
    return fuzzy[0] if len(fuzzy) == 1 else None


class Command(BaseCommand):
    help = 'Apply the approved mobile Dienstplan worker groups/client visibility without touching unrelated workers.'

    def handle(self, *args, **options):
        workers = list(WorkerProfile.objects.select_related('user').all())
        updated = []
        missing = []
        deleted = []

        with transaction.atomic():
            for name, (email, employee_number) in APPROVED_NEW_WORKERS.items():
                if _find_worker(workers, name):
                    continue

                first_name, last_name = name.split(' ', 1)
                aliases = accepted_names(name)
                user = User.objects.filter(email__iexact=email).first()
                if not user:
                    candidates = list(User.objects.filter(first_name__iexact=first_name))
                    matching = [candidate for candidate in candidates if normalize_name(candidate.get_full_name()) in aliases]
                    if len(matching) == 1:
                        user = matching[0]
                    elif len(matching) > 1:
                        raise ValueError(f'Ambiguous requested worker: {name}')

                if user:
                    has_client_identity = user.role == User.Role.CLIENT or user.client_companies.exists()
                    if has_client_identity and not hasattr(user, 'worker_profile'):
                        raise ValueError(f'Existing client account cannot be reused as worker: {name}')
                    if user.role != User.Role.WORKER:
                        user.role = User.Role.WORKER
                        user.save(update_fields=['role'])
                else:
                    user = User.objects.create_user(email, first_name=first_name, last_name=last_name, role=User.Role.WORKER)

                worker, created = WorkerProfile.objects.get_or_create(
                    user=user, defaults={'employee_number': employee_number, 'active': True}
                )
                if not worker.active:
                    worker.active = True
                    worker.save(update_fields=['active', 'updated_at'])
                if created:
                    EmployeeMasterData.objects.get_or_create(
                        worker=worker,
                        defaults={'data': {}, 'missing_fields': ['email'] if email.endswith('@pending.invalid') else []},
                    )
                    self.stdout.write(f'created requested worker: {name}')
                workers.append(worker)

            for target, groups in WORKER_CONFIG.items():
                worker = _find_worker(workers, target)
                if not worker:
                    missing.append(target)
                    continue
                worker.schedule_groups = normalized_groups(groups)
                worker.open_shift_client_ids = []
                worker.active = True
                worker.save(update_fields=['schedule_groups', 'open_shift_client_ids', 'active', 'updated_at'])
                updated.append(worker_name(worker))

            for target in DELETE_FROM_WORKFORCE:
                matches = [worker for worker in workers if normalize_name(worker_name(worker)) == normalize_name(target)]
                worker = matches[0] if len(matches) == 1 else None
                if not worker:
                    continue
                label = worker_name(worker)
                user = worker.user
                if target == 'Julia Stahl' or user.role == User.Role.CLIENT or user.client_companies.exists():
                    worker.delete()
                    if target == 'Julia Stahl' and user.role == User.Role.WORKER:
                        user.role = User.Role.CLIENT
                        user.save(update_fields=['role'])
                else:
                    user.delete()
                deleted.append(label)

        self.stdout.write(self.style.SUCCESS(
            f'Dienstplan workers configured: updated={len(updated)} deleted={len(deleted)} missing={len(missing)}'
        ))
        if updated:
            self.stdout.write('updated: ' + ', '.join(sorted(updated)))
        if deleted:
            self.stdout.write('deleted from workforce: ' + ', '.join(sorted(deleted)))
        if missing:
            self.stdout.write(self.style.WARNING('not found: ' + ', '.join(sorted(missing))))
