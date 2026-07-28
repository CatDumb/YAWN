# ruff: noqa: DJ012

from calendar import monthrange
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import Company, CompanyMembership


class EffectiveDatedModel(models.Model):
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)

    class Meta:
        abstract = True

    def clean(self):
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValidationError("End date cannot be before start date.")


class FiscalPeriod(models.Model):  # noqa: DJ012
    class State(models.TextChoices):
        UPCOMING = "upcoming", "Upcoming"
        ACTIVE = "active", "Active"
        RECONCILIATION = "reconciliation", "Reconciliation"
        FINAL = "final", "Final"

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="fiscal_periods")
    name = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField()
    reconciliation_cutoff = models.DateTimeField(blank=True)
    state = models.CharField(max_length=20, choices=State.choices, default=State.UPCOMING)
    reopened_at = models.DateTimeField(null=True, blank=True)
    reopened_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reopened_periods",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-start_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "name"], name="work_logs_period_company_name_unique"
            ),
            models.UniqueConstraint(
                fields=["company"], condition=Q(state="active"), name="work_logs_one_active_period"
            ),
        ]

    def clean(self):
        if not self.reconciliation_cutoff and self.end_date:
            cutoff_day = self.end_date + timedelta(days=14)
            self.reconciliation_cutoff = timezone.make_aware(
                datetime.combine(cutoff_day, time.max), ZoneInfo(settings.TIME_ZONE)
            )
        if self.end_date < self.start_date:
            raise ValidationError("Period end date cannot be before start date.")
        if self.reconciliation_cutoff.date() < self.end_date:
            raise ValidationError("Reconciliation cutoff cannot precede period end date.")
        overlaps = (
            FiscalPeriod.objects.filter(company=self.company)
            .exclude(pk=self.pk)
            .filter(start_date__lte=self.end_date, end_date__gte=self.start_date)
        )
        if overlaps.exists():
            raise ValidationError("Fiscal periods cannot overlap.")

    def save(self, *args, **kwargs):
        if not self.reconciliation_cutoff and self.end_date:
            cutoff_day = self.end_date + timedelta(days=14)
            self.reconciliation_cutoff = timezone.make_aware(
                datetime.combine(cutoff_day, time.max), ZoneInfo(settings.TIME_ZONE)
            )
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.company}: {self.name}"

    @property
    def derived_state(self):
        today = timezone.localdate()
        if self.state == self.State.FINAL:
            return self.State.FINAL
        if today < self.start_date:
            return self.State.UPCOMING
        if today <= self.end_date:
            return self.State.ACTIVE
        return self.State.RECONCILIATION


class BaseLocation(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="base_locations")
    name = models.CharField(max_length=120)
    code = models.SlugField(max_length=40)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "code"], name="work_logs_location_code_unique"
            )
        ]

    def __str__(self):
        return self.name


class Project(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="projects")
    name = models.CharField(max_length=160)
    code = models.SlugField(max_length=40)
    base_location = models.ForeignKey(
        BaseLocation, on_delete=models.PROTECT, related_name="projects"
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "code"], name="work_logs_project_code_unique"
            )
        ]

    def clean(self):
        if self.base_location_id and self.base_location.company_id != self.company_id:
            raise ValidationError("Project and base location must belong to the same company.")

    def __str__(self):
        return self.name


class EmployeeProjectAssignment(EffectiveDatedModel):
    employee = models.ForeignKey(
        CompanyMembership, on_delete=models.PROTECT, related_name="project_assignments"
    )
    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name="assignments")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-effective_from"]

    def clean(self):
        super().clean()
        if self.pk and WorkInOfficeRecord.objects.filter(assignment_snapshot__id=self.pk).exists():
            raise ValidationError("Historically used assignments cannot be changed.")
        if (
            self.employee_id
            and self.project_id
            and self.employee.company_id != self.project.company_id
        ):
            raise ValidationError("Employee and project must belong to the same company.")
        overlaps = (
            EmployeeProjectAssignment.objects.filter(employee=self.employee)
            .exclude(pk=self.pk)
            .filter(
                effective_from__lte=self.effective_to or date.max,
            )
            .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=self.effective_from))
        )
        if overlaps.exists():
            raise ValidationError("Employee project assignments cannot overlap.")

    def __str__(self):
        return f"{self.employee} / {self.project}"

    def delete(self, *args, **kwargs):
        if WorkInOfficeRecord.objects.filter(assignment_snapshot__id=self.pk).exists():
            raise ValidationError("Historically used assignments cannot be deleted.")
        return super().delete(*args, **kwargs)


