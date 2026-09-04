"""Sprint-scoped vector-index and evidence-search endpoints.

Every one resolves its sprint through `apps.sprints.access.get_authorized_sprint`,
so institution scoping is the same check the rest of the nested sprint routes
use — and the institution a search runs against comes from the URL's sprint,
never from the request body.

Pinecone is never exposed: no index name, no host, no key, and no raw match
objects reach the client.
"""
import logging

from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import CanManageSprint
from apps.documents.models import Document
from apps.sprints.access import get_authorized_sprint
from config.pagination import OptionalPageNumberPagination

from .exceptions import PermanentVectorStoreError, VectorStoreError
from .models import VectorDocumentIndex
from .serializers import (
    EvidenceResultSerializer,
    EvidenceSearchSerializer,
    VectorDocumentIndexSerializer,
    VectorIndexTriggerSerializer,
)
from .services import indexer, search

logger = logging.getLogger(__name__)

#: Returned when the feature is switched off, instead of a 500 or a silent
#: empty list. The distinction matters: "not configured" is an operator
#: problem, "no results" is a data problem, and a caller must be able to tell
#: them apart.
_DISABLED_DETAIL = (
    'Vector search is not configured on this server. Set PINECONE_API_KEY, '
    'PINECONE_INDEX_NAME and an embedding API key to enable it.'
)


class SprintVectorIndexView(APIView):
    """POST — queue every processed document in the sprint for indexing.

    Returns immediately with the tracking rows; the work happens on Celery. A
    write, so it takes the same role gate as managing the sprint itself.
    """
    permission_classes = [CanManageSprint]

    @extend_schema(
        request=VectorIndexTriggerSerializer, responses=VectorDocumentIndexSerializer(many=True),
    )
    def post(self, request, sprint_id):
        sprint = get_authorized_sprint(request.user, sprint_id)

        body = VectorIndexTriggerSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        force = body.validated_data['force']

        if not indexer.is_enabled():
            return Response({'detail': _DISABLED_DETAIL}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        documents = list(
            Document.objects.filter(sprint=sprint, status=Document.Status.PROCESSED)
            .select_related('sprint')
        )
        if not documents:
            return Response(
                {
                    'detail': 'This sprint has no processed documents to index yet. '
                              'Run AI processing first.',
                    'queued': 0,
                    'documents': [],
                },
                status=status.HTTP_200_OK,
            )

        rows = [indexer.queue_document(doc, force=force) for doc in documents]
        rows = [row for row in rows if row is not None]

        logger.info(
            'vector_store.api.index_queued sprint_id=%s documents=%d force=%s',
            sprint.id, len(rows), force,
        )
        return Response(
            {
                'queued': len(rows),
                'documents': VectorDocumentIndexSerializer(rows, many=True).data,
            },
            status=status.HTTP_202_ACCEPTED,
        )


class SprintVectorIndexStatusView(generics.ListAPIView):
    """GET — indexing status for every document in the sprint.

    The observability half of the tracking model: which documents are indexed,
    how many vectors each holds, and why any of them failed.
    """
    serializer_class = VectorDocumentIndexSerializer
    pagination_class = OptionalPageNumberPagination

    def get_queryset(self):
        get_authorized_sprint(self.request.user, self.kwargs['sprint_id'])
        return (
            VectorDocumentIndex.objects
            .filter(sprint_id=self.kwargs['sprint_id'])
            .select_related('document')
        )


class SprintEvidenceSearchView(APIView):
    """POST — semantic search over this college's indexed document content.

    The retrieval layer the future benchmarking framework will call: a
    criterion becomes `query`, and the results are the college's own evidence,
    each citable back to a document and page.

    Read-only, so any authenticated member of the institution may call it —
    the same rule as reading facts or gaps.
    """

    @extend_schema(
        request=EvidenceSearchSerializer, responses=EvidenceResultSerializer(many=True),
    )
    def post(self, request, sprint_id):
        sprint = get_authorized_sprint(request.user, sprint_id)

        body = EvidenceSearchSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data

        if not search.is_enabled():
            return Response({'detail': _DISABLED_DETAIL}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        try:
            results = search.search_college_evidence(
                # From the URL's sprint, never the payload — this is the
                # isolation boundary and must not be caller-supplied.
                institution_id=sprint.institution_id,
                query=data['query'],
                sprint_id=sprint.id if data['scope_to_sprint'] else None,
                document_type=data.get('document_type') or None,
                top_k=data.get('top_k'),
            )
        except PermanentVectorStoreError as exc:
            raise ValidationError({'detail': str(exc)}) from exc
        except VectorStoreError as exc:
            # Transient (rate limit, timeout, provider down). 503 tells the
            # caller to retry, rather than implying their query was wrong.
            logger.warning('vector_store.api.search_unavailable sprint_id=%s error=%s', sprint.id, exc)
            return Response(
                {'detail': f'Evidence search is temporarily unavailable: {exc}'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response({'query': data['query'], 'count': len(results), 'results': results})
