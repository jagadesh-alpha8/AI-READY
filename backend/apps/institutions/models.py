import uuid

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models

phone_validator = RegexValidator(
    regex=r'^\+?[0-9 ()-]{7,20}$',
    message='Enter a valid phone number.',
)


class Institution(models.Model):
    class DigitalMaturity(models.IntegerChoices):
        MANUAL = 1, 'Level 1 — Manual'
        PARTIAL_DIGITAL = 2, 'Level 2 — Partial Digital'
        INTEGRATED = 3, 'Level 3 — Integrated'
        DATA_DRIVEN = 4, 'Level 4 — Data-Driven'
        AI_ENABLED = 5, 'Level 5 — AI-Enabled'

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

    # -- Institution DNA: profile ------------------------------------------
    # Institution-wide headcounts as the institution itself reports them.
    # Stored rather than summed from Department rows on purpose: an official
    # total legitimately differs from the sum of whichever departments have
    # been entered so far, and reporting a partial sum as the institution's
    # total would be wrong rather than merely incomplete. Department and
    # programme counts ARE derived (see the serializer) — those are counts of
    # rows this app owns, so a stored copy could only drift.
    student_count = models.PositiveIntegerField(null=True, blank=True)
    faculty_count = models.PositiveIntegerField(null=True, blank=True)

    #: Free-text strategic priorities, rendered as tags (e.g. "NAAC
    #: Re-accreditation 2025"). A JSON list rather than its own table: these
    #: are labels with no attributes, relationships, or lifecycle of their
    #: own — the same reasoning behind Document.ocr_warnings.
    priorities = models.JSONField(default=list, blank=True)

    # -- Institution DNA: systems & IT --------------------------------------
    digital_maturity_level = models.PositiveSmallIntegerField(
        choices=DigitalMaturity.choices, null=True, blank=True,
    )
    current_ai_usage = models.TextField(blank=True)

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


class InstitutionLeader(models.Model):
    """One named person on the institution's leadership list.

    Deliberately not a link to `accounts.User`: the Director or Dean named
    here is a fact about the institution's org chart, and recording them must
    not depend on whether they happen to hold a login on this platform.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    institution = models.ForeignKey(Institution, on_delete=models.CASCADE, related_name='leaders')
    name = models.CharField(max_length=255)
    role = models.CharField(max_length=150)
    email = models.EmailField(blank=True)
    display_order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['display_order', 'name']

    def __str__(self):
        return f'{self.name} — {self.role}'


class Department(models.Model):
    """An academic department, with the headcounts it reports for itself.

    These counts are the department's own figures, not a share of the
    institution's — see `Institution.student_count` on why the two are stored
    separately rather than one being derived from the other.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    institution = models.ForeignKey(Institution, on_delete=models.CASCADE, related_name='departments')
    name = models.CharField(max_length=150)
    head_name = models.CharField(max_length=255, blank=True)
    faculty_count = models.PositiveIntegerField(default=0)
    student_count = models.PositiveIntegerField(default=0)
    program_count = models.PositiveIntegerField(default=0)
    display_order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['display_order', 'name']
        constraints = [
            models.UniqueConstraint(
                fields=['institution', 'name'], name='unique_department_name_per_institution',
            ),
        ]

    def __str__(self):
        return self.name


class InstitutionSystem(models.Model):
    """One system in the institution's current IT estate.

    `tag` marks the two states that matter to an AI-readiness assessment — a
    legacy system and a still-manual process are both obstacles — and is blank
    for everything else. It is not a general-purpose category field.
    """
    class Tag(models.TextChoices):
        LEGACY = 'legacy', 'Legacy'
        MANUAL = 'manual', 'Manual'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    institution = models.ForeignKey(Institution, on_delete=models.CASCADE, related_name='systems')
    name = models.CharField(max_length=200)
    tag = models.CharField(max_length=20, choices=Tag.choices, blank=True)
    notes = models.CharField(max_length=500, blank=True)
    display_order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['display_order', 'name']

    def __str__(self):
        return self.name
