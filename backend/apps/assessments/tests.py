import os
import shutil
import tempfile
from datetime import date
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.benchmarks.models import ApplicabilityRule, Benchmark, InstitutionType
from apps.benchmarks.services import evidence_rules, releases
from apps.benchmarks.tests import PASSWORD, RULE, _LinkFixture, make_ready
from apps.institutions.models import Institution

from . import services as svc
from .models import AssessmentCycle, EvidenceItem, ScoringModel

L2_RULE = {**RULE, 'level': 'L2', 'title': 'Similarity-check reports for theses', 'minimum_count': 2,
           'minimum_currency_months': None}
L1_RULE = {**RULE, 'level': 'L1', 'title': 'Annual academic-integrity outcome review', 'minimum_currency_months': None}
GOOD_REVIEW = {'decision': 'accepted', 'relevance_score': 90, 'completeness_score': 80, 'currency_score': 100,
               'authenticity_score': 90, 'scope_score': 90}  # quality 90


class _AssessmentFixture(_LinkFixture):
    """A published Release 1.0 with ACA-05 (engineering colleges) and GOV-01 (polytechnics only)."""

    def setUp(self):
        super().setUp()
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=self.media)
        override.enable()
        self.addCleanup(override.disable)
        self.aca = Benchmark.objects.get(benchmark_code='ACA-05')
        self.gov = Benchmark.objects.get(benchmark_code='GOV-01')
        make_ready(self.aca, self.user, self.req)
        evidence_rules.create_rule(self.user, L2_RULE, benchmark=self.aca)
        evidence_rules.create_rule(self.user, L1_RULE, benchmark=self.aca)
        make_ready(self.gov, self.user, self.req)
        ApplicabilityRule.objects.get(benchmark=self.gov).institution_types.set(
            [InstitutionType.objects.get(code='polytechnic')])
        self.boss = User.objects.create_user(email='boss@ingage.ai', username='boss', password=PASSWORD, role='super_admin')
        self.release = self._publish()
        self.college = Institution.objects.create(name='MKCE', city='Karur', state='TN')
        self.other = Institution.objects.create(name='Other College', city='Salem', state='TN')
        self.admin = User.objects.create_user(email='iqac@mkce.edu', username='iqac', password=PASSWORD,
                                              role='institution_admin', institution=self.college)
        svc.save_profile(self.college, self.user, {
            'institution_type': 'engineering', 'autonomous_status': 'autonomous', 'approval_bodies': ['AICTE'],
            'programmes': [{'programme_type': 'ug_engineering', 'name': 'B.E. CSE', 'approval_body': 'NBA'}]})

    def _publish(self, label='Release 1.0'):
        from apps.benchmarks.tests import confirm_current
        rel = releases.create_release(label, self.user)
        for b in (self.aca, self.gov):
            confirm_current(b, self.user)  # the fixture edits them after make_ready
            releases.add_item(rel, b, self.user)
        releases.submit(rel, self.user)
        releases.approve(rel, self.boss)
        return releases.publish(rel, self.boss)

    def cycle(self, opens_on=date(2026, 7, 1)):
        return svc.create_cycle(self.college, self.user, 'AI readiness 2026-27', opens_on)

    def ab(self, cycle, code='ACA-05'):
        return cycle.benchmarks.select_related('release_item', 'benchmark').get(benchmark__benchmark_code=code)

    def upload(self, ab, rule, title='Policy', issued_on=date(2026, 1, 10), by=None):
        f = SimpleUploadedFile('policy.pdf', b'%PDF-1.4 integrity policy', content_type='application/pdf')
        return svc.submit_evidence(ab, by or self.admin, {'rule_key': svc.rule_key({**rule, 'level': rule.get('level', '')}),
                                                          'title': title, 'issued_on': issued_on}, f)


