"""Reusable role- and institution-scoped DRF permission classes.

Two kinds of check live here:

- Role gates (IsSuperAdmin, IsConsultant, ..., CanManageSprint, ...): does
  this user's `role` allow this kind of action at all?
- Institution scoping (IsInstitutionMember, user_can_access_institution,
  get_accessible_institution_ids): given the user passed a role gate, are
  they allowed to touch *this particular* institution's data? Cross-campus
  roles (super_admin, consultant) see everything; everyone else is
  confined to the institution on their own profile.

Views combine both: a role gate in `permission_classes`, plus a queryset
filtered by `get_accessible_institution_ids` (for list endpoints) or an
explicit `user_can_access_institution` check (for the nested sprint
sub-resource endpoints, which look up their sprint manually instead of via
DRF's generic `get_object()`).
"""
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import SAFE_METHODS, BasePermission

from .models import User

MANAGE_SPRINT_ROLES = {User.Role.SUPER_ADMIN, User.Role.CONSULTANT, User.Role.INSTITUTION_ADMIN}
MANAGE_RECOMMENDATION_ROLES = {
    User.Role.SUPER_ADMIN, User.Role.CONSULTANT, User.Role.INSTITUTION_ADMIN, User.Role.IQAC_COORDINATOR,
}
#: Editing a recommendation's content (title/description/priority/...) is
#: narrower than viewing or generating one -- only InGage's own consultants
#: (and platform super admins) are trusted to rewrite the engine's output,
#: not every institution-side role that can view it.
EDIT_RECOMMENDATION_ROLES = {User.Role.SUPER_ADMIN, User.Role.CONSULTANT}
# Every role can review facts / resolve gaps except the read-only viewer persona.
REVIEW_ROLES = set(User.Role.values) - {User.Role.VIEWER}


def _is_authenticated(request):
    return bool(request.user and request.user.is_authenticated)


class IsSuperAdmin(BasePermission):
    message = 'This action requires a super admin account.'

    def has_permission(self, request, view):
        return _is_authenticated(request) and request.user.role == User.Role.SUPER_ADMIN


class IsConsultant(BasePermission):
    message = 'This action requires an InGage consultant account.'

    def has_permission(self, request, view):
        return _is_authenticated(request) and request.user.role == User.Role.CONSULTANT


class IsInstitutionAdmin(BasePermission):
    message = 'This action requires an institution admin account.'

    def has_permission(self, request, view):
        return _is_authenticated(request) and request.user.role == User.Role.INSTITUTION_ADMIN


class IsReadOnly(BasePermission):
    """Grants access for safe (GET/HEAD/OPTIONS) methods only."""

    def has_permission(self, request, view):
        return request.method in SAFE_METHODS


class IsInstitutionMember(BasePermission):
    """Object-level check: user belongs to the object's institution.

    Cross-institution roles (super_admin, consultant) always pass. Works
    against an Institution instance directly, anything with an
    `institution`/`institution_id` attribute (e.g. Sprint), or anything
    nested under a sprint (e.g. Document, ExtractedFact, GapItem — via `.sprint`).
    """
    message = 'You do not have access to this institution.'

    def has_permission(self, request, view):
        return _is_authenticated(request)

    def has_object_permission(self, request, view, obj):
        return user_can_access_institution(request.user, _resolve_institution_id(obj))


class CanManageSprint(BasePermission):
    """Anyone authenticated can read; only sprint-owning roles can write."""
    message = 'You do not have permission to create or modify discovery sprints.'

    def has_permission(self, request, view):
        if not _is_authenticated(request):
            return False
        if request.method in SAFE_METHODS:
            return True
        return request.user.role in MANAGE_SPRINT_ROLES


class CanApproveBaseline(BasePermission):
    """Anyone can read a sprint's baseline; only sprint-owning roles (the
    same set as CanManageSprint) may submit/approve/return it -- baseline
    approval is a sprint-management decision, not a review action every
    non-viewer role gets (unlike CanReviewFacts/CanResolveGaps)."""
    message = "You do not have permission to approve this sprint's baseline."

    def has_permission(self, request, view):
        if not _is_authenticated(request):
            return False
        if request.method in SAFE_METHODS:
            return True
        return request.user.role in MANAGE_SPRINT_ROLES


class CanReviewFacts(BasePermission):
    message = 'You do not have permission to review extracted facts.'

    def has_permission(self, request, view):
        if not _is_authenticated(request):
            return False
        if request.method in SAFE_METHODS:
            return True
        return request.user.role in REVIEW_ROLES


class CanResolveGaps(BasePermission):
    message = 'You do not have permission to resolve data gaps.'

    def has_permission(self, request, view):
        if not _is_authenticated(request):
            return False
        if request.method in SAFE_METHODS:
            return True
        return request.user.role in REVIEW_ROLES


class CanManageRecommendations(BasePermission):
    message = 'You do not have permission to manage recommendations.'

    def has_permission(self, request, view):
        if not _is_authenticated(request):
            return False
        if request.method in SAFE_METHODS:
            return True
        return request.user.role in MANAGE_RECOMMENDATION_ROLES


class CanEditRecommendation(BasePermission):
    """Gate for PATCH .../recommendations/{id}/ specifically -- narrower
    than CanManageRecommendations (which also allows generating them)."""
    message = 'Only InGage consultants can edit recommendations.'

    def has_permission(self, request, view):
        if not _is_authenticated(request):
            return False
        if request.method in SAFE_METHODS:
            return True
        return request.user.role in EDIT_RECOMMENDATION_ROLES


def _resolve_institution_id(obj):
    from apps.institutions.models import Institution

    if isinstance(obj, Institution):
        return obj.pk
    if hasattr(obj, 'institution_id'):
        return obj.institution_id
    sprint = getattr(obj, 'sprint', None)
    if sprint is not None:
        return sprint.institution_id
    return None


def user_can_access_institution(user, institution_id):
    if institution_id is None:
        return False
    if user.role in User.CROSS_INSTITUTION_ROLES:
        return True
    return user.institution_id is not None and user.institution_id == institution_id


def get_accessible_institution_ids(user):
    """None means "no restriction" (cross-institution role); otherwise a set of allowed ids."""
    if user.role in User.CROSS_INSTITUTION_ROLES:
        return None
    return {user.institution_id} if user.institution_id else set()


def require_institution_access(user, obj):
    """Raise 403 unless `user` may access the institution that owns `obj`."""
    if not user_can_access_institution(user, _resolve_institution_id(obj)):
        raise PermissionDenied('You do not have access to this institution.')
