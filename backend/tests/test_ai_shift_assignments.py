import pytest
from django.utils import timezone

from core.models import Location, Notification, Position, Shift, User, WorkerProfile
from core.shift_slots import ShiftSlot


@pytest.mark.django_db
def test_semantic_ai_approval_assigns_explicit_directory_workers(auth_admin, company, location):
    front_office = Position.objects.create(name='Front Office')

    simret_user = User.objects.create_user(
        'simret@example.com',
        None,
        first_name='Simret',
        last_name='Solomon',
        role=User.Role.WORKER,
        is_onboarded=True,
    )
    simret = WorkerProfile.objects.create(
        user=simret_user,
        employee_number='SIMRET-001',
        employment_type='minijob',
        monthly_hours='40',
        tariff_hourly_rate='15',
    )
    marie_user = User.objects.create_user(
        'marie@example.com',
        None,
        first_name='Marie',
        last_name='Krass',
        role=User.Role.WORKER,
        is_onboarded=True,
    )
    marie = WorkerProfile.objects.create(
        user=marie_user,
        employee_number='MARIE-001',
        employment_type='minijob',
        monthly_hours='40',
        tariff_hourly_rate='15',
    )

    parsed = {
        'contract_no': '',
        'shifts': [
            {
                'date': '2028-10-03',
                'start_time': '22:45',
                'end_time': '06:45',
                'count': 1,
                'client_id': str(company.id),
                'site_text': company.name,
                'location_id': str(location.id),
                'location_text': location.name,
                'position_id': str(front_office.id),
                'role': front_office.name,
                'assignment_worker_id': str(simret.id),
                'assignment_worker_name': 'Simret Solomon',
                'site_address': company.address,
                'notes': '',
            },
            {
                'date': '2028-10-04',
                'start_time': '06:45',
                'end_time': '14:45',
                'count': 1,
                'client_id': str(company.id),
                'site_text': company.name,
                'location_id': str(location.id),
                'location_text': location.name,
                'position_id': str(front_office.id),
                'role': front_office.name,
                'assignment_worker_id': str(marie.id),
                'assignment_worker_name': 'Marie Krass',
                'site_address': company.address,
                'notes': '',
            },
        ],
    }

    response = auth_admin.post(
        '/api/automation/orders/approve/',
        {'raw_text': 'arbitrary multilingual workforce request', 'parsed': parsed},
        format='json',
    )

    assert response.status_code == 200, response.data
    assert response.data['assigned_count'] == 2
    assert response.data['created_open_count'] == 0

    shifts = list(Shift.objects.filter(order__client=company).order_by('starts_at'))
    assert len(shifts) == 2
    first_slot = ShiftSlot.objects.get(shift=shifts[0], status=ShiftSlot.Status.CLAIMED)
    second_slot = ShiftSlot.objects.get(shift=shifts[1], status=ShiftSlot.Status.CLAIMED)
    assert first_slot.worker_id == simret.id
    assert second_slot.worker_id == marie.id
    assert all(shift.status == Shift.Status.CONFIRMED for shift in shifts)
    assert all(not shift.is_open for shift in shifts)
    assert all(shift.location_id == location.id for shift in shifts)
    assert all(shift.position_id == front_office.id for shift in shifts)
    assert all(shift.notes == '' for shift in shifts)
    assert not Notification.objects.filter(kind__startswith='open-shift-').exists()
    assert Notification.objects.filter(user=simret_user, kind__startswith='shift-event-ai-semantic-assignment-').count() == 1
    assert Notification.objects.filter(user=marie_user, kind__startswith='shift-event-ai-semantic-assignment-').count() == 1


