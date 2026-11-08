import json
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.documents.models import Document
from apps.extraction.models import DocumentPage
from apps.institutions.models import Institution
from apps.scoring.capability.storage import evidence_snapshot
from apps.scoring.models import CapabilityRun
from apps.sprints.models import Sprint


class ExportSprintSourcesTests(TestCase):
    def setUp(self):
        institution = Institution.objects.create(name='VISTAS')
        self.sprint = Sprint.objects.create(institution=institution, mode=Sprint.SprintMode.VERIFIED_CRI)
        doc = Document.objects.create(sprint=self.sprint, original_filename='NAAC SSR.pdf', document_type='naac_ssr',
                                      status=Document.Status.PROCESSED, page_count=3)
        DocumentPage.objects.create(document=doc, page_number=1, text='6.2.3 Implementation of e-governance')
        DocumentPage.objects.create(document=doc, page_number=2, text='Response: ERP covers finance and admission')

    def test_writes_the_same_sources_an_assessment_freezes_without_side_effects(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'out.json'
            call_command('export_sprint_sources', str(self.sprint.pk), output=str(target))
            data = json.loads(target.read_text(encoding='utf-8'))
        manifest, sources = evidence_snapshot(self.sprint)
        self.assertEqual(data['sources'], json.loads(json.dumps(sources)))
        self.assertEqual(data['coverage']['totals']['missing_rows'], 1)
        self.assertFalse(data['coverage']['complete'])
        self.assertEqual(CapabilityRun.objects.count(), 0)

    def test_refuses_existing_output_and_unknown_sprint(self):
        with tempfile.TemporaryDirectory() as tmp:
            existing = Path(tmp) / 'x.json'
            existing.write_text('{}')
            with self.assertRaises(CommandError):
                call_command('export_sprint_sources', str(self.sprint.pk), output=str(existing))
            with self.assertRaises(CommandError):
                call_command('export_sprint_sources', 'not-a-uuid', output=str(Path(tmp) / 'y.json'))


class WarmEmbeddingCacheTests(TestCase):
    def setUp(self):
        institution = Institution.objects.create(name='VISTAS')
        self.sprint = Sprint.objects.create(institution=institution, mode=Sprint.SprintMode.VERIFIED_CRI)
        for name in ('a.pdf', 'b.pdf'):
            doc = Document.objects.create(sprint=self.sprint, original_filename=name, document_type='naac_ssr',
                                          status=Document.Status.PROCESSED, page_count=1)
            DocumentPage.objects.create(document=doc, page_number=1, text='The same page text in two copies of a file.')

    def test_requires_a_cache_and_semantic_retrieval(self):
        from django.test import override_settings
        with override_settings(CAPABILITY_EMBEDDING_CACHE_DIR=''):
            with self.assertRaises(CommandError):
                call_command('warm_embedding_cache', str(self.sprint.pk))
        with override_settings(CAPABILITY_EMBEDDING_CACHE_DIR='/tmp/x', CAPABILITY_RETRIEVAL_MODE='bm25'):
            with self.assertRaises(CommandError):
                call_command('warm_embedding_cache', str(self.sprint.pk))

    def test_embeds_through_the_assessment_path_with_deduplication(self):
        from unittest.mock import MagicMock, patch
        from django.test import override_settings
        seen = {}
        ranker = MagicMock(stats={'embedded_passages': 1, 'cached_passages': 0})
        def capture(indicator, sources, semantic_ranker=None):
            seen['sources'], seen['ranker'] = sources, semantic_ranker
            return []
        module = 'apps.scoring.management.commands.warm_embedding_cache'
        with override_settings(CAPABILITY_EMBEDDING_CACHE_DIR='/tmp/x'), \
                patch(f'{module}.configured_policy', return_value={'mode': 'hybrid', 'deduplicate': 'exact-page-text-v1'}), \
                patch(f'{module}.ranker_for', return_value=ranker), patch(f'{module}.select_context', side_effect=capture):
            call_command('warm_embedding_cache', str(self.sprint.pk))
        self.assertIs(seen['ranker'], ranker)
        self.assertEqual(len(seen['sources']), 1)  # the duplicate page is read once, as the assessment would
