from rest_framework import serializers

from .models import Shift, ShiftAssignment, User


class ShiftAssignmentSerializer(serializers.ModelSerializer):
    worker_name = serializers.CharField(source='worker.user.get_full_name', read_only=True)
    employee_number = serializers.CharField(source='worker.employee_number', read_only=True)

    class Meta:
        model = ShiftAssignment
        fields = ['id', 'worker', 'worker_name', 'employee_number', 'status', 'source', 'wiw_shift_id', 'claimed_at', 'released_at']
        read_only_fields = fields


class StaffingShiftSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source='client.name', read_only=True)
    location_name = serializers.CharField(source='location.name', read_only=True)
    location_address = serializers.CharField(source='location.address', read_only=True)
    position_name = serializers.CharField(source='position.name', read_only=True)
    order_title = serializers.CharField(source='order.title', read_only=True)
    assignments = ShiftAssignmentSerializer(many=True, read_only=True)
    assigned_count = serializers.SerializerMethodField()
    available_count = serializers.SerializerMethodField()
    my_assignment = serializers.SerializerMethodField()

    class Meta:
        model = Shift
        fields = [
            'id', 'order', 'order_title', 'client', 'client_name', 'location', 'location_name',
            'location_address', 'position', 'position_name', 'starts_at', 'ends_at', 'break_minutes',
            'status', 'is_open', 'notes', 'required_count', 'published_at', 'assignments',
            'assigned_count', 'available_count', 'my_assignment', 'created_at', 'updated_at',
        ]
        read_only_fields = ['is_open', 'published_at', 'assignments']

    def get_assigned_count(self, obj):
        return obj.assignments.filter(status=ShiftAssignment.Status.CLAIMED, worker__isnull=False).count()

    def get_available_count(self, obj):
        return obj.assignments.filter(status=ShiftAssignment.Status.OPEN, worker__isnull=True).count()

    def get_my_assignment(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated or request.user.role != User.Role.WORKER:
            return None
        assignment = obj.assignments.filter(worker=request.user.worker_profile, status=ShiftAssignment.Status.CLAIMED).first()
        return ShiftAssignmentSerializer(assignment).data if assignment else None

    def validate(self, attrs):
        starts = attrs.get('starts_at', getattr(self.instance, 'starts_at', None))
        ends = attrs.get('ends_at', getattr(self.instance, 'ends_at', None))
        if starts and ends and ends <= starts:
            raise serializers.ValidationError({'ends_at': 'Das Ende muss nach dem Beginn liegen.'})
        required = attrs.get('required_count', getattr(self.instance, 'required_count', 1))
        if int(required or 0) < 1:
            raise serializers.ValidationError({'required_count': 'Mindestens eine Person wird benötigt.'})
        return attrs
