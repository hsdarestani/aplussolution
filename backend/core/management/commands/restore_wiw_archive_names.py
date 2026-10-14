"""Restore display names of inactive WIW migration placeholders from a private CSV.

Input columns: wiw_user_id,first_name,last_name
Only name fields of exact inactive archive placeholders can change. The private
mapping file is intentionally never committed to the public repository.
"""
import csv
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import WorkerProfile


def read_mapping(file_path):
    source = Path(file_path)
    if not source.is_file():
        raise CommandError('Private WIW mapping CSV file not found.')
    with source.open('r', encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        required = {'wiw_user_id', 'first_name', 'last_name'}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise CommandError('CSV must contain wiw_user_id,first_name,last_name.')
        mapping = {}
        for row in reader:
            wid = str(row['wiw_user_id'] or '').strip()
            first = str(row['first_name'] or '').strip()
            last = str(row['last_name'] or '').strip()
            if not wid.isdecimal() or wid == '0' or not (first or last):
                raise CommandError('Invalid WIW id or empty historical worker name.')
            if len(first) > 150 or len(last) > 150:
                raise CommandError('Historical worker name is too long.')
            names = (first, last)
            if wid in mapping and mapping[wid] != names:
                raise CommandError('Conflicting names for the same WIW id.')
            mapping[wid] = names
    return mapping


class Command(BaseCommand):
    help = (
        'Safely backfill names on inactive WIW-HIST placeholder users from a '
        'private export. Read-only by default; pass --apply to update names.'
    )

    def add_arguments(self, parser):
        parser.add_argument('file', help='Private WIW-id-to-name CSV, never commit to Git')
        parser.add_argument('--apply', action='store_true')

    def handle(self, *args, **options):
        mapping = read_mapping(options['file'])
        counts = {
            'mapping_rows': len(mapping), 'updated': 0, 'already_named': 0,
            'not_found': 0, 'skipped_not_archival': 0, 'skipped_active': 0,
            'name_conflicts': 0, 'would_update': 0,
        }
        with transaction.atomic():
            qs = WorkerProfile.objects.select_related('user')
            if options['apply']:
                qs = qs.select_for_update()
            profiles = {str(w.wiw_user_id): w for w in qs.filter(wiw_user_id__in=mapping)}
            for wid, (first, last) in mapping.items():
                worker = profiles.get(wid)
                if not worker:
                    counts['not_found'] += 1
                    continue
                user = worker.user
                historical = (
                    worker.employee_number == f'WIW-HIST-{wid}'
                    and str(user.wiw_id or '') == wid
                    and str(user.email or '').lower() == f'wiw-{wid}@sync.invalid'
                )
                if not historical:
                    counts['skipped_not_archival'] += 1
                    continue
                if user.is_active or worker.active or user.is_staff or user.is_superuser:
                    counts['skipped_active'] += 1
                    continue
                present = ((user.first_name or '').strip(), (user.last_name or '').strip())
                if present == (first, last):
                    counts['already_named'] += 1
                    continue
                if any(present):
                    counts['name_conflicts'] += 1
                    continue
                if options['apply']:
                    user.first_name = first
                    user.last_name = last
                    user.save(update_fields=['first_name', 'last_name'])
                    counts['updated'] += 1
                else:
                    counts['would_update'] += 1
        # IDs and names are intentionally excluded from logs.
        self.stdout.write(json.dumps({'dry_run': not options['apply'], **counts}, sort_keys=True))
