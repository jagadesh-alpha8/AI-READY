"""Follow-up to 0003: every role in the data is one of the three platform roles.

0003 converted the known lower-case legacy roles. Production data can also hold other spellings ('HOD',
'Registrar', 'RESEARCH_CELL', ...) and former viewer accounts kept the role 'viewer'. This migration:

- users: any role other than super_admin / consultant / iqac_coordinator becomes iqac_coordinator. A user who is
  deactivated stays deactivated (former viewers were deactivated by 0003 on purpose -- reactivating one now
  grants IQAC Coordinator access, so it is noted in the audit and the department name). Every change is a
  RoleMigrationAudit row with the original role.
- owner roles on facts, evidence requests and recommendations: anything other than the three (any case)
  becomes 'iqac_coordinator'; on documents (stored upper-case) 'IQAC_COORDINATOR'. Blank stays blank.

Idempotent: running it again changes nothing. Reverse restores the users' roles from the audit only.
"""
from django.db import migrations

PLATFORM_ROLES = ('super_admin', 'consultant', 'iqac_coordinator')


def _legacy(qs, field):
    """Rows whose `field` is set and is not one of the platform roles, ignoring case."""
    keep = qs.none()
    rows = qs.exclude(**{field: ''})
    for role in PLATFORM_ROLES:
        keep = keep | rows.filter(**{f'{field}__iexact': role})
    return rows.exclude(pk__in=keep.values('pk'))


def forward(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    Audit = apps.get_model('accounts', 'RoleMigrationAudit')
    users = 0
    for user in User.objects.exclude(role__in=PLATFORM_ROLES):
        original = user.role
        note = f'Converted remaining role {original!r} to iqac_coordinator (3-role follow-up).'
        if not user.is_active:
            note += ' Account stays deactivated; reactivating it grants IQAC Coordinator access.'
            dept = user.department_name or ''
            if 'former' not in dept.lower():
                user.department_name = f'{dept} [Deactivated former {original}]'.strip()[:150]
        user.role = 'iqac_coordinator'
        user.save(update_fields=['role', 'department_name'])
        Audit.objects.create(user_id=user.id, email=user.email, username=user.username, original_role=original,
                             new_role='iqac_coordinator', original_is_active=user.is_active,
                             new_is_active=user.is_active, notes=note)
        users += 1

    counts = {'users': users}
    for label, model, field, value in (
            ('facts', apps.get_model('facts', 'ExtractedFact'), 'owner_role', 'iqac_coordinator'),
            ('evidence_requests', apps.get_model('facts', 'EvidenceRequest'), 'suggested_owner_role',
             'iqac_coordinator'),
            ('recommendations', apps.get_model('recommendations', 'Recommendation'), 'owner_role',
             'iqac_coordinator'),
            ('documents', apps.get_model('documents', 'Document'), 'owner_role', 'IQAC_COORDINATOR')):
        changed = _legacy(model.objects.all(), field).update(**{field: value})
        # Platform roles in the other case ('IQAC_COORDINATOR' on a fact) get the table's own spelling.
        changed += model.objects.filter(**{f'{field}__iexact': 'iqac_coordinator'}).exclude(
            **{field: value}).update(**{field: value})
        counts[label] = changed
    print(f'\n3-role follow-up: {counts}')


def reverse(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    Audit = apps.get_model('accounts', 'RoleMigrationAudit')
    for record in Audit.objects.filter(notes__startswith='Converted remaining role'):
        User.objects.filter(id=record.user_id).update(role=record.original_role)


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_rename_accounts_us_user_id_4407b8_idx_accounts_us_user_id_f73d7a_idx_and_more'),
        ('facts', '0014_evidence_assessment_retry'),
        ('documents', '0006_sprint_processing'),
        ('recommendations', '0002_aiqif_pillar_choices'),
    ]

    operations = [migrations.RunPython(forward, reverse)]
