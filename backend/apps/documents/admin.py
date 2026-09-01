from django.contrib import admin

from .models import Document, DriveImportJob


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = [
        'title', 'original_filename', 'sprint', 'document_type', 'owner_role',
        'status', 'file_size', 'ocr_required', 'uploaded_at',
    ]
    list_filter = ['status', 'document_type', 'owner_role', 'ocr_required']
    search_fields = ['title', 'original_filename', 'document_type', 'checksum']
    autocomplete_fields = ['sprint', 'uploaded_by']
    readonly_fields = [
        'id', 'original_filename', 'mime_type', 'file_size', 'checksum',
        'uploaded_at', 'created_at', 'updated_at',
    ]


@admin.register(DriveImportJob)
class DriveImportJobAdmin(admin.ModelAdmin):
    list_display = ['id', 'sprint', 'status', 'drive_url', 'files_scanned', 'files_imported', 'created_at']
    list_filter = ['status']
    search_fields = ['drive_url']
    autocomplete_fields = ['sprint', 'created_by']
    readonly_fields = ['id', 'results', 'celery_task_id', 'started_at', 'completed_at', 'created_at', 'updated_at']
