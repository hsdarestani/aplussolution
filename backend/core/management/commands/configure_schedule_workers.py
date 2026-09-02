from __future__ import annotations

import re
import unicodedata

from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import User, WorkerProfile
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
    'Izabella Somodo': ['housekeeping'],
    'Musa Jamali': ['service', 'housekeeping', 'front_office'],
    'Max Najmudinov': ['service'],
}

DELETE_FROM_WORKFORCE = {'Lara Mohieddine', 'Julia Stahl'}


def normalize_name(value: str) -> str:
    text = unicodedata.normalize('NFKD', str(value or ''))
    text = ''.join(char for char in text if not unicodedata.combining(char))
    text = text.casefold()
    return re.sub(r'[^a-z0-9]+', ' ', text).strip()


def worker_name(worker: WorkerProfile) -> str:
    return (worker.user.get_full_name() or worker.user.email or '').strip()


def _find_worker(workers: list[WorkerProfile], target: str):
    wanted = normalize_name(target)
    exact = [worker for worker in workers if normalize_name(worker_name(worker)) == wanted]
    if len(exact) == 1:
        return exact[0]
    # Names imported from WIW can occasionally omit punctuation/initial dots.
    wanted_parts = wanted.split()
    fuzzy = []
    for worker in workers:
        current = normalize_name(worker_name(worker))
        parts = current.split()
        if not wanted_parts or not parts:
            continue
        if current.startswith(wanted) or wanted.startswith(current):
            fuzzy.append(worker)
            continue
        if parts[0] == wanted_parts[0] and parts[-1] == wanted_parts[-1]:
            fuzzy.append(worker)
    return fuzzy[0] if len(fuzzy) == 1 else None


class Command(BaseCommand):
    help = 'Apply the approved mobile Dienstplan worker groups/client visibility without touching unrelated workers.'

    def handle(self, *args, **options):
        workers = list(WorkerProfile.objects.select_related('user').all())
        updated = []
        missing = []
        deleted = []

        with transaction.atomic():
            for target, groups in WORKER_CONFIG.items():
                worker = _find_worker(workers, target)
                if not worker:
                    missing.append(target)
                    continue
                worker.schedule_groups = normalized_groups(groups)
                # Empty means unrestricted/all clients in shift_visible_to_worker().
                worker.open_shift_client_ids = []
                worker.active = True
                worker.save(update_fields=['schedule_groups', 'open_shift_client_ids', 'active', 'updated_at'])
                updated.append(worker_name(worker))

            for target in DELETE_FROM_WORKFORCE:
                matches = [worker for worker in workers if normalize_name(worker_name(worker)) == normalize_name(target)]
                worker = matches[0] if len(matches) == 1 else None
                if not worker:
                    # Already removed is a valid idempotent state.
                    continue
                label = worker_name(worker)
                user = worker.user
                # Julia is a client in the business data. If an inconsistent
                # client-role account has a WorkerProfile, remove only that
                # employee profile and preserve the client login/contact.
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
