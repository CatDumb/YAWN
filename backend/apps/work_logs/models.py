# ruff: noqa: DJ012

from calendar import monthrange
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import Company, CompanyMembership

_final_period_mutation_allowed = ContextVar(
    "final_period_mutation_allowed",
    default=False,
)


@contextmanager
def _allow_final_period_mutation():
    token = _final_period_mutation_allowed.set(True)
    try:
        yield
    finally:
        _final_period_mutation_allowed.reset(token)


class EffectiveDatedModel(models.Model):
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)

    class Meta:
        abstract = True

    def clean(self):
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValidationError("End date cannot be before start date.")

    def _validate_started_version(self, *, company, immutable_fields, label):
        if not self.pk:
            return
        original = type(self).objects.filter(pk=self.pk).first()
        if original is None:
            return
        today = timezone.now().astimezone(ZoneInfo(company.timezone)).date()
        if original.effective_from > today:
            return
        changed = any(
            getattr(original, field) != getattr(self, field) for field in immutable_fields
        )
        end_changed = original.effective_to != self.effective_to
        unsafe_end_change = end_changed and (
            (original.effective_to is not None and original.effective_to < today)
            or self.effective_to is None
            or self.effective_to < today
        )
        if changed or unsafe_end_change:
            raise ValidationError(
                f"Started {label} versions are immutable; append a future-dated correction."
            )

    def _started(self, *, company):
        today = timezone.now().astimezone(ZoneInfo(company.timezone)).date()
        return self.effective_from <= today


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
                datetime.combine(cutoff_day, time.max), ZoneInfo(self.company.timezone)
            )
        if self.end_date < self.start_date:
            raise ValidationError("Period end date cannot be before start date.")
        cutoff_date = self.reconciliation_cutoff.astimezone(ZoneInfo(self.company.timezone)).date()
        if cutoff_date < self.end_date:
            raise ValidationError("Reconciliation cutoff cannot precede period end date.")
        overlaps = (
            FiscalPeriod.objects.filter(company=self.company)
            .exclude(pk=self.pk)
            .filter(start_date__lte=self.end_date, end_date__gte=self.start_date)
        )
        if overlaps.exists():
            raise ValidationError("Fiscal periods cannot overlap.")

    def save(self, *args, **kwargs):
        with transaction.atomic():
            original_company_id = (
                FiscalPeriod.objects.filter(pk=self.pk).values_list("company_id", flat=True).first()
                if self.pk
                else None
            )
            company_ids = {self.company_id}
            if original_company_id is not None:
                company_ids.add(original_company_id)
            list(Company.objects.select_for_update().filter(pk__in=company_ids).order_by("pk"))
            if self.pk:
                original = FiscalPeriod.objects.select_for_update().filter(pk=self.pk).first()
                if original is None:
                    raise RuntimeError("Fiscal period was deleted while acquiring its lock.")
                if original.company_id != original_company_id:
                    raise RuntimeError("Fiscal period changed while acquiring its company lock.")
                protected_fields = (
                    "company_id",
                    "start_date",
                    "end_date",
                    "reconciliation_cutoff",
                    "state",
                )
                protected_change = any(
                    getattr(original, field) != getattr(self, field) for field in protected_fields
                )
                if (
                    original.state == self.State.FINAL
                    and protected_change
                    and not _final_period_mutation_allowed.get()
                ):
                    raise ValidationError(
                        "Final fiscal period boundaries and state can only change through "
                        "the audited reopen service."
                    )
            if not self.reconciliation_cutoff and self.end_date:
                cutoff_day = self.end_date + timedelta(days=14)
                self.reconciliation_cutoff = timezone.make_aware(
                    datetime.combine(cutoff_day, time.max), ZoneInfo(self.company.timezone)
                )
            self.full_clean()
            super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.company}: {self.name}"

    @property
    def derived_state(self):
        today = timezone.now().astimezone(ZoneInfo(self.company.timezone)).date()
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


