from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.facts.models import ExtractedFact
from apps.gaps.models import GapItem
from apps.institutions.models import Institution
from apps.recommendations.models import Recommendation
from apps.recommendations.services import generate_recommendations_for_sprint
from apps.sprints.models import Sprint

from .models import Report
from .services import build_report_data, next_report_version
from .tasks import generate_report_task

PASSWORD = 'Str0ng!DevPassw0rd'


class ReportsTestBase(APITestCase):
    def setUp(self):
        self.institution = Institution.objects.create(name='MKCE', city='Karur', state='TN')
        self.other_institution = Institution.objects.create(name='Other', city='X', state='Y')

        self.admin = self._make_user('admin@test.edu', User.Role.INSTITUTION_ADMIN, self.institution)
        self.viewer = self._make_user('viewer@test.edu', User.Role.VIEWER, self.institution)
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
            'sprint': self.sprint, 'field_name': 'Faculty Certified %', 'field_key': 'faculty_certified_pct',
            'value': 62.5, 'pillar': 'aiqif_c1', 'owner_role': 'registrar',
            'status': ExtractedFact.Status.CONFIRMED, 'confidence_score': 0.8,
        }
        defaults.update(overrides)
        return ExtractedFact.objects.create(**defaults)

    def _make_gap(self, **overrides):
        defaults = {
            'sprint': self.sprint, 'gap_type': GapItem.GapType.MISSING_DOCUMENT, 'title': 'Missing something',
            'pillar': 'aiqif_c1', 'priority': GapItem.Priority.HIGH,
        }
        defaults.update(overrides)
        return GapItem.objects.create(**defaults)


