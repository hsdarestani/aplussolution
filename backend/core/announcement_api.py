import json

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Announcement, AnnouncementRecipient, Notification, User
from .permissions import IsAdminOrManager
from .services import audit


class AnnouncementSerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()
    recipient_count = serializers.SerializerMethodField()
    read_count = serializers.SerializerMethodField()
    recipients_detail = serializers.SerializerMethodField()
    is_read = serializers.SerializerMethodField()

    class Meta:
        model = Announcement
        fields = [
            'id', 'title', 'body', 'attachment', 'created_by', 'created_by_name',
            'sent_at', 'created_at', 'updated_at', 'recipient_count', 'read_count',
            'recipients_detail', 'is_read',
        ]
        read_only_fields = ['created_by', 'sent_at']

    def get_created_by_name(self, obj):
        if not obj.created_by:
            return 'Administration'
        return obj.created_by.get_full_name() or obj.created_by.email

    def get_recipient_count(self, obj):
        return obj.recipient_links.count()

    def get_read_count(self, obj):
        return obj.recipient_links.filter(read_at__isnull=False).count()

    def get_recipients_detail(self, obj):
        request = self.context.get('request')
        if not request or request.user.role not in {User.Role.ADMIN, User.Role.MANAGER}:
            return []
        return [
            {
                'id': str(link.user_id),
                'name': link.user.get_full_name() or link.user.email,
                'role': link.user.role,
                'read_at': link.read_at,
            }
            for link in obj.recipient_links.select_related('user').all()
        ]

    def get_is_read(self, obj):
        request = self.context.get('request')
        if not request or request.user.role in {User.Role.ADMIN, User.Role.MANAGER}:
            return False
        return obj.recipient_links.filter(user=request.user, read_at__isnull=False).exists()

    def validate_attachment(self, uploaded):
        if not uploaded:
            return uploaded
        if getattr(uploaded, 'size', 0) > 20 * 1024 * 1024:
            raise serializers.ValidationError('Der Anhang darf maximal 20 MB groß sein.')
        name = str(getattr(uploaded, 'name', '') or '').lower()
        allowed = ('.pdf', '.doc', '.docx', '.xls', '.xlsx', '.csv', '.txt', '.png', '.jpg', '.jpeg', '.webp')
        if not name.endswith(allowed):
            raise serializers.ValidationError('Erlaubt sind Bilder, PDF, Word, Excel/CSV und Textdateien.')
        return uploaded


class AnnouncementViewSet(viewsets.ModelViewSet):
    queryset = Announcement.objects.none()
    serializer_class = AnnouncementSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    http_method_names = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        qs = Announcement.objects.select_related('created_by').prefetch_related('recipient_links__user').all()
        if self.request.user.role in {User.Role.ADMIN, User.Role.MANAGER}:
            return qs
        return qs.filter(recipient_links__user=self.request.user).distinct()

    def get_permissions(self):
        if self.action == 'create':
            return [IsAdminOrManager()]
        return [IsAuthenticated()]

    @staticmethod
    def _truthy(value):
        return str(value or '').strip().lower() in {'1', 'true', 'yes', 'on'}

    def _recipient_ids(self, request):
        if hasattr(request.data, 'getlist'):
            values = request.data.getlist('recipient_ids')
        else:
            values = request.data.get('recipient_ids', [])
            if not isinstance(values, list):
                values = [values] if values else []
        if len(values) == 1 and isinstance(values[0], str) and values[0].strip().startswith('['):
            try:
                values = json.loads(values[0])
            except json.JSONDecodeError:
                pass
        return [str(value).strip() for value in values if str(value).strip()]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not str(serializer.validated_data.get('body', '') or '').strip() and not serializer.validated_data.get('attachment'):
            return Response({'detail': 'Bitte Text oder einen Anhang hinzufügen.'}, status=400)

        all_recipients = self._truthy(request.data.get('all_recipients'))
        if all_recipients:
            targets = User.objects.filter(
                is_active=True, role__in=[User.Role.WORKER, User.Role.CLIENT]
            ).exclude(email__iendswith='@sync.invalid').order_by('last_name', 'first_name', 'email')
        else:
            ids = self._recipient_ids(request)
            targets = User.objects.filter(
                id__in=ids, is_active=True, role__in=[User.Role.WORKER, User.Role.CLIENT]
            ).exclude(email__iendswith='@sync.invalid').order_by('last_name', 'first_name', 'email')

        targets = list(targets)
        if not targets:
            return Response({'detail': 'Bitte mindestens einen aktiven Empfänger auswählen.'}, status=400)

        with transaction.atomic():
            announcement = serializer.save(
                created_by=request.user,
                sent_at=timezone.now(),
                title=str(serializer.validated_data.get('title') or '').strip() or 'Mitteilung',
            )
            for recipient in targets:
                notification = Notification.objects.create(
                    user=recipient,
                    kind=f'announcement-{announcement.id}',
                    title=announcement.title,
                    body=(announcement.body or 'Neue Mitteilung mit Anhang')[:180],
                    action_url=f'/?view=messages&announcement={announcement.id}',
                )
                AnnouncementRecipient.objects.create(
                    announcement=announcement, user=recipient, notification=notification
                )
            audit(request, 'announcement.sent', announcement, {
                'recipient_count': len(targets),
                'all_recipients': all_recipients,
            })

        output = self.get_serializer(announcement)
        return Response(output.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def read(self, request, pk=None):
        announcement = self.get_object()
        if request.user.role in {User.Role.ADMIN, User.Role.MANAGER}:
            return Response(self.get_serializer(announcement).data)
        link = announcement.recipient_links.filter(user=request.user).select_related('notification').first()
        if not link:
            return Response({'detail': 'Mitteilung wurde nicht gefunden.'}, status=404)
        now = timezone.now()
        if not link.read_at:
            link.read_at = now
            link.save(update_fields=['read_at', 'updated_at'])
        if link.notification and not link.notification.read_at:
            link.notification.read_at = now
            link.notification.save(update_fields=['read_at', 'updated_at'])
        return Response(self.get_serializer(announcement).data)
