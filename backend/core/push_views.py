from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .push_models import PushDevice
from .push_notifications import push_provider_status


@api_view(['POST'])
def register_push_device(request):
    token = str(request.data.get('token') or '').strip()
    platform = str(request.data.get('platform') or '').strip().lower()
    app_id = str(request.data.get('app_id') or 'de.aplussolution.workforce').strip()
    device_name = str(request.data.get('device_name') or '').strip()[:200]

    if platform not in {PushDevice.Platform.ANDROID, PushDevice.Platform.IOS}:
        return Response({'detail': 'Ungültige Push-Plattform.'}, status=400)
    if len(token) < 16:
        return Response({'detail': 'Ungültiges Push-Token.'}, status=400)

    device, created = PushDevice.objects.update_or_create(
        token=token,
        defaults={
            'user': request.user,
            'platform': platform,
            'app_id': app_id or 'de.aplussolution.workforce',
            'device_name': device_name,
            'active': True,
            'last_seen_at': timezone.now(),
            'last_error': '',
        },
    )
    return Response({
        'id': str(device.id),
        'created': created,
        'platform': device.platform,
        'active': device.active,
    }, status=201 if created else 200)


@api_view(['POST'])
def unregister_push_device(request):
    token = str(request.data.get('token') or '').strip()
    if not token:
        return Response({'detail': 'Push-Token fehlt.'}, status=400)
    updated = PushDevice.objects.filter(user=request.user, token=token, active=True).update(
        active=False,
        last_seen_at=timezone.now(),
    )
    return Response({'unregistered': bool(updated)})


@api_view(['GET'])
def push_status(request):
    providers = push_provider_status()
    devices = PushDevice.objects.filter(user=request.user, active=True)
    return Response({
        'providers': providers,
        'active_devices': devices.count(),
        'android_devices': devices.filter(platform=PushDevice.Platform.ANDROID).count(),
        'ios_devices': devices.filter(platform=PushDevice.Platform.IOS).count(),
    })
