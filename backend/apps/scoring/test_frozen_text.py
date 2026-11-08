"""Frozen evidence stored once by hash: same evaluation inputs, smaller runs, tamper-evident."""
import json

from django.test import TestCase, override_settings

from apps.documents.models import Document
from apps.extraction.models import DocumentPage
from apps.institutions.models import Institution
from apps.scoring.capability.storage import TEXT_FORMAT, create_run, digest, frozen_sources, text_hash
from apps.scoring.models import CapabilityRun, FrozenText
from apps.sprints.models import Sprint

PAGES = {1: 'The institution approved its Strategic Plan 2019-24 with e-governance as a priority.',
         2: 'The Registrar owns the ERP system that serves admissions and examinations.'}


class FrozenTextTests(TestCase):
    def setUp(self):
        institution = Institution.objects.create(name='VISTAS')
        self.sprint = Sprint.objects.create(institution=institution, mode=Sprint.SprintMode.VERIFIED_CRI)
        doc = Document.objects.create(sprint=self.sprint, original_filename='NAAC SSR.pdf', document_type='naac_ssr',
                                      status=Document.Status.PROCESSED, page_count=2)
        for number, text in PAGES.items():
            DocumentPage.objects.create(document=doc, page_number=number, text=text)

    def run_with(self, store):
        with override_settings(CAPABILITY_FROZEN_TEXT_STORE=store):
            return create_run(institution_id=self.sprint.institution_id, sprint_id=self.sprint.pk)

    def test_hashed_run_reads_back_exactly_what_an_inline_run_holds(self):
        inline, hashed = self.run_with(False), self.run_with(True)
        self.assertNotIn('sources_format', inline.inputs)
        self.assertEqual(hashed.inputs['sources_format'], TEXT_FORMAT)
        self.assertTrue(all('text' not in s and len(s['text_hash']) == 64 for s in hashed.inputs['sources']))
        fresh = CapabilityRun.objects.get(pk=hashed.pk)
        self.assertEqual(frozen_sources(fresh), inline.inputs['sources'])
        self.assertEqual(frozen_sources(inline), inline.inputs['sources'])
        self.assertEqual(digest(fresh.inputs), fresh.inputs_hash)
        self.assertLess(len(json.dumps(hashed.inputs['sources'])), len(json.dumps(inline.inputs['sources'])) + 200)

    def test_a_second_run_stores_no_new_text(self):
        self.run_with(True)
        count = FrozenText.objects.count()
        self.run_with(True)
        self.assertEqual(FrozenText.objects.count(), count)

    def test_altered_or_missing_text_is_refused(self):
        run = self.run_with(True)
        row = FrozenText.objects.get(text_hash=run.inputs['sources'][0]['text_hash'])
        FrozenText.objects.filter(pk=row.pk).update(text_json=json.dumps(json.loads(row.text_json) + ' altered'))
        with self.assertRaises(ValueError):
            frozen_sources(CapabilityRun.objects.get(pk=run.pk))
        with self.assertRaises(ValueError):
            row.text_json = '"x"'
            row.save()
        with self.assertRaises(ValueError):
            row.delete()

    def test_damaged_pdf_characters_store_and_read_back(self):
        from apps.scoring.capability.storage import store_texts
        odd = 'Table\x00cell \ud800 broken glyph'
        hashed = store_texts([{'id': 'x', 'document_id': 'd', 'page_number': 1, 'text': odd}])
        stored = FrozenText.objects.get(text_hash=hashed[0]['text_hash'])
        self.assertEqual(json.loads(stored.text_json), odd)

    def test_hash_is_of_the_exact_text(self):
        self.assertEqual(text_hash('abc'), 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad')
