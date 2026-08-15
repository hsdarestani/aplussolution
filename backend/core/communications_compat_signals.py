from django.db.models.signals import post_save
from django.dispatch import receiver

from .communications_models import NotificationPreference
from .communications_service import active_members, notify
from .models import Message


@receiver(post_save, sender=Message)
def preserve_conversation_notification_title(sender, instance, created=False, **kwargs):
    """Keep the pre-V6 notification contract while using the V6 delivery pipeline.

    The central ``post_message`` service uses the same dedupe key afterwards, so
    this receiver becomes the single notification for each recipient rather than
    creating a duplicate. Legacy conversations can predate V6 membership rows,
    therefore their historical ``participants`` relation remains the fallback.
    """
    if not created or not instance.sender_id:
        return

    conversation = instance.conversation
    sender_user = instance.sender
    title = conversation.title or sender_user.get_full_name() or sender_user.email
    recipients = active_members(conversation).exclude(pk=sender_user.pk)
    if not recipients.exists():
        recipients = conversation.participants.filter(is_active=True).exclude(pk=sender_user.pk)

    for recipient in recipients:
        membership = conversation.channel_memberships.filter(user=recipient, left_at__isnull=True).first()
        if membership and (membership.muted or not membership.notifications_enabled):
            continue
        notify(
            recipient,
            category=NotificationPreference.Category.WORKCHAT,
            kind=f'workchat-{instance.id}',
            title=title,
            body=instance.body or 'Bild',
            action_url=f'/messages?channel={conversation.id}',
            data={'conversation_id': str(conversation.id), 'message_id': str(instance.id)},
            dedupe_key=f'workchat-{instance.id}-{recipient.id}',
        )
