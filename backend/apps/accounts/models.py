import uuid

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.validators import RegexValidator
from django.db import models

phone_validator = RegexValidator(
    regex=r'^\+?[0-9 ()-]{7,20}$',
    message='Enter a valid phone number.',
)


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Users must have an email address')
        email = self.normalize_email(email)
        extra_fields.setdefault('username', email.split('@')[0])
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('role', User.Role.SUPER_ADMIN)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    class Role(models.TextChoices):
        SUPER_ADMIN = 'super_admin', 'Super Admin'
        CONSULTANT = 'consultant', 'InGage Consultant'
        IQAC_COORDINATOR = 'iqac_coordinator', 'IQAC Coordinator'

    #: Roles that operate across every institution rather than being scoped
    #: to the one on their profile (platform staff, not campus staff).
    CROSS_INSTITUTION_ROLES = (Role.SUPER_ADMIN, Role.CONSULTANT)

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    username = models.CharField(
        max_length=150, unique=True, validators=[UnicodeUsernameValidator()],
    )
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    phone = models.CharField(max_length=20, blank=True, validators=[phone_validator])
    role = models.CharField(max_length=32, choices=Role.choices, default=Role.IQAC_COORDINATOR)
    institution = models.ForeignKey(
        'institutions.Institution',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='users',
    )
    department_name = models.CharField(max_length=255, blank=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    class Meta:
        ordering = ['email']

    def __str__(self):
        return f'{self.get_full_name()} ({self.email})'

    def get_full_name(self):
        full_name = f'{self.first_name} {self.last_name}'.strip()
        return full_name or self.username

    def get_short_name(self):
        return self.first_name or self.username

    @property
    def is_cross_institution(self):
        return self.role in self.CROSS_INSTITUTION_ROLES


class RoleMigrationAudit(models.Model):
    """Audit record capturing the consolidation of user roles to the 3-role model."""
    migrated_at = models.DateTimeField(auto_now_add=True)
    user_id = models.UUIDField()
    email = models.CharField(max_length=255)
    username = models.CharField(max_length=150)
    original_role = models.CharField(max_length=64)
    new_role = models.CharField(max_length=64)
    original_is_active = models.BooleanField()
    new_is_active = models.BooleanField()
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-migrated_at']

    def __str__(self):
        return f'{self.email}: {self.original_role} -> {self.new_role} (active={self.new_is_active})'


class UserDeletionAuditEvent(models.Model):
    """Append-only identity snapshot for a permanently deleted user.

    User FKs are deliberately avoided: the event must remain after its target
    account is removed, and should not itself prevent deletion.
    """
    actor_user_id = models.UUIDField()
    actor_email = models.EmailField()
    target_user_id = models.UUIDField()
    target_email = models.EmailField()
    target_username = models.CharField(max_length=150)
    target_full_name = models.CharField(max_length=300, blank=True)
    target_role = models.CharField(max_length=32)
    target_institution_id = models.UUIDField(null=True, blank=True)
    target_institution_name = models.CharField(max_length=255, blank=True)
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.target_email} permanently deleted by {self.actor_email}'

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            from django.core.exceptions import ValidationError
            raise ValidationError('User deletion audit events are append-only.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        from django.core.exceptions import ValidationError
        raise ValidationError('User deletion audit events are append-only.')


class UserGuideState(models.Model):
    """Persisted in-app onboarding guide choices for a user.

    Scoped by user, institution, and optionally sprint.
    Records which steps the user has skipped, and whether the guide card is
    dismissed. Actual completion is NEVER stored here -- completion is always
    derived dynamically from the real underlying database records.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='guide_states')
    institution = models.ForeignKey(
        'institutions.Institution', on_delete=models.CASCADE, null=True, blank=True, related_name='guide_states'
    )
    sprint = models.ForeignKey(
        'sprints.Sprint', on_delete=models.CASCADE, null=True, blank=True, related_name='guide_states'
    )
    skipped_steps = models.JSONField(default=list, blank=True)
    is_dismissed = models.BooleanField(default=False)
    dismissed_at = models.DateTimeField(null=True, blank=True)
    menu_tours = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['user', 'institution', 'sprint']),
        ]

    def __str__(self):
        return f'UserGuideState({self.user_id}, inst={self.institution_id}, sprint={self.sprint_id})'

