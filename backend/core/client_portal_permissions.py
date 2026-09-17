from rest_framework.permissions import SAFE_METHODS, IsAuthenticated


class ClientPortalRestrictionPermission(IsAuthenticated):
    """Hard-stop read-only scoped client accounts outside their permitted shift view."""

    READ_ONLY_PATHS = {
        '/api/auth/me',
        '/api/portal/client-access',
        '/api/portal/client-dashboard',
        '/api/portal/client-shifts',
    }

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        user = request.user
        if getattr(user, 'role', None) != 'client':
            return True

        try:
            from .client_portal_access import is_read_only_client
            restricted = is_read_only_client(user)
        except Exception:
            restricted = False
        if not restricted:
            return True

        path = request.path.rstrip('/') or '/'
        return request.method in SAFE_METHODS and path in self.READ_ONLY_PATHS
