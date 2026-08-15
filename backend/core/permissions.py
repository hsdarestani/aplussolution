from rest_framework.permissions import BasePermission

from .workplace_access import has_capability


SAFE_METHODS = {'GET', 'HEAD', 'OPTIONS'}


def inferred_capability(request, view):
    explicit = getattr(view, 'required_capability', None)
    if explicit:
        return explicit
    path = request.path.lower()
    safe = request.method in SAFE_METHODS
    action = str(getattr(view, 'action', '') or '').lower()

    if '/pay-periods/' in path or '/timesheets/' in path or '/timesheet-entries/' in path or '/timesheet-exceptions/' in path:
        if 'export' in action or 'export-' in path:
            return 'payroll.export'
        return 'payroll.view' if safe else 'payroll.review'
    if '/scheduling/' in path or '/schedule-' in path or '/shifts/' in path or '/operations/copy-week/' in path or '/operations/bulk-publish/' in path:
        if 'publish' in action or 'publish' in path:
            return 'schedule.publish'
        return 'schedule.view' if safe else 'schedule.edit'
    if '/attendance/' in path or '/attendance-' in path or '/time-entries/' in path:
        return 'attendance.view' if safe else 'attendance.edit'
    if '/workers/' in path or '/users/' in path:
        return 'people.view' if safe else 'people.edit'
    if '/clients/' in path or '/orders/' in path:
        return 'clients.view' if safe else 'clients.edit'
    if '/document' in path or '/contract' in path:
        return 'manager.access' if safe else 'documents.manage'
    if '/reports/' in path:
        return 'reports.view'
    return 'manager.access'


class IsAdminOrManager(BasePermission):
    """Manager gate backed by granular workplace capabilities.

    New views may declare ``required_capability`` explicitly. Existing manager
    endpoints are mapped from their route so custom roles are enforced without
    relying on UI-only hiding.
    """

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.user.role == 'admin' or request.user.is_superuser:
            return True
        if request.user.role != 'manager':
            return False
        return has_capability(request.user, inferred_capability(request, view))


class HasCapability(BasePermission):
    def has_permission(self, request, view):
        capability = getattr(view, 'required_capability', None)
        return bool(capability and has_capability(request.user, capability))


class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user.is_authenticated and (request.user.role == 'admin' or request.user.is_superuser))
