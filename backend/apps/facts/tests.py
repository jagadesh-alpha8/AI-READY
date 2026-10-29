import tempfile
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.documents.models import Document
from apps.gaps.models import GapEvent, GapItem
from apps.gaps.services import generate_gaps_for_sprint
from apps.institutions.models import Institution
from apps.sprints.models import Sprint

from .models import EvidenceRequest, EvidenceRequestDocument, EvidenceRequestEvent, ExtractedFact, FactReviewHistory

PASSWORD = 'Str0ng!DevPassw0rd'


class FactTestBase(APITestCase):
    def setUp(self):
        self.institution = Institution.objects.create(name='MKCE', city='Karur', state='TN')
        self.other_institution = Institution.objects.create(name='Other', city='X', state='Y')

        self.iqac = self._make_user('iqac@test.edu', User.Role.IQAC_COORDINATOR, self.institution)
        self.hod = self._make_user('hod@test.edu', User.Role.IQAC_COORDINATOR, self.institution)
        self.viewer = self._make_user('viewer@test.edu', User.Role.IQAC_COORDINATOR, self.other_institution)
        self.outsider = self._make_user('outsider@test.edu', User.Role.IQAC_COORDINATOR, self.other_institution)

        self.sprint = Sprint.objects.create(institution=self.institution, mode=Sprint.SprintMode.VERIFIED_CRI)

    @staticmethod
    def _make_user(email, role, institution):
        return User.objects.create_user(
            email=email, username=email.split('@')[0], password=PASSWORD,
            first_name='Test', last_name=role, role=role, institution=institution,
        )

    def _auth(self, user):
        login = self.client.post('/api/v1/auth/login/', {'email': user.email, 'password': PASSWORD})
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {login.data["access_token"]}')

    def _make_fact(self, **overrides):
        defaults = {
            'sprint': self.sprint,
            'field_name': 'Faculty Foundation AI Certification %',
            'field_key': 'faculty_foundation_ai_certified_pct',
            'value': 62.5,
            'data_type': ExtractedFact.DataType.PERCENTAGE,
            'pillar': 'aiqif_c4',
            'owner_role': 'HOD',
            'source_page': 'Page 45',
            'source_snippet': '120 out of 192 faculty completed AI foundation FDP.',
            'confidence_score': 0.85,
            'extraction_method': 'ocr_table_extractor',
        }
        defaults.update(overrides)
        return ExtractedFact.objects.create(**defaults)


class FactListingTests(FactTestBase):
    def test_list_scoped_to_sprint(self):
        self._make_fact()
        other_sprint = Sprint.objects.create(institution=self.institution, mode=Sprint.SprintMode.QUICK_CRI)
        self._make_fact(sprint=other_sprint, field_key='other_field')

        self._auth(self.iqac)
        response = self.client.get(f'/api/v1/sprints/{self.sprint.id}/facts/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)

    def test_list_without_trailing_slash_matches_frontend_client(self):
        self._make_fact()
        self._auth(self.iqac)
        response = self.client.get(f'/api/v1/sprints/{self.sprint.id}/facts')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)

    def test_list_forbidden_for_outsider(self):
        self._make_fact()
        self._auth(self.outsider)
        response = self.client.get(f'/api/v1/sprints/{self.sprint.id}/facts/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_list_unauthenticated_rejected(self):
        response = self.client.get(f'/api/v1/sprints/{self.sprint.id}/facts/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_facts_endpoint_is_read_only(self):
        self._auth(self.iqac)
        response = self.client.post(f'/api/v1/sprints/{self.sprint.id}/facts/', {
            'field_key': 'sneaky', 'value': 1,
        })
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_the_list_is_always_paginated(self):
        for i in range(3):
            self._make_fact(field_key=f'field_{i}')
        self._auth(self.iqac)

        plain = self.client.get(f'/api/v1/sprints/{self.sprint.id}/facts/')
        self.assertEqual((plain.data['count'], len(plain.data['results'])), (3, 3))

        paginated = self.client.get(f'/api/v1/sprints/{self.sprint.id}/facts/', {'page_size': 2, 'page': 1})
        self.assertIn('results', paginated.data)
        self.assertEqual(paginated.data['count'], 3)
        self.assertEqual(len(paginated.data['results']), 2)

    # -- filtering -------------------------------------------------------

    def test_filter_by_pillar(self):
        self._make_fact(pillar='aiqif_c4')
        self._make_fact(field_key='f2', pillar='aiqif_c1')
        self._auth(self.iqac)
        response = self.client.get(f'/api/v1/sprints/{self.sprint.id}/facts/', {'pillar': 'aiqif_c1'})
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['pillar'], 'aiqif_c1')

    def test_filter_by_status(self):
        f1 = self._make_fact()
        self._make_fact(field_key='f2')
        f1.status = ExtractedFact.Status.CONFIRMED
        f1.save(update_fields=['status'])

        self._auth(self.iqac)
        response = self.client.get(f'/api/v1/sprints/{self.sprint.id}/facts/', {'status': 'confirmed'})
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], str(f1.id))

    def test_filter_by_owner_role(self):
        self._make_fact(owner_role='HOD')
        self._make_fact(field_key='f2', owner_role='REGISTRAR')
        self._auth(self.iqac)
        response = self.client.get(f'/api/v1/sprints/{self.sprint.id}/facts/', {'owner_role': 'REGISTRAR'})
        self.assertEqual(response.data['count'], 1)

    def test_filter_by_document(self):
        from apps.documents.models import Document
        document = Document.objects.create(sprint=self.sprint, document_type='naac_ssr')
        self._make_fact(document=document)
        self._make_fact(field_key='f2')

        self._auth(self.iqac)
        response = self.client.get(f'/api/v1/sprints/{self.sprint.id}/facts/', {'document': str(document.id)})
        self.assertEqual(response.data['count'], 1)

    def test_filter_by_confidence_range(self):
        self._make_fact(field_key='low', confidence_score=0.3)
        self._make_fact(field_key='high', confidence_score=0.9)
        self._auth(self.iqac)

        response = self.client.get(f'/api/v1/sprints/{self.sprint.id}/facts/', {'confidence_min': 0.5})
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['field_key'], 'high')

        response = self.client.get(f'/api/v1/sprints/{self.sprint.id}/facts/', {'confidence_max': 0.5})
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['field_key'], 'low')

    def test_ordering_by_confidence_score(self):
        self._make_fact(field_key='low', confidence_score=0.3)
        self._make_fact(field_key='high', confidence_score=0.9)
        self._auth(self.iqac)
        response = self.client.get(f'/api/v1/sprints/{self.sprint.id}/facts/', {'ordering': 'confidence_score'})
        keys = [row['field_key'] for row in response.data['results']]
        self.assertEqual(keys, ['low', 'high'])


