"""Tests for the vector-store layer.

Pinecone and the embedding provider are always faked — no test here opens a
network connection, and the suite passes whether or not the `pinecone` package
is installed. That is the same posture `apps.extraction` takes with the AI
provider, and it is what lets CI run this without credentials.
"""
from unittest import mock

from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.documents.models import Document
from apps.institutions.models import Institution
from apps.sprints.models import Sprint

from .exceptions import (
    PermanentEmbeddingError,
    PermanentVectorStoreError,
    RecoverableVectorStoreError,
)
from .models import VectorDocumentIndex
from .services import chunking, indexer, search
from .services import pinecone_client as pc

PASSWORD = 'Str0ng!DevPassw0rd'

VECTOR_SETTINGS = {
    'PINECONE_API_KEY': 'test-key-not-real',
    'PINECONE_INDEX_NAME': 'test-index',
    'PINECONE_NAMESPACE': '',
    'EMBEDDING_API_KEY': 'sk-test-not-real',
    'EMBEDDING_MODEL': 'text-embedding-3-small',
    'VECTOR_CHUNK_MAX_CHARS': 200,
    'VECTOR_CHUNK_OVERLAP_CHARS': 40,
    'VECTOR_CHUNK_MIN_CHARS': 10,
}


class FakeEmbedder:
    """Deterministic stand-in. Returns a distinct 4-dim vector per input so a
    test can tell which chunk produced which vector."""

    model = 'text-embedding-3-small'

    def __init__(self, fail_with=None):
        self.fail_with = fail_with
        self.calls = []

    def generate_embedding(self, text):
        return self.generate_embeddings([text])[0]

    def generate_embeddings(self, texts):
        texts = list(texts)
        if self.fail_with:
            raise self.fail_with
        self.calls.append(texts)
        return [[float(len(t)), 0.1, 0.2, 0.3] for t in texts]


class FakeStore:
    """Records upserts/deletes/queries instead of performing them."""

    handles_embedding = False

    def __init__(self, *, matches=None, fail_upsert=None, fail_query=None):
        self.upserted = []
        self.deleted = []
        self.queries = []
        self.matches = matches or []
        self.fail_upsert = fail_upsert
        self.fail_query = fail_query

    def upsert(self, vectors):
        if self.fail_upsert:
            raise self.fail_upsert
        self.upserted.append(vectors)
        return len(vectors)

    def delete_ids(self, ids):
        self.deleted.append(list(ids))
        return len(ids)

    def query(self, *, query_text, top_k, metadata_filter, embedder=None):
        if self.fail_query:
            raise self.fail_query
        self.queries.append({
            'query_text': query_text, 'top_k': top_k,
            'metadata_filter': metadata_filter, 'embedder': embedder,
        })
        return self.matches


class FakeIntegratedStore(FakeStore):
    """A store whose index embeds server-side, like the project's
    llama-text-embed-v2 index."""

    handles_embedding = True


def make_pages(*texts):
    return [
        {'page_number': i, 'text': t, 'char_count': len(t), 'requires_ocr': False, 'tables': []}
        for i, t in enumerate(texts, start=1)
    ]


class BaseVectorTest(TestCase):
    def setUp(self):
        self.institution = Institution.objects.create(name='College A', city='Chennai', state='TN')
        self.other_institution = Institution.objects.create(name='College B')
        self.sprint = Sprint.objects.create(institution=self.institution)
        self.document = Document.objects.create(
            sprint=self.sprint,
            document_type='faculty_master_list',
            title='Faculty Report',
            original_filename='Faculty_Report.pdf',
            status=Document.Status.PROCESSED,
        )


# --------------------------------------------------------------- 1. chunking

@override_settings(**VECTOR_SETTINGS)
class ChunkingTests(TestCase):
    def test_chunks_carry_page_and_running_index(self):
        chunks = chunking.chunk_pages(make_pages('Alpha sentence here.', 'Beta sentence here.'))
        self.assertEqual([c['chunk_index'] for c in chunks], [0, 1])
        self.assertEqual([c['page_number'] for c in chunks], [1, 2])

    def test_a_chunk_never_spans_two_pages(self):
        """Page number is the citation this platform promises, so a chunk built
        from two pages could only cite one of them honestly."""
        chunks = chunking.chunk_pages(make_pages('Short one.', 'Short two.'))
        self.assertEqual(len(chunks), 2)
        self.assertNotIn('Short two', chunks[0]['text'])

    def test_long_page_splits_into_several_chunks_with_overlap(self):
        sentence = 'The institution has three hundred and twelve faculty members on record. '
        chunks = chunking.chunk_pages(make_pages(sentence * 12))
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(chunk['char_count'], 200)
        # Overlap means the tail of one chunk reappears at the head of the next.
        self.assertTrue(any(chunks[0]['text'][-20:] in chunks[1]['text'] for _ in [0]))

    def test_sentence_longer_than_budget_is_hard_split_not_dropped(self):
        chunks = chunking.chunk_pages(make_pages('x' * 700))
        self.assertGreater(len(chunks), 1)
        self.assertEqual(sum(c['char_count'] for c in chunks), 700)

    def test_page_furniture_below_min_chars_is_skipped(self):
        chunks = chunking.chunk_pages(make_pages('12', 'A real sentence with content.'))
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]['page_number'], 2)

    def test_whitespace_is_normalised(self):
        chunks = chunking.chunk_pages(make_pages('Ragged   \n\n  PDF    text here.'))
        self.assertEqual(chunks[0]['text'], 'Ragged PDF text here.')

    def test_empty_and_none_pages_yield_no_chunks(self):
        self.assertEqual(chunking.chunk_pages([]), [])
        self.assertEqual(chunking.chunk_pages(None), [])
        self.assertEqual(chunking.chunk_pages(make_pages('', '   ')), [])

    def test_overlap_not_smaller_than_max_is_rejected(self):
        """Would make every chunk start with the whole of its predecessor and
        never terminate."""
        with self.assertRaises(ValueError):
            chunking.chunk_pages(make_pages('a. b. c.'), max_chars=50, overlap_chars=50)