class BuildReportDataTests(ReportsTestBase):
    def test_report_data_reflects_real_scoring_and_evidence(self):
        self._make_fact(confidence_score=0.8)
        data = build_report_data(self.sprint)

        self.assertEqual(data['overall_cri'], 9.6)  # 0.8 confidence * 100 * C1 weight 0.12
        self.assertEqual(len(data['pillar_scorecards']), 9)
        self.assertEqual(data['institution']['name'], 'MKCE')
        self.assertIn('MKCE', data['executive_summary'])

    def test_report_shows_raw_cri_coverage_and_the_adjusted_cri_apart(self):
        from apps.facts.models import FactAIQIFMapping

        from .rendering import _coverage_lines
        fact = self._make_fact(confidence_score=0.8)
        FactAIQIFMapping.objects.create(
            fact=fact, criterion='aiqif_c1', indicator_code='AIQIF-C1.1', reason='Test.', confidence=0.9,
            status=FactAIQIFMapping.Status.MAPPED, review_status=FactAIQIFMapping.ReviewStatus.CONFIRMED)
        data = build_report_data(self.sprint)

        self.assertEqual((data['raw_cri'], data['overall_cri']), (9.6, 9.6))
        self.assertEqual(data['coverage_adjusted_cri'], round(9.6 * 0.03, 2))  # C1.1 = 0.12 / 4 of the weight
        self.assertIn('1 of 36 applicable AI-QIF indicators covered', data['evidence_coverage']['summary'])
        self.assertIn('coverage incomplete', data['evidence_coverage']['summary'])
        lines = _coverage_lines(data)
        self.assertTrue(lines[0].startswith('Coverage-adjusted CRI: 0.3 / 100'))
        self.assertEqual(_coverage_lines({'overall_cri': 50}), [])  # a report made before coverage

    def test_unscored_sprint_still_gets_a_real_computed_score_not_a_placeholder(self):
        data = build_report_data(self.sprint)
        self.assertEqual(data['overall_cri'], 0.0)
        self.assertNotEqual(data['overall_cri'], 58)  # never the frontend's old hardcoded demo score
        self.assertEqual(len(data['pillar_scorecards']), 9)

    def test_missing_data_appendix_lists_open_gaps_ordered_by_priority(self):
        self._make_gap(priority=GapItem.Priority.MEDIUM, title='Medium gap')
        self._make_gap(
            priority=GapItem.Priority.BLOCKING, title='Blocking gap', gap_type=GapItem.GapType.STALE_DATA,
        )
        self._make_gap(priority=GapItem.Priority.BLOCKING, status=GapItem.Status.RESOLVED, title='Resolved gap')

        data = build_report_data(self.sprint)
        titles = [g['title'] for g in data['missing_data_appendix']]
        self.assertEqual(titles, ['Blocking gap', 'Medium gap'])  # resolved excluded, blocking first

    def test_recommendations_and_action_plans_are_populated_from_real_recommendations(self):
        self._make_gap(priority=GapItem.Priority.MEDIUM, title='Medium gap')
        generate_recommendations_for_sprint(self.sprint)
        # Checked directly against the model, not via build_report_data --
        # build_report_data bootstraps CRI scoring as a side effect (see its
        # docstring), and once PillarScore rows exist, an unevidenced
        # pillar's own weakness would start generating extra recommendations
        # on the *next* generate_recommendations_for_sprint call below,
        # contaminating this test's count.
        self.assertEqual(Recommendation.objects.filter(sprint=self.sprint).count(), 0)

        # add blocking + high gaps too, so the 90-day bucket gets real content
        self._make_gap(
            priority=GapItem.Priority.BLOCKING, title='Blocking gap', gap_type=GapItem.GapType.STALE_DATA,
        )
        self._make_gap(priority=GapItem.Priority.HIGH, title='High gap', gap_type=GapItem.GapType.CONFLICT)
        generate_recommendations_for_sprint(self.sprint)
        data = build_report_data(self.sprint)

        self.assertEqual(len(data['recommendations']), 2)
        ninety_day_titles = {item['title'] for bucket in data['ninety_day_action_plan'] for item in bucket['items']}
        self.assertEqual(ninety_day_titles, {'Resolve: Blocking gap', 'Resolve: High gap'})
        self.assertEqual(data['twelve_month_roadmap'], [])

    def test_hidden_recommendation_excluded_from_report(self):
        self._make_gap(priority=GapItem.Priority.BLOCKING)
        rec = generate_recommendations_for_sprint(self.sprint)[0]
        rec.status = 'hidden'
        rec.save(update_fields=['status'])

        data = build_report_data(self.sprint)
        self.assertEqual(data['recommendations'], [])

    def test_how_ingage_can_help_rolls_up_support_offerings(self):
        self._make_gap(priority=GapItem.Priority.BLOCKING)
        generate_recommendations_for_sprint(self.sprint)
        data = build_report_data(self.sprint)
        self.assertEqual(len(data['how_ingage_can_help']), 1)
        self.assertEqual(data['how_ingage_can_help'][0]['recommendation_count'], 1)

    def test_next_report_version_increments_and_never_overwrites(self):
        self.assertEqual(next_report_version(self.sprint), 1)
        Report.objects.create(sprint=self.sprint, version=1)
        self.assertEqual(next_report_version(self.sprint), 2)
        Report.objects.create(sprint=self.sprint, version=2)
        self.assertEqual(next_report_version(self.sprint), 3)


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
class GenerateReportTaskTests(TestCase):
    def setUp(self):
        self.institution = Institution.objects.create(name='MKCE', city='Karur', state='TN')
        self.sprint = Sprint.objects.create(institution=self.institution, mode=Sprint.SprintMode.VERIFIED_CRI)

    def test_task_moves_report_to_ready_with_real_files(self):
        report = Report.objects.create(sprint=self.sprint, version=1)
        generate_report_task.delay(str(report.id))
        report.refresh_from_db()

        self.assertEqual(report.status, Report.Status.READY)
        self.assertIsNotNone(report.generated_at)
        self.assertTrue(report.pdf_file)
        self.assertTrue(report.docx_file)
        self.assertGreater(len(report.report_data['pillar_scorecards']), 0)

        with report.pdf_file.open('rb') as f:
            self.assertTrue(f.read(5).startswith(b'%PDF-'))
        with report.docx_file.open('rb') as f:
            self.assertTrue(f.read(2) == b'PK')  # docx is a zip archive

    def test_task_marks_report_failed_on_render_error(self):
        from unittest.mock import patch

        report = Report.objects.create(sprint=self.sprint, version=1)
        with patch('apps.reports.tasks.render_pdf_bytes', side_effect=RuntimeError('boom')):
            generate_report_task.delay(str(report.id))
        report.refresh_from_db()
        self.assertEqual(report.status, Report.Status.FAILED)
        self.assertIn('error', report.report_data)
        self.assertFalse(report.pdf_file)

    def test_task_advances_sprint_from_baseline_approved_to_report_ready(self):
        self.sprint.status = Sprint.Status.BASELINE_APPROVED
        self.sprint.save(update_fields=['status'])
        report = Report.objects.create(sprint=self.sprint, version=1)
        generate_report_task.delay(str(report.id))
        self.sprint.refresh_from_db()
        self.assertEqual(self.sprint.status, Sprint.Status.REPORT_READY)

    def test_task_does_not_advance_sprint_still_at_scoring(self):
        """A report can be generated before the baseline is decided (it's
        just labeled 'preliminary' -- see ReportContentTests below), but the
        sprint itself shouldn't skip straight from SCORING to REPORT_READY
        without ever passing through baseline approval."""
        self.sprint.status = Sprint.Status.SCORING
        self.sprint.save(update_fields=['status'])
        report = Report.objects.create(sprint=self.sprint, version=1)
        generate_report_task.delay(str(report.id))
        self.sprint.refresh_from_db()
        self.assertEqual(self.sprint.status, Sprint.Status.SCORING)


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
class ReportEndpointTests(ReportsTestBase):
    def test_generate_endpoint_creates_a_ready_report(self):
        self._make_fact(confidence_score=0.8)
        self._auth(self.admin)
        response = self.client.post(f'/api/v1/sprints/{self.sprint.id}/reports/generate/')
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(response.data['version'], 1)
        self.assertEqual(response.data['status'], Report.Status.READY)
        self.assertTrue(response.data['pdf_available'])
        self.assertTrue(response.data['docx_available'])

    def test_generate_endpoint_without_trailing_slash(self):
        self._auth(self.admin)
        response = self.client.post(f'/api/v1/sprints/{self.sprint.id}/reports/generate')
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

    def test_post_to_list_endpoint_also_generates_for_backward_compatibility(self):
        self._auth(self.admin)
        response = self.client.post(f'/api/v1/sprints/{self.sprint.id}/reports')
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(response.data['version'], 1)

    def test_regenerating_creates_a_new_version_without_touching_the_old_one(self):
        self._auth(self.admin)
        first = self.client.post(f'/api/v1/sprints/{self.sprint.id}/reports/generate/')
        second = self.client.post(f'/api/v1/sprints/{self.sprint.id}/reports/generate/')

        self.assertEqual(first.data['version'], 1)
        self.assertEqual(second.data['version'], 2)
        self.assertEqual(Report.objects.filter(sprint=self.sprint).count(), 2)

        first_report = Report.objects.get(sprint=self.sprint, version=1)
        self.assertEqual(first_report.status, Report.Status.READY)  # untouched by the second generation

    def test_get_list_returns_reports_without_the_report_data_blob(self):
        self._auth(self.admin)
        self.client.post(f'/api/v1/sprints/{self.sprint.id}/reports/generate/')
        response = self.client.get(f'/api/v1/sprints/{self.sprint.id}/reports/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertNotIn('report_data', response.data[0])

    def test_get_detail_includes_full_report_data(self):
        self._auth(self.admin)
        created = self.client.post(f'/api/v1/sprints/{self.sprint.id}/reports/generate/')
        response = self.client.get(f"/api/v1/reports/{created.data['id']}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('report_data', response.data)
        self.assertEqual(len(response.data['report_data']['pillar_scorecards']), 9)

    def test_download_pdf(self):
        self._auth(self.admin)
        created = self.client.post(f'/api/v1/sprints/{self.sprint.id}/reports/generate/')
        response = self.client.get(f"/api/v1/reports/{created.data['id']}/download/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        content = b''.join(response.streaming_content)
        self.assertTrue(content.startswith(b'%PDF-'))

    def test_download_docx(self):
        self._auth(self.admin)
        created = self.client.post(f'/api/v1/sprints/{self.sprint.id}/reports/generate/')
        response = self.client.get(f"/api/v1/reports/{created.data['id']}/download/?file=docx")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response['Content-Type'],
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        )

    def test_download_not_ready_returns_404(self):
        report = Report.objects.create(sprint=self.sprint, version=1, status=Report.Status.DRAFT)
        self._auth(self.admin)
        response = self.client.get(f'/api/v1/reports/{report.id}/download/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_viewer_can_view_but_not_generate(self):
        self._auth(self.viewer)
        get_response = self.client.get(f'/api/v1/sprints/{self.sprint.id}/reports/')
        self.assertEqual(get_response.status_code, status.HTTP_200_OK)
        post_response = self.client.post(f'/api/v1/sprints/{self.sprint.id}/reports/generate/')
        self.assertEqual(post_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_outsider_forbidden(self):
        self._auth(self.outsider)
        response = self.client.get(f'/api/v1/sprints/{self.sprint.id}/reports/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_rejected(self):
        response = self.client.get(f'/api/v1/sprints/{self.sprint.id}/reports/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
class ReportRecalculationTests(ReportsTestBase):
    """Every report recalculates the CRI first and keeps its own scoring run."""

    def _generate(self):
        report = Report.objects.create(sprint=self.sprint, version=next_report_version(self.sprint))
        generate_report_task.delay(str(report.id))
        report.refresh_from_db()
        return report

    def _approve_baseline(self):
        from apps.scoring.services.baseline import approve_baseline, get_or_create_pending_baseline
        get_or_create_pending_baseline(self.sprint, triggered_by=self.admin)
        return approve_baseline(self.sprint, user=self.admin)

    def test_each_report_runs_the_engine_and_records_its_own_run(self):
        from apps.scoring.models import ScoringRun
        self._make_fact(confidence_score=0.8)
        first = self._generate()
        self._make_fact(field_key='more', pillar='aiqif_c3', confidence_score=0.9)
        second = self._generate()
        self.assertEqual((first.status, second.status), (Report.Status.READY, Report.Status.READY))
        self.assertNotEqual(first.scoring_run_id, second.scoring_run_id)
        self.assertEqual(ScoringRun.objects.filter(sprint=self.sprint).count(), 2)
        first.refresh_from_db()  # the earlier report keeps its own snapshot
        self.assertEqual(first.overall_cri, first.scoring_run.overall_cri)
        self.assertLess(first.overall_cri, second.overall_cri)
        self.assertEqual(second.report_data['cri_source']['scoring_run_id'], str(second.scoring_run_id))
        self.assertEqual(second.report_data['overall_cri'], second.scoring_run.overall_cri)
        self.assertEqual([p['pillar'] for p in second.report_data['pillar_scorecards']],
                         [p['pillar'] for p in second.scoring_run.pillar_snapshot])

    def test_report_after_approval_is_labelled_when_the_score_differs(self):
        self._make_fact(confidence_score=0.8)
        baseline = self._approve_baseline()
        pinned = (baseline.scoring_run_id, baseline.scoring_run.overall_cri)

        same = self._generate()
        self.assertFalse(same.report_data['cri_source']['differs_from_baseline'])
        self.assertIn('matches', same.report_data['cri_source']['note'])

        self._make_fact(field_key='more', pillar='aiqif_c3', confidence_score=0.9)
        changed = self._generate()
        source = changed.report_data['cri_source']
        self.assertEqual(changed.status, Report.Status.READY)
        self.assertTrue(source['differs_from_baseline'])
        self.assertEqual(source['baseline_cri'], pinned[1])
        self.assertIn('recalculated CRI', source['note'])
        baseline.refresh_from_db()
        self.assertEqual((baseline.scoring_run_id, baseline.scoring_run.overall_cri), pinned)  # never overwritten

    def test_report_before_any_baseline_is_preliminary(self):
        self._make_fact(confidence_score=0.8)
        source = self._generate().report_data['cri_source']
        self.assertFalse(source['differs_from_baseline'])
        self.assertIsNone(source['baseline_cri'])
        self.assertIn('preliminary', source['note'])

    def test_a_scoring_failure_fails_the_report(self):
        from unittest.mock import patch
        self._make_fact(confidence_score=0.8)
        with patch('apps.scoring.services.run_scoring_engine', side_effect=RuntimeError('scoring broke')):
            report = self._generate()
        self.assertEqual(report.status, Report.Status.FAILED)
        self.assertIn('scoring broke', report.report_data['error'])
        self.assertIsNone(report.scoring_run_id)
        self.assertFalse(report.pdf_file)

    def test_api_returns_the_run_and_the_label(self):
        self._make_fact(confidence_score=0.8)
        self._auth(self.admin)
        r = self.client.post(f'/api/v1/sprints/{self.sprint.id}/reports/generate/')
        detail = self.client.get(f'/api/v1/reports/{r.data["id"]}/').data
        self.assertEqual(str(detail['scoring_run_id']), detail['report_data']['cri_source']['scoring_run_id'])
