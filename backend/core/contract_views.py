from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from .document_center import contract_readiness
from .document_engine import DocumentGenerationError, generate_contract_files
from .models import Contract, ContractSignature, Notification, User
from .permissions import IsAdminOrManager
from .searchable_views import ContractViewSet as SearchableContractViewSet
from .serializers import ContractSerializer
from .services import allowed_signature_role, audit, sign_contract


class ContractLifecycleSerializer(ContractSerializer):
    """Expose backend lifecycle/readiness decisions to every scoped contract row."""

    readiness = serializers.SerializerMethodField()

    def get_readiness(self, obj):
        return contract_readiness(obj)


class ContractViewSet(SearchableContractViewSet):
    """Contract lifecycle with immutable sent/signed documents."""

    serializer_class = ContractLifecycleSerializer

    def perform_update(self, serializer):
        contract = serializer.instance
        if contract.status not in {Contract.Status.DRAFT, Contract.Status.READY}:
            raise ValidationError('Versendete, unterzeichnete, abgelaufene oder stornierte Verträge können nicht bearbeitet werden.')
        if contract.signatures.exists():
            raise ValidationError('Ein Vertrag mit vorhandenen Signaturen kann nicht bearbeitet werden.')
        had_generated_document = bool(contract.pdf or contract.docx or contract.generated_at)
        obj = serializer.save()
        if had_generated_document:
            if obj.pdf:
                obj.pdf.delete(save=False)
            if obj.docx:
                obj.docx.delete(save=False)
            obj.pdf = None
            obj.docx = None
            obj.data_snapshot = {}
            obj.generated_at = None
            obj.status = Contract.Status.DRAFT
            obj.save(update_fields=['pdf', 'docx', 'data_snapshot', 'generated_at', 'status', 'updated_at'])
        audit(self.request, 'contract.updated', obj, {'document_invalidated': had_generated_document})

    def destroy(self, request, *args, **kwargs):
        contract = self.get_object()
        if contract.status != Contract.Status.DRAFT or contract.signatures.exists():
            return Response(
                {'detail': 'Nur unversendete Vertragsentwürfe ohne Signatur dürfen gelöscht werden. Nutze sonst „Stornieren“.'},
                status=400,
            )
        audit(request, 'contract.deleted', contract)
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=['post'], permission_classes=[IsAdminOrManager])
    def generate_pdf(self, request, pk=None):
        contract = self.get_object()
        readiness = contract_readiness(contract)
        if not readiness['generation_allowed']:
            return Response({
                'detail': 'Dieser Vertrag kann in seinem aktuellen Zustand nicht neu erzeugt werden.',
                'readiness': readiness,
            }, status=400)
        try:
            generate_contract_files(contract)
        except DocumentGenerationError as exc:
            return Response({'detail': str(exc), 'readiness': contract_readiness(contract)}, status=400)
        audit(request, 'contract.document_generated', contract)
        contract.refresh_from_db()
        return Response(self.get_serializer(contract).data)

    @action(detail=True, methods=['post'], permission_classes=[IsAdminOrManager])
    def send(self, request, pk=None):
        contract = self.get_object()
        readiness = contract_readiness(contract)
        if not readiness['send_allowed']:
            return Response({
                'detail': 'Dieser Vertrag kann in seinem aktuellen Zustand nicht versendet werden.',
                'readiness': readiness,
            }, status=400)
        if not readiness['document_current']:
            try:
                generate_contract_files(contract)
            except DocumentGenerationError as exc:
                return Response({'detail': str(exc), 'readiness': contract_readiness(contract)}, status=400)
            contract.refresh_from_db()
        contract.status = Contract.Status.SENT
        contract.sent_at = timezone.now()
        contract.save(update_fields=['status', 'sent_at', 'updated_at'])

        recipients = list(User.objects.filter(role__in=[User.Role.ADMIN, User.Role.MANAGER], is_active=True))
        if contract.worker_id and contract.worker.user.is_active:
            recipients.append(contract.worker.user)
        if contract.client_id:
            recipients.extend(contract.client.contacts.filter(is_active=True))
        for recipient in {user.pk: user for user in recipients}.values():
            Notification.objects.get_or_create(
                user=recipient,
                kind=f'contract-sent-{contract.id}',
                defaults={
                    'title': 'Dokument zur Prüfung bereit',
                    'body': contract.title,
                    'action_url': '/contracts',
                },
            )
        audit(request, 'contract.sent', contract)
        return Response(self.get_serializer(contract).data)

    @action(detail=True, methods=['post'])
    def sign(self, request, pk=None):
        contract = self.get_object()
        if contract.status not in {Contract.Status.READY, Contract.Status.SENT}:
            return Response({'detail': 'Dieses Dokument kann nicht mehr unterzeichnet oder überschrieben werden.'}, status=400)
        try:
            role = allowed_signature_role(contract, request.user, request.data.get('role'))
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=400)
        if contract.signatures.filter(role=role).exists():
            return Response({'detail': 'Diese Signaturrolle hat das Dokument bereits unterzeichnet.'}, status=400)
        try:
            sign_contract(
                contract,
                str(request.data.get('name', '')).strip(),
                request.data.get('signature', ''),
                request,
                requested_role=request.data.get('role'),
            )
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=400)
        contract.refresh_from_db()
        return Response(ContractLifecycleSerializer(contract, context={'request': request}).data)

    @action(detail=True, methods=['post'], permission_classes=[IsAdminOrManager])
    def cancel(self, request, pk=None):
        contract = self.get_object()
        if contract.status == Contract.Status.SIGNED or contract.signatures.exists():
            return Response({'detail': 'Ein bereits unterzeichneter Vertrag wird nicht überschrieben oder gelöscht. Verwende den passenden Folgeprozess bzw. Aufhebungsvertrag.'}, status=400)
        if contract.status in {Contract.Status.CANCELLED, Contract.Status.EXPIRED}:
            return Response({'detail': 'Der Vertrag ist bereits abgeschlossen/storniert.'}, status=400)
        reason = str(request.data.get('reason') or '').strip()
        if len(reason) < 5:
            return Response({'detail': 'Bitte dokumentiere den Grund der Stornierung.'}, status=400)
        previous = contract.status
        contract.status = Contract.Status.CANCELLED
        contract.save(update_fields=['status', 'updated_at'])
        audit(request, 'contract.cancelled', contract, {'reason': reason, 'previous_status': previous})
        return Response(self.get_serializer(contract).data)
