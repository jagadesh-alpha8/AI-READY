from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.facts.models import ExtractedFact
from apps.gaps.models import GapItem
from apps.institutions.models import Institution
from apps.scoring.models import Pillar, PillarScore
from apps.sprints.models import Sprint

from .models import Recommendation
from .services import generate_recommendations_for_sprint

PASSWORD = 'Str0ng!DevPassw0rd'


class RecommendationsTestBase(APITestCase):
    def setUp(self):
        self.institution = Institution.objects.create(name='MKCE', city='Karur', state='TN')
        self.other_institution = Institution.objects.create(name='Other', city='X', state='Y')

        self.admin = self._make_user('admin@test.edu', User.Role.INSTITUTION_ADMIN, self.institution)
        self.viewer = self._make_user('viewer@test.edu', User.Role.VIEWER, self.institution)
        self.iqac = self._make_user('iqac@test.edu', User.Role.IQAC_COORDINATOR, self.institution)
        self.consultant = self._make_user('consultant@ingage.io', User.Role.CONSULTANT, None)
        self.outsider = self._make_user('outsider@test.edu', User.Role.INSTITUTION_ADMIN, self.other_institution)

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
            'field_name': 'Faculty Certified %',
            'field_key': 'faculty_certified_pct',
            'value': 62.5,
            'pillar': 'governance_strategy',
            'owner_role': 'registrar',
            'status': ExtractedFact.Status.CONFIRMED,
            'confidence_score': 0.8,
        }
        defaults.update(overrides)
        return ExtractedFact.objects.create(**defaults)

    def _make_gap(self, **overrides):
        defaults = {
            'sprint': self.sprint,
            'gap_type': GapItem.GapType.MISSING_DOCUMENT,
            'title': 'Missing something',
            'pillar': 'governance_strategy',
            'priority': GapItem.Priority.HIGH,
        }
        defaults.update(overrides)
        return GapItem.objects.create(**defaults)

    def _score_pillar(self, pillar_key, **overrides):
        pillar = Pillar.objects.get(key=pillar_key)
        defaults = {
            'sprint': self.sprint, 'pillar': pillar, 'raw_score': 30.0,
            'status': PillarScore.Status.AT_RISK, 'evidence_count': 1, 'gap_count': 0,
        }
        defaults.update(overrides)
        return PillarScore.objects.create(**defaults)


class GapRecommendationGeneratorTests(RecommendationsTestBase):
    def test_blocking_gap_generates_a_recommendation(self):
        gap = self._make_gap(priority=GapItem.Priority.BLOCKING, title='Missing NAAC SSR')
        generate_recommendations_for_sprint(self.sprint)
        rec = Recommendation.objects.get(sprint=self.sprint)
        self.assertEqual(rec.source_gap, gap)
        self.assertEqual(rec.pillar, 'governance_strategy')
        self.assertEqual(rec.priority, GapItem.Priority.BLOCKING)
        self.assertEqual(rec.timeline, '0-30 days')
        self.assertEqual(rec.expected_cri_lift, 8.0)
        self.assertIn('Why:', rec.description)

    def test_high_gap_generates_a_recommendation(self):
        self._make_gap(priority=GapItem.Priority.HIGH)
        generate_recommendations_for_sprint(self.sprint)
        rec = Recommendation.objects.get(sprint=self.sprint)
        self.assertEqual(rec.expected_cri_lift, 5.0)
        self.assertEqual(rec.timeline, '30-60 days')

    def test_medium_and_optional_gaps_do_not_generate_recommendations(self):
        self._make_gap(priority=GapItem.Priority.MEDIUM)
        self._make_gap(priority=GapItem.Priority.OPTIONAL, gap_type=GapItem.GapType.STALE_DATA)
        generate_recommendations_for_sprint(self.sprint)
        self.assertEqual(Recommendation.objects.count(), 0)

    def test_resolved_gap_does_not_generate_a_recommendation(self):
        self._make_gap(priority=GapItem.Priority.BLOCKING, status=GapItem.Status.RESOLVED)
        generate_recommendations_for_sprint(self.sprint)
        self.assertEqual(Recommendation.objects.count(), 0)

    def test_owner_role_derived_from_gap_source_fact(self):
        fact = self._make_fact(owner_role='faculty')
        gap = self._make_gap(priority=GapItem.Priority.HIGH, source_fact=fact, gap_type=GapItem.GapType.LOW_CONFIDENCE)
        generate_recommendations_for_sprint(self.sprint)
        rec = Recommendation.objects.get(source_gap=gap)
        self.assertEqual(rec.owner_role, 'faculty')
        self.assertIn(fact, rec.supporting_facts.all())

    def test_regenerate_does_not_duplicate_gap_recommendation(self):
        self._make_gap(priority=GapItem.Priority.BLOCKING)
        generate_recommendations_for_sprint(self.sprint)
        generate_recommendations_for_sprint(self.sprint)
        generate_recommendations_for_sprint(self.sprint)
        self.assertEqual(Recommendation.objects.count(), 1)


