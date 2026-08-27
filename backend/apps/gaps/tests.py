from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.documents.models import Document
from apps.facts.models import ExtractedFact
from apps.institutions.models import Institution
from apps.sprints.models import Sprint

from .models import GapItem
from .services import generate_gaps_for_sprint

PASSWORD = 'Str0ng!DevPassw0rd'


class GapTestBase(APITestCase):
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

    def _make_gap(self, **overrides):
        defaults = {
            'sprint': self.sprint,
            'gap_type': GapItem.GapType.MISSING_DOCUMENT,
            'title': 'Missing NAAC SSR',
            'description': 'Required for a verified CRI baseline.',
            'priority': GapItem.Priority.BLOCKING,
        }
        defaults.update(overrides)
        return GapItem.objects.create(**defaults)

    def _make_fact(self, **overrides):
        defaults = {
            'sprint': self.sprint,
            'field_name': 'Faculty Foundation AI Certification %',
            'field_key': 'faculty_foundation_ai_certified_pct',
            'value': 62.5,
            'data_type': ExtractedFact.DataType.PERCENTAGE,
            'pillar': 'faculty_ai_capability',
            'owner_role': 'HOD',
            'source_snippet': '120 out of 192 faculty completed AI foundation FDP.',
            'confidence_score': 0.85,
            'extraction_method': 'ocr_table_extractor',
        }
        defaults.update(overrides)
        return ExtractedFact.objects.create(**defaults)

    def _make_document(self, **overrides):
        defaults = {'sprint': self.sprint, 'document_type': 'naac_ssr', 'owner_role': 'IQAC_COORDINATOR'}
        defaults.update(overrides)
        return Document.objects.create(**defaults)


