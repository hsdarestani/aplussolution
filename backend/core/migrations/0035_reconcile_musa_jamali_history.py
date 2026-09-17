from django.db import migrations, transaction
from django.db.models import Q


TARGET_EMPLOYEE_NUMBER = '53560424'
TARGET_EMAIL = 'mussajamali@hotmail.de'
LEGACY_EMPLOYEE_NUMBER = 'LOCAL-MUSA-JAMALI'
LEGACY_EMAIL = 'musa.jamali@pending.invalid'


def _is_musa_name(user):
    first = (getattr(user, 'first_name', '') or '').strip().casefold()
    last = (getattr(user, 'last_name', '') or '').strip().casefold()
    full = f'{first} {last}'.strip()
    return full in {'musa jamali', 'musa  jamali'} or first == 'musa jamali' or last == 'musa jamali'


def reconcile_musa_history(apps, schema_editor):
    User = apps.get_model('core', 'User')
    WorkerProfile = apps.get_model('core', 'WorkerProfile')
    TimeEntry = apps.get_model('core', 'TimeEntry')
    Shift = apps.get_model('core', 'Shift')
    ShiftSlot = apps.get_model('core', 'ShiftSlot')
    AuditLog = apps.get_model('core', 'AuditLog')

    target = WorkerProfile.objects.filter(employee_number=TARGET_EMPLOYEE_NUMBER).select_related('user').first()
    if not target:
        target_user = User.objects.filter(email__iexact=TARGET_EMAIL).first()
        target = WorkerProfile.objects.filter(user=target_user).select_related('user').first() if target_user else None
    if not target:
        return

    target_user = target.user

    # 0031 merged the known local placeholder. This follow-up also catches any
    # historical/synthetic WIW duplicate for the same person so attendance history
    # cannot remain stranded on an account Musa cannot log into.
    candidates = WorkerProfile.objects.exclude(pk=target.pk).select_related('user').filter(
        Q(employee_number=LEGACY_EMPLOYEE_NUMBER)
        | Q(user__email__iexact=LEGACY_EMAIL)
        | Q(user__email__iendswith='@sync.invalid')
        | Q(active=False)
        | Q(user__is_active=False)
    )
    sources = [worker for worker in candidates if _is_musa_name(worker.user) or worker.employee_number == LEGACY_EMPLOYEE_NUMBER or worker.user.email.lower() == LEGACY_EMAIL]

    if not sources:
        # Keep the real profile usable even when the old duplicate has already
        # been fully retired by the earlier merge migration.
        updates = []
        if not target.active:
            target.active = True
            updates.append('active')
        if updates:
            target.save(update_fields=updates + ['updated_at'])
        if not target_user.is_active:
            target_user.is_active = True
            target_user.save(update_fields=['is_active'])
        return

    moved_time_entries = 0
    moved_shifts = 0
    moved_slots = 0
    source_ids = []

    with transaction.atomic():
        for source in sources:
            source_ids.append(str(source.pk))
            source_user = source.user

            # Scheduling and time history are the two user-visible areas where the
            # duplicate account caused missing data.
            moved_shifts += Shift.objects.filter(worker=source).update(worker=target)
            moved_slots += ShiftSlot.objects.filter(worker=source).update(worker=target)
            moved_time_entries += TimeEntry.objects.filter(worker=source).update(worker=target)

            # Move the remaining worker-owned operational history as well so the
            # login account is the single source of truth going forward.
            simple_worker_links = [
                ('Availability', 'worker'),
                ('TimeOffRequest', 'worker'),
                ('Contract', 'worker'),
                ('Document', 'worker'),
                ('WorkerRating', 'worker'),
                ('TaskRun', 'assigned_worker'),
                ('StaffCallout', 'worker'),
                ('StaffCallout', 'covered_by'),
                ('TimeEntryCorrection', 'requested_by'),
                ('ShiftSwapRequest', 'requested_by'),
                ('ShiftSwapRequest', 'offered_to'),
                ('ShiftReleaseRequest', 'requested_worker'),
            ]
            for model_name, field_name in simple_worker_links:
                model = apps.get_model('core', model_name)
                model.objects.filter(**{field_name: source}).update(**{field_name: target})

            # If the login profile does not yet carry the historical WIW identity,
            # move it from the retired duplicate. This prevents a later WIW import
            # from recreating time rows under the old profile again.
            if not target.wiw_user_id and source.wiw_user_id:
                legacy_wiw_user_id = source.wiw_user_id
                source.wiw_user_id = None
                source.save(update_fields=['wiw_user_id', 'updated_at'])
                target.wiw_user_id = legacy_wiw_user_id
                if not target.wiw_payload and source.wiw_payload:
                    target.wiw_payload = source.wiw_payload
                if target.wiw_synced_at is None and source.wiw_synced_at is not None:
                    target.wiw_synced_at = source.wiw_synced_at
                target.save(update_fields=['wiw_user_id', 'wiw_payload', 'wiw_synced_at', 'updated_at'])

            if not target_user.wiw_id and source_user.wiw_id:
                legacy_user_wiw_id = source_user.wiw_id
                source_user.wiw_id = None
                source_user.save(update_fields=['wiw_id'])
                target_user.wiw_id = legacy_user_wiw_id
                if not target_user.wiw_payload and source_user.wiw_payload:
                    target_user.wiw_payload = source_user.wiw_payload
                if target_user.wiw_synced_at is None and source_user.wiw_synced_at is not None:
                    target_user.wiw_synced_at = source_user.wiw_synced_at
                target_user.save(update_fields=['wiw_id', 'wiw_payload', 'wiw_synced_at'])

            source.active = False
            source.schedule_groups = []
            source.open_shift_client_ids = []
            source.save(update_fields=['active', 'schedule_groups', 'open_shift_client_ids', 'updated_at'])
            if source_user.is_active:
                source_user.is_active = False
                source_user.save(update_fields=['is_active'])

        target.active = True
        target.save(update_fields=['active', 'updated_at'])
        if not target_user.is_active:
            target_user.is_active = True
            target_user.save(update_fields=['is_active'])

        AuditLog.objects.create(
            action='reconcile_duplicate_worker_history',
            object_type='WorkerProfile',
            object_id=str(target.pk),
            metadata={
                'employee_number': TARGET_EMPLOYEE_NUMBER,
                'email': TARGET_EMAIL,
                'source_worker_ids': source_ids,
                'moved_time_entries': moved_time_entries,
                'moved_shifts': moved_shifts,
                'moved_shift_slots': moved_slots,
                'reason': 'Move all remaining Musa Jamali history from retired duplicate profiles to the login account.',
            },
        )


def noop_reverse(apps, schema_editor):
    # Re-splitting merged attendance history would be ambiguous.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0034_enable_admin_open_shift_push'),
    ]

    operations = [
        migrations.RunPython(reconcile_musa_history, noop_reverse),
    ]