class EvidenceRecommendationGeneratorTests(RecommendationsTestBase):
    def test_low_confidence_confirmed_fact_generates_a_recommendation(self):
        fact = self._make_fact(confidence_score=0.2, status=ExtractedFact.Status.CONFIRMED)
        generate_recommendations_for_sprint(self.sprint)
        rec = Recommendation.objects.get(sprint=self.sprint)
        self.assertIn(fact, rec.supporting_facts.all())
        self.assertEqual(rec.priority, Recommendation.Priority.HIGH)
        self.assertEqual(rec.expected_cri_lift, 3.0)  # (0.5 - 0.2) * 10
        self.assertIn('Why:', rec.description)

    def test_moderately_low_confidence_fact_is_medium_priority(self):
        self._make_fact(confidence_score=0.45, status=ExtractedFact.Status.CORRECTED)
        generate_recommendations_for_sprint(self.sprint)
        rec = Recommendation.objects.get(sprint=self.sprint)
        self.assertEqual(rec.priority, Recommendation.Priority.MEDIUM)
        self.assertEqual(rec.expected_cri_lift, 0.5)

    def test_high_confidence_fact_does_not_generate_a_recommendation(self):
        self._make_fact(confidence_score=0.8, status=ExtractedFact.Status.CONFIRMED)
        generate_recommendations_for_sprint(self.sprint)
        self.assertEqual(Recommendation.objects.count(), 0)

    def test_unreviewed_low_confidence_fact_does_not_generate_a_recommendation(self):
        self._make_fact(confidence_score=0.1, status=ExtractedFact.Status.EXTRACTED)
        generate_recommendations_for_sprint(self.sprint)
        self.assertEqual(Recommendation.objects.count(), 0)

    def test_regenerate_does_not_duplicate_evidence_recommendation(self):
        self._make_fact(confidence_score=0.2)
        generate_recommendations_for_sprint(self.sprint)
        generate_recommendations_for_sprint(self.sprint)
        self.assertEqual(Recommendation.objects.count(), 1)


class PillarWeaknessRecommendationGeneratorTests(RecommendationsTestBase):
    def test_at_risk_pillar_generates_a_blocking_recommendation(self):
        self._score_pillar('governance_strategy', raw_score=30.0, status=PillarScore.Status.AT_RISK)
        generate_recommendations_for_sprint(self.sprint)
        rec = Recommendation.objects.get(sprint=self.sprint)
        self.assertEqual(rec.pillar, 'governance_strategy')
        self.assertIsNone(rec.source_gap)
        self.assertEqual(rec.priority, Recommendation.Priority.BLOCKING)
        self.assertEqual(rec.expected_cri_lift, 4.0)  # 0.10 weight * (70 - 30)
        self.assertIn('Why:', rec.description)

    def test_not_started_pillar_generates_a_high_priority_recommendation(self):
        self._score_pillar(
            'governance_strategy', raw_score=0.0, status=PillarScore.Status.NOT_STARTED, evidence_count=0,
        )
        generate_recommendations_for_sprint(self.sprint)
        rec = Recommendation.objects.get(sprint=self.sprint)
        self.assertEqual(rec.priority, Recommendation.Priority.HIGH)
        self.assertEqual(rec.expected_cri_lift, 7.0)  # 0.10 weight * (70 - 0)

    def test_strong_pillar_does_not_generate_a_recommendation(self):
        self._score_pillar('governance_strategy', raw_score=90.0, status=PillarScore.Status.STRONG)
        generate_recommendations_for_sprint(self.sprint)
        self.assertEqual(Recommendation.objects.count(), 0)

    def test_regenerate_does_not_duplicate_weakness_recommendation(self):
        self._score_pillar('governance_strategy', status=PillarScore.Status.AT_RISK)
        generate_recommendations_for_sprint(self.sprint)
        generate_recommendations_for_sprint(self.sprint)
        self.assertEqual(Recommendation.objects.count(), 1)


