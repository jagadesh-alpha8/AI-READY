from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.facts.models import ExtractedFact
from apps.gaps.models import GapItem
from apps.institutions.models import Institution
from apps.reports.models import Report
from apps.reports.tasks import generate_report_task
from apps.sprints.models import Sprint

PASSWORD = 'Str0ng!DevPassw0rd'


class DashboardTestBase(APITestCase):
    def setUp(self):
        self.institution = Institution.objects.create(name='MKCE', city='Karur', state='TN')
        self.other_institution = Institution.objects.create(name='Other', city='X', state='Y')

        self.admin = self._make_user('admin@test.edu', User.Role.INSTITUTION_ADMIN, self.institution)
        self.consultant = self._make_user('consultant@ingage.io', User.Role.CONSULTANT, None)

    @staticmethod
    def _make_user(email, role, institution):
        return User.objects.create_user(
            email=email, username=email.split('@')[0], password=PASSWORD,
            first_name='Test', last_name=role, role=role, institution=institution,
        )

    def _auth(self, user):
        login = self.client.post('/api/v1/auth/login/', {'email': user.email, 'password': PASSWORD})
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {login.data["access_token"]}')

    def _make_sprint(self, institution, **overrides):
        defaults = {'institution': institution, 'mode': Sprint.SprintMode.VERIFIED_CRI}
        defaults.update(overrides)
        return Sprint.objects.create(**defaults)

    def _make_gap(self, sprint, **overrides):
        defaults = {
            'sprint': sprint, 'gap_type': GapItem.GapType.MISSING_DOCUMENT, 'title': 'Missing something',
            'pillar': 'governance_strategy', 'priority': GapItem.Priority.HIGH,
        }
        defaults.update(overrides)
        return GapItem.objects.create(**defaults)

    def _make_fact(self, sprint, **overrides):
        defaults = {
            'sprint': sprint, 'field_name': 'Faculty Certified %', 'field_key': 'faculty_certified_pct',
            'value': 62.5, 'pillar': 'governance_strategy', 'status': ExtractedFact.Status.EXTRACTED,
            'confidence_score': 0.8,
        }
        defaults.update(overrides)
        return ExtractedFact.objects.create(**defaults)


