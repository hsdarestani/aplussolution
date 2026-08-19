import hashlib
import json

from django.utils import timezone

from .models import AuditLog, Contract, ContractSignature, User


def client_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    return forwarded.split(',')[0].strip() if forwarded else request.META.get('REMOTE_ADDR')


def audit(request, action, obj, metadata=None):
    AuditLog.objects.create(
        actor=request.user if request.user.is_authenticated else None,
        action=action,
        object_type=obj.__class__.__name__,
        object_id=str(getattr(obj, 'pk', '')),
        metadata=metadata or {},
        ip_address=client_ip(request),
    )


def render_contract_pdf(contract):
    from .document_engine import generate_contract_files
    generate_contract_files(contract)
    return contract.pdf


def allowed_signature_role(contract, user, requested_role=None):
    if user.role in {User.Role.ADMIN, User.Role.MANAGER}:
        role = requested_role or ContractSignature.Role.EMPLOYER
        if role not in ContractSignature.Role.values:
            raise ValueError('Ungültige Signaturrolle.')
        return role
    if user.role == User.Role.WORKER and contract.worker_id and contract.worker.user_id == user.id:
        if requested_role and requested_role != ContractSignature.Role.EMPLOYEE:
            raise ValueError('Mitarbeiter dürfen ausschließlich als Mitarbeiter unterzeichnen.')
        return ContractSignature.Role.EMPLOYEE
    if user.role == User.Role.CLIENT and contract.client_id and contract.client.contacts.filter(pk=user.pk).exists():
        if requested_role and requested_role != ContractSignature.Role.CLIENT:
            raise ValueError('Kunden dürfen ausschließlich als Kunde unterzeichnen.')
        return ContractSignature.Role.CLIENT
    raise ValueError('Du bist für die Unterzeichnung dieses Dokuments nicht berechtigt.')


def required_signature_roles(contract):
    roles = contract.template.schema.get('signature_roles') or []
    if not contract.template.requires_signature:
        return []
    if not roles:
        if contract.worker_id:
            roles = [ContractSignature.Role.EMPLOYEE, ContractSignature.Role.EMPLOYER]
        elif contract.client_id:
            roles = [ContractSignature.Role.CLIENT, ContractSignature.Role.EMPLOYER]
    return roles


def sign_contract(contract, signer_name, signature_data, request, requested_role=None):
    if not signer_name or not signature_data:
        raise ValueError('Name und Signatur sind erforderlich.')
    if isinstance(signature_data, str) and signature_data.startswith('data:image/') and len(signature_data) > 900_000:
        raise ValueError('Die gezeichnete Signatur ist zu groß. Bitte löschen und erneut, etwas kompakter, unterschreiben.')
    role = allowed_signature_role(contract, request.user, requested_role)
    if role not in required_signature_roles(contract):
        raise ValueError('Diese Signaturrolle ist für das Dokument nicht vorgesehen.')
    signed_at = timezone.now()
    payload = json.dumps({
        'contract': str(contract.id),
        'role': role,
        'user': str(request.user.id),
        'name': signer_name,
        'signature': signature_data,
        'timestamp': signed_at.isoformat(),
    }, sort_keys=True)
    signature_hash = hashlib.sha256(payload.encode()).hexdigest()
    signature, _ = ContractSignature.objects.update_or_create(
        contract=contract,
        role=role,
        defaults={
            'signer': request.user,
            'signer_name': signer_name,
            'signature_data': signature_data,
            'signature_hash': signature_hash,
            'ip_address': client_ip(request),
            'signed_at': signed_at,
        },
    )
    completed_roles = set(contract.signatures.values_list('role', flat=True))
    required_roles = set(required_signature_roles(contract))
    if required_roles.issubset(completed_roles):
        contract.status = Contract.Status.SIGNED
        contract.signed_at = signed_at
        contract.signed_by_name = ', '.join(contract.signatures.order_by('signed_at').values_list('signer_name', flat=True))
        contract.signature_hash = hashlib.sha256(''.join(sorted(contract.signatures.values_list('signature_hash', flat=True))).encode()).hexdigest()
        contract.signature_ip = client_ip(request)
    elif contract.status == Contract.Status.READY:
        contract.status = Contract.Status.SENT
    contract.signature_data = signature_data
    contract.save()
    from .document_engine import generate_contract_files
    if contract.template.source_file or contract.template.source_format == 'html':
        generate_contract_files(contract, validate=False)
        from .signature_pdf import stamp_drawn_signatures
        stamp_drawn_signatures(contract)
    audit(request, 'contract.signed', contract, {'role': role, 'signer': signer_name, 'hash': signature_hash})
    return signature
