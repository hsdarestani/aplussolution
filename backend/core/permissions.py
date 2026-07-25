from rest_framework.permissions import BasePermission
class IsAdminOrManager(BasePermission):
    def has_permission(self,request,view): return bool(request.user.is_authenticated and request.user.role in {'admin','manager'})
class IsAdmin(BasePermission):
    def has_permission(self,request,view): return bool(request.user.is_authenticated and request.user.role=='admin')
