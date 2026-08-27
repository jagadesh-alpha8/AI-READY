from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.filters import OrderingFilter
from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.accounts.models import User
from apps.accounts.permissions import IsInstitutionMember, get_accessible_institution_ids
from config.pagination import OptionalPageNumberPagination

from .filters import InstitutionFilter
from .models import Institution
from .serializers import InstitutionSerializer

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
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=['is_active', 'updated_at'])