class ProjectStatusRule(EffectiveDatedModel):
    class AssignmentStatus(models.TextChoices):
        BENCHED = "benched", "Benched"
        SAME_BASE = "same_base", "Same base"
        DIFFERENT_BASE = "different_base", "Different base"

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="project_status_rules"
    )
    assignment_status = models.CharField(max_length=20, choices=AssignmentStatus.choices)
    expected_fraction = models.DecimalField(max_digits=4, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        super().clean()
        if (
            self.pk
            and WorkInOfficeRecord.objects.filter(policy_snapshot__rule__id=self.pk).exists()
        ):
            raise ValidationError("Historically used policy rules cannot be changed.")
        if not 0 <= self.expected_fraction <= 1:
            raise ValidationError("Expected fraction must be between zero and one.")
        overlaps = (
            ProjectStatusRule.objects.filter(
                company=self.company, assignment_status=self.assignment_status
            )
            .exclude(pk=self.pk)
            .filter(effective_from__lte=self.effective_to or date.max)
            .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=self.effective_from))
        )
        if overlaps.exists():
            raise ValidationError("Policy rule versions cannot overlap.")

    def __str__(self):
        return f"{self.company}: {self.assignment_status}"

    def delete(self, *args, **kwargs):
        if WorkInOfficeRecord.objects.filter(policy_snapshot__rule__id=self.pk).exists():
            raise ValidationError("Historically used policy rules cannot be deleted.")
        return super().delete(*args, **kwargs)


class CompanyHoliday(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="holidays")
    date = models.DateField()
    name = models.CharField(max_length=120)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "date"], name="work_logs_holiday_unique")
        ]

    def __str__(self):
        return f"{self.date}: {self.name}"


class EmployeeExclusion(EffectiveDatedModel):
    employee = models.ForeignKey(
        CompanyMembership, on_delete=models.CASCADE, related_name="%(class)s_records"
    )
    reason = models.CharField(max_length=240)
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True


class ApprovedLeave(EmployeeExclusion):
    def __str__(self):
        return f"{self.employee}: {self.reason}"


class RemoteWorkException(EmployeeExclusion):
    def __str__(self):
        return f"{self.employee}: {self.reason}"


class WorkInOfficeRecord(models.Model):
    class LocationChoice(models.TextChoices):
        IN_OFFICE = "in_office", "In office"
        NOT_IN_OFFICE = "not_in_office", "Not in office"

    class ReviewState(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING = "pending", "Pending"
        PENDING_ASSIGNMENT = "pending_assignment", "Pending assignment"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        NOT_REQUIRED = "not_required", "Not required"
        EXPIRED_PENDING = "expired_pending", "Expired pending"

    employee = models.ForeignKey(
        CompanyMembership, on_delete=models.PROTECT, related_name="wio_records"
    )
    work_date = models.DateField()
    location_choice = models.CharField(
        max_length=20, choices=LocationChoice.choices, null=True, blank=True
    )
    review_state = models.CharField(
        max_length=20, choices=ReviewState.choices, default=ReviewState.DRAFT
    )
    note = models.CharField(max_length=500, blank=True)
    approver_note = models.CharField(max_length=500, blank=True)
    rejected_at = models.DateTimeField(null=True, blank=True)
    correction_deadline = models.DateTimeField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)
    assignment_snapshot = models.JSONField(default=dict, blank=True)
    policy_snapshot = models.JSONField(default=dict, blank=True)
    approval_owner_snapshot = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by_snapshot = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-work_date", "-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "work_date"], name="work_logs_one_record_per_employee_day"
            )
        ]

    def clean(self):
        if self.note and self.location_choice != self.LocationChoice.IN_OFFICE:
            raise ValidationError("A note is only available for In office records.")
        if self.review_state == self.ReviewState.APPROVED and self.pk:
            old = WorkInOfficeRecord.objects.get(pk=self.pk)
            if old.location_choice != self.location_choice or old.note != self.note:
                raise ValidationError("Approved records are immutable.")

    def __str__(self):
        return f"{self.employee} / {self.work_date}"

    @property
    def is_locked(self):
        return self.review_state in {
            self.ReviewState.PENDING,
            self.ReviewState.PENDING_ASSIGNMENT,
            self.ReviewState.APPROVED,
            self.ReviewState.EXPIRED_PENDING,
        }


