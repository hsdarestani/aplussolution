from rest_framework import serializers
from .models import Shift
from .premium_approval_models import ShiftReleaseRequest
from .shift_slots import ShiftSlot
from .shift_rules import automatic_break_minutes, normalized_groups


class ShiftApiSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source='client.name', read_only=True)
    location_name = serializers.CharField(source='location.name', read_only=True)
    position_name = serializers.CharField(source='position.name', read_only=True)
    order_title = serializers.CharField(source='order.title', read_only=True)
    open_count = serializers.SerializerMethodField()
    filled_count = serializers.SerializerMethodField()
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

    def _list_instances(self):
        instances = getattr(getattr(self, 'parent', None), 'instance', None)
        if instances is None or isinstance(instances, Shift):
            return []
        try:
            return list(instances)
        except TypeError:
            return []

    def _schedule_slots(self, obj):
        """Load card slots once for a whole list instead of once per Shift.

        The admin Dienstplan can contain hundreds of imported/historical shifts.
        Counts, assigned_workers and slot_cards all use the same slot data. When
        serializing a list, build one in-memory slot map for every Shift in that
        response. Single-object/create callers retain one small safe fallback.
        """
        prefetched = getattr(obj, '_schedule_slots', None)
        if prefetched is not None:
            return prefetched

        bulk_map = getattr(self, '_bulk_schedule_slot_map', None)
        if bulk_map is None:
            rows = self._list_instances()
            shift_ids = [row.pk for row in rows if getattr(row, 'pk', None)]
            bulk_map = {shift_id: [] for shift_id in shift_ids}
            if shift_ids:
                slots = ShiftSlot.objects.filter(shift_id__in=shift_ids).select_related(
                    'worker__user'
                ).order_by('shift_id', 'created_at')
                for slot in slots:
                    bulk_map.setdefault(slot.shift_id, []).append(slot)
            self._bulk_schedule_slot_map = bulk_map

        if obj.pk in bulk_map:
            slots = bulk_map[obj.pk]
        else:
            slots = list(obj.slots.select_related('worker__user').order_by('created_at'))
        setattr(obj, '_schedule_slots', slots)
        return slots

    def get_open_count(self, obj):
        return sum(
            1 for slot in self._schedule_slots(obj)
            if slot.status == ShiftSlot.Status.OPEN and slot.worker_id is None
        )

    def get_filled_count(self, obj):
        return sum(
            1 for slot in self._schedule_slots(obj)
            if slot.status == ShiftSlot.Status.CLAIMED and slot.worker_id is not None
        )

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
            bulk_map = getattr(self, '_bulk_release_request_map', None)
            if bulk_map is None:
                rows = self._list_instances()
                shift_ids = [item.pk for item in rows if getattr(item, 'pk', None)]
                bulk_map = {}
                if shift_ids:
                    pending = ShiftReleaseRequest.objects.filter(
                        shift_id__in=shift_ids,
                        worker=worker,
                        status=ShiftReleaseRequest.Status.PENDING,
                    ).order_by('shift_id', '-created_at')
                    for item in pending:
                        bulk_map.setdefault(item.shift_id, item)
                self._bulk_release_request_map = bulk_map
            row = bulk_map.get(obj.pk)
            if row is None and not self._list_instances():
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
            'required_count', 'confirmation_required', 'schedule_groups', 'color_hue', 'open_count', 'filled_count',
            'assigned_workers', 'slot_cards', 'my_release_request',
        ]
