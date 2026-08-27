import re
import unicodedata
from difflib import SequenceMatcher

from django.db import migrations

CLIENTS = [
    ("Martha's Finest", ("marthas finest", "martha finest", "martha's finest")),
    ("City Beach", ("city beach", "citybeach")),
    ("OMMIA Frankfurt", ("ommia frankfurt", "ommia", "omnia frankfurt", "omnia")),
    ("Messe Frankfurt", ("messe frankfurt", "frankfurter messe")),
    ("Stadthaus am Markt", ("stadthaus am markt", "stadhaust am markt")),
    ("Hofgut", ("hofgut",)),
    ("Restaurant Hirschgarten", ("restaurant hirschgarten", "hirschgarten")),
    ("Hotel Spenerhaus", ("hotel spenerhaus", "spenerhaus")),
    ("Höfel Catering – Aschaffenburg", ("höfel catering aschaffenburg", "hoefel catering aschaffenburg", "hofel catering aschaffenburg", "höfel catering", "hoefel catering")),
]
POSITIONS = [
    ("Servicekraft", ("servicekraft", "servicekrat", "service kraft"), '#155eef'),
    ("Serviceleitung", ("serviceleitung", "service leitung"), '#7a5af8'),
    ("Front Office", ("front office", "front-office", "frontoffice"), '#0891b2'),
    ("Housekeeping", ("housekeeping", "houskeeping", "house keeping"), '#16a34a'),
    ("Bar-Support", ("bar support", "bar-support", "barsupport"), '#d97706'),
]


def norm(value):
    value = unicodedata.normalize('NFKD', str(value or '')).encode('ascii', 'ignore').decode('ascii').lower().replace('ß', 'ss')
    return re.sub(r'[^a-z0-9]+', ' ', value).strip()


def similarity(value, canonical, aliases):
    needle = norm(value)
    scores = [SequenceMatcher(None, needle, norm(item)).ratio() for item in (canonical, *aliases)]
    if needle in {norm(item) for item in (canonical, *aliases)}:
        return 1.0
    return max(scores or [0.0])


def next_customer_number(ClientCompany, index):
    base = f'KD-SCOPE-{index:02d}'
    if not ClientCompany.objects.filter(customer_number=base).exists():
        return base
    suffix = 2
    while ClientCompany.objects.filter(customer_number=f'{base}-{suffix}').exists():
        suffix += 1
    return f'{base}-{suffix}'


def apply_scope(apps, schema_editor):
    ClientCompany = apps.get_model('core', 'ClientCompany')
    Position = apps.get_model('core', 'Position')

    clients = list(ClientCompany.objects.all())
    claimed = set()
    for index, (canonical, aliases) in enumerate(CLIENTS, start=1):
        available = [item for item in clients if item.pk not in claimed]
        exact = [item for item in available if norm(item.name) == norm(canonical)]
        if exact:
            chosen = exact[0]
        else:
            ranked = sorted(((similarity(item.name, canonical, aliases), item) for item in available), key=lambda pair: pair[0], reverse=True)
            chosen = ranked[0][1] if ranked and ranked[0][0] >= 0.78 else None
        if chosen is None:
            chosen = ClientCompany.objects.create(name=canonical, customer_number=next_customer_number(ClientCompany, index), active=True)
            clients.append(chosen)
        else:
            chosen.name = canonical
            chosen.active = True
            chosen.save(update_fields=['name', 'active'])
        claimed.add(chosen.pk)

    ClientCompany.objects.exclude(pk__in=claimed).update(active=False)

    positions = list(Position.objects.all())
    position_claimed = set()
    for canonical, aliases, color in POSITIONS:
        available = [item for item in positions if item.pk not in position_claimed]
        exact = [item for item in available if norm(item.name) == norm(canonical)]
        if exact:
            chosen = exact[0]
        else:
            ranked = sorted(((similarity(item.name, canonical, aliases), item) for item in available), key=lambda pair: pair[0], reverse=True)
            chosen = ranked[0][1] if ranked and ranked[0][0] >= 0.76 else None
        if chosen is None:
            chosen = Position.objects.create(name=canonical, color=color, active=True)
            positions.append(chosen)
        else:
            chosen.name = canonical
            chosen.active = True
            if not chosen.color:
                chosen.color = color
            chosen.save(update_fields=['name', 'active', 'color'])
        position_claimed.add(chosen.pk)

    Position.objects.exclude(pk__in=position_claimed).update(active=False)


class Migration(migrations.Migration):
    dependencies = [('core', '0012_pushdevice')]
    operations = [migrations.RunPython(apply_scope, migrations.RunPython.noop)]
