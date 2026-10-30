from django.db import transaction
from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.filters import OrderingFilter
from rest_framework.permissions import SAFE_METHODS, AllowAny, BasePermission
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.accounts.permissions import (
    IsInstitutionMember,
    get_accessible_institution_ids,
    require_institution_access,
)
from config.pagination import OptionalPageNumberPagination

from . import coordinator as coordinator_service
from .deletion import get_institution_deletion_dependencies
from .filters import InstitutionFilter
from .models import Institution
from .serializers import (
    DepartmentSerializer,
    InstitutionDetailSerializer,
    InstitutionLeaderSerializer,
    InstitutionSerializer,
    InstitutionSystemSerializer,
)

WRITE_INSTITUTION_ROLES = {User.Role.SUPER_ADMIN, User.Role.CONSULTANT, User.Role.IQAC_COORDINATOR}
DELETE_INSTITUTION_ROLES = {User.Role.SUPER_ADMIN}
#: Creating a college names and invites its IQAC Coordinator, so it is InGage staff's job (as is changing the
#: coordinator). A college's own coordinator edits its profile, never creates another college.
CREATE_INSTITUTION_ROLES = {User.Role.SUPER_ADMIN, User.Role.CONSULTANT}


class CanManageInstitution(BasePermission):
    message = 'You do not have permission to manage institutions.'

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return True
        if request.method == 'DELETE':
            return request.user.role in DELETE_INSTITUTION_ROLES
        if request.method == 'POST' and getattr(view, 'action', None) == 'create':
            return request.user.role in CREATE_INSTITUTION_ROLES
        return request.user.role in WRITE_INSTITUTION_ROLES


