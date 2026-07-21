import uuid

from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("Email address is required.")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(email, password, **extra_fields)

    def get_by_natural_key(self, email):
        return self.get(email__iexact=email)


class Company(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    email_domain = models.CharField(max_length=255, blank=True)
    timezone = models.CharField(max_length=64, default="Asia/Ho_Chi_Minh")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "companies"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.email_domain = self.email_domain.strip().lower()
        super().save(*args, **kwargs)


class User(AbstractUser):
    username = None
    email = models.EmailField(unique=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    def __str__(self):
        return self.email

    def clean(self):
        super().clean()
        self.email = self.__class__.objects.normalize_email(self.email).lower()

    def save(self, *args, **kwargs):
        self.email = self.__class__.objects.normalize_email(self.email).lower()
        super().save(*args, **kwargs)


class CompanyMembership(models.Model):
    class Role(models.TextChoices):
        EMPLOYEE = "employee", "Employee"
        MANAGER = "manager", "Line manager"
        HR_ADMIN = "hr_admin", "HR/admin"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.EMPLOYEE)
    is_active = models.BooleanField(default=True)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "company"],
                name="accounts_membership_user_company_unique",
            )
        ]

    def __str__(self):
        return f"{self.user.email} at {self.company.name}"


class ManagerAssignment(models.Model):
    manager = models.ForeignKey(
        CompanyMembership,
        on_delete=models.CASCADE,
        related_name="managed_assignments",
    )
    employee = models.ForeignKey(
        CompanyMembership,
        on_delete=models.CASCADE,
        related_name="manager_assignments",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["manager", "employee"],
                name="accounts_manager_employee_unique",
            )
        ]

    def __str__(self):
        return f"{self.manager.user.email} manages {self.employee.user.email}"

    def clean(self):
        if self.manager_id == self.employee_id:
            raise ValidationError("Manager and employee must be different memberships.")
        if self.manager.company_id != self.employee.company_id:
            raise ValidationError("Manager and employee must belong to the same company.")
        if self.manager.role not in {
            CompanyMembership.Role.MANAGER,
            CompanyMembership.Role.HR_ADMIN,
        }:
            raise ValidationError("Manager membership must have manager or HR/admin role.")


class AccessRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="access_requests",
    )
    email = models.EmailField(db_index=True)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    request_fingerprint = models.CharField(max_length=64, db_index=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewer = models.ForeignKey(
        "User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_access_requests",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "email"],
                condition=Q(status="pending"),
                name="accounts_pending_access_request_unique",
            )
        ]
        indexes = [
            models.Index(
                fields=["company", "email", "created_at"],
                name="access_company_email_idx",
            ),
            models.Index(
                fields=["company", "request_fingerprint", "created_at"],
                name="access_company_fingerprint_idx",
            ),
        ]

    def __str__(self):
        return f"{self.email} access request for {self.company.name}"

    def save(self, *args, **kwargs):
        self.email = User.objects.normalize_email(self.email).lower()
        super().save(*args, **kwargs)


class EmailOTPChallenge(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="otp_challenges",
        null=True,
        blank=True,
    )
    email = models.EmailField(db_index=True)
    code_hash = models.CharField(max_length=128)
    request_fingerprint = models.CharField(max_length=64, db_index=True)
    attempt_count = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    expires_at = models.DateTimeField(db_index=True)
    consumed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["email", "created_at"], name="otp_email_created_idx"),
        ]

    def __str__(self):
        return f"OTP challenge {self.pk}"
