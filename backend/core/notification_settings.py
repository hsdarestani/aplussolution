from __future__ import annotations

from dataclasses import dataclass

from django.db import OperationalError, ProgrammingError

from .push_models import NotificationPushRule


@dataclass(frozen=True)
class PushRuleDefinition:
    key: str
    label: str
    enabled: bool = True
    title_template: str = '{title}'
    body_template: str = '{body}'


PUSH_RULE_CATALOG = (
    PushRuleDefinition('open_shift', 'Neue OpenShifts'),
    PushRuleDefinition('admin_open_shift', 'OpenShift-Zusammenfassung für Admins'),
    PushRuleDefinition('shift_assignment', 'Schicht zugeteilt / übertragen'),
    PushRuleDefinition('shift_updated', 'Schicht geändert'),
    PushRuleDefinition('shift_deleted', 'Schicht gelöscht'),
    PushRuleDefinition('shift_manual_reminder', 'Manuelle Schichterinnerung'),
    PushRuleDefinition('shift_24h_reminder', '24-Stunden-Schichterinnerung'),
    PushRuleDefinition('shift_claimed', 'OpenShift übernommen'),
    PushRuleDefinition('shift_confirmation', 'Schichtbestätigung angefordert'),
    PushRuleDefinition('shift_confirmation_response', 'Schichtbestätigung beantwortet', enabled=False),
    PushRuleDefinition('pickup_request', 'OpenShift-Übernahmeanfrage'),
    PushRuleDefinition('pickup_approved', 'OpenShift-Übernahme genehmigt'),
    PushRuleDefinition('pickup_rejected', 'OpenShift-Übernahme abgelehnt', enabled=False),
    PushRuleDefinition('release_request', 'Schichtfreigabe angefragt'),
    PushRuleDefinition('release_decision', 'Schichtfreigabe entschieden'),
    PushRuleDefinition('shift_swap', 'Schichttausch'),
    PushRuleDefinition('attendance_status', 'Check-in / Check-out'),
    PushRuleDefinition('attendance_reminder', 'Check-in / Check-out Erinnerung'),
    PushRuleDefinition('offsite_checkout', 'Check-out außerhalb Einsatzort'),
    PushRuleDefinition('portal_registration', 'Portal-Registrierung abgeschlossen'),
    PushRuleDefinition('contract', 'Verträge und Unterschriften'),
    PushRuleDefinition('announcement', 'Mitteilungen'),
    PushRuleDefinition('message', 'Nachrichten'),
    PushRuleDefinition('general', 'Sonstige Benachrichtigungen'),
)

_CATALOG_BY_KEY = {item.key: item for item in PUSH_RULE_CATALOG}


