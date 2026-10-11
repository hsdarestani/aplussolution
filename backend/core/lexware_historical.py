"""Conservative, repeatable reconciliation of archived Lexware payroll evidence.

Only source-confirmed archived rows are used. Former staff accounts have no
login, no shifts, no invented hours. Previously imported payroll statements
and working-time balances are not modified. Ambiguous identities are held.
"""
import hashlib
import re
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from django.db import transaction

from .lexware_pdf import parse_lexware_pdf
from .models import AuditLog, Document, EmployeeMasterData, PayrollStatement, User, WorkerProfile
from .payroll_views import _employee_matchers, _find_worker, _lexware_document_kind, _norm


def _personnel_number(row):
    return re.sub(r'\s+', '', str(row.get('personal_number') or '')).upper()


def _source_identity(name, personnel=''):
    key = f'PERSONNEL:{personnel}' if personnel else f'NAME:{_norm(name)}'
    return hashlib.sha256(key.encode('utf-8')).hexdigest()[:22].upper()


def _historical_worker(name, personnel, aliases):
    """Only called after separate dry-run matching and ambiguity checks."""
    digest = _source_identity(name, personnel)
    code = f'LEXH-{digest}'
    worker = WorkerProfile.objects.select_related('user').filter(employee_number=code).first()
    if worker:
        return worker, False
    email = f'lexware-history-{digest.lower()}@inactive.invalid'
    existing = User.objects.filter(email=email).first()
    if existing:
        worker = WorkerProfile.objects.filter(user=existing).first()
        if worker:
            return worker, False
        # Never repurpose a user account whose origin we cannot verify.
        raise ValueError('Historical identity email conflicts with a non-worker account')
    first, _, last = name.strip().partition(' ')
    user = User(
        email=email, username=email, first_name=first,
        last_name=last, role=User.Role.WORKER, is_active=False,
        is_onboarded=False,
    )
    user.set_unusable_password()
    user.save()
    worker = WorkerProfile.objects.create(
        user=user, employee_number=code, active=False,
        employment_type=WorkerProfile.EmploymentType.HISTORICAL,
    )
    EmployeeMasterData.objects.create(
        worker=worker,
        data={
            'historical_lexware_only': True,
            'lexware_personal_number': personnel or '',
            'lexware_source_names': sorted(set(aliases)),
            'employment_type_unverified': True,
            'origin': 'verified_lexware_archived_documents',
        },
        source_map={'lexware_personal_number': 'archived_payslip', 'origin': 'lexware_archive'},
    )
    AuditLog.objects.create(
        actor=None, action='payroll.historical_worker_created',
        object_type='WorkerProfile', object_id=str(worker.pk),
        metadata={'inactive_login': True, 'archived_source': True},
    )
    return worker, True


def _evidence(year, month):
    period = f'{year:04d}-{month:02d}'
    sources = []
    errors = 0
    queryset = Document.objects.filter(
        folder=Document.Folder.PAYROLL,
        title__startswith=f'Lexware {period} ·',
    ).order_by('created_at')
    for document in queryset:
        if _lexware_document_kind(document.title) not in {'lohnabrechnungen', 'zahlungsliste'}:
            continue
        try:
            with document.file.open('rb') as stream:
                doc_kind, parsed = parse_lexware_pdf(stream.read())
        except Exception:
            errors += 1
            continue
        if doc_kind not in {'lohnabrechnungen', 'zahlungsliste'}:
            errors += 1
            continue
        for row in parsed:
            if not str(row.get('employee_name') or '').strip():
                continue
            sources.append((document.title, dict(row)))
    return sources, errors


def _ambiguous_name(key, candidates):
    tokens = set(key.split())
    # Prefix/subset variations might refer to different people; match only
    # with the same personal number, not by a surname/first name guess.
    for other in candidates:
        if other == key:
            continue
        other_tokens = set(_norm(other).split())
        if tokens < other_tokens or other_tokens < tokens:
            return True
    return False


def _row_key(title, row, period):
    return hashlib.sha256('|'.join([
        title, period, str(row.get('kind') or ''),
        _norm(row.get('employee_name')), _personnel_number(row),
        str(row.get('is_correction') or False),
        str(row.get('gross_amount') or ''),
        str(row.get('net_amount') or ''),
        str(row.get('payout_amount') or ''),
        str(row.get('amount') or ''),
        str(row.get('iban') or ''),
        str(row.get('page') or ''),
    ]).encode('utf-8')).hexdigest()


