from datetime import timedelta

import pytest
from django.utils import timezone

from core.models import ClientOrder, Shift, User


@pytest.mark.django_db
def test_qa_admin_onboards_worker_and_client_then_both_can_login(auth_admin, api_client, settings):
    settings.EMAIL_HOST = ''
    worker = auth_admin.post(
        '/api/workers/onboard/',
        {
            'email': 'qa.worker@example.com',
            'first_name': 'QA',
            'last_name': 'Worker',
            'employee_number': 'QA-W-001',
            'employment_type': 'teilzeit',
            'monthly_hours': '80',
            'tariff_hourly_rate': '15.50',
        },
        format='json',
    )
    assert worker.status_code == 201
    assert worker.data['worker']['employee_number'] == 'QA-W-001'
    assert worker.data['temporary_password'] is None
    assert worker.data['requires_activation'] is True

    worker_id = worker.data['worker']['id']
    invited = auth_admin.post(f'/api/workers/{worker_id}/invite/', {}, format='json')
    assert invited.status_code == 201
    assert invited.data['delivered'] is False
    token = invited.data['activation_url'].split('token=', 1)[1]

    activated = api_client.post(
        '/api/auth/activation/complete/',
        {
            'token': token,
            'password': 'QaWorkerPass123!',
            'password_confirm': 'QaWorkerPass123!',
        },
        format='json',
    )
    assert activated.status_code == 200
    assert activated.data['user']['role'] == 'worker'

    worker_login = api_client.post(
        '/api/auth/login/',
        {'email': 'qa.worker@example.com', 'password': 'QaWorkerPass123!'},
        format='json',
    )
    assert worker_login.status_code == 200
    assert worker_login.data['user']['role'] == 'worker'

    client = auth_admin.post(
        '/api/clients/onboard/',
        {
            'name': 'QA Kunde GmbH',
            'customer_number': 'QA-KD-001',
            'address': 'Testweg 1, Frankfurt',
            'contact_email': 'qa.client@example.com',
            'contact_first_name': 'QA',
            'contact_last_name': 'Client',
        },
        format='json',
    )
    assert client.status_code == 201
    assert client.data['client']['name'] == 'QA Kunde GmbH'
    assert client.data['temporary_password']

    client_login = api_client.post(
        '/api/auth/login/',
        {'email': 'qa.client@example.com', 'password': client.data['temporary_password']},
        format='json',
    )
    assert client_login.status_code == 200
    assert client_login.data['user']['role'] == 'client'


@pytest.mark.django_db
def test_qa_client_order_roundtrip_is_scoped_to_own_company(auth_client, company):
    now = timezone.now() + timedelta(days=3)
    created = auth_client.post(
        '/api/orders/',
        {
            'title': 'QA Personalbedarf',
            'starts_at': now.isoformat(),
            'ends_at': (now + timedelta(hours=6)).isoformat(),
            'requested_staff': 3,
            'description': 'QA End-to-End Auftrag',
        },
        format='json',
    )
    assert created.status_code == 201
    assert str(created.data['client']) == str(company.id)
    assert created.data['requested_staff'] == 3

    other_contact = User.objects.create_user(
        'qa.otherclient@example.com',
        'StrongPass123!',
        first_name='Other',
        role=User.Role.CLIENT,
        is_onboarded=True,
    )
    other_company = company.__class__.objects.create(name='Other QA GmbH', customer_number='QA-KD-OTHER')
    other_company.contacts.add(other_contact)
    ClientOrder.objects.create(
        client=other_company,
        title='Fremder Auftrag',
        starts_at=now,
        ends_at=now + timedelta(hours=4),
        requested_staff=1,
        created_by=other_contact,
    )

    listing = auth_client.get('/api/orders/')
    assert listing.status_code == 200
    rows = listing.data['results'] if isinstance(listing.data, dict) else listing.data
    assert any(str(item['id']) == str(created.data['id']) for item in rows)
    assert all(str(item['client']) == str(company.id) for item in rows)


