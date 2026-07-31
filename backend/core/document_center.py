import hashlib
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.mail import send_mail
from django.utils import timezone

from .document_catalog import CATALOG_BY_SLUG
from .document_catalog_service import ensure_document_catalog
from .document_engine import contract_data, format_value
from .models import Contract, ContractSignature, ContractTemplate, Notification, User
from .services import required_signature_roles


class DocumentCenterError(ValueError):
    pass


def _source_ready(template):
    if template.source_format == ContractTemplate.SourceFormat.HTML:
        return bool((template.html_template or '').strip())
    return bool(template.source_file)


def _catalog_item(template):
    return CATALOG_BY_SLUG.get(template.slug or '')


def template_readiness(template):
    catalog = _catalog_item(template)
    fields = list((template.schema or {}).get('fields') or [])
    required_fields = [item for item in fields if item.get('required')]
    source_required = template.source_format != ContractTemplate.SourceFormat.HTML
    source_installed = _source_ready(template)
    issues = []
    if not template.active:
        issues.append({'code': 'inactive', 'label': 'Vorlage ist deaktiviert.'})
    if source_required and not source_installed:
        issues.append({'code': 'source_missing', 'label': 'Originaldatei ist noch nicht installiert.'})
    if template.source_format == ContractTemplate.SourceFormat.HTML and not source_installed:
        issues.append({'code': 'html_missing', 'label': 'HTML-Vorlage ist leer.'})
    if not template.slug:
        issues.append({'code': 'slug_missing', 'label': 'Vorlagenkennung fehlt.'})
    return {
        'id': str(template.id),
        'slug': template.slug,
        'name': template.name,
        'kind': template.kind,
        'audience': template.audience,
        'version': template.version,
        'source_format': template.source_format,
        'source_required': source_required,
        'source_installed': source_installed,
        'source_checksum': template.source_checksum,
        'expected_source_name': catalog.get('source_name') if catalog else None,
        'requires_signature': template.requires_signature,
        'signature_roles': list((template.schema or {}).get('signature_roles') or []),
        'field_count': len(fields),
        'required_field_count': len(required_fields),
        'active': template.active,
        'ready': not issues,
        'issues': issues,
        'catalog_managed': bool(catalog),
    }


def _formatted_snapshot(data):
    return {key: format_value(value) for key, value in data.items()}


def _subject(contract):
    if contract.worker_id:
        return contract.worker.user.get_full_name() or contract.worker.user.email
    if contract.client_id:
        return contract.client.name
    return 'Ohne Zuordnung'


def contract_readiness(contract):
    template_state = template_readiness(contract.template)
    data = contract_data(contract)
    missing = []
    for field in (contract.template.schema or {}).get('fields', []):
        if field.get('required') and data.get(field.get('name')) in (None, '', [], {}):
            missing.append({
                'field': field.get('name'),
                'label': field.get('label') or field.get('name'),
                'source': field.get('source'),
            })

    required_roles = list(required_signature_roles(contract))
    completed_roles = list(contract.signatures.values_list('role', flat=True))
    pending_roles = [role for role in required_roles if role not in completed_roles]
    generated = bool(contract.pdf and contract.generated_at)
    current_snapshot = _formatted_snapshot(data)
    document_current = bool(generated and contract.data_snapshot == current_snapshot)
    locked = contract.status in {Contract.Status.SENT, Contract.Status.SIGNED} or bool(completed_roles)

    blockers = list(template_state['issues'])
    if missing:
        blockers.append({
            'code': 'required_data_missing',
            'label': f'{len(missing)} Pflichtangabe(n) fehlen.',
        })

    if contract.status in {Contract.Status.CANCELLED, Contract.Status.EXPIRED}:
        state = 'archived'
    elif blockers:
        state = 'blocked'
    elif contract.status == Contract.Status.SIGNED:
        state = 'complete'
    elif contract.status == Contract.Status.SENT and pending_roles:
        state = 'awaiting_signature'
    elif contract.status == Contract.Status.SENT:
        state = 'sent'
    elif contract.status == Contract.Status.READY:
        state = 'ready_to_send' if document_current else 'ready_to_regenerate'
    elif contract.status == Contract.Status.DRAFT:
        state = 'ready_to_generate'
    else:
        state = contract.status

    return {
        'id': str(contract.id),
        'title': contract.title,
        'subject': _subject(contract),
        'template': template_state,
        'status': contract.status,
        'state': state,
        'starts_on': contract.starts_on,
        'ends_on': contract.ends_on,
        'reminder_date': contract.reminder_date,
        'generated_at': contract.generated_at,
        'sent_at': contract.sent_at,
        'signed_at': contract.signed_at,
        'has_pdf': bool(contract.pdf),
        'has_docx': bool(contract.docx),
        'document_current': document_current,
        'locked': locked,
        'missing_fields': missing,
        'blocking_issues': blockers,
        'required_signature_roles': required_roles,
        'completed_signature_roles': completed_roles,
        'pending_signature_roles': pending_roles,
        'generation_allowed': not blockers and not locked and contract.status in {Contract.Status.DRAFT, Contract.Status.READY},
        'send_allowed': not blockers and not locked and contract.status in {Contract.Status.DRAFT, Contract.Status.READY},
        'delete_allowed': contract.status == Contract.Status.DRAFT and not completed_roles,
        'cancel_allowed': contract.status in {Contract.Status.DRAFT, Contract.Status.READY, Contract.Status.SENT} and contract.status != Contract.Status.SIGNED,
    }


