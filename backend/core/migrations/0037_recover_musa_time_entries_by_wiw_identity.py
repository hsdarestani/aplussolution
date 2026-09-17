from django.db import migrations, transaction


TARGET_EMPLOYEE_NUMBER = '53560424'
TARGET_EMAIL = 'mussajamali@hotmail.de'
LEGACY_EMAIL = 'musa.jamali@pending.invalid'


def _text(value):
    try:
        return str(value or '').casefold()
    except Exception:
        return ''


def _user_id_from_payload(payload):
    if not isinstance(payload, dict):
        return ''
    value = payload.get('user_id') or payload.get('user')
    if isinstance(value, dict):
        value = value.get('id') or value.get('user_id')
    return str(value or '').strip()


def _looks_like_musa(worker):
    user = worker.user
    email = _text(getattr(user, 'email', ''))
    first = _text(getattr(user, 'first_name', '')).strip()
    last = _text(getattr(user, 'last_name', '')).strip()
    employee_number = _text(getattr(worker, 'employee_number', '')).strip()
    payload = f"{_text(getattr(worker, 'wiw_payload', {}))} {_text(getattr(user, 'wiw_payload', {}))}"

    if employee_number == 'local-musa-jamali' or email == LEGACY_EMAIL:
        return True
    if first in {'musa', 'mussa'} and last.startswith('jamal'):
        return True
    if 'musa' in email and 'jamal' in email:
        return True
    if 'mussa' in email and 'jamal' in email:
        return True
    return ('musa' in payload or 'mussa' in payload) and 'jamal' in payload


def recover_musa_time_entries(apps, schema_editor):
    User = apps.get_model('core', 'User')
    WorkerProfile = apps.get_model('core', 'WorkerProfile')
    TimeEntry = apps.get_model('core', 'TimeEntry')
    TimeEntryCorrection = apps.get_model('core', 'TimeEntryCorrection')
    WorkingTimeAccountRecord = apps.get_model('core', 'WorkingTimeAccountRecord')
    PayrollStatement = apps.get_model('core', 'PayrollStatement')
    AuditLog = apps.get_model('core', 'AuditLog')

    target = WorkerProfile.objects.filter(employee_number=TARGET_EMPLOYEE_NUMBER).select_related('user').first()
    if not target:
        target_user = User.objects.filter(email__iexact=TARGET_EMAIL).first()
        target = WorkerProfile.objects.filter(user=target_user).select_related('user').first() if target_user else None
    if not target:
        print('Musa time recovery skipped: canonical login profile not found.')
        return

    target_user = target.user
    target_wiw_ids = {
        str(value).strip()
        for value in (getattr(target, 'wiw_user_id', None), getattr(target_user, 'wiw_id', None))
        if value not in (None, '')
    }

    candidate_workers = []
    for worker in WorkerProfile.objects.exclude(pk=target.pk).select_related('user').order_by('created_at'):
        if _looks_like_musa(worker):
            candidate_workers.append(worker)
    candidate_ids = [worker.pk for worker in candidate_workers]

    entry_ids = set()
    identity_entry_ids = set()
    shift_entry_ids = set()

    # Recover rows from any remaining duplicate worker that still carries Musa's
    # name/email/WIW payload, even when the duplicate was active or had a normal
    # email address and therefore escaped the earlier narrow migrations.
    if candidate_ids:
        identity_entry_ids.update(
            TimeEntry.objects.filter(worker_id__in=candidate_ids).values_list('pk', flat=True)
        )

    # Imported WIW time rows preserve the original WIW user id in wiw_payload.
    # That is stronger evidence than a local display name, and lets us recover a
    # row even if its historical WorkerProfile was created with a wrong/blank name.
    if target_wiw_ids:
        for entry in TimeEntry.objects.exclude(worker=target).only('pk', 'wiw_payload'):
            if _user_id_from_payload(entry.wiw_payload) in target_wiw_ids:
                identity_entry_ids.add(entry.pk)

    # A time row attached to a shift that now belongs to Musa also belongs to his
    # attendance history. This covers records whose old WorkerProfile identity was
    # too damaged to recognize from names or WIW metadata.
    shift_entry_ids.update(
        TimeEntry.objects.exclude(worker=target).filter(shift__worker=target).values_list('pk', flat=True)
    )
    shift_entry_ids.update(
        TimeEntry.objects.exclude(worker=target).filter(
            shift__slots__worker=target,
            shift__slots__status='claimed',
        ).values_list('pk', flat=True).distinct()
    )

    entry_ids.update(identity_entry_ids)
    entry_ids.update(shift_entry_ids)

    moved_entries = 0
    with transaction.atomic():
        if entry_ids:
            moved_entries = TimeEntry.objects.filter(pk__in=entry_ids).exclude(worker=target).update(worker=target)

        # Corrections and monthly working-time/payroll records on positively
        # identified duplicate profiles should follow the same canonical account.
        if candidate_ids:
            TimeEntryCorrection.objects.filter(requested_by_id__in=candidate_ids).update(requested_by=target)

            for model, period_field in (
                (WorkingTimeAccountRecord, 'year_month'),
                (PayrollStatement, 'period'),
            ):
                for row in model.objects.filter(worker_id__in=candidate_ids).order_by(period_field, 'created_at'):
                    existing = model.objects.filter(
                        worker=target,
                        **{period_field: getattr(row, period_field)},
                    ).exclude(pk=row.pk).first()
                    if existing:
                        # Prefer the non-empty historical record when the target
                        # placeholder row contains only zeros/empty values.
                        if model is WorkingTimeAccountRecord:
                            changed = []
                            for field in ('ist_hours', 'soll_hours', 'difference_hours'):
                                if not getattr(existing, field) and getattr(row, field):
                                    setattr(existing, field, getattr(row, field))
                                    changed.append(field)
                            if changed:
                                existing.save(update_fields=changed + ['updated_at'])
                        row.delete()
                    else:
                        row.worker = target
                        row.save(update_fields=['worker', 'updated_at'])

        target.active = True
        target.save(update_fields=['active', 'updated_at'])
        if not target_user.is_active:
            target_user.is_active = True
            target_user.save(update_fields=['is_active'])

        closed_after = TimeEntry.objects.filter(worker=target, clock_out__isnull=False).count()
        total_after = TimeEntry.objects.filter(worker=target).count()
        AuditLog.objects.create(
            action='recover_musa_time_entries_by_identity',
            object_type='WorkerProfile',
            object_id=str(target.pk),
            metadata={
                'candidate_workers': len(candidate_ids),
                'identity_entry_matches': len(identity_entry_ids),
                'shift_entry_matches': len(shift_entry_ids),
                'moved_time_entries': moved_entries,
                'target_time_entries_after': total_after,
                'target_closed_time_entries_after': closed_after,
            },
        )

    print(
        'Musa time recovery complete: '
        f'candidate_workers={len(candidate_ids)}, identity_matches={len(identity_entry_ids)}, '
        f'shift_matches={len(shift_entry_ids)}, moved={moved_entries}, '
        f'closed_after={closed_after}, total_after={total_after}'
    )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0036_merge_all_musa_jamali_profiles'),
    ]

    operations = [
        migrations.RunPython(recover_musa_time_entries, noop_reverse),
    ]
