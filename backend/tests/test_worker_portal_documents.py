import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from core.models import Document


def upload(name='note.pdf'):
    return SimpleUploadedFile(name, b'%PDF-1.4\n% QA\n', content_type='application/pdf')


@pytest.mark.django_db
def test_worker_upload_is_forced_to_own_file_and_worker_visibility(auth_worker, worker_user, company):
    response = auth_worker.post(
        '/api/documents/',
        {
            'title': 'Mein Nachweis',
            'file': upload(),
            'folder': Document.Folder.CERTIFICATES,
            'visibility': Document.Visibility.CLIENT,
            'client': str(company.id),
        },
        format='multipart',
    )

    assert response.status_code == 201
    document = Document.objects.get(pk=response.data['id'])
    assert document.worker_id == worker_user.worker_profile.id
    assert document.client_id is None
    assert document.visibility == Document.Visibility.WORKER


@pytest.mark.django_db
def test_client_upload_cannot_attach_file_to_worker(auth_client, client_user, second_worker, company):
    company.contacts.add(client_user)
    response = auth_client.post(
        '/api/documents/',
        {
            'title': 'Kundendokument',
            'file': upload('client.pdf'),
            'folder': Document.Folder.GENERAL,
            'visibility': Document.Visibility.WORKER,
            'worker': str(second_worker.id),
        },
        format='multipart',
    )

    assert response.status_code == 201
    document = Document.objects.get(pk=response.data['id'])
    assert document.worker_id is None
    assert document.client_id == company.id
    assert document.visibility == Document.Visibility.CLIENT


@pytest.mark.django_db
def test_worker_cannot_read_admin_only_own_document(auth_worker, worker_user, admin_user):
    hidden = Document.objects.create(
        title='Interne Notiz',
        file=upload('internal.pdf'),
        worker=worker_user.worker_profile,
        visibility=Document.Visibility.ADMIN,
        uploaded_by=admin_user,
    )

    response = auth_worker.get('/api/documents/')
    assert response.status_code == 200
    rows = response.data['results'] if isinstance(response.data, dict) and 'results' in response.data else response.data
    assert str(hidden.id) not in {row['id'] for row in rows}


@pytest.mark.django_db
def test_worker_cannot_delete_document(auth_worker, worker_user, admin_user):
    document = Document.objects.create(
        title='Mein Dokument',
        file=upload('mine.pdf'),
        worker=worker_user.worker_profile,
        visibility=Document.Visibility.WORKER,
        uploaded_by=worker_user,
    )

    response = auth_worker.delete(f'/api/documents/{document.id}/')
    assert response.status_code == 403
    assert Document.objects.filter(pk=document.id).exists()
