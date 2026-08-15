from rest_framework.permissions import BasePermission

from .workplace_access import has_capability


class IsAdminOrManager(BasePermission):
    """Backward-compatible manager gate with optional capability enforcement.

    Views can set ``required_capability``. Legacy manager surfaces without that
    attribute still require the explicit ``manager.access`` capability.
    """

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.user.role == 'admin' or request.user.is_superuser:
            return True
        if request.user.role != 'manager':
            return False
        capability = getattr(view, 'required_capability', 'manager.access')
        return has_capability(request.user, capability)


class HasCapability(BasePermission):
    def has_permission(self, request, view):
        capability = getattr(view, 'required_capability', None)
        return bool(capability and has_capability(request.user, capability))


class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user.is_authenticated and (request.user.role == 'admin' or request.user.is_superuser))
