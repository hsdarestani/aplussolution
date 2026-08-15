from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from .communications_models import (
    CommunicationSettings,
    ConversationChannel,
    ConversationMembership,
    DeviceRegistration,
    MessageState,
    NotificationPreference,
    NotificationState,
)
from .communications_serializers import (
    CommunicationSettingsSerializer,
    DeviceRegistrationSerializer,
    NotificationPreferenceSerializer,
)
from .communications_service import (
    active_members,
    can_manage_channel,
    can_post,
    candidate_users,
    create_channel,
    ensure_notification_state,
    ensure_preferences,
    ensure_workplace_channel,
    is_active_member,
    post_message,
)
from .models import Conversation, Message, Notification, User
from .services import audit
from .workplace_access import has_capability


def _user_row(user):
    return {
        'id': str(user.id),
        'name': user.get_full_name() or user.email,
        'email': user.email,
        'role': user.role,
        'avatar': user.avatar.url if getattr(user, 'avatar', None) else None,
    }


def _ensure_channel_metadata(conversation, created_by=None):
    channel, _ = ConversationChannel.objects.get_or_create(
        conversation=conversation,
        defaults={
            'channel_type': ConversationChannel.ChannelType.GROUP,
            'created_by': created_by,
        },
    )
    for user in conversation.participants.filter(is_active=True):
        ConversationMembership.objects.get_or_create(conversation=conversation, user=user)
    return channel


def _message_row(message, viewer):
    state = getattr(message, 'message_state', None)
    deleted = bool(state and state.deleted_at)
    return {
        'id': str(message.id),
        'conversation': str(message.conversation_id),
        'sender': str(message.sender_id) if message.sender_id else None,
        'sender_detail': _user_row(message.sender) if message.sender_id else None,
        'body': 'Nachricht gelöscht' if deleted else message.body,
        'attachment': None if deleted or not message.attachment else message.attachment.url,
        'created_at': message.created_at,
        'edited_at': state.edited_at if state else None,
        'deleted_at': state.deleted_at if state else None,
        'mine': message.sender_id == viewer.id,
        'read_count': message.read_by.exclude(pk=message.sender_id).count(),
    }


def _channel_title(conversation, user, channel):
    if conversation.title:
        return conversation.title
    if channel.channel_type == ConversationChannel.ChannelType.DIRECT:
        other = active_members(conversation).exclude(pk=user.pk).first()
        if other:
            return other.get_full_name() or other.email
    return 'Unterhaltung'


def _channel_row(conversation, user, *, include_messages=True):
    channel = _ensure_channel_metadata(conversation)
    membership = ConversationMembership.objects.filter(conversation=conversation, user=user, left_at__isnull=True).first()
    last_read_at = membership.last_read_at if membership else None
    unread = conversation.messages.exclude(sender=user)
    if last_read_at:
        unread = unread.filter(created_at__gt=last_read_at)
    unread_count = unread.exclude(message_state__deleted_at__isnull=False).count()
    members = list(active_members(conversation).order_by('first_name', 'last_name', 'email'))
    result = {
        'id': str(conversation.id),
        'title': _channel_title(conversation, user, channel),
        'channel_type': channel.channel_type,
        'is_announcement': conversation.is_announcement,
        'pinned': channel.pinned,
        'active': channel.active,
        'participants': [str(item.id) for item in members],
        'participants_detail': [_user_row(item) for item in members],
        'unread_count': unread_count,
        'can_post': can_post(conversation, user),
        'can_manage': can_manage_channel(conversation, user),
        'can_leave': channel.channel_type != ConversationChannel.ChannelType.WORKPLACE,
        'muted': bool(membership and membership.muted),
        'notifications_enabled': bool(not membership or membership.notifications_enabled),
        'updated_at': conversation.updated_at,
    }
    if include_messages:
        messages = conversation.messages.select_related('sender', 'message_state').prefetch_related('read_by').order_by('created_at')
        result['messages'] = [_message_row(item, user) for item in messages]
    return result


def _notification_row(notification):
    state = ensure_notification_state(notification)
    return {
        'id': str(notification.id),
        'title': notification.title,
        'body': notification.body,
        'kind': notification.kind,
        'action_url': notification.action_url,
        'category': state.category,
        'priority': state.priority,
        'read_at': state.read_at,
        'is_read': bool(state.read_at),
        'data': state.data,
        'created_at': notification.created_at,
    }


class NotificationCenterViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    queryset = Notification.objects.none()

    def get_queryset(self):
        ensure_preferences(self.request.user)
        # Backward compatibility for rows created before V6 state existed.
        missing = Notification.objects.filter(user=self.request.user, delivery_state__isnull=True)
        for item in missing[:500]:
            ensure_notification_state(item)
        enabled_categories = NotificationPreference.objects.filter(
            user=self.request.user, in_app_enabled=True
        ).values_list('category', flat=True)
        return Notification.objects.filter(
            user=self.request.user,
            delivery_state__deleted_at__isnull=True,
            delivery_state__category__in=enabled_categories,
        ).select_related('delivery_state').order_by('-created_at')

    def list(self, request, *args, **kwargs):
        qs = self.get_queryset()
        page = self.paginate_queryset(qs)
        rows = [_notification_row(item) for item in (page if page is not None else qs)]
        if page is not None:
            return self.get_paginated_response(rows)
        return Response(rows)

    def retrieve(self, request, *args, **kwargs):
        return Response(_notification_row(self.get_object()))

    def destroy(self, request, *args, **kwargs):
        notification = self.get_object()
        state = ensure_notification_state(notification)
        state.deleted_at = timezone.now()
        state.save(update_fields=['deleted_at', 'updated_at'])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        notification = self.get_object()
        state = ensure_notification_state(notification)
        state.read_at = state.read_at or timezone.now()
        state.save(update_fields=['read_at', 'updated_at'])
        return Response(_notification_row(notification))

    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        now = timezone.now()
        updated = NotificationState.objects.filter(
            notification__user=request.user,
            read_at__isnull=True,
            deleted_at__isnull=True,
        ).update(read_at=now, updated_at=now)
        return Response({'updated': updated})

    @action(detail=False, methods=['get'])
    def unread_count(self, request):
        ensure_preferences(request.user)
        enabled_categories = NotificationPreference.objects.filter(
            user=request.user, in_app_enabled=True
        ).values_list('category', flat=True)
        count = NotificationState.objects.filter(
            notification__user=request.user,
            category__in=enabled_categories,
            read_at__isnull=True,
            deleted_at__isnull=True,
        ).count()
        return Response({'unread': count})


class NotificationPreferenceViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = NotificationPreferenceSerializer
    pagination_class = None

    def get_queryset(self):
        ensure_preferences(self.request.user)
        return NotificationPreference.objects.filter(user=self.request.user).order_by('category')

    @action(detail=True, methods=['patch'])
    def configure(self, request, pk=None):
        pref = self.get_object()
        serializer = self.get_serializer(pref, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @action(detail=False, methods=['patch'])
    def bulk(self, request):
        rows = request.data if isinstance(request.data, list) else request.data.get('preferences', [])
        by_category = {item.category: item for item in self.get_queryset()}
        errors = []
        for row in rows:
            category = row.get('category')
            pref = by_category.get(category)
            if not pref:
                errors.append({'category': category, 'detail': 'Unbekannte Kategorie.'})
                continue
            serializer = self.get_serializer(pref, data=row, partial=True)
            if not serializer.is_valid():
                errors.append({'category': category, 'detail': serializer.errors})
                continue
            serializer.save()
        if errors:
            return Response({'errors': errors}, status=400)
        return Response(self.get_serializer(self.get_queryset(), many=True).data)


class DeviceRegistrationViewSet(viewsets.ModelViewSet):
    serializer_class = DeviceRegistrationSerializer
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_queryset(self):
        return DeviceRegistration.objects.filter(user=self.request.user).order_by('-last_seen_at')

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        token = serializer.validated_data['token']
        device, _ = DeviceRegistration.objects.update_or_create(
            token=token,
            defaults={
                'user': request.user,
                'platform': serializer.validated_data['platform'],
                'device_name': serializer.validated_data.get('device_name', ''),
                'app_version': serializer.validated_data.get('app_version', ''),
                'active': True,
                'last_seen_at': timezone.now(),
            },
        )
        return Response(self.get_serializer(device).data, status=201)

    @action(detail=False, methods=['post'])
    def deactivate_token(self, request):
        token = str(request.data.get('token') or '')
        updated = self.get_queryset().filter(token=token).update(active=False, updated_at=timezone.now())
        return Response({'updated': updated})


class WorkChatChannelViewSet(viewsets.ViewSet):
    def _queryset(self):
        cfg = CommunicationSettings.load()
        if not cfg.workchat_enabled:
            return Conversation.objects.none()
        if self.request.user.role != User.Role.CLIENT:
            ensure_workplace_channel()
        # Upgrade legacy conversations lazily before querying memberships.
        for conversation in Conversation.objects.filter(participants=self.request.user, channel__isnull=True)[:100]:
            _ensure_channel_metadata(conversation)
        return Conversation.objects.filter(
            channel_memberships__user=self.request.user,
            channel_memberships__left_at__isnull=True,
            channel__active=True,
        ).select_related('channel').distinct().order_by('-channel__pinned', '-updated_at')

    def _get(self, pk):
        conversation = self._queryset().filter(pk=pk).first()
        if not conversation:
            raise PermissionDenied('Dieser Kanal ist für dich nicht verfügbar.')
        return conversation

    def list(self, request):
        return Response([_channel_row(item, request.user) for item in self._queryset()])

    def retrieve(self, request, pk=None):
        return Response(_channel_row(self._get(pk), request.user))

    def create(self, request):
        participants = request.data.get('participants') or request.data.get('participant_ids') or []
        try:
            conversation = create_channel(request.user, participants, request.data.get('title', ''))
        except PermissionError as exc:
            raise PermissionDenied(str(exc))
        except ValueError as exc:
            raise ValidationError(str(exc))
        audit(request, 'workchat.channel_created', conversation)
        return Response(_channel_row(conversation, request.user), status=201)

    @action(detail=True, methods=['post'])
    def post_message(self, request, pk=None):
        conversation = self._get(pk)
        try:
            message = post_message(
                conversation,
                request.user,
                request.data.get('body', ''),
                request.FILES.get('attachment') or request.FILES.get('image'),
            )
        except PermissionError as exc:
            raise PermissionDenied(str(exc))
        except ValueError as exc:
            raise ValidationError(str(exc))
        audit(request, 'workchat.message_sent', conversation, {'message': str(message.id)})
        conversation.save(update_fields=['updated_at'])
        return Response(_message_row(message, request.user), status=201)

    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        conversation = self._get(pk)
        now = timezone.now()
        membership = ConversationMembership.objects.get(conversation=conversation, user=request.user, left_at__isnull=True)
        membership.last_read_at = now
        membership.save(update_fields=['last_read_at', 'updated_at'])
        unread = conversation.messages.exclude(sender=request.user).filter(created_at__lte=now)
        for message in unread:
            message.read_by.add(request.user)
        return Response({'read_at': now})

    @action(detail=True, methods=['patch'])
    def rename(self, request, pk=None):
        conversation = self._get(pk)
        if not can_manage_channel(conversation, request.user):
            raise PermissionDenied('Du darfst diesen Kanal nicht umbenennen.')
        if conversation.channel.channel_type == ConversationChannel.ChannelType.WORKPLACE:
            raise ValidationError('Der Betriebskanal kann nicht umbenannt werden.')
        title = str(request.data.get('title') or '').strip()
        if not title:
            raise ValidationError('Titel fehlt.')
        conversation.title = title[:200]
        conversation.save(update_fields=['title', 'updated_at'])
        return Response(_channel_row(conversation, request.user))

    @action(detail=True, methods=['post'])
    def mute(self, request, pk=None):
        conversation = self._get(pk)
        membership = ConversationMembership.objects.get(conversation=conversation, user=request.user, left_at__isnull=True)
        membership.muted = bool(request.data.get('muted', True))
        if 'notifications_enabled' in request.data:
            membership.notifications_enabled = bool(request.data['notifications_enabled'])
        membership.save(update_fields=['muted', 'notifications_enabled', 'updated_at'])
        return Response({'muted': membership.muted, 'notifications_enabled': membership.notifications_enabled})

    @action(detail=True, methods=['post'])
    def manage_members(self, request, pk=None):
        conversation = self._get(pk)
        if not can_manage_channel(conversation, request.user):
            raise PermissionDenied('Du darfst Mitglieder dieses Kanals nicht verwalten.')
        if conversation.channel.channel_type == ConversationChannel.ChannelType.WORKPLACE:
            raise ValidationError('Mitglieder des Betriebskanals werden automatisch synchronisiert.')
        add_ids = {str(item) for item in request.data.get('add', []) if item}
        remove_ids = {str(item) for item in request.data.get('remove', []) if item}
        if add_ids:
            allowed = list(candidate_users(request.user).filter(pk__in=add_ids))
            if len(allowed) != len(add_ids):
                raise PermissionDenied('Mindestens ein Benutzer liegt außerhalb deines Kommunikationsbereichs.')
            for user in allowed:
                conversation.participants.add(user)
                membership, _ = ConversationMembership.objects.get_or_create(conversation=conversation, user=user)
                membership.left_at = None
                membership.save(update_fields=['left_at', 'updated_at'])
        if remove_ids:
            if str(request.user.id) in remove_ids:
                raise ValidationError('Nutze „Kanal verlassen“, um dich selbst zu entfernen.')
            memberships = ConversationMembership.objects.filter(conversation=conversation, user_id__in=remove_ids, left_at__isnull=True)
            now = timezone.now()
            removed_users = list(memberships.values_list('user_id', flat=True))
            memberships.update(left_at=now, updated_at=now)
            conversation.participants.remove(*removed_users)
        return Response(_channel_row(conversation, request.user))

    @action(detail=True, methods=['post'])
    def leave(self, request, pk=None):
        conversation = self._get(pk)
        if conversation.channel.channel_type == ConversationChannel.ChannelType.WORKPLACE:
            raise ValidationError('Der Betriebskanal kann nicht verlassen werden.')
        membership = ConversationMembership.objects.get(conversation=conversation, user=request.user, left_at__isnull=True)
        membership.left_at = timezone.now()
        membership.save(update_fields=['left_at', 'updated_at'])
        conversation.participants.remove(request.user)
        audit(request, 'workchat.channel_left', conversation)
        return Response(status=204)


@api_view(['GET'])
def communication_candidates(request):
    return Response([_user_row(item) for item in candidate_users(request.user).order_by('first_name', 'last_name', 'email')])


@api_view(['GET', 'PATCH'])
def communication_settings(request):
    cfg = CommunicationSettings.load()
    can_manage = request.user.role == User.Role.ADMIN or has_capability(request.user, 'workplace.manage')
    if request.method == 'GET':
        return Response({**CommunicationSettingsSerializer(cfg).data, 'can_manage': can_manage})
    if not can_manage:
        raise PermissionDenied('Nur berechtigte Administratoren dürfen WorkChat global konfigurieren.')
    disabling = cfg.workchat_enabled and request.data.get('workchat_enabled') is False
    if disabling and request.data.get('confirm_delete_history') is not True:
        return Response(
            {'detail': 'Das Deaktivieren von WorkChat löscht den gesamten WorkChat-Verlauf. Bitte ausdrücklich bestätigen.', 'requires_confirmation': True},
            status=409,
        )
    serializer = CommunicationSettingsSerializer(cfg, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    with transaction.atomic():
        serializer.save()
        if disabling:
            Conversation.objects.filter(channel__isnull=False).delete()
    audit(request, 'workchat.settings_updated', cfg, {'workchat_enabled': cfg.workchat_enabled})
    return Response({**serializer.data, 'can_manage': can_manage})


@api_view(['GET'])
def communications_snapshot(request):
    ensure_preferences(request.user)
    cfg = CommunicationSettings.load()
    unread_notifications = NotificationState.objects.filter(
        notification__user=request.user, read_at__isnull=True, deleted_at__isnull=True
    ).count()
    unread_chat = 0
    if cfg.workchat_enabled:
        if request.user.role != User.Role.CLIENT:
            ensure_workplace_channel()
        for membership in ConversationMembership.objects.filter(user=request.user, left_at__isnull=True).select_related('conversation'):
            qs = membership.conversation.messages.exclude(sender=request.user)
            if membership.last_read_at:
                qs = qs.filter(created_at__gt=membership.last_read_at)
            unread_chat += qs.exclude(message_state__deleted_at__isnull=False).count()
    return Response({
        'settings': CommunicationSettingsSerializer(cfg).data,
        'unread_notifications': unread_notifications,
        'unread_chat': unread_chat,
        'devices': DeviceRegistration.objects.filter(user=request.user, active=True).count(),
    })


@api_view(['POST'])
def notifications_read_all(request):
    now = timezone.now()
    updated = NotificationState.objects.filter(
        notification__user=request.user, read_at__isnull=True, deleted_at__isnull=True
    ).update(read_at=now, updated_at=now)
    return Response({'updated': updated})


@api_view(['DELETE'])
def delete_chat_message(request, pk):
    message = Message.objects.select_related('conversation', 'sender').filter(pk=pk).first()
    if not message or not is_active_member(message.conversation, request.user):
        raise PermissionDenied('Nachricht nicht verfügbar.')
    if message.sender_id != request.user.id:
        raise PermissionDenied('Nur eigene Nachrichten können gelöscht werden.')
    state, _ = MessageState.objects.get_or_create(message=message)
    state.deleted_at = timezone.now()
    state.deleted_by = request.user
    state.save(update_fields=['deleted_at', 'deleted_by', 'updated_at'])
    audit(request, 'workchat.message_deleted', message.conversation, {'message': str(message.id)})
    return Response(status=204)