@pytest.mark.django_db
def test_semantic_ai_admin_review_keeps_exact_directory_entities(auth_admin, company, location):
    serviceleitung = Position.objects.create(name='Serviceleitung')
    reviewed = {
        'contract_no': '',
        'shifts': [
            {
                'date': '2028-10-05',
                'start_time': '12:30',
                'end_time': '18:15',
                'count': 1,
                'client_id': str(company.id),
                'site_text': company.name,
                'location_id': str(location.id),
                'location_text': location.name,
                'position_id': str(serviceleitung.id),
                'role': serviceleitung.name,
                'assignment_worker_id': '',
                'assignment_worker_name': '',
                'site_address': company.address,
                'notes': 'Admin korrigiert',
            },
        ],
    }

    response = auth_admin.post(
        '/api/automation/orders/approve/',
        {'raw_text': 'freely phrased request', 'parsed': reviewed, 'admin_reviewed': True},
        format='json',
    )

    assert response.status_code == 200, response.data
    assert response.data['created_count'] == 1
    shift = Shift.objects.get(order__client=company)
    local_start = timezone.localtime(shift.starts_at)
    local_end = timezone.localtime(shift.ends_at)
    assert local_start.date().isoformat() == '2028-10-05'
    assert local_start.strftime('%H:%M') == '12:30'
    assert local_end.strftime('%H:%M') == '18:15'
    assert shift.position_id == serviceleitung.id
    assert shift.location_id == location.id
    assert shift.notes == 'Admin korrigiert'
    assert 'Auftrag:' not in shift.notes
    assert 'Managed by A+ Workforce' not in shift.notes


@pytest.mark.django_db
def test_semantic_ai_maps_any_language_to_live_hotel_directory(
    auth_admin,
    company,
    location,
    monkeypatch,
):
    address = 'Dominikanergasse 5, 60311 Frankfurt am Main, Deutschland'
    company.name = 'Hotel Spenerhaus'
    company.address = address
    company.active = True
    company.save(update_fields=['name', 'address', 'active', 'updated_at'])
    location.name = 'Hotel Spenerhaus'
    location.address = address
    location.client = company
    location.active = True
    location.save(update_fields=['name', 'address', 'client', 'active', 'updated_at'])

    # A misleading location name can exist in the directory. The AI chooses the
    # canonical hotel location by ID; backend code does not reinterpret prose.
    front_office_location = Location.objects.create(
        client=company,
        name='Front Office',
        address=address,
        active=True,
    )
    front_office_position = Position.objects.create(name='Front Office')
    reviewer_user = User.objects.create_user(
        'store.reviewer@aplus-test.de',
        None,
        first_name='Store',
        last_name='Reviewer',
        role=User.Role.WORKER,
        is_onboarded=True,
    )
    reviewer = WorkerProfile.objects.create(
        user=reviewer_user,
        employee_number='STORE-REVIEWER',
        employment_type='minijob',
        monthly_hours='40',
        tariff_hourly_rate='15',
    )

    ai_payload = {
        'contract_no': '',
        'shifts': [
            {
                'date': '2028-10-20',
                'start_time': '06:30',
                'end_time': '14:30',
                'count': 1,
                'client_id': str(company.id),
                'site_text': 'whatever the user wrote',
                'location_id': str(location.id),
                'location_text': 'whatever the user wrote',
                'position_id': str(front_office_position.id),
                'role': 'Front Office',
                'assignment_worker_id': str(reviewer.id),
                'assignment_worker_name': 'Store Reviewer',
                'site_address': '',
                'notes': 'AI-Test 3 Schichten',
            },
            {
                'date': '2028-10-21',
                'start_time': '14:30',
                'end_time': '22:30',
                'count': 1,
                'client_id': str(company.id),
                'site_text': '',
                'location_id': str(location.id),
                'location_text': '',
                'position_id': str(front_office_position.id),
                'role': 'Front Office',
                'assignment_worker_id': str(reviewer.id),
                'assignment_worker_name': 'Store Reviewer',
                'site_address': '',
                'notes': 'AI-Test 3 Schichten',
            },
            {
                'date': '2028-10-22',
                'start_time': '22:30',
                'end_time': '06:30',
                'count': 1,
                'client_id': str(company.id),
                'site_text': '',
                'location_id': str(location.id),
                'location_text': '',
                'position_id': str(front_office_position.id),
                'role': 'Front Office',
                'assignment_worker_id': str(reviewer.id),
                'assignment_worker_name': 'Store Reviewer',
                'site_address': '',
                'notes': 'AI-Test 3 Schichten',
            },
        ],
    }
    monkeypatch.setattr('core.semantic_ai_views._call_ai', lambda _text, _directory: ai_payload)

    # Deliberately mixed/free wording. There is no required German syntax or
    # date/worker separator pattern in the backend anymore.
    raw_text = (
        'برای Store Reviewer سه نوبت در Hotel Spenerhaus بساز؛ '
        'یکی صبح 20 اکتبر، یکی عصر 21 اکتبر و یکی شب 22 اکتبر. '
        'کارش Front Office است. Thanks!'
    )
    parsed_response = auth_admin.post(
        '/api/automation/orders/parse/',
        {'text': raw_text},
        format='json',
    )
    assert parsed_response.status_code == 200, parsed_response.data
    assert len(parsed_response.data['shifts']) == 3
    for row in parsed_response.data['shifts']:
        assert row['client_id'] == str(company.id)
        assert row['site_text'] == 'Hotel Spenerhaus'
        assert row['location_id'] == str(location.id)
        assert row['location_id'] != str(front_office_location.id)
        assert row['location_text'] == 'Hotel Spenerhaus'
        assert row['position_id'] == str(front_office_position.id)
        assert row['assignment_worker_id'] == str(reviewer.id)
        assert row['assignment_worker_name'] == 'Store Reviewer'

    metadata_response = auth_admin.get('/api/automation/orders/metadata/')
    assert metadata_response.status_code == 200, metadata_response.data
    assert any(item['id'] == str(company.id) for item in metadata_response.data['clients'])
    assert any(item['id'] == str(location.id) for item in metadata_response.data['locations'])
    assert any(item['id'] == str(reviewer.id) for item in metadata_response.data['workers'])

    approve_response = auth_admin.post(
        '/api/automation/orders/approve/',
        {'raw_text': raw_text, 'parsed': parsed_response.data, 'admin_reviewed': True},
        format='json',
    )
    assert approve_response.status_code == 200, approve_response.data
    assert approve_response.data['assigned_count'] == 3

    shifts = list(Shift.objects.filter(order__client=company, starts_at__year=2028).order_by('starts_at'))
    assert len(shifts) == 3
    assert all(item.location_id == location.id for item in shifts)
    assert all(item.position_id == front_office_position.id for item in shifts)
    assert all(item.schedule_groups == ['front_office'] for item in shifts)
    assert all(item.notes == 'AI-Test 3 Schichten' for item in shifts)
    assert not Notification.objects.filter(kind__startswith='open-shift-').exists()
    assert all(
        ShiftSlot.objects.filter(shift=item, worker=reviewer, status=ShiftSlot.Status.CLAIMED).exists()
        for item in shifts
    )
    assert not Location.objects.filter(client=company, name='Front Office im Hotel Spenerhaus').exists()


