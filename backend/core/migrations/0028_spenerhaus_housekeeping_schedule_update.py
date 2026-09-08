from datetime import datetime
from zoneinfo import ZoneInfo

from django.db import migrations
from django.db.models import Q
from django.utils import timezone


BERLIN = ZoneInfo('Europe/Berlin')
IZABELLA_EMAIL = 'izabellasomodi21@yahoo.com'

# Ashkan schedule received 08.09.2026. Missing names are intentional OpenShifts.
SCHEDULE = {
    9: 'izabella',
    10: 'musa',
    11: 'musa',
    12: None,
    14: None,
    18: None,
    19: None,
    21: None,
    22: None,
    23: None,
    24: None,
    26: None,
    27: None,
}


def _find_worker(WorkerProfile, User, first_name, email=None):
    user = None
    if email:
        user = User.objects.filter(email__iexact=email).first()

    if user:
        worker = WorkerProfile.objects.filter(user=user, active=True).first()
        if worker:
            return worker

    candidates = list(
        WorkerProfile.objects.filter(
            active=True,
            user__is_active=True,
            user__first_name__iexact=first_name,
        ).order_by('created_at')
    )
    if len(candidates) == 1:
        return candidates[0]

    housekeeping = [
        worker for worker in candidates
        if 'housekeeping' in [str(item).lower() for item in (worker.schedule_groups or [])]
    ]
    if len(housekeeping) == 1:
        return housekeeping[0]

    if not candidates:
        raise RuntimeError(f'Spenerhaus schedule update: active worker {first_name!r} was not found.')
    raise RuntimeError(
        f'Spenerhaus schedule update: {first_name!r} is ambiguous ({len(candidates)} active workers).'
    )


def _active_slots(ShiftSlot, shift):
    return ShiftSlot.objects.filter(shift=shift).exclude(status='cancelled').order_by('created_at')


def _normalize_claimed_slot(ShiftSlot, shift, worker, now):
    active_slots = _active_slots(ShiftSlot, shift)
    slot = active_slots.filter(worker=worker).first()
    if not slot:
        slot = active_slots.filter(worker__isnull=True).first()
    if not slot:
        slot = active_slots.first()

    if slot:
        slot.worker = worker
        slot.status = 'claimed'
        slot.source = 'manual_schedule_import'
        slot.claimed_at = slot.claimed_at or now
        slot.released_at = None
        slot.confirmation_status = 'confirmed'
        slot.confirmation_requested_at = None
        slot.confirmation_decided_at = now
        slot.save(update_fields=[
            'worker', 'status', 'source', 'claimed_at', 'released_at',
            'confirmation_status', 'confirmation_requested_at',
            'confirmation_decided_at', 'updated_at',
        ])
    else:
        slot = ShiftSlot.objects.create(
            shift=shift,
            worker=worker,
            status='claimed',
            source='manual_schedule_import',
            claimed_at=now,
            confirmation_status='confirmed',
            confirmation_decided_at=now,
        )

    _active_slots(ShiftSlot, shift).exclude(pk=slot.pk).update(
        status='cancelled',
        worker=None,
        released_at=now,
    )


def _normalize_open_slot(ShiftSlot, shift, now):
    active_slots = _active_slots(ShiftSlot, shift)
    slot = active_slots.filter(worker__isnull=True, status='open').first() or active_slots.first()

    if slot:
        slot.worker = None
        slot.status = 'open'
        slot.source = 'manual_schedule_import'
        slot.released_at = now
        slot.confirmation_status = 'confirmed'
        slot.confirmation_requested_at = None
        slot.confirmation_decided_at = None
        slot.save(update_fields=[
            'worker', 'status', 'source', 'released_at',
            'confirmation_status', 'confirmation_requested_at',
            'confirmation_decided_at', 'updated_at',
        ])
    else:
        slot = ShiftSlot.objects.create(
            shift=shift,
            worker=None,
            status='open',
            source='manual_schedule_import',
            released_at=now,
            confirmation_status='confirmed',
        )

    _active_slots(ShiftSlot, shift).exclude(pk=slot.pk).update(
        status='cancelled',
        worker=None,
        released_at=now,
    )


