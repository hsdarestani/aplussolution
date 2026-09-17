from django.db import migrations, transaction


SOURCE_EMPLOYEE_NUMBER = 'LOCAL-MUSA-JAMALI'
SOURCE_EMAIL = 'musa.jamali@pending.invalid'
TARGET_EMPLOYEE_NUMBER = '53560424'
TARGET_EMAIL = 'mussajamali@hotmail.de'


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
    """Move request rows while avoiding duplicate pending constraints."""
    source_rows = model.objects.filter(**{worker_field: source}).order_by('created_at')
    for row in source_rows:
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


def merge_musa_jamali(apps, schema_editor):
    User = apps.get_model('core', 'User')
    WorkerProfile = apps.get_model('core', 'WorkerProfile')

    source = WorkerProfile.objects.filter(employee_number=SOURCE_EMPLOYEE_NUMBER).select_related('user').first()
    if not source:
        source_user = User.objects.filter(email__iexact=SOURCE_EMAIL).first()
        source = WorkerProfile.objects.filter(user=source_user).first() if source_user else None

    target = WorkerProfile.objects.filter(employee_number=TARGET_EMPLOYEE_NUMBER).select_related('user').first()
    if not target:
        target_user = User.objects.filter(email__iexact=TARGET_EMAIL).first()
        target = WorkerProfile.objects.filter(user=target_user).first() if target_user else None

    if not source or not target or source.pk == target.pk:
        return

    source_user = source.user
    target_user = target.user

    with transaction.atomic():
        # Keep the real/login profile authoritative, but preserve any scheduling
        # metadata that had accidentally accumulated on the local placeholder.
        target.skills = _merge_list_values(target.skills, source.skills)
        target.open_shift_client_ids = _merge_list_values(
            target.open_shift_client_ids,
            source.open_shift_client_ids,
        )
        target.schedule_groups = _merge_list_values(target.schedule_groups, source.schedule_groups)
        target.ranking_points = max(target.ranking_points or 0, source.ranking_points or 0)
        if target.monthly_hours is None and source.monthly_hours is not None:
            target.monthly_hours = source.monthly_hours
        if target.tariff_hourly_rate is None and source.tariff_hourly_rate is not None:
            target.tariff_hourly_rate = source.tariff_hourly_rate
        if not target.extra_allowance and source.extra_allowance:
            target.extra_allowance = source.extra_allowance
        target.active = True
        target.save(update_fields=[
            'skills',
            'open_shift_client_ids',
            'schedule_groups',
            'ranking_points',
            'monthly_hours',
            'tariff_hourly_rate',
            'extra_allowance',
            'active',
            'updated_at',
        ])

        # Shift visibility in the employee app is driven primarily by ShiftSlot,
        # while some legacy/admin code still reads Shift.worker. Move both so Musa
        # immediately sees every assignment under the account he can actually use.
        Shift = apps.get_model('core', 'Shift')
        ShiftSlot = apps.get_model('core', 'ShiftSlot')
        Shift.objects.filter(worker=source).update(worker=target)
        ShiftSlot.objects.filter(worker=source).update(worker=target)

        # Move normal worker-owned history and operational data.
        simple_worker_links = [
            ('Availability', 'worker'),
            ('TimeEntry', 'worker'),
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

        # Pending pickup/release rows have conditional unique constraints on
        # (shift, worker), so resolve a duplicate before changing the worker id.
        ShiftPickupRequest = apps.get_model('core', 'ShiftPickupRequest')
        ShiftReleaseRequest = apps.get_model('core', 'ShiftReleaseRequest')
        _move_pending_unique_requests(ShiftPickupRequest, source, target)
        _move_pending_unique_requests(ShiftReleaseRequest, source, target)
        ShiftReleaseRequest.objects.filter(requested_worker=source).update(requested_worker=target)

        # One row per worker/location. Merge flags when both accounts already have
        # a row for the same location instead of violating the unique constraint.
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

        # Period keyed records can also collide. Keep the real account's row when
        # present; otherwise move the placeholder row intact.
        for model_name, period_field in [
            ('PayrollStatement', 'period'),
            ('WorkingTimeAccountRecord', 'year_month'),
        ]:
            model = apps.get_model('core', model_name)
            for row in model.objects.filter(worker=source).order_by(period_field, 'created_at'):
                conflict = model.objects.filter(
                    worker=target,
                    **{period_field: getattr(row, period_field)},
                ).exclude(pk=row.pk).exists()
                if conflict:
                    row.delete()
                else:
                    row.worker = target
                    row.save(update_fields=['worker', 'updated_at'])

        # Merge one-to-one employee master data, preferring populated values on the
        # login account and filling only missing fields from the placeholder.
        EmployeeMasterData = apps.get_model('core', 'EmployeeMasterData')
        source_master = EmployeeMasterData.objects.filter(worker=source).first()
        target_master = EmployeeMasterData.objects.filter(worker=target).first()
        if source_master:
            if target_master:
                target_data = dict(target_master.data or {})
                for key, value in dict(source_master.data or {}).items():
                    if target_data.get(key) in (None, '', [], {}):
                        target_data[key] = value
                target_source_map = dict(source_master.source_map or {})
                target_source_map.update(dict(target_master.source_map or {}))
                target_master.data = target_data
                target_master.source_map = target_source_map
                target_master.completeness = max(
                    target_master.completeness or 0,
                    source_master.completeness or 0,
                )
                target_master.missing_fields = [
                    item for item in (target_master.missing_fields or [])
                    if target_data.get(item) in (None, '', [], {})
                ]
                target_master.save(update_fields=[
                    'data', 'source_map', 'completeness', 'missing_fields', 'updated_at'
                ])
                source_master.delete()
            else:
                source_master.worker = target
                source_master.save(update_fields=['worker', 'updated_at'])

        # Working-time settings are one-to-one. Preserve explicit settings already
        # present on the real account; otherwise move the placeholder settings.
        WorkingTimeSetting = apps.get_model('core', 'WorkingTimeSetting')
        source_setting = WorkingTimeSetting.objects.filter(worker=source).first()
        target_setting = WorkingTimeSetting.objects.filter(worker=target).first()
        if source_setting:
            if target_setting:
                source_setting.delete()
            else:
                source_setting.worker = target
                source_setting.save(update_fields=['worker', 'updated_at'])

        # Notifications that were created for the placeholder now become visible
        # to Musa's real/login account. Push devices are also safe to rebind because
        # their token, not the user FK, is unique.
        Notification = apps.get_model('core', 'Notification')
        PushDevice = apps.get_model('core', 'PushDevice')
        Notification.objects.filter(user=source_user).update(user=target_user)
        PushDevice.objects.filter(user=source_user).update(user=target_user)

        # Retire the duplicate without deleting it. Keeping the row makes this
        # migration reversible operationally from a database backup and prevents
        # accidental cascades on any obscure historic relation not used by shifts.
        source.active = False
        source.schedule_groups = []
        source.open_shift_client_ids = []
        source.save(update_fields=['active', 'schedule_groups', 'open_shift_client_ids', 'updated_at'])

        source_user.is_active = False
        source_user.save(update_fields=['is_active'])

        AuditLog = apps.get_model('core', 'AuditLog')
        AuditLog.objects.create(
            action='merge_duplicate_worker',
            object_type='WorkerProfile',
            object_id=str(target.pk),
            metadata={
                'source_employee_number': SOURCE_EMPLOYEE_NUMBER,
                'source_email': SOURCE_EMAIL,
                'target_employee_number': TARGET_EMPLOYEE_NUMBER,
                'target_email': TARGET_EMAIL,
                'reason': 'Duplicate Musa Jamali profile prevented assigned shifts from appearing on the login account.',
            },
        )


def noop_reverse(apps, schema_editor):
    # Re-splitting worker history after it has been merged would be ambiguous.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0030_pushdelivery'),
    ]

    operations = [
        migrations.RunPython(merge_musa_jamali, noop_reverse),
    ]
