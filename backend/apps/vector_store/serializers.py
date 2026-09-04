from rest_framework import serializers

from .models import VectorDocumentIndex


class VectorDocumentIndexSerializer(serializers.ModelSerializer):
    document_name = serializers.SerializerMethodField()
    document_type = serializers.CharField(source='document.document_type', read_only=True)

    class Meta:
        model = VectorDocumentIndex
        fields = [
            'id', 'document', 'document_name', 'document_type', 'sprint', 'institution',
            'status', 'vector_count', 'embedding_model', 'content_hash',
            'indexed_at', 'error_message', 'created_at', 'updated_at',
        ]
        read_only_fields = fields

    def get_document_name(self, obj) -> str:
        return obj.document.original_filename or obj.document.title or ''


class VectorIndexTriggerSerializer(serializers.Serializer):
    """Body for POST .../vector-index."""

    #: Re-embed even when the content hash is unchanged. Off by default so the
    #: common "make sure this sprint is indexed" press is cheap; on when the
    #: embedding model changed or an index was rebuilt from scratch.
    force = serializers.BooleanField(required=False, default=False)


class EvidenceSearchSerializer(serializers.Serializer):
    """Body for POST .../evidence-search.

    No institution field: it is derived from the sprint in the URL, so a caller
    cannot ask for another college's evidence by changing a payload value.
    """

    query = serializers.CharField(min_length=3, max_length=2000, trim_whitespace=True)
    top_k = serializers.IntegerField(required=False, min_value=1, max_value=50)
    document_type = serializers.CharField(required=False, allow_blank=True, max_length=100)
    #: Restrict results to this sprint. Defaults true — a sprint's evidence
    #: screen means this sprint. Set false to search everything the institution
    #: has ever uploaded, which is what a cross-sprint benchmark query wants.
    scope_to_sprint = serializers.BooleanField(required=False, default=True)


class EvidenceResultSerializer(serializers.Serializer):
    """Documents the response shape for the OpenAPI schema. Results are built
    as plain dicts by `services.search`, so this is never used to serialize —
    only to describe."""

    score = serializers.FloatField()
    text = serializers.CharField()
    document_id = serializers.CharField()
    document_name = serializers.CharField()
    document_type = serializers.CharField()
    page_number = serializers.IntegerField(allow_null=True)
    chunk_index = serializers.IntegerField(allow_null=True)
    sprint_id = serializers.CharField()
    institution_id = serializers.CharField()