# ------------------------------------------------- 2 & 3. ids and metadata

@override_settings(**VECTOR_SETTINGS)
class VectorIdAndMetadataTests(BaseVectorTest):
    def test_vector_id_is_deterministic(self):
        first = pc.build_vector_id(self.institution.id, self.document.id, 4)
        second = pc.build_vector_id(self.institution.id, self.document.id, 4)
        self.assertEqual(first, second)
        self.assertEqual(
            first, f'college_{self.institution.id}_document_{self.document.id}_chunk_4',
        )

    def test_vector_ids_differ_by_chunk_document_and_college(self):
        base = pc.build_vector_id(self.institution.id, self.document.id, 0)
        self.assertNotEqual(base, pc.build_vector_id(self.institution.id, self.document.id, 1))
        self.assertNotEqual(base, pc.build_vector_id(self.other_institution.id, self.document.id, 0))

    def test_metadata_carries_isolation_and_traceability_fields(self):
        chunk = {'chunk_index': 3, 'page_number': 17, 'text': 'The institution has 312 faculty.'}
        meta = pc.build_vector_metadata(document=self.document, chunk=chunk)

        self.assertEqual(meta['college_id'], str(self.institution.id))
        self.assertEqual(meta['sprint_id'], str(self.sprint.id))
        self.assertEqual(meta['document_id'], str(self.document.id))
        self.assertEqual(meta['document_name'], 'Faculty_Report.pdf')
        self.assertEqual(meta['document_type'], 'faculty_master_list')
        self.assertEqual(meta['page_number'], 17)
        self.assertEqual(meta['chunk_index'], 3)
        self.assertEqual(meta['source_type'], 'college_document')
        self.assertIn('312 faculty', meta['text'])

    def test_metadata_does_not_duplicate_unrelated_postgres_fields(self):
        meta = pc.build_vector_metadata(
            document=self.document, chunk={'chunk_index': 0, 'page_number': 1, 'text': 'x'},
        )
        for absent in ('checksum', 'file_size', 'mime_type', 'status', 'uploaded_by'):
            self.assertNotIn(absent, meta)


# --------------------------------------------------------------- indexing

