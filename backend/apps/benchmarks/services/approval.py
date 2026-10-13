"""Approving a source version (draft -> active) and withdrawing one.

An active version is the official one; approving it supersedes the
previously active version of the same document. After that its content is
frozen (see SourceVersion.save).
"""
from django.db import transaction
from django.utils import timezone

from ..models import SourceAuditEvent, SourceVersion


class ApprovalError(Exception):
    def __init__(self, message, flags=None):
        super().__init__(message)
        self.flags = flags or []


def approval_blockers(version):
    """Hard reasons a version can't be approved (flags are separate: they can be acknowledged)."""
    blockers = []
    if version.status != SourceVersion.Status.DRAFT:
        blockers.append(f'Only a draft can be approved (this one is {version.status}).')
    if version.collection_status == SourceVersion.Collection.DOWNLOADED:
        if not version.file_uri or version.intake_status not in (SourceVersion.Intake.VERIFIED,
                                                                 SourceVersion.Intake.COMPUTED):
            blockers.append('The file has not been stored and checksum-checked yet (run file intake).')
    elif version.collection_status in (SourceVersion.Collection.TO_FIND, SourceVersion.Collection.NOT_AVAILABLE,
                                       SourceVersion.Collection.BLOCKED):
        blockers.append(f'Nothing collected yet ({version.get_collection_status_display()}).')
    if version.version_label == SourceVersion.UNVERSIONED:
        blockers.append('No version / edition recorded.')
    return blockers


def approve(version, user, *, note='', acknowledge_flags=False):
    blockers = approval_blockers(version)
    if blockers:
        raise ApprovalError(' '.join(blockers))
    if version.review_flags and not acknowledge_flags:
        raise ApprovalError('This version has open review flags; check them and approve with acknowledgement.',
                            flags=version.review_flags)
    with transaction.atomic():
        now = timezone.now()
        previous = (SourceVersion.objects.select_for_update()
                    .filter(document=version.document, status=SourceVersion.Status.ACTIVE).exclude(pk=version.pk))
        for old in previous:
            old.status = SourceVersion.Status.SUPERSEDED
            old.effective_to = old.effective_to or (version.effective_from or now.date())
            old.save()
            SourceAuditEvent.objects.create(actor=user.email, action='version.superseded', object_type='SourceVersion',
                                            object_id=str(old.pk), after={'by': str(version.pk)}, reason=note)
            version.supersedes = version.supersedes or old
        version.status, version.approved_by, version.approved_at = SourceVersion.Status.ACTIVE, user, now
        version.save()
        SourceAuditEvent.objects.create(
            actor=user.email, action='version.approved', object_type='SourceVersion', object_id=str(version.pk),
            after={'status': 'active', 'acknowledged_flags': version.review_flags if acknowledge_flags else []},
            reason=note)
    return version


def withdraw(version, user, *, note):
    if version.status != SourceVersion.Status.ACTIVE:
        raise ApprovalError(f'Only an active version can be withdrawn (this one is {version.status}).')
    if not note.strip():
        raise ApprovalError('Give a reason for withdrawing.')
    version.status = SourceVersion.Status.WITHDRAWN
    version.effective_to = version.effective_to or timezone.now().date()
    version.save()
    SourceAuditEvent.objects.create(actor=user.email, action='version.withdrawn', object_type='SourceVersion',
                                    object_id=str(version.pk), reason=note)
    return version