class CombinedGenerationTests(RecommendationsTestBase):
    def test_generate_covers_all_three_sources_independently_in_one_call(self):
        self._make_gap(priority=GapItem.Priority.BLOCKING, pillar='infrastructure_digital_capability')
        self._make_fact(
            field_key='low_conf', pillar='faculty_ai_capability', confidence_score=0.2,
            status=ExtractedFact.Status.CONFIRMED,
        )
        self._score_pillar('student_ai_readiness', raw_score=25.0, status=PillarScore.Status.AT_RISK)

        recommendations = generate_recommendations_for_sprint(self.sprint)

        self.assertEqual(len(recommendations), 3)
        pillars = {r.pillar for r in recommendations}
        self.assertEqual(
            pillars, {'infrastructure_digital_capability', 'faculty_ai_capability', 'student_ai_readiness'},
        )

    def test_generation_is_deterministic_for_the_same_input_data(self):
        self._make_gap(priority=GapItem.Priority.HIGH)
        self._make_fact(field_key='low_conf', confidence_score=0.3, status=ExtractedFact.Status.CONFIRMED)
        self._score_pillar('research_innovation', status=PillarScore.Status.AT_RISK, raw_score=10.0)

        run1 = {(r.pillar, r.priority, r.expected_cri_lift) for r in generate_recommendations_for_sprint(self.sprint)}
        run2 = {(r.pillar, r.priority, r.expected_cri_lift) for r in generate_recommendations_for_sprint(self.sprint)}
        self.assertEqual(run1, run2)


