from __future__ import annotations

from django.db import transaction

from .models import ClientCompany, ClientOrder, Contract, Document, Location, Position, Shift, ShiftImportPackage, TimeEntry, WorkerRating
from .workforce_scope import CANONICAL_CLIENTS, CANONICAL_POSITIONS, canonical_client_name, canonical_position_name

POSITION_COLORS = {
    'Servicekraft': '#155eef',
    'Serviceleitung': '#7a5af8',
    'Front Office': '#0891b2',
    'Housekeeping': '#16a34a',
    'Bar-Support': '#d97706',
}


def _next_customer_number(index: int) -> str:
    base = f'KD-SCOPE-{index:02d}'
    if not ClientCompany.objects.filter(customer_number=base).exists():
        return base
    suffix = 2
    while ClientCompany.objects.filter(customer_number=f'{base}-{suffix}').exists():
        suffix += 1
    return f'{base}-{suffix}'


def _ensure_canonical_clients():
    targets = {}
    for index, name in enumerate(CANONICAL_CLIENTS, start=1):
        matches = ClientCompany.objects.filter(name__iexact=name)
        target = matches.exclude(customer_number__startswith='WIW-').first() or matches.first()
        if target is None:
            target = ClientCompany.objects.create(name=name, customer_number=_next_customer_number(index), active=True)
        elif target.name != name or not target.active:
            target.name = name
            target.active = True
            target.save(update_fields=['name', 'active', 'updated_at'])
        targets[name] = target
    return targets


def _ensure_canonical_positions():
    targets = {}
    for name in CANONICAL_POSITIONS:
        target = Position.objects.filter(name__iexact=name).first()
        if target is None:
            target = Position.objects.create(name=name, color=POSITION_COLORS[name], active=True)
        else:
            changed = []
            if target.name != name:
                target.name = name
                changed.append('name')
            if not target.active:
                target.active = True
                changed.append('active')
            if not target.color:
                target.color = POSITION_COLORS[name]
                changed.append('color')
            if changed:
                target.save(update_fields=[*changed, 'updated_at'])
        targets[name] = target
    return targets


def _relink_client(source, target):
    counts = {
        'locations_relinked': Location.objects.filter(client=source).update(client=target),
        'orders_relinked': ClientOrder.objects.filter(client=source).update(client=target),
        'shifts_client_relinked': Shift.objects.filter(client=source).update(client=target),
        'contracts_relinked': Contract.objects.filter(client=source).update(client=target),
        'documents_relinked': Document.objects.filter(client=source).update(client=target),
        'ratings_relinked': WorkerRating.objects.filter(client=source).update(client=target),
        'shift_import_packages_relinked': ShiftImportPackage.objects.filter(client=source).update(client=target),
    }
    contact_ids = list(source.contacts.values_list('id', flat=True))
    if contact_ids:
        target.contacts.add(*contact_ids)
    return counts


@transaction.atomic
def reconcile_wiw_history_scope():
    """Link imported WIW history to the Phase 1 master-data scope without deleting history."""
    shift_count_before = Shift.objects.count()
    time_count_before = TimeEntry.objects.count()
    wiw_shift_count_before = Shift.objects.exclude(wiw_shift_id__isnull=True).exclude(wiw_shift_id='').count()
    wiw_time_count_before = TimeEntry.objects.exclude(wiw_time_id__isnull=True).exclude(wiw_time_id='').count()

    counts = {
        'clients_merged': 0,
        'clients_archived': 0,
        'positions_merged': 0,
        'positions_archived': 0,
        'locations_archived': 0,
        'locations_relinked': 0,
        'orders_relinked': 0,
        'shifts_client_relinked': 0,
        'shifts_position_relinked': 0,
        'contracts_relinked': 0,
        'documents_relinked': 0,
        'ratings_relinked': 0,
        'shift_import_packages_relinked': 0,
    }

    client_targets = _ensure_canonical_clients()
    for source in list(ClientCompany.objects.all()):
        canonical = canonical_client_name(source.name)
        if canonical:
            target = client_targets[canonical]
            if source.pk != target.pk:
                relinked = _relink_client(source, target)
                for key, amount in relinked.items():
                    counts[key] += amount
                was_active = source.active
                if was_active:
                    source.active = False
                    source.save(update_fields=['active', 'updated_at'])
                if was_active or any(relinked.values()):
                    counts['clients_merged'] += 1
            continue
        if source.active:
            source.active = False
            source.save(update_fields=['active', 'updated_at'])
            counts['clients_archived'] += 1

    position_targets = _ensure_canonical_positions()
    for source in list(Position.objects.all()):
        canonical = canonical_position_name(source.name)
        if canonical:
            target = position_targets[canonical]
            if source.pk != target.pk:
                relinked = Shift.objects.filter(position=source).update(position=target)
                counts['shifts_position_relinked'] += relinked
                was_active = source.active
                if was_active:
                    source.active = False
                    source.save(update_fields=['active', 'updated_at'])
                if was_active or relinked:
                    counts['positions_merged'] += 1
            continue
        if source.active:
            source.active = False
            source.save(update_fields=['active', 'updated_at'])
            counts['positions_archived'] += 1

    counts['locations_archived'] = Location.objects.filter(client__active=False, active=True).update(active=False)

    shift_count_after = Shift.objects.count()
    time_count_after = TimeEntry.objects.count()
    wiw_shift_count_after = Shift.objects.exclude(wiw_shift_id__isnull=True).exclude(wiw_shift_id='').count()
    wiw_time_count_after = TimeEntry.objects.exclude(wiw_time_id__isnull=True).exclude(wiw_time_id='').count()
    if shift_count_after != shift_count_before or time_count_after != time_count_before:
        raise RuntimeError('WIW scope reconciliation changed historical Shift/TimeEntry row counts.')
    if wiw_shift_count_after != wiw_shift_count_before or wiw_time_count_after != wiw_time_count_before:
        raise RuntimeError('WIW scope reconciliation changed imported WIW identity counts.')

    active_clients = list(ClientCompany.objects.filter(active=True).order_by('name').values_list('name', flat=True))
    active_positions = list(Position.objects.filter(active=True).order_by('name').values_list('name', flat=True))
    invalid_active_locations = Location.objects.filter(active=True, client__active=False).count()
    valid = active_clients == sorted(CANONICAL_CLIENTS) and active_positions == sorted(CANONICAL_POSITIONS) and invalid_active_locations == 0

    return {
        'valid': valid,
        'counts': counts,
        'active_clients': active_clients,
        'active_positions': active_positions,
        'invalid_active_locations': invalid_active_locations,
        'history': {
            'shifts_before': shift_count_before,
            'shifts_after': shift_count_after,
            'time_entries_before': time_count_before,
            'time_entries_after': time_count_after,
            'wiw_shifts_before': wiw_shift_count_before,
            'wiw_shifts_after': wiw_shift_count_after,
            'wiw_time_entries_before': wiw_time_count_before,
            'wiw_time_entries_after': wiw_time_count_after,
        },
    }
