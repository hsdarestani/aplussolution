"""Confirmed Lexware employee name aliases.

These aliases bridge legal / payroll names from Lexware to the employee names
used in A+ Solution. Keep them explicit so fuzzy matching never silently links
an employee to the wrong person.
"""

LEXWARE_EMPLOYEE_ALIAS_TARGETS = {
    "fatemeh bagheri hosseinabadi": "shahrzad bagheri",
    "julius philipp degen": "julius degen",
    "mohammad musa jamali": "musa jamali",
    "aikaterini gentsou": "katerina gentsou",
    "ashkan asadian ghaferokhi": "ashkan asadian",
}


def aliases_for_target(target_normalized: str) -> set[str]:
    target = str(target_normalized or "").strip()
    return {
        alias
        for alias, canonical in LEXWARE_EMPLOYEE_ALIAS_TARGETS.items()
        if canonical == target
    }


def canonical_target(source_normalized: str) -> str:
    source = str(source_normalized or "").strip()
    return LEXWARE_EMPLOYEE_ALIAS_TARGETS.get(source, source)
