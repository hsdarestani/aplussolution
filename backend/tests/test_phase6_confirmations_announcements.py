from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from core.models import Announcement, AnnouncementRecipient, Notification


@pytest.mark.django_db
def test_direct_admin_assignment_is_confirmed_without_worker_confirmation(
    auth_admin, auth_worker, worker_user, company, location, position
):
    starts_at = timezone.now() + timedelta(days=2)
    created = auth_admin.post('/api/shifts/', {
        'client': str(company.id), 'location': str(location.id), 'position': str(position.id),
        'starts_at': starts_at.isoformat(), 'ends_at': (starts_at + timedelta(hours=4)).isoformat(),
        'required_count': 1, 'break_minutes': 0, 'status': 'draft', 'confirmation_required': True,
    }, format='json')
    assert created.status_code == 201, created.data

    assigned = auth_admin.post(f"/api/shifts/{created.data['id']}/assign/", {
        'workers': [str(worker_user.worker_profile.id)], 'publish_remaining': True,
    }, format='json')
    assert assigned.status_code == 200, assigned.data
    worker = assigned.data['assigned_workers'][0]
    assert worker['confirmation_status'] == 'confirmed'
    assert worker['confirmation_label'] == 'Bestätigt'
    assert worker['slot_id']
    assignment_notice = Notification.objects.get(user=worker_user, kind__startswith='shift-admin-assigned-')
    assert assignment_notice.title == 'Anna Becker übernimmt folgende Schicht:'
    assert not Notification.objects.filter(user=worker_user, title='Bitte Schicht bestätigen').exists()

    # Even when the shift template has confirmation_required enabled, selecting a
    # worker directly in the admin form is the acceptance decision for this slot.
    confirmation = auth_worker.post(
        f"/api/shifts/{created.data['id']}/confirmation/",
        {'status': 'confirmed'},
        format='json',
    )
    assert confirmation.status_code == 200, confirmation.data
    assert confirmation.data['assigned_workers'][0]['confirmation_status'] == 'confirmed'


@pytest.mark.django_db
def test_admin_sends_one_way_announcement_with_attachment_and_push_notification(
    auth_admin, auth_worker, admin_user, worker_user
):
    attachment = SimpleUploadedFile('einsatz.pdf', b'%PDF-1.4 phase6', content_type='application/pdf')
    sent = auth_admin.post('/api/announcements/', {
        'title': 'Wichtige Mitteilung',
        'body': 'Bitte vor dem Einsatz lesen.',
        'all_recipients': 'false',
        'recipient_ids': [str(worker_user.id)],
        'attachment': attachment,
    }, format='multipart')
    assert sent.status_code == 201, sent.data
    assert sent.data['recipient_count'] == 1
    assert sent.data['read_count'] == 0
    announcement = Announcement.objects.get(pk=sent.data['id'])
    link = AnnouncementRecipient.objects.get(announcement=announcement, user=worker_user)
    assert link.notification_id
    notification = Notification.objects.get(pk=link.notification_id, kind=f'announcement-{announcement.id}')
    assert notification.title == f'Neue Mitteilung von {admin_user.get_full_name() or admin_user.email}'
    assert notification.body == 'Bitte vor dem Einsatz lesen.'

    inbox = auth_worker.get('/api/announcements/')
    assert inbox.status_code == 200
    rows = inbox.data.get('results', inbox.data)
    assert len(rows) == 1
    assert rows[0]['title'] == 'Wichtige Mitteilung'
    assert rows[0]['is_read'] is False

    read = auth_worker.post(f'/api/announcements/{announcement.id}/read/', {}, format='json')
    assert read.status_code == 200
    assert read.data['is_read'] is True
    link.refresh_from_db()
    assert link.read_at is not None

    forbidden = auth_worker.post('/api/announcements/', {
        'title': 'Nicht erlaubt', 'body': 'Antwort', 'recipient_ids': [str(worker_user.id)]
    }, format='json')
    assert forbidden.status_code == 403
