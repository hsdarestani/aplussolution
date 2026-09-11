import pytest
from rest_framework.test import APIClient

from core.models import Notification


@pytest.mark.django_db
def test_normal_login_does_not_reemit_registration_completed(admin_user, worker_user):
    password = 'LoginPass123!'
    worker_user.set_password(password)
    worker_user.is_onboarded = True
    worker_user.save(update_fields=['password', 'is_onboarded'])

    kind = f'portal-registration-complete-{worker_user.id}'
    Notification.objects.filter(user=admin_user, kind=kind).delete()

    response = APIClient().post(
        '/api/auth/login/',
        {'email': worker_user.email, 'password': password},
        format='json',
    )

    assert response.status_code == 200
    assert not Notification.objects.filter(user=admin_user, kind=kind).exists()


@pytest.mark.django_db
def test_real_onboarding_transition_still_notifies_once(admin_user, worker_user):
    worker_user.is_onboarded = False
    worker_user.save(update_fields=['is_onboarded'])
    kind = f'portal-registration-complete-{worker_user.id}'
    Notification.objects.filter(user=admin_user, kind=kind).delete()

    worker_user.is_onboarded = True
    worker_user.save(update_fields=['is_onboarded'])
    worker_user.save(update_fields=['last_name'])

    assert Notification.objects.filter(user=admin_user, kind=kind).count() == 1


@pytest.mark.django_db
def test_wiw_synced_onboarding_transition_never_emits_registration(admin_user, worker_user):
    worker_user.wiw_id = 'wiw-regression-123'
    worker_user.is_onboarded = False
    worker_user.save(update_fields=['wiw_id', 'is_onboarded'])
    kind = f'portal-registration-complete-{worker_user.id}'
    Notification.objects.filter(user=admin_user, kind=kind).delete()

    # WIW reconciliation may promote an imported/stub identity to onboarded.
    # This is synchronization, not a person completing portal registration.
    worker_user.is_onboarded = True
    worker_user.save(update_fields=['is_onboarded'])

    assert not Notification.objects.filter(user=admin_user, kind=kind).exists()
