import uuid

from django.db import models


class VectorDocumentIndex(models.Model):
    """Tracks one document's presence in the vector index.

    Pinecone is not the source of truth for anything, and it is not queryable
    for operational questions like "did this document ever index, and if not
    why". This row is what makes the indexing layer **observable and
    retryable** — the same reason `ExtractionJob` exists for the extraction
    pipeline.

    Deliberately holds no embedding arrays. PostgreSQL stores *that* a document
    is indexed, with what and when; the vectors themselves live in Pinecone,
    and duplicating them here would be a second copy with no reader.

    One row per document (`OneToOne`): re-indexing updates this row rather than
    accumulating history, because the useful question is "what is the current
    state", and `ScoringRun`-style history has no consumer here.
    """

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PROCESSING = 'processing', 'Processing'
        INDEXED = 'indexed', 'Indexed'
        FAILED = 'failed', 'Failed'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    #: Denormalised from `document.sprint.institution` so status can be listed
    #: and filtered per institution without a two-table join on every read.
    #: Safe to copy: a document never moves between institutions.
    institution = models.ForeignKey(
        'institutions.Institution', on_delete=models.CASCADE, related_name='vector_indexes',
    )
    sprint = models.ForeignKey(
        'sprints.Sprint', on_delete=models.CASCADE, related_name='vector_indexes',
    )
    document = models.OneToOneField(
        'documents.Document', on_delete=models.CASCADE, related_name='vector_index',
    )

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    #: How many vectors this document currently has in Pinecone. Also the input
    #: to obsolete-chunk cleanup: a re-index that produces fewer chunks deletes
    #: ids `new_count .. vector_count-1`. See `services/indexer.py`.
    vector_count = models.PositiveIntegerField(default=0)

    #: The model that produced the stored vectors. A query embedded with a
    #: different model is not comparable to these, so recording it makes the
    #: mismatch detectable instead of silently returning nonsense.
    embedding_model = models.CharField(max_length=100, blank=True)

    #: SHA-256 of the document's extracted text (not the file). Text is what
    #: gets embedded, so it is the honest thing to compare: a re-uploaded PDF
    #: with identical text needs no re-embedding, and `Document.checksum`
    #: cannot tell you that.
    content_hash = models.CharField(max_length=64, blank=True, db_index=True)

    indexed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    celery_task_id = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        verbose_name_plural = 'Vector document indexes'
        indexes = [
            models.Index(fields=['sprint', 'status'], name='ix_vecidx_sprint_status'),
        ]

    def __str__(self):
        return f'VectorDocumentIndex({self.document_id}) — {self.status}'