class InstitutionViewSet(viewsets.ModelViewSet):
    """CRUD for institutions, scoped to the ones a user is authorized to see.

    Cross-institution roles (super_admin, consultant) see every institution;
    everyone else only sees the one on their own profile. Deletion is a hard
    delete: the institution and everything that hangs off it (departments,
    leaders, systems, sprints, and every document/fact/gap/score/
    recommendation/report scoped to those sprints) is removed for good — see
    `perform_destroy`.
    """
    serializer_class = InstitutionSerializer
    permission_classes = [CanManageInstitution, IsInstitutionMember]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_class = InstitutionFilter
    ordering_fields = ['name', 'city', 'state', 'created_at', 'updated_at']
    ordering = ['name']
    pagination_class = OptionalPageNumberPagination

    def get_queryset(self):
        qs = Institution.objects.all()
        # Only the list action filters by accessible institutions. Detail
        # actions (retrieve/update/destroy) intentionally use the unscoped
        # queryset and rely on IsInstitutionMember's has_object_permission
        # for a real 403 on out-of-scope institutions, rather than a
        # queryset-driven 404 that would mask an authorization failure as
        # "not found".
        if self.action == 'list':
            allowed_ids = get_accessible_institution_ids(self.request.user)
            if allowed_ids is not None:
                qs = qs.filter(id__in=allowed_ids)
        if self.action == 'retrieve':
            qs = qs.prefetch_related('leaders', 'departments')
        return qs

    def get_serializer_class(self):
        # Only the single-record read pays for leaders, derived counts and the
        # maturity rubric; a list of institutions has no use for any of it.
        if self.action == 'retrieve':
            return InstitutionDetailSerializer
        return InstitutionSerializer

    def create(self, request, *args, **kwargs):
        """The institution, its IQAC Coordinator and the invitation are saved together (all or nothing); the
        invitation email goes out only after they are committed. A failed email never undoes the institution --
        the response says so and the coordinator can be re-invited (POST .../coordinator/resend)."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        name, email = data.pop('coordinator_name'), data.pop('coordinator_email')
        with transaction.atomic():
            institution = Institution.objects.create(created_by=request.user, **data)
            invitation, token = coordinator_service.assign(institution, name, email, request.user)
        sent = coordinator_service.deliver(invitation, token, request.user) if invitation is not None else False
        institution.refresh_from_db()
        body = self.get_serializer(institution).data
        body['invitation_email_sent'] = sent
        return Response(body, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'], url_path='deletion-preview')
    def deletion_preview(self, request, pk=None):
        """Provide a backend-generated preview of all related dependencies before deletion."""
        institution = self.get_object()
        preview = get_institution_deletion_dependencies(institution)
        return Response(preview)

    @action(detail=True, methods=['get'], url_path='delete-preview')
    def delete_preview(self, request, pk=None):
        """Alias for deletion-preview."""
        return self.deletion_preview(request, pk)

    @action(detail=True, methods=['post'], url_path='archive')
    def archive(self, request, pk=None):
        """Deactivate/archive an institution to preserve assessment evidence and audit history."""
        institution = self.get_object()
        institution.is_active = False
        institution.save(update_fields=['is_active', 'updated_at'])
        return Response(self.get_serializer(institution).data)

    @action(detail=True, methods=['post'], url_path='unarchive')
    def unarchive(self, request, pk=None):
        """Reactivate an archived institution."""
        institution = self.get_object()
        institution.is_active = True
        institution.save(update_fields=['is_active', 'updated_at'])
        return Response(self.get_serializer(institution).data)

    def destroy(self, request, *args, **kwargs):
        """Safe transactional deletion of an institution.

        Enforces:
        1. Super Admin authorization (DELETE_INSTITUTION_ROLES).
        2. Institution boundary checks (IsInstitutionMember).
        3. Transactional dependency checking with row locking to eliminate race conditions.
        4. Permanent deletion is blocked with 409 Conflict if protected records exist.
        5. Any ProtectedError raised during deletion is caught and surfaced as a clean 409 Conflict.
        """
        if request.user.role != User.Role.SUPER_ADMIN:
            raise PermissionDenied('Only Super Admins can permanently delete institutions.')

        instance = self.get_object()

        with transaction.atomic():
            locked_inst = Institution.objects.select_for_update().get(pk=instance.pk)
            preview = get_institution_deletion_dependencies(locked_inst)

            if not preview['can_delete']:
                return Response(
                    {
                        'detail': preview['block_reason'],
                        'error_code': 'INSTITUTION_DELETE_BLOCKED',
                        'can_delete': False,
                        'block_reason': preview['block_reason'],
                        'recommended_action': preview['recommended_action'],
                        'dependencies': preview['dependencies'],
                        'protected_counts': preview['protected_counts'],
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            try:
                locked_inst.delete()
            except ProtectedError as exc:
                blockers = sorted({type(obj).__name__ for obj in exc.protected_objects})
                return Response(
                    {
                        'detail': (
                            f"Cannot delete institution because it is referenced through protected foreign keys: "
                            f"{', '.join(blockers)}. Archive it instead."
                        ),
                        'error_code': 'PROTECTED_DEPENDENCIES_EXIST',
                        'can_delete': False,
                        'block_reason': f"Protected references detected: {', '.join(blockers)}.",
                        'recommended_action': 'archive',
                        'dependencies': preview['dependencies'],
                        'protected_counts': preview['protected_counts'],
                    },
                    status=status.HTTP_409_CONFLICT,
                )

        return Response(status=status.HTTP_204_NO_CONTENT)


class CanManageInstitutionDna(BasePermission):
    """Write access to an institution's DNA sub-resources.

    Deliberately NOT `CanManageInstitution`: that class restricts DELETE to
    super admins and consultants, because deleting an *institution* orphans
    every sprint hanging off it. Removing one department or one system is an
    ordinary correction to a list the institution admin maintains, so DELETE
    here follows the same rule as any other write.
    """
    message = 'You do not have permission to manage this institution\'s profile.'

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return True
        return request.user.role in WRITE_INSTITUTION_ROLES


class InstitutionScopedMixin:
    """Shared plumbing for the Institution DNA sub-resources.

    Each one is addressed as `/institutions/{institution_id}/<thing>`, so the
    institution is resolved and authorized once here, and every queryset is
    scoped to it — which is what makes an id belonging to another institution
    a 404 on this route rather than something to be checked for separately.
    """
    permission_classes = [CanManageInstitutionDna]
    related_name = ''

    def get_institution(self):
        institution = get_object_or_404(Institution, pk=self.kwargs['institution_id'])
        require_institution_access(self.request.user, institution)
        return institution

    def get_queryset(self):
        return getattr(self.get_institution(), self.related_name).all()

    def get_serializer_context(self):
        # DepartmentSerializer validates its name against the institution's
        # existing departments, so it needs the institution, not just the row.
        context = super().get_serializer_context()
        if self.kwargs.get('institution_id'):
            context['institution'] = self.get_institution()
        return context

    def perform_create(self, serializer):
        serializer.save(institution=self.get_institution())


class InstitutionLeaderListCreateView(InstitutionScopedMixin, generics.ListCreateAPIView):
    serializer_class = InstitutionLeaderSerializer
    related_name = 'leaders'


class InstitutionLeaderDetailView(InstitutionScopedMixin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = InstitutionLeaderSerializer
    related_name = 'leaders'


class DepartmentListCreateView(InstitutionScopedMixin, generics.ListCreateAPIView):
    serializer_class = DepartmentSerializer
    related_name = 'departments'


class DepartmentDetailView(InstitutionScopedMixin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = DepartmentSerializer
    related_name = 'departments'


class InstitutionSystemListCreateView(InstitutionScopedMixin, generics.ListCreateAPIView):
    serializer_class = InstitutionSystemSerializer
    related_name = 'systems'


class InstitutionSystemDetailView(InstitutionScopedMixin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = InstitutionSystemSerializer
    related_name = 'systems'


# -- IQAC Coordinator -----------------------------------------------------------------------------------

class CoordinatorInputSerializer(serializers.Serializer):
    coordinator_name = serializers.CharField(max_length=150, allow_blank=True)
    coordinator_email = serializers.CharField(max_length=254, allow_blank=True)


def _staff_institution(request, institution_id):
    institution = get_object_or_404(Institution, pk=institution_id)
    require_institution_access(request.user, institution)
    if request.user.role not in CREATE_INSTITUTION_ROLES:
        raise PermissionDenied("Only InGage staff can name or invite a college's IQAC Coordinator.")
    return institution


class InstitutionCoordinatorView(APIView):
    """GET  /institutions/<id>/coordinator -- the coordinator, invitation state and audit history (members).
    POST /institutions/<id>/coordinator -- name / change the coordinator (InGage staff): a different email
    revokes the pending invitation and invites the new person; the same email only corrects the name."""

    def get(self, request, institution_id):
        institution = get_object_or_404(Institution, pk=institution_id)
        require_institution_access(request.user, institution)
        events = [{'action': e.action, 'label': e.get_action_display(), 'note': e.note,
                   'user_name': (e.user.get_full_name() or e.user.email) if e.user_id else '',
                   'created_at': e.created_at} for e in institution.coordinator_events.select_related('user')]
        staff = request.user.role in CREATE_INSTITUTION_ROLES
        return Response({**coordinator_service.status_of(institution, for_staff=staff), 'events': events})

    def post(self, request, institution_id):
        institution = _staff_institution(request, institution_id)
        body = CoordinatorInputSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                invitation, token = coordinator_service.assign(
                    Institution.objects.select_for_update().get(pk=institution.pk),
                    body.validated_data['coordinator_name'], body.validated_data['coordinator_email'],
                    request.user, refuse_unavailable=True)
        except coordinator_service.CoordinatorError as exc:
            raise ValidationError({exc.field or 'detail': [str(exc)]})
        sent = coordinator_service.deliver(invitation, token, request.user) if invitation is not None else None
        institution.refresh_from_db()
        return Response({**coordinator_service.status_of(institution, for_staff=True),
                         'invitation_email_sent': sent, 'changed': invitation is not None})


class InstitutionCoordinatorResendView(APIView):
    """POST /institutions/<id>/coordinator/resend -- a new link on the same invitation (InGage staff)."""

    def post(self, request, institution_id):
        institution = _staff_institution(request, institution_id)
        try:
            invitation = coordinator_service.resend(institution, request.user)
        except coordinator_service.CoordinatorError as exc:
            raise ValidationError({'detail': [str(exc)]})
        institution.refresh_from_db()
        return Response({**coordinator_service.status_of(institution, for_staff=True),
                         'invitation_email_sent': invitation.delivery == invitation.Delivery.SENT})


# -- the invitation link (public) ------------------------------------------------------------------------

class InvitationTokenSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=128)
    new_password = serializers.CharField(required=False, allow_blank=True, write_only=True,
                                         trim_whitespace=False)


class _PublicInvitationView(APIView):
    """POST only (the token never lands in a URL the server logs), throttled per client address."""
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'invitation'


class InvitationCheckView(_PublicInvitationView):
    """POST /auth/invitation {token} -> the college and person, and whether a password must be chosen."""

    def post(self, request):
        body = InvitationTokenSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            return Response(coordinator_service.describe(body.validated_data['token']))
        except coordinator_service.CoordinatorError as exc:
            raise ValidationError({'token': [str(exc)]})


class InvitationAcceptView(_PublicInvitationView):
    """POST /auth/invitation/accept {token, new_password?} -> activates / links the account (single use)."""

    def post(self, request):
        body = InvitationTokenSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            user = coordinator_service.accept(body.validated_data['token'],
                                              body.validated_data.get('new_password') or None)
        except coordinator_service.InvalidToken as exc:
            raise ValidationError({'token': [str(exc)]})
        except coordinator_service.CoordinatorError as exc:
            raise ValidationError({'new_password': [str(exc)]})
        return Response({'detail': 'Your IQAC Coordinator access is ready. Sign in to continue.',
                         'email': user.email})
