from django.db import migrations, transaction


TARGET_EMPLOYEE_NUMBER = '53560424'
TARGET_EMAIL = 'mussajamali@hotmail.de'


def _normalized_name(user):
    first = (getattr(user, 'first_name', '') or '').strip().casefold()
    last = (getattr(user, 'last_name', '') or '').strip().casefold()
    return ' '.join(part for part in (first, last) if part)


def _is_musa_jamali(user):
    name = _normalized_name(user)
    return name == 'musa jamali' or (
        (getattr(user, 'first_name', '') or '').strip().casefold() == 'musa'
        and (getattr(user, 'last_name', '') or '').strip().casefold().startswith('jamali')
    )


def _merge_list_values(*values):
    merged = []
    seen = set()
    for value in values:
        if not isinstance(value, list):
            continue
        for item in value:
            marker = repr(item)
            if marker in seen:
                continue
            seen.add(marker)
            merged.append(item)
    return merged


def _move_pending_unique_requests(model, source, target, *, worker_field='worker'):
    for row in model.objects.filter(**{worker_field: source}).order_by('created_at'):
        if getattr(row, 'status', None) == 'pending':
            conflict = model.objects.filter(
                shift_id=row.shift_id,
                status='pending',
                **{worker_field: target},
            ).exclude(pk=row.pk).exists()
            if conflict:
                row.delete()
                continue
        setattr(row, worker_field, target)
        row.save(update_fields=[worker_field, 'updated_at'])


