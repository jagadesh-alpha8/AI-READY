import uuid
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User, UserGuideState
from apps.documents.models import Document
from apps.extraction.models import ExtractionJob
from apps.facts.models import ExtractedFact
from apps.gaps.models import GapItem
from apps.institutions.models import Department, Institution
from apps.recommendations.models import Recommendation
from apps.reports.models import Report
from apps.scoring.models import Baseline, ScoringRun
from apps.sprints.models import Sprint


class OnboardingGuideTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Institutions
        self.institution_a = Institution.objects.create(
            name='Alpha College of Engineering',
            student_count=1200,
            faculty_count=80,
            digital_maturity_level=3,
        )
        self.institution_b = Institution.objects.create(
            name='Beta Institute of Technology',
            student_count=800,
            faculty_count=50,
        )

        # Users for 3 target roles
        self.super_admin = User.objects.create_user(
            email='super@ingage.in',
            username='super_admin',
            password='Password123!',
            role=User.Role.SUPER_ADMIN,
        )
        self.consultant = User.objects.create_user(
            email='consultant@ingage.in',
            username='consultant',
            password='Password123!',
            role=User.Role.CONSULTANT,
        )
        self.iqac_a = User.objects.create_user(
            email='iqac@alpha.edu',
            username='iqac_alpha',
            password='Password123!',
            role=User.Role.IQAC_COORDINATOR,
            institution=self.institution_a,
        )
        self.iqac_b = User.objects.create_user(
            email='iqac@beta.edu',
            username='iqac_beta',
            password='Password123!',
            role=User.Role.IQAC_COORDINATOR,
            institution=self.institution_b,
        )

        # Sprints
        self.sprint_a = Sprint.objects.create(
            institution=self.institution_a,
            name='Alpha Q1 Audit',
            status=Sprint.Status.COLLECTING,
        )

    def test_first_login_detection_and_dna_status(self):
        """IQAC coordinator logging in detects existing Institution DNA."""
        self.client.force_authenticate(user=self.iqac_a)
        res = self.client.get('/api/v1/auth/guide-status')
        self.assertEqual(res.status_code, 200)
        data = res.data

        self.assertEqual(data['total_steps'], 11)
        step1 = data['steps'][0]
        self.assertEqual(step1['id'], 'institution_dna')
        self.assertEqual(step1['status'], 'completed')
        self.assertEqual(step1['number'], 1)
        self.assertIn('/institution-dna', step1['target_path'])

    def test_sprint_selection_and_progression(self):
        """Selecting sprint_a scopes workflow steps to sprint_a."""
        self.client.force_authenticate(user=self.iqac_a)
        res = self.client.get(f'/api/v1/auth/guide-status?sprint_id={self.sprint_a.id}')
        self.assertEqual(res.status_code, 200)
        data = res.data

        step2 = data['steps'][1]
        self.assertEqual(step2['id'], 'sprint_setup')
        self.assertEqual(step2['status'], 'completed')

        step3 = data['steps'][2]
        self.assertEqual(step3['id'], 'upload_documents')
        self.assertEqual(step3['status'], 'not_started')

        # Current active step should be upload_documents
        self.assertEqual(data['current_step_id'], 'upload_documents')

    def test_upload_and_processing_monitor_needs_attention(self):
        """Documents with partial completeness or unreadable pages flag 'needs_attention'."""
        doc = Document.objects.create(
            sprint=self.sprint_a,
            title='SSR Report.pdf',
            document_type='naac_ssr',
            status=Document.Status.PROCESSED,
        )
        job = ExtractionJob.objects.create(
            sprint=self.sprint_a,
            document=doc,
            status=ExtractionJob.Status.COMPLETED,
            completeness=ExtractionJob.Completeness.PARTIAL,
            unreadable_pages=2,
        )

        self.client.force_authenticate(user=self.iqac_a)
        res = self.client.get(f'/api/v1/auth/guide-status?sprint_id={self.sprint_a.id}')
        self.assertEqual(res.status_code, 200)

        step3 = res.data['steps'][2]
        self.assertEqual(step3['status'], 'completed')

        step4 = res.data['steps'][3]
        self.assertEqual(step4['id'], 'monitor_processing')
        self.assertEqual(step4['status'], 'needs_attention')
        self.assertEqual(res.data['current_step_id'], 'monitor_processing')

    def test_processing_monitor_completed_when_clean(self):
        """When all jobs are complete with 0 unreadable pages, status is completed."""
        doc = Document.objects.create(
            sprint=self.sprint_a,
            title='SSR Report.pdf',
            document_type='naac_ssr',
            status=Document.Status.PROCESSED,
        )
        ExtractionJob.objects.create(
            sprint=self.sprint_a,
            document=doc,
            status=ExtractionJob.Status.COMPLETED,
            completeness=ExtractionJob.Completeness.COMPLETE,
            unreadable_pages=0,
        )

        self.client.force_authenticate(user=self.iqac_a)
        res = self.client.get(f'/api/v1/auth/guide-status?sprint_id={self.sprint_a.id}')
        self.assertEqual(res.status_code, 200)

        step4 = res.data['steps'][3]
        self.assertEqual(step4['status'], 'completed')
        # Advances to step 5 (facts_review)
        self.assertEqual(res.data['current_step_id'], 'facts_review')

    def test_facts_review_in_progress_and_completion(self):
        """Unreviewed facts show in_progress; all confirmed/corrected show completed."""
        doc = Document.objects.create(sprint=self.sprint_a, document_type='naac_ssr')
        f1 = ExtractedFact.objects.create(
            sprint=self.sprint_a, document=doc, field_name='Faculty Count', status=ExtractedFact.Status.EXTRACTED
        )
        self.client.force_authenticate(user=self.iqac_a)

        res = self.client.get(f'/api/v1/auth/guide-status?sprint_id={self.sprint_a.id}')
        step5 = res.data['steps'][4]
        self.assertEqual(step5['status'], 'in_progress')

        # Review the fact
        f1.status = ExtractedFact.Status.CONFIRMED
        f1.save()

        res2 = self.client.get(f'/api/v1/auth/guide-status?sprint_id={self.sprint_a.id}')
        step5_updated = res2.data['steps'][4]
        self.assertEqual(step5_updated['status'], 'completed')

    def test_gaps_review_blocking_needs_attention(self):
        """Blocking gaps mark Gaps Review as needs_attention."""
        GapItem.objects.create(
            sprint=self.sprint_a,
            title='Missing Audit Statement',
            priority=GapItem.Priority.BLOCKING,
            status=GapItem.Status.OPEN,
        )
        self.client.force_authenticate(user=self.iqac_a)
        res = self.client.get(f'/api/v1/auth/guide-status?sprint_id={self.sprint_a.id}')

        step6 = res.data['steps'][5]
        self.assertEqual(step6['id'], 'gaps_evidence')
        self.assertEqual(step6['status'], 'needs_attention')

    def test_skip_step_advances_without_changing_underlying_data(self):
        """Skipping a step marks it as 'skipped', advances to next step, and alters NO underlying records."""
        self.client.force_authenticate(user=self.iqac_a)

        # Baseline: step 3 is upload_documents (not_started)
        res_before = self.client.get(f'/api/v1/auth/guide-status?sprint_id={self.sprint_a.id}')
        self.assertEqual(res_before.data['current_step_id'], 'upload_documents')

        # Counts before skip
        doc_count_before = Document.objects.filter(sprint=self.sprint_a).count()
        fact_count_before = ExtractedFact.objects.filter(sprint=self.sprint_a).count()
        baseline_count_before = Baseline.objects.filter(sprint=self.sprint_a).count()
        report_count_before = Report.objects.filter(sprint=self.sprint_a).count()

        # Skip upload_documents
        res_skip = self.client.post('/api/v1/auth/guide-skip', {
            'step_id': 'upload_documents',
            'sprint_id': str(self.sprint_a.id),
            'skipped': True,
        })
        self.assertEqual(res_skip.status_code, 200)

        step3 = [s for s in res_skip.data['steps'] if s['id'] == 'upload_documents'][0]
        self.assertEqual(step3['status'], 'skipped')
        # Crucial: underlying data untouched!
        self.assertEqual(Document.objects.filter(sprint=self.sprint_a).count(), doc_count_before)
        self.assertEqual(ExtractedFact.objects.filter(sprint=self.sprint_a).count(), fact_count_before)
        self.assertEqual(Baseline.objects.filter(sprint=self.sprint_a).count(), baseline_count_before)
        self.assertEqual(Report.objects.filter(sprint=self.sprint_a).count(), report_count_before)

        # Current step immediately advances past upload_documents
        self.assertNotEqual(res_skip.data['current_step_id'], 'upload_documents')
        self.assertEqual(res_skip.data['current_step_id'], 'monitor_processing')

    def test_skip_persists_across_sessions_and_refreshes(self):
        """Skip state persists across separate requests and user sessions."""
        self.client.force_authenticate(user=self.iqac_a)

        self.client.post('/api/v1/auth/guide-skip', {
            'step_id': 'upload_documents',
            'sprint_id': str(self.sprint_a.id),
            'skipped': True,
        })

        # New request simulating a page refresh
        client2 = APIClient()
        client2.force_authenticate(user=self.iqac_a)
        res = client2.get(f'/api/v1/auth/guide-status?sprint_id={self.sprint_a.id}')
        step3 = [s for s in res.data['steps'] if s['id'] == 'upload_documents'][0]
        self.assertEqual(step3['status'], 'skipped')

    def test_unskip_step_restores_step(self):
        """Un-skipping a step restores its status from real underlying state."""
        self.client.force_authenticate(user=self.iqac_a)
        self.client.post('/api/v1/auth/guide-skip', {
            'step_id': 'upload_documents',
            'sprint_id': str(self.sprint_a.id),
            'skipped': True,
        }, format='json')

        res_unskip = self.client.post('/api/v1/auth/guide-skip', {
            'step_id': 'upload_documents',
            'sprint_id': str(self.sprint_a.id),
            'skipped': False,
        }, format='json')
        step3 = [s for s in res_unskip.data['steps'] if s['id'] == 'upload_documents'][0]
        self.assertEqual(step3['status'], 'not_started')
        self.assertEqual(res_unskip.data['current_step_id'], 'upload_documents')

    def test_sprint_switching_loads_own_guide_progress(self):
        """Switching sprint loads that specific sprint's own progress and skips."""
        sprint_a2 = Sprint.objects.create(
            institution=self.institution_a,
            name='Alpha Sprint 2',
            status=Sprint.Status.COLLECTING,
        )

        self.client.force_authenticate(user=self.iqac_a)
        # Skip step 3 on sprint_a
        self.client.post('/api/v1/auth/guide-skip', {
            'step_id': 'upload_documents',
            'sprint_id': str(self.sprint_a.id),
            'skipped': True,
        })

        # Check sprint_a: upload_documents is skipped
        res_a = self.client.get(f'/api/v1/auth/guide-status?sprint_id={self.sprint_a.id}')
        step3_a = [s for s in res_a.data['steps'] if s['id'] == 'upload_documents'][0]
        self.assertEqual(step3_a['status'], 'skipped')

        # Check sprint_a2: upload_documents is NOT skipped
        res_a2 = self.client.get(f'/api/v1/auth/guide-status?sprint_id={sprint_a2.id}')
        step3_a2 = [s for s in res_a2.data['steps'] if s['id'] == 'upload_documents'][0]
        self.assertEqual(step3_a2['status'], 'not_started')

    def test_dismiss_and_reset_guide(self):
        """Dismissing hides the card; resetting restores all steps."""
        self.client.force_authenticate(user=self.iqac_a)

        res_dismiss = self.client.post('/api/v1/auth/guide-dismiss', {
            'dismissed': True,
            'sprint_id': str(self.sprint_a.id),
        })
        self.assertTrue(res_dismiss.data['is_dismissed'])

        # Reset
        res_reset = self.client.post('/api/v1/auth/guide-reset', {
            'sprint_id': str(self.sprint_a.id),
        })
        self.assertFalse(res_reset.data['is_dismissed'])
        self.assertEqual(res_reset.data['skipped_count'], 0)

    def test_iqac_coordinator_strict_cross_institution_protection(self):
        """IQAC user cannot load another institution's sprint guide progress."""
        self.client.force_authenticate(user=self.iqac_b)
        # Attempt to access sprint_a belonging to Institution A
        res = self.client.get(f'/api/v1/auth/guide-status?sprint_id={self.sprint_a.id}')
        self.assertEqual(res.status_code, 200)
        # The service protects against cross-institution leak: resolves to user's own institution
        self.assertNotEqual(res.data['institution_id'], str(self.institution_a.id))
        self.assertEqual(res.data['institution_id'], str(self.institution_b.id))
        self.assertNotEqual(res.data['sprint_id'], str(self.sprint_a.id))

    def test_menu_tour_update_persists_without_altering_business_data(self):
        """Updating menu tour persists state and never alters underlying business records."""
        self.client.force_authenticate(user=self.iqac_a)

        doc_count_before = Document.objects.filter(sprint=self.sprint_a).count()
        fact_count_before = ExtractedFact.objects.filter(sprint=self.sprint_a).count()
        gap_count_before = GapItem.objects.filter(sprint=self.sprint_a).count()

        res = self.client.post('/api/v1/auth/menu-tour-update', {
            'menu_key': 'sprint-facts',
            'status': 'completed',
            'sprint_id': str(self.sprint_a.id),
        }, format='json')

        self.assertEqual(res.status_code, 200)
        self.assertIn('menu_tours', res.data)
        self.assertEqual(res.data['menu_tours']['sprint-facts']['status'], 'completed')

        # Business data untouched
        self.assertEqual(Document.objects.filter(sprint=self.sprint_a).count(), doc_count_before)
        self.assertEqual(ExtractedFact.objects.filter(sprint=self.sprint_a).count(), fact_count_before)
        self.assertEqual(GapItem.objects.filter(sprint=self.sprint_a).count(), gap_count_before)

    def test_menu_tour_dismissal_persists(self):
        """Dismissing a menu tour marks it dismissed so first-visit offer is not replayed."""
        self.client.force_authenticate(user=self.iqac_a)

        res = self.client.post('/api/v1/auth/menu-tour-update', {
            'menu_key': 'dashboard',
            'status': 'dismissed',
        }, format='json')

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['menu_tours']['dashboard']['status'], 'dismissed')