class GapModelConstraintTests(GapTestBase):
    def test_duplicate_active_gap_for_same_fact_and_type_rejected(self):
        fact = self._make_fact()
        self._make_gap(gap_type=GapItem.GapType.LOW_CONFIDENCE, source_fact=fact, title='Low-confidence: x')
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._make_gap(gap_type=GapItem.GapType.LOW_CONFIDENCE, source_fact=fact, title='Low-confidence: y')

    def test_duplicate_active_gap_for_same_document_and_type_rejected(self):
        document = self._make_document()
        self._make_gap(
            gap_type=GapItem.GapType.STALE_DATA, related_document=document, title='Stale: a', source_fact=None,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._make_gap(
                    gap_type=GapItem.GapType.STALE_DATA, related_document=document, title='Stale: b',
                    source_fact=None,
                )

    def test_duplicate_active_gap_for_same_sprint_type_title_rejected(self):
        self._make_gap(title='Missing NAAC SSR')
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._make_gap(title='Missing NAAC SSR')

    def test_resolved_gap_does_not_block_a_fresh_one_of_same_kind(self):
        first = self._make_gap(title='Missing NAAC SSR')
        first.status = GapItem.Status.RESOLVED
        first.save(update_fields=['status'])
        second = self._make_gap(title='Missing NAAC SSR')
        self.assertNotEqual(first.id, second.id)

    def test_different_titles_are_not_treated_as_duplicates(self):
        self._make_gap(title='Missing NAAC SSR')
        second = self._make_gap(title='Missing AQAR')
        self.assertEqual(GapItem.objects.count(), 2)
        self.assertIsNotNone(second.id)


class GapGenerationServiceTests(GapTestBase):
    def test_missing_document_gaps_created_for_each_required_type_not_uploaded(self):
        created = generate_gaps_for_sprint(self.sprint)
        missing_gaps = [g for g in created if g.gap_type == GapItem.GapType.MISSING_DOCUMENT]
        self.assertTrue(len(missing_gaps) >= 1)
        self.assertTrue(all(g.priority == GapItem.Priority.BLOCKING for g in missing_gaps))

    def test_missing_document_gap_not_created_once_document_uploaded(self):
        self._make_document(document_type='naac_ssr')
        created = generate_gaps_for_sprint(self.sprint)
        titles = [g.title for g in created]
        self.assertNotIn('Missing NAAC SSR', titles)

    def test_generation_is_idempotent_no_duplicates_on_repeat_calls(self):
        generate_gaps_for_sprint(self.sprint)
        count_after_first = GapItem.objects.filter(sprint=self.sprint).count()
        generate_gaps_for_sprint(self.sprint)
        count_after_second = GapItem.objects.filter(sprint=self.sprint).count()
        self.assertEqual(count_after_first, count_after_second)

    def test_low_confidence_fact_creates_low_confidence_gap(self):
        fact = self._make_fact(confidence_score=0.4)
        created = generate_gaps_for_sprint(self.sprint)
        low_conf_gaps = [g for g in created if g.gap_type == GapItem.GapType.LOW_CONFIDENCE]
        self.assertEqual(len(low_conf_gaps), 1)
        self.assertEqual(low_conf_gaps[0].source_fact_id, fact.id)
        # below the "very low" threshold -> high priority, not medium
        self.assertEqual(low_conf_gaps[0].priority, GapItem.Priority.HIGH)

    def test_moderately_low_confidence_fact_is_medium_priority(self):
        self._make_fact(confidence_score=0.6)
        created = generate_gaps_for_sprint(self.sprint)
        low_conf_gaps = [g for g in created if g.gap_type == GapItem.GapType.LOW_CONFIDENCE]
        self.assertEqual(len(low_conf_gaps), 1)
        self.assertEqual(low_conf_gaps[0].priority, GapItem.Priority.MEDIUM)

    def test_high_confidence_fact_does_not_get_low_confidence_gap(self):
        self._make_fact(confidence_score=0.95)
        created = generate_gaps_for_sprint(self.sprint)
        low_conf_gaps = [g for g in created if g.gap_type == GapItem.GapType.LOW_CONFIDENCE]
        self.assertEqual(len(low_conf_gaps), 0)

    def test_extracted_but_high_confidence_fact_gets_unconfirmed_gap(self):
        fact = self._make_fact(confidence_score=0.95)
        created = generate_gaps_for_sprint(self.sprint)
        unconfirmed = [g for g in created if g.gap_type == GapItem.GapType.UNCONFIRMED_FACT]
        self.assertEqual(len(unconfirmed), 1)
        self.assertEqual(unconfirmed[0].source_fact_id, fact.id)

    def test_confirmed_fact_does_not_get_unconfirmed_gap(self):
        self._make_fact(confidence_score=0.95, status=ExtractedFact.Status.CONFIRMED)
        created = generate_gaps_for_sprint(self.sprint)
        unconfirmed = [g for g in created if g.gap_type == GapItem.GapType.UNCONFIRMED_FACT]
        self.assertEqual(len(unconfirmed), 0)

    def test_conflicting_fact_values_create_a_conflict_gap(self):
        self._make_fact(field_key='total_faculty', value=100, confidence_score=0.9)
        self._make_fact(field_key='total_faculty', value=120, confidence_score=0.6)
        created = generate_gaps_for_sprint(self.sprint)
        conflicts = [g for g in created if g.gap_type == GapItem.GapType.CONFLICT]
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].priority, GapItem.Priority.HIGH)

    def test_matching_fact_values_do_not_create_a_conflict_gap(self):
        self._make_fact(field_key='total_faculty', value=100, confidence_score=0.9)
        self._make_fact(field_key='total_faculty', value=100, confidence_score=0.6)
        created = generate_gaps_for_sprint(self.sprint)
        conflicts = [g for g in created if g.gap_type == GapItem.GapType.CONFLICT]
        self.assertEqual(len(conflicts), 0)

    def test_rejected_fact_excluded_from_conflict_detection(self):
        self._make_fact(field_key='total_faculty', value=100, confidence_score=0.9)
        self._make_fact(
            field_key='total_faculty', value=999, confidence_score=0.6, status=ExtractedFact.Status.REJECTED,
        )
        created = generate_gaps_for_sprint(self.sprint)
        conflicts = [g for g in created if g.gap_type == GapItem.GapType.CONFLICT]
        self.assertEqual(len(conflicts), 0)

    def test_stale_document_creates_stale_data_gap(self):
        document = self._make_document(uploaded_at=timezone.now() - timedelta(days=400))
        created = generate_gaps_for_sprint(self.sprint)
        stale = [g for g in created if g.gap_type == GapItem.GapType.STALE_DATA]
        self.assertEqual(len(stale), 1)
        self.assertEqual(stale[0].related_document_id, document.id)

    def test_recent_document_does_not_create_stale_data_gap(self):
        self._make_document(uploaded_at=timezone.now())
        created = generate_gaps_for_sprint(self.sprint)
        stale = [g for g in created if g.gap_type == GapItem.GapType.STALE_DATA]
        self.assertEqual(len(stale), 0)


