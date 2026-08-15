from rest_framework import serializers

from .communications_models import CommunicationSettings, ConversationMembership, DeviceRegistration, NotificationPreference
from .models import User


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    category_label = serializers.CharField(source='get_category_display', read_only=True)

    class Meta:
        model = NotificationPreference
        fields = ['id', 'category', 'category_label', 'in_app_enabled', 'push_enabled', 'email_enabled', 'sms_enabled', 'reminder_minutes', 'dnd_start', 'dnd_end']
        read_only_fields = ['id', 'category', 'category_label']

    def validate_reminder_minutes(self, value):
        if value < 1 or value > 1440:
            raise serializers.ValidationError('Schichterinnerungen müssen zwischen 1 Minute und 24 Stunden liegen.')
        return value


class DeviceRegistrationSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeviceRegistration
        fields = ['id', 'token', 'platform', 'device_name', 'app_version', 'active', 'last_seen_at']
        read_only_fields = ['id', 'last_seen_at']
        # A native token identifies the device installation, not the account.
        # The view intentionally transfers an existing token to the currently
        # authenticated user on login/account switch.
        extra_kwargs = {'token': {'validators': []}}


class CommunicationSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = CommunicationSettings
        fields = ['id', 'workchat_enabled', 'employees_can_post_workplace', 'users_can_create_channels', 'images_enabled', 'sms_fallback_enabled']
        read_only_fields = ['id']


class ChatUserSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'name', 'email', 'role', 'avatar']

    def get_name(self, obj):
        return obj.get_full_name() or obj.email


class ConversationMembershipSerializer(serializers.ModelSerializer):
    user_detail = ChatUserSerializer(source='user', read_only=True)

    class Meta:
        model = ConversationMembership
        fields = ['id', 'user', 'user_detail', 'role', 'notifications_enabled', 'muted', 'joined_at', 'left_at', 'last_read_at']
