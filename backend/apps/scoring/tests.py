from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.facts.models import ExtractedFact
from apps.gaps.models import GapItem
from apps.institutions.models import Institution
from apps.sprints.models import Sprint

from .models import Baseline, BaselineDecisionHistory, Pillar, PillarCriterion, PillarScore, ScoringRun
from .services import build_score_snapshot, run_scoring_engine

PASSWORD = 'Str0ng!DevPassw0rd'


class ScoringTestBase(APITestCase):
    def setUp(self):
        self.institution = Institution.objects.create(name='MKCE', city='Karur', state='TN')
        self.other_institution = Institution.objects.create(name='Other', city='X', state='Y')

        self.admin = self._make_user('admin@test.edu', User.Role.INSTITUTION_ADMIN, self.institution)
        self.viewer = self._make_user('viewer@test.edu', User.Role.VIEWER, self.institution)
        self.iqac = self._make_user('iqac@test.edu', User.Role.IQAC_COORDINATOR, self.institution)
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
            'priority': GapItem.Priority.MEDIUM,
        }
        defaults.update(overrides)
        return GapItem.objects.create(**defaults)


class EngineDeterminismTests(ScoringTestBase):
    """Known-input, known-output tests: the engine must be a pure function
    of the fact/gap/pillar-config data in the database."""

    def test_raw_score_is_average_confidence_of_confirmed_and_corrected_facts(self):
        self._make_fact(field_key='f1', confidence_score=0.8, status=ExtractedFact.Status.CONFIRMED)
        self._make_fact(field_key='f2', confidence_score=0.6, status=ExtractedFact.Status.CORRECTED)

        run_scoring_engine(self.sprint)
        pillar_score = PillarScore.objects.get(sprint=self.sprint, pillar__key='governance_strategy')
        self.assertEqual(pillar_score.raw_score, 70.0)
        self.assertEqual(pillar_score.confidence_score, 0.7)
        self.assertEqual(pillar_score.evidence_count, 2)

    def test_weighted_score_is_raw_score_times_pillar_weight(self):
        self._make_fact(confidence_score=0.8)
        run_scoring_engine(self.sprint)
        pillar_score = PillarScore.objects.get(sprint=self.sprint, pillar__key='governance_strategy')
        governance = Pillar.objects.get(key='governance_strategy')
        self.assertEqual(pillar_score.weighted_score, round(pillar_score.raw_score * governance.weight, 2))

    def test_extracted_but_unreviewed_facts_do_not_count_as_evidence(self):
        self._make_fact(status=ExtractedFact.Status.EXTRACTED, confidence_score=0.99)
        run_scoring_engine(self.sprint)
        pillar_score = PillarScore.objects.get(sprint=self.sprint, pillar__key='governance_strategy')
        self.assertEqual(pillar_score.evidence_count, 0)
        self.assertEqual(pillar_score.raw_score, 0.0)
        self.assertEqual(pillar_score.status, PillarScore.Status.NOT_STARTED)

    def test_rejected_facts_do_not_count_as_evidence(self):
        self._make_fact(status=ExtractedFact.Status.REJECTED, confidence_score=0.99)
        run_scoring_engine(self.sprint)
        pillar_score = PillarScore.objects.get(sprint=self.sprint, pillar__key='governance_strategy')
        self.assertEqual(pillar_score.evidence_count, 0)

    def test_unresolved_gap_reduces_raw_score_by_fixed_priority_penalty(self):
        self._make_fact(confidence_score=0.95)
        self._make_gap(priority=GapItem.Priority.BLOCKING)
        run_scoring_engine(self.sprint)
        pillar_score = PillarScore.objects.get(sprint=self.sprint, pillar__key='governance_strategy')
        self.assertEqual(pillar_score.raw_score, 87.0)  # 95 - 8 (blocking penalty)
        self.assertEqual(pillar_score.gap_count, 1)

    def test_resolved_gap_does_not_reduce_score(self):
        self._make_fact(confidence_score=0.95)
        self._make_gap(priority=GapItem.Priority.BLOCKING, status=GapItem.Status.RESOLVED)
        run_scoring_engine(self.sprint)
        pillar_score = PillarScore.objects.get(sprint=self.sprint, pillar__key='governance_strategy')
        self.assertEqual(pillar_score.raw_score, 95.0)
        self.assertEqual(pillar_score.gap_count, 0)

    def test_blocking_gap_forces_at_risk_status_despite_high_score(self):
        self._make_fact(confidence_score=0.99)
        self._make_gap(priority=GapItem.Priority.BLOCKING)
        run_scoring_engine(self.sprint)
        pillar_score = PillarScore.objects.get(sprint=self.sprint, pillar__key='governance_strategy')
        self.assertGreater(pillar_score.raw_score, 70)
        self.assertEqual(pillar_score.status, PillarScore.Status.AT_RISK)

    def test_status_thresholds(self):
        cases = [
            (0.90, GapItem.Priority.OPTIONAL, PillarScore.Status.STRONG),   # 90 - 1 = 89
            (0.45, GapItem.Priority.OPTIONAL, PillarScore.Status.DEVELOPING),  # 45 - 1 = 44
            (0.20, GapItem.Priority.OPTIONAL, PillarScore.Status.AT_RISK),  # 20 - 1 = 19
        ]
        for confidence, gap_priority, expected_status in cases:
            sprint = Sprint.objects.create(institution=self.institution, mode=Sprint.SprintMode.VERIFIED_CRI)
            self._make_fact(sprint=sprint, confidence_score=confidence)
            self._make_gap(sprint=sprint, priority=gap_priority)
            run_scoring_engine(sprint)
            pillar_score = PillarScore.objects.get(sprint=sprint, pillar__key='governance_strategy')
            self.assertEqual(pillar_score.status, expected_status, msg=f'confidence={confidence}')

    def test_overall_cri_is_sum_of_pillar_weighted_scores(self):
        self._make_fact(pillar='governance_strategy', confidence_score=0.8)  # weight .10 -> 8.0
        self._make_fact(
            sprint=self.sprint, field_key='f2', pillar='faculty_ai_capability', confidence_score=0.5,
        )  # weight .18 -> 9.0
        scoring_run = run_scoring_engine(self.sprint)
        self.assertEqual(scoring_run.overall_cri, 17.0)

    def test_overall_confidence_is_weight_weighted_average_of_pillar_confidence(self):
        self._make_fact(pillar='governance_strategy', confidence_score=0.8)  # weight .10
        self._make_fact(
            sprint=self.sprint, field_key='f2', pillar='faculty_ai_capability', confidence_score=0.5,
        )  # weight .18
        scoring_run = run_scoring_engine(self.sprint)
        expected = round(0.8 * 0.10 + 0.5 * 0.18, 4)
        self.assertEqual(scoring_run.overall_confidence, expected)

    def test_engine_is_deterministic_across_repeated_runs_with_unchanged_data(self):
        self._make_fact(confidence_score=0.73)
        self._make_gap(priority=GapItem.Priority.HIGH)
        run1 = run_scoring_engine(self.sprint)
        run2 = run_scoring_engine(self.sprint)
        run3 = run_scoring_engine(self.sprint)
        self.assertEqual(run1.overall_cri, run2.overall_cri)
        self.assertEqual(run2.overall_cri, run3.overall_cri)
        self.assertEqual(run1.overall_confidence, run3.overall_confidence)
        self.assertEqual(run1.calculation_version, run3.calculation_version)

    def test_does_not_hardcode_the_frontend_demo_score(self):
        """Regression guard: an unscored sprint with no evidence must score
        0, never the frontend's old fallback demo value of 58 (or any other
        pillar's hardcoded demo score like 62.5, 45.0, 70.0...)."""
        scoring_run = run_scoring_engine(self.sprint)
        self.assertEqual(scoring_run.overall_cri, 0.0)
        self.assertNotEqual(scoring_run.overall_cri, 58)
        for pillar_score in PillarScore.objects.filter(sprint=self.sprint):
            self.assertEqual(pillar_score.raw_score, 0.0)
            self.assertEqual(pillar_score.status, PillarScore.Status.NOT_STARTED)

    def test_calculation_version_changes_when_pillar_weight_changes(self):
        self._make_fact(confidence_score=0.8)
        run1 = run_scoring_engine(self.sprint)

        governance = Pillar.objects.get(key='governance_strategy')
        governance.weight = 0.20
        governance.save(update_fields=['weight'])

        run2 = run_scoring_engine(self.sprint)
        self.assertNotEqual(run1.calculation_version, run2.calculation_version)

    def test_calculation_version_unchanged_when_config_is_unchanged(self):
        self._make_fact(confidence_score=0.8)
        run1 = run_scoring_engine(self.sprint)
        run2 = run_scoring_engine(self.sprint)
        self.assertEqual(run1.calculation_version, run2.calculation_version)

    def test_inactive_pillar_is_excluded_and_contributes_zero(self):
        self._make_fact(pillar='research_innovation', confidence_score=0.9)
        research = Pillar.objects.get(key='research_innovation')
        research.is_active = False
        research.save(update_fields=['is_active'])

        scoring_run = run_scoring_engine(self.sprint)
        self.assertFalse(PillarScore.objects.filter(sprint=self.sprint, pillar=research).exists())
        self.assertEqual(scoring_run.overall_cri, 0.0)

    def test_inactive_criterion_excluded_from_pillar_evaluation(self):
        governance = Pillar.objects.get(key='governance_strategy')
        criterion = PillarCriterion.objects.get(pillar=governance, key='general_evidence')
        criterion.is_active = False
        criterion.save(update_fields=['is_active'])

        self._make_fact(confidence_score=0.9)
        run_scoring_engine(self.sprint)
        pillar_score = PillarScore.objects.get(sprint=self.sprint, pillar=governance)
        self.assertEqual(pillar_score.raw_score, 0.0)
        self.assertEqual(pillar_score.status, PillarScore.Status.NOT_STARTED)

    def test_criterion_scoped_to_specific_fact_field_keys(self):
        governance = Pillar.objects.get(key='governance_strategy')
        PillarCriterion.objects.filter(pillar=governance).update(fact_field_keys=['relevant_field'])

        self._make_fact(field_key='relevant_field', confidence_score=0.9)
        self._make_fact(field_key='irrelevant_field', confidence_score=0.1)

        run_scoring_engine(self.sprint)
        pillar_score = PillarScore.objects.get(sprint=self.sprint, pillar=governance)
        self.assertEqual(pillar_score.raw_score, 90.0)
        self.assertEqual(pillar_score.evidence_count, 1)

    def test_scoring_run_persists_a_pillar_snapshot(self):
        self._make_fact(confidence_score=0.8)
        scoring_run = run_scoring_engine(self.sprint)
        governance_snapshot = next(p for p in scoring_run.pillar_snapshot if p['pillar'] == 'governance_strategy')
        self.assertEqual(governance_snapshot['raw_score'], 80.0)
        self.assertEqual(governance_snapshot['evidence_count'], 1)

    def test_triggered_by_recorded_on_scoring_run(self):
        self._make_fact()
        scoring_run = run_scoring_engine(self.sprint, triggered_by=self.admin)
        self.assertEqual(scoring_run.triggered_by, self.admin)


