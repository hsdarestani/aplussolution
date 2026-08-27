from rest_framework import serializers
from .models import Shift
from .shift_slots import ShiftSlot


class ShiftApiSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source='client.name', read_only=True)
    location_name = serializers.CharField(source='location.name', read_only=True)
    position_name = serializers.CharField(source='position.name', read_only=True)
    order_title = serializers.CharField(source='order.title', read_only=True)
    open_count = serializers.IntegerField(read_only=True)
    filled_count = serializers.IntegerField(read_only=True)
    assigned_workers = serializers.SerializerMethodField()

    def get_assigned_workers(self, obj):
        request = self.context.get('request')
        slots = obj.slots.filter(
            status=ShiftSlot.Status.CLAIMED,
            worker__isnull=False,
        ).select_related('worker__user').order_by('created_at')
        workers = []
        for slot in slots:
            avatar = ''
            if slot.worker.user.avatar:
                avatar = slot.worker.user.avatar.url
                if request:
                    avatar = request.build_absolute_uri(avatar)
            workers.append(
                {
                    'id': str(slot.worker_id),
                    'name': slot.worker.user.get_full_name() or slot.worker.user.email,
                    'employee_number': slot.worker.employee_number,
                    'avatar': avatar,
                }
            )
        return workers

    class Meta:
        model = Shift
        fields = [
            'id', 'order', 'order_title', 'client', 'client_name', 'location', 'location_name',
            'position', 'position_name', 'starts_at', 'ends_at', 'break_minutes', 'status', 'notes',
            'required_count', 'open_count', 'filled_count', 'assigned_workers',
        ]
