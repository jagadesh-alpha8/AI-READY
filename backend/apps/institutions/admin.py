from django.contrib import admin

from .models import Institution


@admin.register(Institution)
class InstitutionAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'short_name', 'institution_type', 'city', 'state', 'country',
        'is_active', 'created_by', 'created_at',
    ]
    list_filter = ['is_active', 'institution_type', 'state', 'country']
    search_fields = ['name', 'short_name', 'city', 'state', 'contact_email']
    readonly_fields = ['id', 'created_at', 'updated_at']
    autocomplete_fields = ['created_by']
