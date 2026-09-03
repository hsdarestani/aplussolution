from datetime import datetime
from zoneinfo import ZoneInfo

from django.db import migrations
from django.db.models import Q
from django.utils import timezone


DATES = (3, 4, 7, 8, 9, 10, 11, 14, 18, 19)
BERLIN = ZoneInfo('Europe/Berlin')
IZABELLA_EMAIL = 'izabellasomodi21@yahoo.com'


def reconcile_izabella_housekeeping(apps, schema_editor):
    User = apps.get_model('core', 'User')
    WorkerProfile = apps.get_model('core', 'WorkerProfile')
    ClientCompany = apps.get_model('core', 'ClientCompany')
    Location = apps.get_model('core', 'Location')
    Position = apps.get_model('core', 'Position')
    Shift = apps.get_model('core', 'Shift')
    ShiftSlot = apps.get_model('core', 'ShiftSlot')

    user = User.objects.filter(email__iexact=IZABELLA_EMAIL).first()
    if not user:
        user = User.objects.filter(first_name__iexact='Izabella', last_name__iexact='Somodi').first()
    if not user:
        user = User.objects.filter(first_name__iexact='Izabella', last_name__iexact='Somodo').first()
    if not user:
        print('Izabella reconcile skipped: approved employee account not found.')
        return

    worker = WorkerProfile.objects.filter(user=user).first()
    if not worker:
        print('Izabella reconcile skipped: WorkerProfile not found for approved account.')
        return

    changed_worker_fields = []
    if not worker.active:
        worker.active = True
        changed_worker_fields.append('active')
    if list(worker.schedule_groups or []) != ['housekeeping']:
        worker.schedule_groups = ['housekeeping']
        changed_worker_fields.append('schedule_groups')
    if changed_worker_fields:
        changed_worker_fields.append('updated_at')
        worker.save(update_fields=changed_worker_fields)

    hotel = ClientCompany.objects.filter(name__iexact='Hotel Spenerhaus', active=True).first()
    if not hotel:
        matches = list(ClientCompany.objects.filter(name__icontains='Spenerhaus', active=True)[:2])
        hotel = matches[0] if len(matches) == 1 else None
    if not hotel:
        print('Izabella reconcile skipped: unique Hotel Spenerhaus customer not found.')
        return

    location = Location.objects.filter(client=hotel, name__iexact='Hotel Spenerhaus', active=True).first()
    if not location:
        matches = list(Location.objects.filter(client=hotel, name__icontains='Spenerhaus', active=True)[:2])
        location = matches[0] if len(matches) == 1 else None
    if not location:
        matches = list(Location.objects.filter(client=hotel, active=True)[:2])
        location = matches[0] if len(matches) == 1 else None
    if not location:
        print('Izabella reconcile skipped: Hotel Spenerhaus location is ambiguous or missing.')
        return

    position = Position.objects.filter(name__iexact='Housekeeping', active=True).first()
    if not position:
        position = Position.objects.filter(name__iexact='Houskeeping', active=True).first()
    if not position:
        print('Izabella reconcile skipped: Housekeeping position not found.')
        return

    created_count = 0
    existing_count = 0
    conflict_count = 0

    for day in DATES:
        starts_at = datetime(2026, 9, day, 8, 0, tzinfo=BERLIN)
        ends_at = datetime(2026, 9, day, 13, 0, tzinfo=BERLIN)

        target = Shift.objects.filter(
            client=hotel,
            starts_at=starts_at,
            ends_at=ends_at,
        ).filter(
            Q(worker=worker) |
            Q(slots__worker=worker, slots__status='claimed')
        ).exclude(status='cancelled').distinct().first()

        if not target:
            conflict = Shift.objects.filter(
                starts_at__lt=ends_at,
                ends_at__gt=starts_at,
            ).filter(
                Q(worker=worker) |
                Q(slots__worker=worker, slots__status='claimed')
            ).exclude(status='cancelled').distinct().first()
            if conflict:
                conflict_count += 1
                print(f'Izabella reconcile: {day:02d}.09 skipped because another active shift overlaps.')
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
            expected = {
                'client_id': hotel.pk,
                'location_id': location.pk,
                'position_id': position.pk,
                'worker_id': worker.pk,
                'status': 'confirmed',
                'is_open': False,
                'required_count': 1,
                'schedule_groups': ['housekeeping'],
                'break_minutes': 0,
            }
            changed = []
            for field, value in expected.items():
                if getattr(target, field) != value:
                    setattr(target, field, value)
                    changed.append(field.removesuffix('_id') if field.endswith('_id') else field)
            if changed:
                target.save(update_fields=list(dict.fromkeys(changed + ['updated_at'])))

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

        # A one-person shift must have exactly one active slot. Cancel stale extras
        # rather than leaving an accidental OpenShift beside Izabella's assignment.
        extras = active_slots.exclude(pk=slot.pk if slot else None)
        if extras.exists():
            extras.update(status='cancelled', worker=None, released_at=now)

    print(
        'Izabella Housekeeping September reconcile complete: '
        f'{created_count} created, {existing_count} existing, {conflict_count} conflicts skipped.'
    )


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0021_seed_izabella_housekeeping_september'),
    ]

    operations = [
        migrations.RunPython(reconcile_izabella_housekeeping, migrations.RunPython.noop),
    ]
