from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.institutions.models import Institution
from apps.sprints.models import Sprint

from .models import ExtractedFact, FactReviewHistory

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
            'pillar': 'faculty_ai_capability',
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
        self._make_fact(pillar='faculty_ai_capability')
        self._make_fact(field_key='f2', pillar='governance_strategy')
        self._auth(self.iqac)
        response = self.client.get(f'/api/v1/sprints/{self.sprint.id}/facts/', {'pillar': 'governance_strategy'})
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['pillar'], 'governance_strategy')

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
        response = self.client.post(f'/api/v1/facts/{fact.id}/request-evidence', {})
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