class EmployeeBaseLocationAssignment(EffectiveDatedModel):
    employee = models.ForeignKey(
        CompanyMembership,
        on_delete=models.PROTECT,
        related_name="base_location_assignments",
    )
    base_location = models.ForeignKey(
        BaseLocation,
        on_delete=models.PROTECT,
        related_name="employee_assignments",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-effective_from"]

    def clean(self):
        super().clean()
        if self.employee_id:
            self._validate_started_version(
                company=self.employee.company,
                immutable_fields=("employee_id", "base_location_id", "effective_from"),
                label="employee base-location",
            )
        if self.employee_id and self.base_location_id:
            if self.employee.company_id != self.base_location.company_id:
                raise ValidationError("Employee and base location must belong to the same company.")
        overlaps = (
            EmployeeBaseLocationAssignment.objects.filter(employee=self.employee)
            .exclude(pk=self.pk)
            .filter(effective_from__lte=self.effective_to or date.max)
            .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=self.effective_from))
        )
        if overlaps.exists():
            raise ValidationError("Employee base-location assignments cannot overlap.")

    @transaction.atomic
    def save(self, *args, **kwargs):
        CompanyMembership.objects.select_for_update().get(pk=self.employee_id)
        self.full_clean()
        super().save(*args, **kwargs)
        today = timezone.now().astimezone(ZoneInfo(self.employee.company.timezone)).date()
        if self.effective_from <= today and (
            self.effective_to is None or self.effective_to >= today
        ):
            CompanyMembership.objects.filter(pk=self.employee_id).update(
                base_location_id=self.base_location_id
            )

    @transaction.atomic
    def delete(self, *args, **kwargs):
        CompanyMembership.objects.select_for_update().get(pk=self.employee_id)
        if self._started(company=self.employee.company):
            raise ValidationError("Started employee base-location versions cannot be deleted.")
        return super().delete(*args, **kwargs)

    def __str__(self):
        return f"{self.employee} / {self.base_location}"


