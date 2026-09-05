from __future__ import annotations

import re
import unicodedata
from typing import Iterable

from django.db import transaction

from .models import (
    ClientCompany,
    ClientOrder,
    Contract,
    Document,
    Location,
    Shift,
    ShiftImportPackage,
    WorkerRating,
)


ACTIVE_CLIENT_NAMES = (
    'Martha',
    'Stadthaus am Markt',
    'Hotel Spenerhaus',
    'Restaurant Hirschgarten',
    'City Beach',
    'Höfel Catering',
    'Messe Frankfurt',
    'OMMIA',
    'Hofgut',
)

MARTHA_LOCATION_NAMES = (
    'Goethe Uni',
    'Evangelische Akademie',
    'Dominikankloster',
)

WIW_ALIAS_KEY = '_aplus_wiw_aliases'


def normalize_name(value: str) -> str:
    """Normalize imported WIW labels without changing the stored local display name."""
    text = unicodedata.normalize('NFKD', str(value or ''))
    text = ''.join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace('ß', 'ss')
    text = re.sub(r'^\s*\(\s*\d+\s*\)\s*', '', text)
    text = re.sub(r'^\s*\d+\s*[-.:)]\s*', '', text)
    text = re.sub(r'\s+[\-–—:/]*\s*\d+\s*$', '', text)
    text = re.sub(r'[^a-zA-Z0-9]+', ' ', text).strip().casefold()
    return re.sub(r'\s+', ' ', text)


def clean_display_name(value: str) -> str:
    text = str(value or '').strip()
    text = re.sub(r'^\s*\(\s*\d+\s*\)\s*', '', text)
    text = re.sub(r'^\s*\d+\s*[-.:)]\s*', '', text)
    text = re.sub(r'\s+[\-–—:/]*\s*\d+\s*$', '', text)
    return re.sub(r'\s+', ' ', text).strip()


CLIENT_ALIASES = {
    'Martha': {
        'martha', 'marthas', 'martha s', 'marthas finest', 'martha s finest',
    },
    'Stadthaus am Markt': {'stadthaus am markt', 'stadthaus markt'},
    'Hotel Spenerhaus': {'hotel spenerhaus', 'spenerhaus'},
    'Restaurant Hirschgarten': {'restaurant hirschgarten', 'hirschgarten'},
    'City Beach': {'city beach', 'citybeach'},
    'Höfel Catering': {
        'hofel catering', 'hoefel catering', 'hofel', 'hoefel',
        'manuel hofel', 'manuel hoefel', 'manuel hofel catering', 'manuel hoefel catering',
    },
    'Messe Frankfurt': {'messe frankfurt', 'messe'},
    'OMMIA': {'ommia', 'omnia'},
    'Hofgut': {'hofgut'},
}

MARTHA_LOCATION_ALIASES = {
    'Goethe Uni': {
        'goethe uni', 'goethe universitat', 'goethe university', 'goethe universitaet',
    },
    'Evangelische Akademie': {
        'evangelische akademie', 'evangelishe akademie', 'evangelische', 'evangelishe',
    },
    'Dominikankloster': {
        'dominikankloster', 'dominikanerkloster', 'dominikan kloster', 'dominikaner kloster',
    },
}


def canonical_client_name(value: str) -> str | None:
    normalized = normalize_name(value)
    if not normalized:
        return None
    for canonical, aliases in CLIENT_ALIASES.items():
        if normalized in aliases:
            return canonical
        # WIW often appends bookkeeping suffixes/prefixes to otherwise stable names.
        if any(normalized.startswith(alias + ' ') or normalized.endswith(' ' + alias) for alias in aliases):
            return canonical
    return None


def canonical_martha_location_name(value: str) -> str | None:
    normalized = normalize_name(value)
    if not normalized:
        return None
    for canonical, aliases in MARTHA_LOCATION_ALIASES.items():
        if normalized in aliases:
            return canonical
        if any(normalized.startswith(alias + ' ') or normalized.endswith(' ' + alias) for alias in aliases):
            return canonical
    return None


def _client_score(client: ClientCompany, canonical: str) -> tuple[int, int, str]:
    score = 0
    if client.name == canonical:
        score += 100
    elif canonical_client_name(client.name) == canonical:
        score += 60
    if not str(client.customer_number or '').upper().startswith('WIW-'):
        score += 20
    if client.active:
        score += 10
    return (-score, 0 if client.created_at else 1, str(client.created_at or ''))


def get_canonical_client(canonical: str) -> ClientCompany:
    candidates = [
        client for client in ClientCompany.objects.all()
        if canonical_client_name(client.name) == canonical or client.name == canonical
    ]
    if candidates:
        target = sorted(candidates, key=lambda row: _client_score(row, canonical))[0]
    else:
        slug = re.sub(r'[^A-Z0-9]+', '-', normalize_name(canonical).upper()).strip('-') or 'CLIENT'
        number = f'APLUS-{slug}'[:50]
        suffix = 1
        candidate = number
        while ClientCompany.objects.filter(customer_number=candidate).exists():
            suffix += 1
            candidate = f'{number[:44]}-{suffix}'[:50]
        target = ClientCompany.objects.create(name=canonical, customer_number=candidate)
    changed = []
    if target.name != canonical:
        target.name = canonical
        changed.append('name')
    if not target.active:
        target.active = True
        changed.append('active')
    if changed:
        target.save(update_fields=changed + ['updated_at'])
    return target