@override_settings(**VECTOR_SETTINGS)
class IndexDocumentTests(BaseVectorTest):
    def _index(self, pages, *, store=None, embedder=None, force=False):
        store = store or FakeStore()
        embedder = embedder or FakeEmbedder()
        with mock.patch.object(indexer, '_read_pages', return_value=pages):
            row = indexer.index_document(
                self.document, force=force, store=store, embedder=embedder,
            )
        return row, store, embedder

    def test_indexing_upserts_one_vector_per_chunk_and_records_status(self):
        row, store, _ = self._index(make_pages('Alpha sentence here.', 'Beta sentence here.'))

        self.assertEqual(row.status, VectorDocumentIndex.Status.INDEXED)
        self.assertEqual(row.vector_count, 2)
        self.assertEqual(row.embedding_model, 'text-embedding-3-small')
        self.assertTrue(row.content_hash)
        self.assertIsNotNone(row.indexed_at)
        self.assertEqual(len(store.upserted[0]), 2)

    def test_upserted_payload_has_deterministic_ids(self):
        _, store, _ = self._index(make_pages('Alpha sentence here.'))
        vector = store.upserted[0][0]
        self.assertEqual(
            vector['id'],
            f'college_{self.institution.id}_document_{self.document.id}_chunk_0',
        )
        self.assertEqual(vector['metadata']['college_id'], str(self.institution.id))

    def test_reindexing_unchanged_content_does_not_re_embed(self):
        """Idempotency: same text, same model → no duplicate work and no
        duplicate vectors."""
        pages = make_pages('Alpha sentence here.')
        self._index(pages)

        second_store, second_embedder = FakeStore(), FakeEmbedder()
        row, _, _ = self._index(pages, store=second_store, embedder=second_embedder)

        self.assertEqual(row.status, VectorDocumentIndex.Status.INDEXED)
        self.assertEqual(second_store.upserted, [])
        self.assertEqual(second_embedder.calls, [])

    def test_force_reindexes_even_when_unchanged(self):
        pages = make_pages('Alpha sentence here.')
        self._index(pages)
        _, store, _ = self._index(pages, force=True)
        self.assertEqual(len(store.upserted[0]), 1)

    def test_changed_content_is_re_embedded_and_upserted(self):
        self._index(make_pages('Alpha sentence here.'))
        row, store, _ = self._index(make_pages('Completely different content now.'))
        self.assertEqual(len(store.upserted[0]), 1)
        self.assertEqual(row.vector_count, 1)

    def test_fewer_chunks_after_replacement_deletes_the_obsolete_ones(self):
        """The document shrank, so vectors 1..N-1 from the old revision must
        go — otherwise stale evidence keeps surfacing in search."""
        long_page = 'The institution has three hundred and twelve faculty members. ' * 10
        first_row, _, _ = self._index(make_pages(long_page))
        self.assertGreater(first_row.vector_count, 1)
        previous_count = first_row.vector_count

        row, store, _ = self._index(make_pages('Short replacement text here.'))

        self.assertEqual(row.vector_count, 1)
        self.assertEqual(len(store.deleted), 1)
        expected = [
            pc.build_vector_id(self.institution.id, self.document.id, i)
            for i in range(1, previous_count)
        ]
        self.assertEqual(store.deleted[0], expected)

    def test_more_chunks_deletes_nothing(self):
        self._index(make_pages('Short one.'))
        long_page = 'The institution has three hundred and twelve faculty members. ' * 10
        _, store, _ = self._index(make_pages(long_page))
        self.assertEqual(store.deleted, [])

    def test_empty_document_is_indexed_with_zero_vectors_not_failed(self):
        """A scanned PDF with no OCR has nothing to embed. That is a terminal
        state, not an error to retry forever."""
        row, store, embedder = self._index(make_pages('', '  '))
        self.assertEqual(row.status, VectorDocumentIndex.Status.INDEXED)
        self.assertEqual(row.vector_count, 0)
        self.assertEqual(store.upserted, [])
        self.assertEqual(embedder.calls, [])
        self.assertIn('No extractable text', row.error_message)

    def test_emptied_document_prunes_its_previous_vectors(self):
        first_row, _, _ = self._index(make_pages('Alpha sentence here.'))
        self.assertEqual(first_row.vector_count, 1)
        _, store, _ = self._index(make_pages(''))
        self.assertEqual(store.deleted, [[
            pc.build_vector_id(self.institution.id, self.document.id, 0),
        ]])

    def test_pinecone_failure_marks_the_row_failed_and_reraises(self):
        store = FakeStore(fail_upsert=RecoverableVectorStoreError('Pinecone unavailable'))
        with self.assertRaises(RecoverableVectorStoreError):
            self._index(make_pages('Alpha sentence here.'), store=store)

        row = VectorDocumentIndex.objects.get(document=self.document)
        self.assertEqual(row.status, VectorDocumentIndex.Status.FAILED)
        self.assertIn('Pinecone unavailable', row.error_message)

    def test_embedding_failure_marks_the_row_failed_and_upserts_nothing(self):
        store = FakeStore()
        embedder = FakeEmbedder(fail_with=PermanentEmbeddingError('bad api key'))
        with self.assertRaises(PermanentEmbeddingError):
            self._index(make_pages('Alpha sentence here.'), store=store, embedder=embedder)

        row = VectorDocumentIndex.objects.get(document=self.document)
        self.assertEqual(row.status, VectorDocumentIndex.Status.FAILED)
        self.assertEqual(store.upserted, [])

    def test_unreadable_format_fails_permanently(self):
        unsupported = {'pages': [], 'format_supported': False, 'format_note': 'not a PDF'}
        with mock.patch(
            'apps.vector_store.services.indexer.PDFPageReader.read_pages', return_value=unsupported,
        ):
            with self.assertRaises(PermanentVectorStoreError):
                indexer.index_document(self.document, store=FakeStore(), embedder=FakeEmbedder())
        row = VectorDocumentIndex.objects.get(document=self.document)
        self.assertEqual(row.status, VectorDocumentIndex.Status.FAILED)


# ------------------------------------------------------- enable / disable

