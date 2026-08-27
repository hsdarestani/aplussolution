from pathlib import Path

from rest_framework import serializers
from .models import *
from .workforce_scope import CANONICAL_POSITIONS, canonical_position_name


class UserSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'email', 'first_name', 'last_name', 'name', 'phone', 'role', 'avatar', 'is_onboarded']
        read_only_fields = ['role']

    def get_name(self, obj):
        return obj.get_full_name() or obj.email


class UserAdminSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'email', 'first_name', 'last_name', 'name', 'phone', 'role', 'is_active']

    def get_name(self, obj):
        return obj.get_full_name() or obj.email


class ClientCompanySerializer(serializers.ModelSerializer):
    contacts_detail = UserSerializer(source='contacts', many=True, read_only=True)

    class Meta:
        model = ClientCompany
        fields = '__all__'


class WorkerProfileSerializer(serializers.ModelSerializer):
    user_detail = UserSerializer(source='user', read_only=True)

    class Meta:
        model = WorkerProfile
        fields = '__all__'


class LocationSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source='client.name', read_only=True)

    class Meta:
        model = Location
        fields = '__all__'


class PositionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Position
        fields = '__all__'

    def validate_name(self, value):
        canonical = canonical_position_name(value)
        if not canonical:
            allowed = ', '.join(CANONICAL_POSITIONS)
            raise serializers.ValidationError(f'Aktuell sind nur diese Positionen vorgesehen: {allowed}.')
        qs = Position.objects.filter(name__iexact=canonical)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError('Diese Position ist bereits vorhanden.')
        return canonical


class ClientOrderSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source='client.name', read_only=True)
    location_name = serializers.CharField(source='location.name', read_only=True)

    class Meta:
        model = ClientOrder
        fields = '__all__'
        read_only_fields = ['created_by']
        extra_kwargs = {'client': {'required': False}}

    def validate_attachment(self, uploaded):
        if not uploaded:
            return uploaded
        if getattr(uploaded, 'size', 0) > 20 * 1024 * 1024:
            raise serializers.ValidationError('Die Auftragsdatei darf maximal 20 MB groß sein.')
        extension = Path(str(getattr(uploaded, 'name', '') or '')).suffix.lower()
        allowed = {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.csv', '.txt', '.png', '.jpg', '.jpeg'}
        if extension not in allowed:
            raise serializers.ValidationError('Erlaubt sind PDF, Word, Excel/CSV, Text und Bilder (JPG/PNG).')
        return uploaded


class AvailabilitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Availability
        fields = '__all__'


class ShiftSerializer(serializers.ModelSerializer):
    worker_name = serializers.CharField(source='worker.user.get_full_name', read_only=True)
    client_name = serializers.CharField(source='client.name', read_only=True)
    location_name = serializers.CharField(source='location.name', read_only=True)
    position_name = serializers.CharField(source='position.name', read_only=True)

    class Meta:
        model = Shift
        fields = '__all__'


class TimeEntrySerializer(serializers.ModelSerializer):
    worked_minutes = serializers.IntegerField(read_only=True)
    worker_name = serializers.CharField(source='worker.user.get_full_name', read_only=True)
    shift_title = serializers.CharField(source='shift.position.name', read_only=True)

    class Meta:
        model = TimeEntry
        fields = '__all__'
        read_only_fields = ['approved_by']


class TimeOffRequestSerializer(serializers.ModelSerializer):
    worker_name = serializers.CharField(source='worker.user.get_full_name', read_only=True)

    class Meta:
        model = TimeOffRequest
        fields = '__all__'
        read_only_fields = ['decided_by']
        extra_kwargs = {'worker': {'required': False}}

    def validate(self, attrs):
        starts_on = attrs.get('starts_on', getattr(self.instance, 'starts_on', None))
        ends_on = attrs.get('ends_on', getattr(self.instance, 'ends_on', None))
        if starts_on and ends_on and ends_on < starts_on:
            raise serializers.ValidationError({'ends_on': 'Ende muss am oder nach dem Beginn liegen.'})
        return attrs


class ShiftSwapRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShiftSwapRequest
        fields = '__all__'


class ContractTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContractTemplate
        fields = '__all__'


class ContractSignatureSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContractSignature
        fields = ['id', 'role', 'signer_name', 'signature_hash', 'signed_at']


class ContractSerializer(serializers.ModelSerializer):
    template_name = serializers.CharField(source='template.name', read_only=True)
    template_slug = serializers.CharField(source='template.slug', read_only=True)
    worker_name = serializers.CharField(source='worker.user.get_full_name', read_only=True)
    client_name = serializers.CharField(source='client.name', read_only=True)
    signatures = ContractSignatureSerializer(many=True, read_only=True)

    class Meta:
        model = Contract
        fields = '__all__'
        read_only_fields = ['created_by', 'pdf', 'docx', 'sent_at', 'generated_at', 'signed_at', 'signature_hash', 'signature_ip', 'data_snapshot']


class DocumentSerializer(serializers.ModelSerializer):
    worker_name = serializers.CharField(source='worker.user.get_full_name', read_only=True)
    client_name = serializers.CharField(source='client.name', read_only=True)

    class Meta:
        model = Document
        fields = '__all__'
        read_only_fields = ['uploaded_by']


class PayrollStatementSerializer(serializers.ModelSerializer):
    worker_name = serializers.CharField(source='worker.user.get_full_name', read_only=True)

    class Meta:
        model = PayrollStatement
        fields = '__all__'

    def validate_document(self, uploaded):
        name = str(getattr(uploaded, 'name', '') or '').lower()
        content_type = str(getattr(uploaded, 'content_type', '') or '').lower()
        if not name.endswith('.pdf'):
            raise serializers.ValidationError('Lohnabrechnungen müssen als PDF hochgeladen werden.')
        if content_type and content_type not in {'application/pdf', 'application/x-pdf'}:
            raise serializers.ValidationError('Lohnabrechnungen müssen als PDF hochgeladen werden.')
        position = uploaded.tell() if hasattr(uploaded, 'tell') else None
        header = uploaded.read(5) if hasattr(uploaded, 'read') else b''
        if position is not None and hasattr(uploaded, 'seek'):
            uploaded.seek(position)
        if header != b'%PDF-':
            raise serializers.ValidationError('Die hochgeladene Datei ist keine gültige PDF-Datei.')
        return uploaded


class WorkerRatingSerializer(serializers.ModelSerializer):
    worker_name = serializers.CharField(source='worker.user.get_full_name', read_only=True)
    client_name = serializers.CharField(source='client.name', read_only=True)

    class Meta:
        model = WorkerRating
        fields = '__all__'
        read_only_fields = ['created_by']
        extra_kwargs = {'client': {'required': False}}


class MessageSerializer(serializers.ModelSerializer):
    sender_detail = UserSerializer(source='sender', read_only=True)

    class Meta:
        model = Message
        fields = '__all__'
        read_only_fields = ['sender', 'read_by']


class ConversationSerializer(serializers.ModelSerializer):
    messages = MessageSerializer(many=True, read_only=True)
    participants_detail = UserSerializer(source='participants', many=True, read_only=True)

    class Meta:
        model = Conversation
        fields = '__all__'


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = '__all__'
        read_only_fields = ['user']


class EmployeeMasterDataSerializer(serializers.ModelSerializer):
    worker_name = serializers.CharField(source='worker.user.get_full_name', read_only=True)
    employee_number = serializers.CharField(source='worker.employee_number', read_only=True)
    verified_by_name = serializers.CharField(source='verified_by.get_full_name', read_only=True)

    class Meta:
        model = EmployeeMasterData
        fields = '__all__'
        read_only_fields = ['worker', 'source_map', 'missing_fields', 'completeness', 'verified_at', 'verified_by']


class IntegrationSyncRunSerializer(serializers.ModelSerializer):
    triggered_by_name = serializers.CharField(source='triggered_by.get_full_name', read_only=True)

    class Meta:
        model = IntegrationSyncRun
        fields = '__all__'