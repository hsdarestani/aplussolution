from rest_framework import serializers
from .models import Shift

class ShiftApiSerializer(serializers.ModelSerializer):
    open_count = serializers.IntegerField(read_only=True)
    filled_count = serializers.IntegerField(read_only=True)
    class Meta:
        model = Shift
        fields = ['id','client','location','position','starts_at','ends_at','break_minutes','status','notes','required_count','open_count','filled_count']
