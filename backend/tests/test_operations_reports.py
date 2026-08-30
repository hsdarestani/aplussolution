from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from core.models import Conversation, Document, Message, Notification, Shift, TimeEntry, WorkerRating


@pytest.mark.django_db
def test_operations_overview_and_read_all(auth_admin, admin_user):
    Notification.objects.create(user=admin_user, title='A', body='B')
    response = auth_admin.get('/api/operations/')
    assert response.status_code == 200
    assert response.data['unread_notifications'] == 1
    response = auth_admin.post('/api/operations/notifications/read-all/', {}, format='json')
    assert response.data['updated'] == 1


@pytest.mark.django_db
def test_reports_return_semicolon_csv(auth_admin, worker_user, shift):
    TimeEntry.objects.create(worker=worker_user.worker_profile, shift=shift, clock_in=timezone.now()-timedelta(hours=3), clock_out=timezone.now(), approved=True)
    month = timezone.localdate().strftime('%Y-%m')
    response = auth_admin.get(f'/api/reports/timesheets.csv?month={month}')
    assert response.status_code == 200
    assert response['Content-Type'].startswith('text/csv')
    body = response.content.decode('utf-8-sig')
    assert 'Personalnummer;Mitarbeiter' in body
    assert 'MA-001' in body
    response = auth_admin.get(f'/api/reports/payroll-estimate.csv?month={month}')
    assert response.status_code == 200
    assert 'Schätzung' in response.content.decode('utf-8-sig')


@pytest.mark.django_db
def test_message_creates_notification(api_client, admin_user, worker_user):
    conversation = Conversation.objects.create(title='Einsatz')
    conversation.participants.add(admin_user, worker_user)
    api_client.force_authenticate(admin_user)
    response = api_client.post(f'/api/conversations/{conversation.id}/post_message/', {'body': 'Hallo Anna'}, format='json')
    assert response.status_code == 201
    assert Message.objects.count() == 1
    notification = Notification.objects.get(user=worker_user, kind__startswith='message-')
    assert notification.title == 'Neue Nachricht von Admin'
    assert notification.body == 'Hallo Anna'


@pytest.mark.django_db
def test_client_rating_updates_ranking(auth_client, client_user, worker_user, company, shift):
    now = timezone.now()
    shift.starts_at = now - timedelta(hours=3)
    shift.ends_at = now - timedelta(hours=1)
    shift.status = Shift.Status.COMPLETED
    shift.save(update_fields=['starts_at', 'ends_at', 'status', 'updated_at'])

    response = auth_client.post('/api/ratings/', {
        'worker': str(worker_user.worker_profile.id),
        'shift': str(shift.id),
        'score': 4,
        'punctuality': 5,
        'quality': 4,
        'teamwork': 5,
    }, format='json')
    assert response.status_code == 201
    worker_user.worker_profile.refresh_from_db()
    assert worker_user.worker_profile.ranking_points == 40


@pytest.mark.django_db
def test_worker_document_upload_is_forced_to_own_folder(auth_worker, worker_user):
    upload = SimpleUploadedFile('certificate.txt', b'content', content_type='text/plain')
    response = auth_worker.post('/api/documents/', {'title': 'Nachweis', 'file': upload, 'folder': 'certificates', 'visibility': 'worker'}, format='multipart')
    assert response.status_code == 201
    document = Document.objects.get()
    assert document.worker == worker_user.worker_profile