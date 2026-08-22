import pytest

from core.models import Conversation, User


@pytest.mark.django_db
def test_worker_recipient_picker_exposes_disposition_only_without_contact_data(auth_worker, admin_user, manager_user, client_user, second_worker):
    response = auth_worker.get('/api/portal/message-recipients/')

    assert response.status_code == 200
    roles = {row['role'] for row in response.data}
    ids = {row['id'] for row in response.data}
    assert roles <= {'admin', 'manager'}
    assert str(admin_user.id) in ids
    assert str(manager_user.id) in ids
    assert str(client_user.id) not in ids
    assert str(second_worker.user_id) not in ids

    payload = str(response.data).lower()
    assert 'email' not in payload
    assert 'phone' not in payload


@pytest.mark.django_db
def test_worker_can_start_conversation_with_manager(auth_worker, worker_user, manager_user):
    response = auth_worker.post(
        '/api/conversations/',
        {'title': 'Frage an Disposition', 'participants': [str(manager_user.id)]},
        format='json',
    )

    assert response.status_code == 201
    conversation = Conversation.objects.get(pk=response.data['id'])
    assert set(conversation.participants.values_list('id', flat=True)) == {worker_user.id, manager_user.id}


@pytest.mark.django_db
def test_worker_cannot_start_conversation_with_another_worker(auth_worker, second_worker):
    response = auth_worker.post(
        '/api/conversations/',
        {'title': 'Nicht erlaubt', 'participants': [str(second_worker.user_id)]},
        format='json',
    )

    assert response.status_code == 400
    assert Conversation.objects.count() == 0


@pytest.mark.django_db
def test_worker_cannot_start_empty_conversation(auth_worker):
    response = auth_worker.post('/api/conversations/', {'title': 'Leer', 'participants': []}, format='json')
    assert response.status_code == 400
    assert Conversation.objects.count() == 0


@pytest.mark.django_db
def test_worker_cannot_read_conversation_they_do_not_participate_in(auth_worker, admin_user, manager_user):
    conversation = Conversation.objects.create(title='Intern')
    conversation.participants.add(admin_user, manager_user)

    response = auth_worker.get(f'/api/conversations/{conversation.id}/')
    assert response.status_code == 404