def document_center_overview():
    ensure_document_catalog()
    templates = list(ContractTemplate.objects.all().order_by('name'))
    template_states = [template_readiness(template) for template in templates]
    contracts = Contract.objects.select_related(
        'template', 'worker__user', 'client'
    ).prefetch_related('signatures').exclude(status=Contract.Status.CANCELLED).order_by('-updated_at')[:300]
    contract_states = [contract_readiness(contract) for contract in contracts]
    today = timezone.localdate()
    actions = []

    for template in template_states:
        if not template['ready']:
            actions.append({
                'type': 'template',
                'severity': 'critical',
                'action': 'install_source',
                'id': template['id'],
                'slug': template['slug'],
                'title': 'Vorlage nicht einsatzbereit',
                'message': f"{template['name']} · {template['issues'][0]['label']}",
            })

    for contract in contract_states:
        if contract['state'] == 'blocked':
            issue = contract['blocking_issues'][0]
            actions.append({
                'type': 'contract', 'severity': 'critical', 'action': 'fix_data',
                'id': contract['id'], 'title': 'Vertrag blockiert',
                'message': f"{contract['title']} · {issue['label']}",
            })
        elif contract['state'] in {'ready_to_generate', 'ready_to_regenerate'}:
            actions.append({
                'type': 'contract', 'severity': 'warning', 'action': 'generate',
                'id': contract['id'], 'title': 'Dokument muss erzeugt werden',
                'message': f"{contract['title']} · {contract['subject']}",
            })
        elif contract['state'] == 'ready_to_send':
            actions.append({
                'type': 'contract', 'severity': 'info', 'action': 'send',
                'id': contract['id'], 'title': 'Dokument ist versandbereit',
                'message': f"{contract['title']} · {contract['subject']}",
            })
        elif contract['state'] == 'awaiting_signature':
            actions.append({
                'type': 'contract', 'severity': 'warning', 'action': 'signature',
                'id': contract['id'], 'title': 'Unterschrift ausstehend',
                'message': f"{contract['title']} · {', '.join(contract['pending_signature_roles'])}",
            })
        if contract['ends_on'] and today <= contract['ends_on'] <= today + timedelta(days=30):
            days = (contract['ends_on'] - today).days
            actions.append({
                'type': 'contract', 'severity': 'critical' if days <= 7 else 'warning', 'action': 'deadline',
                'id': contract['id'], 'title': 'Vertragsfrist',
                'message': f"{contract['title']} · endet in {days} Tag(en)",
            })

    severity_order = {'critical': 0, 'warning': 1, 'info': 2}
    actions.sort(key=lambda item: (severity_order.get(item['severity'], 9), item['title'], item['message']))
    return {
        'summary': {
            'templates_total': len(template_states),
            'templates_ready': sum(item['ready'] for item in template_states),
            'templates_missing_source': sum(any(issue['code'] in {'source_missing', 'html_missing'} for issue in item['issues']) for item in template_states),
            'contracts_total': len(contract_states),
            'blocked': sum(item['state'] == 'blocked' for item in contract_states),
            'ready_to_generate': sum(item['state'] in {'ready_to_generate', 'ready_to_regenerate'} for item in contract_states),
            'ready_to_send': sum(item['state'] == 'ready_to_send' for item in contract_states),
            'awaiting_signature': sum(item['state'] == 'awaiting_signature' for item in contract_states),
        },
        'templates': template_states,
        'contracts': contract_states,
        'actions': actions[:160],
    }


