import pytest
import base64
from django.core.files.uploadedfile import SimpleUploadedFile


@pytest.mark.django_db
def test_worker_can_upload_profile_avatar(auth_worker, worker_user, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    pixels = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=')
    image = SimpleUploadedFile('portrait.png', pixels, content_type='image/png')

    response = auth_worker.post('/api/auth/profile/avatar/', {'avatar': image}, format='multipart')

    assert response.status_code == 200
    worker_user.refresh_from_db()
    assert worker_user.avatar.name.startswith('avatars/portrait')
    assert response.data['avatar']


@pytest.mark.django_db
def test_profile_avatar_rejects_non_images(auth_worker):
    upload = SimpleUploadedFile('notes.txt', b'hello', content_type='text/plain')

    response = auth_worker.post('/api/auth/profile/avatar/', {'avatar': upload}, format='multipart')

    assert response.status_code == 400