class CycleTests(_AssessmentFixture, TestCase):
    def test_applicability_comes_from_the_profile_with_reasons(self):
        c = self.cycle()
        self.assertEqual(c.release, self.release)
        self.assertEqual(c.profile_snapshot['programme_types'], ['ug_engineering'])
        self.assertEqual(sorted(c.profile_snapshot['approval_bodies']), ['AICTE', 'NBA'])
        aca, gov = self.ab(c), self.ab(c, 'GOV-01')
        self.assertEqual((aca.included, aca.applicability_result), (True, 'applies'))
        self.assertEqual((gov.included, gov.applicability_result), (False, 'does_not_apply'))
        self.assertIn('needs institution type is Polytechnic', gov.applicability_reason['reason'])

    def test_needs_a_published_release_and_a_profile(self):
        AssessmentCycle.objects.all().delete()
        self.release.status = 'retired'
        self.release.save(update_fields=['status'])
        with self.assertRaisesMessage(svc.AssessmentError, 'No benchmark release has been published'):
            self.cycle()
        self.release.status = 'published'
        self.release.save(update_fields=['status'])
        with self.assertRaisesMessage(svc.AssessmentError, 'no benchmark profile'):
            svc.create_cycle(self.other, self.user, 'x', '2026-07-01')

    def test_later_draft_edits_never_change_who_is_assessed(self):
        self.aca.refresh_from_db()
        releases.reopen_benchmark(self.aca, self.user, 'Next version')
        ApplicabilityRule.objects.get(benchmark=self.aca).institution_types.set(
            [InstitutionType.objects.get(code='polytechnic')])
        self.assertTrue(self.ab(self.cycle()).included)  # still the published rule (engineering)

    def test_going_against_the_rules_needs_a_note_and_undecided_blocks_opening(self):
        c = self.cycle()
        gov = self.ab(c, 'GOV-01')
        with self.assertRaisesMessage(svc.AssessmentError, 'add a note'):
            svc.decide_benchmark(gov, self.user, included=True)
        gov.included = None
        gov.save()
        with self.assertRaisesMessage(svc.AssessmentError, 'Decide whether'):
            svc.open_cycle(c, self.user)
        svc.decide_benchmark(gov, self.user, included=False, note='Not relevant this year')
        svc.open_cycle(c, self.user)
        self.assertEqual(c.status, 'in_progress')


