from django.db.models import Q
from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import ManagerAssignment
from apps.work_logs.models import (
    EmployeeBaseLocationAssignment,
    EmployeeProjectAssignment,
    ProjectBaseLocationAssignment,
    ProjectStatusRule,
)
from apps.work_logs.services import company_today
from apps.work_logs.views import membership_for


def effective(queryset, today):
    return (
        queryset.filter(effective_from__lte=today)
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=today))
        .first()
    )


class ProfileView(APIView):
    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        membership = membership_for(request.user)
        today = company_today(membership.company)
        manager = effective(
            ManagerAssignment.objects.select_related("manager__user").filter(
                employee=membership,
                is_active=True,
                manager__company=membership.company,
                manager__is_active=True,
                manager__user__is_active=True,
            ),
            today,
        )
        assignment = effective(
            EmployeeProjectAssignment.objects.select_related("project").filter(employee=membership),
            today,
        )
        employee_location = effective(
            EmployeeBaseLocationAssignment.objects.select_related("base_location").filter(
                employee=membership
            ),
            today,
        )
        project_location = (
            effective(
                ProjectBaseLocationAssignment.objects.filter(project=assignment.project),
                today,
            )
            if assignment
            else None
        )
        employee_location_value = (
            employee_location.base_location if employee_location else membership.base_location
        )
        project_location_id = (
            project_location.base_location_id
            if project_location
            else assignment.project.base_location_id
            if assignment
            else None
        )
        status = "benched"
        if assignment and project_location_id == (
            employee_location_value.pk if employee_location_value else None
        ):
            status = "same_base"
        elif assignment:
            status = "different_base"
        policy = effective(
            ProjectStatusRule.objects.filter(company=membership.company, assignment_status=status),
            today,
        )
        return Response(
            {
                "legal_name": request.user.get_full_name(),
                "email": request.user.email,
                "company": membership.company.name,
                "role": membership.role,
                "base_location": (
                    employee_location_value.name if employee_location_value else None
                ),
                "manager": (
                    {
                        "name": manager.manager.user.get_full_name(),
                        "effective_from": manager.effective_from,
                        "effective_to": manager.effective_to,
                    }
                    if manager
                    else None
                ),
                "project_assignment": (
                    {
                        "project": assignment.project.name,
                        "effective_from": assignment.effective_from,
                        "effective_to": assignment.effective_to,
                    }
                    if assignment
                    else None
                ),
                "policy": (
                    {
                        "assignment_status": status,
                        "expected_fraction": str(policy.expected_fraction),
                        "effective_from": policy.effective_from,
                        "effective_to": policy.effective_to,
                    }
                    if policy
                    else {"assignment_status": status}
                ),
            }
        )