class WioTransitionBaseline(models.Model):
    """One-time aggregate carry-forward from the predecessor WIO system."""

    employee = models.OneToOneField(
        CompanyMembership,
        on_delete=models.PROTECT,
        related_name="transition_baseline",
    )
    period = models.ForeignKey(
        FiscalPeriod,
        on_delete=models.PROTECT,
        related_name="transition_baselines",
    )
    cutoff_date = models.DateField()
    target_days = models.DecimalField(max_digits=10, decimal_places=2)
    achieved_days = models.DecimalField(max_digits=10, decimal_places=2)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(target_days__gte=0),
                name="work_logs_transition_target_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(achieved_days__gte=0),
                name="work_logs_transition_achieved_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(target_days__gt=0) | Q(achieved_days=0),
                name="work_logs_transition_zero_target_zero_achieved",
            ),
        ]

    def clean(self):
        super().clean()
        if (
            self.employee_id
            and self.period_id
            and self.employee.company_id != self.period.company_id
        ):
            raise ValidationError(
                "Transition baseline and fiscal period must belong to one company."
            )
        if (
            self.cutoff_date
            and self.cutoff_date.day != monthrange(self.cutoff_date.year, self.cutoff_date.month)[1]
        ):
            raise ValidationError("Transition cutoff must be the final day of its month.")
        if self.target_days == 0 and self.achieved_days != 0:
            raise ValidationError("Achieved days must be zero when target days are zero.")

    def __str__(self):
        return f"{self.employee} transition through {self.cutoff_date}"


class FiscalFinalizationStep(models.Model):
    """Idempotent, audited finalization checkpoint for a fiscal period."""

    period = models.ForeignKey(
        FiscalPeriod, on_delete=models.CASCADE, related_name="finalization_steps"
    )
    key = models.CharField(max_length=80)
    completed_at = models.DateTimeField(null=True, blank=True)
    effect_token = models.UUIDField(null=True, blank=True, unique=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["period", "key"], name="work_logs_finalization_step_unique"
            )
        ]

    def __str__(self):
        return f"{self.period}: {self.key}"


class FinalizedLedgerRevision(models.Model):
    period = models.ForeignKey(
        FiscalPeriod, on_delete=models.PROTECT, related_name="ledger_revisions"
    )
    employee = models.ForeignKey(
        CompanyMembership, on_delete=models.PROTECT, related_name="ledger_revisions"
    )
    revision = models.PositiveIntegerField(default=1)
    predecessor = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="successors"
    )
    summary = models.JSONField(default=dict)
    ledger = models.JSONField(default=list)
    input_versions = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["period", "employee", "revision"], name="work_logs_ledger_revision_unique"
            )
        ]

    def __str__(self):
        return f"{self.period} / {self.employee} / r{self.revision}"


class WorkIntentionSeries(models.Model):
    employee = models.ForeignKey(
        CompanyMembership, on_delete=models.CASCADE, related_name="intention_series"
    )
    location = models.CharField(max_length=12, choices=[("office", "Office"), ("home", "Home")])
    commitment = models.CharField(
        max_length=12, choices=[("firm", "Firm"), ("flexible", "Flexible")]
    )
    weekdays = models.JSONField(default=list, blank=True)
    starts_on = models.DateField()
    ends_on = models.DateField()
    note = models.CharField(max_length=300, blank=True)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.employee} intention series from {self.starts_on}"


class WorkIntentionOccurrence(models.Model):
    employee = models.ForeignKey(
        CompanyMembership, on_delete=models.CASCADE, related_name="intentions"
    )
    date = models.DateField()
    location = models.CharField(max_length=12, choices=[("office", "Office"), ("home", "Home")])
    commitment = models.CharField(
        max_length=12, choices=[("firm", "Firm"), ("flexible", "Flexible")]
    )
    note = models.CharField(max_length=300, blank=True)
    series = models.ForeignKey(
        WorkIntentionSeries,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="occurrences",
    )
    excluded_reason = models.CharField(max_length=240, blank=True)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "date"], name="work_logs_one_intention_per_employee_day"
            )
        ]

    def __str__(self):
        return f"{self.employee} intention on {self.date}"