class ScoringTests(_AssessmentFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.c = self.cycle()
        svc.open_cycle(self.c, self.user)
        self.aca_ab = self.ab(self.c)

    def _score(self):
        svc.score_cycle(self.c, self.user)
        return self.ab(self.c).assessment

    def test_foundational_level_and_the_four_scores(self):
        svc.review_evidence(self.upload(self.aca_ab, RULE), self.user, GOOD_REVIEW)
        svc.submit_cycle(self.c, self.admin)
        a = self._score()
        self.assertEqual((a.computed_level, a.current_level), ('L3', 'L3'))
        self.assertEqual(a.compliance_score, Decimal('100.00'))
        self.assertEqual(a.maturity_score, Decimal('33.33'))
        self.assertEqual(a.evidence_confidence_score, Decimal('90.00'))
        self.assertIsNone(a.outcome_score)
        self.assertIsNone(a.composite_score)
        # Released benchmarks have approved weights (a release gate); the composite then waits for the outcome.
        self.assertIn('Waiting for: outcome', a.detail['composite'])
        self.assertIn('L2 not reached: missing Similarity-check reports', a.detail['level_notes'][0])
        from .models import BenchmarkScoreRule
        BenchmarkScoreRule.objects.filter(benchmark=self.aca).delete()  # weights withdrawn later
        self.assertIn('not approved weights', self._score().detail['composite'])

    def test_an_assessment_never_changes_the_sprint_cri(self):
        from apps.scoring.models import ScoringRun
        from apps.sprints.models import Sprint
        sprint = Sprint.objects.create(institution=self.college, mode=Sprint.SprintMode.VERIFIED_CRI)
        Sprint.objects.filter(pk=sprint.pk).update(overall_cri=41.5, confidence_score=0.7)
        runs = ScoringRun.objects.count()
        svc.review_evidence(self.upload(self.aca_ab, RULE), self.user, GOOD_REVIEW)
        svc.submit_cycle(self.c, self.admin)
        self.assertIsNotNone(self._score().compliance_score)  # the assessment was scored...
        sprint.refresh_from_db()
        self.assertEqual((sprint.overall_cri, sprint.confidence_score), (41.5, 0.7))  # ...the CRI was not touched
        self.assertEqual(ScoringRun.objects.count(), runs)

    def test_levels_build_up_and_composite_needs_approved_weights_and_outcome(self):
        for rule, n in ((RULE, 1), (L2_RULE, 2), (L1_RULE, 1)):
            for i in range(n):
                svc.review_evidence(self.upload(self.aca_ab, rule, f'{rule["title"]} {i}'), self.user, GOOD_REVIEW)
        svc.submit_cycle(self.c, self.admin)
        with self.assertRaisesMessage(svc.AssessmentError, 'add up to 1'):
            svc.set_score_rule(self.aca, self.user, {'compliance_weight': 0.5, 'maturity_weight': 0.5,
                                                     'evidence_weight': 0.5, 'outcome_weight': 0, 'note': 'x'})
        svc.set_score_rule(self.aca, self.user, {'compliance_weight': '0.25', 'maturity_weight': '0.25',
                                                 'evidence_weight': '0.25', 'outcome_weight': '0.25',
                                                 'note': 'Approved by the benchmark owner'})
        a = self._score()
        self.assertEqual(a.current_level, 'L1')
        self.assertIsNone(a.composite_score)
        self.assertIn('Waiting for: outcome', a.detail['composite'])
        svc.update_assessment(self.ab(self.c), self.user, {'outcome_score': 60, 'outcome_note': 'Similarity index fell'})
        a.refresh_from_db()
        # 0.25 x (100 + 100 + 90 + 60)
        self.assertEqual(a.composite_score, Decimal('87.50'))
        self.assertEqual(a.weights['outcome'], '0.2500')

    def test_old_expired_or_unreviewed_evidence_does_not_count(self):
        old = self.upload(self.aca_ab, RULE, 'Old policy', issued_on=date(2020, 1, 1))
        undated = self.upload(self.aca_ab, RULE, 'Undated policy', issued_on=None)
        for item in (old, undated):
            svc.review_evidence(item, self.user, GOOD_REVIEW)
        svc.submit_cycle(self.c, self.admin)
        a = self._score()
        self.assertEqual((a.current_level, a.compliance_score), ('', Decimal('0.00')))
        notes = a.detail['requests'][0]['notes'] + a.detail['requests'][1]['notes'] + a.detail['requests'][2]['notes']
        self.assertTrue(any('older than 36 months' in n for n in notes))
        self.assertTrue(any('issue date missing' in n for n in notes))

    def test_review_rules(self):
        mine = self.upload(self.aca_ab, RULE, by=self.user)
        with self.assertRaisesMessage(svc.AssessmentError, 'someone other than'):
            svc.review_evidence(mine, self.user, GOOD_REVIEW)
        item = self.upload(self.aca_ab, RULE)
        with self.assertRaisesMessage(svc.AssessmentError, 'Tell the college why'):
            svc.review_evidence(item, self.user, {**GOOD_REVIEW, 'decision': 'rejected'})
        svc.submit_cycle(self.c, self.admin)
        with self.assertRaisesMessage(svc.AssessmentError, 'still waiting for review'):
            svc.score_cycle(self.c, self.user)

    def test_finalize_freezes_and_needs_fresh_scores(self):
        item = self.upload(self.aca_ab, RULE)
        svc.review_evidence(item, self.user, GOOD_REVIEW)
        svc.submit_cycle(self.c, self.admin)
        self._score()
        svc.review_evidence(item, self.boss, {**GOOD_REVIEW, 'scope_score': 40})
        with self.assertRaises(svc.AssessmentError) as ctx:
            svc.finalize_cycle(self.c, self.user)
        self.assertIn('score again', ctx.exception.problems[0])
        self._score()
        svc.finalize_cycle(self.c, self.user)
        self.assertEqual(self.c.status, 'finalized')
        for fn in (lambda: svc.score_cycle(self.c, self.user),
                   lambda: svc.update_assessment(self.ab(self.c), self.user, {'outcome_score': 10, 'outcome_note': 'x'}),
                   lambda: svc.review_evidence(item, self.boss, GOOD_REVIEW)):
            with self.assertRaises(svc.AssessmentError):
                fn()


class AssessmentApiTests(_AssessmentFixture, APITestCase):
    def _login(self, email):
        token = self.client.post('/api/v1/auth/login/', {'email': email, 'password': PASSWORD}).data['access_token']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

    def test_college_and_staff_flow(self):
        self._login('x@ingage.ai')
        r = self.client.post('/api/v1/assessments/cycles', {'institution': str(self.college.pk), 'name': 'Pilot',
                                                            'opens_on': '2026-07-01'}, format='json')
        self.assertEqual(r.status_code, 201)
        cid = r.data['id']
        self.assertEqual(r.data['release_label'], 'Release 1.0')
        self.assertEqual(self.client.post(f'/api/v1/assessments/cycles/{cid}/open').data['status'], 'in_progress')

        self._login('iqac@mkce.edu')
        self.assertEqual(self.client.post('/api/v1/assessments/cycles', {'institution': str(self.college.pk),
                                                                        'name': 'x'}, format='json').status_code, 403)
        detail = self.client.get(f'/api/v1/assessments/cycles/{cid}/benchmarks/ACA-05').data
        self.assertEqual(len(detail['requests']), 3)
        self.assertIsNone(detail['preview'])  # staff only
        key = detail['requests'][0]['key']
        up = self.client.post(f'/api/v1/assessments/cycles/{cid}/benchmarks/ACA-05/evidence',
                              {'rule_key': key, 'title': 'Integrity policy', 'issued_on': '2026-01-10',
                               'file': SimpleUploadedFile('p.pdf', b'%PDF-1.4 x', content_type='application/pdf')},
                              format='multipart')
        self.assertEqual((up.status_code, up.data['status']), (201, 'submitted'))
        self.assertEqual(len(up.data['file_sha256']), 64)
        bad = self.client.post(f'/api/v1/assessments/cycles/{cid}/benchmarks/ACA-05/evidence',
                               {'rule_key': key, 'title': 'x', 'file': SimpleUploadedFile('x.exe', b'MZ')}, format='multipart')
        self.assertIn('not accepted', bad.data['detail'])
        self.assertEqual(self.client.get(f'/api/v1/assessments/evidence/{up.data["id"]}/file').status_code, 200)
        self.assertEqual(self.client.post(f'/api/v1/assessments/evidence/{up.data["id"]}/review', GOOD_REVIEW,
                                          format='json').status_code, 403)
        self.assertEqual(self.client.post(f'/api/v1/assessments/cycles/{cid}/submit').data['status'], 'submitted')
        self.assertEqual(self.client.get(f'/api/v1/assessments/cycles/{cid}/scorecard').status_code, 403)

        self._login('x@ingage.ai')
        self.client.post(f'/api/v1/assessments/evidence/{up.data["id"]}/review', GOOD_REVIEW, format='json')
        self.assertEqual(self.client.post(f'/api/v1/assessments/cycles/{cid}/score').data['status'], 'reviewed')
        self.assertEqual(self.client.post(f'/api/v1/assessments/cycles/{cid}/finalize').data['status'], 'finalized')

        self._login('iqac@mkce.edu')
        card = self.client.get(f'/api/v1/assessments/cycles/{cid}/scorecard').data
        [row] = card['benchmarks']
        self.assertEqual((row['benchmark_code'], row['assessment']['current_level']), ('ACA-05', 'L3'))
        self.assertEqual(card['scoring_model']['code'], 'BM-SCORE-1')
        self.assertEqual(card['release_hash'], self.release.content_hash)

    def test_colleges_only_see_their_own(self):
        c = self.cycle()
        outsider = User.objects.create_user(email='a@other.edu', username='o', password=PASSWORD,
                                            role='institution_admin', institution=self.other)
        self._login('a@other.edu')
        self.assertEqual(self.client.get(f'/api/v1/assessments/cycles/{c.pk}').status_code, 403)
        self.assertEqual(self.client.get('/api/v1/assessments/cycles').data, [])
        self.assertEqual(self.client.put(f'/api/v1/assessments/institutions/{self.other.pk}/profile',
                                         {'institution_type': 'iti'}, format='json').status_code, 403)
        self.assertTrue(outsider.pk)

    def test_viewers_cannot_upload(self):
        c = self.cycle()
        svc.open_cycle(c, self.user)
        User.objects.create_user(email='v@mkce.edu', username='v', password=PASSWORD, role='viewer',
                                 institution=self.college)
        self._login('v@mkce.edu')
        r = self.client.post(f'/api/v1/assessments/cycles/{c.pk}/benchmarks/ACA-05/evidence', {'title': 'x'},
                             format='multipart')
        self.assertEqual(r.status_code, 403)

    def test_scoring_model_is_seeded_and_active(self):
        self.assertTrue(ScoringModel.objects.filter(code='BM-SCORE-1', active=True).exists())
        self.assertFalse(EvidenceItem.objects.exists())
        self.assertTrue(os.path.isdir(self.media))


# -- Stage 6: improvement plan ------------------------------------------------------------
from . import plan  # noqa: E402
from .models import AssessmentGap, Initiative, Task, TransformationTemplate  # noqa: E402


class _FinalizedFixture(_AssessmentFixture):
    """ACA-05 reaches L3 (target L2) with outcome 60, then the cycle is finalized."""

    def setUp(self):
        super().setUp()
        self.c = self.cycle()
        svc.open_cycle(self.c, self.user)
        self.item = self.upload(self.ab(self.c), RULE)
        svc.review_evidence(self.item, self.user, GOOD_REVIEW)
        svc.submit_cycle(self.c, self.admin)
        svc.score_cycle(self.c, self.user)
        svc.update_assessment(self.ab(self.c), self.user, {'outcome_score': 60, 'outcome_note': 'Similarity index 18%'})
        svc.finalize_cycle(self.c, self.user)
        self.c.refresh_from_db()


class PlanTests(_FinalizedFixture, TestCase):
    def test_plan_needs_a_finalized_cycle(self):
        other = self.cycle()
        with self.assertRaisesMessage(plan.PlanError, 'finalized'):
            plan.generate_plan(other, self.user)

    def test_gaps_initiatives_and_tasks_follow_the_scores(self):
        made = plan.generate_plan(self.c, self.user)
        gaps = {g.gap_type: g for g in AssessmentGap.objects.all()}
        self.assertEqual(set(gaps), {'capability', 'outcome'})  # L3 vs target L2; outcome 60 < 70; compliance 100
        self.assertEqual(gaps['capability'].severity, 'medium')
        self.assertIn('reached L3, target L2', gaps['capability'].description)
        self.assertEqual(gaps['outcome'].severity, 'medium')
        ini = gaps['capability'].initiatives.get()
        self.assertEqual([t.title for t in ini.tasks.all()], ['Provide: Similarity-check reports for theses (L2)'])
        self.assertEqual((ini.target_date - self.c.finalized_at.date()).days, 90)
        self.assertEqual(made, {'gaps': 2, 'initiatives': 2, 'tasks': 2})
        with self.assertRaisesMessage(plan.PlanError, 'already has a plan'):
            plan.generate_plan(self.c, self.user)

    def test_template_shapes_the_initiative(self):
        TransformationTemplate.objects.create(
            benchmark=self.aca, gap_type='capability', title='Run similarity checks on every thesis',
            intervention='Adopt a similarity tool and route every thesis through it.',
            expected_evidence='Similarity reports for all theses of the year',
            expected_outcome='Average similarity below 10%', tasks=['Buy licence', 'Train guides', 'Check theses'])
        plan.generate_plan(self.c, self.user)
        ini = AssessmentGap.objects.get(gap_type='capability').initiatives.get()
        self.assertEqual(ini.title, 'Run similarity checks on every thesis')
        self.assertEqual([t.title for t in ini.tasks.all()], ['Buy licence', 'Train guides', 'Check theses'])

    def test_gap_closes_only_with_accepted_evidence(self):
        plan.generate_plan(self.c, self.user)
        gap = AssessmentGap.objects.get(gap_type='capability')
        with self.assertRaisesMessage(plan.PlanError, 'after accepted evidence'):
            plan.set_gap_status(gap, self.user, 'closed')
        plan.set_gap_status(gap, self.user, 'in_progress')
        pending = EvidenceItem.objects.create(
            cycle=self.c, applicable=self.ab(self.c), rule_key='x', evidence_type=self.item.evidence_type,
            title='Draft report', source_url='https://x.edu/r', submitted_by=self.admin)
        with self.assertRaisesMessage(plan.PlanError, 'Only accepted evidence'):
            plan.validate_gap(gap, self.user, pending, 'n')
        with self.assertRaisesMessage(plan.PlanError, 'Say how'):
            plan.validate_gap(gap, self.user, self.item, '')
        plan.validate_gap(gap, self.user, self.item, 'Reports for all 2026 theses accepted.')
        plan.set_gap_status(gap, self.user, 'closed')
        gap.refresh_from_db()
        self.assertEqual((gap.status, gap.closing_evidence), ('closed', self.item))
        with self.assertRaisesMessage(plan.PlanError, 'cannot be reopened'):
            plan.set_gap_status(gap, self.user, 'open')


class PlanApiTests(_FinalizedFixture, APITestCase):
    def _login(self, email):
        token = self.client.post('/api/v1/auth/login/', {'email': email, 'password': PASSWORD}).data['access_token']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

    def test_staff_generate_college_runs_the_tasks(self):
        url = f'/api/v1/assessments/cycles/{self.c.pk}/plan'
        self._login('iqac@mkce.edu')
        self.assertEqual(self.client.post(url).status_code, 403)
        self._login('x@ingage.ai')
        r = self.client.post(url)
        self.assertEqual((r.status_code, r.data['summary']['gaps']), (201, 2))
        self._login('iqac@mkce.edu')
        plan_data = self.client.get(url).data
        task = plan_data['gaps'][0]['initiatives'][0]['tasks'][0]
        r = self.client.patch(f'/api/v1/assessments/tasks/{task["id"]}',
                              {'status': 'active', 'owner': 'IQAC coordinator', 'due_date': '2026-12-31'}, format='json')
        self.assertEqual((r.status_code, r.data['status'], r.data['owner']), (200, 'active', 'IQAC coordinator'))
        ini = plan_data['gaps'][0]['initiatives'][0]['id']
        r = self.client.post(f'/api/v1/assessments/initiatives/{ini}/tasks', {'title': 'Brief the HoDs'}, format='json')
        self.assertEqual(r.status_code, 201)
        gap = plan_data['gaps'][0]['id']
        self.assertEqual(self.client.patch(f'/api/v1/assessments/gaps/{gap}', {'status': 'planned'},
                                           format='json').status_code, 403)  # gap decisions are staff-only
        User.objects.create_user(email='v@mkce.edu', username='v', password=PASSWORD, role='viewer',
                                 institution=self.college)
        self._login('v@mkce.edu')
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.patch(f'/api/v1/assessments/tasks/{task["id"]}', {'status': 'complete'},
                                           format='json').status_code, 403)

    def test_templates_are_staff_only(self):
        self._login('x@ingage.ai')
        r = self.client.post('/api/v1/assessments/templates', {
            'benchmark_code': 'ACA-05', 'gap_type': 'outcome', 'title': 'Lower similarity',
            'intervention': 'Coach supervisors.', 'expected_evidence': 'Annual similarity report',
            'expected_outcome': 'Similarity under 10%'}, format='json')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(self.client.post('/api/v1/assessments/templates', {
            'benchmark_code': 'ACA-05', 'gap_type': 'outcome', 'title': 'Dup', 'intervention': 'x',
            'expected_evidence': 'x', 'expected_outcome': 'x'}, format='json').status_code, 400)
        self._login('iqac@mkce.edu')
        self.assertEqual(self.client.get('/api/v1/assessments/templates').status_code, 403)


