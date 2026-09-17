import pytest
from django.utils import timezone

from core.models import Notification, Shift, User, WorkerProfile
from core.shift_slots import ShiftSlot


@pytest.mark.django_db
def test_ai_order_assigns_named_workers_without_open_shift_fanout(auth_admin, company, location):
    # A stale/local duplicate with the exact same display name must never win over
    # the real login identity. Create it first so age alone would choose wrongly.
    simret_shadow_user = User.objects.create_user(
        'simret@sync.invalid',
        None,
        first_name='Simret',
        last_name='Solomon',
        role=User.Role.WORKER,
        is_onboarded=False,
    )
    simret_shadow = WorkerProfile.objects.create(
        user=simret_shadow_user,
        employee_number='LOCAL-SIMRET-SOLOMON',
        employment_type='minijob',
        monthly_hours='40',
        tariff_hourly_rate='15',
    )

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

    raw_text = (
        'Die Nachtdienste werden von Simret Solomon übernommen und alle anderen Dienste '
        'werden von Marie Krass übernommen.\n'
        'Die Nachtdienste gehen von 22:45 Uhr bis 6:45 Uhr.\n'
        'Es sind insgesamt 2 Schichten.'
    )
    parsed = {
        'shifts': [
            {
                'date': '2026-10-03',
                'start_time': '22:45',
                'end_time': '06:45',
                'count': 1,
                'role': 'Front Office',
                'site_text': company.name,
                'location_text': location.name,
                'site_address': company.address,
                'notes': 'Übernommen von Simret Solomon',
            },
            {
                'date': '2026-10-04',
                'start_time': '06:45',
                'end_time': '14:45',
                'count': 1,
                'role': 'Front Office',
                'site_text': company.name,
                'location_text': location.name,
                'site_address': company.address,
                'notes': 'Übernommen von Marie Krass',
            },
        ]
    }

    response = auth_admin.post(
        '/api/automation/orders/approve/',
        {'raw_text': raw_text, 'parsed': parsed},
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
    assert first_slot.worker_id != simret_shadow.id
    assert second_slot.worker_id == marie.id
    assert all(shift.status == Shift.Status.CONFIRMED for shift in shifts)
    assert all(not shift.is_open for shift in shifts)
    assert all('Übernommen von' not in (shift.notes or '') for shift in shifts)
    assert not Notification.objects.filter(title='Neue OpenShift verfügbar').exists()
    assert Notification.objects.filter(user=simret_user, title='Deine Schicht wurde aktualisiert').count() == 1
    assert Notification.objects.filter(user=marie_user, title='Deine Schicht wurde aktualisiert').count() == 1
    assert not Notification.objects.filter(user=simret_shadow_user).exists()


@pytest.mark.django_db
def test_ai_admin_review_can_edit_and_delete_rows(auth_admin, company, location):
    raw_text = 'Es sind insgesamt 2 Schichten.'
    reviewed = {
        'admin_reviewed': True,
        'expected_shift_count': 1,
        'shift_count_mismatch': False,
        'shifts': [
            {
                'date': '2026-10-05',
                'start_time': '12:30',
                'end_time': '18:15',
                'count': 1,
                'role': 'Serviceleitung',
                'site_text': company.name,
                'location_text': location.name,
                'site_address': company.address,
                'notes': 'Admin korrigiert',
            },
        ],
    }

    response = auth_admin.post(
        '/api/automation/orders/approve/',
        {'raw_text': raw_text, 'parsed': reviewed, 'admin_reviewed': True},
        format='json',
    )

    assert response.status_code == 200, response.data
    assert response.data['created_count'] == 1
    shifts = list(Shift.objects.filter(order__client=company))
    assert len(shifts) == 1
    shift = shifts[0]
    local_start = timezone.localtime(shift.starts_at)
    local_end = timezone.localtime(shift.ends_at)
    assert local_start.date().isoformat() == '2026-10-05'
    assert local_start.strftime('%H:%M') == '12:30'
    assert local_end.strftime('%H:%M') == '18:15'
    assert shift.position.name == 'Serviceleitung'
    assert shift.location_id == location.id
    assert 'Admin korrigiert' in shift.notes
