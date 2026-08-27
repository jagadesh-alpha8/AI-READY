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
        INSTITUTION_ADMIN = 'institution_admin', 'Institution Admin'
        IQAC_COORDINATOR = 'iqac_coordinator', 'IQAC Coordinator'
        REGISTRAR = 'registrar', 'Registrar'
        HOD = 'hod', 'Head of Department'
        HR_OFFICER = 'hr_officer', 'HR Officer'
        LAB_ADMIN = 'lab_admin', 'Lab Admin'
        PLACEMENT_OFFICER = 'placement_officer', 'Placement Officer'
        FACULTY = 'faculty', 'Faculty'
        VIEWER = 'viewer', 'Viewer'

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
    role = models.CharField(max_length=32, choices=Role.choices, default=Role.VIEWER)
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