class RecommendationEndpointTests(RecommendationsTestBase):
    def test_generate_endpoint_creates_recommendations(self):
        self._make_gap(priority=GapItem.Priority.BLOCKING)
        self._auth(self.admin)
        response = self.client.post(f'/api/v1/sprints/{self.sprint.id}/recommendations/generate/')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(response.data), 1)

    def test_generate_endpoint_without_trailing_slash(self):
        self._make_gap(priority=GapItem.Priority.BLOCKING)
        self._auth(self.admin)
        response = self.client.post(f'/api/v1/sprints/{self.sprint.id}/recommendations/generate')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_post_to_list_endpoint_also_generates_for_backward_compatibility(self):
        self._make_gap(priority=GapItem.Priority.BLOCKING)
        self._auth(self.admin)
        response = self.client.post(f'/api/v1/sprints/{self.sprint.id}/recommendations')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(response.data), 1)

    def test_get_list_endpoint_returns_generated_recommendations(self):
        self._make_gap(priority=GapItem.Priority.HIGH)
        generate_recommendations_for_sprint(self.sprint)
        self._auth(self.iqac)
        response = self.client.get(f'/api/v1/sprints/{self.sprint.id}/recommendations/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_get_detail_endpoint_includes_frontend_compatible_aliases(self):
        self._make_gap(priority=GapItem.Priority.BLOCKING)
        rec = generate_recommendations_for_sprint(self.sprint)[0]
        self._auth(self.iqac)
        response = self.client.get(f'/api/v1/recommendations/{rec.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['recommendation_text'], response.data['description'])
        self.assertEqual(response.data['expected_score_lift'], response.data['expected_cri_lift'])
        self.assertEqual(response.data['edited_text'], '')

    def test_viewer_can_view_but_not_generate(self):
        self._auth(self.viewer)
        get_response = self.client.get(f'/api/v1/sprints/{self.sprint.id}/recommendations/')
        self.assertEqual(get_response.status_code, status.HTTP_200_OK)
        post_response = self.client.post(f'/api/v1/sprints/{self.sprint.id}/recommendations/generate/')
        self.assertEqual(post_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_outsider_forbidden_on_list_and_generate(self):
        self._auth(self.outsider)
        get_response = self.client.get(f'/api/v1/sprints/{self.sprint.id}/recommendations/')
        self.assertEqual(get_response.status_code, status.HTTP_403_FORBIDDEN)
        post_response = self.client.post(f'/api/v1/sprints/{self.sprint.id}/recommendations/generate/')
        self.assertEqual(post_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_rejected(self):
        response = self.client.get(f'/api/v1/sprints/{self.sprint.id}/recommendations/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class RecommendationEditTests(RecommendationsTestBase):
    def _make_recommendation(self):
        self._make_gap(priority=GapItem.Priority.BLOCKING)
        return generate_recommendations_for_sprint(self.sprint)[0]

    def test_consultant_can_edit_and_status_moves_to_edited(self):
        rec = self._make_recommendation()
        self._auth(self.consultant)
        response = self.client.patch(
            f'/api/v1/recommendations/{rec.id}/', {'description': 'Revised guidance for the institution.'},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        rec.refresh_from_db()
        self.assertEqual(rec.description, 'Revised guidance for the institution.')
        self.assertEqual(rec.status, Recommendation.Status.EDITED)
        self.assertEqual(rec.updated_by, self.consultant)

    def test_consultant_can_set_status_explicitly_without_forcing_edited(self):
        rec = self._make_recommendation()
        self._auth(self.consultant)
        response = self.client.patch(f'/api/v1/recommendations/{rec.id}/', {'status': 'accepted'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        rec.refresh_from_db()
        self.assertEqual(rec.status, Recommendation.Status.ACCEPTED)

    def test_consultant_can_add_notes_and_mark_completed(self):
        rec = self._make_recommendation()
        self._auth(self.consultant)
        response = self.client.patch(
            f'/api/v1/recommendations/{rec.id}/',
            {'consultant_notes': 'Verified with registrar.', 'status': 'completed'},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        rec.refresh_from_db()
        self.assertEqual(rec.consultant_notes, 'Verified with registrar.')
        self.assertEqual(rec.status, Recommendation.Status.COMPLETED)

    def test_institution_admin_cannot_edit(self):
        rec = self._make_recommendation()
        self._auth(self.admin)
        response = self.client.patch(f'/api/v1/recommendations/{rec.id}/', {'status': 'hidden'})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_iqac_coordinator_cannot_edit(self):
        rec = self._make_recommendation()
        self._auth(self.iqac)
        response = self.client.patch(f'/api/v1/recommendations/{rec.id}/', {'status': 'hidden'})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_viewer_cannot_edit(self):
        rec = self._make_recommendation()
        self._auth(self.viewer)
        response = self.client.patch(f'/api/v1/recommendations/{rec.id}/', {'status': 'hidden'})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_cannot_edit(self):
        rec = self._make_recommendation()
        response = self.client.patch(f'/api/v1/recommendations/{rec.id}/', {'status': 'hidden'})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_expected_cri_lift_above_100_is_rejected(self):
        rec = self._make_recommendation()
        self._auth(self.consultant)
        response = self.client.patch(f'/api/v1/recommendations/{rec.id}/', {'expected_cri_lift': 150})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('expected_cri_lift', response.data)

    def test_expected_cri_lift_negative_is_rejected(self):
        rec = self._make_recommendation()
        self._auth(self.consultant)
        response = self.client.patch(f'/api/v1/recommendations/{rec.id}/', {'expected_cri_lift': -1})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_expected_cri_lift_in_range_is_accepted(self):
        rec = self._make_recommendation()
        self._auth(self.consultant)
        response = self.client.patch(f'/api/v1/recommendations/{rec.id}/', {'expected_cri_lift': 12.5})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        rec.refresh_from_db()
        self.assertEqual(rec.expected_cri_lift, 12.5)

    def test_edit_cannot_reassign_pillar_or_source_gap(self):
        """PATCH only exposes content fields -- the trigger/evidence linkage
        the engine established stays put no matter what a consultant sends."""
        rec = self._make_recommendation()
        original_pillar = rec.pillar
        original_source_gap_id = rec.source_gap_id
        self._auth(self.consultant)
        response = self.client.patch(
            f'/api/v1/recommendations/{rec.id}/', {'pillar': 'research_innovation'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        rec.refresh_from_db()
        self.assertEqual(rec.pillar, original_pillar)
        self.assertEqual(rec.source_gap_id, original_source_gap_id)
