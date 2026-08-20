import pytest


@pytest.mark.django_db
def test_admin_invite_returns_activation_link_even_when_email_is_delivered(settings, auth_admin, worker_user):
    settings.APP_URL = 'https://solution.smarbiz.sbs'
    settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
    settings.EMAIL_HOST = 'smtp.example.test'
    settings.EMAIL_HOST_USER = 'noreply@example.test'

    worker_user.set_unusable_password()
    worker_user.is_onboarded = False
    worker_user.save(update_fields=['password', 'is_onboarded'])

    response = auth_admin.post(
        f'/api/workers/{worker_user.worker_profile.id}/invite/',
        {},
        format='json',
    )

    assert response.status_code == 201
    assert response.data['delivered'] is True
    assert response.data['activation_url'].startswith('https://solution.smarbiz.sbs/aktivieren?token=')


@pytest.mark.django_db
def test_admin_invite_keeps_activation_link_when_email_delivery_fails(settings, auth_admin, worker_user, monkeypatch):
    settings.APP_URL = 'https://solution.smarbiz.sbs'
    settings.EMAIL_HOST = 'smtp.example.test'
    settings.EMAIL_HOST_USER = 'noreply@example.test'

    worker_user.email = 'qa.leon@example.test'
    worker_user.set_unusable_password()
    worker_user.is_onboarded = False
    worker_user.save(update_fields=['email', 'password', 'is_onboarded'])

    def fail_delivery(*args, **kwargs):
        raise OSError('mailbox unavailable')

    monkeypatch.setattr('core.portal_service.send_mail', fail_delivery)

    response = auth_admin.post(
        f'/api/workers/{worker_user.worker_profile.id}/invite/',
        {},
        format='json',
    )

    assert response.status_code == 201
    assert response.data['delivered'] is False
    assert response.data['activation_url'].startswith('https://solution.smarbiz.sbs/aktivieren?token=')