class BuildScoreSnapshotTests(ScoringTestBase):
    def test_bootstrap_true_computes_a_score_for_a_never_scored_sprint(self):
        self._make_fact(confidence_score=0.8)
        snapshot = build_score_snapshot(self.sprint, bootstrap=True)
        self.assertEqual(snapshot['overall_cri'], 8.0)
        self.assertTrue(ScoringRun.objects.filter(sprint=self.sprint).exists())

    def test_bootstrap_false_returns_none_for_a_never_scored_sprint(self):
        self._make_fact(confidence_score=0.8)
        snapshot = build_score_snapshot(self.sprint, bootstrap=False)
        self.assertIsNone(snapshot)
        self.assertFalse(ScoringRun.objects.filter(sprint=self.sprint).exists())

    def test_strengths_and_weaknesses_are_derived_from_pillar_status(self):
        self._make_fact(pillar='governance_strategy', confidence_score=0.9)  # strong
        run_scoring_engine(self.sprint)
        snapshot = build_score_snapshot(self.sprint)
        strength_keys = [p.pillar.key for p in snapshot['strengths']]
        weakness_keys = [p.pillar.key for p in snapshot['weaknesses']]
        self.assertIn('governance_strategy', strength_keys)
        self.assertNotIn('governance_strategy', weakness_keys)
        self.assertIn('faculty_ai_capability', weakness_keys)  # never evidenced -> not_started

    def test_evidence_metrics_are_live_not_frozen(self):
        fact = self._make_fact(confidence_score=0.8)
        run_scoring_engine(self.sprint)
        self._make_gap()
        snapshot = build_score_snapshot(self.sprint)
        self.assertEqual(snapshot['evidence_metrics']['confirmed_facts'], 1)
        self.assertEqual(snapshot['evidence_metrics']['unresolved_gaps'], 1)
        fact.status = ExtractedFact.Status.REJECTED
        fact.save(update_fields=['status'])
        snapshot2 = build_score_snapshot(self.sprint)
        self.assertEqual(snapshot2['evidence_metrics']['confirmed_facts'], 0)

    def test_unresolved_blocking_gaps_included(self):
        self._make_gap(priority=GapItem.Priority.BLOCKING, title='Blocking one')
        self._make_gap(priority=GapItem.Priority.MEDIUM, title='Non-blocking one')
        snapshot = build_score_snapshot(self.sprint)
        titles = [g.title for g in snapshot['unresolved_blocking_gaps']]
        self.assertEqual(titles, ['Blocking one'])


