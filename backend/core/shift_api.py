from rest_framework import serializers
from .models import Shift
from .shift_slots import ShiftSlot
from .shift_rules import automatic_break_minutes, normalized_groups


class ShiftApiSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source='client.name', read_only=True)
    location_name = serializers.CharField(source='location.name', read_only=True)
    position_name = serializers.CharField(source='position.name', read_only=True)
    order_title = serializers.CharField(source='order.title', read_only=True)
    open_count = serializers.IntegerField(read_only=True)
    filled_count = serializers.IntegerField(read_only=True)
    assigned_workers = serializers.SerializerMethodField()
    slot_cards = serializers.SerializerMethodField()

    def _worker_payload(self, slot, include_avatar=False):
        request = self.context.get('request')
        worker = slot.worker
        if not worker:
            return None
        payload = {
            'id': str(worker.id),
            'slot_id': str(slot.id),
            'name': worker.user.get_full_name() or worker.user.email,
            'employee_number': worker.employee_number,
            'confirmation_status': slot.confirmation_status,
            'confirmation_label': slot.get_confirmation_status_display(),
            'confirmation_requested_at': slot.confirmation_requested_at,
            'confirmation_decided_at': slot.confirmation_decided_at,
            'is_me': bool(request and request.user.is_authenticated and worker.user_id == request.user.id),
        }
        if include_avatar:
            avatar = ''
            if worker.user.avatar:
                avatar = worker.user.avatar.url
                if request:
                    avatar = request.build_absolute_uri(avatar)
            payload['avatar'] = avatar
        return payload

    def get_assigned_workers(self, obj):
        slots = obj.slots.filter(
            status=ShiftSlot.Status.CLAIMED,
            worker__isnull=False,
        ).select_related('worker__user').order_by('created_at')
        return [self._worker_payload(slot, include_avatar=True) for slot in slots]

    def get_slot_cards(self, obj):
        """Expose capacity as first-class cards without duplicating Shift rows.

        A five-person demand therefore has five stable cards. Each card has its
        own slot id and worker/open state, while shared shift data remains on the
        parent Shift. Individual edits can split one card through the dedicated
        slot-edit endpoint; bulk edits keep changing the shared parent.
        """
        slots = obj.slots.exclude(status=ShiftSlot.Status.CANCELLED).select_related(
            'worker__user'
        ).order_by('created_at')
        return [
            {
                'id': str(slot.id),
                'status': slot.status,
                'is_open': slot.status == ShiftSlot.Status.OPEN and slot.worker_id is None,
                'worker': self._worker_payload(slot, include_avatar=False),
                'confirmation_status': slot.confirmation_status,
                'confirmation_label': slot.get_confirmation_status_display(),
                'source': slot.source,
            }
            for slot in slots
        ]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        starts_at = attrs.get('starts_at', getattr(self.instance, 'starts_at', None))
        ends_at = attrs.get('ends_at', getattr(self.instance, 'ends_at', None))
        if starts_at and ends_at:
            if ends_at <= starts_at:
                raise serializers.ValidationError({'ends_at': 'Das Ende muss nach dem Beginn liegen.'})
            attrs['break_minutes'] = automatic_break_minutes(starts_at, ends_at)
        if 'schedule_groups' in attrs:
            attrs['schedule_groups'] = normalized_groups(attrs.get('schedule_groups'))
        return attrs

    class Meta:
        model = Shift
        fields = [
            'id', 'order', 'order_title', 'client', 'client_name', 'location', 'location_name',
            'position', 'position_name', 'starts_at', 'ends_at', 'break_minutes', 'status', 'notes',
            'required_count', 'confirmation_required', 'schedule_groups', 'open_count', 'filled_count',
            'assigned_workers', 'slot_cards',
        ]
