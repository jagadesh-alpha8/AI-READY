"""Who may act on a fact or a gap, and who may hand it to whom -- the one place this is decided.

The rule (enforced in the fact, gap and evidence-request views; the frontend only mirrors it):
- A fact's `owner_role` is the role responsible for it. Only a user of that role, an Institution Admin
  or InGage staff (super admin / consultant) may confirm, correct or reject it, or decide evidence for it.
- A gap belongs to the role of the fact it is about, else of the document it is about, else (a missing
  document) of the checklist owner of that document type. Only that role, an Institution Admin or InGage
  staff may resolve or close it.
- Work with no recognisable owner role falls to the coordinators: Institution Admin, IQAC Coordinator and
  InGage staff.
- Always within the user's own college (InGage staff: every college). A viewer never acts.

Assignment names the one person expected to do the work, with an optional due date. Coordinators assign,
to an active user of the college who may act on the item (its owner role, or an Institution Admin).
Assigning never widens who may act, and every assignment is kept in the item's history.
"""
from datetime import date

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.permissions import user_can_access_institution

Role = User.Role
STAFF_ROLES = frozenset(User.CROSS_INSTITUTION_ROLES)
#: Act on every fact and gap of their college, whatever its owner role.
OVERRIDE_ROLES = STAFF_ROLES | {Role.IQAC_COORDINATOR}
#: Assign work, see every task of the sprint, and own work that has no owner role.
COORDINATOR_ROLES = OVERRIDE_ROLES


class OwnershipError(Exception):
    """A rule above was broken; the message says who may do it (HTTP 400/403)."""


def normalize_role(value):
    """The User.Role a stored owner role names, or '' when it is not one."""
    slug = (value or '').strip().lower()
    return slug if slug in Role.values else ''


def role_label(role):
    return Role(role).label if role in Role.values else (role or '')


def who_can_act(owner_role):
    """Plain words for the people allowed, for "why can't I" messages."""
    return 'the IQAC Coordinator or InGage staff'


# -- owner of a fact / a gap ------------------------------------------------------------------------

def fact_owner_role(fact):
    return normalize_role(fact.owner_role)


def gap_owner_role(gap):
    if gap.source_fact_id:
        return normalize_role(gap.source_fact.owner_role)
    if gap.related_document_id:
        return normalize_role(gap.related_document.owner_role)
    if gap.gap_type == 'missing_document':
        from apps.gaps.services import missing_document_type
        return checklist_owner_role(missing_document_type(gap))
    return ''


def checklist_owner_role(document_type):
    """The upload checklist's owner for a document type (apps.documents.constants), as a role."""
    from apps.documents.constants import DRIVE_IMPORT_CHECKLIST
    from apps.gaps.services import document_type_variants
    if not document_type:
        return ''
    variants = document_type_variants(document_type)
    for item in DRIVE_IMPORT_CHECKLIST:
        if item['type'] in variants:
            return normalize_role(item.get('owner'))
    return ''


# -- may this user act? -------------------------------------------------------------------------------

def check(user, owner_role, institution_id, *, what='this item'):
    """(allowed, reason). `reason` says who may, when the user may not."""
    if not user_can_access_institution(user, institution_id):
        return False, 'This belongs to another college.'
    if user.role in OVERRIDE_ROLES:
        return True, ''
    if owner_role:
        allowed = user.role == owner_role
    else:
        allowed = user.role in COORDINATOR_ROLES
    return (True, '') if allowed else (False, f'Only {who_can_act(owner_role)} can act on {what}.')
    return (True, '') if allowed else (False, f'Only {who_can_act(owner_role)} can act on {what}.')


def check_fact(user, fact):
    return check(user, fact_owner_role(fact), fact.sprint.institution_id, what='this fact')


def check_gap(user, gap):
    return check(user, gap_owner_role(gap), gap.sprint.institution_id, what='this gap')


def require_fact(user, fact):
    allowed, reason = check_fact(user, fact)
    if not allowed:
        raise OwnershipError(reason)


def require_gap(user, gap):
    allowed, reason = check_gap(user, gap)
    if not allowed:
        raise OwnershipError(reason)


def is_coordinator(user, institution_id):
    return user.role in COORDINATOR_ROLES and user_can_access_institution(user, institution_id)


# -- assignment ------------------------------------------------------------------------------------------

def eligible_assignees(institution_id, owner_role=None):
    """Active users of the college who may act on an item."""
    return (User.objects.filter(institution_id=institution_id, is_active=True, role=Role.IQAC_COORDINATOR)
            .order_by('first_name', 'last_name', 'email'))


def _person(user):
    return {'id': str(user.id), 'name': user.get_full_name() or user.email} if user else None


def assign(item, user, *, assigned_to, due_date=None, note=''):
    """Assign, reassign or unassign (assigned_to=None) a fact or a gap. Returns the item."""
    from apps.gaps.models import GapEvent

    from .models import ExtractedFact, FactReviewHistory

    is_fact = isinstance(item, ExtractedFact)
    owner_role = fact_owner_role(item) if is_fact else gap_owner_role(item)
    institution_id = item.sprint.institution_id
    if not is_coordinator(user, institution_id):
        raise OwnershipError('Only the IQAC Coordinator or InGage staff can assign work.')
    if due_date and due_date < date.today():
        raise OwnershipError('The due date cannot be in the past.')
    assignee = None
    if assigned_to:
        assignee = eligible_assignees(institution_id, owner_role).filter(pk=assigned_to).first()
        if assignee is None:
            raise OwnershipError(f'Assign it to an active user of this college who can act on it: '
                                 f'{who_can_act(owner_role)}.')
    before = item.assigned_to
    change = {'from': _person(before), 'to': _person(assignee), 'due_date': str(due_date) if due_date else None}
    with transaction.atomic():
        item.assigned_to, item.due_date = assignee, due_date
        item.assigned_at = timezone.now() if assignee else None
        item.save(update_fields=['assigned_to', 'due_date', 'assigned_at', 'updated_at'])
        if is_fact:
            FactReviewHistory.objects.create(fact=item, action=FactReviewHistory.Action.ASSIGNED,
                                             original_value=item.value, new_value=change, user=user,
                                             reason=(note or '').strip())
        else:
            GapEvent.objects.create(gap=item, action=GapEvent.Action.ASSIGNED, user=user,
                                    note=(note or '').strip(), data=change)
    return item


def person_name(user):
    return (user.get_full_name() or user.email) if user else ''


def check_conflict_choice(user, gap):
    """(allowed, reason): who may decide which value of a conflict is correct."""
    if user.role in STAFF_ROLES:
        return True, ''
    if user.role == Role.IQAC_COORDINATOR and user.institution_id == gap.sprint.institution_id:
        return True, ''
    return False, 'Only the IQAC Coordinator of this college or InGage staff can choose the correct value of this conflict.'
