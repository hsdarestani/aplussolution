"""Apply a verified Personalfragebogen payload to exactly one existing worker.

Executed through SSH into the existing production Django backend.
The payload itself is stored only in an Actions secret, never in Git.
"""
from django.db import transaction
from core.models import EmployeeMasterData, WorkerProfile
from core.wiw_sync import calculate_completeness


def apply_existing_personalfragebogen(payload, dry_run=False):
    if not isinstance(payload, dict):
        raise ValueError('INVALID_PAYLOAD')
    target = payload.get('target')
    profile = payload.get('profile') or {}
    incoming = payload.get('master_data')
    if not isinstance(target, dict) or not isinstance(profile, dict) or not isinstance(incoming, dict):
        raise ValueError('INVALID_PAYLOAD_STRUCTURE')
    if not incoming:
        raise ValueError('EMPTY_MASTER_DATA')

    email = str(target.get('email') or '').strip().casefold()
    first = str(target.get('first_name') or '').strip()
    last = str(target.get('last_name') or '').strip()
    if not (email and first and last and '@' in email):
        raise ValueError('INVALID_TARGET')

    allowed = {
        'street', 'postal_code', 'city', 'full_address', 'birth_date',
        'nationality', 'birth_name', 'birth_place', 'birth_country',
        'social_insurance_number', 'health_insurance_name',
        'tax_identification_number', 'tax_class', 'child_allowance',
        'tax_allowance', 'religion', 'spouse_religion', 'iban',
        'bank_account_holder', 'bank_name', 'salutation',
        'insurance_type', 'has_children', 'children_under_25',
        'other_employments', 'signature_place_and_date_as_written',
    }
    unexpected = sorted(set(incoming) - allowed)
    if unexpected:
        raise ValueError('UNSUPPORTED_MASTER_FIELDS: ' + ','.join(unexpected))
    if set(profile) - {'phone'}:
        raise ValueError('UNSUPPORTED_PROFILE_FIELDS')
    if any(v is None or v == '' for v in incoming.values()):
        raise ValueError('EMPTY_FIELD_NOT_ALLOWED')
    if not isinstance(incoming.get('other_employments', []), list):
        raise ValueError('INVALID_OTHER_EMPLOYMENTS')

    with transaction.atomic():
        matches = list(WorkerProfile.objects.select_for_update().select_related('user').filter(
            user__email__iexact=email,
            user__first_name__iexact=first,
            user__last_name__iexact=last,
        )[:2])
        if len(matches) != 1:
            raise ValueError('EXACT_EXISTING_EMPLOYEE_NOT_FOUND_OR_AMBIGUOUS')
        worker = matches[0]
        if worker.user.role != 'worker':
            raise ValueError('TARGET_IS_NOT_A_WORKER')

        current = EmployeeMasterData.objects.filter(worker=worker).first()
        old = dict(current.data or {}) if current else {}
        changes = {key: value for key, value in incoming.items() if old.get(key) != value}
        new_phone = str(profile.get('phone') or '').strip()
        phone_change = bool(new_phone and worker.user.phone != new_phone)

        if dry_run:
            print('DRY_RUN_OK existing_worker=1 master_fields_to_update=%d phone_to_update=%d' % (
                len(changes), int(phone_change)))
            return

        if phone_change:
            worker.user.phone = new_phone
            worker.user.save(update_fields=['phone'])
        master = current if current is not None else EmployeeMasterData(worker=worker)
        data = dict(old)
        data.update(incoming)
        source_map = dict(master.source_map or {})
        for field in incoming:
            source_map[field] = 'personalfragebogen_admin_manual_2026_11'
        completeness, missing = calculate_completeness(data)
        master.data = data
        master.source_map = source_map
        master.completeness = completeness
        master.missing_fields = missing
        if changes:
            master.verified_at = None
            master.verified_by = None
        master.save()

        master.refresh_from_db()
        worker.user.refresh_from_db()
        if any(master.data.get(key) != value for key, value in incoming.items()):
            raise RuntimeError('POST_SAVE_VERIFICATION_FAILED')
        if new_phone and worker.user.phone != new_phone:
            raise RuntimeError('PHONE_POST_SAVE_VERIFICATION_FAILED')
        print('APPLY_OK existing_worker=1 master_fields_updated=%d phone_updated=%d completeness=%d' % (
            len(changes), int(phone_change), master.completeness))


apply_existing_personalfragebogen(payload, dry_run=dry_run)
