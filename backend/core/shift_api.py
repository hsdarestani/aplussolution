from rest_framework import serializers
from .models import Shift

class ShiftApiSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source='client.name', read_only=True)
    location_name = serializers.CharField(source='location.name', read_only=True)
    position_name = serializers.CharField(source='position.name', read_only=True)
    order_title = serializers.CharField(source='order.title', read_only=True)
    open_count = serializers.IntegerField(read_only=True)
    filled_count = serializers.IntegerField(read_only=True)
    class Meta:
        model = Shift
        fields = ['id','order','order_title','client','client_name','location','location_name','position','position_name','starts_at','ends_at','break_minutes','status','notes','required_count','open_count','filled_count']