class DashboardMetricsTests(DashboardTestBase):
    def test_metrics_reflect_real_data_for_the_users_institution(self):
        active_sprint = self._make_sprint(
            self.institution, status=Sprint.Status.COLLECTING, completion_percentage=40,
        )
        self._make_sprint(self.institution, status=Sprint.Status.COMPLETED, completion_percentage=100)
        # Data for a different institution must never leak into these numbers.
        self._make_sprint(self.other_institution, status=Sprint.Status.COLLECTING, completion_percentage=10)

        self._make_gap(active_sprint, title='Blocking gap', priority=GapItem.Priority.BLOCKING)
        self._make_gap(active_sprint, title='High gap', priority=GapItem.Priority.HIGH)
        self._make_gap(active_sprint, title='Medium gap', priority=GapItem.Priority.MEDIUM)  # not "high priority"
        self._make_gap(
            active_sprint, title='Resolved blocking gap',
            priority=GapItem.Priority.BLOCKING, status=GapItem.Status.RESOLVED,
        )

        self._make_fact(active_sprint, field_key='f1', status=ExtractedFact.Status.EXTRACTED)
        self._make_fact(active_sprint, field_key='f2', status=ExtractedFact.Status.CONFIRMED)  # not pending

        self._auth(self.admin)
        response = self.client.get('/api/v1/dashboard/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data

        self.assertEqual(data['sprint_count'], 2)  # only this institution's 2 sprints
        self.assertEqual(data['active_sprints'], 1)  # the completed one is excluded
        self.assertEqual(data['completion_percentage'], 70.0)  # avg(40, 100)
        self.assertEqual(data['reports_ready'], 0)
        self.assertEqual(data['pending_confirmations'], 1)
        self.assertEqual(data['high_priority_gaps'], 2)  # blocking + high, resolved/medium excluded
        self.assertEqual(data['institution_count'], 1)

    def test_scoped_user_never_sees_another_institutions_sprints_in_the_list(self):
        self._make_sprint(self.institution, name='Mine')
        self._make_sprint(self.other_institution, name='Not mine')

        self._auth(self.admin)
        response = self.client.get('/api/v1/dashboard/')
        names = [s['name'] for s in response.data['sprints']]
        self.assertEqual(names, ['Mine'])

    def test_cross_institution_user_sees_every_institution_and_sprint(self):
        self._make_sprint(self.institution)
        self._make_sprint(self.other_institution)

        self._auth(self.consultant)
        response = self.client.get('/api/v1/dashboard/')
        self.assertEqual(response.data['institution_count'], 2)
        self.assertEqual(response.data['sprint_count'], 2)
        self.assertEqual(len(response.data['sprints']), 2)

    def test_unauthenticated_rejected(self):
        response = self.client.get('/api/v1/dashboard/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class DashboardSprintListTests(DashboardTestBase):
    def test_sprint_fields_include_institution_name_and_honest_null_scores(self):
        sprint = self._make_sprint(
            self.institution, name='Sprint One', status=Sprint.Status.COLLECTING, completion_percentage=25,
        )
        self._make_gap(sprint, priority=GapItem.Priority.HIGH)

        self._auth(self.admin)
        response = self.client.get('/api/v1/dashboard/')
        row = response.data['sprints'][0]

        self.assertEqual(row['id'], str(sprint.id))
        self.assertEqual(row['institution'], 'MKCE')
        self.assertEqual(row['name'], 'Sprint One')
        self.assertEqual(row['status'], Sprint.Status.COLLECTING)
        self.assertEqual(row['completion'], 25)
        self.assertIsNone(row['cri'])  # never scored -- honest null, not a fabricated 0
        self.assertIsNone(row['confidence'])
        self.assertEqual(row['pending_gaps'], 1)
        self.assertIsNone(row['report_status'])  # no report generated yet

    def test_report_status_reflects_the_latest_report_version(self):
        from django.test import override_settings

        sprint = self._make_sprint(self.institution)
        with override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True):
            report = Report.objects.create(sprint=sprint, version=1)
            generate_report_task.delay(str(report.id))

        self._auth(self.admin)
        response = self.client.get('/api/v1/dashboard/')
        self.assertEqual(response.data['sprints'][0]['report_status'], Report.Status.READY)
        self.assertEqual(response.data['reports_ready'], 1)

    def test_sprint_list_is_a_plain_array_by_default(self):
        self._make_sprint(self.institution)
        self._auth(self.admin)
        response = self.client.get('/api/v1/dashboard/')
        self.assertIsInstance(response.data['sprints'], list)

    def test_sprint_list_pagination_is_opt_in(self):
        for _ in range(3):
            self._make_sprint(self.institution)

        self._auth(self.admin)
        response = self.client.get('/api/v1/dashboard/', {'page_size': 2, 'page': 1})
        self.assertIn('results', response.data['sprints'])
        self.assertEqual(response.data['sprints']['count'], 3)
        self.assertEqual(len(response.data['sprints']['results']), 2)
        # Summary metrics are unaffected by list pagination.
        self.assertEqual(response.data['sprint_count'], 3)


class DashboardQueryEfficiencyTests(DashboardTestBase):
    def _seed(self, sprint_count):
        for i in range(sprint_count):
            sprint = self._make_sprint(self.institution, name=f'Sprint {i}')
            self._make_gap(sprint, priority=GapItem.Priority.BLOCKING)
            self._make_fact(sprint, field_key=f'f{i}')

    def test_query_count_does_not_grow_with_sprint_count(self):
        """The dashboard reads gaps/reports per sprint via annotate/prefetch,
        not a query per row -- so the same fixed number of queries must run
        whether there are 2 sprints or 6."""
        self._auth(self.admin)

        self._seed(2)
        with CaptureQueriesContext(connection) as small:
            self.client.get('/api/v1/dashboard/')

        self._seed(4)  # 6 sprints total now
        with CaptureQueriesContext(connection) as large:
            self.client.get('/api/v1/dashboard/')

        self.assertEqual(len(small.captured_queries), len(large.captured_queries))
