"""The production database must not freeze half a review transaction."""
from threading import Event, Thread
from unittest import skipUnless

from django.db import connection, connections, transaction
from django.test import TransactionTestCase

from apps.documents.models import Document
from apps.extraction.models import DocumentPage
from apps.facts.models import ExtractedFact, FactReviewHistory
from apps.institutions.models import Institution
from apps.sprints.models import Sprint
from .capability.storage import create_run


@skipUnless(connection.vendor == 'postgresql', 'PostgreSQL snapshot-lock regression')
class ReviewSnapshotConcurrencyTests(TransactionTestCase):
    def test_review_history_and_claim_revision_are_frozen_together(self):
        institution = Institution.objects.create(name='Synthetic College')
        sprint = Sprint.objects.create(institution=institution)
        doc = Document.objects.create(sprint=sprint)
        DocumentPage.objects.create(document=doc, page_number=1, text='Synthetic source-backed record for the test.')
        fact = ExtractedFact.objects.create(sprint=sprint, document=doc, field_key='synthetic', value=20)
        halfway, release, reading, finished = Event(), Event(), Event(), Event()
        errors, results = [], []
        def writer():
            try:
                with transaction.atomic():
                    f = ExtractedFact.objects.get(pk=fact.pk)
                    FactReviewHistory.objects.create(fact=f, action='corrected', original_value=20, new_value=21)
                    halfway.set()
                    if not release.wait(10): raise RuntimeError('Writer timed out')
                    f.value, f.status = 21, 'corrected'; f.save()
            except BaseException as exc: errors.append(exc)
            finally: connections.close_all()
        def reader():
            try:
                reading.set()
                run = create_run(institution_id=institution.pk, sprint_id=sprint.pk,
                    population='Synthetic', reference_period='2025-26')
                results.append(run.inputs['reviewed_evidence']['claims'][0])
            except BaseException as exc: errors.append(exc)
            finally: finished.set(); connections.close_all()
        w = Thread(target=writer); r = Thread(target=reader)
        try:
            w.start(); self.assertTrue(halfway.wait(5))
            r.start(); self.assertTrue(reading.wait(5))
            self.assertFalse(finished.wait(0.2))
        finally:
            release.set(); w.join(10)
            if r.ident: r.join(10)
        self.assertFalse(w.is_alive()); self.assertFalse(r.is_alive()); self.assertEqual(errors, [])
        self.assertEqual(results[0]['value'], 21)
        self.assertEqual(results[0]['decisions'][0]['after'], 21)
