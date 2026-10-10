"""Statutory public holidays in Hessen, computed for the calendar year.

Dates follow the Hessian Ministry of the Interior's statutory holiday list.
This only identifies worked holiday hours. Tax ceilings in § 3b EStG are not
employer payment obligations, and paid time off for a holiday is a separate
Entgeltfortzahlung entitlement.
"""
from datetime import date, timedelta
from functools import lru_cache


def easter_sunday(year: int) -> date:
    """Anonymous Gregorian computus, valid for the Gregorian calendar."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    ell = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ell) // 451
    month = (h + ell - 7 * m + 114) // 31
    day = ((h + ell - 7 * m + 114) % 31) + 1
    return date(year, month, day)


@lru_cache(maxsize=32)
def hessen_public_holidays(year: int) -> dict[date, str]:
    easter = easter_sunday(year)
    return {
        date(year, 1, 1): 'Neujahr',
        easter - timedelta(days=2): 'Karfreitag',
        easter + timedelta(days=1): 'Ostermontag',
        date(year, 5, 1): 'Tag der Arbeit',
        easter + timedelta(days=39): 'Christi Himmelfahrt',
        easter + timedelta(days=50): 'Pfingstmontag',
        easter + timedelta(days=60): 'Fronleichnam',
        date(year, 10, 3): 'Tag der Deutschen Einheit',
        date(year, 12, 25): '1. Weihnachtsfeiertag',
        date(year, 12, 26): '2. Weihnachtsfeiertag',
    }


def hessen_holiday(on_date: date) -> str | None:
    return hessen_public_holidays(on_date.year).get(on_date)


def holiday_tax_exempt_ceiling_percent(on_date: date) -> int:
    """§ 3b EStG maximum tax-exempt uplift, NOT a mandatory wage supplement."""
    if on_date in (date(on_date.year, 5, 1), date(on_date.year, 12, 25), date(on_date.year, 12, 26)):
        return 150
    return 125
