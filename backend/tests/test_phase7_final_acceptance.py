from datetime import timedelta

import pytest
from django.utils import timezone

from core.models import Announcement, AnnouncementRecipient, Notification


@pytest.mark.django_db
def test_phase7_mitteilungen_are_one_way_and_recipient_scoped(
    auth_admin, auth_worker, auth_client, worker_user, client_user
):
    sent = auth_admin.post('/api/announcements/', {
        'title': 'Phase 7 Abnahme',
        'body': 'Diese Mitteilung ist nur für den Mitarbeiter bestimmt.',
        'all_recipients': False,
        'recipient_ids': [str(worker_user.id)],
    }, format='json')
    assert sent.status_code == 201, sent.data
    announcement = Announcement.objects.get(pk=sent.data['id'])
    assert AnnouncementRecipient.objects.filter(announcement=announcement, user=worker_user).exists()
    assert not AnnouncementRecipient.objects.filter(announcement=announcement, user=client_user).exists()

    worker_inbox = auth_worker.get('/api/announcements/')
    assert worker_inbox.status_code == 200
    worker_rows = worker_inbox.data.get('results', worker_inbox.data)
    assert [row['id'] for row in worker_rows] == [str(announcement.id)]
    assert worker_rows[0]['recipients_detail'] == []

    client_inbox = auth_client.get('/api/announcements/')
    assert client_inbox.status_code == 200
    assert client_inbox.data.get('results', client_inbox.data) == []

    for portal in (auth_worker, auth_client):
        forbidden = portal.post('/api/announcements/', {
            'title': 'Nicht erlaubt', 'body': 'Keine Antwortfunktion.'
        }, format='json')
        assert forbidden.status_code == 403

    read = auth_worker.post(f'/api/announcements/{announcement.id}/read/', {}, format='json')
    assert read.status_code == 200
    link = AnnouncementRecipient.objects.get(announcement=announcement, user=worker_user)
    assert link.read_at is not None
    assert link.notification_id
    assert Notification.objects.filter(pk=link.notification_id, read_at__isnull=False).exists()


@pytest.mark.django_db
def test_phase7_confirmation_requires_an_explicit_worker_decision(
    auth_admin, auth_worker, worker_user, company, location, position
):
    starts_at = timezone.now() + timedelta(days=3)
    created = auth_admin.post('/api/shifts/', {
        'client': str(company.id),
        'location': str(location.id),
        'position': str(position.id),
        'starts_at': starts_at.isoformat(),
        'ends_at': (starts_at + timedelta(hours=5)).isoformat(),
        'required_count': 1,
        'break_minutes': 0,
        'status': 'draft',
        'confirmation_required': True,
    }, format='json')
    assert created.status_code == 201, created.data

    assigned = auth_admin.post(f"/api/shifts/{created.data['id']}/assign/", {
        'workers': [str(worker_user.worker_profile.id)],
        'publish_remaining': True,
    }, format='json')
    assert assigned.status_code == 200, assigned.data
    assignee = assigned.data['assigned_workers'][0]
    assert assignee['confirmation_status'] == 'pending'
    assert assignee['confirmation_label'] == 'Ausstehend'

    rejected = auth_worker.post(
        f"/api/shifts/{created.data['id']}/confirmation/",
        {'status': 'rejected'},
        format='json',
    )
    assert rejected.status_code == 200, rejected.data
    mine = next(item for item in rejected.data['assigned_workers'] if item['is_me'])
    assert mine['confirmation_status'] == 'rejected'
    assert mine['confirmation_label'] == 'Abgelehnt'

    reset = auth_admin.post(f"/api/shifts/{created.data['id']}/confirmation/", {
        'slot_id': assignee['slot_id'],
        'status': 'pending',
    }, format='json')
    assert reset.status_code == 200, reset.data
    assert reset.data['assigned_workers'][0]['confirmation_status'] == 'pending'