def update_spenerhaus_housekeeping_schedule(apps, schema_editor):
    User = apps.get_model('core', 'User')
    WorkerProfile = apps.get_model('core', 'WorkerProfile')
    ClientCompany = apps.get_model('core', 'ClientCompany')
    Location = apps.get_model('core', 'Location')
    Position = apps.get_model('core', 'Position')
    Shift = apps.get_model('core', 'Shift')
    ShiftSlot = apps.get_model('core', 'ShiftSlot')

    izabella = _find_worker(WorkerProfile, User, 'Izabella', IZABELLA_EMAIL)
    musa = _find_worker(WorkerProfile, User, 'Musa')

    # Keep both named workers eligible for the Housekeeping schedule group.
    for worker in (izabella, musa):
        groups = [str(item).lower() for item in (worker.schedule_groups or [])]
        if 'housekeeping' not in groups:
            worker.schedule_groups = list(worker.schedule_groups or []) + ['housekeeping']
            worker.save(update_fields=['schedule_groups', 'updated_at'])

    hotel = ClientCompany.objects.filter(name__iexact='Hotel Spenerhaus', active=True).first()
    if not hotel:
        matches = list(ClientCompany.objects.filter(name__icontains='Spenerhaus', active=True)[:2])
        hotel = matches[0] if len(matches) == 1 else None
    if not hotel:
        raise RuntimeError('Spenerhaus schedule update: unique Hotel Spenerhaus customer not found.')

    location = Location.objects.filter(client=hotel, name__iexact='Hotel Spenerhaus', active=True).first()
    if not location:
        matches = list(Location.objects.filter(client=hotel, name__icontains='Spenerhaus', active=True)[:2])
        location = matches[0] if len(matches) == 1 else None
    if not location:
        matches = list(Location.objects.filter(client=hotel, active=True)[:2])
        location = matches[0] if len(matches) == 1 else None
    if not location:
        raise RuntimeError('Spenerhaus schedule update: Hotel Spenerhaus location is ambiguous or missing.')

    position = Position.objects.filter(name__iexact='Housekeeping', active=True).first()
    if not position:
        position = Position.objects.filter(name__iexact='Houskeeping', active=True).first()
    if not position:
        raise RuntimeError('Spenerhaus schedule update: Housekeeping position not found.')

    created = 0
    updated = 0
    now = timezone.now()

    for day, assignee in SCHEDULE.items():
        starts_at = datetime(2026, 9, day, 8, 0, tzinfo=BERLIN)
        ends_at = datetime(2026, 9, day, 13, 0, tzinfo=BERLIN)

        matching = Shift.objects.filter(
            client=hotel,
            location=location,
            position=position,
            starts_at=starts_at,
            ends_at=ends_at,
        ).exclude(status='cancelled').distinct()

        target = None
        desired_worker = izabella if assignee == 'izabella' else musa if assignee == 'musa' else None

        if desired_worker:
            # Prefer an already-correct assignment, then the previous Izabella seed,
            # then an OpenShift. This transfers 10/11 from Izabella to Musa without
            # touching another independently assigned housekeeping shift.
            target = matching.filter(
                Q(worker=desired_worker) |
                Q(slots__worker=desired_worker, slots__status='claimed')
            ).distinct().first()
            if not target and desired_worker.pk != izabella.pk:
                target = matching.filter(
                    Q(worker=izabella) |
                    Q(slots__worker=izabella, slots__status='claimed')
                ).distinct().first()
            if not target:
                target = matching.filter(
                    Q(is_open=True) |
                    Q(slots__worker__isnull=True, slots__status='open')
                ).distinct().first()
        else:
            # 14/18/19 were previously seeded to Izabella and are now explicitly
            # unnamed, so release those exact assignments back to OpenShift.
            if day in {14, 18, 19}:
                target = matching.filter(
                    Q(worker=izabella) |
                    Q(slots__worker=izabella, slots__status='claimed')
                ).distinct().first()
            if not target:
                target = matching.filter(
                    Q(is_open=True) |
                    Q(slots__worker__isnull=True, slots__status='open')
                ).distinct().first()

        if not target:
            target = Shift.objects.create(
                client=hotel,
                location=location,
                position=position,
                worker=desired_worker,
                starts_at=starts_at,
                ends_at=ends_at,
                break_minutes=0,
                status='confirmed' if desired_worker else 'published',
                is_open=desired_worker is None,
                required_count=1,
                confirmation_required=False,
                schedule_groups=['housekeeping'],
                notes='',
                published_at=None if desired_worker else now,
            )
            created += 1
        else:
            target.client = hotel
            target.location = location
            target.position = position
            target.worker = desired_worker
            target.break_minutes = 0
            target.status = 'confirmed' if desired_worker else 'published'
            target.is_open = desired_worker is None
            target.required_count = 1
            target.confirmation_required = False
            target.schedule_groups = ['housekeeping']
            if desired_worker is None:
                target.published_at = target.published_at or now
            target.save(update_fields=[
                'client', 'location', 'position', 'worker', 'break_minutes', 'status',
                'is_open', 'required_count', 'confirmation_required', 'schedule_groups',
                'published_at', 'updated_at',
            ])
            updated += 1

        if desired_worker:
            _normalize_claimed_slot(ShiftSlot, target, desired_worker, now)
        else:
            _normalize_open_slot(ShiftSlot, target, now)

    print(
        'Spenerhaus Housekeeping schedule update complete: '
        f'{created} created, {updated} normalized.'
    )


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0027_retire_wiw_zero_placeholder'),
    ]

    operations = [
        migrations.RunPython(update_spenerhaus_housekeeping_schedule, migrations.RunPython.noop),
    ]