class FactDetailTests(FactTestBase):
    def test_retrieve_includes_empty_review_history_initially(self):
        fact = self._make_fact()
        self._auth(self.iqac)
        response = self.client.get(f'/api/v1/facts/{fact.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['review_history'], [])
        self.assertEqual(response.data['status'], ExtractedFact.Status.EXTRACTED)

    def test_retrieve_forbidden_for_outsider(self):
        fact = self._make_fact()
        self._auth(self.outsider)
        response = self.client.get(f'/api/v1/facts/{fact.id}/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_no_generic_patch_endpoint(self):
        fact = self._make_fact()
        self._auth(self.iqac)
        response = self.client.patch(f'/api/v1/facts/{fact.id}/', {'value': 999})
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_response_includes_frontend_compatible_aliases(self):
        """FactsReview.tsx (existing, unmodified) reads fact.audit_field_id/
        fact.value_json/fact.confidence -- none of which are real column
        names (field_key/value/confidence_score)."""
        fact = self._make_fact()
        self._auth(self.iqac)
        response = self.client.get(f'/api/v1/facts/{fact.id}/')
        self.assertEqual(response.data['audit_field_id'], fact.field_key)
        self.assertEqual(response.data['value_json'], fact.value)
        self.assertEqual(response.data['confidence'], fact.confidence_score)

    def test_response_includes_source_document_filename(self):
        """The Facts Review UI's 'Source Document' column needs a
        human-readable name -- source_document_id alone is a UUID."""
        from apps.documents.models import Document

        document = Document.objects.create(
            sprint=self.sprint, document_type='naac_ssr', original_filename='ssr_2025.pdf',
        )
        fact = self._make_fact(source_document=document)
        self._auth(self.iqac)
        response = self.client.get(f'/api/v1/facts/{fact.id}/')
        self.assertEqual(response.data['source_document_filename'], 'ssr_2025.pdf')

    def test_source_document_filename_blank_when_no_source_document(self):
        fact = self._make_fact()
        self._auth(self.iqac)
        response = self.client.get(f'/api/v1/facts/{fact.id}/')
        self.assertEqual(response.data['source_document_filename'], '')


class FactConfirmActionTests(FactTestBase):
    def test_confirm_sets_status_and_reviewer(self):
        fact = self._make_fact()
        self._auth(self.hod)
        response = self.client.post(f'/api/v1/facts/{fact.id}/confirm/', {'reason': 'Looks right'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], ExtractedFact.Status.CONFIRMED)

        fact.refresh_from_db()
        self.assertEqual(fact.status, ExtractedFact.Status.CONFIRMED)
        self.assertEqual(fact.reviewed_by, self.hod)
        self.assertIsNotNone(fact.reviewed_at)

    def test_confirm_creates_history_entry_with_unchanged_value(self):
        fact = self._make_fact()
        self._auth(self.hod)
        self.client.post(f'/api/v1/facts/{fact.id}/confirm/', {'reason': 'Verified against source'})

        entry = FactReviewHistory.objects.get(fact=fact)
        self.assertEqual(entry.action, FactReviewHistory.Action.CONFIRMED)
        self.assertEqual(entry.original_value, 62.5)
        self.assertIsNone(entry.new_value)
        self.assertEqual(entry.user, self.hod)
        self.assertEqual(entry.reason, 'Verified against source')

    def test_confirm_accepts_legacy_comment_field(self):
        """The unmodified frontend sends `comment`, not `reason`."""
        fact = self._make_fact()
        self._auth(self.hod)
        self.client.post(f'/api/v1/facts/{fact.id}/confirm/', {'comment': 'Confirmed by reviewer'})
        entry = FactReviewHistory.objects.get(fact=fact)
        self.assertEqual(entry.reason, 'Confirmed by reviewer')

    def test_confirm_without_trailing_slash(self):
        fact = self._make_fact()
        self._auth(self.hod)
        response = self.client.post(f'/api/v1/facts/{fact.id}/confirm', {})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_viewer_cannot_confirm(self):
        fact = self._make_fact()
        self._auth(self.viewer)
        response = self.client.post(f'/api/v1/facts/{fact.id}/confirm/', {})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        fact.refresh_from_db()
        self.assertEqual(fact.status, ExtractedFact.Status.EXTRACTED)

    def test_unauthenticated_confirm_rejected(self):
        fact = self._make_fact()
        response = self.client.post(f'/api/v1/facts/{fact.id}/confirm/', {})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_outsider_cannot_confirm(self):
        fact = self._make_fact()
        self._auth(self.outsider)
        response = self.client.post(f'/api/v1/facts/{fact.id}/confirm/', {})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class FactCorrectActionTests(FactTestBase):
    def test_correct_updates_value_and_status(self):
        fact = self._make_fact()
        self._auth(self.hod)
        response = self.client.post(f'/api/v1/facts/{fact.id}/correct/', {
            'new_value': 75.0, 'reason': 'Recount from master register',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['value'], 75.0)
        self.assertEqual(response.data['status'], ExtractedFact.Status.CORRECTED)

        fact.refresh_from_db()
        self.assertEqual(fact.value, 75.0)

    def test_correct_accepts_legacy_corrected_value_field(self):
        """The unmodified frontend sends `corrected_value`, not `new_value`."""
        fact = self._make_fact()
        self._auth(self.hod)
        response = self.client.post(f'/api/v1/facts/{fact.id}/correct/', {
            'corrected_value': 'Active Industry 4.0 & AI Lab', 'comment': 'User correction',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['value'], 'Active Industry 4.0 & AI Lab')

    def test_correct_requires_a_value(self):
        fact = self._make_fact()
        self._auth(self.hod)
        response = self.client.post(f'/api/v1/facts/{fact.id}/correct/', {'reason': 'no value given'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_correct_accepts_explicit_null_as_a_real_value(self):
        """JSON null is itself a legitimate corrected value, not 'no value provided'."""
        fact = self._make_fact()
        self._auth(self.hod)
        response = self.client.post(
            f'/api/v1/facts/{fact.id}/correct/', {'new_value': None}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        fact.refresh_from_db()
        self.assertIsNone(fact.value)

    def test_original_value_is_never_destroyed_by_a_correction(self):
        fact = self._make_fact(value=62.5)
        self._auth(self.hod)
        self.client.post(
            f'/api/v1/facts/{fact.id}/correct/', {'new_value': 75.0, 'reason': 'first correction'}, format='json',
        )

        history = FactReviewHistory.objects.get(fact=fact)
        self.assertEqual(history.original_value, 62.5)
        self.assertEqual(history.new_value, 75.0)

        fact.refresh_from_db()
        self.assertEqual(fact.value, 75.0)

    def test_full_correction_chain_is_reconstructable(self):
        """Multiple corrections: every intermediate value survives in history,
        so the original extracted value is always recoverable from the
        earliest entry even after several rounds of correction."""
        from .verification import corrections
        fact = self._make_fact(value=62.5)
        self._auth(self.hod)
        self.client.post(
            f'/api/v1/facts/{fact.id}/correct/', {'new_value': 70.0, 'reason': 'round 1'}, format='json',
        )
        # A second change to a value a person already decided goes through a proposal another reviewer approves.
        refused = self.client.post(
            f'/api/v1/facts/{fact.id}/correct/', {'new_value': 75.0, 'reason': 'round 2'}, format='json',
        )
        self.assertEqual(refused.status_code, status.HTTP_400_BAD_REQUEST)
        doc = Document.objects.create(sprint=self.sprint, original_filename='aqar.pdf', document_type='aqar_report',
                                      status=Document.Status.PROCESSED, page_count=10)
        fact.refresh_from_db()
        proposal = corrections.propose(fact, self.hod, value=75.0, reason='round 2', source_document=doc,
                                       source_page='4', source_snippet='75%')
        corrections.approve(proposal, self.iqac)

        history = list(FactReviewHistory.objects.filter(fact=fact).order_by('created_at'))
        self.assertEqual([h.action for h in history], ['corrected', 'correction_proposed', 'corrected'])
        self.assertEqual(history[0].original_value, 62.5)
        self.assertEqual(history[0].new_value, 70.0)
        self.assertEqual(history[2].original_value, 70.0)
        self.assertEqual(history[2].new_value, 75.0)

        fact.refresh_from_db()
        self.assertEqual(fact.value, 75.0)
        # the true original is still recoverable from the earliest record
        earliest_original = history[0].original_value
        self.assertEqual(earliest_original, 62.5)

    def test_correction_appears_in_detail_review_history(self):
        fact = self._make_fact()
        self._auth(self.hod)
        self.client.post(
            f'/api/v1/facts/{fact.id}/correct/', {'new_value': 75.0, 'reason': 'recount'}, format='json',
        )

        response = self.client.get(f'/api/v1/facts/{fact.id}/')
        self.assertEqual(len(response.data['review_history']), 1)
        self.assertEqual(response.data['review_history'][0]['action'], 'corrected')
        self.assertEqual(response.data['review_history'][0]['original_value'], 62.5)
        self.assertEqual(response.data['review_history'][0]['new_value'], 75.0)

    def test_viewer_cannot_correct(self):
        fact = self._make_fact()
        self._auth(self.viewer)
        response = self.client.post(f'/api/v1/facts/{fact.id}/correct/', {'new_value': 1}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_outsider_cannot_correct(self):
        fact = self._make_fact()
        self._auth(self.outsider)
        response = self.client.post(f'/api/v1/facts/{fact.id}/correct/', {'new_value': 1}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class FactRejectActionTests(FactTestBase):
    def test_reject_sets_status_without_changing_value(self):
        fact = self._make_fact(value=62.5)
        self._auth(self.hod)
        response = self.client.post(f'/api/v1/facts/{fact.id}/reject/', {'reason': 'Not applicable to this sprint'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], ExtractedFact.Status.REJECTED)
        self.assertEqual(response.data['value'], 62.5)

        history = FactReviewHistory.objects.get(fact=fact)
        self.assertEqual(history.action, FactReviewHistory.Action.REJECTED)
        self.assertEqual(history.original_value, 62.5)
        self.assertIsNone(history.new_value)

    def test_viewer_cannot_reject(self):
        fact = self._make_fact()
        self._auth(self.viewer)
        response = self.client.post(f'/api/v1/facts/{fact.id}/reject/', {})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_reject_rejected(self):
        fact = self._make_fact()
        response = self.client.post(f'/api/v1/facts/{fact.id}/reject/', {})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_outsider_cannot_reject(self):
        fact = self._make_fact()
        self._auth(self.outsider)
        response = self.client.post(f'/api/v1/facts/{fact.id}/reject/', {})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class FactRequestEvidenceActionTests(FactTestBase):
    def test_request_evidence_sets_status(self):
        fact = self._make_fact()
        self._auth(self.hod)
        response = self.client.post(f'/api/v1/facts/{fact.id}/request-evidence/', {
            'reason': 'Need the signed circular, not just the summary',
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], ExtractedFact.Status.EVIDENCE_REQUESTED)

        history = FactReviewHistory.objects.get(fact=fact)
        self.assertEqual(history.action, FactReviewHistory.Action.EVIDENCE_REQUESTED)

    def test_request_evidence_without_trailing_slash(self):
        fact = self._make_fact()
        self._auth(self.hod)
        self.assertEqual(self.client.post(f'/api/v1/facts/{fact.id}/request-evidence', {}).status_code,
                         status.HTTP_400_BAD_REQUEST)  # what is needed, and why, is required
        response = self.client.post(f'/api/v1/facts/{fact.id}/request-evidence', {'reason': 'Signed copy'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_viewer_cannot_request_evidence(self):
        fact = self._make_fact()
        self._auth(self.viewer)
        response = self.client.post(f'/api/v1/facts/{fact.id}/request-evidence/', {})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_outsider_cannot_request_evidence(self):
        fact = self._make_fact()
        self._auth(self.outsider)
        response = self.client.post(f'/api/v1/facts/{fact.id}/request-evidence/', {})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)



class ConfirmingFactClosesUnconfirmedGapTests(FactTestBase):
    """Confirmed/Corrected closes only the fact's own "unconfirmed fact" gap
    (removing its -3 CRI penalty). Genuine gaps stay open, and the CRI score
    and Evidence Confidence both come only from Confirmed/Corrected facts."""

    PILLAR = 'aiqif_c4'

    def _gap(self, gap_type, *, fact=None, priority='medium'):
        from apps.gaps.models import GapItem
        return GapItem.objects.create(
            sprint=self.sprint, gap_type=gap_type, title='t', pillar=self.PILLAR,
            priority=priority, source_fact=fact,
        )

    def _pillar(self):
        from apps.scoring.services.cri_engine import run_scoring_engine
        run = run_scoring_engine(self.sprint)
        pillar = next(p for p in run.pillar_snapshot if p['pillar'] == self.PILLAR)
        return run, pillar

    # -- which gaps close ------------------------------------------------

    def test_confirm_closes_only_its_own_unconfirmed_fact_gap(self):
        from apps.gaps.models import GapItem
        fact = self._make_fact()
        self._make_fact(value=70.0)  # another document's value for the same field: the conflict is real
        other_fact = self._make_fact(field_key='other')
        own_gap = self._gap(GapItem.GapType.UNCONFIRMED_FACT, fact=fact)
        other_facts_gap = self._gap(GapItem.GapType.UNCONFIRMED_FACT, fact=other_fact)
        genuine = [
            self._gap(GapItem.GapType.CONFLICT, fact=fact, priority='high'),
            self._gap(GapItem.GapType.LOW_CONFIDENCE, fact=fact),
            self._gap(GapItem.GapType.MISSING_DOCUMENT, priority='blocking'),
            self._gap(GapItem.GapType.STALE_DATA),
        ]

        self._auth(self.hod)
        response = self.client.post(f'/api/v1/facts/{fact.id}/confirm/', {'reason': 'ok'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        own_gap.refresh_from_db()
        self.assertEqual(own_gap.status, GapItem.Status.RESOLVED)
        self.assertEqual(own_gap.resolved_by, self.hod)
        self.assertIsNotNone(own_gap.resolved_at)
        for gap in [other_facts_gap, *genuine]:
            gap.refresh_from_db()
            self.assertEqual(gap.status, GapItem.Status.OPEN, gap.gap_type)

    def test_correct_closes_its_unconfirmed_fact_gap(self):
        from apps.gaps.models import GapItem
        fact = self._make_fact()
        gap = self._gap(GapItem.GapType.UNCONFIRMED_FACT, fact=fact)
        self._auth(self.hod)
        response = self.client.post(
            f'/api/v1/facts/{fact.id}/correct/', {'new_value': 75.0, 'reason': 'recount'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        gap.refresh_from_db()
        self.assertEqual(gap.status, GapItem.Status.RESOLVED)

    def test_reject_moves_the_gap_to_needs_replacement_and_request_evidence_leaves_it_open(self):
        from apps.gaps.models import GapItem
        rejected = self._make_fact(field_key='r')
        pending = self._make_fact(field_key='p')
        rejected_gap = self._gap(GapItem.GapType.UNCONFIRMED_FACT, fact=rejected)
        pending_gap = self._gap(GapItem.GapType.UNCONFIRMED_FACT, fact=pending)

        self._auth(self.hod)  # the facts' owner role rejects
        self.assertEqual(
            self.client.post(f'/api/v1/facts/{rejected.id}/reject/', {'reason': 'n/a'}).status_code,
            status.HTTP_200_OK,
        )
        self._auth(self.iqac)  # a coordinator may chase evidence for any fact
        self.assertEqual(
            self.client.post(f'/api/v1/facts/{pending.id}/request-evidence/', {'reason': 'need it'}).status_code,
            status.HTTP_200_OK,
        )
        rejected_gap.refresh_from_db()
        pending_gap.refresh_from_db()
        # A rejected value is not confirmed: its gap stays active (with its penalty) as needs-replacement.
        self.assertEqual(rejected_gap.status, GapItem.Status.NEEDS_REPLACEMENT)
        self.assertIn(rejected_gap.status, GapItem.ACTIVE_STATUSES)
        self.assertEqual(pending_gap.status, GapItem.Status.OPEN)

    # -- effect on the CRI -----------------------------------------------

    def test_confirming_raises_pillar_score_and_removes_the_penalty(self):
        from apps.gaps.models import GapItem
        fact = self._make_fact(confidence_score=0.85)
        self._gap(GapItem.GapType.UNCONFIRMED_FACT, fact=fact)
        # A second, still-unconfirmed fact keeps its gap: only the confirmed
        # fact's own -3 should disappear.
        pending = self._make_fact(field_key='pending', confidence_score=0.4)
        self._gap(GapItem.GapType.UNCONFIRMED_FACT, fact=pending)

        _run, before = self._pillar()
        self.assertEqual(before['raw_score'], 0.0)      # no reviewed evidence yet
        self.assertEqual(before['evidence_count'], 0)
        self.assertEqual(before['gap_count'], 2)

        self._auth(self.hod)
        self.client.post(f'/api/v1/facts/{fact.id}/confirm/', {'reason': 'ok'})

        _run, after = self._pillar()
        self.assertEqual(after['evidence_count'], 1)
        self.assertEqual(after['gap_count'], 1)          # the confirmed fact's gap is gone
        self.assertEqual(after['raw_score'], 85.0 - 3.0)  # only the pending fact's -3 remains
        self.assertGreater(after['raw_score'], before['raw_score'])

    def test_genuine_gap_penalty_is_kept_after_confirming(self):
        from apps.gaps.models import GapItem
        fact = self._make_fact(confidence_score=0.85)
        self._make_fact(value=70.0)  # a second, disagreeing value: confirming one side doesn't reconcile it
        self._gap(GapItem.GapType.UNCONFIRMED_FACT, fact=fact)
        self._gap(GapItem.GapType.CONFLICT, fact=fact, priority='high')  # -5, real problem

        self._auth(self.hod)
        self.client.post(f'/api/v1/facts/{fact.id}/confirm/', {'reason': 'ok'})

        _run, pillar = self._pillar()
        self.assertEqual(pillar['raw_score'], 85.0 - 5.0)

    def test_score_and_confidence_use_only_confirmed_or_corrected_facts(self):
        confirmed = self._make_fact(field_key='c1', confidence_score=0.9)
        corrected = self._make_fact(field_key='c2', confidence_score=0.7)
        # Unreviewed / rejected facts must not move the score or the confidence.
        self._make_fact(field_key='x1', confidence_score=0.1)
        self._make_fact(field_key='x2', confidence_score=0.2, status=ExtractedFact.Status.REJECTED)
        self._make_fact(field_key='x3', confidence_score=0.3, status=ExtractedFact.Status.EVIDENCE_REQUESTED)

        self._auth(self.hod)
        self.client.post(f'/api/v1/facts/{confirmed.id}/confirm/', {'reason': 'ok'})
        self.client.post(
            f'/api/v1/facts/{corrected.id}/correct/', {'new_value': 1, 'reason': 'fix'}, format='json',
        )

        run, pillar = self._pillar()
        self.assertEqual(pillar['evidence_count'], 2)
        self.assertEqual(pillar['raw_score'], 80.0)          # avg(0.9, 0.7) * 100
        self.assertEqual(pillar['confidence_score'], 0.8)    # same two facts
        # Overall confidence = pillar confidence x the (unchanged) pillar weight.
        self.assertAlmostEqual(run.overall_confidence, round(0.8 * pillar['weight'], 4))
        self.assertAlmostEqual(run.overall_cri, round(80.0 * pillar['weight'], 2))


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix='evidence-tests-'))
class EvidenceRequestWorkflowTests(FactTestBase):
    """Request -> assignment -> evidence -> explicit reviewer decision (apps/facts/evidence_requests.py)."""

    def setUp(self):
        super().setUp()
        self.registrar = self._make_user('registrar@test.edu', User.Role.IQAC_COORDINATOR, self.institution)
        # Decides evidence: the facts are owned by HOD, who also submits it here, so the reviewer is an
        # Institution Admin (apps/facts/ownership.py); the IQAC Coordinator requests and withdraws.
        self.admin = self._make_user('admin@test.edu', User.Role.IQAC_COORDINATOR, self.institution)
        self.fact = self._make_fact()

    # -- helpers ------------------------------------------------------------------------------------
    def _request(self, user=None, **body):
        self._auth(user or self.iqac)
        payload = {'description': 'Signed FDP attendance register, to back the 62.5% figure.', **body}
        return self.client.post(f'/api/v1/facts/{self.fact.id}/request-evidence', payload, format='json')

    def _open(self, assignee=None, **body):
        response = self._request(assigned_to=str((assignee or self.hod).id), **body)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return EvidenceRequest.objects.get(fact=self.fact)

    def _url(self, req, action=''):
        return f'/api/v1/evidence-requests/{req.id}' + (f'/{action}' if action else '')

    def _upload(self, req, user=None, name='register.pdf', **extra):
        self._auth(user or self.hod)
        f = SimpleUploadedFile(name, b'%PDF-1.4 signed FDP register ' + name.encode(), content_type='application/pdf')
        with patch('apps.extraction.views.dispatch_job', side_effect=lambda job: job):
            return self.client.post(self._url(req, 'submit'), {'file': f, 'source_page': '3',
                                                               'source_snippet': '120 of 192 signed.', **extra},
                                    format='multipart')

    def _submit_text(self, req, user=None, text='120 of 192 faculty completed AI foundation FDP.',
                     source='Signed HR training register, 2025-26'):
        self._auth(user or self.hod)
        with patch('apps.facts.tasks.analyze_text_evidence_submission.delay'):
            return self.client.post(self._url(req, 'submit'), {
                'submitted_text': text, 'source_context': source,
            }, format='json')

    def _review(self, req, user, decision, **body):
        self._auth(user)
        return self.client.post(self._url(req, 'review'), {'decision': decision, **body}, format='json')

    def _link(self, req):
        return req.evidence.order_by('-created_at').first()

    # -- request + assignment --------------------------------------------------------------------------
    def test_request_records_who_what_and_whom_with_history(self):
        req = self._open(due_date=str(date.today() + timedelta(days=7)))
        self.fact.refresh_from_db()
        self.assertEqual(self.fact.status, ExtractedFact.Status.EVIDENCE_REQUESTED)
        self.assertEqual((req.requested_by, req.assigned_to, req.suggested_owner_role, req.status),
                         (self.iqac, self.hod, 'HOD', 'open'))
        self.assertEqual(req.fact_status_before, ExtractedFact.Status.EXTRACTED)
        self.assertEqual(FactReviewHistory.objects.get(fact=self.fact).action, 'evidence_requested')
        self.assertEqual(list(req.events.values_list('action', flat=True)), ['created', 'assigned'])
        self.assertEqual(self._request().status_code, status.HTTP_400_BAD_REQUEST)  # one open request per fact

    def test_request_stores_required_evidence_reason_and_responsible_role(self):
        self._auth(self.iqac)
        response = self.client.post(f'/api/v1/facts/{self.fact.id}/request-evidence', {
            'evidence_needed': 'Signed faculty training register for 2025-26.',
            'reason': 'Verify the reported completion percentage.',
            'assigned_to': str(self.hod.id),
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        req = EvidenceRequest.objects.get(fact=self.fact)
        self.assertEqual((req.evidence_needed, req.reason, req.suggested_owner_role),
                         ('Signed faculty training register for 2025-26.', 'Verify the reported completion percentage.', 'HOD'))
        self.assertEqual(response.data['open_evidence_request']['status'], 'open')
        self.assertEqual(req.events.first().data['responsible_role'], 'HOD')

    def test_fact_reviewer_can_create_request_within_fact_ownership(self):
        response = self._request(user=self.hod, assigned_to=str(self.registrar.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_request_needs_a_description_an_eligible_person_and_a_future_due_date(self):
        self.assertEqual(self._request(description='').status_code, status.HTTP_400_BAD_REQUEST)
        for bad in (self.viewer, self.outsider):
            self.assertEqual(self._request(assigned_to=str(bad.id)).status_code, status.HTTP_400_BAD_REQUEST)
        past = str(date.today() - timedelta(days=1))
        self.assertEqual(self._request(due_date=past).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self._request(user=self.viewer).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self._request(user=self.outsider).status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(EvidenceRequest.objects.exists())

    def test_assignees_are_active_non_viewer_people_of_the_college(self):
        self._auth(self.iqac)
        rows = self.client.get(f'/api/v1/sprints/{self.sprint.id}/evidence-requests/assignees').data
        emails = {r['email'] for r in rows}
        self.assertIn('hod@test.edu', emails)
        self.assertNotIn('viewer@test.edu', emails)
        self.assertNotIn('outsider@test.edu', emails)

    def test_an_unassigned_request_is_assigned_by_authorized_staff_only(self):
        response = self._request()  # no user holds the role yet: left unassigned, never guessed
        req = EvidenceRequest.objects.get(fact=self.fact)
        self.assertIsNone(req.assigned_to)
        self._auth(self.outsider)  # another college's coordinator
        self.assertIn(self.client.post(self._url(req, 'assign'), {'assigned_to': str(self.hod.id)},
                                       format='json').status_code, (400, 403, 404))
        self._auth(self.iqac)
        response = self.client.post(self._url(req, 'assign'), {'assigned_to': str(self.hod.id), 'note': 'HOD has it'},
                                    format='json')
        self.assertEqual(response.data['assigned_to_name'], self.hod.get_full_name())
        response = self.client.post(self._url(req, 'assign'), {'assigned_to': str(self.registrar.id)}, format='json')
        event = response.data['events'][-1]
        self.assertEqual((event['action'], event['data']['from']['id'], event['data']['to']['id']),
                         ('assigned', str(self.hod.id), str(self.registrar.id)))

    def test_the_assignee_sees_it_as_a_task(self):
        self._open()
        self._auth(self.hod)
        mine = self.client.get('/api/v1/evidence-requests?assigned_to=me&unresolved=true').data
        self.assertEqual([r['fact_field_key'] for r in mine], [self.fact.field_key])
        self.assertEqual(self.client.get('/api/v1/evidence-requests/summary').data['assigned_to_me'], 1)
        self._auth(self.outsider)
        self.assertEqual(self.client.get('/api/v1/evidence-requests').data, [])
        self.assertEqual(self.client.get(f'/api/v1/evidence-requests/{EvidenceRequest.objects.get().id}').status_code,
                         status.HTTP_404_NOT_FOUND)

    def test_overdue_requests_are_flagged_and_filterable(self):
        req = self._open(due_date=str(date.today() + timedelta(days=1)))
        EvidenceRequest.objects.filter(pk=req.pk).update(due_date=date.today() - timedelta(days=2))
        self._auth(self.iqac)
        rows = self.client.get(f'/api/v1/sprints/{self.sprint.id}/evidence-requests?overdue=true').data
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]['overdue'])
        self.assertTrue(self.client.get(f'/api/v1/facts/{self.fact.id}').data['open_evidence_request']['overdue'])

    # -- evidence ------------------------------------------------------------------------------------
    def test_only_the_assignee_submits_and_nothing_is_confirmed_by_it(self):
        req = self._open()
        self.assertEqual(self._upload(req, user=self.registrar).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn(self._upload(req, user=self.viewer).status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND))
        response = self._upload(req)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        link = self._link(req)
        self.assertTrue(link.uploaded_for_request)
        self.assertEqual((link.document.sprint, link.document.uploaded_by, link.source_page), (self.sprint, self.hod, '3'))
        self.assertEqual(response.data['status'], 'submitted')
        self.fact.refresh_from_db()
        self.assertEqual((self.fact.status, self.fact.value), (ExtractedFact.Status.EVIDENCE_REQUESTED, 62.5))

    def test_an_existing_sprint_document_can_be_linked_but_not_one_from_elsewhere(self):
        req = self._open()
        mine = Document.objects.create(sprint=self.sprint, document_type='hr_records', original_filename='hr.pdf')
        other_sprint = Sprint.objects.create(institution=self.other_institution, mode=Sprint.SprintMode.VERIFIED_CRI)
        theirs = Document.objects.create(sprint=other_sprint, document_type='hr_records', original_filename='x.pdf')
        self._auth(self.hod)
        submit = lambda doc: self.client.post(self._url(req, 'submit'), {'document_id': str(doc.id)}, format='json')  # noqa: E731
        with patch('apps.extraction.views.dispatch_job', side_effect=lambda job: job), \
                patch('apps.facts.tasks.analyze_existing_document_evidence.delay'):
            self.assertEqual(submit(theirs).status_code, status.HTTP_400_BAD_REQUEST)
            self.assertEqual(submit(mine).status_code, status.HTTP_200_OK)
            self.assertEqual(submit(mine).status_code, status.HTTP_400_BAD_REQUEST)  # already linked
        self.assertFalse(self._link(req).uploaded_for_request)

    def test_extraction_can_be_started_for_an_upload_and_its_facts_are_only_suggested(self):
        req = self._open()
        with patch('apps.facts.evidence_requests._start_extraction') as start:
            self._upload(req, run_extraction='true')
        document = self._link(req).document
        start.assert_called_once_with(self.sprint, document, link=self._link(req))
        # What an extraction of that document would add: its own facts with page and snippet.
        found = self._make_fact(document=document, source_document=document, value=63.0, source_page='3',
                                source_snippet='121 of 192 signed.')
        self._make_fact(document=document, field_key='campus_area', field_name='Campus Area')
        self._auth(self.iqac)
        suggested = self.client.get(self._url(req)).data['suggested_facts']
        self.assertEqual([(s['id'], s['why'], s['source_page']) for s in suggested], [(str(found.id), 'Same field', '3')])
        found.refresh_from_db()
        self.fact.refresh_from_db()
        self.assertEqual((found.status, self.fact.status, self.fact.value), ('extracted', 'evidence_requested', 62.5))
        self.assertEqual(EvidenceRequest.objects.get().status, 'submitted')

    # -- decisions -------------------------------------------------------------------------------------
    def test_direct_fact_actions_wait_for_the_request_decision(self):
        self._open()
        self._auth(self.hod)  # even the owner role must decide on the request
        self.assertEqual(self.client.post(f'/api/v1/facts/{self.fact.id}/confirm', {}).status_code,
                         status.HTTP_400_BAD_REQUEST)

    def test_accept_confirms_the_fact_with_the_accepted_citation(self):
        req = self._open()
        self._upload(req)
        link = self._link(req)
        self.assertEqual(self._review(req, self.hod, 'accept', evidence_id=str(link.id)).status_code,
                         status.HTTP_400_BAD_REQUEST)  # the submitter cannot accept their own evidence
        response = self._review(req, self.admin, 'accept', evidence_id=str(link.id), source_page='4',
                                reason='Register matches.')
        self.assertEqual(response.data['status'], 'accepted', response.data)
        self.fact.refresh_from_db()
        self.assertEqual((self.fact.status, self.fact.value), (ExtractedFact.Status.CONFIRMED, 62.5))
        self.assertEqual((self.fact.source_document, self.fact.source_page, self.fact.source_snippet),
                         (link.document, '4', '120 of 192 signed.'))
        self.assertEqual(self.fact.review_history.first().action, 'confirmed')
        self.assertEqual([e['action'] for e in response.data['events']],
                         ['created', 'assigned', 'evidence_submitted', 'fact_updated', 'accepted'])
        # Resolved: kept visible, but closed to further changes.
        self.assertEqual(self._review(req, self.iqac, 'withdraw', reason='x').status_code, status.HTTP_400_BAD_REQUEST)
        rows = self.client.get(f'/api/v1/sprints/{self.sprint.id}/evidence-requests?status=accepted').data
        self.assertEqual(len(rows), 1)

    def test_accept_with_correction_records_the_new_value(self):
        req = self._open()
        self._upload(req)
        link = self._link(req)
        self.assertEqual(self._review(req, self.admin, 'accept_corrected', evidence_id=str(link.id)).status_code,
                         status.HTTP_400_BAD_REQUEST)  # needs the corrected value
        self._review(req, self.admin, 'accept_corrected', evidence_id=str(link.id), corrected_value=63.0)
        self.fact.refresh_from_db()
        history = self.fact.review_history.first()
        self.assertEqual((self.fact.status, self.fact.value), (ExtractedFact.Status.CORRECTED, 63.0))
        self.assertEqual((history.action, history.original_value, history.new_value), ('corrected', 62.5, 63.0))
        self.assertEqual(EvidenceRequest.objects.get().status, 'accepted_corrected')

    def test_rejected_evidence_goes_back_for_more_and_can_be_resubmitted(self):
        req = self._open()
        self._upload(req)
        first = self._link(req)
        self.assertEqual(self._review(req, self.admin, 'reject', evidence_id=str(first.id)).status_code,
                         status.HTTP_400_BAD_REQUEST)  # a reason is required
        response = self._review(req, self.admin, 'reject', evidence_id=str(first.id), reason='Unsigned copy.')
        self.assertEqual(response.data['status'], 'returned')
        first.refresh_from_db()
        self.assertEqual((first.status, first.review_reason), ('rejected', 'Unsigned copy.'))
        self.fact.refresh_from_db()
        self.assertEqual(self.fact.status, ExtractedFact.Status.EVIDENCE_REQUESTED)

        self._upload(req, name='signed.pdf')
        second = self._link(req)
        response = self._review(req, self.admin, 'reject', evidence_id=str(second.id), reason='Wrong year.',
                                return_to_assignee=False)
        self.assertEqual(response.data['status'], 'returned')
        self.assertEqual([e['action'] for e in response.data['events']].count('evidence_rejected'), 2)

    def test_return_for_more_evidence_is_distinct_from_reject_and_allows_another_submission(self):
        req = self._open()
        self._upload(req)
        first = self._link(req)
        response = self._review(req, self.admin, 'return', evidence_id=str(first.id),
                                reason='Please include the signed approval page.')
        self.assertEqual(response.data['status'], 'returned')
        first.refresh_from_db()
        self.assertEqual(first.status, EvidenceRequestDocument.Status.RETURNED)
        self.assertTrue(req.events.filter(action=EvidenceRequestEvent.Action.EVIDENCE_RETURNED).exists())
        self._submit_text(req, text='Signed by the principal on 15 June 2026.', source='Approval page')
        self.assertEqual(req.evidence.count(), 2)

    def test_text_evidence_is_linked_and_ai_support_result_is_advisory_only(self):
        from .evidence_analysis import analyze_submission

        req = self._open()
        response = self._submit_text(req)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        link = self._link(req)
        self.assertIsNone(link.document_id)
        self.assertEqual(link.submitted_text, '120 of 192 faculty completed AI foundation FDP.')
        with patch('apps.facts.evidence_analysis.get_ai_service') as get_service:
            get_service.return_value.extract_structured_data.return_value = {
                'outcome': 'supports', 'summary': 'The text supports the reported completion rate.',
                'quote': '120 of 192 faculty completed AI foundation FDP.', 'page_number': None,
                'suggested_corrected_value': None, 'confidence': 0.96, 'reasoning': 'Counts match the stated rate.',
            }
            analyze_submission(link)
        link.refresh_from_db()
        req.refresh_from_db()
        self.fact.refresh_from_db()
        self.assertEqual((link.analysis_status, link.analysis_outcome, link.analysis_confidence), ('ready', 'supports', 0.96))
        self.assertEqual((req.status, self.fact.status, self.fact.value),
                         ('ready_for_review', ExtractedFact.Status.EVIDENCE_REQUESTED, 62.5))
        actions = list(req.events.values_list('action', flat=True))
        self.assertIn('analysis_started', actions)
        self.assertIn('analysis_completed', actions)
        self.assertEqual(FactReviewHistory.objects.filter(fact=self.fact, action='confirmed').count(), 0)

    def test_uploaded_document_pages_feed_ai_assessment_and_citation(self):
        from .evidence_analysis import analyze_pending_document_submissions

        req = self._open()
        response = self._upload(req)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        link = self._link(req)
        pages = {'format_supported': True, 'pages': [{
            'page_number': 3, 'text': '120 of 192 faculty completed AI foundation FDP.',
        }]}
        with patch('apps.facts.evidence_analysis.get_ai_service') as get_service:
            get_service.return_value.extract_structured_data.return_value = {
                'outcome': 'supports', 'summary': 'The register supports the reported value.',
                'quote': '120 of 192 faculty completed AI foundation FDP.', 'page_number': 3,
                'suggested_corrected_value': None, 'confidence': 0.94,
            }
            analyze_pending_document_submissions(link.document, pages)
        link.refresh_from_db()
        req.refresh_from_db()
        self.assertEqual((link.analysis_status, link.analysis_outcome, link.analysis_page_number),
                         ('ready', 'supports', 3))
        self.assertEqual(req.status, EvidenceRequest.Status.READY_FOR_REVIEW)

    def test_ai_contradiction_and_corrected_value_are_shown_but_not_applied(self):
        from .evidence_analysis import analyze_submission

        req = self._open()
        self._submit_text(req, text='The verified figure is 58 percent.', source='Signed annual HR report')
        link = self._link(req)
        with patch('apps.facts.evidence_analysis.get_ai_service') as get_service:
            get_service.return_value.extract_structured_data.return_value = {
                'outcome': 'contradicts', 'summary': 'The source gives a different figure.',
                'quote': 'The verified figure is 58 percent.', 'page_number': None,
                'suggested_corrected_value': 58, 'confidence': 0.9, 'reasoning': 'The source directly states 58 percent.',
            }
            analyze_submission(link)
        self.fact.refresh_from_db()
        link.refresh_from_db()
        self.assertEqual((link.analysis_outcome, link.analysis_suggested_value), ('contradicts', 58))
        self.assertEqual((self.fact.status, self.fact.value), (ExtractedFact.Status.EVIDENCE_REQUESTED, 62.5))

    def test_ocr_and_extraction_failures_are_reported_and_audited(self):
        from .evidence_analysis import analyze_submission, fail_pending_document_submissions

        req = self._open()
        self._upload(req)
        link = self._link(req)
        analyze_submission(link, pages={'format_supported': True, 'pages': [],
                                        'ocr_warnings': ['Page 1 requires OCR but OCR is unavailable.']})
        link.refresh_from_db()
        self.assertEqual(link.analysis_status, 'failed')
        self.assertIn('OCR is unavailable', link.analysis_error)
        self.assertTrue(req.events.filter(action='analysis_failed').exists())

        req2 = self._open_for_another_fact()
        self._upload(req2, name='corrupt.pdf')
        link2 = self._link(req2)
        fail_pending_document_submissions(link2.document, 'Corrupt PDF')
        link2.refresh_from_db()
        self.assertEqual(link2.analysis_status, 'failed')
        self.assertIn('Corrupt PDF', link2.analysis_error)

    def _open_for_another_fact(self):
        another = self._make_fact(field_key='faculty_training_count', field_name='Faculty Training Count')
        self.fact = another
        return self._open()

    def test_ai_quote_must_be_verifiable_before_assessment_is_ready(self):
        from .evidence_analysis import analyze_submission

        req = self._open()
        self._submit_text(req)
        link = self._link(req)
        with patch('apps.facts.evidence_analysis.get_ai_service') as get_service:
            get_service.return_value.extract_structured_data.return_value = {
                'outcome': 'supports', 'summary': 'Seems relevant.', 'quote': 'Invented quote',
                'page_number': None, 'suggested_corrected_value': None, 'confidence': 0.7, 'reasoning': 'No basis.',
            }
            analyze_submission(link)
        link.refresh_from_db()
        self.assertEqual(link.analysis_status, 'failed')
        self.assertIn('word-for-word', link.analysis_error)

    def test_withdraw_restores_the_fact_and_needs_a_reason(self):
        self.fact.status = ExtractedFact.Status.CONFIRMED
        self.fact.save()
        req = self._open()
        self.assertEqual(self._review(req, self.iqac, 'withdraw').status_code, status.HTTP_400_BAD_REQUEST)
        response = self._review(req, self.iqac, 'withdraw', reason='Figure no longer used.')
        self.assertEqual((response.data['status'], response.data['resolution_note']),
                         ('withdrawn', 'Figure no longer used.'))
        self.fact.refresh_from_db()
        self.assertEqual(self.fact.status, ExtractedFact.Status.CONFIRMED)
        self.assertEqual(self.fact.review_history.first().action, 'request_withdrawn')

    def test_only_an_accepted_decision_changes_the_cri_and_only_after_recalculation(self):
        from apps.scoring.models import ScoringRun
        from apps.scoring.services import run_scoring_engine
        before = run_scoring_engine(self.sprint)
        self.assertEqual(before.overall_cri, 0.0)  # an extracted fact never counts
        req = self._open()
        self._upload(req)
        self.assertEqual(run_scoring_engine(self.sprint).overall_cri, 0.0)  # evidence alone changes nothing
        self._review(req, self.admin, 'accept', evidence_id=str(self._link(req).id))
        self.sprint.refresh_from_db()
        self.assertEqual(self.sprint.overall_cri, 0.0)  # not until the CRI is recalculated
        after = run_scoring_engine(self.sprint)
        self.assertGreater(after.overall_cri, 0.0)
        before.refresh_from_db()
        self.assertEqual((before.overall_cri, ScoringRun.objects.filter(sprint=self.sprint).count()), (0.0, 3))

    def test_comments_are_part_of_the_trail(self):
        req = self._open()
        self._auth(self.hod)
        response = self.client.post(self._url(req, 'comment'), {'note': 'Register is with the principal.'},
                                    format='json')
        self.assertEqual(response.data['events'][-1]['action'], 'commented')
        self._auth(self.viewer)
        self.assertIn(self.client.post(self._url(req, 'comment'), {'note': 'x'}, format='json').status_code,
                      (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND))

    def test_a_document_submitted_as_evidence_cannot_be_deleted(self):
        req = self._open()
        self._upload(req)
        document = self._link(req).document
        self._auth(self.hod)
        response = self.client.delete(f'/api/v1/documents/{document.id}')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertTrue(Document.objects.filter(pk=document.pk).exists())


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix='evidence-gap-tests-'))
class LowConfidenceGapEvidenceTests(FactTestBase):
    """A low-confidence gap is settled through the fact's evidence request: only a different reviewer's
    accepted decision closes it; uploads, extraction, rejection and withdrawal leave it open, and the
    generic gap actions cannot go around that (apps/gaps/services.py, apps/gaps/views.py)."""

    # The evidence-request helpers, shared with EvidenceRequestWorkflowTests.
    _request = EvidenceRequestWorkflowTests._request
    _open = EvidenceRequestWorkflowTests._open
    _url = EvidenceRequestWorkflowTests._url
    _upload = EvidenceRequestWorkflowTests._upload
    _review = EvidenceRequestWorkflowTests._review
    _link = EvidenceRequestWorkflowTests._link

    def setUp(self):
        super().setUp()
        self.admin = self._make_user('admin@test.edu', User.Role.IQAC_COORDINATOR, self.institution)
        self.fact = self._make_fact(confidence_score=0.4, confidence_reason='Blurred table cell.')
        generate_gaps_for_sprint(self.sprint)
        self.gap = GapItem.objects.get(source_fact=self.fact, gap_type=GapItem.GapType.LOW_CONFIDENCE)

    def _gap_row(self, user=None):
        self._auth(user or self.iqac)
        rows = self.client.get(f'/api/v1/sprints/{self.sprint.id}/gaps').data['results']
        return next(r for r in rows if r['id'] == str(self.gap.id))

    def _gap_action(self, action, user=None, **body):
        self._auth(user or self.hod)  # the gap's owner role (its fact is HOD's)
        return self.client.post(f'/api/v1/gaps/{self.gap.id}/{action}', body, format='json')

    def _gap_status(self):
        self.gap.refresh_from_db()
        return self.gap.status

    def test_gap_row_shows_the_request_and_its_assignee_apart_from_the_owner_role(self):
        row = self._gap_row()
        self.assertEqual((row['owner_role'], row['evidence_request'], row['fact_status']), ('HOD', None, 'extracted'))
        self.assertIn('not been verified', row['resolve_blocked_reason'])
        self._open(assignee=self.hod)
        row = self._gap_row()
        self.assertEqual(row['owner_role'], 'HOD')  # still only the role
        self.assertEqual((row['evidence_request']['status'], row['evidence_request']['assigned_to_name']),
                         ('open', self.hod.get_full_name()))
        self.assertIn('open evidence request', row['resolve_blocked_reason'])
        self.assertIn('open evidence request', row['close_blocked_reason'])
        # The assignee finds it in "Assigned to me"; the request shows the gap it will settle.
        self._auth(self.hod)
        mine = self.client.get('/api/v1/evidence-requests?assigned_to=me&unresolved=true').data
        self.assertEqual([r['fact'] for r in mine], [self.fact.id])
        detail = self.client.get(f"/api/v1/evidence-requests/{mine[0]['id']}").data
        self.assertEqual([(g['gap_type'], g['status']) for g in detail['fact_gaps']], [('low_confidence', 'open')])

    def test_a_second_request_for_the_same_fact_is_refused(self):
        self._open()
        response = self._request(assigned_to=str(self.hod.id))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(EvidenceRequest.objects.filter(fact=self.fact).count(), 1)

    def test_uploading_or_extracting_evidence_leaves_the_gap_and_the_fact_alone(self):
        req = self._open()
        with patch('apps.facts.evidence_requests._start_extraction'):
            self._upload(req, run_extraction='true')
        document = self._link(req).document
        self._make_fact(document=document, source_document=document, value=63.0, confidence_score=0.95)
        self.fact.refresh_from_db()
        self.assertEqual((self.fact.status, self.fact.value), (ExtractedFact.Status.EVIDENCE_REQUESTED, 62.5))
        self.assertEqual(self._gap_status(), 'open')
        self.assertEqual(self._gap_action('resolve', resolution='Evidence uploaded.').status_code,
                         status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self._gap_status(), 'open')

    def test_only_a_different_reviewers_acceptance_closes_the_gap(self):
        req = self._open()
        self._upload(req)
        link = self._link(req)
        self.assertEqual(self._review(req, self.hod, 'accept', evidence_id=str(link.id)).status_code,
                         status.HTTP_400_BAD_REQUEST)  # the submitter
        self.assertIn(self._review(req, self.viewer, 'accept', evidence_id=str(link.id)).status_code,
                      (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND))
        self.assertEqual(self._review(req, self.outsider, 'accept', evidence_id=str(link.id)).status_code,
                         status.HTTP_404_NOT_FOUND)
        self.assertEqual(self._gap_status(), 'open')
        self._review(req, self.admin, 'accept', evidence_id=str(link.id))
        self.gap.refresh_from_db()
        self.assertEqual((self.gap.status, self.gap.resolved_by), ('resolved', self.admin))
        for part in (str(req.id), 'register.pdf', 'page 3', 'accepted by', self.admin.get_full_name()):
            self.assertIn(part, self.gap.resolution)
        self.fact.refresh_from_db()
        self.assertEqual(self.fact.status, ExtractedFact.Status.CONFIRMED)

    def test_accepting_with_a_correction_closes_the_gap_and_says_so(self):
        req = self._open()
        self._upload(req)
        self._review(req, self.admin, 'accept_corrected', evidence_id=str(self._link(req).id), corrected_value=63.0)
        self.gap.refresh_from_db()
        self.assertEqual(self.gap.status, 'resolved')
        self.assertIn('accepted with correction', self.gap.resolution)

    def test_evidence_acceptance_closes_only_this_facts_unconfirmed_and_low_confidence_gaps(self):
        other_fact = self._make_fact(value=59.0, confidence_score=0.95)
        replacement = GapItem.objects.create(
            sprint=self.sprint, gap_type=GapItem.GapType.UNCONFIRMED_FACT,
            title='Replacement needed for another fact', source_fact=other_fact,
            status=GapItem.Status.NEEDS_REPLACEMENT,
        )
        conflict = GapItem.objects.create(
            sprint=self.sprint, gap_type=GapItem.GapType.CONFLICT, title='Unresolved faculty figure conflict',
            source_fact=self.fact, conflict_fact_b=other_fact, conflict_value_a=self.fact.value,
            conflict_value_b=other_fact.value, status=GapItem.Status.OPEN,
        )
        unconfirmed = GapItem.objects.create(
            sprint=self.sprint, gap_type=GapItem.GapType.UNCONFIRMED_FACT,
            title='This fact still needs confirmation', source_fact=self.fact,
        )
        req = self._open()
        self._upload(req)
        self._review(req, self.admin, 'accept', evidence_id=str(self._link(req).id))
        for gap in (self.gap, unconfirmed):
            gap.refresh_from_db()
            self.assertEqual(gap.status, GapItem.Status.RESOLVED)
            self.assertTrue(gap.events.filter(action=GapEvent.Action.AUTO_RESOLVED).exists())
        replacement.refresh_from_db()
        conflict.refresh_from_db()
        self.assertEqual(replacement.status, GapItem.Status.NEEDS_REPLACEMENT)
        self.assertEqual(conflict.status, GapItem.Status.OPEN)
        event = req.events.get(action=EvidenceRequestEvent.Action.GAPS_RESOLVED)
        self.assertEqual(set(event.data['gap_ids']), {str(self.gap.id), str(unconfirmed.id)})

    def test_rejected_returned_or_withdrawn_evidence_keeps_the_gap_open(self):
        req = self._open()
        self._upload(req)
        self._review(req, self.admin, 'reject', evidence_id=str(self._link(req).id), reason='Unsigned copy.')
        self.assertEqual(self._gap_status(), 'open')
        self.assertEqual(self._gap_row()['evidence_request']['status'], 'returned')  # next: more evidence
        for action in ('resolve', 'skip', 'mark-unavailable'):
            self.assertEqual(self._gap_action(action, resolution='Done.').status_code, status.HTTP_400_BAD_REQUEST)
        self._upload(req, name='second.pdf')
        self._review(req, self.admin, 'reject', evidence_id=str(self._link(req).id), reason='Wrong year.',
                     return_to_assignee=False)
        self.assertEqual(self._gap_status(), 'open')
        self._review(req, self.iqac, 'withdraw', reason='Not needed.')
        self.assertEqual(self._gap_status(), 'open')
        # Withdrawn: the fact is unverified again, so Resolve still points to review / a new request.
        self.assertEqual(self._gap_action('resolve', resolution='Done.').status_code, status.HTTP_400_BAD_REQUEST)

    def test_generic_resolve_needs_a_reviewed_citation_and_an_explanation(self):
        self.assertEqual(self._gap_action('resolve', resolution='Looks fine.').status_code,
                         status.HTTP_400_BAD_REQUEST)
        document = Document.objects.create(sprint=self.sprint, document_type='hr_records', original_filename='hr.pdf')
        self.fact.source_document = document
        self.fact.save()
        self._auth(self.hod)
        self.client.post(f'/api/v1/facts/{self.fact.id}/confirm', {})  # confirmed directly, with its citation
        self.assertEqual(self._gap_status(), 'open')  # confirming alone does not settle the low-confidence flag
        self.assertEqual(self._gap_action('resolve').status_code, status.HTTP_400_BAD_REQUEST)  # no explanation
        response = self._gap_action('resolve', resolution='Checked against hr.pdf page 45.')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(self._gap_status(), 'resolved')

    def test_skip_or_mark_unavailable_needs_an_explanation(self):
        self.assertEqual(self._gap_action('skip').status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self._gap_action('skip', resolution='Not part of this audit.').status_code,
                         status.HTTP_200_OK)

    def test_other_gap_types_keep_their_own_rules(self):
        other = self._make_fact(field_key='campus_area', field_name='Campus Area', confidence_score=0.9)
        generate_gaps_for_sprint(self.sprint)
        unconfirmed = GapItem.objects.get(source_fact=other, gap_type=GapItem.GapType.UNCONFIRMED_FACT)
        self._auth(self.hod)
        response = self.client.post(f'/api/v1/gaps/{unconfirmed.id}/resolve', {}, format='json')
        # Not the low-confidence rule: a "needs confirmation" gap closes by confirming its fact.
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Confirm or correct the fact', response.data['detail'])
        self.client.post(f'/api/v1/facts/{other.id}/confirm', {})
        unconfirmed.refresh_from_db()
        self.assertEqual(unconfirmed.status, 'resolved')


class EvidenceRequestSprintScopeTests(FactTestBase):
    """Evidence requests are listed per sprint (?sprint=<id>) or across sprints (?sprint=all / none), and a sprint
    the user cannot access is refused, never silently shown as empty."""

    def setUp(self):
        super().setUp()
        self.sprint2 = Sprint.objects.create(institution=self.institution, mode=Sprint.SprintMode.VERIFIED_CRI,
                                             name='Second sprint')
        self.other_sprint = Sprint.objects.create(institution=self.other_institution, mode=Sprint.SprintMode.VERIFIED_CRI)
        self.fact1 = self._make_fact()
        self.fact2 = self._make_fact(sprint=self.sprint2, field_key='labs')
        self._auth(self.iqac)
        for fact in (self.fact1, self.fact2):
            r = self.client.post(f'/api/v1/facts/{fact.id}/request-evidence', {
                'description': 'The signed register behind this figure.', 'assigned_to': str(self.hod.id),
            }, format='json')
            self.assertEqual(r.status_code, status.HTTP_200_OK, r.data)

    def _codes(self, query):
        r = self.client.get(f'/api/v1/evidence-requests{query}')
        self.assertEqual(r.status_code, status.HTTP_200_OK, r.data)
        rows = r.data['results'] if isinstance(r.data, dict) else r.data
        return sorted(row['fact_field_key'] for row in rows), rows

    def test_one_sprint_or_all_sprints(self):
        keys, rows = self._codes(f'?sprint={self.sprint.id}')
        self.assertEqual(keys, [self.fact1.field_key])
        self.assertEqual((rows[0]['sprint_code'], rows[0]['sprint_name']), (self.sprint.sprint_code, self.sprint.name))
        self.assertEqual(self._codes(f'?sprint={self.sprint2.id}')[0], ['labs'])
        self.assertEqual(len(self._codes('?sprint=all')[0]), 2)
        self.assertEqual(len(self._codes('')[0]), 2)

    def test_status_views_combine_with_the_sprint(self):
        self._auth(self.hod)
        keys, _ = self._codes(f'?assigned_to=me&unresolved=true&sprint={self.sprint2.id}')
        self.assertEqual(keys, ['labs'])
        summary = self.client.get(f'/api/v1/evidence-requests/summary?sprint={self.sprint2.id}').data
        self.assertEqual(summary['assigned_to_me'], 1)
        self.assertEqual(self.client.get('/api/v1/evidence-requests/summary').data['assigned_to_me'], 2)

    def test_a_sprint_of_another_college_is_refused(self):
        r = self.client.get(f'/api/v1/evidence-requests?sprint={self.other_sprint.id}')
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.get('/api/v1/evidence-requests?sprint=not-a-uuid').status_code,
                         status.HTTP_404_NOT_FOUND)
        self._auth(self.outsider)
        self.assertEqual(self._codes('?sprint=all')[0], [])  # other colleges see none of ours
        r = self.client.get(f'/api/v1/evidence-requests/summary?sprint={self.sprint.id}')
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)


TEST_CROSSWALK = [
    ('AIQIF-C5.1', [{'metric': '2.1.2', 'naac_key_indicator': '2.1', 'relationship': 'Contextual'}], 'AI-QIF v1.0'),
    ('AIQIF-C3.1', [{'metric': '1.1.3', 'naac_key_indicator': '1.1', 'relationship': 'Direct/Supporting'}],
     'AI-QIF v1.0'),
]


class AIQIFExpertQueueTests(FactTestBase):
    """Rule 3 (what counts toward coverage), the Super Admin's expert queue and decisions, the sales summary,
    and the baseline gate (apps/facts/aiqif_tagging.py)."""

    def setUp(self):
        super().setUp()
        from .models import FactAIQIFMapping
        self.M = FactAIQIFMapping
        self.expert = self._make_user('expert@ingage.test', User.Role.SUPER_ADMIN, None)
        self.consultant = self._make_user('sales@ingage.test', User.Role.CONSULTANT, None)
        patcher = patch('apps.facts.aiqif_tagging.crosswalk_rows', return_value=TEST_CROSSWALK)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _tag(self, fact, code, **fields):
        from apps.scoring.constants import AIQIF_INDICATORS
        defaults = {'reason': 'x', 'confidence': 0.9, 'status': self.M.Status.MAPPED}
        defaults.update(fields)
        return self.M.objects.create(fact=fact, criterion=AIQIF_INDICATORS[code][0], indicator_code=code, **defaults)

    def _covered(self):
        from apps.scoring.services import run_scoring_engine
        cov = run_scoring_engine(self.sprint).evidence_coverage
        return sorted(r['code'] for r in cov['indicators'] if r['covered']) if 'indicators' in cov else cov

    def test_only_accepted_direct_or_supporting_tags_on_confirmed_ai_evidence_count(self):
        from .aiqif_tagging import counting_q
        ok = self._make_fact(field_key='a', fact_kind='ai_evidence', status='confirmed')
        self._tag(ok, 'AIQIF-C4.1', auto_accepted=True)                                  # counts
        self._tag(ok, 'AIQIF-C4.2', review_status='confirmed')                           # counts (expert)
        self._tag(ok, 'AIQIF-C5.1', auto_accepted=True, relationship='contextual')       # contextual: no
        self._tag(ok, 'AIQIF-C6.1', auto_accepted=True, review_status='rejected')        # rejected: no
        self._tag(ok, 'AIQIF-C6.2')                                                      # waiting: no
        unconfirmed = self._make_fact(field_key='b', fact_kind='ai_evidence')
        self._tag(unconfirmed, 'AIQIF-C7.1', auto_accepted=True)                         # fact not confirmed: no
        context = self._make_fact(field_key='c', fact_kind='context', status='confirmed')
        self._tag(context, 'AIQIF-C7.2', auto_accepted=True)                             # not AI evidence: no
        counted = sorted(self.M.objects.filter(counting_q()).values_list('indicator_code', flat=True))
        self.assertEqual(counted, ['AIQIF-C4.1', 'AIQIF-C4.2'])

    def test_coverage_is_provisional_while_the_expert_queue_is_not_empty(self):
        from apps.scoring.services import run_scoring_engine
        fact = self._make_fact(field_key='a', fact_kind='ai_evidence', status='confirmed')
        tag = self._tag(fact, 'AIQIF-C4.1')
        cov = run_scoring_engine(self.sprint).evidence_coverage
        self.assertEqual((cov['provisional'], cov['expert_queue']['tags'], cov['covered_count']), (True, 1, 0))
        self._auth(self.expert)
        r = self.client.post(f'/api/v1/facts/{fact.id}/aiqif-mappings/AIQIF-C4.1/review', {'decision': 'confirm'},
                             format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK, r.data)
        cov = self.sprint.scoring_runs.order_by('-created_at').first().evidence_coverage
        self.assertEqual((cov['provisional'], cov['covered_count']), (False, 1))
        self.assertTrue(FactReviewHistory.objects.filter(fact=fact, action='aiqif_tag_reviewed').exists())
        tag.refresh_from_db()
        self.assertEqual(tag.reviewed_by, self.expert)

    def test_unclassified_facts_wait_for_the_expert(self):
        from .aiqif_tagging import queue_counts
        self._make_fact(field_key='legacy')  # extracted before kinds existed
        self.assertEqual(queue_counts(self.sprint), {'tags': 0, 'facts': 1, 'total': 1})

    def test_only_the_super_admin_sees_the_queue_and_decides(self):
        fact = self._make_fact(field_key='seats', fact_kind='context', kind_needs_check=True,
                               source_snippet='120 seats in the AI programme.')
        url = f'/api/v1/sprints/{self.sprint.id}/aiqif-expert-queue'
        for user in (self.iqac, self.consultant):
            self._auth(user)
            self.assertEqual(self.client.get(url).status_code, status.HTTP_403_FORBIDDEN)
            self.assertEqual(self.client.post(f'/api/v1/facts/{fact.id}/fact-kind', {'fact_kind': 'ai_evidence'},
                                              format='json').status_code, status.HTTP_403_FORBIDDEN)
            self.assertEqual(self.client.post(f'/api/v1/facts/{fact.id}/aiqif-mappings',
                                              {'indicator_code': 'C5.2'}, format='json').status_code,
                             status.HTTP_403_FORBIDDEN)
        self._auth(self.expert)
        r = self.client.get(url)
        self.assertEqual((r.data['count'], r.data['facts'][0]['id']), (1, str(fact.id)))
        self.assertEqual(len(r.data['indicators']), 36)
        # The expert decides it is AI evidence and adds the indicator: the queue is empty again.
        r = self.client.post(f'/api/v1/facts/{fact.id}/fact-kind', {'fact_kind': 'ai_evidence', 'note': 'AI seats.'},
                             format='json')
        self.assertEqual((r.status_code, r.data['fact_kind'], r.data['kind_needs_check']), (200, 'ai_evidence', True))
        r = self.client.post(f'/api/v1/facts/{fact.id}/aiqif-mappings',
                             {'indicator_code': 'C5.2', 'relationship': 'supporting', 'note': 'Seats in AI.'},
                             format='json')
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)
        tag = r.data['aiqif_mappings'][0]
        self.assertEqual((tag['indicator_code'], tag['source'], tag['review_status']),
                         ('AIQIF-C5.2', 'expert', 'confirmed'))
        self.assertEqual((r.data['kind_needs_check'], self.client.get(url).data['count']), (False, 0))
        self.assertEqual(sorted(FactReviewHistory.objects.filter(fact=fact).values_list('action', flat=True)),
                         ['aiqif_tag_added', 'fact_kind_changed'])
        bad = self.client.post(f'/api/v1/facts/{fact.id}/aiqif-mappings', {'indicator_code': 'C99.9'}, format='json')
        self.assertEqual(bad.status_code, status.HTTP_400_BAD_REQUEST)

    def test_the_sales_summary_has_no_indicator_codes_and_flags_provisional(self):
        self._make_fact(field_key='a', fact_kind='ai_evidence')
        self._make_fact(field_key='b', fact_kind='context')
        self._make_fact(field_key='c', fact_kind='profile')
        self._make_fact(field_key='d', fact_kind='context', status='rejected')
        self._auth(self.consultant)
        r = self.client.get(f'/api/v1/sprints/{self.sprint.id}/aiqif-summary')
        self.assertEqual(r.status_code, status.HTTP_200_OK, r.data)
        self.assertEqual({k: r.data[k] for k in ('facts', 'ai_evidence', 'context', 'profile', 'not_classified')},
                         {'facts': 3, 'ai_evidence': 1, 'context': 1, 'profile': 1, 'not_classified': 0})
        self.assertFalse(r.data['coverage_provisional'])
        self._make_fact(field_key='e', fact_kind='context', kind_needs_check=True)
        r = self.client.get(f'/api/v1/sprints/{self.sprint.id}/aiqif-summary')
        self.assertEqual((r.data['coverage_provisional'], r.data['expert_queue']['total']), (True, 1))

    def test_no_baseline_decision_while_items_wait_for_the_expert(self):
        from rest_framework.exceptions import ValidationError
        from apps.scoring.services.baseline import _expert_queue_gate
        self._make_fact(field_key='a', fact_kind='context', kind_needs_check=True)
        with self.assertRaises(ValidationError) as caught:
            _expert_queue_gate(self.sprint)
        self.assertIn('waiting for a Super Admin', str(caught.exception.detail['detail']))
        ExtractedFact.objects.update(kind_needs_check=False)
        _expert_queue_gate(self.sprint)  # empty queue: allowed

class ProfileSuggestionTests(FactTestBase):
    """The benchmark profile pre-filled from profile facts (apps/facts/profile_suggestion.py)."""

    def setUp(self):
        super().setUp()
        self.consultant = self._make_user('sales@ingage.test', User.Role.CONSULTANT, None)
        self.url = f'/api/v1/sprints/{self.sprint.id}/profile-suggestion'

    def _profile_fact(self, key, field, value):
        from .profile_suggestion import match_code
        fact = self._make_fact(field_key=key, field_name=key.replace('_', ' '), value=value, fact_kind='profile',
                               profile_field=field)
        fact.profile_code = match_code(fact)
        fact.save()
        return fact

    def test_values_are_matched_to_the_closed_lists_only(self):
        self.assertEqual(self._profile_fact('itype', 'institution_type', 'Engineering College').profile_code, 'engineering')
        self.assertEqual(self._profile_fact('status', 'autonomous_status', 'Affiliated to Anna University').profile_code,
                         'affiliated')
        self.assertEqual(self._profile_fact('body', 'approval_body', 'Approved by AICTE').profile_code, 'AICTE')
        self.assertEqual(self._profile_fact('prog', 'programme', 'MBA').profile_code, 'mba_pgdm')
        self.assertEqual(self._profile_fact('aicte_type', 'institution_type', 'Private-Self Financing').profile_code, '')

    def test_suggestion_shows_conflicts_and_unmatched_values_and_staff_confirm_it(self):
        self._profile_fact('itype', 'institution_type', 'Engineering College')
        self._profile_fact('itype2', 'institution_type', 'Polytechnic')
        self._profile_fact('body', 'approval_body', 'AICTE')
        self._profile_fact('prog', 'programme', 'MBA')
        self._profile_fact('aicte_type', 'institution_type', 'Private-Self Financing')
        self._auth(self.iqac)
        data = self.client.get(self.url).data
        itype = data['suggested']['institution_type']
        self.assertEqual((itype['value'], itype['conflict'], [c['code'] for c in itype['candidates']]),
                         ('', True, ['engineering', 'polytechnic']))
        self.assertEqual(data['suggested']['approval_bodies'], ['AICTE'])
        self.assertEqual([p['programme_type'] for p in data['suggested']['programmes']], ['mba_pgdm'])
        self.assertEqual([u['value'] for u in data['unmatched']], ['Private-Self Financing'])
        values = {'institution_type': 'engineering', 'autonomous_status': 'affiliated', 'approval_bodies': ['AICTE'],
                  'programmes': [{'name': 'MBA', 'programme_type': 'mba_pgdm', 'approval_body': 'AICTE'}]}
        self.assertEqual(self.client.post(self.url, values, format='json').status_code, status.HTTP_403_FORBIDDEN)
        self._auth(self.consultant)
        r = self.client.post(self.url, values, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK, r.data)
        self.assertEqual(r.data['current']['institution_type'], 'engineering')
        self.assertEqual(self.sprint.institution.benchmark_programmes.get().programme_type.code, 'mba_pgdm')
        bad = self.client.post(self.url, {**values, 'institution_type': 'spaceport'}, format='json')
        self.assertEqual(bad.status_code, status.HTTP_400_BAD_REQUEST)


class RetagCommandTests(FactTestBase):
    """python manage.py retag_aiqif_facts (dry run unless --commit)."""

    def _call(self, *args):
        from io import StringIO
        from django.core.management import call_command
        out = StringIO()
        with patch('apps.facts.aiqif_tagging.crosswalk_rows', return_value=TEST_CROSSWALK):
            call_command('retag_aiqif_facts', *args, stdout=out)
        return out.getvalue()

    def setUp(self):
        super().setUp()
        from .models import FactAIQIFMapping
        self.ai = self._make_fact(field_key='ai_course', field_name='AI course', value='Yes',
                                  source_snippet='1.1.3 The MBA has a course on Artificial Intelligence.')
        self.intake = self._make_fact(field_key='mba_intake', field_name='MBA intake', value=120,
                                      source_snippet='2.1.2 Approved intake 120.')
        FactAIQIFMapping.objects.create(fact=self.intake, criterion='aiqif_c3', indicator_code='AIQIF-C3.1',
                                        reason='Programme.', confidence=0.9, status='mapped',
                                        review_status='confirmed')  # a person confirmed it: it counted before

    def test_a_dry_run_changes_nothing(self):
        out = self._call()
        self.assertIn('Would re-tag 2 fact(s)', out)
        self.assertIn('Dry run', out)
        self.ai.refresh_from_db()
        self.assertEqual(self.ai.fact_kind, '')

    def test_commit_classifies_finds_metrics_and_sends_doubtful_facts_to_the_expert(self):
        self._call('--commit')
        self.ai.refresh_from_db()
        self.intake.refresh_from_db()
        self.assertEqual((self.ai.fact_kind, self.ai.naac_metric), ('ai_evidence', '1.1.3'))
        self.assertEqual(list(self.ai.aiqif_mappings.values_list('indicator_code', 'source', 'relationship')),
                         [('AIQIF-C3.1', 'crosswalk', 'direct')])
        self.assertEqual((self.intake.fact_kind, self.intake.naac_metric), ('context', '2.1.2'))
        # Its person-confirmed C3.1 tag is kept (a person's decision wins) but no longer counts on a context fact,
        # so the expert decides the kind; the crosswalk adds C5.1 as Contextual.
        self.assertEqual(sorted(self.intake.aiqif_mappings.values_list('indicator_code', 'relationship')),
                         [('AIQIF-C3.1', 'supporting'), ('AIQIF-C5.1', 'contextual')])
        self.assertTrue(self.intake.kind_needs_check)
        self.assertEqual((self.ai.value, self.intake.value), ('Yes', 120))  # values never change

    def test_old_unreviewed_ai_tags_on_context_facts_do_not_go_to_the_expert(self):
        from .models import FactAIQIFMapping
        FactAIQIFMapping.objects.filter(fact=self.intake).update(review_status='unreviewed')  # never counted
        self._call('--commit')
        self.intake.refresh_from_db()
        self.assertEqual((self.intake.fact_kind, self.intake.kind_needs_check), ('context', False))
        self.assertEqual(list(self.intake.aiqif_mappings.values_list('indicator_code', flat=True)), ['AIQIF-C5.1'])

    def test_it_refuses_without_the_crosswalk(self):
        from io import StringIO
        from django.core.management import CommandError, call_command
        with patch('apps.facts.aiqif_tagging.crosswalk_rows', return_value=[]):
            with self.assertRaises(CommandError):
                call_command('retag_aiqif_facts', '--commit', stdout=StringIO())
        self.ai.refresh_from_db()
        self.assertEqual(self.ai.fact_kind, '')


class PaginatedFactsAndGapsTests(FactTestBase):
    """Facts and gaps lists: always paginated (50 / max 100), filtered on the server, sprint- and
    institution-scoped, facets from aggregates, and a fixed number of queries per page."""

    def _gap(self, **fields):
        defaults = {'sprint': self.sprint, 'gap_type': GapItem.GapType.UNCONFIRMED_FACT, 'title': 'Gap',
                    'pillar': 'aiqif_c4'}
        defaults.update(fields)
        return GapItem.objects.create(**defaults)

    def _doc(self, name):
        return Document.objects.create(sprint=self.sprint, original_filename=name, document_type='naac_ssr',
                                       status=Document.Status.PROCESSED, owner_role='HOD')

    def test_facts_are_paginated_with_counts_and_server_side_filters(self):
        doc = self._doc('ssr.pdf')
        for i in range(60):
            self._make_fact(field_key=f'f{i:02d}', confidence_score=0.9 if i < 10 else 0.4,
                            fact_kind='ai_evidence' if i < 5 else '', source_document=doc if i < 3 else None,
                            source_snippet='The AI lab has 40 GPUs.' if i == 7 else 'x')
        self._auth(self.iqac)
        url = f'/api/v1/sprints/{self.sprint.id}/facts'
        first = self.client.get(url).data
        self.assertEqual((first['count'], len(first['results']), first['previous']), (60, 50, None))
        self.assertIsNotNone(first['next'])
        second = self.client.get(url, {'page': 2}).data
        self.assertEqual(len(second['results']), 10)
        self.assertEqual(len({r['id'] for r in first['results']} | {r['id'] for r in second['results']}), 60)
        self.assertEqual(len(self.client.get(url, {'page_size': 500}).data['results']), 60)  # capped at 100
        self.assertEqual(self.client.get(url, {'confidence_band': 'high'}).data['count'], 10)
        self.assertEqual(self.client.get(url, {'fact_kind': 'ai_evidence'}).data['count'], 5)
        self.assertEqual(self.client.get(url, {'fact_kind': 'none'}).data['count'], 55)
        self.assertEqual(self.client.get(url, {'source_document': 'ssr.pdf'}).data['count'], 3)
        self.assertEqual([r['field_key'] for r in self.client.get(url, {'q': 'gpus'}).data['results']], ['f07'])
        facets = self.client.get(f'{url}/facets').data
        self.assertEqual((facets['total'], facets['confidence_band'], facets['fact_kind']),
                         (60, {'high': 10, 'medium': 0, 'low': 50}, {'ai_evidence': 5, 'none': 55}))
        self.assertEqual(facets['source_document'], {'ssr.pdf': 3})

    def test_gaps_are_paginated_and_filtered_on_the_server(self):
        doc = self._doc('register.pdf')
        facts = [self._make_fact(field_key=f'src{i}', source_document=doc, owner_role='iqac_coordinator')
                 for i in range(2)]
        for i in range(55):
            self._gap(title=f'Gap {i}', priority=GapItem.Priority.HIGH if i < 5 else GapItem.Priority.MEDIUM,
                      source_fact=facts[i] if i < 2 else None)
        self._auth(self.iqac)
        url = f'/api/v1/sprints/{self.sprint.id}/gaps'
        page = self.client.get(url).data
        self.assertEqual((page['count'], len(page['results'])), (55, 50))
        self.assertEqual(self.client.get(url, {'priority': 'high'}).data['count'], 5)
        self.assertEqual(self.client.get(url, {'source_document': 'register.pdf'}).data['count'], 2)
        self.assertEqual(self.client.get(url, {'owner_role': 'iqac_coordinator'}).data['count'], 2)
        self.assertEqual(self.client.get(url, {'q': 'Gap 4'}).data['count'], 11)  # "Gap 4" and "Gap 40" to "Gap 49"
        facets = self.client.get(f'{url}/facets').data
        self.assertEqual((facets['total'], facets['open'], facets['priority']), (55, 55, {'high': 5, 'medium': 50}))
        self.assertEqual(facets['source_document'], {'register.pdf': 2})

    def test_cri_pillar_filter_and_its_options_on_facts_and_gaps(self):
        for i in range(3):
            self._make_fact(field_key=f'c4_{i}', pillar='aiqif_c4')
        self._make_fact(field_key='c1', pillar='aiqif_c1')
        self._gap(title='c4 gap')
        self._gap(title='c1 gap', pillar='aiqif_c1')
        self._gap(title='no pillar', pillar='')
        self._auth(self.iqac)
        for kind, c4, c1 in (('facts', 3, 1), ('gaps', 1, 1)):
            url = f'/api/v1/sprints/{self.sprint.id}/{kind}'
            self.assertEqual(self.client.get(url, {'pillar': 'aiqif_c4'}).data['count'], c4, kind)
            self.assertEqual(self.client.get(url, {'pillar': 'aiqif_c1'}).data['count'], c1, kind)
            pillars = self.client.get(f'{url}/facets').data['pillars']
            # All nine AI-QIF criteria in framework order, an unused one as 0; blank pillars are not an option.
            self.assertEqual([p['code'] for p in pillars], [f'AIQIF-C{n}' for n in range(1, 10)], kind)
            counts = {p['value']: p['count'] for p in pillars}
            self.assertEqual((counts['aiqif_c4'], counts['aiqif_c1'], counts['aiqif_c9']), (c4, c1, 0), kind)
            self.assertEqual(pillars[0]['label'], 'Institutional AI Strategy & Governance')

    def test_aiqif_category_filter_by_indicator_and_its_options(self):
        from .models import FactAIQIFMapping
        tag = lambda fact, criterion, code: FactAIQIFMapping.objects.create(
            fact=fact, criterion=criterion, indicator_code=code, reason='x', confidence=0.9, status='mapped')
        both = self._make_fact(field_key='both')
        tag(both, 'aiqif_c4', 'AIQIF-C4.1')
        tag(both, 'aiqif_c4', 'AIQIF-C4.2')
        tag(self._make_fact(field_key='other'), 'aiqif_c4', 'AIQIF-C4.1')
        self._make_fact(field_key='untagged')
        self._auth(self.iqac)
        url = f'/api/v1/sprints/{self.sprint.id}/facts'
        self.assertEqual(self.client.get(url, {'aiqif_indicator': 'AIQIF-C4.1'}).data['count'], 2)
        self.assertEqual(self.client.get(url, {'aiqif_indicator': 'AIQIF-C4.2'}).data['count'], 1)
        self.assertEqual(self.client.get(url, {'aiqif_indicator': 'AIQIF-C9.1'}).data['count'], 0)
        options = self.client.get(f'{url}/facets').data['aiqif_indicators']
        self.assertEqual(len(options), 36)
        self.assertEqual(options[0]['code'], 'AIQIF-C1.1')
        counts = {o['value']: o['count'] for o in options}
        self.assertEqual((counts['AIQIF-C4.1'], counts['AIQIF-C4.2'], counts['AIQIF-C9.1']), (2, 1, 0))

    def test_pages_never_leak_another_sprint_or_institution(self):
        other_sprint = Sprint.objects.create(institution=self.institution, mode=Sprint.SprintMode.QUICK_CRI)
        foreign_sprint = Sprint.objects.create(institution=self.other_institution, mode=Sprint.SprintMode.QUICK_CRI)
        for i in range(55):
            self._make_fact(field_key=f'mine{i}')
            self._make_fact(sprint=other_sprint, field_key=f'other{i}')
            self._gap(title=f'mine {i}')
            self._gap(sprint=other_sprint, title=f'other {i}')
        self._auth(self.iqac)
        for kind, prefix in (('facts', 'field_key'), ('gaps', 'title')):
            url = f'/api/v1/sprints/{self.sprint.id}/{kind}'
            rows = self.client.get(url).data['results'] + self.client.get(url, {'page': 2}).data['results']
            self.assertEqual(len(rows), 55)
            self.assertTrue(all(str(r[prefix]).startswith('mine') for r in rows))
            self.assertEqual(self.client.get(f'{url}/facets').data['total'], 55)
        self._auth(self.outsider)  # another institution
        for path in ('facts', 'facts/facets', 'gaps', 'gaps/facets'):
            self.assertEqual(self.client.get(f'/api/v1/sprints/{self.sprint.id}/{path}').status_code,
                             status.HTTP_403_FORBIDDEN, path)
        self._auth(self.iqac)  # a sprint of another institution
        self.assertEqual(self.client.get(f'/api/v1/sprints/{foreign_sprint.id}/facts').status_code,
                         status.HTTP_403_FORBIDDEN)

    def _queries(self, url):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return len(ctx.captured_queries)

    def _add_rows(self, n, start):
        """Facts whose documents are evidence for gaps, with tags and an open evidence request, plus gaps."""
        from .models import FactAIQIFMapping
        for i in range(start, start + n):
            doc = self._doc(f'd{i}.pdf')
            fact = self._make_fact(field_key=f'k{i}', document=doc, source_document=doc, fact_kind='ai_evidence',
                                   assigned_to=self.hod)
            FactAIQIFMapping.objects.create(fact=fact, criterion='aiqif_c4', indicator_code='AIQIF-C4.1',
                                            reason='x', confidence=0.9, status='mapped')
            gap = self._gap(title=f'g{i}', source_fact=fact, gap_type=GapItem.GapType.LOW_CONFIDENCE)
            gap.evidence_documents.add(doc)
            EvidenceRequest.objects.create(sprint=self.sprint, fact=fact, requested_by=self.iqac, description='x',
                                           fact_status_before='extracted')

    def test_facts_and_gaps_queries_do_not_grow_with_the_rows(self):
        self._auth(self.iqac)  # a college user: per-row ownership checks included
        for kind in ('facts', 'gaps'):
            url = f'/api/v1/sprints/{self.sprint.id}/{kind}'
            GapItem.objects.all().delete()
            ExtractedFact.objects.all().delete()
            self._add_rows(3, 0)
            few = self._queries(url)
            self._add_rows(12, 100)
            many = self._queries(url)
            self.assertEqual(many, few, f'{kind}: {few} queries for 3 rows but {many} for 15')


class AIQIFTagLifecycleTests(FactTestBase):
    """Reviewed AI-QIF tags stay visible after leaving the expert queue; a Super Admin can edit them (a new
    indicator never inherits the old approval) and reopen them (the earlier decision stays in history); the fact
    is never changed; coverage follows; the Raw CRI does not."""

    def setUp(self):
        super().setUp()
        from .models import FactAIQIFMapping
        self.M = FactAIQIFMapping
        self.expert = self._make_user('expert@ingage.test', User.Role.SUPER_ADMIN, None)
        self.consultant = self._make_user('sales@ingage.test', User.Role.CONSULTANT, None)
        patcher = patch('apps.facts.aiqif_tagging.crosswalk_rows', return_value=TEST_CROSSWALK)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.fact = self._make_fact(field_key='ai_fdp', fact_kind='ai_evidence', status='confirmed', value=120)
        self.tag = self.M.objects.create(fact=self.fact, criterion='aiqif_c4', indicator_code='AIQIF-C4.1',
                                         reason='AI.', confidence=0.5, status='needs_review')
        self.base = f'/api/v1/facts/{self.fact.id}/aiqif-mappings/AIQIF-C4.1'

    def _post(self, url, body=None, user=None):
        self._auth(user or self.expert)
        return self.client.post(url, body or {}, format='json')

    def _queue(self):
        from .aiqif_tagging import queue_counts
        return queue_counts(self.sprint)['tags']

    def _coverage(self):
        run = self.sprint.scoring_runs.order_by('-created_at').first()
        return run.evidence_coverage['covered_count'], run.overall_cri

    def _fact_state(self):
        self.fact.refresh_from_db()
        return self.fact.value, self.fact.status, self.fact.fact_kind

    def test_a_reviewed_tag_leaves_the_queue_but_stays_findable_with_its_decision(self):
        self.assertEqual(self._queue(), 1)
        r = self._post(f'{self.base}/review', {'decision': 'confirm', 'note': 'Checked.'})
        self.assertEqual(r.status_code, status.HTTP_200_OK, r.data)
        self.assertEqual(self._queue(), 0)
        self._auth(self.expert)
        listed = self.client.get(f'/api/v1/sprints/{self.sprint.id}/facts', {'tag_review': 'confirmed'}).data
        self.assertEqual(listed['count'], 1)
        reviewed = self.client.get(f'/api/v1/sprints/{self.sprint.id}/facts', {'tag_review': 'reviewed'}).data
        self.assertEqual(reviewed['count'], 1)  # what the expert queue's "Reviewed" tab lists
        tag = listed['results'][0]['aiqif_mappings'][0]
        self.assertEqual((tag['review_status'], tag['reviewed_by_name'], tag['relationship'], tag['counts'],
                          tag['counts_reason'], tag['pending']),
                         ('confirmed', self.expert.get_full_name(), 'supporting', True, 'counts toward coverage', False))
        self.assertIsNotNone(tag['reviewed_at'])
        facets = self.client.get(f'/api/v1/sprints/{self.sprint.id}/facts/facets').data
        self.assertEqual(facets['tag_review'], {'confirmed': 1, 'rejected': 0, 'pending': 0})
        self.assertEqual(len(facets['indicators']), 36)

    def test_reopening_keeps_the_earlier_decision_and_returns_the_tag_to_the_queue(self):
        self._post(f'{self.base}/review', {'decision': 'confirm', 'note': 'Checked.'})
        covered_before, raw_before = self._coverage()
        self.assertEqual(covered_before, 1)
        state = self._fact_state()
        self.assertEqual(self._post(f'{self.base}/reopen', {}).status_code, status.HTTP_400_BAD_REQUEST)  # needs a reason
        r = self._post(f'{self.base}/reopen', {'reason': 'The FDP was not AI-specific.'})
        self.assertEqual(r.status_code, status.HTTP_200_OK, r.data)
        tag = r.data['aiqif_mappings'][0]
        self.assertEqual((tag['review_status'], tag['pending'], tag['counts'], tag['pending_reason']),
                         ('unreviewed', True, False, 'The FDP was not AI-specific.'))
        self.assertEqual(self._queue(), 1)  # back in this sprint's queue
        reopened = FactReviewHistory.objects.get(fact=self.fact, action='aiqif_tag_reopened')
        self.assertEqual((reopened.new_value['previous']['decision'], reopened.new_value['previous']['reviewer'],
                          reopened.new_value['previous']['note']), ('confirmed', str(self.expert.id), 'Checked.'))
        self.assertIsNotNone(reopened.new_value['previous']['reviewed_at'])
        self.assertTrue(FactReviewHistory.objects.filter(fact=self.fact, action='aiqif_tag_reviewed').exists())
        covered_after, raw_after = self._coverage()
        self.assertEqual((covered_after, raw_after), (0, raw_before))  # coverage follows; the Raw CRI does not
        self.assertEqual(self._fact_state(), state)  # the fact is untouched
        self.assertEqual(self._post(f'{self.base}/reopen', {'reason': 'again'}).status_code,
                         status.HTTP_400_BAD_REQUEST)  # already pending
        # Re-extraction never drops a reopened tag.
        from .aiqif_tagging import apply_tags
        apply_tags(self.fact, [])
        self.assertTrue(self.M.objects.filter(fact=self.fact, indicator_code='AIQIF-C4.1', pending_since__isnull=False).exists())

    def test_editing_the_indicator_never_carries_the_approval_over(self):
        self._post(f'{self.base}/review', {'decision': 'confirm'})
        state = self._fact_state()
        r = self._post(f'{self.base}/edit', {'indicator_code': 'C4.2', 'note': 'It is AI pedagogy training.'})
        self.assertEqual(r.status_code, status.HTTP_200_OK, r.data)
        tag = r.data['aiqif_mappings'][0]
        self.assertEqual((tag['indicator_code'], tag['review_status'], tag['source'], tag['pending'], tag['counts']),
                         ('AIQIF-C4.2', 'unreviewed', 'expert', True, False))
        self.assertEqual(self._queue(), 1)
        self.assertEqual(self._coverage()[0], 0)
        edited = FactReviewHistory.objects.get(fact=self.fact, action='aiqif_tag_edited')
        self.assertEqual((edited.new_value['previous']['indicator_code'], edited.new_value['previous']['decision'],
                          edited.new_value['indicator_code'], edited.new_value['decision_carried_over'], edited.user),
                         ('AIQIF-C4.1', 'confirmed', 'AIQIF-C4.2', False, self.expert))
        self.assertEqual(self._fact_state(), state)
        # An explicit decision on the new mapping.
        r = self._post(f'/api/v1/facts/{self.fact.id}/aiqif-mappings/AIQIF-C4.2/review', {'decision': 'confirm'})
        self.assertEqual((r.data['aiqif_mappings'][0]['counts'], self._queue(), self._coverage()[0]), (True, 0, 1))

    def test_editing_the_relationship_with_a_decision_in_the_same_request(self):
        r = self._post(f'{self.base}/edit', {'relationship': 'direct', 'decision': 'confirm', 'note': 'Direct.'})
        self.assertEqual(r.status_code, status.HTTP_200_OK, r.data)
        tag = r.data['aiqif_mappings'][0]
        self.assertEqual((tag['relationship'], tag['review_status'], tag['pending'], tag['counts']),
                         ('direct', 'confirmed', False, True))
        actions = list(FactReviewHistory.objects.filter(fact=self.fact).order_by('created_at').values_list('action', flat=True))
        self.assertEqual(actions, ['aiqif_tag_edited', 'aiqif_tag_reviewed'])
        r = self._post(f'{self.base}/edit', {'relationship': 'contextual', 'decision': 'confirm'})
        tag = r.data['aiqif_mappings'][0]
        self.assertEqual((tag['counts'], tag['counts_reason']), (False, 'contextual link (never counts)'))

    def test_duplicates_and_invalid_values_are_refused_and_change_nothing(self):
        self.M.objects.create(fact=self.fact, criterion='aiqif_c4', indicator_code='AIQIF-C4.2', reason='x',
                              confidence=0.9, status='mapped')
        for body in ({'indicator_code': 'C4.2'}, {'indicator_code': 'C99.9'}, {'relationship': 'sideways'},
                     {'decision': 'maybe', 'note': 'x'}, {}):
            r = self._post(f'{self.base}/edit', body)
            self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST, body)
        self.tag.refresh_from_db()
        self.assertEqual((self.tag.indicator_code, self.tag.relationship, self.tag.review_status),
                         ('AIQIF-C4.1', 'supporting', 'unreviewed'))
        self.assertFalse(FactReviewHistory.objects.filter(fact=self.fact).exists())

    def test_only_a_super_admin_may_edit_reopen_or_decide(self):
        outsider_admin = self._make_user('admin@other.edu', User.Role.IQAC_COORDINATOR, self.other_institution)
        for user in (self.iqac, self.consultant, self.outsider, outsider_admin):
            for action, body in (('edit', {'indicator_code': 'C4.2'}), ('reopen', {'reason': 'x'}),
                                 ('review', {'decision': 'confirm'})):
                self.assertEqual(self._post(f'{self.base}/{action}', body, user).status_code,
                                 status.HTTP_403_FORBIDDEN, (user.email, action))
        self.assertEqual(self._post(f'/api/v1/facts/{self.fact.id}/aiqif-mappings/AIQIF-C9.9/reopen',
                                    {'reason': 'x'}).status_code, status.HTTP_404_NOT_FOUND)
        self.tag.refresh_from_db()
        self.assertEqual((self.tag.indicator_code, self.tag.review_status), ('AIQIF-C4.1', 'unreviewed'))


class ConflictChoiceTests(FactTestBase):
    """Gap Dashboard conflict comparison: the owner (or a Super Admin) chooses the correct value -- the chosen fact
    is confirmed, competing values are rejected, the conflict closes (gaps/services.choose_conflict_value)."""

    def setUp(self):
        super().setUp()
        self.expert = self._make_user('expert@ingage.test', User.Role.SUPER_ADMIN, None)
        self.consultant = self._make_user('sales@ingage.test', User.Role.CONSULTANT, None)
        self.admin = self._make_user('admin@test.edu', User.Role.IQAC_COORDINATOR, self.institution)
        docs = [Document.objects.create(sprint=self.sprint, original_filename=n, document_type='naac_ssr',
                                        status=Document.Status.PROCESSED) for n in ('EOA 2026.pdf', 'SSR.pdf', 'AQAR.pdf')]
        self.a = self._make_fact(field_key='ug_ai_ml_intake', value=120, document=docs[0], source_document=docs[0],
                                 source_page='3')
        self.b = self._make_fact(field_key='ug_ai_ml_intake', value=30, document=docs[1], source_document=docs[1])
        self.c = self._make_fact(field_key='ug_ai_ml_intake', value=120, document=docs[2], source_document=docs[2],
                                 status='confirmed')
        # As the end-of-sprint detector records it: one representative fact, no side B.
        self.gap = GapItem.objects.create(sprint=self.sprint, gap_type=GapItem.GapType.CONFLICT,
                                          title='Conflicting values for UG intake', source_fact=self.a,
                                          pillar='aiqif_c4', priority=GapItem.Priority.HIGH)
        self.url = f'/api/v1/gaps/{self.gap.id}/choose-value'

    def _choose(self, user, fact, reason='EOA is the AICTE approval.'):
        self._auth(user)
        return self.client.post(self.url, {'fact_id': str(fact.id), 'reason': reason}, format='json')

    def test_the_detail_lists_every_competing_value_and_who_may_choose(self):
        self._auth(self.hod)
        data = self.client.get(f'/api/v1/gaps/{self.gap.id}').data
        self.assertEqual(sorted(c['current_value'] for c in data['conflict_candidates']), [30, 120, 120])
        self.assertEqual({c['document_name'] for c in data['conflict_candidates']}, {'EOA 2026.pdf', 'SSR.pdf', 'AQAR.pdf'})
        self.assertTrue(data['can_choose_value'])
        self._auth(self.iqac)
        self.assertTrue(self.client.get(f'/api/v1/gaps/{self.gap.id}').data['can_choose_value'])

    def test_the_owner_chooses_a_value_the_rest_follows_and_the_conflict_closes(self):
        from apps.gaps.models import GapEvent
        r = self._choose(self.hod, self.a)
        self.assertEqual(r.status_code, status.HTTP_200_OK, r.data)
        for f in (self.a, self.b, self.c):
            f.refresh_from_db()
        self.assertEqual((self.a.status, self.b.status, self.c.status), ('confirmed', 'rejected', 'confirmed'))
        self.assertEqual((self.a.reviewed_by, self.b.reviewed_by), (self.hod, self.hod))
        self.gap.refresh_from_db()
        self.assertEqual(self.gap.status, 'resolved')
        self.assertIn("120 from EOA 2026.pdf, page 3 is the correct value", self.gap.resolution)
        self.assertIn('EOA is the AICTE approval.', self.gap.resolution)
        self.assertTrue(GapEvent.objects.filter(gap=self.gap, action='resolved', user=self.hod).exists())
        rejected = FactReviewHistory.objects.get(fact=self.b, action='rejected')
        self.assertEqual((rejected.original_value, rejected.user), (30, self.hod))
        self.assertTrue(FactReviewHistory.objects.filter(fact=self.a, action='confirmed').exists())
        self.assertFalse(FactReviewHistory.objects.filter(fact=self.c).exists())  # same value: untouched
        self.assertTrue(self.sprint.scoring_runs.exists())  # CRI recalculated
        self.assertEqual(self._choose(self.hod, self.a).status_code, status.HTTP_400_BAD_REQUEST)  # already closed

    def test_a_super_admin_may_choose_too(self):
        self.assertEqual(self._choose(self.expert, self.b).status_code, status.HTTP_200_OK)
        for f in (self.a, self.b, self.c):
            f.refresh_from_db()
        self.assertEqual((self.a.status, self.b.status, self.c.status), ('rejected', 'confirmed', 'rejected'))

    def test_another_college_cannot_choose(self):
        for user in (self.viewer, self.outsider):
            self.assertIn(self._choose(user, self.a).status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND), user.email)
        self.a.refresh_from_db()
        self.gap.refresh_from_db()
        self.assertEqual((self.a.status, self.gap.status), ('extracted', 'open'))

    def test_invalid_choices_change_nothing(self):
        other = self._make_fact(field_key='something_else', value=5)
        self.assertEqual(self._choose(self.hod, other).status_code, status.HTTP_400_BAD_REQUEST)
        EvidenceRequest.objects.create(sprint=self.sprint, fact=self.b, requested_by=self.iqac, description='x',
                                       fact_status_before='extracted')
        r = self._choose(self.hod, self.a)
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('open evidence request', str(r.data))
        self.a.refresh_from_db()
        self.assertEqual(self.a.status, 'extracted')


class AIQIFAutoDecisionTests(FactTestBase):
    """Rule 4 (apps/facts/aiqif_tagging.py): earlier expert decisions on the same field decide new tags, and an
    AI second opinion decides what is still waiting -- both reversible, neither ever a person's decision."""

    def setUp(self):
        super().setUp()
        from .models import FactAIQIFMapping
        self.M = FactAIQIFMapping
        self.expert = self._make_user('expert@ingage.test', User.Role.SUPER_ADMIN, None)
        # The precedent: last year's sprint, where the expert decided this field's tags.
        old_sprint = Sprint.objects.create(institution=self.institution, mode=Sprint.SprintMode.VERIFIED_CRI)
        old = self._make_fact(sprint=old_sprint, field_key='ai_coe_count_2023_24', fact_kind='ai_evidence',
                              status='confirmed')
        now = __import__('django.utils.timezone', fromlist=['now']).now()
        self.M.objects.create(fact=old, criterion='aiqif_c7', indicator_code='AIQIF-C7.2', reason='x', confidence=0.6,
                              status='needs_review', review_status='confirmed', reviewed_by=self.expert,
                              reviewed_at=now, relationship='direct')
        self.M.objects.create(fact=old, criterion='aiqif_c9', indicator_code='AIQIF-C9.1', reason='x', confidence=0.9,
                              status='mapped', review_status='rejected', reviewed_by=self.expert, reviewed_at=now)
        self.M.objects.create(fact=old, criterion='aiqif_c4', indicator_code='AIQIF-C4.3', reason='x', confidence=0.9,
                              status='mapped', review_status='confirmed', reviewed_by=self._auto_user(), reviewed_at=now)
        self.fact = self._make_fact(field_key='ai_coe_count_2025_26', fact_kind='ai_evidence', pillar='aiqif_c7')

    @staticmethod
    def _auto_user():
        from .auto_confirm import system_user
        return system_user()

    def _tag(self, code, confidence=0.5, **fields):
        from apps.scoring.constants import AIQIF_INDICATORS
        return self.M.objects.create(fact=self.fact, criterion=AIQIF_INDICATORS[code][0], indicator_code=code,
                                     reason='AI.', confidence=confidence, status='needs_review', **fields)

    def _tags(self):
        return {m.indicator_code: m for m in self.M.objects.filter(fact=self.fact)}

    def test_the_precedent_key_ignores_years_and_numbers(self):
        from .aiqif_tagging import precedent_key
        self.assertEqual(precedent_key('ai_coe_count_2023_24'), precedent_key('AI_COE_COUNT_2025-26'))
        self.assertEqual(precedent_key('mba_approved_intake_2024_25_course_2'), 'mba_approved_intake_course')
        self.assertNotEqual(precedent_key('ai_coe_count'), precedent_key('ai_lab_count'))

    def test_earlier_expert_decisions_decide_the_same_field_in_a_new_sprint(self):
        from .aiqif_tagging import Precedents, apply_precedents, queue_counts
        self._tag('AIQIF-C7.2')               # low confidence: would wait -- the expert confirmed it before
        self._tag('AIQIF-C9.1', 0.9)          # the expert rejected it before
        self._tag('AIQIF-C4.3', 0.4)          # only an automatic decision exists: not a precedent
        self.assertEqual(apply_precedents(self.fact, Precedents()), 2)
        tags = self._tags()
        self.assertEqual((tags['AIQIF-C7.2'].auto_accepted, tags['AIQIF-C7.2'].auto_decision,
                          tags['AIQIF-C7.2'].relationship, tags['AIQIF-C7.2'].review_status),
                         (True, 'accepted_precedent', 'direct', 'unreviewed'))
        self.assertIn('ai_coe_count_2023_24', tags['AIQIF-C7.2'].auto_reason)
        self.assertEqual((tags['AIQIF-C9.1'].auto_accepted, tags['AIQIF-C9.1'].auto_decision),
                         (False, 'rejected_precedent'))
        self.assertEqual(tags['AIQIF-C4.3'].auto_decision, '')
        self.assertEqual(queue_counts(self.sprint)['tags'], 1)  # only C4.3 still waits

    def test_a_confirmed_precedent_adds_an_indicator_the_ai_did_not_suggest(self):
        from .aiqif_tagging import Precedents, apply_precedents
        apply_precedents(self.fact, Precedents())
        added = self._tags()['AIQIF-C7.2']
        self.assertEqual((added.source, added.auto_accepted, added.relationship), ('precedent', True, 'direct'))
        self.assertNotIn('AIQIF-C9.1', self._tags())  # a rejected precedent never adds a tag

    def test_a_persons_decision_and_a_reopened_tag_are_never_overridden(self):
        from .aiqif_tagging import Precedents, apply_precedents
        mine = self._tag('AIQIF-C9.1', 0.9, review_status='confirmed', reviewed_by=self.expert)
        pending = self._tag('AIQIF-C7.2', pending_since=__import__('django.utils.timezone', fromlist=['now']).now())
        apply_precedents(self.fact, Precedents())
        mine.refresh_from_db()
        pending.refresh_from_db()
        self.assertEqual((mine.review_status, mine.auto_decision), ('confirmed', ''))
        self.assertEqual((pending.auto_accepted, pending.auto_decision), (False, ''))

    def _service(self, *answers):
        service = MagicMock()
        service.extract_structured_data.side_effect = list(answers)
        return service

    def test_the_ai_second_opinion_accepts_only_a_confident_agreeing_check(self):
        from .aiqif_tagging import ai_check_pending, queue_counts
        ok = self._tag('AIQIF-C7.1')
        doubtful = self._tag('AIQIF-C7.3')
        contextual = self._tag('AIQIF-C7.4')
        service = self._service(
            {'supports': True, 'relationship': 'direct', 'confidence': 0.92, 'reason': 'The quote names the AI CoE.'},
            {'supports': True, 'relationship': 'supporting', 'confidence': 0.55, 'reason': 'Unclear.'},
            {'supports': True, 'relationship': 'contextual', 'confidence': 0.95, 'reason': 'Background only.'})
        with override_settings(AIQIF_AI_CHECK_MIN_CONFIDENCE=0.8):
            result = ai_check_pending([self.fact], service=service)
        self.assertEqual(result, {'checked': 3, 'accepted': 1})
        for m in (ok, doubtful, contextual):
            m.refresh_from_db()
        self.assertEqual((ok.auto_accepted, ok.auto_decision, ok.relationship), (True, 'accepted_ai_check', 'direct'))
        self.assertIn('AI check agreed (92%)', ok.auto_reason)
        self.assertEqual((doubtful.auto_accepted, contextual.auto_accepted), (False, False))
        self.assertIn('AI check disagreed', doubtful.auto_reason)
        self.assertEqual(queue_counts(self.sprint)['tags'], 2)  # the two left for the expert, with the reason
        # Checked once: a second run asks the AI nothing.
        self.assertEqual(ai_check_pending([self.fact], service=self._service())['checked'], 0)

    def test_a_failed_check_leaves_the_tag_waiting(self):
        from apps.extraction.exceptions import PermanentExtractionError, RecoverableExtractionError

        from .aiqif_tagging import ai_check_pending
        a, b = self._tag('AIQIF-C7.1'), self._tag('AIQIF-C7.3')
        result = ai_check_pending([self.fact], service=self._service(PermanentExtractionError('bad json'),
                                                                    RecoverableExtractionError('rate limited')))
        self.assertEqual(result, {'checked': 0, 'accepted': 0})
        for m in (a, b):
            m.refresh_from_db()
            self.assertEqual((m.auto_accepted, m.auto_reason), (False, ''))

    def test_reopening_an_automatic_decision_sends_it_back_to_the_expert(self):
        from .aiqif_tagging import Precedents, apply_precedents, queue_counts, reopen_tag
        tag = self._tag('AIQIF-C7.2')
        apply_precedents(self.fact, Precedents())
        reopen_tag(self.M.objects.get(pk=tag.pk), self.expert, 'Not an AI CoE this year.')
        tag.refresh_from_db()
        self.assertEqual((tag.auto_accepted, tag.auto_decision, tag.auto_reason), (False, '', ''))
        self.assertEqual(queue_counts(self.sprint)['tags'], 1)
        reopened = FactReviewHistory.objects.get(fact=self.fact, action='aiqif_tag_reopened')
        self.assertEqual(reopened.new_value['previous']['auto_decision'], 'accepted_precedent')

    def test_decide_automatically_from_the_expert_queue(self):
        self._tag('AIQIF-C7.2')
        url = f'/api/v1/sprints/{self.sprint.id}/aiqif-expert-queue/auto-check'
        self._auth(self.iqac)
        self.assertEqual(self.client.post(url).status_code, status.HTTP_403_FORBIDDEN)
        self._auth(self.expert)
        r = self.client.post(url)
        self.assertEqual(r.status_code, status.HTTP_200_OK, r.data)
        self.assertEqual((r.data['precedent_decisions'], r.data['ai_check'], r.data['expert_queue']['tags']),
                         (1, 'off', 0))  # the AI check is off in tests
        listed = self.client.get(f'/api/v1/sprints/{self.sprint.id}/facts').data['results']
        tag = next(f for f in listed if f['id'] == str(self.fact.id))['aiqif_mappings'][0]
        self.assertEqual((tag['auto_decision'], tag['pending']), ('accepted_precedent', False))
        self.assertTrue(tag['auto_reason'])
        # Listed in the Reviewed tab, where it can be reversed.
        reviewed = self.client.get(f'/api/v1/sprints/{self.sprint.id}/facts', {'tag_review': 'reviewed'}).data
        self.assertEqual([f['id'] for f in reviewed['results']], [str(self.fact.id)])


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix='evidence-retry-tests-'))
class EvidenceAssessmentRetryTests(FactTestBase):
    """A reviewer retries a failed AI assessment of the same submission: no re-upload, no OCR or extraction, one run
    per click, advisory result only (evidence_requests.request_assessment_retry, tasks.retry_evidence_assessment)."""

    def setUp(self):
        super().setUp()
        self.registrar = self._make_user('registrar@test.edu', User.Role.IQAC_COORDINATOR, self.institution)
        self.admin = self._make_user('admin@test.edu', User.Role.IQAC_COORDINATOR, self.institution)  # reviews
        self.fact = self._make_fact()

    _request = EvidenceRequestWorkflowTests._request
    _open = EvidenceRequestWorkflowTests._open
    _url = EvidenceRequestWorkflowTests._url
    _upload = EvidenceRequestWorkflowTests._upload
    _submit_text = EvidenceRequestWorkflowTests._submit_text
    _link = EvidenceRequestWorkflowTests._link

    GOOD = {'outcome': 'supports', 'summary': 'The text supports the reported completion rate.',
            'quote': '120 of 192 faculty completed AI foundation FDP.', 'page_number': None,
            'suggested_corrected_value': None, 'confidence': 0.93}

    def _ai(self, *, fail=None, result=None):
        get = patch('apps.facts.evidence_analysis.get_ai_service')
        mock = get.start()
        self.addCleanup(get.stop)
        if fail is not None:
            mock.return_value.extract_structured_data.side_effect = fail
        else:
            mock.return_value.extract_structured_data.side_effect = None
            mock.return_value.extract_structured_data.return_value = result or self.GOOD
        return mock

    def _failed_text_submission(self, error=TimeoutError('Request timed out.')):
        from .evidence_analysis import analyze_submission
        req = self._open()
        self._submit_text(req)
        link = self._link(req)
        self._ai(fail=error)
        analyze_submission(link)
        link.refresh_from_db()
        self.assertEqual(link.analysis_status, 'failed')
        return req, link

    def _retry(self, req, link, user=None, run=True):
        """POST the retry; with run=True the queued task runs right after the commit (as a worker would)."""
        self._auth(user or self.admin)
        url = self._url(req, f'evidence/{link.id}/retry-assessment')
        if not run:
            with patch('apps.facts.tasks.retry_evidence_assessment.delay') as delay:
                with self.captureOnCommitCallbacks(execute=True):
                    response = self.client.post(url, format='json')
            return response, delay
        from .tasks import retry_evidence_assessment
        with patch('apps.facts.tasks.retry_evidence_assessment.delay', side_effect=retry_evidence_assessment):
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(url, format='json')
        return response, None

    def test_a_timeout_then_a_successful_retry_stays_advisory(self):
        from apps.gaps.models import GapItem
        gap = GapItem.objects.create(sprint=self.sprint, source_fact=self.fact, gap_type=GapItem.GapType.LOW_CONFIDENCE,
                                     title='Low confidence', pillar='aiqif_c4')
        req, link = self._failed_text_submission()
        self.assertIn('timed out', link.analysis_error)
        self.assertIn('Retry the assessment', link.analysis_error)

        self._ai(result=self.GOOD)  # the service has recovered
        response, _ = self._retry(req, link)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        link.refresh_from_db()
        req.refresh_from_db()
        self.assertEqual((link.analysis_status, link.analysis_outcome, link.analysis_error), ('ready', 'supports', ''))
        self.assertEqual((link.analysis_attempts, link.analysis_retry_count), (2, 1))
        self.assertIsNotNone(link.analysis_finished_at)
        self.assertEqual(req.status, EvidenceRequest.Status.READY_FOR_REVIEW)
        evidence = response.data['evidence'][0]  # answered before the queued run starts: "retry in progress"
        self.assertEqual((evidence['analysis_status'], evidence['analysis_retry_count']), ('pending', 1))
        # Advisory only: the fact, its review history and its gap are exactly as before.
        self.fact.refresh_from_db()
        gap.refresh_from_db()
        self.assertEqual((self.fact.status, self.fact.value), (ExtractedFact.Status.EVIDENCE_REQUESTED, 62.5))
        self.assertFalse(FactReviewHistory.objects.filter(fact=self.fact, action__in=['confirmed', 'corrected']).exists())
        self.assertEqual(gap.status, GapItem.Status.OPEN)
        self.assertEqual(req.evidence.count(), 1)  # the same submission, nothing re-submitted
        self.assertEqual(list(req.events.values_list('action', flat=True))[-5:],
                         ['analysis_started', 'analysis_failed', 'analysis_retry', 'analysis_started',
                          'analysis_completed'])

    def test_a_document_retry_reuses_the_saved_pages_without_ocr_or_extraction(self):
        from apps.documents.models import Document
        from apps.extraction.models import ExtractionJob

        from .evidence_analysis import analyze_pending_document_submissions
        req = self._open()
        self._upload(req)
        link = self._link(req)
        pages = {'format_supported': True, 'pages': [
            {'page_number': 3, 'text': '120 of 192 faculty completed AI foundation FDP.', 'source': 'ocr'}]}
        self._ai(fail=TimeoutError('Request timed out.'))
        analyze_pending_document_submissions(link.document, pages)
        link.refresh_from_db()
        self.assertEqual(link.analysis_status, 'failed')
        self.assertEqual(link.source_pages, [{'page_number': 3, 'text': '120 of 192 faculty completed AI foundation FDP.'}])
        documents, jobs = Document.objects.count(), ExtractionJob.objects.count()

        self._ai(result={**self.GOOD, 'page_number': 3})
        with patch('apps.extraction.services.pdf_reader.PDFPageReader.read_pages',
                   side_effect=AssertionError('the document must not be read again')), \
                patch('apps.extraction.views.dispatch_job', side_effect=AssertionError('no extraction on retry')):
            response, _ = self._retry(req, link)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        link.refresh_from_db()
        self.assertEqual((link.analysis_status, link.analysis_page_number), ('ready', 3))
        self.assertEqual((Document.objects.count(), ExtractionJob.objects.count(), req.evidence.count()),
                         (documents, jobs, 1))

    def test_repeated_clicks_queue_one_retry(self):
        req, link = self._failed_text_submission()
        first, delay = self._retry(req, link, run=False)
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(delay.call_count, 1)
        self.assertEqual(first.data['evidence'][0]['analysis_status'], 'pending')  # "retry in progress"
        second, delay2 = self._retry(req, link, run=False)
        self.assertEqual(second.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(second.data['code'], 'retry_in_progress')
        self.assertEqual(delay2.call_count, 0)
        link.refresh_from_db()
        self.assertEqual(link.analysis_retry_count, 1)
        self.assertEqual(req.events.filter(action='analysis_retry').count(), 1)
        # A repeated delivery of the same task after it ran does nothing.
        from .tasks import retry_evidence_assessment
        self._ai(result=self.GOOD)
        retry_evidence_assessment(str(link.id))
        retry_evidence_assessment(str(link.id))
        link.refresh_from_db()
        self.assertEqual((link.analysis_status, link.analysis_attempts), ('ready', 2))
        self.assertEqual(req.events.filter(action='analysis_completed').count(), 1)

    def test_a_retry_that_fails_again_can_be_retried_once_the_service_recovers(self):
        req, link = self._failed_text_submission()
        self._ai(fail=RuntimeError('Rate limit reached (429). Bearer sk-abcdef1234567890 rejected'))
        response, _ = self._retry(req, link)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        link.refresh_from_db()
        self.assertEqual((link.analysis_status, link.analysis_retry_count), ('failed', 1))
        self.assertIn('temporarily unavailable', link.analysis_error)
        self.assertNotIn('sk-abcdef', link.analysis_error)  # no secrets in the stored error or the audit trail
        self.assertFalse(any('sk-abcdef' in (e.note or '') for e in req.events.all()))
        self._ai(result=self.GOOD)
        response, _ = self._retry(req, link)
        link.refresh_from_db()
        self.assertEqual((link.analysis_status, link.analysis_retry_count, link.analysis_attempts), ('ready', 2, 3))

    def test_only_a_reviewer_of_the_fact_who_did_not_submit_it_may_retry(self):
        req, link = self._failed_text_submission()
        response, delay = self._retry(req, link, user=self.hod, run=False)  # the submitter
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Someone other than the person who submitted', str(response.data['detail']))
        response, _ = self._retry(req, link, user=self.viewer, run=False)
        self.assertIn(response.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND))
        response, _ = self._retry(req, link, user=self.registrar, run=False)  # not the fact's reviewer
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response, _ = self._retry(req, link, user=self.outsider, run=False)  # another college
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        link.refresh_from_db()
        self.assertEqual((link.analysis_status, link.analysis_retry_count), ('failed', 0))
        self.assertFalse(req.events.filter(action='analysis_retry').exists())

    def test_only_a_failed_assessment_of_an_unreviewed_submission_is_retried(self):
        req, link = self._failed_text_submission()
        self._ai(result=self.GOOD)
        self._retry(req, link)
        response, delay = self._retry(req, link, run=False)  # now ready: nothing to retry
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(delay.call_count, 0)

    def test_a_run_lost_mid_way_can_be_retried_after_a_while(self):
        from django.utils import timezone

        from .evidence_requests import STALE_ASSESSMENT_MINUTES
        req, link = self._failed_text_submission()
        EvidenceRequestDocument.objects.filter(pk=link.pk).update(
            analysis_status='processing', analysis_started_at=timezone.now() - timedelta(minutes=5))
        response, _ = self._retry(req, link, run=False)
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)  # still running
        EvidenceRequestDocument.objects.filter(pk=link.pk).update(
            analysis_started_at=timezone.now() - timedelta(minutes=STALE_ASSESSMENT_MINUTES + 1))
        response, delay = self._retry(req, link, run=False)
        self.assertEqual((response.status_code, delay.call_count), (status.HTTP_200_OK, 1))


class PostgreSQLRowLockTests(FactTestBase):
    """Row locks must be valid on PostgreSQL (production): FOR UPDATE may not reach the nullable side of an outer
    join. SQLite (local, CI) ignores FOR UPDATE, so the locking queries are checked for FOR UPDATE OF (the row itself) here."""

    def _locking_queries(self, run):
        """Run `run()` and return each row-locking query it fetched with .get()."""
        from django.db.models.query import QuerySet
        captured, real_get = [], QuerySet.get

        def spy(qs, *args, **kwargs):
            captured.append(qs.query)
            return real_get(qs, *args, **kwargs)

        with patch.object(QuerySet, 'get', spy):
            run()
        return [q for q in captured if q.select_for_update]

    def test_tag_lock_only_locks_the_tag_row(self):
        from .aiqif_tagging import _lock
        from .models import FactAIQIFMapping
        mapping = FactAIQIFMapping.objects.create(fact=self._make_fact(), criterion='aiqif_c4',
                                                  indicator_code='AIQIF-C4.1', reason='x', confidence=0.9,
                                                  status=FactAIQIFMapping.Status.MAPPED)
        queries = self._locking_queries(lambda: _lock(mapping))  # reviewed_by (nullable) is joined
        self.assertEqual(len(queries), 1)
        self.assertIn('reviewed_by', queries[0].select_related)
        self.assertEqual(queries[0].select_for_update_of, ('self',))  # FOR UPDATE OF the tag row only

    def test_evidence_assessment_lock_only_locks_the_submission_row(self):
        from .evidence_analysis import analyze_submission
        req = EvidenceRequest.objects.create(sprint=self.sprint, fact=self._make_fact(), description='Proof',
                                             fact_status_before='extracted')
        link = EvidenceRequestDocument.objects.create(request=req, submitted_text='120 of 192.', source_context='HR')
        with patch('apps.facts.evidence_analysis.get_ai_service') as ai:
            ai.return_value.extract_structured_data.side_effect = TimeoutError('timed out')
            queries = self._locking_queries(lambda: analyze_submission(link))
        joined = [q for q in queries if isinstance(q.select_related, dict) and 'document' in q.select_related]
        self.assertTrue(joined)  # the query that joins the nullable document
        for q in joined:
            self.assertEqual(q.select_for_update_of, ('self',))


class ProfileProgrammeNamesTests(FactTestBase):
    """A programme fact whose value is a list (or list-looking text) becomes one programme per name."""

    def test_list_values_are_split(self):
        from .profile_suggestion import programme_names
        self.assertEqual(programme_names("['Computer Science & Engineering', 'MBA (Logistics)']"),
                         ['Computer Science & Engineering', 'MBA (Logistics)'])
        self.assertEqual(programme_names('["BCA", "MCA", "BCA"]'), ['BCA', 'MCA'])
        self.assertEqual(programme_names(['B.Tech IT', '  MBA ']), ['B.Tech IT', 'MBA'])
        self.assertEqual(programme_names('Master of Computer Applications'), ['Master of Computer Applications'])
        self.assertEqual(programme_names('[not a list'), ['[not a list'])
