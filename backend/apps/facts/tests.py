import tempfile
from datetime import date, timedelta
from unittest.mock import patch

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
        self.hod = self._make_user('hod@test.edu', User.Role.HOD, self.institution)
        self.viewer = self._make_user('viewer@test.edu', User.Role.VIEWER, self.institution)
        self.outsider = self._make_user('outsider@test.edu', User.Role.HOD, self.other_institution)

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
        self.assertEqual(len(response.data), 1)

    def test_list_without_trailing_slash_matches_frontend_client(self):
        self._make_fact()
        self._auth(self.iqac)
        response = self.client.get(f'/api/v1/sprints/{self.sprint.id}/facts')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.data, list)

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

    def test_pagination_is_opt_in(self):
        for i in range(3):
            self._make_fact(field_key=f'field_{i}')
        self._auth(self.iqac)

        plain = self.client.get(f'/api/v1/sprints/{self.sprint.id}/facts/')
        self.assertIsInstance(plain.data, list)
        self.assertEqual(len(plain.data), 3)

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
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['pillar'], 'aiqif_c1')

    def test_filter_by_status(self):
        f1 = self._make_fact()
        self._make_fact(field_key='f2')
        f1.status = ExtractedFact.Status.CONFIRMED
        f1.save(update_fields=['status'])

        self._auth(self.iqac)
        response = self.client.get(f'/api/v1/sprints/{self.sprint.id}/facts/', {'status': 'confirmed'})
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['id'], str(f1.id))

    def test_filter_by_owner_role(self):
        self._make_fact(owner_role='HOD')
        self._make_fact(field_key='f2', owner_role='REGISTRAR')
        self._auth(self.iqac)
        response = self.client.get(f'/api/v1/sprints/{self.sprint.id}/facts/', {'owner_role': 'REGISTRAR'})
        self.assertEqual(len(response.data), 1)

    def test_filter_by_document(self):
        from apps.documents.models import Document
        document = Document.objects.create(sprint=self.sprint, document_type='naac_ssr')
        self._make_fact(document=document)
        self._make_fact(field_key='f2')

        self._auth(self.iqac)
        response = self.client.get(f'/api/v1/sprints/{self.sprint.id}/facts/', {'document': str(document.id)})
        self.assertEqual(len(response.data), 1)

    def test_filter_by_confidence_range(self):
        self._make_fact(field_key='low', confidence_score=0.3)
        self._make_fact(field_key='high', confidence_score=0.9)
        self._auth(self.iqac)

        response = self.client.get(f'/api/v1/sprints/{self.sprint.id}/facts/', {'confidence_min': 0.5})
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['field_key'], 'high')

        response = self.client.get(f'/api/v1/sprints/{self.sprint.id}/facts/', {'confidence_max': 0.5})
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['field_key'], 'low')

    def test_ordering_by_confidence_score(self):
        self._make_fact(field_key='low', confidence_score=0.3)
        self._make_fact(field_key='high', confidence_score=0.9)
        self._auth(self.iqac)
        response = self.client.get(f'/api/v1/sprints/{self.sprint.id}/facts/', {'ordering': 'confidence_score'})
        keys = [row['field_key'] for row in response.data]
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
        fact = self._make_fact(value=62.5)
        self._auth(self.hod)
        self.client.post(
            f'/api/v1/facts/{fact.id}/correct/', {'new_value': 70.0, 'reason': 'round 1'}, format='json',
        )
        self.client.post(
            f'/api/v1/facts/{fact.id}/correct/', {'new_value': 75.0, 'reason': 'round 2'}, format='json',
        )

        history = list(FactReviewHistory.objects.filter(fact=fact).order_by('created_at'))
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0].original_value, 62.5)
        self.assertEqual(history[0].new_value, 70.0)
        self.assertEqual(history[1].original_value, 70.0)
        self.assertEqual(history[1].new_value, 75.0)

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
        self.registrar = self._make_user('registrar@test.edu', User.Role.REGISTRAR, self.institution)
        # Decides evidence: the facts are owned by HOD, who also submits it here, so the reviewer is an
        # Institution Admin (apps/facts/ownership.py); the IQAC Coordinator requests and withdraws.
        self.admin = self._make_user('admin@test.edu', User.Role.INSTITUTION_ADMIN, self.institution)
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
        self._auth(self.registrar)  # neither the requester nor an admin / IQAC
        self.assertEqual(self.client.post(self._url(req, 'assign'), {'assigned_to': str(self.hod.id)},
                                          format='json').status_code, status.HTTP_400_BAD_REQUEST)
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
        self.assertEqual(self._upload(req, user=self.viewer).status_code, status.HTTP_403_FORBIDDEN)
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
        self.assertEqual(self.client.post(self._url(req, 'comment'), {'note': 'x'}, format='json').status_code,
                         status.HTTP_403_FORBIDDEN)

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
        self.admin = self._make_user('admin@test.edu', User.Role.INSTITUTION_ADMIN, self.institution)
        self.fact = self._make_fact(confidence_score=0.4, confidence_reason='Blurred table cell.')
        generate_gaps_for_sprint(self.sprint)
        self.gap = GapItem.objects.get(source_fact=self.fact, gap_type=GapItem.GapType.LOW_CONFIDENCE)

    def _gap_row(self, user=None):
        self._auth(user or self.iqac)
        rows = self.client.get(f'/api/v1/sprints/{self.sprint.id}/gaps').data
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
        self.assertEqual(self._review(req, self.viewer, 'accept', evidence_id=str(link.id)).status_code,
                         status.HTTP_403_FORBIDDEN)
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
