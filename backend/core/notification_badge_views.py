from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Notification
from .notification_badges import clear_ios_badge


@api_view(['POST'])
def notifications_read_all(request):
    count = Notification.objects.filter(
        user=request.user,
        read_at__isnull=True,
    ).update(read_at=timezone.now())

    # APNs app-icon badges are device state, not derived from Notification rows.
    # Always send badge=0, even when the database already says everything is read,
    # so an old/stuck iOS badge can be repaired by pressing "Alle gelesen" again.
    badge = clear_ios_badge(request.user)
    return Response({'updated': count, 'badge': badge})