class AuditDocumentEvidenceTests(_AssessmentFixture, APITestCase):
    def test_a_sprint_document_can_be_reused_as_evidence(self):
        from apps.documents.models import Document
        from apps.sprints.models import Sprint
        sprint = Sprint.objects.create(institution=self.college, name='Audit 2026')
        doc = Document.objects.create(sprint=sprint, document_type='naac_ssr', title='SSR 2026',
                                      original_filename='ssr.pdf', checksum='b' * 64,
                                      file=SimpleUploadedFile('ssr.pdf', b'%PDF-1.4 ssr'))
        c = self.cycle()
        svc.open_cycle(c, self.user)
        token = self.client.post('/api/v1/auth/login/', {'email': 'iqac@mkce.edu', 'password': PASSWORD}).data['access_token']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        listed = self.client.get(f'/api/v1/assessments/cycles/{c.pk}/sprint-documents').data
        self.assertEqual([d['id'] for d in listed], [str(doc.pk)])
        key = svc.rule_key({**RULE, 'level': ''})
        r = self.client.post(f'/api/v1/assessments/cycles/{c.pk}/benchmarks/ACA-05/evidence',
                             {'rule_key': key, 'title': 'SSR section 2.5', 'sprint_document': str(doc.pk),
                              'issued_on': '2026-01-10'}, format='multipart')
        self.assertEqual((r.status_code, r.data['from_audit'], r.data['has_file']), (201, True, True))
        self.assertEqual(r.data['file_sha256'], 'b' * 64)
        self.assertEqual(self.client.get(f'/api/v1/assessments/evidence/{r.data["id"]}/file').status_code, 200)
        other = Institution.objects.create(name='Other', city='X', state='TN')
        foreign = Document.objects.create(sprint=Sprint.objects.create(institution=other), document_type='aqar',
                                          file=SimpleUploadedFile('a.pdf', b'%PDF a'), checksum='c' * 64)
        r = self.client.post(f'/api/v1/assessments/cycles/{c.pk}/benchmarks/ACA-05/evidence',
                             {'rule_key': key, 'title': 'x', 'sprint_document': str(foreign.pk)}, format='multipart')
        self.assertIn('not found for this college', r.data['detail'])