def _alias_meta(location: Location) -> dict[str, list[str]]:
    payload = location.wiw_payload if isinstance(location.wiw_payload, dict) else {}
    raw = payload.get(WIW_ALIAS_KEY) if isinstance(payload, dict) else None
    raw = raw if isinstance(raw, dict) else {}
    return {
        'locations': sorted({str(value) for value in (raw.get('locations') or []) if value not in (None, '')}),
        'sites': sorted({str(value) for value in (raw.get('sites') or []) if value not in (None, '')}),
    }


def location_aliases(location: Location, kind: str) -> set[str]:
    key = 'sites' if kind == 'site' else 'locations'
    values = set(_alias_meta(location)[key])
    direct = location.wiw_site_id if kind == 'site' else location.wiw_location_id
    if direct:
        values.add(str(direct))
    return values


def merge_wiw_payload(location: Location, raw_payload: dict | None, *, location_ids: Iterable[str] = (), site_ids: Iterable[str] = ()) -> dict:
    existing = location.wiw_payload if isinstance(location.wiw_payload, dict) else {}
    aliases = _alias_meta(location)
    aliases['locations'] = sorted(set(aliases['locations']) | {str(v) for v in location_ids if v not in (None, '')})
    aliases['sites'] = sorted(set(aliases['sites']) | {str(v) for v in site_ids if v not in (None, '')})
    if location.wiw_location_id:
        aliases['locations'] = sorted(set(aliases['locations']) | {str(location.wiw_location_id)})
    if location.wiw_site_id:
        aliases['sites'] = sorted(set(aliases['sites']) | {str(location.wiw_site_id)})
    payload = dict(existing)
    if isinstance(raw_payload, dict):
        # Keep a fresh WIW snapshot while preserving A+ mapping metadata.
        payload.update(raw_payload)
    payload[WIW_ALIAS_KEY] = aliases
    return payload


def find_location_by_external(kind: str, external_id: str | None, *, active_only: bool = True) -> Location | None:
    if external_id in (None, ''):
        return None
    value = str(external_id)
    qs = Location.objects.all()
    if active_only:
        qs = qs.filter(active=True)
    direct_field = 'wiw_site_id' if kind == 'site' else 'wiw_location_id'
    direct = qs.filter(**{direct_field: value}).select_related('client').first()
    if direct:
        return direct
    for location in qs.select_related('client').only(
        'id', 'client_id', 'name', 'active', 'wiw_location_id', 'wiw_site_id', 'wiw_payload'
    ):
        if value in location_aliases(location, kind):
            return location
    return None


def cache_location_aliases(cache: dict[str, Location]) -> None:
    for location in Location.objects.filter(active=True).select_related('client'):
        for external_id in location_aliases(location, 'location'):
            cache[external_id] = location
        for external_id in location_aliases(location, 'site'):
            cache[f'site:{external_id}'] = location


def _move_location_relations(source: Location, target: Location) -> None:
    if source.pk == target.pk:
        return
    Shift.objects.filter(location=source).update(location=target, client=target.client)
    ClientOrder.objects.filter(location=source).update(location=target, client=target.client)

    # Premium/approval models live in separate modules but share the `core` app.
    from .premium_approval_models import WorkerLocationMembership
    from .premium_models import DailyForecast, ScheduleTemplate, TaskList, TaskRun

    for membership in WorkerLocationMembership.objects.filter(location=source).select_related('worker'):
        existing = WorkerLocationMembership.objects.filter(worker=membership.worker, location=target).first()
        if existing:
            if membership.home and not existing.home:
                existing.home = True
                existing.save(update_fields=['home', 'updated_at'])
            membership.delete()
        else:
            membership.location = target
            membership.save(update_fields=['location', 'updated_at'])

    ScheduleTemplate.objects.filter(location=source).update(location=target)
    TaskList.objects.filter(location=source).update(location=target)
    TaskRun.objects.filter(location=source).update(location=target)

    for forecast in DailyForecast.objects.filter(location=source):
        duplicate = DailyForecast.objects.filter(
            location=target,
            date=forecast.date,
            metric=forecast.metric,
        ).exclude(pk=forecast.pk).first()
        if duplicate:
            forecast.delete()
        else:
            forecast.location = target
            forecast.save(update_fields=['location', 'updated_at'])


def _move_client_relations(source: ClientCompany, target: ClientCompany) -> None:
    if source.pk == target.pk:
        return
    target.contacts.add(*source.contacts.all())
    Location.objects.filter(client=source).update(client=target)
    ClientOrder.objects.filter(client=source).update(client=target)
    Shift.objects.filter(client=source).update(client=target)
    Contract.objects.filter(client=source).update(client=target)
    Document.objects.filter(client=source).update(client=target)
    WorkerRating.objects.filter(client=source).update(client=target)
    ShiftImportPackage.objects.filter(client=source).update(client=target)


