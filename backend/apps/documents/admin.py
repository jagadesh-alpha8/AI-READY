from django.contrib import admin

from .models import Document, DriveImportJob


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = [
        'title', 'original_filename', 'sprint', 'document_type', 'ai_document_type', 'classification_status',
        'ai_confidence', 'owner_role', 'status', 'file_size', 'ocr_required', 'uploaded_at',
    ]
    list_filter = [
        'status', 'classification_status', 'document_type_source', 'document_type', 'ai_document_type',
        'owner_role', 'ocr_required',
    ]
    search_fields = ['title', 'original_filename', 'document_type', 'ai_document_type', 'checksum']
    autocomplete_fields = ['sprint', 'uploaded_by']
    readonly_fields = [
        'id', 'original_filename', 'mime_type', 'file_size', 'checksum', 'document_type_source',
        'classification_status', 'ai_document_type', 'ai_confidence', 'ai_reasoning', 'classified_at',
        'category_confirmed_by', 'category_confirmed_at',
        'uploaded_at', 'created_at', 'updated_at',
    ]


@admin.register(DriveImportJob)
class DriveImportJobAdmin(admin.ModelAdmin):
    list_display = ['id', 'sprint', 'status', 'drive_url', 'files_scanned', 'files_imported', 'created_at']
    list_filter = ['status']
    search_fields = ['drive_url']
    autocomplete_fields = ['sprint', 'created_by']
    readonly_fields = ['id', 'results', 'celery_task_id', 'started_at', 'completed_at', 'created_at', 'updated_at']