class FeatureFlagTests(BaseVectorTest):
    @override_settings(PINECONE_API_KEY='', PINECONE_INDEX_NAME='', EMBEDDING_API_KEY='')
    def test_disabled_when_unconfigured(self):
        self.assertFalse(indexer.is_enabled())
        self.assertFalse(search.is_enabled())

    @override_settings(
        PINECONE_API_KEY='', PINECONE_INDEX_NAME='', EMBEDDING_API_KEY='',
        OPENAI_API_KEY='', AI_API_KEY='',
    )
    def test_queue_document_is_a_noop_when_disabled(self):
        """Backward compatibility: an unconfigured deployment queues nothing
        and writes nothing."""
        self.assertIsNone(indexer.queue_document(self.document))
        self.assertFalse(VectorDocumentIndex.objects.exists())

    @override_settings(**VECTOR_SETTINGS)
    def test_queue_document_writes_a_pending_row_and_dispatches(self):
        with mock.patch('apps.vector_store.tasks.index_document_vectors.delay') as delay:
            delay.return_value = mock.Mock(id='task-123')
            with self.captureOnCommitCallbacks(execute=True):
                row = indexer.queue_document(self.document)

        self.assertIsNotNone(row)
        delay.assert_called_once_with(str(self.document.id), False)
        row.refresh_from_db()
        self.assertEqual(row.celery_task_id, 'task-123')

    @override_settings(**VECTOR_SETTINGS)
    def test_broker_failure_is_recorded_not_raised(self):
        """A dead broker must not break the document workflow."""
        with mock.patch(
            'apps.vector_store.tasks.index_document_vectors.delay',
            side_effect=OSError('broker down'),
        ):
            with self.captureOnCommitCallbacks(execute=True):
                row = indexer.queue_document(self.document)

        row.refresh_from_db()
        self.assertEqual(row.status, VectorDocumentIndex.Status.FAILED)
        self.assertIn('Celery broker', row.error_message)


# ------------------------------------------------------------------ search

@override_settings(**VECTOR_SETTINGS)
class SearchTests(BaseVectorTest):
    def _match(self, score=0.89, **overrides):
        metadata = {
            'college_id': str(self.institution.id),
            'sprint_id': str(self.sprint.id),
            'document_id': str(self.document.id),
            'document_name': 'Faculty_Report.pdf',
            'document_type': 'faculty_master_list',
            'page_number': 17,
            'chunk_index': 4,
            'text': 'The institution has 312 faculty members...',
            'source_type': 'college_document',
        }
        metadata.update(overrides)
        return {'id': 'v1', 'score': score, 'metadata': metadata}

    def test_filter_always_pins_college_and_source_type(self):
        built = search.build_filter(institution_id=self.institution.id)
        self.assertEqual(built['college_id'], {'$eq': str(self.institution.id)})
        self.assertEqual(built['source_type'], {'$eq': 'college_document'})

    def test_filter_adds_optional_narrowing(self):
        built = search.build_filter(
            institution_id=self.institution.id,
            sprint_id=self.sprint.id,
            document_type='aqar',
        )
        self.assertEqual(built['sprint_id'], {'$eq': str(self.sprint.id)})
        self.assertEqual(built['document_type'], {'$eq': 'aqar'})

    def test_filter_requires_an_institution(self):
        with self.assertRaises(PermanentVectorStoreError):
            search.build_filter(institution_id=None)

    def test_search_sends_the_institution_filter_to_pinecone(self):
        """Isolation is enforced server-side, not by filtering results after
        they come back."""
        store = FakeStore(matches=[self._match()])
        search.search_college_evidence(
            institution_id=self.institution.id, query='AI certified faculty',
            store=store, embedder=FakeEmbedder(),
        )
        sent = store.queries[0]['metadata_filter']
        self.assertEqual(sent['college_id'], {'$eq': str(self.institution.id)})

    def test_search_cannot_be_run_without_a_filter(self):
        """The store refuses an unfiltered query outright — the guarantee does
        not depend on every caller remembering."""
        store = pc.PineconeVectorStore(index=mock.Mock())
        with self.assertRaises(PermanentVectorStoreError):
            store.query(query_text='faculty', top_k=5, metadata_filter=None,
                        embedder=FakeEmbedder())

    def test_results_carry_full_provenance(self):
        store = FakeStore(matches=[self._match()])
        results = search.search_college_evidence(
            institution_id=self.institution.id, query='faculty training',
            store=store, embedder=FakeEmbedder(),
        )
        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertEqual(result['score'], 0.89)
        self.assertEqual(result['document_name'], 'Faculty_Report.pdf')
        self.assertEqual(result['page_number'], 17)
        self.assertEqual(result['chunk_index'], 4)
        self.assertEqual(result['document_id'], str(self.document.id))
        self.assertIn('312 faculty', result['text'])

    def test_top_k_is_capped(self):
        store = FakeStore(matches=[])
        search.search_college_evidence(
            institution_id=self.institution.id, query='x' * 5, top_k=9999,
            store=store, embedder=FakeEmbedder(),
        )
        self.assertEqual(store.queries[0]['top_k'], 50)

    def test_blank_query_is_rejected(self):
        with self.assertRaises(PermanentVectorStoreError):
            search.search_college_evidence(
                institution_id=self.institution.id, query='   ',
                store=FakeStore(), embedder=FakeEmbedder(),
            )

    def test_pinecone_failure_propagates(self):
        store = FakeStore(fail_query=RecoverableVectorStoreError('index unavailable'))
        with self.assertRaises(RecoverableVectorStoreError):
            search.search_college_evidence(
                institution_id=self.institution.id, query='faculty',
                store=store, embedder=FakeEmbedder(),
            )


