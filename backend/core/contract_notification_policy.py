"""Recipient-level privacy policy for contract deadline notifications.

Marthas client-portal contacts must not receive or see contractual END-date
alerts. Signature requests, contract delivery and operational notifications
remain available, and admins retain deadline visibility.
"""
import re

from .models import User


CONTRACT_END_KIND_PATTERN = r'^contract-(?:end-)?[0-9]+d?-'
_CONTRACT_END_KIND_RE = re.compile(CONTRACT_END_KIND_PATTERN)


def is_contract_end_notice(kind: str) -> bool:
    """Match deadline events, but not contract-sent/signature/explicit reminders."""
    return bool(_CONTRACT_END_KIND_RE.match(str(kind or '')))


def is_marthas_client_contact(user: User) -> bool:
    """Use actual customer membership, never notification text or recipient name."""
    return bool(
        user
        and user.role == User.Role.CLIENT
        and user.client_companies.filter(name__icontains='martha').exists()
    )


def suppress_contract_end_notice(user: User, kind: str) -> bool:
    return is_contract_end_notice(kind) and is_marthas_client_contact(user)


def visible_notifications_for_user(queryset, user: User):
    """Hide already-created expiry events from all Marthas client accounts."""
    if is_marthas_client_contact(user):
        return queryset.exclude(kind__regex=CONTRACT_END_KIND_PATTERN)
    return queryset
