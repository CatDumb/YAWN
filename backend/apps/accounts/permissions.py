from rest_framework.permissions import BasePermission

from apps.accounts.models import CompanyMembership


class HasActiveCompanyMembership(BasePermission):
    message = "Active company membership required."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        return user.memberships.filter(is_active=True, company__is_active=True).exists()


class HasCompanyRole(BasePermission):
    allowed_roles: frozenset[str] = frozenset()

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        return user.memberships.filter(
            is_active=True,
            company__is_active=True,
            role__in=self.allowed_roles,
        ).exists()


class IsManagerOrHRAdmin(HasCompanyRole):
    allowed_roles = frozenset(
        {
            CompanyMembership.Role.MANAGER,
            CompanyMembership.Role.HR_ADMIN,
        }
    )


class IsHRAdmin(HasCompanyRole):
    allowed_roles = frozenset({CompanyMembership.Role.HR_ADMIN})