def install_template_source(slug, upload, version=None):
    ensure_document_catalog()
    catalog = CATALOG_BY_SLUG.get(slug)
    if not catalog:
        raise DocumentCenterError('Unbekannte Dokumentvorlage.')
    template = ContractTemplate.objects.filter(slug=slug).first()
    if not template:
        raise DocumentCenterError('Dokumentvorlage wurde nicht initialisiert.')
    filename = Path(upload.name or '').name
    suffix = Path(filename).suffix.lower()
    expected = '.docx' if template.source_format == ContractTemplate.SourceFormat.DOCX else '.pdf'
    if template.source_format == ContractTemplate.SourceFormat.HTML:
        raise DocumentCenterError('HTML-Vorlagen werden nicht als Binärdatei hochgeladen.')
    if suffix != expected:
        raise DocumentCenterError(f'Für diese Vorlage wird eine {expected.upper()}-Datei erwartet.')
    content = upload.read()
    if not content:
        raise DocumentCenterError('Die hochgeladene Datei ist leer.')
    checksum = hashlib.sha256(content).hexdigest()
    template.source_file.save(filename, ContentFile(content), save=False)
    template.source_checksum = checksum
    if version:
        template.version = str(version).strip()[:30]
    template.save()
    return template_readiness(template)


def reminder_recipients(contract, missing_roles=None):
    users = {}
    admins = User.objects.filter(role__in=[User.Role.ADMIN, User.Role.MANAGER], is_active=True)
    for user in admins:
        users[user.pk] = user
    roles = set(missing_roles or [])
    if not missing_roles or ContractSignature.Role.EMPLOYEE in roles:
        if contract.worker_id and contract.worker.user.is_active:
            users[contract.worker.user_id] = contract.worker.user
    if not missing_roles or ContractSignature.Role.CLIENT in roles:
        if contract.client_id:
            for user in contract.client.contacts.filter(is_active=True):
                users[user.pk] = user
    return list(users.values())


def _create_notice(contract, event_key, title, body, recipients):
    notifications = 0
    emailed = []
    for user in recipients:
        _, created = Notification.objects.get_or_create(
            user=user,
            kind=f'{event_key}-{contract.id}',
            defaults={
                'action_url': '/contracts',
                'title': title,
                'body': body,
            },
        )
        if not created:
            continue
        notifications += 1
        if user.email:
            emailed.append(user.email)
    if emailed:
        send_mail(
            f'A+ Solution: {title}',
            f'{body}\n\nBitte im A+ Solution Portal prüfen.',
            settings.DEFAULT_FROM_EMAIL,
            sorted(set(emailed)),
            fail_silently=True,
        )
    return notifications, len(set(emailed))


def dispatch_contract_reminders(today=None):
    today = today or timezone.localdate()
    notifications = 0
    emails = 0
    events = 0
    contracts = Contract.objects.select_related(
        'template', 'worker__user', 'client'
    ).prefetch_related('client__contacts', 'signatures').exclude(
        status__in=[Contract.Status.CANCELLED, Contract.Status.EXPIRED]
    )

    for contract in contracts:
        state = contract_readiness(contract)
        if contract.ends_on:
            days = (contract.ends_on - today).days
            if days in {30, 14, 7, 1, 0} and contract.status in {Contract.Status.READY, Contract.Status.SENT, Contract.Status.SIGNED}:
                title = 'Vertrag endet heute' if days == 0 else f'Vertrag endet in {days} Tagen'
                body = f'{contract.title} · {state["subject"]}'
                event_key = f'contract-{days}' if days in {30, 7} else f'contract-end-{days}d'
                created, mailed = _create_notice(
                    contract, event_key, title, body, reminder_recipients(contract)
                )
                notifications += created; emails += mailed; events += int(bool(created))

        if contract.reminder_date == today:
            created, mailed = _create_notice(
                contract, 'contract-explicit-reminder', 'Vertragserinnerung',
                f'{contract.title} · {state["subject"]}', reminder_recipients(contract)
            )
            notifications += created; emails += mailed; events += int(bool(created))

        if contract.status == Contract.Status.SENT and state['pending_signature_roles'] and contract.sent_at:
            age_days = (today - timezone.localtime(contract.sent_at).date()).days
            if age_days in {3, 7, 14, 30}:
                roles = state['pending_signature_roles']
                role_labels = {'employee': 'Mitarbeiter', 'employer': 'Arbeitgeber', 'client': 'Kunde'}
                labels = ', '.join(role_labels.get(role, role) for role in roles)
                created, mailed = _create_notice(
                    contract, f'contract-signature-{age_days}d', 'Unterschrift ausstehend',
                    f'{contract.title} · ausstehend: {labels}', reminder_recipients(contract, roles)
                )
                notifications += created; emails += mailed; events += int(bool(created))

    return {'events': events, 'notifications': notifications, 'emails': emails}
