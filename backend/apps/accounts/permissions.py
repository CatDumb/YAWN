from rest_framework.permissions import BasePermission


class HasActiveCompanyMembership(BasePermission):
    message = "Active company membership required."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        return user.memberships.filter(is_active=True, company__is_active=True).exists()
