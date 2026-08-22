from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import ClientCompany, ClientOrder, Location, Shift, User, WorkerRating

pytestmark = pytest.mark.django_db


def make_foreign_client():
    user = User.objects.create_user(
        'other-client@example.com',
        'StrongPass123!',
        first_name='Andere',
        last_name='Kundin',
        role=User.Role.CLIENT,
        is_onboarded=True,
    )
    company = ClientCompany.objects.create(
        name='Andere Kunde GmbH',
        customer_number='KD-OTHER',
        address='Fremdweg 9, Frankfurt',
    )
    company.contacts.add(user)
    location = Location.objects.create(
        client=company,
        name='Fremder Standort',
        address='Fremdweg 10, Frankfurt',
    )
    return user, company, location


def order_payload(location, *, title='Client QA Auftrag'):
    start = timezone.now() + timedelta(days=3)
    return {
        'title': title,
        'description': 'Client Portal Security QA',
        'location': str(location.id),
        'starts_at': start.isoformat(),
        'ends_at': (start + timedelta(hours=5)).isoformat(),
        'requested_staff': 2,
        'functions': ['Servicekraft'],
    }


def test_client_order_create_rejects_location_from_another_client(auth_client, company, location):
    _foreign_user, foreign_company, foreign_location = make_foreign_client()

    response = auth_client.post('/api/orders/', order_payload(foreign_location), format='json')

    assert response.status_code == 400, response.data
    assert not ClientOrder.objects.filter(client=company, location=foreign_location).exists()
    assert not ClientOrder.objects.filter(client=foreign_company, created_by__email='client@example.com').exists()


def test_client_cannot_move_existing_order_to_foreign_client_or_location(auth_client, company, location, client_user):
    _foreign_user, foreign_company, foreign_location = make_foreign_client()
    start = timezone.now() + timedelta(days=4)
    order = ClientOrder.objects.create(
        client=company,
        location=location,
        title='Eigener Auftrag',
        starts_at=start,
        ends_at=start + timedelta(hours=4),
        requested_staff=1,
        created_by=client_user,
    )

    response = auth_client.patch(
        f'/api/orders/{order.id}/',
        {'client': str(foreign_company.id), 'location': str(foreign_location.id)},
        format='json',
    )

    assert response.status_code == 400, response.data
    order.refresh_from_db()
    assert order.client_id == company.id
    assert order.location_id == location.id


def test_client_put_cannot_change_order_status_or_tenant(auth_client, company, location, client_user):
    _foreign_user, foreign_company, foreign_location = make_foreign_client()
    start = timezone.now() + timedelta(days=5)
    order = ClientOrder.objects.create(
        client=company,
        location=location,
        title='PUT Schutz Auftrag',
        starts_at=start,
        ends_at=start + timedelta(hours=4),
        requested_staff=1,
        created_by=client_user,
    )
    payload = order_payload(foreign_location, title='Manipulierter Auftrag')
    payload.update({'client': str(foreign_company.id), 'status': ClientOrder.Status.CONFIRMED})

    response = auth_client.put(f'/api/orders/{order.id}/', payload, format='json')

    assert response.status_code == 400, response.data
    order.refresh_from_db()
    assert order.client_id == company.id
    assert order.location_id == location.id
    assert order.status == ClientOrder.Status.NEW


def test_client_rating_rejects_unserved_worker_and_foreign_shift(
    auth_client, company, location, position, second_worker, client_user
):
    _foreign_user, foreign_company, foreign_location = make_foreign_client()
    now = timezone.now()
    foreign_shift = Shift.objects.create(
        client=foreign_company,
        location=foreign_location,
        position=position,
        worker=second_worker,
        starts_at=now - timedelta(hours=6),
        ends_at=now - timedelta(hours=1),
        status=Shift.Status.COMPLETED,
    )

    no_shift = auth_client.post('/api/ratings/', {
        'worker': str(second_worker.id),
        'score': 5,
        'punctuality': 5,
        'quality': 5,
        'teamwork': 5,
        'comment': 'Soll nicht möglich sein',
    }, format='json')
    assert no_shift.status_code == 400, no_shift.data

    foreign = auth_client.post('/api/ratings/', {
        'worker': str(second_worker.id),
        'shift': str(foreign_shift.id),
        'score': 5,
        'punctuality': 5,
        'quality': 5,
        'teamwork': 5,
        'comment': 'Fremder Einsatz',
    }, format='json')
    assert foreign.status_code == 400, foreign.data
    assert not WorkerRating.objects.filter(created_by=client_user).exists()


def test_client_can_rate_own_completed_assignment_once(
    auth_client, company, location, position, second_worker, client_user
):
    now = timezone.now()
    shift = Shift.objects.create(
        client=company,
        location=location,
        position=position,
        worker=second_worker,
        starts_at=now - timedelta(hours=6),
        ends_at=now - timedelta(hours=1),
        status=Shift.Status.COMPLETED,
    )
    payload = {
        'worker': str(second_worker.id),
        'shift': str(shift.id),
        'score': 4,
        'punctuality': 5,
        'quality': 4,
        'teamwork': 5,
        'comment': 'Guter Einsatz',
    }

    first = auth_client.post('/api/ratings/', payload, format='json')
    assert first.status_code == 201, first.data
    assert WorkerRating.objects.filter(client=company, worker=second_worker, shift=shift, created_by=client_user).count() == 1

    duplicate = auth_client.post('/api/ratings/', payload, format='json')
    assert duplicate.status_code == 400, duplicate.data
    assert WorkerRating.objects.filter(client=company, worker=second_worker, shift=shift).count() == 1
