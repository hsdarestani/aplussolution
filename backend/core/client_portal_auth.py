from django.contrib.auth import authenticate
from django.db.models import Q
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from .models import User
from .serializers import UserSerializer


@api_view(['POST'])
@permission_classes([AllowAny])
def login(request):
    identifier = str(request.data.get('email') or request.data.get('username') or '').strip()
    password = request.data.get('password')
    if not identifier or not password:
        return Response({'detail': 'Benutzername/E-Mail oder Passwort ist falsch.'}, status=400)

    user = User.objects.filter(
        Q(email__iexact=identifier) | Q(username__iexact=identifier),
        is_active=True,
    ).order_by('date_joined').first()
    if not user:
        return Response({'detail': 'Benutzername/E-Mail oder Passwort ist falsch.'}, status=400)

    authenticated = authenticate(request, username=user.email, password=password)
    if not authenticated:
        return Response({'detail': 'Benutzername/E-Mail oder Passwort ist falsch.'}, status=400)

    refresh = RefreshToken.for_user(authenticated)
    return Response({
        'access': str(refresh.access_token),
        'refresh': str(refresh),
        'user': UserSerializer(authenticated, context={'request': request}).data,
    })
