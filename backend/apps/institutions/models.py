import uuid

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models

phone_validator = RegexValidator(
    regex=r'^\+?[0-9 ()-]{7,20}$',
    message='Enter a valid phone number.',
)


class Institution(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    short_name = models.CharField(max_length=50, blank=True)
    institution_type = models.CharField(max_length=255, blank=True)
    university_affiliation = models.CharField(max_length=255, blank=True)
    website_url = models.URLField(blank=True)
    location = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=120, blank=True)
    state = models.CharField(max_length=120, blank=True)
    country = models.CharField(max_length=120, blank=True, default='India')
    accreditation_details = models.TextField(blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=20, blank=True, validators=[phone_validator])
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='created_institutions',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name