@pytest.mark.django_db
def test_qa_staffing_publish_claim_release_roundtrip(auth_admin, auth_worker, company, location, position):
    now = timezone.now() + timedelta(days=2)
    created = auth_admin.post(
        '/api/shifts/',
        {
            'client': str(company.id),
            'location': str(location.id),
            'position': str(position.id),
            'starts_at': now.isoformat(),
            'ends_at': (now + timedelta(hours=6)).isoformat(),
            'break_minutes': 30,
            'status': 'draft',
            'required_count': 1,
            'notes': 'QA staffing lifecycle',
        },
        format='json',
    )
    assert created.status_code == 201
    shift_id = created.data['id']

    published = auth_admin.post(f'/api/shifts/{shift_id}/publish/', {}, format='json')
    assert published.status_code == 200
    assert published.data['status'] == 'published'
    assert published.data['open_count'] == 1

    available = auth_worker.get('/api/shifts/available/')
    assert available.status_code == 200
    available_rows = available.data['results'] if isinstance(available.data, dict) else available.data
    assert any(str(item['id']) == str(shift_id) for item in available_rows)

    claimed = auth_worker.post(f'/api/shifts/{shift_id}/claim/', {}, format='json')
    assert claimed.status_code == 200
    assert claimed.data['filled_count'] == 1
    assert claimed.data['open_count'] == 0

    mine = auth_worker.get('/api/shifts/mine/')
    mine_rows = mine.data['results'] if isinstance(mine.data, dict) else mine.data
    assert any(str(item['id']) == str(shift_id) for item in mine_rows)

    # Employees cannot directly give back an accepted shift anymore.
    direct_release = auth_worker.post(f'/api/shifts/{shift_id}/release/', {}, format='json')
    assert direct_release.status_code == 400

    requested = auth_worker.post(f'/api/employee/shifts/{shift_id}/release-request/', {}, format='json')
    assert requested.status_code == 202
    assert requested.data['pending_approval'] is True

    still_mine = auth_worker.get('/api/shifts/mine/')
    still_mine_rows = still_mine.data['results'] if isinstance(still_mine.data, dict) else still_mine.data
    assert any(str(item['id']) == str(shift_id) for item in still_mine_rows)

    pending = auth_admin.get('/api/premium/release-requests/')
    assert pending.status_code == 200
    row = next(item for item in pending.data if str(item['shift_id']) == str(shift_id))
    approved = auth_admin.post(
        f"/api/premium/release-requests/{row['id']}/decide/",
        {'status': 'approved'},
        format='json',
    )
    assert approved.status_code == 200
    assert approved.data['status'] == 'approved'

    reopened = auth_worker.get('/api/shifts/available/')
    reopened_rows = reopened.data['results'] if isinstance(reopened.data, dict) else reopened.data
    reopened_shift = next(item for item in reopened_rows if str(item['id']) == str(shift_id))
    assert reopened_shift['filled_count'] == 0
    assert reopened_shift['open_count'] == 1


@pytest.mark.django_db
def test_qa_worker_availability_and_time_off_roundtrip(auth_worker, auth_admin, worker_user):
    start = timezone.now() + timedelta(days=5)
    availability = auth_worker.post(
        '/api/operations/availability/',
        {
            'starts_at': start.isoformat(),
            'ends_at': (start + timedelta(hours=8)).isoformat(),
            'available': False,
            'note': 'QA unavailable window',
        },
        format='json',
    )
    assert availability.status_code == 201
    assert str(availability.data['worker']) == str(worker_user.worker_profile.id)
    assert availability.data['available'] is False

    deleted = auth_worker.delete(f"/api/operations/availability/{availability.data['id']}/")
    assert deleted.status_code == 204

    day = timezone.localdate() + timedelta(days=10)
    time_off = auth_worker.post(
        '/api/time-off/',
        {
            'starts_on': day.isoformat(),
            'ends_on': (day + timedelta(days=2)).isoformat(),
            'reason': 'QA Urlaub',
        },
        format='json',
    )
    assert time_off.status_code == 201
    assert str(time_off.data['worker']) == str(worker_user.worker_profile.id)
    assert time_off.data['status'] == 'pending'

    decided = auth_admin.post(
        f"/api/time-off/{time_off.data['id']}/decide/",
        {'status': 'approved'},
        format='json',
    )
    assert decided.status_code == 200
    assert decided.data['status'] == 'approved'


