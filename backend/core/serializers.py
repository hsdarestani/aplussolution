from rest_framework import serializers
from .models import *
class UserSerializer(serializers.ModelSerializer):
    name=serializers.SerializerMethodField()
    class Meta: model=User; fields=['id','email','first_name','last_name','name','phone','role','avatar','is_onboarded']; read_only_fields=['role']
    def get_name(self,obj): return obj.get_full_name() or obj.email
class ClientCompanySerializer(serializers.ModelSerializer):
    class Meta: model=ClientCompany; fields='__all__'
class WorkerProfileSerializer(serializers.ModelSerializer):
    user_detail=UserSerializer(source='user',read_only=True)
    class Meta: model=WorkerProfile; fields='__all__'
class LocationSerializer(serializers.ModelSerializer):
    class Meta: model=Location; fields='__all__'
class PositionSerializer(serializers.ModelSerializer):
    class Meta: model=Position; fields='__all__'
class ClientOrderSerializer(serializers.ModelSerializer):
    client_name=serializers.CharField(source='client.name',read_only=True)
    class Meta: model=ClientOrder; fields='__all__'; read_only_fields=['created_by']
class AvailabilitySerializer(serializers.ModelSerializer):
    class Meta: model=Availability; fields='__all__'
class ShiftSerializer(serializers.ModelSerializer):
    worker_name=serializers.CharField(source='worker.user.get_full_name',read_only=True); client_name=serializers.CharField(source='client.name',read_only=True); location_name=serializers.CharField(source='location.name',read_only=True); position_name=serializers.CharField(source='position.name',read_only=True)
    class Meta: model=Shift; fields='__all__'
class TimeEntrySerializer(serializers.ModelSerializer):
    worked_minutes=serializers.IntegerField(read_only=True)
    class Meta: model=TimeEntry; fields='__all__'; read_only_fields=['approved_by']
class TimeOffRequestSerializer(serializers.ModelSerializer):
    class Meta: model=TimeOffRequest; fields='__all__'; read_only_fields=['decided_by']
class ShiftSwapRequestSerializer(serializers.ModelSerializer):
    class Meta: model=ShiftSwapRequest; fields='__all__'
class ContractTemplateSerializer(serializers.ModelSerializer):
    class Meta: model=ContractTemplate; fields='__all__'
class ContractSerializer(serializers.ModelSerializer):
    template_name=serializers.CharField(source='template.name',read_only=True); worker_name=serializers.CharField(source='worker.user.get_full_name',read_only=True); client_name=serializers.CharField(source='client.name',read_only=True)
    class Meta: model=Contract; fields='__all__'; read_only_fields=['created_by','pdf','sent_at','signed_at','signature_hash','signature_ip']
class DocumentSerializer(serializers.ModelSerializer):
    class Meta: model=Document; fields='__all__'; read_only_fields=['uploaded_by']
class PayrollStatementSerializer(serializers.ModelSerializer):
    class Meta: model=PayrollStatement; fields='__all__'
class WorkerRatingSerializer(serializers.ModelSerializer):
    class Meta: model=WorkerRating; fields='__all__'; read_only_fields=['created_by']
class MessageSerializer(serializers.ModelSerializer):
    sender_detail=UserSerializer(source='sender',read_only=True)
    class Meta: model=Message; fields='__all__'; read_only_fields=['sender','read_by']
class ConversationSerializer(serializers.ModelSerializer):
    messages=MessageSerializer(many=True,read_only=True)
    class Meta: model=Conversation; fields='__all__'
class NotificationSerializer(serializers.ModelSerializer):
    class Meta: model=Notification; fields='__all__'; read_only_fields=['user']
