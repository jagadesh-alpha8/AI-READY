import os

from django.conf import settings
from django.template.defaultfilters import filesizeformat
from rest_framework import serializers

from .constants import ALLOWED_UPLOAD_EXTENSIONS, humanize_document_type
from .drive_import import parse_drive_folder_id
from .exceptions import DriveImportError
from .models import Document, DriveImportJob, document_type_validator
from .utils import compute_file_checksum, humanize_filename


class DocumentSerializer(serializers.ModelSerializer):
    sprint_id = serializers.PrimaryKeyRelatedField(source='sprint', read_only=True)
    uploaded_by = serializers.PrimaryKeyRelatedField(read_only=True)
    document_type_label = serializers.SerializerMethodField()
    download_url = serializers.SerializerMethodField()
    has_file = serializers.SerializerMethodField()
    file_size_display = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = [
            'id', 'sprint_id', 'document_type', 'document_type_label', 'title',
            'original_filename', 'mime_type', 'file_size', 'file_size_display', 'checksum',
            'download_url', 'has_file', 'uploaded_by', 'owner_role', 'status',
            'page_count', 'quality_score', 'ocr_required', 'ocr_warnings', 'processing_status',
            'uploaded_at', 'processed_at', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'sprint_id', 'original_filename', 'mime_type', 'file_size', 'file_size_display',
            'checksum', 'download_url', 'has_file', 'document_type_label', 'uploaded_by',
            'uploaded_at', 'processed_at', 'created_at', 'updated_at',
        ]

    def get_document_type_label(self, obj):
        return humanize_document_type(obj.document_type)

    def get_has_file(self, obj):
        return bool(obj.file)

    def get_file_size_display(self, obj):
        return filesizeformat(obj.file_size) if obj.file_size else None

    def get_download_url(self, obj):
        if not obj.file:
            return None
        path = f'/api/v1/documents/{obj.id}/download'
        request = self.context.get('request')
        return request.build_absolute_uri(path) if request else path


class DocumentUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    document_type = serializers.CharField(max_length=100, validators=[document_type_validator])
    title = serializers.CharField(max_length=255, required=False, allow_blank=True, default='')
    owner_role = serializers.CharField(max_length=50, required=False, allow_blank=True, default='')

    def validate_file(self, value):
        max_size = settings.MAX_DOCUMENT_UPLOAD_SIZE
        if value.size > max_size:
            raise serializers.ValidationError(
                f'File is too large ({filesizeformat(value.size)}). '
                f'Maximum allowed size is {filesizeformat(max_size)}.',
            )

        ext = os.path.splitext(value.name)[1].lower()
        if ext not in ALLOWED_UPLOAD_EXTENSIONS:
            allowed = ', '.join(sorted(ALLOWED_UPLOAD_EXTENSIONS))
            raise serializers.ValidationError(
                f"Unsupported file type '{ext or 'unknown'}'. Allowed types: {allowed}.",
            )
        return value

    def validate(self, attrs):
        sprint = self.context['sprint']
        file_obj = attrs['file']
        checksum = compute_file_checksum(file_obj)

        duplicate = Document.objects.filter(sprint=sprint, checksum=checksum).first()
        if duplicate is not None:
            raise serializers.ValidationError({
                'file': (
                    f"This exact file was already uploaded to this sprint as "
                    f"'{duplicate.original_filename or duplicate.title}' (document {duplicate.id})."
                ),
            })

        attrs['checksum'] = checksum
        if not attrs.get('title'):
            attrs['title'] = humanize_filename(file_obj.name)
        return attrs


class DriveImportJobSerializer(serializers.ModelSerializer):
    sprint_id = serializers.PrimaryKeyRelatedField(source='sprint', read_only=True)
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = DriveImportJob
        fields = [
            'id', 'sprint_id', 'drive_url', 'status', 'results', 'files_scanned',
            'files_imported', 'error_message', 'created_by', 'started_at',
            'completed_at', 'created_at', 'updated_at',
        ]
        read_only_fields = fields


class DriveImportJobCreateSerializer(serializers.Serializer):
    """Request body for POST /sprints/{id}/drive-import-jobs. Validates the
    URL is at least parseable to a folder ID up front (400 immediately)
    rather than only discovering a bad link once the Celery task runs."""
    drive_url = serializers.CharField(max_length=500)

    def validate_drive_url(self, value):
        try:
            parse_drive_folder_id(value)
        except DriveImportError as exc:
            raise serializers.ValidationError(str(exc))
        return value.strip()
