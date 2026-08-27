from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    ordering = ['email']
    list_display = [
        'email', 'username', 'first_name', 'last_name', 'role',
        'institution', 'is_staff', 'is_active',
    ]
    list_filter = ['role', 'is_staff', 'is_active', 'institution']
    search_fields = ['email', 'username', 'first_name', 'last_name']
    filter_horizontal = ['groups', 'user_permissions']

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Profile', {
            'fields': ('username', 'first_name', 'last_name', 'phone', 'role', 'institution', 'department_name'),
        }),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_joined', 'updated_at')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'username', 'first_name', 'last_name', 'role', 'password1', 'password2'),
        }),
    )
    readonly_fields = ['date_joined', 'updated_at']
