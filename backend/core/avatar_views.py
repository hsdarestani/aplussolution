from PIL import Image
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import User, WorkerProfile
from .serializers import UserSerializer
from .services import audit


@api_view(['POST'])
def profile_avatar(request):
    """Update a worker avatar without changing the existing public API path.

    Workers update their own image. Admins/managers can target a worker by
    including ``worker_id`` in the multipart form payload.
    """
    if request.user.role == User.Role.WORKER:
        target_user = request.user
    elif request.user.role in [User.Role.ADMIN, User.Role.MANAGER]:
        worker_id = request.data.get('worker_id')
        if not worker_id:
            return Response({'detail': 'worker_id ist erforderlich.'}, status=status.HTTP_400_BAD_REQUEST)
        worker = get_object_or_404(WorkerProfile.objects.select_related('user'), pk=worker_id)
        target_user = worker.user
    else:
        return Response({'detail': 'Profilfotos können nur für Mitarbeiter geändert werden.'}, status=status.HTTP_403_FORBIDDEN)

    uploaded = request.FILES.get('avatar')
    if not uploaded:
        return Response({'detail': 'Bitte ein Bild auswählen.'}, status=status.HTTP_400_BAD_REQUEST)
    if uploaded.size > 5 * 1024 * 1024:
        return Response({'detail': 'Das Profilbild darf maximal 5 MB groß sein.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        image = Image.open(uploaded)
        image.verify()
        uploaded.seek(0)
    except Exception:
        return Response({'detail': 'Die Datei ist kein gültiges Bild.'}, status=status.HTTP_400_BAD_REQUEST)

    target_user.avatar = uploaded
    target_user.save(update_fields=['avatar'])
    audit(
        request,
        'account.avatar_updated',
        target_user,
        metadata={'worker_id': str(getattr(target_user, 'worker_profile', None).pk) if hasattr(target_user, 'worker_profile') else None},
    )
    return Response(UserSerializer(target_user, context={'request': request}).data)