def _location_score(location: Location, *, canonical_name: str | None = None) -> tuple[int, str]:
    score = 0
    if canonical_name and location.name == canonical_name:
        score += 100
    if not location.wiw_location_id and not location.wiw_site_id:
        score += 30
    if location.active:
        score += 10
    return (-score, str(location.created_at or ''))


def _merge_location_group(target: Location, duplicates: list[Location], *, canonical_name: str | None = None) -> int:
    aliases_locations = set(location_aliases(target, 'location'))
    aliases_sites = set(location_aliases(target, 'site'))
    merged = 0
    for source in duplicates:
        if source.pk == target.pk:
            continue
        aliases_locations |= location_aliases(source, 'location')
        aliases_sites |= location_aliases(source, 'site')
        _move_location_relations(source, target)
        source.active = False
        source.wiw_location_id = None
        source.wiw_site_id = None
        source.save(update_fields=['active', 'wiw_location_id', 'wiw_site_id', 'updated_at'])
        merged += 1
    target.wiw_payload = merge_wiw_payload(
        target,
        None,
        location_ids=aliases_locations,
        site_ids=aliases_sites,
    )
    if canonical_name:
        target.name = canonical_name
    target.active = True
    target.save(update_fields=['wiw_payload', 'name', 'active', 'updated_at'])
    return merged


@transaction.atomic
def normalize_wiw_directory() -> dict[str, int]:
    """Make the A+ directory canonical while keeping WIW external IDs as aliases."""
    stats = {
        'clients_merged': 0,
        'clients_deactivated': 0,
        'locations_merged': 0,
        'locations_deactivated': 0,
    }

    canonical_clients: dict[str, ClientCompany] = {}
    all_clients = list(ClientCompany.objects.all())
    for canonical in ACTIVE_CLIENT_NAMES:
        target = get_canonical_client(canonical)
        canonical_clients[canonical] = target
        for source in all_clients:
            if source.pk == target.pk:
                continue
            if canonical_client_name(source.name) != canonical:
                continue
            _move_client_relations(source, target)
            if source.active:
                source.active = False
                source.save(update_fields=['active', 'updated_at'])
            stats['clients_merged'] += 1

    canonical_ids = {client.pk for client in canonical_clients.values()}
    for client in ClientCompany.objects.exclude(pk__in=canonical_ids).filter(active=True):
        client.active = False
        client.save(update_fields=['active', 'updated_at'])
        stats['clients_deactivated'] += 1

    martha = canonical_clients['Martha']
    # Pull any historical WIW rows named like the three Martha sites into Martha,
    # even when WIW previously created a bogus client for the location itself.
    for canonical_location in MARTHA_LOCATION_NAMES:
        candidates = [
            location for location in Location.objects.select_related('client').all()
            if canonical_martha_location_name(location.name) == canonical_location
        ]
        if not candidates:
            target = Location.objects.create(
                client=martha,
                name=canonical_location,
                address=canonical_location,
                active=True,
            )
        else:
            target = sorted(candidates, key=lambda row: _location_score(row, canonical_name=canonical_location))[0]
            target.client = martha
            target.name = canonical_location
            target.active = True
            target.save(update_fields=['client', 'name', 'active', 'updated_at'])
        stats['locations_merged'] += _merge_location_group(
            target,
            [row for row in candidates if row.pk != target.pk],
            canonical_name=canonical_location,
        )

    martha_locations = Location.objects.filter(client=martha)
    allowed_martha_ids = set(
        martha_locations.filter(name__in=MARTHA_LOCATION_NAMES, active=True).values_list('pk', flat=True)
    )
    for location in martha_locations.exclude(pk__in=allowed_martha_ids).filter(active=True):
        location.active = False
        location.save(update_fields=['active', 'updated_at'])
        stats['locations_deactivated'] += 1

    for canonical, client in canonical_clients.items():
        if canonical == 'Martha':
            continue
        locations = list(Location.objects.filter(client=client).order_by('created_at'))
        if not locations:
            target = Location.objects.create(
                client=client,
                name=canonical,
                address=client.address or canonical,
                active=True,
            )
            continue
        target = sorted(locations, key=_location_score)[0]
        cleaned = clean_display_name(target.name) or canonical
        target.client = client
        target.name = cleaned
        target.active = True
        target.save(update_fields=['client', 'name', 'active', 'updated_at'])
        stats['locations_merged'] += _merge_location_group(
            target,
            [row for row in locations if row.pk != target.pk],
            canonical_name=cleaned,
        )

    # Any locations belonging to non-canonical/inactive clients must stay out of
    # operational pickers, but remain retained for historical traceability.
    for location in Location.objects.exclude(client_id__in=canonical_ids).filter(active=True):
        location.active = False
        location.save(update_fields=['active', 'updated_at'])
        stats['locations_deactivated'] += 1

    return stats
