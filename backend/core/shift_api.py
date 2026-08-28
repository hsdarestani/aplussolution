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
    my_release_request = serializers.SerializerMethodField()

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

    def _schedule_slots(self, obj):
        """Reuse the bulk-prefetched slot list when the shift view provided it.

        Schedule pages can contain hundreds of shifts. Querying claimed slots and
        card slots separately for every Shift created an avoidable 2N query fanout
        and made the admin Dienstplan feel much slower than WIW. The view now
        prefetches one ordered slot list for all shifts; serializers filter that
        list in memory. Callers that do not use the optimized queryset keep the
        old safe fallback.
        """
        prefetched = getattr(obj, '_schedule_slots', None)
        if prefetched is not None:
            return prefetched
        return list(obj.slots.select_related('worker__user').order_by('created_at'))

    def get_assigned_workers(self, obj):
        slots = [
            slot for slot in self._schedule_slots(obj)
            if slot.status == ShiftSlot.Status.CLAIMED and slot.worker_id is not None
        ]
        return [self._worker_payload(slot, include_avatar=True) for slot in slots]

    def get_slot_cards(self, obj):
        """Expose capacity as first-class cards without duplicating Shift rows.

        A five-person demand therefore has five stable cards. Each card has its
        own slot id and worker/open state, while shared shift data remains on the
        parent Shift. Individual edits can split one card through the dedicated
        slot-edit endpoint; bulk edits keep changing the shared parent.
        """
        slots = [slot for slot in self._schedule_slots(obj) if slot.status != ShiftSlot.Status.CANCELLED]
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

    def get_my_release_request(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated or getattr(request.user, 'role', None) != 'worker':
            return None
        try:
            worker = request.user.worker_profile
        except Exception:
            return None

        prefetched = getattr(obj, '_pending_release_requests', None)
        if prefetched is not None:
            row = next((item for item in prefetched if item.worker_id == worker.id), None)
        else:
            row = obj.release_requests.filter(worker=worker, status='pending').order_by('-created_at').first()
        if not row:
            return None
        return {
            'id': str(row.id),
            'status': row.status,
            'created_at': row.created_at,
        }

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
            'assigned_workers', 'slot_cards', 'my_release_request',
        ]
