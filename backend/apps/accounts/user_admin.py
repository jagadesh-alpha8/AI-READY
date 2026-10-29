"""User administration — list, create, update and deactivate platform users.

Kept in its own module rather than piled into `views.py`, which owns the
authentication endpoints (login, refresh, logout, me, change-password). Those
answer "who is this request", this answers "who exists" — different concerns,
different permission rules.

Three rules shape everything here, and each one is a real attack surface:

1. **Institution scoping.** An institution admin manages only their own
   college's people. Another college's users are not merely hidden from the
   list — they cannot be fetched, edited or deactivated by id either.

2. **No privilege escalation.** An institution admin cannot mint a
   super_admin or a consultant, and cannot move a user to another
   institution. Without this, "add a user" is a one-step path to owning the
   platform.

3. **No self-lockout, and no self-promotion.** Nobody may deactivate
   themselves or change their own role, however senior they are.

Deletion is deactivation. `is_active=False` blocks login (LoginSerializer
checks it) while keeping the row, because fact reviews, baseline decisions and
uploaded documents all name their user and an audit trail that resolves to
nothing is not an audit trail.
"""
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, serializers, status, viewsets
from rest_framework.permissions import BasePermission
from rest_framework.response import Response

from apps.institutions.models import Institution
from config.pagination import OptionalPageNumberPagination

from .models import User

#: Roles only platform staff may hand out. An institution coordinator creating one
#: of these would be granting access to every other college's data.
PLATFORM_ROLES = frozenset({User.Role.SUPER_ADMIN, User.Role.CONSULTANT})

#: Who may reach this API at all: Super Admin (platform-wide) and IQAC Coordinator (own college).
USER_ADMIN_ROLES = frozenset({User.Role.SUPER_ADMIN, User.Role.IQAC_COORDINATOR})


class CanAdministerUsers(BasePermission):
    message = 'You do not have permission to administer users.'

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.role in USER_ADMIN_ROLES)


class UserAdminSerializer(serializers.ModelSerializer):
    """Read and write shape for an administered user.

    `password` is write-only and optional on update — an admin changing a
    colleague's department should not have to reset their password to do it.
    """
    password = serializers.CharField(write_only=True, required=False, allow_blank=False)
    institution_id = serializers.PrimaryKeyRelatedField(
        source='institution', queryset=Institution.objects.all(),
        required=False, allow_null=True,
    )
    institution_name = serializers.CharField(source='institution.name', read_only=True, default='')
    full_name = serializers.CharField(source='get_full_name', read_only=True)
    role_label = serializers.CharField(source='get_role_display', read_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'email', 'username', 'first_name', 'last_name', 'full_name',
            'phone', 'role', 'role_label', 'institution_id', 'institution_name',
            'department_name', 'is_active', 'date_joined', 'updated_at', 'password',
        ]
        read_only_fields = ['id', 'full_name', 'role_label', 'institution_name', 'date_joined', 'updated_at']

    def validate_password(self, value):
        """Run Django's own validators, so an admin cannot set 'password123'
        for someone else when the user could not set it for themselves."""
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages)) from exc
        return value

    def validate(self, attrs):
        actor = self.context['request'].user
        target = self.instance

        # --- Rule 3: no self-lockout, no self-promotion.
        if target is not None and target.pk == actor.pk:
            if 'role' in attrs and attrs['role'] != target.role:
                raise serializers.ValidationError(
                    {'role': 'You cannot change your own role.'},
                )
            if attrs.get('is_active') is False:
                raise serializers.ValidationError(
                    {'is_active': 'You cannot deactivate your own account.'},
                )

        if actor.role == User.Role.SUPER_ADMIN:
            return attrs

        # --- Everything below applies to an IQAC coordinator administering their college.
        # Rule 2: cannot grant a platform role.
        role = attrs.get('role', getattr(target, 'role', None))
        if role in PLATFORM_ROLES:
            raise serializers.ValidationError(
                {'role': 'Only a super admin can assign platform-wide roles.'},
            )
        if role and role != User.Role.IQAC_COORDINATOR:
            raise serializers.ValidationError(
                {'role': 'IQAC Coordinators can only assign the IQAC Coordinator role.'},
            )

        # Rule 1 + 2: the user belongs to the actor's institution, and cannot
        # be moved out of it. An IQAC coordinator with no institution on
        # their own profile can administer nobody.
        if actor.institution_id is None:
            raise serializers.ValidationError(
                'Your account is not attached to an institution, so it cannot administer users.',
            )
        if 'institution' in attrs and attrs['institution'] is not None:
            if attrs['institution'].pk != actor.institution_id:
                raise serializers.ValidationError(
                    {'institution_id': 'You can only administer users in your own institution.'},
                )
        attrs['institution'] = actor.institution

        return attrs

    def create(self, validated_data):
        password = validated_data.pop('password', None)
        if not password:
            raise serializers.ValidationError({'password': 'A password is required for a new user.'})

        # DRF reads an ABSENT boolean in form-encoded data as False (an
        # unchecked HTML checkbox sends nothing), so `is_active` arrived False
        # on a create that never mentioned it -- silently producing a user who
        # could not sign in. The model default cannot help: the key is present
        # by the time it gets there. Honour an explicit value, default to
        # active otherwise.
        if 'is_active' not in self.initial_data:
            validated_data['is_active'] = True
        # create_user hashes the password and derives a username when one was
        # not supplied; assigning `password` directly would store it in clear.
        email = validated_data.pop('email')
        return User.objects.create_user(email=email, password=password, **validated_data)

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        user = super().update(instance, validated_data)
        if password:
            user.set_password(password)
            user.save(update_fields=['password'])
        return user


class UserAdminViewSet(viewsets.ModelViewSet):
    """`/api/v1/users` — administer the people who can sign in.

    DELETE deactivates rather than destroys; see the module docstring.
    """
    serializer_class = UserAdminSerializer
    permission_classes = [CanAdministerUsers]
    pagination_class = OptionalPageNumberPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['role', 'is_active', 'institution']
    search_fields = ['email', 'username', 'first_name', 'last_name']
    ordering_fields = ['email', 'role', 'date_joined']
    ordering = ['email']

    def get_queryset(self):
        actor = self.request.user
        qs = User.objects.select_related('institution')
        if actor.role == User.Role.SUPER_ADMIN:
            return qs
        # An IQAC coordinator with no institution administers nobody. Without
        # this, `filter(institution_id=None)` matches every platform-staff user
        # instead of none of them -- and DELETE never reaches the serializer's
        # checks, so such a coordinator could deactivate a super admin.
        if actor.institution_id is None:
            return qs.none()
        # Scoped for EVERY action, not just list: an out-of-scope id must be
        # unreachable by direct fetch, update and delete too, not merely
        # absent from the listing.
        return qs.filter(institution_id=actor.institution_id)

    def perform_destroy(self, instance):
        if instance.pk == self.request.user.pk:
            raise serializers.ValidationError('You cannot deactivate your own account.')
        instance.is_active = False
        instance.save(update_fields=['is_active', 'updated_at'])

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        # The row still exists, so return it rather than a bare 204 — the
        # caller's list should show the user as inactive, not drop them.
        return Response(self.get_serializer(instance).data, status=status.HTTP_200_OK)