class SprintScoreEndpointTests(ScoringTestBase):
    def test_get_computes_and_persists_score_for_unscored_sprint(self):
        self._make_fact(confidence_score=0.8)
        self._auth(self.iqac)
        response = self.client.get(f'/api/v1/sprints/{self.sprint.id}/score/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['overall_cri'], 8.0)
        self.assertTrue(ScoringRun.objects.filter(sprint=self.sprint).exists())

    def test_get_without_trailing_slash(self):
        self._auth(self.iqac)
        response = self.client.get(f'/api/v1/sprints/{self.sprint.id}/score')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_response_includes_frontend_compatible_aliases(self):
        self._make_fact(confidence_score=0.8)
        self._auth(self.iqac)
        response = self.client.get(f'/api/v1/sprints/{self.sprint.id}/score/')
        self.assertEqual(response.data['cri_score'], response.data['overall_cri'])
        self.assertEqual(response.data['cri_confidence'], response.data['overall_confidence'])
        pillar = next(p for p in response.data['pillar_scores'] if p['pillar'] == 'governance_strategy')
        self.assertEqual(pillar['score'], pillar['raw_score'])
        self.assertEqual(pillar['confidence'], pillar['confidence_score'])
        self.assertIn('label', pillar)
        self.assertIn('weight', pillar)

    def test_response_includes_full_explainable_shape(self):
        self._make_fact(confidence_score=0.8)
        self._make_gap(priority=GapItem.Priority.BLOCKING)
        self._auth(self.iqac)
        response = self.client.get(f'/api/v1/sprints/{self.sprint.id}/score/')
        for key in (
            'overall_cri', 'overall_confidence', 'calculation_version', 'calculated_at',
            'pillar_scores', 'strengths', 'weaknesses', 'evidence_metrics', 'unresolved_blocking_gaps',
        ):
            self.assertIn(key, response.data)
        self.assertEqual(len(response.data['pillar_scores']), 8)
        self.assertEqual(len(response.data['unresolved_blocking_gaps']), 1)

    def test_post_recalculates_and_advances_sprint_status(self):
        self.sprint.status = Sprint.Status.REVIEWING
        self.sprint.save(update_fields=['status'])
        self._make_fact(confidence_score=0.8)

        self._auth(self.admin)
        response = self.client.post(f'/api/v1/sprints/{self.sprint.id}/score/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['overall_cri'], 8.0)

        self.sprint.refresh_from_db()
        self.assertEqual(self.sprint.status, Sprint.Status.SCORING)
        self.assertEqual(ScoringRun.objects.filter(sprint=self.sprint).count(), 1)

    def test_post_creates_a_new_scoring_run_each_time(self):
        self._auth(self.admin)
        self.client.post(f'/api/v1/sprints/{self.sprint.id}/score/')
        self.client.post(f'/api/v1/sprints/{self.sprint.id}/score/')
        self.assertEqual(ScoringRun.objects.filter(sprint=self.sprint).count(), 2)

    def test_viewer_can_get_but_not_post(self):
        self._auth(self.viewer)
        get_response = self.client.get(f'/api/v1/sprints/{self.sprint.id}/score/')
        self.assertEqual(get_response.status_code, status.HTTP_200_OK)
        post_response = self.client.post(f'/api/v1/sprints/{self.sprint.id}/score/')
        self.assertEqual(post_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_outsider_forbidden_on_get_and_post(self):
        self._auth(self.outsider)
        get_response = self.client.get(f'/api/v1/sprints/{self.sprint.id}/score/')
        self.assertEqual(get_response.status_code, status.HTTP_403_FORBIDDEN)
        post_response = self.client.post(f'/api/v1/sprints/{self.sprint.id}/score/')
        self.assertEqual(post_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_rejected(self):
        response = self.client.get(f'/api/v1/sprints/{self.sprint.id}/score/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class SprintScoreHistoryEndpointTests(ScoringTestBase):
    def test_history_lists_runs_most_recent_first(self):
        self._auth(self.admin)
        self.client.post(f'/api/v1/sprints/{self.sprint.id}/score/')
        self._make_fact(confidence_score=0.5)
        self.client.post(f'/api/v1/sprints/{self.sprint.id}/score/')
        creation_order = list(
            ScoringRun.objects.filter(sprint=self.sprint).order_by('created_at').values_list('id', flat=True),
        )

        response = self.client.get(f'/api/v1/sprints/{self.sprint.id}/score/history/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)
        self.assertEqual([row['id'] for row in response.data], [str(rid) for rid in reversed(creation_order)])

    def test_history_without_trailing_slash(self):
        self._auth(self.admin)
        self.client.post(f'/api/v1/sprints/{self.sprint.id}/score/')
        response = self.client.get(f'/api/v1/sprints/{self.sprint.id}/score/history')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_history_entry_includes_pillar_snapshot(self):
        self._make_fact(confidence_score=0.8)
        self._auth(self.admin)
        self.client.post(f'/api/v1/sprints/{self.sprint.id}/score/')
        response = self.client.get(f'/api/v1/sprints/{self.sprint.id}/score/history/')
        self.assertEqual(len(response.data[0]['pillar_snapshot']), 8)

    def test_history_pagination_is_opt_in(self):
        self._auth(self.admin)
        for _ in range(3):
            self.client.post(f'/api/v1/sprints/{self.sprint.id}/score/')

        plain = self.client.get(f'/api/v1/sprints/{self.sprint.id}/score/history/')
        self.assertIsInstance(plain.data, list)
        self.assertEqual(len(plain.data), 3)

        paginated = self.client.get(
            f'/api/v1/sprints/{self.sprint.id}/score/history/', {'page_size': 2, 'page': 1},
        )
        self.assertIn('results', paginated.data)
        self.assertEqual(paginated.data['count'], 3)

    def test_history_forbidden_for_outsider(self):
        self._auth(self.outsider)
        response = self.client.get(f'/api/v1/sprints/{self.sprint.id}/score/history/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_history_unauthenticated_rejected(self):
        response = self.client.get(f'/api/v1/sprints/{self.sprint.id}/score/history/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class SprintOverviewScoreIntegrationTests(ScoringTestBase):
    def test_overview_scorecard_is_none_when_never_scored(self):
        self._auth(self.iqac)
        response = self.client.get(f'/api/v1/sprints/{self.sprint.id}/overview/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data['scorecard'])

    def test_overview_scorecard_reflects_latest_score_after_post(self):
        self._make_fact(confidence_score=0.8)
        self._auth(self.admin)
        self.client.post(f'/api/v1/sprints/{self.sprint.id}/score/')

        response = self.client.get(f'/api/v1/sprints/{self.sprint.id}/overview/')
        self.assertEqual(response.data['scorecard']['overall_cri'], 8.0)


class ScoringConfigEndpointTests(ScoringTestBase):
    def test_config_returns_all_eight_pillars_from_the_database(self):
        self._auth(self.iqac)
        response = self.client.get('/api/v1/scoring/config')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 8)
        keys = {p['key'] for p in response.data}
        self.assertIn('governance_strategy', keys)
        self.assertIn('evidence_quality', keys)

    def test_config_reflects_database_weight_not_a_hardcoded_constant(self):
        governance = Pillar.objects.get(key='governance_strategy')
        governance.weight = 0.33
        governance.save(update_fields=['weight'])

        self._auth(self.iqac)
        response = self.client.get('/api/v1/scoring/config')
        pillar = next(p for p in response.data if p['key'] == 'governance_strategy')
        self.assertEqual(pillar['weight'], 0.33)


class BaselineWorkflowTests(ScoringTestBase):
    """Real persistent baseline approval -- apps.scoring.models.Baseline,
    apps.scoring.services.baseline, apps.scoring.views.SprintBaseline*."""

    def _get_baseline(self, user):
        self._auth(user)
        return self.client.get(f'/api/v1/sprints/{self.sprint.id}/baseline/')

    # -- bootstrap ------------------------------------------------------------

    def test_get_baseline_bootstraps_pending_from_scoring_status(self):
        self._make_fact(confidence_score=0.8)
        self.sprint.status = Sprint.Status.REVIEWING
        self.sprint.save(update_fields=['status'])
        self._auth(self.admin)
        self.client.post(f'/api/v1/sprints/{self.sprint.id}/score/')

        response = self._get_baseline(self.admin)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['baseline']['status'], Baseline.Status.PENDING)
        self.assertIsNotNone(response.data['score'])

        self.sprint.refresh_from_db()
        self.assertEqual(self.sprint.status, Sprint.Status.BASELINE_PENDING)

    def test_get_baseline_bootstraps_score_if_never_explicitly_scored(self):
        """A sprint still at REVIEWING (POST /score was never called) still
        gets a real baseline on first GET -- same bootstrap posture as
        GET .../score/ itself."""
        self._make_fact(confidence_score=0.9)
        self.assertEqual(self.sprint.status, Sprint.Status.DRAFT)
        self.sprint.status = Sprint.Status.REVIEWING
        self.sprint.save(update_fields=['status'])

        response = self._get_baseline(self.admin)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(ScoringRun.objects.filter(sprint=self.sprint).count(), 1)
        self.sprint.refresh_from_db()
        self.assertEqual(self.sprint.status, Sprint.Status.BASELINE_PENDING)

    def test_get_baseline_is_idempotent(self):
        self._make_fact(confidence_score=0.7)
        self._auth(self.admin)
        self.client.post(f'/api/v1/sprints/{self.sprint.id}/score/')

        first = self._get_baseline(self.admin)
        second = self._get_baseline(self.admin)
        self.assertEqual(first.data['baseline']['id'], second.data['baseline']['id'])
        self.assertEqual(Baseline.objects.filter(sprint=self.sprint).count(), 1)

    def test_get_baseline_reports_blocking_and_high_priority_gaps(self):
        self._make_fact(confidence_score=0.8)
        self._make_gap(title='Blocking gap', priority=GapItem.Priority.BLOCKING)
        self._make_gap(title='High gap', priority=GapItem.Priority.HIGH)
        self._make_gap(title='Medium gap', priority=GapItem.Priority.MEDIUM)
        self._auth(self.admin)
        self.client.post(f'/api/v1/sprints/{self.sprint.id}/score/')

        response = self._get_baseline(self.admin)
        self.assertEqual(len(response.data['high_priority_gaps']), 2)
        self.assertFalse(response.data['can_approve'])

    def test_can_approve_true_with_no_blocking_gaps(self):
        self._make_fact(confidence_score=0.8)
        response = self._get_baseline(self.admin)
        self.assertTrue(response.data['can_approve'])

    # -- permissions ------------------------------------------------------------

    def test_viewer_can_read_but_not_approve_baseline(self):
        self._make_fact(confidence_score=0.8)
        get_response = self._get_baseline(self.viewer)
        self.assertEqual(get_response.status_code, status.HTTP_200_OK)

        self._auth(self.viewer)
        response = self.client.post(f'/api/v1/sprints/{self.sprint.id}/baseline/approve/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_iqac_coordinator_cannot_approve_baseline(self):
        """Only sprint-management roles (super_admin/consultant/
        institution_admin) may decide a baseline -- every other non-viewer
        role can review facts/gaps, but not this."""
        self._make_fact(confidence_score=0.8)
        self._get_baseline(self.iqac)
        self._auth(self.iqac)
        response = self.client.post(f'/api/v1/sprints/{self.sprint.id}/baseline/approve/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_outsider_forbidden_from_other_institution_baseline(self):
        self._make_fact(confidence_score=0.8)
        response = self._get_baseline(self.outsider)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_baseline_access_rejected(self):
        response = self.client.get(f'/api/v1/sprints/{self.sprint.id}/baseline/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    # -- approve ------------------------------------------------------------

    def test_approve_baseline_locks_it_and_advances_sprint(self):
        self._make_fact(confidence_score=0.8)
        self._get_baseline(self.admin)

        self._auth(self.admin)
        response = self.client.post(
            f'/api/v1/sprints/{self.sprint.id}/baseline/approve/', {'comments': 'Looks solid.'},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], Baseline.Status.APPROVED)
        self.assertEqual(response.data['comments'], 'Looks solid.')
        self.assertIsNotNone(response.data['approved_at'])

        self.sprint.refresh_from_db()
        self.assertEqual(self.sprint.status, Sprint.Status.BASELINE_APPROVED)

    def test_cannot_approve_with_unresolved_blocking_gap(self):
        self._make_fact(confidence_score=0.8)
        self._make_gap(title='Blocking', priority=GapItem.Priority.BLOCKING)
        self.sprint.status = Sprint.Status.REVIEWING
        self.sprint.save(update_fields=['status'])
        self._get_baseline(self.admin)

        self._auth(self.admin)
        response = self.client.post(f'/api/v1/sprints/{self.sprint.id}/baseline/approve/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        self.sprint.refresh_from_db()
        self.assertEqual(self.sprint.status, Sprint.Status.BASELINE_PENDING)

    def test_cannot_re_approve_an_already_approved_baseline(self):
        self._make_fact(confidence_score=0.8)
        self._get_baseline(self.admin)
        self._auth(self.admin)
        self.client.post(f'/api/v1/sprints/{self.sprint.id}/baseline/approve/')

        response = self.client.post(f'/api/v1/sprints/{self.sprint.id}/baseline/approve/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_approving_baseline_locks_score_recalculation(self):
        self._make_fact(confidence_score=0.8)
        self._get_baseline(self.admin)
        self._auth(self.admin)
        self.client.post(f'/api/v1/sprints/{self.sprint.id}/baseline/approve/')

        response = self.client.post(f'/api/v1/sprints/{self.sprint.id}/score/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # -- approve provisionally ------------------------------------------------

    def test_approve_provisional_allowed_with_blocking_gap(self):
        self._make_fact(confidence_score=0.8)
        self._make_gap(title='Blocking', priority=GapItem.Priority.BLOCKING)
        self._get_baseline(self.admin)

        self._auth(self.admin)
        response = self.client.post(
            f'/api/v1/sprints/{self.sprint.id}/baseline/approve-provisional/', {'comments': 'Proceeding anyway.'},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], Baseline.Status.PROVISIONAL)

        self.sprint.refresh_from_db()
        self.assertEqual(self.sprint.status, Sprint.Status.BASELINE_APPROVED)

    # -- return for correction -------------------------------------------------

    def test_return_requires_comments(self):
        self._make_fact(confidence_score=0.8)
        self._get_baseline(self.admin)
        self._auth(self.admin)
        response = self.client.post(f'/api/v1/sprints/{self.sprint.id}/baseline/return/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_return_for_correction_sends_sprint_back_to_reviewing(self):
        self._make_fact(confidence_score=0.8)
        self._get_baseline(self.admin)

        self._auth(self.admin)
        response = self.client.post(
            f'/api/v1/sprints/{self.sprint.id}/baseline/return/', {'comments': 'Faculty count looks wrong.'},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], Baseline.Status.RETURNED)

        self.sprint.refresh_from_db()
        self.assertEqual(self.sprint.status, Sprint.Status.REVIEWING)

    def test_new_baseline_submitted_after_return_is_a_new_row(self):
        self._make_fact(confidence_score=0.8)
        first = self._get_baseline(self.admin)
        first_id = first.data['baseline']['id']

        self._auth(self.admin)
        self.client.post(f'/api/v1/sprints/{self.sprint.id}/baseline/return/', {'comments': 'Needs work.'})
        self.client.post(f'/api/v1/sprints/{self.sprint.id}/score/')

        second = self._get_baseline(self.admin)
        self.assertNotEqual(first_id, second.data['baseline']['id'])
        self.assertEqual(Baseline.objects.filter(sprint=self.sprint).count(), 2)
        # The original, returned baseline is never mutated into the new one.
        original = Baseline.objects.get(id=first_id)
        self.assertEqual(original.status, Baseline.Status.RETURNED)

    # -- audit trail ------------------------------------------------------------

    def test_every_decision_is_recorded_in_history(self):
        self._make_fact(confidence_score=0.8)
        self._get_baseline(self.admin)
        self._auth(self.admin)
        self.client.post(f'/api/v1/sprints/{self.sprint.id}/baseline/approve/', {'comments': 'Good.'})

        baseline = Baseline.objects.get(sprint=self.sprint)
        actions = list(
            BaselineDecisionHistory.objects.filter(baseline=baseline).order_by('created_at')
            .values_list('action', flat=True),
        )
        self.assertEqual(
            actions, [BaselineDecisionHistory.Action.SUBMITTED, BaselineDecisionHistory.Action.APPROVED],
        )