def notification_rule_key(notification) -> str:
    kind = str(getattr(notification, 'kind', '') or '')
    title = str(getattr(notification, 'title', '') or '').strip()

    if kind.startswith('admin-open-shift-summary-'):
        return 'admin_open_shift'
    if kind.startswith('open-shift-'):
        return 'open_shift'
    if kind.startswith(('shift-admin-assigned-', 'shift-release-transfer-', 'shift-published-')):
        return 'shift_assignment'
    if kind.startswith('shift-event-'):
        if '-manual-reminder-' in kind:
            return 'shift_manual_reminder'
        if '-deleted-' in kind or '-card-delete-' in kind:
            return 'shift_deleted'
        return 'shift_updated'
    if kind.startswith('shift-24h-'):
        return 'shift_24h_reminder'
    if kind.startswith('shift-claimed-'):
        return 'shift_claimed'
    if kind.startswith(('shift-confirmation-response-', 'shift-confirmation-admin-')):
        return 'shift_confirmation_response'
    if title in {'Schicht bestätigen', 'Bitte Schicht bestätigen'}:
        return 'shift_confirmation'
    if kind.startswith('pickup-request-'):
        return 'pickup_request'
    if kind.startswith('pickup-'):
        return 'pickup_rejected' if kind.endswith('-rejected') else 'pickup_approved'
    if kind.startswith('shift-release-request-'):
        return 'release_request'
    if kind.startswith('shift-release-'):
        return 'release_decision'
    if kind == 'shift-swap' or kind.startswith('shift-swap-'):
        return 'shift_swap'
    if kind.startswith(('attendance-check_in-', 'attendance-check_out-')):
        return 'attendance_status'
    if kind.startswith(('attendance-checkin-reminder-', 'attendance-checkout-reminder-')):
        return 'attendance_reminder'
    if kind.startswith('offsite-checkout-'):
        return 'offsite_checkout'
    if kind.startswith('portal-registration-complete-'):
        return 'portal_registration'
    if kind.startswith('contract-'):
        return 'contract'
    if kind.startswith(('announcement-', 'mitteilung-')) or 'mitteilung' in kind.lower():
        return 'announcement'
    if kind.startswith(('message-', 'conversation-')) or 'nachricht' in kind.lower():
        return 'message'

    # Preserve the old intentionally in-app-only behavior as defaults while
    # allowing admins to turn these event families back on from Settings.
    if title in {
        'Schichtübernahme abgelehnt',
        'Schicht bestätigt',
        'Schicht abgelehnt',
        'Schichtbestätigung aktualisiert',
    }:
        return 'shift_confirmation_response'
    if title == 'Zeiterfassung wurde beendet':
        return 'attendance_status'
    return 'general'


def _stored_rule(key: str):
    try:
        return NotificationPushRule.objects.filter(key=key).first()
    except (OperationalError, ProgrammingError):
        # During first deployment the app can import before migration 0019 has
        # created the table. Native push must not make migrations fail.
        return None


def push_rule_payload(key: str) -> dict:
    definition = _CATALOG_BY_KEY.get(key, _CATALOG_BY_KEY['general'])
    stored = _stored_rule(definition.key)
    return {
        'key': definition.key,
        'label': definition.label,
        'enabled': stored.enabled if stored else definition.enabled,
        'title_template': stored.title_template if stored else definition.title_template,
        'body_template': stored.body_template if stored else definition.body_template,
    }


def all_push_rule_payloads() -> list[dict]:
    try:
        stored = {item.key: item for item in NotificationPushRule.objects.all()}
    except (OperationalError, ProgrammingError):
        stored = {}
    result = []
    for definition in PUSH_RULE_CATALOG:
        override = stored.get(definition.key)
        result.append({
            'key': definition.key,
            'label': definition.label,
            'enabled': override.enabled if override else definition.enabled,
            'title_template': override.title_template if override else definition.title_template,
            'body_template': override.body_template if override else definition.body_template,
        })
    return result


def render_push_notification(notification) -> tuple[bool, str, str, str]:
    key = notification_rule_key(notification)
    rule = push_rule_payload(key)
    title = str(getattr(notification, 'title', '') or '')
    body = str(getattr(notification, 'body', '') or '')
    try:
        rendered_title = str(rule['title_template']).format(title=title, body=body)
    except (KeyError, ValueError, IndexError):
        rendered_title = title
    try:
        rendered_body = str(rule['body_template']).format(title=title, body=body)
    except (KeyError, ValueError, IndexError):
        rendered_body = body
    return bool(rule['enabled']), rendered_title[:240], rendered_body[:4000], key


def save_push_rules(items: list[dict]) -> list[dict]:
    for raw in items:
        key = str(raw.get('key') or '').strip()
        if key not in _CATALOG_BY_KEY:
            continue
        definition = _CATALOG_BY_KEY[key]
        enabled = bool(raw.get('enabled', definition.enabled))
        title_template = str(raw.get('title_template', definition.title_template))[:240]
        body_template = str(raw.get('body_template', definition.body_template))[:4000]
        NotificationPushRule.objects.update_or_create(
            key=key,
            defaults={
                'enabled': enabled,
                'title_template': title_template,
                'body_template': body_template,
            },
        )
    return all_push_rule_payloads()