def _archived_evidence_keys(year, month):
    """Exact source evidence keys already attached to a 2025 payroll statement.

    Historical name variants can be shorter than the created worker's display
    name. A linked source row must not repeatedly appear as an unmatched
    employee merely because the display name is different. This is read-only
    and never attempts to match a new identity.
    """
    prefix = f'Lexware {year:04d}-{month:02d} ·'
    keys = set()
    for raw_data in PayrollStatement.objects.filter(
        period__year=year
    ).values_list('raw_data', flat=True):
        if not isinstance(raw_data, list):
            continue
        for entry in raw_data:
            if not isinstance(entry, dict):
                continue
            if (
                entry.get('source_type') in {'lexware_payslip_pdf', 'lexware_zahlungsliste_pdf'}
                and str(entry.get('source_file') or '').startswith(prefix)
                and isinstance(entry.get('key'), str)
            ):
                keys.add(entry['key'])
    return keys


def reconcile_archive(year=2025, month=12, *, apply=False):
    """Safely resolve historical employees and missing payslip/payment entries.

    The default is read-only. Even in apply mode, only originally unmatched
    lines are attached, and previously stored payroll or Saldo is untouched.
    """
    period = f'{year:04d}-{month:02d}'
    evidence, errors = _evidence(year, month)
    original = _employee_matchers()
    already_attached = _archived_evidence_keys(year, month)
    outstanding = [
        (title, row) for title, row in evidence
        if _find_worker({'employee_name': row['employee_name']}, original) is None
        and _row_key(
            title, row,
            str(row.get('period') or '') if row.get('kind') == 'payslip' else period,
        ) not in already_attached
    ]
    # Payslip personal numbers are reliable; payment lists alone have no ID.
    by_personnel = defaultdict(list)
    no_personnel = defaultdict(list)
    all_names = {_norm(row['employee_name']) for _, row in outstanding}
    for title, row in outstanding:
        pn = _personnel_number(row)
        if pn:
            by_personnel[pn].append((title, row))
        else:
            no_personnel[_norm(row['employee_name'])].append((title, row))

    groups = []
    for personnel, items in sorted(by_personnel.items()):
        names = sorted({str(r['employee_name']).strip() for _, r in items}, key=len, reverse=True)
        groups.append((names[0], personnel, names))
    for normalized, items in sorted(no_personnel.items()):
        names = sorted({str(r['employee_name']).strip() for _, r in items}, key=len, reverse=True)
        # If its full name is already represented by an identified payslip,
        # defer until there is explicit evidence tying it to the same person.
        if any(_norm(n) == normalized for _display, _pn, names_known in groups for n in names_known):
            continue
        groups.append((names[0], '', names))

    # An ambiguous shortened/longened pair without confirmed matching
    # Personalnummer MUST NOT be silently merged or made into duplicate users.
    group_names = [_norm(name) for name, _pn, _names in groups]
    safe_groups = [
        item for item in groups
        if (item[1] or not _ambiguous_name(_norm(item[0]), [
            name for name, pn, _ in groups if pn != item[1] or not pn
        ]))
        and len(_norm(item[0]).split()) >= 2
    ]
    held_groups = len(groups) - len(safe_groups)

    summary = {
        'source_files': len({title for title, _ in evidence}),
        'archive_parse_errors': errors,
        'unmatched_source_rows': len(outstanding),
        'identity_groups': len(groups),
        'profiles_eligible': len(safe_groups),
        'ambiguous_groups_held': held_groups,
        'created_inactive_profiles': 0,
        'reused_historical_profiles': 0,
        'added_payroll_rows': 0,
        'created_payroll_months': 0,
        'unresolved_rows': len(outstanding),
        'existing_payroll_untouched': True,
        'applied': apply,
    }
    if not apply:
        return summary

    with transaction.atomic():
        # Reuse a real existing worker if its Lexware Personalnummer is
        # already explicitly recorded; never create a duplicate payroll identity.
        personnel_matches = defaultdict(list)
        for candidate in WorkerProfile.objects.select_related('user').all():
            number = str(candidate.employee_number or '').strip().upper()
            if number:
                personnel_matches[number].append(candidate)
        for master in EmployeeMasterData.objects.select_related('worker').all():
            number = str((master.data or {}).get('lexware_personal_number') or '').strip().upper()
            if number and all(existing.pk != master.worker_id for existing in personnel_matches[number]):
                personnel_matches[number].append(master.worker)

        # A matching existing user account should never be silently repurposed.
        roster = list(User.objects.all().only('id', 'first_name', 'last_name'))
        worker_by_key = {}
        ambiguous_worker_keys = set()
        for name, personnel, aliases in safe_groups:
            key = _norm(name)
            existing_person = any(
                _norm(user.get_full_name()) == key
                and not WorkerProfile.objects.filter(user_id=user.id).exists()
                for user in roster
            )
            if existing_person:
                continue
            previously_known = personnel_matches.get(personnel, []) if personnel else []
            if len(previously_known) > 1:
                continue
            if len(previously_known) == 1:
                worker, created = previously_known[0], False
            else:
                worker, created = _historical_worker(name, personnel, aliases)
            summary['created_inactive_profiles' if created else 'reused_historical_profiles'] += 1
            for alias in aliases:
                alias_key = _norm(alias)
                prior = worker_by_key.get(alias_key)
                if prior is not None and prior.pk != worker.pk:
                    ambiguous_worker_keys.add(alias_key)
                elif alias_key not in ambiguous_worker_keys:
                    worker_by_key[alias_key] = worker
            if personnel:
                worker_by_key[f'PERSONNEL:{personnel}'] = worker

        rows_by_worker = defaultdict(list)
        for title, row in outstanding:
            pn = _personnel_number(row)
            worker = worker_by_key.get(f'PERSONNEL:{pn}') if pn else None
            if worker is None and _norm(row['employee_name']) not in ambiguous_worker_keys:
                worker = worker_by_key.get(_norm(row['employee_name']))
            if worker is None:
                continue
            row_period = str(row.get('period') or '') if row.get('kind') == 'payslip' else period
            if not re.fullmatch(r'20\d\d-(0[1-9]|1[0-2])', row_period):
                continue
            rows_by_worker[(worker.pk, row_period)].append((title, row))
            summary['unresolved_rows'] -= 1

        for (worker_id, row_period), rows in rows_by_worker.items():
            y, m = map(int, row_period.split('-'))
            record, created = PayrollStatement.objects.get_or_create(
                worker_id=worker_id, period=datetime(y, m, 1).date(),
                defaults={'source': 'lexware_historical_archive'},
            )
            if created:
                summary['created_payroll_months'] += 1
            saved = list(record.raw_data or [])
            keys = {entry.get('key') for entry in saved if isinstance(entry, dict)}
            incoming = []
            for title, row in rows:
                key = _row_key(title, row, row_period)
                if key in keys:
                    continue
                item = dict(row)
                item.update({'key': key, 'source_file': title,
                             'source_type': 'lexware_payslip_pdf' if row.get('kind') == 'payslip' else 'lexware_zahlungsliste_pdf'})
                incoming.append(item)
                keys.add(key)
            if not incoming:
                continue
            saved.extend(incoming)
            summary['added_payroll_rows'] += len(incoming)
            update_fields = ['raw_data', 'updated_at']
            record.raw_data = saved
            if created:
                payslips = [item for item in saved if item.get('kind') == 'payslip']
                if payslips:
                    latest = sorted(payslips, key=lambda item: bool(item.get('is_correction')))[-1]
                    if latest.get('gross_amount') not in (None, ''):
                        record.gross_amount = Decimal(str(latest['gross_amount']))
                        update_fields.append('gross_amount')
                    if latest.get('net_amount') not in (None, ''):
                        record.net_amount = Decimal(str(latest['net_amount']))
                        update_fields.append('net_amount')
                payments = [item for item in saved if item.get('kind') == 'payment' and item.get('amount') is not None]
                if payments:
                    record.transferred_amount = sum(Decimal(str(item['amount'])) for item in payments)
                    update_fields.append('transferred_amount')
            record.save(update_fields=update_fields)
        if summary['created_inactive_profiles'] or summary['added_payroll_rows']:
            AuditLog.objects.create(
                actor=None, action='payroll.historical_archive_reconciled',
                object_type='LexwareArchive', object_id=period,
                metadata={k: v for k, v in summary.items() if k not in ('applied',)},
            )
    return summary