@pytest.mark.django_db
def test_semantic_ai_open_front_office_notifies_only_front_office_zeitplan(
    auth_admin,
    company,
    location,
    worker_user,
    second_worker,
):
    front_office = Position.objects.create(name='Front Office')
    front_worker = worker_user.worker_profile
    front_worker.schedule_groups = ['front_office']
    front_worker.save(update_fields=['schedule_groups', 'updated_at'])
    second_worker.schedule_groups = ['housekeeping']
    second_worker.save(update_fields=['schedule_groups', 'updated_at'])

    reviewed = {
        'contract_no': '',
        'shifts': [{
            'date': '2028-11-01',
            'start_time': '08:00',
            'end_time': '16:00',
            'count': 1,
            'client_id': str(company.id),
            'site_text': company.name,
            'location_id': str(location.id),
            'location_text': location.name,
            'position_id': str(front_office.id),
            'role': 'Front Office',
            'assignment_worker_id': '',
            'assignment_worker_name': '',
            'site_address': company.address,
            'notes': 'Nur echte Notiz',
        }],
    }

    response = auth_admin.post(
        '/api/automation/orders/approve/',
        {'raw_text': 'free wording for one open front office shift', 'parsed': reviewed},
        format='json',
    )

    assert response.status_code == 200, response.data
    shift = Shift.objects.get(order__client=company)
    assert shift.schedule_groups == ['front_office']
    assert shift.notes == 'Nur echte Notiz'
    assert Notification.objects.filter(
        user=worker_user,
        kind__startswith='open-shift-ai-order-',
    ).count() == 1
    assert not Notification.objects.filter(
        user=second_worker.user,
        kind__startswith='open-shift-ai-order-',
    ).exists()
