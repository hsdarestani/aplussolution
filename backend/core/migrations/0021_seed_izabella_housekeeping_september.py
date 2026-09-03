from datetime import datetime
from zoneinfo import ZoneInfo

from django.db import migrations
from django.utils import timezone


DATES = (3, 4, 7, 8, 9, 10, 11, 14, 18, 19)
BERLIN = ZoneInfo('Europe/Berlin')


def seed_izabella_housekeeping(apps, schema_editor):
    User = apps.get_model('core', 'User')
    WorkerProfile = apps.get_model('core', 'WorkerProfile')
    ClientCompany = apps.get_model('core', 'ClientCompany')
    Location = apps.get_model('core', 'Location')
    Position = apps.get_model('core', 'Position')
    Shift = apps.get_model('core', 'Shift')
    ShiftSlot = apps.get_model('core', 'ShiftSlot')

    user = User.objects.filter(first_name__iexact='Izabella', last_name__iexact='Somodo').first()
    if not user:
        print('Izabella seed skipped: user Izabella Somodo not found.')
        return
    worker = WorkerProfile.objects.filter(user=user, active=True).first()
    if not worker:
        print('Izabella seed skipped: active worker profile not found.')
        return

    # Her configured Zeitplan for these hotel duties is Housekeeping. Keeping this
    # authoritative also makes the mobile replacement picker show her correctly.
    if list(worker.schedule_groups or []) != ['housekeeping']:
        worker.schedule_groups = ['housekeeping']
        worker.save(update_fields=['schedule_groups', 'updated_at'])

    hotel = ClientCompany.objects.filter(name__iexact='Hotel Spenerhaus', active=True).first()
    if not hotel:
        hotel_matches = list(ClientCompany.objects.filter(name__icontains='Spenerhaus', active=True)[:2])
        hotel = hotel_matches[0] if len(hotel_matches) == 1 else None
    if not hotel:
        print('Izabella seed skipped: unique Hotel Spenerhaus customer not found.')
        return

    location = Location.objects.filter(client=hotel, name__iexact='Hotel Spenerhaus', active=True).first()
    if not location:
        named_locations = list(Location.objects.filter(client=hotel, name__icontains='Spenerhaus', active=True)[:2])
        if len(named_locations) == 1:
            location = named_locations[0]
    if not location:
        active_locations = list(Location.objects.filter(client=hotel, active=True)[:2])
        if len(active_locations) == 1:
            location = active_locations[0]
    if not location:
        print('Izabella seed skipped: Hotel Spenerhaus location is ambiguous or missing.')
        return

    position = Position.objects.filter(name__iexact='Housekeeping', active=True).first()
    if not position:
        position = Position.objects.filter(name__iexact='Houskeeping', active=True).first()
    if not position:
        print('Izabella seed skipped: Housekeeping position not found.')
        return

    created_count = 0
    existing_count = 0
    conflict_count = 0

    for day in DATES:
        starts_at = datetime(2026, 9, day, 8, 0, tzinfo=BERLIN)
        ends_at = datetime(2026, 9, day, 13, 0, tzinfo=BERLIN)

        target = Shift.objects.filter(
            worker=worker,
            client=hotel,
            starts_at=starts_at,
            ends_at=ends_at,
        ).exclude(status='cancelled').first()

        if not target:
            conflict = Shift.objects.filter(
                worker=worker,
                starts_at__lt=ends_at,
                ends_at__gt=starts_at,
            ).exclude(status='cancelled').first()
            if conflict:
                conflict_count += 1
                print(f'Izabella seed: {day:02d}.09 skipped because another active shift overlaps.')
                continue

            target = Shift.objects.create(
                client=hotel,
                location=location,
                position=position,
                worker=worker,
                starts_at=starts_at,
                ends_at=ends_at,
                break_minutes=0,
                status='confirmed',
                is_open=False,
                required_count=1,
                confirmation_required=False,
                schedule_groups=['housekeeping'],
                notes='',
            )
            created_count += 1
        else:
            existing_count += 1
            changed = False
            expected = {
                'location_id': location.pk,
                'position_id': position.pk,
                'status': 'confirmed',
                'is_open': False,
                'required_count': 1,
                'schedule_groups': ['housekeeping'],
                'break_minutes': 0,
            }
            for field, value in expected.items():
                if getattr(target, field) != value:
                    setattr(target, field, value)
                    changed = True
            if changed:
                target.save(update_fields=[
                    'location', 'position', 'status', 'is_open', 'required_count',
                    'schedule_groups', 'break_minutes', 'updated_at',
                ])

        # Data migrations use historical model classes, so live post_save signals
        # are intentionally not relied on. Normalize the single slot explicitly.
        active_slots = ShiftSlot.objects.filter(shift=target).exclude(status='cancelled').order_by('created_at')
        slot = active_slots.filter(worker=worker).first() or active_slots.filter(worker__isnull=True).first()
        now = timezone.now()
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
            ShiftSlot.objects.create(
                shift=target,
                worker=worker,
                status='claimed',
                source='manual_schedule_import',
                claimed_at=now,
                confirmation_status='confirmed',
                confirmation_decided_at=now,
            )

    print(
        f'Izabella Housekeeping September seed complete: '
        f'{created_count} created, {existing_count} already present, {conflict_count} conflicts skipped.'
    )


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0020_reset_qa_client_password'),
    ]

    operations = [
        migrations.RunPython(seed_izabella_housekeeping, migrations.RunPython.noop),
    ]