@pytest.mark.django_db
def test_qa_worker_portal_status_and_bulk_invite_routes_are_not_shadowed(auth_admin, worker_user, settings):
    settings.EMAIL_HOST = ''
    worker_user.set_unusable_password()
    worker_user.is_onboarded = False
    worker_user.save(update_fields=['password', 'is_onboarded'])

    statuses = auth_admin.get('/api/workers/portal-status/')
    assert statuses.status_code == 200
    assert any(item['worker_id'] == str(worker_user.worker_profile.id) for item in statuses.data)

    bulk = auth_admin.post(
        '/api/workers/bulk-invite/',
        {'worker_ids': [str(worker_user.worker_profile.id)]},
        format='json',
    )
    assert bulk.status_code == 200
    assert bulk.data['count'] == 1
    assert bulk.data['results'][0]['worker_id'] == str(worker_user.worker_profile.id)


@pytest.mark.django_db
def test_qa_operations_overview_shows_partial_multislot_claim(auth_admin, auth_worker, worker_user, company, location, position):
    now = timezone.now() + timedelta(days=2)
    created = auth_admin.post(
        '/api/shifts/',
        {
            'client': str(company.id),
            'location': str(location.id),
            'position': str(position.id),
            'starts_at': now.isoformat(),
            'ends_at': (now + timedelta(hours=5)).isoformat(),
            'status': 'published',
            'required_count': 2,
        },
        format='json',
    )
    assert created.status_code == 201
    assert auth_worker.post(f"/api/shifts/{created.data['id']}/claim/", {}, format='json').status_code == 200
    shift = Shift.objects.get(pk=created.data['id'])
    assert shift.worker_id is None
    assert shift.slots.filter(worker=worker_user.worker_profile, status='claimed').exists()

    overview = auth_worker.get('/api/operations/')
    assert overview.status_code == 200
    assert any(str(item['id']) == str(created.data['id']) for item in overview.data['upcoming_shifts'])


@pytest.mark.django_db
def test_qa_partial_multislot_claim_can_be_swapped_and_transfers_only_owned_slot(
    auth_admin,
    auth_worker,
    worker_user,
    company,
    location,
    position,
    second_worker,
):
    now = timezone.now() + timedelta(days=2)
    created = auth_admin.post(
        '/api/shifts/',
        {
            'client': str(company.id),
            'location': str(location.id),
            'position': str(position.id),
            'starts_at': now.isoformat(),
            'ends_at': (now + timedelta(hours=5)).isoformat(),
            'status': 'published',
            'required_count': 2,
        },
        format='json',
    )
    assert created.status_code == 201
    assert auth_worker.post(f"/api/shifts/{created.data['id']}/claim/", {}, format='json').status_code == 200
    shift = Shift.objects.get(pk=created.data['id'])
    assert shift.worker_id is None
    assert shift.slots.filter(worker=worker_user.worker_profile, status='claimed').exists()

    swap = auth_worker.post(
        '/api/operations/swaps/',
        {
            'shift': created.data['id'],
            'offered_to': str(second_worker.id),
            'note': 'QA Tauschanfrage',
        },
        format='json',
    )
    assert swap.status_code == 201

    approved = auth_admin.post(
        f"/api/operations/swaps/{swap.data['id']}/decide/",
        {'status': 'approved'},
        format='json',
    )
    assert approved.status_code == 200
    shift.refresh_from_db()
    assert not shift.slots.filter(worker=worker_user.worker_profile, status='claimed').exists()
    assert shift.slots.filter(worker=second_worker, status='claimed').exists()
    assert shift.worker_id is None
