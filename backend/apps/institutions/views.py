from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, viewsets
from rest_framework.filters import OrderingFilter
from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.accounts.models import User
from apps.accounts.permissions import (
    IsInstitutionMember,
    get_accessible_institution_ids,
    require_institution_access,
)
from config.pagination import OptionalPageNumberPagination

from .filters import InstitutionFilter
from .models import Institution
from .serializers import (
    DepartmentSerializer,
    InstitutionDetailSerializer,
    InstitutionLeaderSerializer,
    InstitutionSerializer,
    InstitutionSystemSerializer,
)

WRITE_INSTITUTION_ROLES = {User.Role.SUPER_ADMIN, User.Role.CONSULTANT, User.Role.INSTITUTION_ADMIN}
DELETE_INSTITUTION_ROLES = {User.Role.SUPER_ADMIN, User.Role.CONSULTANT}


class CanManageInstitution(BasePermission):
    message = 'You do not have permission to manage institutions.'

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return True
        if request.method == 'DELETE':
            return request.user.role in DELETE_INSTITUTION_ROLES
        return request.user.role in WRITE_INSTITUTION_ROLES


class InstitutionViewSet(viewsets.ModelViewSet):
    """CRUD for institutions, scoped to the ones a user is authorized to see.

    Cross-institution roles (super_admin, consultant) see every institution;
    everyone else only sees the one on their own profile. Deletion is a soft
    delete (is_active=False) so existing sprints keep a valid institution
    reference.
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

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=['is_active', 'updated_at'])


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
