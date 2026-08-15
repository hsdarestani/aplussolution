import pytest

from core.models import Conversation, Message, Notification


@pytest.mark.django_db
def test_legacy_conversation_message_keeps_conversation_title(admin_user, worker_user):
    conversation = Conversation.objects.create(title='Einsatz')
    conversation.participants.add(admin_user, worker_user)

    message = Message.objects.create(conversation=conversation, sender=admin_user, body='Hallo Anna')

    notification = Notification.objects.get(user=worker_user, kind=f'workchat-{message.id}')
    assert notification.title == 'Einsatz'
    assert notification.body == 'Hallo Anna'
