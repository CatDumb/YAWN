from django.urls import path

from apps.work_logs.dashboard_views import (
    DashboardActivityView,
    DashboardHeatmapView,
    DashboardRatioView,
    DashboardTodayView,
)
from apps.work_logs.planner_views import (
    PlannerIntentionDetailView,
    PlannerIntentionsView,
    PlannerPreviewView,
    PlannerProjectionView,
)
from apps.work_logs.profile_views import ProfileView
from apps.work_logs.report_views import ReportCSVView, ReportView
from apps.work_logs.transition_views import TransitionBaselineView
from apps.work_logs.views import (
    ApprovalAssigneeView,
    ApprovalCountView,
    ApprovalDecisionView,
    ApprovalOwnershipQueueView,
    ApprovalQueueView,
    ApprovalTimelineView,
    PendingAssignmentQueueView,
    SelfApprovalUndoView,
    WorkInOfficeDetailView,
    WorkInOfficeListCreateView,
    WorkInOfficeMetadataView,
    WorkInOfficeTimelineView,
)

urlpatterns = [
    path("work-in-office/", WorkInOfficeListCreateView.as_view(), name="work-in-office-list"),
    path("work-in-office/meta/", WorkInOfficeMetadataView.as_view(), name="work-in-office-meta"),
    path(
        "work-in-office/<int:pk>/", WorkInOfficeDetailView.as_view(), name="work-in-office-detail"
    ),
    path(
        "work-in-office/<int:pk>/undo-self-approval/",
        SelfApprovalUndoView.as_view(),
        name="work-in-office-undo-self-approval",
    ),
    path(
        "work-in-office/<int:pk>/timeline/",
        WorkInOfficeTimelineView.as_view(),
        name="work-in-office-timeline",
    ),
    path("approvals/", ApprovalQueueView.as_view(), name="approval-queue"),
    path(
        "approvals/pending-assignment/",
        PendingAssignmentQueueView.as_view(),
        name="pending-assignment-queue",
    ),
    path("approvals/assignees/", ApprovalAssigneeView.as_view(), name="approval-assignees"),
    path("approvals/count/", ApprovalCountView.as_view(), name="approval-count"),
    path(
        "approvals/ownership/",
        ApprovalOwnershipQueueView.as_view(),
        name="approval-ownership-queue",
    ),
    path(
        "approvals/<int:pk>/timeline/",
        ApprovalTimelineView.as_view(),
        name="approval-timeline",
    ),
    path(
        "approvals/<int:pk>/<str:action>/", ApprovalDecisionView.as_view(), name="approval-decision"
    ),
    path("reports/", ReportView.as_view(), name="report"),
    path("reports/csv/", ReportCSVView.as_view(), name="report-csv"),
    path(
        "transition-baseline/",
        TransitionBaselineView.as_view(),
        name="transition-baseline",
    ),
    path("planner/", PlannerIntentionsView.as_view(), name="planner-intentions"),
    path(
        "planner/<int:pk>/",
        PlannerIntentionDetailView.as_view(),
        name="planner-intention-detail",
    ),
    path("planner/preview/", PlannerPreviewView.as_view(), name="planner-preview"),
    path("planner/projection/", PlannerProjectionView.as_view(), name="planner-projection"),
    path("profile/", ProfileView.as_view(), name="profile"),
    path("dashboard/today/", DashboardTodayView.as_view(), name="dashboard-today"),
    path("dashboard/ratio/", DashboardRatioView.as_view(), name="dashboard-ratio"),
    path("dashboard/activity/", DashboardActivityView.as_view(), name="dashboard-activity"),
    path("dashboard/heatmap/", DashboardHeatmapView.as_view(), name="dashboard-heatmap"),
]
