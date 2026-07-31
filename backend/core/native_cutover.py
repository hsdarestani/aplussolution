from .models import Contract, ShiftImportPackage
from .native_workforce import (
    approve_order as _approve_order,
    generate_client_contract as _generate_client_contract,
    sync_packages_from_local_shifts,
    sync_working_time,
)
from .order_automation import _validate_parsed, extract_request_id, fallback_request_id, payload_hash


LOCKED_CONTRACT_STATUSES = {Contract.Status.SENT, Contract.Status.SIGNED}


def approve_order(parsed: dict, raw_text: str, actor=None, client_id=None) -> dict:
    clean = _validate_parsed(parsed)
    client_hint = str(client_id or clean['shifts'][0].get('site_text') or '')
    request_id = extract_request_id(raw_text, clean) or fallback_request_id(clean, client_hint)
    source_hash = payload_hash(clean, client_hint, request_id)
    existing = ShiftImportPackage.objects.select_related('contract').filter(request_id=request_id).first()
    if (
        existing
        and existing.source_hash != source_hash
        and existing.contract_id
        and existing.contract.status in LOCKED_CONTRACT_STATUSES
    ):
        raise ValueError(
            'Der Auftrag ist mit einem bereits versendeten oder unterzeichneten Vertrag verknüpft. '
            'Bitte eine neue Auftragsversion anlegen, statt den bestehenden Rechtsstand zu überschreiben.'
        )
    return _approve_order(clean, raw_text, actor=actor, client_id=client_id)


def generate_client_contract(package: ShiftImportPackage, actor=None):
    if package.contract_id and package.contract.status in LOCKED_CONTRACT_STATUSES:
        raise ValueError('Ein versendeter oder unterzeichneter Vertrag darf nicht neu erzeugt oder überschrieben werden.')
    return _generate_client_contract(package, actor=actor)
