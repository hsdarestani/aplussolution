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
