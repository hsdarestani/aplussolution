import re
import unicodedata
from difflib import SequenceMatcher

CANONICAL_CLIENTS = {
    "Martha's Finest": ("marthas finest", "martha finest", "martha's finest"),
    "City Beach": ("city beach", "citybeach"),
    "OMMIA Frankfurt": ("ommia frankfurt", "ommia", "omnia frankfurt", "omnia"),
    "Messe Frankfurt": ("messe frankfurt", "frankfurter messe"),
    "Stadthaus am Markt": ("stadthaus am markt", "stadhaust am markt"),
    "Hofgut": ("hofgut",),
    "Restaurant Hirschgarten": ("restaurant hirschgarten", "hirschgarten"),
    "Hotel Spenerhaus": ("hotel spenerhaus", "spenerhaus"),
    "Höfel Catering – Aschaffenburg": ("höfel catering aschaffenburg", "hoefel catering aschaffenburg", "hofel catering aschaffenburg", "höfel catering", "hoefel catering"),
}

CANONICAL_POSITIONS = {
    "Servicekraft": ("servicekraft", "servicekrat", "service kraft"),
    "Serviceleitung": ("serviceleitung", "service leitung"),
    "Front Office": ("front office", "front-office", "frontoffice"),
    "Housekeeping": ("housekeeping", "houskeeping", "house keeping"),
    "Bar-Support": ("bar support", "bar-support", "barsupport"),
}


def normalize(value):
    value = unicodedata.normalize('NFKD', str(value or '')).encode('ascii', 'ignore').decode('ascii').lower().replace('ß', 'ss')
    return re.sub(r'[^a-z0-9]+', ' ', value).strip()


def _canonical(value, catalog, threshold=0.80):
    needle = normalize(value)
    if not needle:
        return None
    best_name, best_score = None, 0.0
    for canonical, aliases in catalog.items():
        for alias in (canonical, *aliases):
            candidate = normalize(alias)
            if needle == candidate:
                return canonical
            score = SequenceMatcher(None, needle, candidate).ratio()
            if score > best_score:
                best_name, best_score = canonical, score
    return best_name if best_score >= threshold else None


def canonical_client_name(value):
    return _canonical(value, CANONICAL_CLIENTS, 0.78)


def canonical_position_name(value):
    return _canonical(value, CANONICAL_POSITIONS, 0.76)
