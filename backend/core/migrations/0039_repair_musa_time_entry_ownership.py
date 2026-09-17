from django.db import migrations, transaction


TARGET_EMPLOYEE_NUMBER = '53560424'
TARGET_EMAIL = 'mussajamali@hotmail.de'


def _payload_user_id(payload):
    if not isinstance(payload, dict):
        return ''
    value = payload.get('user_id') or payload.get('user')
    if isinstance(value, dict):
        value = value.get('id') or value.get('user_id')
    return str(value or '').strip()


def repair_musa_time_entry_ownership(apps, schema_editor):
    """Undo any cross-worker ownership caused by the old 0037 shift heuristic.

    The previous migration briefly treated membership in the same Shift/ShiftSlot
    as worker identity evidence. That is unsafe for multi-person shifts. Production
    may already have executed that version, so this migration repairs only rows for
    which the original worker can be proven from an immutable native audit actor or
    from the WIW user id embedded in the imported TimeEntry payload.

    Ambiguous rows are deliberately left untouched and reported in AuditLog. We do
    not infer ownership from the shift relationship again.
    """
    User = apps.get_model('core', 'User')
    WorkerProfile = apps.get_model('core', 'WorkerProfile')
    TimeEntry = apps.get_model('core', 'TimeEntry')
    ShiftSlot = apps.get_model('core', 'ShiftSlot')
    AuditLog = apps.get_model('core', 'AuditLog')

    target = WorkerProfile.objects.filter(employee_number=TARGET_EMPLOYEE_NUMBER).select_related('user').first()
    if not target:
        target_user = User.objects.filter(email__iexact=TARGET_EMAIL).first()
        target = WorkerProfile.objects.filter(user=target_user).select_related('user').first() if target_user else None
    if not target:
        print('Musa ownership repair skipped: canonical profile not found.')
        return

    workers = list(WorkerProfile.objects.select_related('user').all())
    worker_by_user = {worker.user_id: worker.pk for worker in workers}
    wiw_owners = {}
    for worker in workers:
        values = {
            str(getattr(worker, 'wiw_user_id', '') or '').strip(),
            str(getattr(worker.user, 'wiw_id', '') or '').strip(),
        }
        for value in values:
            if value:
                wiw_owners.setdefault(value, set()).add(worker.pk)

    repaired = []
    ambiguous = []
    unresolved_shared_shift = []
    checked = 0

    # 0037 could only have contaminated rows by moving them *to* Musa. Restrict
    # the repair to Musa-owned TimeEntries so nobody else's current ownership can
    # be changed by this corrective migration.
    rows = TimeEntry.objects.filter(worker=target).order_by('created_at', 'pk')

    with transaction.atomic():
        for entry in rows.iterator(chunk_size=250):
            checked += 1
            evidence_sets = []
            evidence_labels = []

            wiw_user_id = _payload_user_id(getattr(entry, 'wiw_payload', None))
            if wiw_user_id and wiw_user_id in wiw_owners:
                evidence_sets.append(set(wiw_owners[wiw_user_id]))
                evidence_labels.append('wiw_payload_user_id')

            actor_ids = AuditLog.objects.filter(
                object_type='TimeEntry',
                object_id=str(entry.pk),
                action__in=['time.clock_in', 'time.clock_out'],
                actor_id__isnull=False,
            ).values_list('actor_id', flat=True)
            audit_workers = {
                worker_by_user[actor_id]
                for actor_id in actor_ids
                if actor_id in worker_by_user
            }
            if audit_workers:
                evidence_sets.append(audit_workers)
                evidence_labels.append('native_time_audit_actor')

            candidates = set().union(*evidence_sets) if evidence_sets else set()
            if len(candidates) == 1:
                original_worker_id = next(iter(candidates))
                if original_worker_id != target.pk:
                    TimeEntry.objects.filter(pk=entry.pk, worker=target).update(worker_id=original_worker_id)
                    repaired.append({
                        'time_entry_id': str(entry.pk),
                        'worker_id': str(original_worker_id),
                        'evidence': evidence_labels,
                    })
                continue

            if len(candidates) > 1:
                ambiguous.append({
                    'time_entry_id': str(entry.pk),
                    'worker_ids': sorted(str(item) for item in candidates),
                    'evidence': evidence_labels,
                })
                continue

            if entry.shift_id:
                other_claimed = list(
                    ShiftSlot.objects.filter(
                        shift_id=entry.shift_id,
                        status='claimed',
                        worker__isnull=False,
                    ).exclude(worker=target).values_list('worker_id', flat=True).distinct()[:10]
                )
                if other_claimed:
                    unresolved_shared_shift.append({
                        'time_entry_id': str(entry.pk),
                        'shift_id': str(entry.shift_id),
                        'other_claimed_worker_ids': [str(item) for item in other_claimed],
                    })

        AuditLog.objects.create(
            action='repair_musa_time_entry_ownership',
            object_type='WorkerProfile',
            object_id=str(target.pk),
            metadata={
                'checked_musa_time_entries': checked,
                'repaired_count': len(repaired),
                'repaired': repaired[:250],
                'ambiguous_count': len(ambiguous),
                'ambiguous': ambiguous[:250],
                'unresolved_shared_shift_count': len(unresolved_shared_shift),
                'unresolved_shared_shift': unresolved_shared_shift[:250],
                'policy': 'positive_identity_evidence_only',
            },
        )

    print(
        'Musa ownership repair complete: '
        f'checked={checked}, repaired={len(repaired)}, ambiguous={len(ambiguous)}, '
        f'unresolved_shared_shift={len(unresolved_shared_shift)}'
    )


def noop_reverse(apps, schema_editor):
    # Reassigning repaired attendance rows back to Musa would recreate the bug.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0038_client_portal_v4'),
    ]

    operations = [
        migrations.RunPython(repair_musa_time_entry_ownership, noop_reverse),
    ]