# ----------------------------------------------------------- API endpoints

@override_settings(**VECTOR_SETTINGS)
class VectorApiTests(APITestCase):
    def setUp(self):
        self.institution = Institution.objects.create(name='College A')
        self.other_institution = Institution.objects.create(name='College B')
        self.sprint = Sprint.objects.create(institution=self.institution)
        self.other_sprint = Sprint.objects.create(institution=self.other_institution)
        self.document = Document.objects.create(
            sprint=self.sprint, document_type='aqar', original_filename='AQAR.pdf',
            status=Document.Status.PROCESSED,
        )

        self.admin = self._user('vs_admin@test.edu', User.Role.INSTITUTION_ADMIN, self.institution)
        self.viewer = self._user('vs_viewer@test.edu', User.Role.VIEWER, self.institution)
        self.outsider = self._user('vs_out@test.edu', User.Role.INSTITUTION_ADMIN, self.other_institution)

    @staticmethod
    def _user(email, role, institution):
        return User.objects.create_user(
            email=email, username=email.split('@')[0], password=PASSWORD,
            first_name='T', last_name='U', role=role, institution=institution,
        )

    def _auth(self, user):
        login = self.client.post('/api/v1/auth/login/', {'email': user.email, 'password': PASSWORD})
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {login.data["access_token"]}')

    # -- authorization ---------------------------------------------------

    def test_another_institutions_sprint_is_forbidden(self):
        self._auth(self.outsider)
        for url in (
            f'/api/v1/sprints/{self.sprint.id}/vector-index/status',
            f'/api/v1/sprints/{self.sprint.id}/evidence-search',
        ):
            response = (
                self.client.get(url) if 'status' in url
                else self.client.post(url, {'query': 'faculty'}, format='json')
            )
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, url)

    def test_anonymous_is_rejected(self):
        response = self.client.get(f'/api/v1/sprints/{self.sprint.id}/vector-index/status')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_viewer_cannot_trigger_indexing(self):
        self._auth(self.viewer)
        response = self.client.post(
            f'/api/v1/sprints/{self.sprint.id}/vector-index', {}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_viewer_can_search_evidence(self):
        """Search is a read, so it follows the same rule as reading facts."""
        self._auth(self.viewer)
        with mock.patch.object(search, 'search_college_evidence', return_value=[]) as searcher:
            response = self.client.post(
                f'/api/v1/sprints/{self.sprint.id}/evidence-search',
                {'query': 'faculty training'}, format='json',
            )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        searcher.assert_called_once()

    # -- behaviour --------------------------------------------------------

    def test_index_endpoint_queues_processed_documents(self):
        self._auth(self.admin)
        with mock.patch.object(indexer, 'queue_document') as queue:
            queue.return_value = VectorDocumentIndex(
                institution=self.institution, sprint=self.sprint, document=self.document,
            )
            response = self.client.post(
                f'/api/v1/sprints/{self.sprint.id}/vector-index', {}, format='json',
            )
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(response.data['queued'], 1)

    def test_search_is_scoped_to_the_url_sprints_institution(self):
        """The institution comes from the sprint in the URL, never the payload
        — so a caller cannot ask for another college's evidence."""
        self._auth(self.admin)
        with mock.patch.object(search, 'search_college_evidence', return_value=[]) as searcher:
            self.client.post(
                f'/api/v1/sprints/{self.sprint.id}/evidence-search',
                {'query': 'faculty', 'institution_id': str(self.other_institution.id)},
                format='json',
            )
        self.assertEqual(
            searcher.call_args.kwargs['institution_id'], self.institution.id,
        )

    def test_search_response_shape(self):
        self._auth(self.admin)
        fake = [{
            'score': 0.89, 'text': 'The institution has 312 faculty members...',
            'document_id': str(self.document.id), 'document_name': 'AQAR.pdf',
            'document_type': 'aqar', 'page_number': 17, 'chunk_index': 4,
            'sprint_id': str(self.sprint.id), 'institution_id': str(self.institution.id),
        }]
        with mock.patch.object(search, 'search_college_evidence', return_value=fake):
            response = self.client.post(
                f'/api/v1/sprints/{self.sprint.id}/evidence-search',
                {'query': 'AI certified faculty'}, format='json',
            )
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['page_number'], 17)

    def test_short_query_is_rejected(self):
        self._auth(self.admin)
        response = self.client.post(
            f'/api/v1/sprints/{self.sprint.id}/evidence-search', {'query': 'a'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_status_endpoint_lists_rows_for_the_sprint_only(self):
        VectorDocumentIndex.objects.create(
            institution=self.institution, sprint=self.sprint, document=self.document,
            status=VectorDocumentIndex.Status.INDEXED, vector_count=7,
        )
        other_doc = Document.objects.create(
            sprint=self.other_sprint, document_type='aqar', status=Document.Status.PROCESSED,
        )
        VectorDocumentIndex.objects.create(
            institution=self.other_institution, sprint=self.other_sprint, document=other_doc,
        )

        self._auth(self.admin)
        response = self.client.get(f'/api/v1/sprints/{self.sprint.id}/vector-index/status')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['vector_count'], 7)

    def test_transient_search_failure_is_a_503_not_a_500(self):
        self._auth(self.admin)
        with mock.patch.object(
            search, 'search_college_evidence',
            side_effect=RecoverableVectorStoreError('rate limited'),
        ):
            response = self.client.post(
                f'/api/v1/sprints/{self.sprint.id}/evidence-search',
                {'query': 'faculty training'}, format='json',
            )
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)

    @override_settings(
        PINECONE_API_KEY='', PINECONE_INDEX_NAME='', EMBEDDING_API_KEY='',
        OPENAI_API_KEY='', AI_API_KEY='',
    )
    def test_endpoints_answer_503_with_a_reason_when_unconfigured(self):
        self._auth(self.admin)
        response = self.client.post(
            f'/api/v1/sprints/{self.sprint.id}/evidence-search',
            {'query': 'faculty training'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertIn('not configured', response.data['detail'])


# --------------------------------------------- extraction pipeline is safe

@override_settings(**VECTOR_SETTINGS)
class ExtractionIntegrationTests(BaseVectorTest):
    def test_vector_queue_failure_cannot_break_extraction(self):
        """A Pinecone or broker problem must never fail a document that
        extracted successfully."""
        from apps.extraction.tasks import _queue_vector_indexing

        with mock.patch.object(indexer, 'queue_document', side_effect=RuntimeError('boom')):
            _queue_vector_indexing(self.document)  # must not raise


# ----------------------------------------- integrated (self-embedding) index

@override_settings(**{**VECTOR_SETTINGS, 'PINECONE_EMBEDDING_MODE': 'integrated',
                      'EMBEDDING_MODEL': 'llama-text-embed-v2', 'EMBEDDING_API_KEY': ''})
class IntegratedIndexTests(BaseVectorTest):
    """An index created with an `embed` config embeds server-side, so this app
    supplies text rather than vectors and needs no embedding key of its own."""

    def test_enabled_without_any_embedding_key(self):
        self.assertTrue(indexer.is_enabled())
        self.assertTrue(search.is_enabled())

    def test_indexing_sends_no_local_embeddings(self):
        store = FakeIntegratedStore()
        with mock.patch.object(indexer, '_read_pages', return_value=make_pages('Alpha sentence here.')):
            row = indexer.index_document(self.document, store=store)

        self.assertEqual(row.status, VectorDocumentIndex.Status.INDEXED)
        self.assertEqual(row.vector_count, 1)
        self.assertEqual(row.embedding_model, 'llama-text-embed-v2')
        # No embedding service was built, and the payload carries no vector.
        self.assertIsNone(store.upserted[0][0]['values'])

    def test_payload_still_carries_ids_and_full_metadata(self):
        store = FakeIntegratedStore()
        with mock.patch.object(indexer, '_read_pages', return_value=make_pages('Alpha sentence here.')):
            indexer.index_document(self.document, store=store)

        item = store.upserted[0][0]
        self.assertEqual(
            item['id'], f'college_{self.institution.id}_document_{self.document.id}_chunk_0',
        )
        self.assertEqual(item['metadata']['college_id'], str(self.institution.id))
        self.assertEqual(item['metadata']['page_number'], 1)

    def test_search_needs_no_embedder(self):
        store = FakeIntegratedStore(matches=[{
            'id': 'v1', 'score': 0.91,
            'metadata': {
                'college_id': str(self.institution.id), 'document_id': str(self.document.id),
                'document_name': 'Faculty_Report.pdf', 'page_number': 17, 'chunk_index': 4,
                'text': 'The institution has 312 faculty members...', 'sprint_id': str(self.sprint.id),
                'document_type': 'faculty_master_list', 'source_type': 'college_document',
            },
        }])
        results = search.search_college_evidence(
            institution_id=self.institution.id, query='AI certified faculty', store=store,
        )
        self.assertIsNone(store.queries[0]['embedder'])
        self.assertEqual(results[0]['page_number'], 17)
        self.assertEqual(results[0]['score'], 0.91)

    def test_integrated_store_flattens_records_and_maps_search_hits(self):
        """The two Pinecone APIs disagree on shape; the store is the adapter."""
        index = mock.Mock()
        index.search.return_value = {
            'result': {'hits': [
                {'_id': 'v1', '_score': 0.77, 'fields': {'text': 'x', 'college_id': 'c1'}},
            ]},
        }
        store = pc.PineconeIntegratedVectorStore(index=index, namespace='')

        store.upsert([{'id': 'v1', 'values': None, 'metadata': {'text': 'x', 'college_id': 'c1'}}])
        namespace, records = index.upsert_records.call_args.args
        # Empty string, not "__default__" — see IntegratedNamespaceTests.
        self.assertEqual(namespace, '')
        self.assertEqual(records[0], {'_id': 'v1', 'text': 'x', 'college_id': 'c1'})

        matches = store.query(
            query_text='faculty', top_k=3, metadata_filter={'college_id': {'$eq': 'c1'}},
        )
        self.assertEqual(matches[0]['id'], 'v1')
        self.assertEqual(matches[0]['score'], 0.77)
        self.assertEqual(matches[0]['metadata']['text'], 'x')
        # The institution filter reached Pinecone, not a post-filter.
        self.assertEqual(
            index.search.call_args.kwargs['query']['filter'], {'college_id': {'$eq': 'c1'}},
        )

    def test_integrated_store_still_refuses_an_unfiltered_query(self):
        store = pc.PineconeIntegratedVectorStore(index=mock.Mock())
        with self.assertRaises(PermanentVectorStoreError):
            store.query(query_text='faculty', top_k=5, metadata_filter=None)


class EmbeddingModeDetectionTests(TestCase):
    def setUp(self):
        pc.reset_mode_cache()

    def tearDown(self):
        pc.reset_mode_cache()

    @override_settings(PINECONE_EMBEDDING_MODE='integrated')
    def test_explicit_mode_short_circuits_detection(self):
        self.assertEqual(pc.detect_embedding_mode(), 'integrated')
        self.assertIsInstance(pc.get_vector_store(index=mock.Mock()), pc.PineconeIntegratedVectorStore)

    @override_settings(PINECONE_EMBEDDING_MODE='manual')
    def test_manual_mode_returns_the_raw_vector_store(self):
        store = pc.get_vector_store(index=mock.Mock())
        self.assertIsInstance(store, pc.PineconeVectorStore)
        self.assertFalse(store.handles_embedding)

    @override_settings(PINECONE_EMBEDDING_MODE='auto', PINECONE_API_KEY='k', PINECONE_INDEX_NAME='i')
    def test_auto_detects_an_integrated_index_and_caches_it(self):
        described = mock.Mock()
        described.get.side_effect = lambda key, default=None: (
            {'model': 'llama-text-embed-v2'} if key == 'embed' else default
        )
        with mock.patch('pinecone.Pinecone') as Pinecone:
            Pinecone.return_value.describe_index.return_value = {'embed': {'model': 'llama-text-embed-v2'}}
            self.assertEqual(pc.detect_embedding_mode(), 'integrated')
            self.assertEqual(pc.detect_embedding_mode(), 'integrated')
            # Cached: describe_index is a network call, so it happens once.
            self.assertEqual(Pinecone.return_value.describe_index.call_count, 1)

    @override_settings(PINECONE_EMBEDDING_MODE='auto', PINECONE_API_KEY='k', PINECONE_INDEX_NAME='i')
    def test_auto_falls_back_to_manual_when_detection_fails(self):
        """The conservative answer: raw vectors sent to an integrated index
        fail loudly, whereas the reverse would silently store nothing useful."""
        with mock.patch('pinecone.Pinecone', side_effect=RuntimeError('network down')):
            self.assertEqual(pc.detect_embedding_mode(), 'manual')

    @override_settings(PINECONE_EMBEDDING_MODE='manual', PINECONE_API_KEY='k',
                       PINECONE_INDEX_NAME='i', EMBEDDING_API_KEY='', OPENAI_API_KEY='',
                       AI_API_KEY='sk-ant-anthropic-only')
    def test_manual_index_without_a_usable_embedding_key_is_disabled(self):
        """An Anthropic key cannot embed, so the feature reports itself off
        rather than queueing work that can only fail."""
        self.assertFalse(indexer.is_enabled())


class ErrorClassificationTests(TestCase):
    """Retry behaviour is decided entirely by `_translate`, so getting it wrong
    means either pointless retries or a lost transient failure.

    Regression guard: an earlier version keyword-matched `str(exc)`, which for
    this SDK includes the HTTP header dump — so a permanent 400 matched on
    "Connection: keep-alive" and was retried three times. Found by a real API
    call, not by a unit test.
    """

    class _ApiError(Exception):
        def __init__(self, status, body):
            self.status = status
            self.body = body
            super().__init__(
                f'({status})\nReason: Bad Request\n'
                "HTTPHeaderDict({'Connection': 'keep-alive', 'server': 'envoy'})\n" + body
            )

    def test_400_is_permanent_despite_connection_in_the_header_dump(self):
        exc = self._ApiError(400, '{"error":{"code":"INVALID_ARGUMENT"}}')
        translated = pc.PineconeVectorStore._translate(exc, 'upserting records')
        self.assertIsInstance(translated, PermanentVectorStoreError)

    def test_401_and_404_are_permanent(self):
        for code in (401, 403, 404):
            translated = pc.PineconeVectorStore._translate(self._ApiError(code, '{}'), 'x')
            self.assertIsInstance(translated, PermanentVectorStoreError, code)

    def test_429_and_5xx_are_recoverable(self):
        for code in (429, 500, 502, 503, 504):
            translated = pc.PineconeVectorStore._translate(self._ApiError(code, '{}'), 'x')
            self.assertIsInstance(translated, RecoverableVectorStoreError, code)

    def test_transport_error_without_a_status_is_recoverable(self):
        class ConnectionError_(Exception):
            pass
        ConnectionError_.__name__ = 'ConnectionError'
        translated = pc.PineconeVectorStore._translate(ConnectionError_('boom'), 'x')
        self.assertIsInstance(translated, RecoverableVectorStoreError)

    def test_the_provider_body_is_surfaced_not_the_header_dump(self):
        exc = self._ApiError(400, '{"error":{"message":"Invalid Namespace"}}')
        translated = pc.PineconeVectorStore._translate(exc, 'upserting records')
        self.assertIn('Invalid Namespace', str(translated))
        self.assertNotIn('HTTPHeaderDict', str(translated))


class IntegratedNamespaceTests(TestCase):
    """`__default__` is rejected with a 400 by API versions before 2025-04,
    which is what this SDK negotiates. The empty string is the default
    namespace on every version. Verified against a live index."""

    def test_default_namespace_is_empty_not_the_literal(self):
        store = pc.PineconeIntegratedVectorStore(index=mock.Mock(), namespace='')
        self.assertEqual(store._namespace(), '')

    def test_upsert_sends_the_empty_default_namespace(self):
        index = mock.Mock()
        pc.PineconeIntegratedVectorStore(index=index, namespace='').upsert(
            [{'id': 'v1', 'values': None, 'metadata': {'text': 'x'}}],
        )
        self.assertEqual(index.upsert_records.call_args.args[0], '')

    def test_an_explicit_namespace_is_still_honoured(self):
        index = mock.Mock()
        pc.PineconeIntegratedVectorStore(index=index, namespace='tenant-a').upsert(
            [{'id': 'v1', 'values': None, 'metadata': {'text': 'x'}}],
        )
        self.assertEqual(index.upsert_records.call_args.args[0], 'tenant-a')


class BatchLimitTests(TestCase):
    """`upsert_records` on an integrated index caps at 96 records per call —
    a count limit, not the 2 MB size limit that governs raw-vector upserts,
    because Pinecone embeds each record server-side.

    Regression guard: a real 316-chunk PDF returned
    `400 Invalid input: Batch size exceeds 96`.
    """

    @staticmethod
    def _payload(n):
        return [
            {'id': f'v{i}', 'values': None, 'metadata': {'text': f'chunk {i}'}}
            for i in range(n)
        ]

    def test_integrated_batches_at_96(self):
        self.assertEqual(pc.PineconeIntegratedVectorStore.UPSERT_BATCH_SIZE, 96)

        index = mock.Mock()
        store = pc.PineconeIntegratedVectorStore(index=index, namespace='')
        self.assertEqual(store.upsert(self._payload(316)), 316)

        sizes = [len(call.args[1]) for call in index.upsert_records.call_args_list]
        self.assertEqual(sizes, [96, 96, 96, 28])
        self.assertTrue(all(size <= 96 for size in sizes))

    def test_raw_vector_store_keeps_the_larger_batch(self):
        index = mock.Mock()
        store = pc.PineconeVectorStore(index=index, namespace='')
        store.upsert(self._payload(250))
        sizes = [len(call.kwargs['vectors']) for call in index.upsert.call_args_list]
        self.assertEqual(sizes, [100, 100, 50])


class NumericMetadataTests(TestCase):
    """Pinecone stores metadata numbers as doubles, so a page number comes
    back as 17.0. A page number is not a real quantity."""

    def test_page_and_chunk_come_back_as_ints(self):
        formatted = search._format({
            'score': 0.5,
            'metadata': {'page_number': 17.0, 'chunk_index': 202.0, 'text': 'x'},
        })
        self.assertEqual(formatted['page_number'], 17)
        self.assertEqual(formatted['chunk_index'], 202)

    def test_missing_numbers_are_none_not_zero(self):
        formatted = search._format({'score': 0.5, 'metadata': {'text': 'x'}})
        self.assertIsNone(formatted['page_number'])
        self.assertIsNone(formatted['chunk_index'])

    def test_chunk_index_zero_is_preserved(self):
        """0 is a real chunk index — it must not be flattened to None."""
        formatted = search._format({'score': 0.5, 'metadata': {'chunk_index': 0.0, 'text': 'x'}})
        self.assertEqual(formatted['chunk_index'], 0)
