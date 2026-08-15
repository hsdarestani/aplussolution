from rest_framework import serializers

from .models import Shift, User
from .shift_slots import ShiftSlot


class ShiftApiSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source='client.name', read_only=True)
    location_name = serializers.CharField(source='location.name', read_only=True)
    position_name = serializers.CharField(source='position.name', read_only=True)
    order_title = serializers.CharField(source='order.title', read_only=True)
    open_count = serializers.IntegerField(read_only=True)
    filled_count = serializers.IntegerField(read_only=True)
    assignments = serializers.SerializerMethodField()
    required_tags = serializers.SerializerMethodField()

    class Meta:
        model = Shift
        fields = [
            'id', 'order', 'order_title', 'client', 'client_name', 'location', 'location_name',
            'position', 'position_name', 'starts_at', 'ends_at', 'break_minutes', 'status', 'notes',
            'required_count', 'open_count', 'filled_count', 'assignments', 'required_tags',
        ]

    def get_assignments(self, obj):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated or user.role == User.Role.CLIENT:
            return []
        qs = obj.slots.filter(status=ShiftSlot.Status.CLAIMED, worker__isnull=False).select_related('worker__user')
        if user.role == User.Role.WORKER:
            qs = qs.filter(worker__user=user)
        return [
            {
                'slot': str(slot.id),
                'worker': str(slot.worker_id),
                'worker_name': slot.worker.user.get_full_name() or slot.worker.user.email,
                'source': slot.source,
            }
            for slot in qs
        ]

    def get_required_tags(self, obj):
        try:
            links = obj.position.required_tag_links.filter(required=True, tag__active=True).select_related('tag')
        except AttributeError:
            return []
        return [{'id': str(link.tag_id), 'name': link.tag.name} for link in links]
