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
            'pillar': 'aiqif_c1',
            'status': ExtractedFact.Status.CONFIRMED,
            'confidence_score': 0.8,
            'fact_kind': ExtractedFact.FactKind.AI_EVIDENCE,  # only AI evidence covers an indicator
        }
        defaults.update(overrides)
        return ExtractedFact.objects.create(**defaults)

    def _make_gap(self, **overrides):
        defaults = {
            'sprint': self.sprint,
            'gap_type': GapItem.GapType.MISSING_DOCUMENT,
            'title': 'Missing something',
            'pillar': 'aiqif_c1',
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
        pillar_score = PillarScore.objects.get(sprint=self.sprint, pillar__key='aiqif_c1')
        self.assertEqual(pillar_score.raw_score, 70.0)
        self.assertEqual(pillar_score.confidence_score, 0.7)
        self.assertEqual(pillar_score.evidence_count, 2)

    def test_weighted_score_is_raw_score_times_pillar_weight(self):
        self._make_fact(confidence_score=0.8)
        run_scoring_engine(self.sprint)
        pillar_score = PillarScore.objects.get(sprint=self.sprint, pillar__key='aiqif_c1')
        governance = Pillar.objects.get(key='aiqif_c1')
        self.assertEqual(pillar_score.weighted_score, round(pillar_score.raw_score * governance.weight, 2))

    def test_ai_qif_category_tags_do_not_change_any_score(self):
        """A fact's AI-QIF indicator tags are categories only: the CRI scores
        `pillar` (+ `field_key`), so tagging a confirmed aiqif_c1 fact with
        another criterion's indicators moves nothing."""
        from apps.facts.models import FactAIQIFMapping

        fact = self._make_fact(field_key='f1', confidence_score=0.8)
        self._make_fact(field_key='f2', pillar='aiqif_c5', confidence_score=0.6)

        def scores():
            run = run_scoring_engine(self.sprint)
            return run.overall_cri, sorted(
                PillarScore.objects.filter(sprint=self.sprint).values_list('pillar__key', 'raw_score', 'evidence_count'),
            )

        before = scores()
        for code, criterion in (('AIQIF-C5.4', 'aiqif_c5'), ('AIQIF-C9.2', 'aiqif_c9')):
            FactAIQIFMapping.objects.create(
                fact=fact, criterion=criterion, indicator_code=code, reason='Test tag.', confidence=0.95,
                status=FactAIQIFMapping.Status.MAPPED,
            )
        fact.aiqif_mapping_status = ExtractedFact.AIQIFMappingStatus.MAPPED
        fact.save()

        self.assertEqual(scores(), before)

    def test_extracted_but_unreviewed_facts_do_not_count_as_evidence(self):
        self._make_fact(status=ExtractedFact.Status.EXTRACTED, confidence_score=0.99)
        run_scoring_engine(self.sprint)
        pillar_score = PillarScore.objects.get(sprint=self.sprint, pillar__key='aiqif_c1')
        self.assertEqual(pillar_score.evidence_count, 0)
        self.assertEqual(pillar_score.raw_score, 0.0)
        self.assertEqual(pillar_score.status, PillarScore.Status.NOT_STARTED)

    def test_rejected_facts_do_not_count_as_evidence(self):
        self._make_fact(status=ExtractedFact.Status.REJECTED, confidence_score=0.99)
        run_scoring_engine(self.sprint)
        pillar_score = PillarScore.objects.get(sprint=self.sprint, pillar__key='aiqif_c1')
        self.assertEqual(pillar_score.evidence_count, 0)

    def test_facts_and_scores_are_isolated_between_sprints(self):
        other_sprint = Sprint.objects.create(institution=self.institution, mode=Sprint.SprintMode.QUICK_CRI)
        self._make_fact(sprint=other_sprint, field_key='other_sprint_fact', pillar='aiqif_c1')

        run_scoring_engine(self.sprint)
        first_score = PillarScore.objects.get(sprint=self.sprint, pillar__key='aiqif_c1')
        self.assertEqual((first_score.evidence_count, first_score.raw_score), (0, 0.0))

        self._make_fact(field_key='this_sprint_fact', pillar='aiqif_c1', confidence_score=0.6)
        run_scoring_engine(self.sprint)
        first_score.refresh_from_db()
        run_scoring_engine(other_sprint)
        other_score = PillarScore.objects.get(sprint=other_sprint, pillar__key='aiqif_c1')
        self.assertEqual((first_score.evidence_count, first_score.raw_score), (1, 60.0))
        self.assertEqual((other_score.evidence_count, other_score.raw_score), (1, 80.0))

    def test_unresolved_gap_reduces_raw_score_by_fixed_priority_penalty(self):
        self._make_fact(confidence_score=0.95)
        self._make_gap(priority=GapItem.Priority.BLOCKING)
        run_scoring_engine(self.sprint)
        pillar_score = PillarScore.objects.get(sprint=self.sprint, pillar__key='aiqif_c1')
        self.assertEqual(pillar_score.raw_score, 87.0)  # 95 - 8 (blocking penalty)
        self.assertEqual(pillar_score.gap_count, 1)

    def test_resolved_gap_does_not_reduce_score(self):
        self._make_fact(confidence_score=0.95)
        self._make_gap(priority=GapItem.Priority.BLOCKING, status=GapItem.Status.RESOLVED)
        run_scoring_engine(self.sprint)
        pillar_score = PillarScore.objects.get(sprint=self.sprint, pillar__key='aiqif_c1')
        self.assertEqual(pillar_score.raw_score, 95.0)
        self.assertEqual(pillar_score.gap_count, 0)

    def test_blocking_gap_forces_at_risk_status_despite_high_score(self):
        self._make_fact(confidence_score=0.99)
        self._make_gap(priority=GapItem.Priority.BLOCKING)
        run_scoring_engine(self.sprint)
        pillar_score = PillarScore.objects.get(sprint=self.sprint, pillar__key='aiqif_c1')
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
            pillar_score = PillarScore.objects.get(sprint=sprint, pillar__key='aiqif_c1')
            self.assertEqual(pillar_score.status, expected_status, msg=f'confidence={confidence}')

    def test_overall_cri_is_sum_of_pillar_weighted_scores(self):
        self._make_fact(pillar='aiqif_c1', confidence_score=0.8)  # weight .12 -> 9.6
        self._make_fact(
            sprint=self.sprint, field_key='f2', pillar='aiqif_c4', confidence_score=0.5,
        )  # weight .10 -> 5.0
        scoring_run = run_scoring_engine(self.sprint)
        self.assertEqual(scoring_run.overall_cri, 14.6)

    def test_overall_confidence_is_weight_weighted_average_of_pillar_confidence(self):
        self._make_fact(pillar='aiqif_c1', confidence_score=0.8)  # weight .12
        self._make_fact(
            sprint=self.sprint, field_key='f2', pillar='aiqif_c4', confidence_score=0.5,
        )  # weight .10
        scoring_run = run_scoring_engine(self.sprint)
        expected = round(0.8 * 0.12 + 0.5 * 0.10, 4)
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

        governance = Pillar.objects.get(key='aiqif_c1')
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
        self._make_fact(pillar='aiqif_c7', confidence_score=0.9)
        research = Pillar.objects.get(key='aiqif_c7')
        research.is_active = False
        research.save(update_fields=['is_active'])

        scoring_run = run_scoring_engine(self.sprint)
        self.assertFalse(PillarScore.objects.filter(sprint=self.sprint, pillar=research).exists())
        self.assertEqual(scoring_run.overall_cri, 0.0)

    def test_inactive_criterion_excluded_from_pillar_evaluation(self):
        governance = Pillar.objects.get(key='aiqif_c1')
        criterion = PillarCriterion.objects.get(pillar=governance, key='general_evidence')
        criterion.is_active = False
        criterion.save(update_fields=['is_active'])

        self._make_fact(confidence_score=0.9)
        run_scoring_engine(self.sprint)
        pillar_score = PillarScore.objects.get(sprint=self.sprint, pillar=governance)
        self.assertEqual(pillar_score.raw_score, 0.0)
        self.assertEqual(pillar_score.status, PillarScore.Status.NOT_STARTED)

    def test_criterion_scoped_to_specific_fact_field_keys(self):
        governance = Pillar.objects.get(key='aiqif_c1')
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
        governance_snapshot = next(p for p in scoring_run.pillar_snapshot if p['pillar'] == 'aiqif_c1')
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
        self.assertEqual(snapshot['overall_cri'], 9.6)
        self.assertTrue(ScoringRun.objects.filter(sprint=self.sprint).exists())

    def test_bootstrap_false_returns_none_for_a_never_scored_sprint(self):
        self._make_fact(confidence_score=0.8)
        snapshot = build_score_snapshot(self.sprint, bootstrap=False)
        self.assertIsNone(snapshot)
        self.assertFalse(ScoringRun.objects.filter(sprint=self.sprint).exists())

    def test_strengths_and_weaknesses_are_derived_from_pillar_status(self):
        self._make_fact(pillar='aiqif_c1', confidence_score=0.9)  # strong
        run_scoring_engine(self.sprint)
        snapshot = build_score_snapshot(self.sprint)
        strength_keys = [p.pillar.key for p in snapshot['strengths']]
        weakness_keys = [p.pillar.key for p in snapshot['weaknesses']]
        self.assertIn('aiqif_c1', strength_keys)
        self.assertNotIn('aiqif_c1', weakness_keys)
        self.assertIn('aiqif_c4', weakness_keys)  # never evidenced -> not_started

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
        self.assertEqual(response.data['overall_cri'], 9.6)
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
        pillar = next(p for p in response.data['pillar_scores'] if p['pillar'] == 'aiqif_c1')
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
        self.assertEqual(len(response.data['pillar_scores']), 9)
        self.assertEqual(len(response.data['unresolved_blocking_gaps']), 1)

    def test_post_recalculates_and_advances_sprint_status(self):
        self.sprint.status = Sprint.Status.REVIEWING
        self.sprint.save(update_fields=['status'])
        self._make_fact(confidence_score=0.8)

        self._auth(self.admin)
        response = self.client.post(f'/api/v1/sprints/{self.sprint.id}/score/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['overall_cri'], 9.6)

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
        self.assertEqual(len(response.data[0]['pillar_snapshot']), 9)

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
        self.assertEqual(response.data['scorecard']['overall_cri'], 9.6)


class ScoringConfigEndpointTests(ScoringTestBase):
    def test_config_returns_the_nine_active_pillars_from_the_database(self):
        self._auth(self.iqac)
        response = self.client.get('/api/v1/scoring/config')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 9)
        keys = {p['key'] for p in response.data}
        self.assertIn('aiqif_c1', keys)
        self.assertIn('aiqif_c9', keys)

    def test_config_reflects_database_weight_not_a_hardcoded_constant(self):
        governance = Pillar.objects.get(key='aiqif_c1')
        governance.weight = 0.33
        governance.save(update_fields=['weight'])

        self._auth(self.iqac)
        response = self.client.get('/api/v1/scoring/config')
        pillar = next(p for p in response.data if p['key'] == 'aiqif_c1')
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

    def test_score_can_be_recalculated_after_approval_without_touching_the_baseline(self):
        self._make_fact(confidence_score=0.8)
        self._get_baseline(self.admin)
        self._auth(self.admin)
        self.client.post(f'/api/v1/sprints/{self.sprint.id}/baseline/approve/')
        baseline = Baseline.objects.get(sprint=self.sprint)
        pinned = (baseline.scoring_run_id, baseline.scoring_run.overall_cri, baseline.scoring_run.pillar_snapshot)
        runs_before = ScoringRun.objects.filter(sprint=self.sprint).count()
        status_before = Sprint.objects.get(pk=self.sprint.pk).status

        self._make_fact(field_key='more_evidence', confidence_score=0.9, pillar='aiqif_c3')  # data changed
        response = self.client.post(f'/api/v1/sprints/{self.sprint.id}/score/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(ScoringRun.objects.filter(sprint=self.sprint).count(), runs_before + 1)  # new history entry
        self.assertNotEqual(response.data['overall_cri'], pinned[1])

        baseline.refresh_from_db()
        self.assertEqual((baseline.scoring_run_id, baseline.scoring_run.overall_cri, baseline.scoring_run.pillar_snapshot),
                         pinned)  # the approved snapshot is untouched
        self.assertEqual(baseline.status, Baseline.Status.APPROVED)
        self.assertEqual(Sprint.objects.get(pk=self.sprint.pk).status, status_before)
        shown = self.client.get(f'/api/v1/sprints/{self.sprint.id}/baseline/').data['baseline']
        self.assertEqual((shown['overall_cri'], shown['pillar_snapshot']), (pinned[1], pinned[2]))

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


class AiQifPillarTests(ScoringTestBase):
    """The CRI pillars are the 9 AI-QIF criteria; the 8 earlier pillars are kept only as history."""

    def test_active_pillars_are_the_nine_aiqif_criteria_weighing_one(self):
        active = Pillar.objects.filter(is_active=True)
        self.assertEqual(sorted(active.values_list('key', flat=True)), [f'aiqif_c{i}' for i in range(1, 10)])
        self.assertAlmostEqual(sum(active.values_list('weight', flat=True)), 1.0)
        self.assertFalse(Pillar.objects.get(key='governance_strategy').is_active)

    def test_scores_on_retired_pillars_are_not_shown_for_an_open_sprint(self):
        old = Pillar.objects.get(key='governance_strategy')
        PillarScore.objects.create(sprint=self.sprint, pillar=old, raw_score=50, weighted_score=5)
        self._make_fact()
        snapshot = build_score_snapshot(self.sprint)
        self.assertEqual({p.pillar.key for p in snapshot['pillar_scores']}, {f'aiqif_c{i}' for i in range(1, 10)})

    def test_an_approved_sprint_keeps_the_scores_it_was_approved_on(self):
        old = Pillar.objects.get(key='governance_strategy')
        PillarScore.objects.create(sprint=self.sprint, pillar=old, raw_score=50, weighted_score=5)
        ScoringRun.objects.create(sprint=self.sprint, overall_cri=5, overall_confidence=0.5)
        self.sprint.status = Sprint.Status.REPORT_READY
        self.sprint.save(update_fields=['status'])
        snapshot = build_score_snapshot(self.sprint)
        self.assertEqual([p.pillar.key for p in snapshot['pillar_scores']], ['governance_strategy'])


class EvidenceCoverageTests(ScoringTestBase):
    """AI-QIF evidence coverage and the coverage-adjusted CRI (services/coverage.py, AIQIF-COV-1).
    Without a published release the CRI pillar weights split equally over each criterion's four
    indicators: 0.12/4, 0.10/4, 0.13/4, ... (they add up to 1.0)."""

    def _map(self, fact, code, review=None):
        from apps.facts.models import FactAIQIFMapping
        from .constants import AIQIF_INDICATORS
        return FactAIQIFMapping.objects.create(
            fact=fact, criterion=AIQIF_INDICATORS[code][0], indicator_code=code, reason='Test.', confidence=0.9,
            status=FactAIQIFMapping.Status.MAPPED,
            review_status=review or FactAIQIFMapping.ReviewStatus.CONFIRMED,
        )

    def _coverage(self):
        run = run_scoring_engine(self.sprint)
        return run, run.evidence_coverage

    def _release(self, rules_by_code=None, weights=None):
        """Patch in a published release whose items carry these applicability rules / weights, and a profile."""
        from types import SimpleNamespace
        from unittest.mock import patch
        from apps.benchmarks.services.applicability import Profile
        from .constants import AIQIF_INDICATORS
        applies = [{'result': 'applies', 'institution_types': [], 'autonomous_statuses': [], 'programme_types': [],
                    'approval_bodies': [], 'jurisdiction': ''}]
        items = {code: {'benchmark_code': code, 'applicability_rules': (rules_by_code or {}).get(code, applies),
                        'weight': (weights or {}).get(code)}
                 for code in AIQIF_INDICATORS if code not in (rules_by_code or {}) or rules_by_code[code] is not None}
        release = SimpleNamespace(release_label='AI-QIF v1.0', content_hash='abc123')
        for target, value in (('_release_items', (release, items)), ('_profile', Profile(institution_type='engineering'))):
            patcher = patch(f'apps.scoring.services.coverage.{target}', return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    @staticmethod
    def _rule(result):
        return [{'result': result, 'institution_types': [], 'autonomous_statuses': [], 'programme_types': [],
                 'approval_bodies': [], 'jurisdiction': ''}]

    def test_partial_coverage_scales_the_raw_cri_and_never_changes_it(self):
        fact = self._make_fact(confidence_score=0.8)
        other = self._make_fact(field_key='curriculum', pillar='aiqif_c3')
        raw_before = run_scoring_engine(self.sprint).overall_cri
        self._map(fact, 'AIQIF-C1.1')
        self._map(other, 'AIQIF-C3.1')

        run, cov = self._coverage()
        self.assertEqual(run.overall_cri, raw_before)  # the Raw CRI is untouched by coverage
        self.assertEqual((cov['covered_count'], cov['applicable_count']), (2, 36))
        self.assertAlmostEqual(cov['ratio'], 0.12 / 4 + 0.13 / 4)
        self.assertEqual(run.coverage_adjusted_cri, round(run.overall_cri * cov['ratio'], 2))
        self.assertEqual((cov['status'], cov['weights_source']), ('incomplete', 'equal_within_criterion'))
        self.assertEqual(cov['unresolved_applicability_count'], 36)  # no published release yet
        self.assertIn('No benchmark release is published', cov['applicability_note'])
        self.assertEqual(cov['formula_version'], 'AIQIF-COV-1')
        self.assertTrue(run.calculation_version.startswith('2.1+'))

    def test_full_coverage_with_resolved_applicability_is_complete(self):
        from .constants import AIQIF_INDICATORS
        self._release()
        fact = self._make_fact()
        for code in AIQIF_INDICATORS:
            self._map(fact, code)  # one fact may cover several indicators
        run, cov = self._coverage()
        self.assertEqual((cov['covered_count'], cov['applicable_count'], cov['status']), (36, 36, 'complete'))
        self.assertEqual((cov['ratio'], run.coverage_adjusted_cri), (1.0, run.overall_cri))
        self.assertEqual(cov['release_label'], 'AI-QIF v1.0')

    def test_only_explicitly_not_applicable_indicators_are_excluded(self):
        not_c2 = {f'AIQIF-C2.{i}': self._rule('does_not_apply') for i in range(1, 5)}
        self._release({**not_c2, 'AIQIF-C3.1': self._rule('optional'), 'AIQIF-C3.2': self._rule('requires_review'),
                       'AIQIF-C3.3': None})  # C3.3 is not in the release at all
        self._map(self._make_fact(), 'AIQIF-C2.1')  # evidence for an excluded indicator does not count
        _, cov = self._coverage()
        rows = {r['code']: r for r in cov['indicators']}
        self.assertEqual((cov['applicable_count'], cov['excluded_count'], cov['covered_count']), (32, 4, 0))
        self.assertAlmostEqual(cov['applicable_weight'], 1.0 - 0.10)
        self.assertTrue(rows['AIQIF-C3.1']['applicable'])          # optional still counts
        self.assertEqual(rows['AIQIF-C3.2']['applicability'], 'requires_review')
        self.assertTrue(rows['AIQIF-C3.2']['applicable'])          # unresolved, not "not applicable"
        self.assertIn('Not in release', rows['AIQIF-C3.3']['applicability_reason'])
        self.assertEqual(cov['unresolved_applicability_count'], 2)
        self.assertFalse(rows['AIQIF-C2.1']['covered'])

    def test_unreviewed_and_rejected_facts_and_mappings_do_not_count(self):
        from apps.facts.models import FactAIQIFMapping
        Review = FactAIQIFMapping.ReviewStatus
        self._map(self._make_fact(field_key='a', status=ExtractedFact.Status.EXTRACTED), 'AIQIF-C1.1')
        self._map(self._make_fact(field_key='b', status=ExtractedFact.Status.REJECTED), 'AIQIF-C1.2')
        self._map(self._make_fact(field_key='c', status=ExtractedFact.Status.EVIDENCE_REQUESTED), 'AIQIF-C1.3')
        self._map(self._make_fact(field_key='d'), 'AIQIF-C1.4', review=Review.UNREVIEWED)
        self._map(self._make_fact(field_key='e', status=ExtractedFact.Status.CORRECTED), 'AIQIF-C2.1',
                  review=Review.REJECTED)
        run, cov = self._coverage()
        self.assertEqual((cov['covered_count'], cov['ratio'], run.coverage_adjusted_cri), (0, 0.0, 0.0))
        self.assertEqual(cov['mappings_awaiting_review'], 1)  # 'd': a confirmed fact whose tag nobody reviewed

    def test_indicators_are_counted_once_however_many_facts_cover_them(self):
        first = self._make_fact(field_key='a')
        second = self._make_fact(field_key='b', status=ExtractedFact.Status.CORRECTED)
        self._map(first, 'AIQIF-C1.1')
        self._map(second, 'AIQIF-C1.1')
        self._map(second, 'AIQIF-C4.2')
        _, cov = self._coverage()
        rows = {r['code']: r for r in cov['indicators']}
        self.assertEqual(cov['covered_count'], 2)
        self.assertEqual(rows['AIQIF-C1.1']['fact_ids'], sorted([str(first.id), str(second.id)]))
        self.assertAlmostEqual(cov['covered_weight'], 0.12 / 4 + 0.10 / 4)

    def test_release_weights_are_used_only_when_every_indicator_has_one(self):
        from .constants import AIQIF_INDICATORS
        weights = {code: '30' for code in AIQIF_INDICATORS}
        weights['AIQIF-C1.1'] = '60'
        self._release(weights=weights)
        self._map(self._make_fact(), 'AIQIF-C1.1')
        _, cov = self._coverage()
        self.assertEqual(cov['weights_source'], 'release')
        self.assertAlmostEqual(cov['ratio'], 60 / (35 * 30 + 60), places=6)

    def test_a_missing_release_weight_falls_back_to_equal_weights_within_criterion(self):
        self._release(weights={'AIQIF-C1.1': '60'})  # the other 35 have none
        _, cov = self._coverage()
        self.assertEqual(cov['weights_source'], 'equal_within_criterion')

    def test_recalculation_keeps_history_and_the_baseline_pinned(self):
        from .services import approve_baseline, get_or_create_pending_baseline
        fact = self._make_fact()
        self._map(fact, 'AIQIF-C1.1')
        self.sprint.status = Sprint.Status.SCORING
        self.sprint.save(update_fields=['status'])
        baseline = get_or_create_pending_baseline(self.sprint, triggered_by=self.admin)
        approve_baseline(self.sprint, user=self.admin, comments='ok')
        pinned = baseline.scoring_run
        pinned_coverage = dict(pinned.evidence_coverage)

        self._map(fact, 'AIQIF-C9.2')
        later, cov = self._coverage()

        pinned.refresh_from_db()
        self.assertNotEqual(later.id, pinned.id)
        self.assertEqual(pinned.evidence_coverage, pinned_coverage)  # never rewritten
        self.assertEqual((pinned_coverage['covered_count'], cov['covered_count']), (1, 2))
        self.assertEqual(ScoringRun.objects.filter(sprint=self.sprint).count(), 2)

    def test_same_data_same_result(self):
        self._map(self._make_fact(), 'AIQIF-C5.3')
        first, second = run_scoring_engine(self.sprint), run_scoring_engine(self.sprint)
        self.assertEqual(first.evidence_coverage, second.evidence_coverage)
        self.assertEqual(first.coverage_adjusted_cri, second.coverage_adjusted_cri)

    def test_score_api_shows_raw_and_adjusted_apart(self):
        self._map(self._make_fact(), 'AIQIF-C1.1')
        self._auth(self.admin)
        data = self.client.post(f'/api/v1/sprints/{self.sprint.id}/score/').data
        self.assertEqual(data['raw_cri'], data['overall_cri'])
        self.assertEqual(data['coverage_adjusted_cri'], round(data['raw_cri'] * data['evidence_coverage']['ratio'], 2))
        self.assertEqual(data['evidence_coverage']['covered_count'], 1)
        history = self.client.get(f'/api/v1/sprints/{self.sprint.id}/score/history/').data
        rows = history['results'] if isinstance(history, dict) else history
        self.assertIn('coverage_adjusted_cri', rows[0])

    def test_a_run_made_before_coverage_reports_none(self):
        run = run_scoring_engine(self.sprint)
        ScoringRun.objects.filter(id=run.id).update(coverage_adjusted_cri=None, evidence_coverage={})
        snapshot = build_score_snapshot(self.sprint)
        self.assertEqual((snapshot['coverage_adjusted_cri'], snapshot['evidence_coverage']), (None, {}))


class AIQIFMappingReviewTests(ScoringTestBase):
    """A reviewer confirms or rejects the AI's AI-QIF tag on a fact; reprocessing keeps the decision."""

    def setUp(self):
        super().setUp()
        from apps.facts.models import FactAIQIFMapping
        self.fact = self._make_fact()
        self.mapping = FactAIQIFMapping.objects.create(
            fact=self.fact, criterion='aiqif_c1', indicator_code='AIQIF-C1.1', reason='AI.', confidence=0.9,
            status=FactAIQIFMapping.Status.MAPPED)

    def _review(self, decision, code='AIQIF-C1.1'):
        return self.client.post(f'/api/v1/facts/{self.fact.id}/aiqif-mappings/{code}/review',
                                {'decision': decision, 'note': 'Checked the source.'}, format='json')

    def test_a_reviewer_confirms_and_rejects(self):
        expert = self._make_user('expert@ingage.test', User.Role.SUPER_ADMIN, None)
        self._auth(self.iqac)
        self.assertEqual(self._review('confirm').status_code, status.HTTP_403_FORBIDDEN)  # the AI-QIF expert only
        self._auth(expert)
        response = self._review('confirm')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        tag = response.data['aiqif_mappings'][0]
        self.assertEqual((tag['review_status'], tag['reviewed_by'], tag['review_note']),
                         ('confirmed', expert.id, 'Checked the source.'))
        self.assertEqual(self._review('reject').data['aiqif_mappings'][0]['review_status'], 'rejected')
        self.assertEqual(self._review('confirm', code='AIQIF-C9.9').status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self._review('maybe').status_code, status.HTTP_400_BAD_REQUEST)

    def test_viewers_and_other_colleges_cannot_review(self):
        self._auth(self.viewer)
        self.assertEqual(self._review('confirm').status_code, status.HTTP_403_FORBIDDEN)
        self._auth(self.outsider)
        self.assertEqual(self._review('confirm').status_code, status.HTTP_403_FORBIDDEN)
        self.mapping.refresh_from_db()
        self.assertEqual(self.mapping.review_status, 'unreviewed')

    def test_reprocessing_keeps_reviewed_tags_and_replaces_the_rest(self):
        from apps.extraction.services.pipeline import ExtractionPipeline
        from apps.facts.models import FactAIQIFMapping
        self.mapping.review_status = FactAIQIFMapping.ReviewStatus.CONFIRMED
        self.mapping.save()
        FactAIQIFMapping.objects.create(fact=self.fact, criterion='aiqif_c2', indicator_code='AIQIF-C2.1',
                                        reason='Old.', confidence=0.9, status=FactAIQIFMapping.Status.MAPPED)
        ExtractionPipeline._save_aiqif_mappings(self.fact, [
            {'criterion': 'aiqif_c1', 'indicator_code': 'AIQIF-C1.1', 'reason': 'New.', 'confidence': 0.4},
            {'criterion': 'aiqif_c3', 'indicator_code': 'AIQIF-C3.1', 'reason': 'New.', 'confidence': 0.9},
        ])
        tags = {m.indicator_code: m for m in self.fact.aiqif_mappings.all()}
        self.assertEqual(sorted(tags), ['AIQIF-C1.1', 'AIQIF-C3.1'])  # unreviewed C2.1 replaced
        self.assertEqual((tags['AIQIF-C1.1'].review_status, tags['AIQIF-C1.1'].reason), ('confirmed', 'AI.'))
        self.assertEqual(tags['AIQIF-C3.1'].review_status, 'unreviewed')
