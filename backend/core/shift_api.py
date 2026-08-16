from rest_framework import serializers

from .models import Shift, User
from .scheduler_completion_models import SchedulerColorOverride
from .shift_slots import ShiftSlot


class ShiftApiSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source='client.name', read_only=True)
    location_name = serializers.CharField(source='location.name', read_only=True)
    location_timezone = serializers.CharField(source='location.timezone', read_only=True)
    position_name = serializers.CharField(source='position.name', read_only=True)
    order_title = serializers.CharField(source='order.title', read_only=True)
    open_count = serializers.IntegerField(read_only=True)
    filled_count = serializers.IntegerField(read_only=True)
    assignments = serializers.SerializerMethodField()
    required_tags = serializers.SerializerMethodField()
    position_color = serializers.CharField(source='position.color', read_only=True)
    shift_color = serializers.SerializerMethodField()
    location_color = serializers.SerializerMethodField()
    my_confirmation = serializers.SerializerMethodField()

    class Meta:
        model = Shift
        fields = [
            'id', 'order', 'order_title', 'client', 'client_name', 'location', 'location_name', 'location_timezone',
            'position', 'position_name', 'position_color', 'shift_color', 'location_color',
            'starts_at', 'ends_at', 'break_minutes', 'status', 'notes',
            'required_count', 'open_count', 'filled_count', 'assignments', 'required_tags', 'my_confirmation',
        ]

    def _confirmation_row(self, slot):
        try:
            confirmation = slot.confirmation
        except Exception:
            confirmation = None
        if not confirmation:
            return {'status': 'not_required', 'confirmed_at': None}
        return {
            'status': confirmation.status,
            'confirmed_at': confirmation.confirmed_at,
            'requested_at': confirmation.requested_at,
        }

    def get_assignments(self, obj):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated or user.role == User.Role.CLIENT:
            return []
        qs = obj.slots.filter(status=ShiftSlot.Status.CLAIMED, worker__isnull=False).select_related('worker__user', 'confirmation')
        if user.role == User.Role.WORKER:
            qs = qs.filter(worker__user=user)
        return [
            {
                'slot': str(slot.id),
                'worker': str(slot.worker_id),
                'worker_name': slot.worker.user.get_full_name() or slot.worker.user.email,
                'source': slot.source,
                'confirmation_status': self._confirmation_row(slot)['status'],
                'confirmed_at': self._confirmation_row(slot)['confirmed_at'],
            }
            for slot in qs
        ]

    def get_required_tags(self, obj):
        try:
            links = obj.position.required_tag_links.filter(required=True, tag__active=True).select_related('tag')
        except AttributeError:
            return []
        return [{'id': str(link.tag_id), 'name': link.tag.name} for link in links]

    def get_shift_color(self, obj):
        return SchedulerColorOverride.objects.filter(
            target_type=SchedulerColorOverride.Target.SHIFT, target_id=obj.id
        ).values_list('color', flat=True).first() or '#2457E6'

    def get_location_color(self, obj):
        return SchedulerColorOverride.objects.filter(
            target_type=SchedulerColorOverride.Target.LOCATION, target_id=obj.location_id
        ).values_list('color', flat=True).first() or '#667085'

    def get_my_confirmation(self, obj):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated or user.role != User.Role.WORKER:
            return None
        slot = obj.slots.filter(
            status=ShiftSlot.Status.CLAIMED, worker__user=user
        ).select_related('confirmation').first()
        if not slot:
            return None
        return {'slot': str(slot.id), **self._confirmation_row(slot)}