class GapListEndpointTests(GapTestBase):
    def test_list_scoped_to_sprint(self):
        self._make_gap()
        other_sprint = Sprint.objects.create(institution=self.institution, mode=Sprint.SprintMode.QUICK_CRI)
        self._make_gap(sprint=other_sprint, title='Other sprint gap')

        self._auth(self.iqac)
        response = self.client.get(f'/api/v1/sprints/{self.sprint.id}/gaps/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_list_without_trailing_slash_matches_frontend_client(self):
        self._make_gap()
        self._auth(self.iqac)
        response = self.client.get(f'/api/v1/sprints/{self.sprint.id}/gaps')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.data, list)

    def test_list_forbidden_for_outsider(self):
        self._make_gap()
        self._auth(self.outsider)
        response = self.client.get(f'/api/v1/sprints/{self.sprint.id}/gaps/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_list_unauthenticated_rejected(self):
        response = self.client.get(f'/api/v1/sprints/{self.sprint.id}/gaps/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_gaps_endpoint_is_read_only(self):
        self._auth(self.iqac)
        response = self.client.post(f'/api/v1/sprints/{self.sprint.id}/gaps/', {'title': 'sneaky'})
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_pagination_is_opt_in(self):
        for i in range(3):
            self._make_gap(title=f'Missing doc {i}')
        self._auth(self.iqac)

        plain = self.client.get(f'/api/v1/sprints/{self.sprint.id}/gaps/')
        self.assertIsInstance(plain.data, list)
        self.assertEqual(len(plain.data), 3)

        paginated = self.client.get(f'/api/v1/sprints/{self.sprint.id}/gaps/', {'page_size': 2, 'page': 1})
        self.assertIn('results', paginated.data)
        self.assertEqual(paginated.data['count'], 3)
        self.assertEqual(len(paginated.data['results']), 2)

    def test_filter_by_status(self):
        g1 = self._make_gap(title='a')
        self._make_gap(title='b')
        g1.status = GapItem.Status.RESOLVED
        g1.save(update_fields=['status'])

        self._auth(self.iqac)
        response = self.client.get(f'/api/v1/sprints/{self.sprint.id}/gaps/', {'status': 'resolved'})
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['id'], str(g1.id))

    def test_filter_by_gap_type(self):
        self._make_gap(title='a', gap_type=GapItem.GapType.MISSING_DOCUMENT)
        self._make_gap(title='b', gap_type=GapItem.GapType.STALE_DATA)
        self._auth(self.iqac)
        response = self.client.get(f'/api/v1/sprints/{self.sprint.id}/gaps/', {'gap_type': 'stale_data'})
        self.assertEqual(len(response.data), 1)

    def test_filter_by_priority(self):
        self._make_gap(title='a', priority=GapItem.Priority.BLOCKING)
        self._make_gap(title='b', priority=GapItem.Priority.OPTIONAL)
        self._auth(self.iqac)
        response = self.client.get(f'/api/v1/sprints/{self.sprint.id}/gaps/', {'priority': 'optional'})
        self.assertEqual(len(response.data), 1)

    def test_filter_by_pillar(self):
        self._make_gap(title='a', pillar='faculty_ai_capability')
        self._make_gap(title='b', pillar='governance_strategy')
        self._auth(self.iqac)
        response = self.client.get(
            f'/api/v1/sprints/{self.sprint.id}/gaps/', {'pillar': 'governance_strategy'},
        )
        self.assertEqual(len(response.data), 1)

    def test_owner_role_derived_from_source_fact(self):
        fact = self._make_fact(owner_role='REGISTRAR')
        self._make_gap(title='needs review', gap_type=GapItem.GapType.UNCONFIRMED_FACT, source_fact=fact)
        self._auth(self.iqac)
        response = self.client.get(f'/api/v1/sprints/{self.sprint.id}/gaps/')
        self.assertEqual(response.data[0]['owner_role'], 'REGISTRAR')

    def test_owner_role_derived_from_related_document(self):
        document = self._make_document(owner_role='LAB_ADMIN')
        self._make_gap(
            title='stale', gap_type=GapItem.GapType.STALE_DATA, related_document=document,
        )
        self._auth(self.iqac)
        response = self.client.get(f'/api/v1/sprints/{self.sprint.id}/gaps/')
        self.assertEqual(response.data[0]['owner_role'], 'LAB_ADMIN')


class GapDetailEndpointTests(GapTestBase):
    def test_retrieve_gap(self):
        gap = self._make_gap()
        self._auth(self.iqac)
        response = self.client.get(f'/api/v1/gaps/{gap.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], str(gap.id))
        self.assertEqual(response.data['status'], GapItem.Status.OPEN)

    def test_retrieve_forbidden_for_outsider(self):
        gap = self._make_gap()
        self._auth(self.outsider)
        response = self.client.get(f'/api/v1/gaps/{gap.id}/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_retrieve_unauthenticated_rejected(self):
        gap = self._make_gap()
        response = self.client.get(f'/api/v1/gaps/{gap.id}/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_response_includes_frontend_compatible_aliases(self):
        """GapDashboard.tsx (existing, unmodified) reads gap.audit_field_id
        and gap.score_impact -- neither is a stored column (score_impact was
        deliberately removed in favour of deriving it from priority)."""
        fact = self._make_fact()
        gap = self._make_gap(
            gap_type=GapItem.GapType.LOW_CONFIDENCE, source_fact=fact, priority=GapItem.Priority.HIGH,
        )
        self._auth(self.iqac)
        response = self.client.get(f'/api/v1/gaps/{gap.id}/')
        self.assertEqual(response.data['audit_field_id'], fact.field_key)
        self.assertEqual(response.data['score_impact'], 5.0)  # GAP_PRIORITY_SCORE_PENALTY['high']

    def test_audit_field_id_blank_when_gap_has_no_source_fact(self):
        gap = self._make_gap()  # default factory gap has no source_fact
        self._auth(self.iqac)
        response = self.client.get(f'/api/v1/gaps/{gap.id}/')
        self.assertEqual(response.data['audit_field_id'], '')


class GapResolveActionTests(GapTestBase):
    def test_resolve_sets_status_and_audit_fields(self):
        gap = self._make_gap()
        self._auth(self.hod)
        response = self.client.post(
            f'/api/v1/gaps/{gap.id}/resolve/', {'resolution': 'Uploaded the missing SSR.'},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], GapItem.Status.RESOLVED)
        self.assertEqual(response.data['resolution'], 'Uploaded the missing SSR.')

        gap.refresh_from_db()
        self.assertEqual(gap.status, GapItem.Status.RESOLVED)
        self.assertEqual(gap.resolved_by, self.hod)
        self.assertIsNotNone(gap.resolved_at)

    def test_resolve_accepts_legacy_value_field(self):
        """The unmodified frontend's GapDashboard sends `value`, not `resolution`."""
        gap = self._make_gap()
        self._auth(self.hod)
        response = self.client.post(f'/api/v1/gaps/{gap.id}/resolve/', {'value': 'Fixed via legacy client'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['resolution'], 'Fixed via legacy client')

    def test_resolve_without_trailing_slash(self):
        gap = self._make_gap()
        self._auth(self.hod)
        response = self.client.post(f'/api/v1/gaps/{gap.id}/resolve', {})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_viewer_cannot_resolve(self):
        gap = self._make_gap()
        self._auth(self.viewer)
        response = self.client.post(f'/api/v1/gaps/{gap.id}/resolve/', {})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        gap.refresh_from_db()
        self.assertEqual(gap.status, GapItem.Status.OPEN)

    def test_unauthenticated_resolve_rejected(self):
        gap = self._make_gap()
        response = self.client.post(f'/api/v1/gaps/{gap.id}/resolve/', {})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_outsider_cannot_resolve(self):
        gap = self._make_gap()
        self._auth(self.outsider)
        response = self.client.post(f'/api/v1/gaps/{gap.id}/resolve/', {})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class GapMarkUnavailableActionTests(GapTestBase):
    def test_mark_unavailable_sets_status_and_audit_fields(self):
        gap = self._make_gap()
        self._auth(self.hod)
        response = self.client.post(
            f'/api/v1/gaps/{gap.id}/mark-unavailable/', {'resolution': 'Data does not exist for this cycle.'},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], GapItem.Status.UNAVAILABLE)

        gap.refresh_from_db()
        self.assertEqual(gap.status, GapItem.Status.UNAVAILABLE)
        self.assertEqual(gap.resolved_by, self.hod)
        self.assertIsNotNone(gap.resolved_at)

    def test_viewer_cannot_mark_unavailable(self):
        gap = self._make_gap()
        self._auth(self.viewer)
        response = self.client.post(f'/api/v1/gaps/{gap.id}/mark-unavailable/', {})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_outsider_cannot_mark_unavailable(self):
        gap = self._make_gap()
        self._auth(self.outsider)
        response = self.client.post(f'/api/v1/gaps/{gap.id}/mark-unavailable/', {})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class GapSkipActionTests(GapTestBase):
    def test_skip_sets_status_and_audit_fields(self):
        gap = self._make_gap()
        self._auth(self.hod)
        response = self.client.post(f'/api/v1/gaps/{gap.id}/skip/', {'resolution': 'Not relevant this cycle.'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], GapItem.Status.SKIPPED)

        gap.refresh_from_db()
        self.assertEqual(gap.status, GapItem.Status.SKIPPED)
        self.assertEqual(gap.resolved_by, self.hod)
        self.assertIsNotNone(gap.resolved_at)

    def test_viewer_cannot_skip(self):
        gap = self._make_gap()
        self._auth(self.viewer)
        response = self.client.post(f'/api/v1/gaps/{gap.id}/skip/', {})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_skip_rejected(self):
        gap = self._make_gap()
        response = self.client.post(f'/api/v1/gaps/{gap.id}/skip/', {})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_outsider_cannot_skip(self):
        gap = self._make_gap()
        self._auth(self.outsider)
        response = self.client.post(f'/api/v1/gaps/{gap.id}/skip/', {})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