class ProjectBaseLocationAssignment(EffectiveDatedModel):
    project = models.ForeignKey(
        Project,
        on_delete=models.PROTECT,
        related_name="base_location_assignments",
    )
    base_location = models.ForeignKey(
        BaseLocation,
        on_delete=models.PROTECT,
        related_name="project_assignments",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-effective_from"]

    def clean(self):
        super().clean()
        if self.project_id:
            self._validate_started_version(
                company=self.project.company,
                immutable_fields=("project_id", "base_location_id", "effective_from"),
                label="project base-location",
            )
        if self.project_id and self.base_location_id:
            if self.project.company_id != self.base_location.company_id:
                raise ValidationError("Project and base location must belong to the same company.")
        overlaps = (
            ProjectBaseLocationAssignment.objects.filter(project=self.project)
            .exclude(pk=self.pk)
            .filter(effective_from__lte=self.effective_to or date.max)
            .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=self.effective_from))
        )
        if overlaps.exists():
            raise ValidationError("Project base-location assignments cannot overlap.")

    @transaction.atomic
    def save(self, *args, **kwargs):
        Project.objects.select_for_update().get(pk=self.project_id)
        self.full_clean()
        super().save(*args, **kwargs)
        today = timezone.now().astimezone(ZoneInfo(self.project.company.timezone)).date()
        if self.effective_from <= today and (
            self.effective_to is None or self.effective_to >= today
        ):
            Project.objects.filter(pk=self.project_id).update(
                base_location_id=self.base_location_id
            )

    @transaction.atomic
    def delete(self, *args, **kwargs):
        Project.objects.select_for_update().get(pk=self.project_id)
        if self._started(company=self.project.company):
            raise ValidationError("Started project base-location versions cannot be deleted.")
        return super().delete(*args, **kwargs)

    def __str__(self):
        return f"{self.project} / {self.base_location}"


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
        if self.employee_id:
            self._validate_started_version(
                company=self.employee.company,
                immutable_fields=("employee_id", "project_id", "effective_from"),
                label="employee project-assignment",
            )
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

    @transaction.atomic
    def save(self, *args, **kwargs):
        CompanyMembership.objects.select_for_update().get(pk=self.employee_id)
        self.full_clean()
        return super().save(*args, **kwargs)

    @transaction.atomic
    def delete(self, *args, **kwargs):
        CompanyMembership.objects.select_for_update().get(pk=self.employee_id)
        if (
            self._started(company=self.employee.company)
            or WorkInOfficeRecord.objects.filter(assignment_snapshot__id=self.pk).exists()
        ):
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
        if self.company_id:
            self._validate_started_version(
                company=self.company,
                immutable_fields=(
                    "company_id",
                    "assignment_status",
                    "expected_fraction",
                    "effective_from",
                ),
                label="policy-rule",
            )
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

    @transaction.atomic
    def save(self, *args, **kwargs):
        Company.objects.select_for_update().get(pk=self.company_id)
        self.full_clean()
        return super().save(*args, **kwargs)

    @transaction.atomic
    def delete(self, *args, **kwargs):
        Company.objects.select_for_update().get(pk=self.company_id)
        live_period_uses_rule = FiscalPeriod.objects.filter(
            company=self.company,
            state__in=(FiscalPeriod.State.ACTIVE, FiscalPeriod.State.RECONCILIATION),
            start_date__lte=self.effective_to or date.max,
            end_date__gte=self.effective_from,
        ).exists()
        if (
            self._started(company=self.company)
            or live_period_uses_rule
            or WorkInOfficeRecord.objects.filter(policy_snapshot__rule__id=self.pk).exists()
        ):
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

    class ApprovalMethod(models.TextChoices):
        MANAGER_APPROVED = "manager_approved", "Manager approved"
        SELF_APPROVED = "self_approved", "Self approved"

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
    approval_method = models.CharField(
        max_length=24, choices=ApprovalMethod.choices, null=True, blank=True
    )

    class Meta:
        ordering = ["-work_date", "-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "work_date"], name="work_logs_one_record_per_employee_day"
            ),
            models.CheckConstraint(
                condition=(
                    Q(review_state="approved", approval_method__isnull=False)
                    | (~Q(review_state="approved") & Q(approval_method__isnull=True))
                ),
                name="work_logs_approval_method_matches_state",
            ),
        ]

    def clean(self):
        if self.note and self.location_choice != self.LocationChoice.IN_OFFICE:
            raise ValidationError("A note is only available for In office records.")
        if self.pk:
            old = WorkInOfficeRecord.objects.get(pk=self.pk)
            protected_fields = (
                "employee_id",
                "work_date",
                "location_choice",
                "review_state",
                "note",
                "approver_note",
                "rejected_at",
                "correction_deadline",
                "version",
                "assignment_snapshot",
                "policy_snapshot",
                "approval_owner_snapshot",
                "created_at",
                "submitted_at",
                "approved_at",
                "approved_by_snapshot",
                "approval_method",
            )
            if old.review_state == self.ReviewState.APPROVED and any(
                getattr(old, field) != getattr(self, field) for field in protected_fields
            ):
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
    class LocationChoice(models.TextChoices):
        OFFICE = "office", "Office"
        HOME = "home", "Home"

    class CommitmentChoice(models.TextChoices):
        FIRM = "firm", "Firm"
        FLEXIBLE = "flexible", "Flexible"

    employee = models.ForeignKey(
        CompanyMembership, on_delete=models.CASCADE, related_name="intention_series"
    )
    location = models.CharField(max_length=12, choices=LocationChoice.choices)
    commitment = models.CharField(max_length=12, choices=CommitmentChoice.choices)
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
    location = models.CharField(
        max_length=12,
        choices=WorkIntentionSeries.LocationChoice.choices,
    )
    commitment = models.CharField(
        max_length=12,
        choices=WorkIntentionSeries.CommitmentChoice.choices,
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