def merge_all_musa_profiles(apps, schema_editor):
    User = apps.get_model('core', 'User')
    WorkerProfile = apps.get_model('core', 'WorkerProfile')

    target = WorkerProfile.objects.filter(employee_number=TARGET_EMPLOYEE_NUMBER).select_related('user').first()
    if not target:
        target_user = User.objects.filter(email__iexact=TARGET_EMAIL).first()
        target = WorkerProfile.objects.filter(user=target_user).select_related('user').first() if target_user else None
    if not target:
        print('Musa reconciliation skipped: target login profile not found.')
        return

    target_user = target.user
    sources = [
        worker
        for worker in WorkerProfile.objects.exclude(pk=target.pk).select_related('user').order_by('created_at')
        if _is_musa_jamali(worker.user)
    ]

    if not sources:
        print('Musa reconciliation: no additional same-name profiles found.')
        return

    Shift = apps.get_model('core', 'Shift')
    ShiftSlot = apps.get_model('core', 'ShiftSlot')
    TimeEntry = apps.get_model('core', 'TimeEntry')
    Notification = apps.get_model('core', 'Notification')
    PushDevice = apps.get_model('core', 'PushDevice')
    AuditLog = apps.get_model('core', 'AuditLog')

    moved = {
        'sources': len(sources),
        'time_entries': 0,
        'shifts': 0,
        'shift_slots': 0,
        'notifications': 0,
        'push_devices': 0,
    }

    with transaction.atomic():
        for source in sources:
            source_user = source.user

            target.skills = _merge_list_values(target.skills, source.skills)
            target.open_shift_client_ids = _merge_list_values(target.open_shift_client_ids, source.open_shift_client_ids)
            target.schedule_groups = _merge_list_values(target.schedule_groups, source.schedule_groups)
            target.ranking_points = max(target.ranking_points or 0, source.ranking_points or 0)
            if target.monthly_hours is None and source.monthly_hours is not None:
                target.monthly_hours = source.monthly_hours
            if target.tariff_hourly_rate is None and source.tariff_hourly_rate is not None:
                target.tariff_hourly_rate = source.tariff_hourly_rate
            if not target.extra_allowance and source.extra_allowance:
                target.extra_allowance = source.extra_allowance

            moved['shifts'] += Shift.objects.filter(worker=source).update(worker=target)
            moved['shift_slots'] += ShiftSlot.objects.filter(worker=source).update(worker=target)
            moved['time_entries'] += TimeEntry.objects.filter(worker=source).update(worker=target)

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
            ]
            for model_name, field_name in simple_worker_links:
                model = apps.get_model('core', model_name)
                model.objects.filter(**{field_name: source}).update(**{field_name: target})

            ShiftPickupRequest = apps.get_model('core', 'ShiftPickupRequest')
            ShiftReleaseRequest = apps.get_model('core', 'ShiftReleaseRequest')
            _move_pending_unique_requests(ShiftPickupRequest, source, target)
            _move_pending_unique_requests(ShiftReleaseRequest, source, target)
            ShiftReleaseRequest.objects.filter(requested_worker=source).update(requested_worker=target)

            WorkerLocationMembership = apps.get_model('core', 'WorkerLocationMembership')
            for membership in WorkerLocationMembership.objects.filter(worker=source).order_by('created_at'):
                existing = WorkerLocationMembership.objects.filter(
                    worker=target,
                    location_id=membership.location_id,
                ).exclude(pk=membership.pk).first()
                if existing:
                    changed = []
                    if membership.home and not existing.home:
                        existing.home = True
                        changed.append('home')
                    if membership.active and not existing.active:
                        existing.active = True
                        changed.append('active')
                    if changed:
                        existing.save(update_fields=changed + ['updated_at'])
                    membership.delete()
                else:
                    membership.worker = target
                    membership.save(update_fields=['worker', 'updated_at'])

            for model_name, period_field in [
                ('PayrollStatement', 'period'),
                ('WorkingTimeAccountRecord', 'year_month'),
            ]:
                model = apps.get_model('core', model_name)
                for row in model.objects.filter(worker=source).order_by(period_field, 'created_at'):
                    conflict = model.objects.filter(
                        worker=target,
                        **{period_field: getattr(row, period_field)},
                    ).exclude(pk=row.pk).first()
                    if conflict:
                        row.delete()
                    else:
                        row.worker = target
                        row.save(update_fields=['worker', 'updated_at'])

            EmployeeMasterData = apps.get_model('core', 'EmployeeMasterData')
            source_master = EmployeeMasterData.objects.filter(worker=source).first()
            target_master = EmployeeMasterData.objects.filter(worker=target).first()
            if source_master:
                if target_master:
                    target_data = dict(target_master.data or {})
                    for key, value in dict(source_master.data or {}).items():
                        if target_data.get(key) in (None, '', [], {}):
                            target_data[key] = value
                    target_master.data = target_data
                    target_master.completeness = max(target_master.completeness or 0, source_master.completeness or 0)
                    target_master.save(update_fields=['data', 'completeness', 'updated_at'])
                    source_master.delete()
                else:
                    source_master.worker = target
                    source_master.save(update_fields=['worker', 'updated_at'])

            WorkingTimeSetting = apps.get_model('core', 'WorkingTimeSetting')
            source_setting = WorkingTimeSetting.objects.filter(worker=source).first()
            target_setting = WorkingTimeSetting.objects.filter(worker=target).first()
            if source_setting:
                if target_setting:
                    source_setting.delete()
                else:
                    source_setting.worker = target
                    source_setting.save(update_fields=['worker', 'updated_at'])

            moved['notifications'] += Notification.objects.filter(user=source_user).update(user=target_user)
            moved['push_devices'] += PushDevice.objects.filter(user=source_user).update(user=target_user)

            if not target.wiw_user_id and source.wiw_user_id:
                old_wiw_user_id = source.wiw_user_id
                source.wiw_user_id = None
                source.save(update_fields=['wiw_user_id', 'updated_at'])
                target.wiw_user_id = old_wiw_user_id
                if not target.wiw_payload and source.wiw_payload:
                    target.wiw_payload = source.wiw_payload
                if target.wiw_synced_at is None and source.wiw_synced_at is not None:
                    target.wiw_synced_at = source.wiw_synced_at

            if not target_user.wiw_id and source_user.wiw_id:
                old_user_wiw_id = source_user.wiw_id
                source_user.wiw_id = None
                source_user.save(update_fields=['wiw_id'])
                target_user.wiw_id = old_user_wiw_id
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
        target.save(update_fields=[
            'skills', 'open_shift_client_ids', 'schedule_groups', 'ranking_points',
            'monthly_hours', 'tariff_hourly_rate', 'extra_allowance', 'active',
            'wiw_user_id', 'wiw_payload', 'wiw_synced_at', 'updated_at',
        ])
        if not target_user.is_active:
            target_user.is_active = True
            target_user.save(update_fields=['is_active'])

        AuditLog.objects.create(
            action='merge_all_duplicate_musa_jamali_profiles',
            object_type='WorkerProfile',
            object_id=str(target.pk),
            metadata={**moved, 'employee_number': TARGET_EMPLOYEE_NUMBER},
        )

    print(
        'Musa reconciliation complete: '
        f"sources={moved['sources']}, time_entries={moved['time_entries']}, "
        f"shifts={moved['shifts']}, shift_slots={moved['shift_slots']}"
    )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0035_reconcile_musa_jamali_history'),
    ]

    operations = [
        migrations.RunPython(merge_all_musa_profiles, noop_reverse),
    ]
