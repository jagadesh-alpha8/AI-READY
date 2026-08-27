from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.institutions.models import Institution

from .models import Sprint

PASSWORD = 'Str0ng!DevPassw0rd'


class RoleAndInstitutionAccessTests(APITestCase):
    """Role-gated writes, institution-scoped reads."""

    def setUp(self):
        self.institution_a = Institution.objects.create(name='College A', city='Chennai', state='TN')
        self.institution_b = Institution.objects.create(name='College B', city='Coimbatore', state='TN')

        self.admin_a = self._make_user(
            'admin_a@test.edu', User.Role.INSTITUTION_ADMIN, self.institution_a,
        )
        self.viewer_a = self._make_user(
            'viewer_a@test.edu', User.Role.VIEWER, self.institution_a,
        )
        self.admin_b = self._make_user(
            'admin_b@test.edu', User.Role.INSTITUTION_ADMIN, self.institution_b,
        )
        self.super_admin = self._make_user(
            'root@test.edu', User.Role.SUPER_ADMIN, None,
        )

        self.sprint_a = Sprint.objects.create(
            institution=self.institution_a, mode=Sprint.SprintMode.VERIFIED_CRI,
        )

    @staticmethod
    def _make_user(email, role, institution):
        return User.objects.create_user(
            email=email, username=email.split('@')[0], password=PASSWORD,
            first_name='Test', last_name=role, role=role, institution=institution,
        )

    def _auth(self, user):
        login = self.client.post('/api/v1/auth/login/', {'email': user.email, 'password': PASSWORD})
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {login.data["access_token"]}')

    # -- role permissions --------------------------------------------------

    def test_institution_admin_can_create_sprint(self):
        self._auth(self.admin_a)
        response = self.client.post('/api/v1/sprints/', {
            'institution_id': str(self.institution_a.id),
            'mode': 'verified_cri',
            'name': 'Q1 Discovery',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_create_accepts_frontend_field_names(self):
        """SprintSetup.tsx (existing, unmodified) posts `sprint_mode` and
        `academic_year`, not `mode` -- without the alias, the user's chosen
        mode was silently ignored (falling back to the model default) and
        academic_year had nowhere to go at all."""
        self._auth(self.admin_a)
        response = self.client.post('/api/v1/sprints/', {
            'institution_id': str(self.institution_a.id),
            'sprint_mode': 'quick_cri',
            'academic_year': '2026-27',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        sprint = Sprint.objects.get(id=response.data['id'])
        self.assertEqual(sprint.mode, Sprint.SprintMode.QUICK_CRI)
        self.assertEqual(sprint.academic_year, '2026-27')
        # And the response echoes both the canonical and alias key, since
        # Dashboard.tsx's sprint table reads `sprint.sprint_mode` back.
        self.assertEqual(response.data['mode'], Sprint.SprintMode.QUICK_CRI)
        self.assertEqual(response.data['sprint_mode'], Sprint.SprintMode.QUICK_CRI)
        self.assertEqual(response.data['academic_year'], '2026-27')

    def test_viewer_role_cannot_create_sprint(self):
        self._auth(self.viewer_a)
        response = self.client.post('/api/v1/sprints/', {
            'institution_id': str(self.institution_a.id),
            'mode': 'verified_cri',
        })
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_viewer_role_can_still_list_sprints(self):
        self._auth(self.viewer_a)
        response = self.client.get('/api/v1/sprints/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_institution_admin_cannot_create_sprint_for_other_institution(self):
        self._auth(self.admin_a)
        response = self.client.post('/api/v1/sprints/', {
            'institution_id': str(self.institution_b.id),
            'mode': 'verified_cri',
        })
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # -- institution-scoped access ------------------------------------------

    def test_user_only_sees_sprints_from_own_institution(self):
        Sprint.objects.create(institution=self.institution_b, mode=Sprint.SprintMode.QUICK_CRI)
        self._auth(self.admin_a)
        response = self.client.get('/api/v1/sprints/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_ids = {row['id'] for row in response.data}
        self.assertEqual(returned_ids, {str(self.sprint_a.id)})

    def test_super_admin_sees_sprints_across_institutions(self):
        Sprint.objects.create(institution=self.institution_b, mode=Sprint.SprintMode.QUICK_CRI)
        self._auth(self.super_admin)
        response = self.client.get('/api/v1/sprints/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_unauthorized_institution_access_to_sprint_detail_is_forbidden(self):
        self._auth(self.admin_b)
        response = self.client.get(f'/api/v1/sprints/{self.sprint_a.id}/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_own_institution_access_to_sprint_detail_is_allowed(self):
        self._auth(self.admin_a)
        response = self.client.get(f'/api/v1/sprints/{self.sprint_a.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_unauthorized_institution_access_to_nested_resource_is_forbidden(self):
        self._auth(self.admin_b)
        response = self.client.get(f'/api/v1/sprints/{self.sprint_a.id}/facts')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_super_admin_can_access_any_institution_sprint(self):
        self._auth(self.super_admin)
        response = self.client.get(f'/api/v1/sprints/{self.sprint_a.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_list_without_trailing_slash_still_matches_frontend_client(self):
        self._auth(self.admin_a)
        response = self.client.get('/api/v1/sprints')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.data, list)


class SprintCrudTests(APITestCase):
    """CRUD, pagination, filtering, ordering, state transitions, deletion guard, overview."""

    def setUp(self):
        self.institution = Institution.objects.create(name='MKCE', city='Karur', state='TN')
        self.consultant = User.objects.create_user(
            email='consultant@test.edu', username='consultant', password=PASSWORD,
            first_name='Con', last_name='Sultant', role=User.Role.CONSULTANT,
        )
        login = self.client.post('/api/v1/auth/login/', {'email': self.consultant.email, 'password': PASSWORD})
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {login.data["access_token"]}')

    def _create_sprint(self, **overrides):
        payload = {
            'institution_id': str(self.institution.id),
            'mode': Sprint.SprintMode.VERIFIED_CRI,
            'name': 'Discovery Sprint',
        }
        payload.update(overrides)
        response = self.client.post('/api/v1/sprints/', payload)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        return response.data

    # -- creation defaults ---------------------------------------------------

    def test_create_sprint_starts_in_draft_with_generated_code(self):
        data = self._create_sprint()
        self.assertEqual(data['status'], Sprint.Status.DRAFT)
        self.assertEqual(data['completion_percentage'], 0)
        self.assertTrue(data['sprint_code'].startswith('SPR-'))
        self.assertIsNone(data['overall_cri'])

    def test_cannot_create_sprint_with_non_draft_status(self):
        response = self.client.post('/api/v1/sprints/', {
            'institution_id': str(self.institution.id),
            'mode': 'verified_cri',
            'status': 'completed',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_sprint_rejects_target_date_before_start_date(self):
        response = self.client.post('/api/v1/sprints/', {
            'institution_id': str(self.institution.id),
            'mode': 'verified_cri',
            'start_date': '2026-06-01',
            'target_completion_date': '2026-05-01',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # -- state machine -------------------------------------------------------

    def test_valid_status_transition_is_accepted_and_advances_completion(self):
        sprint = self._create_sprint()
        response = self.client.patch(f'/api/v1/sprints/{sprint["id"]}/', {'status': 'collecting'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'collecting')
        self.assertEqual(response.data['completion_percentage'], 15)

    def test_invalid_status_transition_is_rejected(self):
        sprint = self._create_sprint()
        # draft -> scoring skips the whole pipeline and must be rejected
        response = self.client.patch(f'/api/v1/sprints/{sprint["id"]}/', {'status': 'scoring'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('status', response.data)

    def test_archiving_is_allowed_from_any_active_status(self):
        sprint = self._create_sprint()
        self.client.patch(f'/api/v1/sprints/{sprint["id"]}/', {'status': 'collecting'})
        response = self.client.patch(f'/api/v1/sprints/{sprint["id"]}/', {'status': 'archived'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_archived_sprint_has_no_further_transitions(self):
        sprint = self._create_sprint()
        self.client.patch(f'/api/v1/sprints/{sprint["id"]}/', {'status': 'archived'})
        response = self.client.patch(f'/api/v1/sprints/{sprint["id"]}/', {'status': 'collecting'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_explicit_completion_percentage_overrides_milestone(self):
        sprint = self._create_sprint()
        response = self.client.patch(f'/api/v1/sprints/{sprint["id"]}/', {
            'status': 'collecting', 'completion_percentage': 42,
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['completion_percentage'], 42)

    # -- baseline approval stages (apps.scoring.models.Baseline drives these
    # in practice via GET/POST .../baseline/..., but the state machine graph
    # itself -- what apps.sprints.serializers.SprintSerializer.validate()
    # accepts on a direct PATCH -- is what's under test here) -------------

    def test_scoring_can_transition_to_baseline_pending(self):
        sprint = self._create_sprint()
        for target in ('collecting', 'processing', 'reviewing', 'scoring'):
            self.client.patch(f'/api/v1/sprints/{sprint["id"]}/', {'status': target})
        response = self.client.patch(f'/api/v1/sprints/{sprint["id"]}/', {'status': 'baseline_pending'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['completion_percentage'], 80)

    def test_scoring_can_no_longer_skip_directly_to_report_ready(self):
        """Extending the pipeline with baseline_pending/baseline_approved
        means scoring -> report_ready is no longer a direct hop -- a
        baseline decision must happen in between."""
        sprint = self._create_sprint()
        for target in ('collecting', 'processing', 'reviewing', 'scoring'):
            self.client.patch(f'/api/v1/sprints/{sprint["id"]}/', {'status': target})
        response = self.client.patch(f'/api/v1/sprints/{sprint["id"]}/', {'status': 'report_ready'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_baseline_pending_can_advance_to_baseline_approved_or_return_to_reviewing(self):
        sprint = self._create_sprint()
        for target in ('collecting', 'processing', 'reviewing', 'scoring', 'baseline_pending'):
            self.client.patch(f'/api/v1/sprints/{sprint["id"]}/', {'status': target})

        returned = self.client.patch(f'/api/v1/sprints/{sprint["id"]}/', {'status': 'reviewing'})
        self.assertEqual(returned.status_code, status.HTTP_200_OK)

        for target in ('scoring', 'baseline_pending', 'baseline_approved'):
            response = self.client.patch(f'/api/v1/sprints/{sprint["id"]}/', {'status': target})
            self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['completion_percentage'], 85)

    def test_baseline_approved_is_locked_against_returning_to_review(self):
        sprint = self._create_sprint()
        for target in ('collecting', 'processing', 'reviewing', 'scoring', 'baseline_pending', 'baseline_approved'):
            self.client.patch(f'/api/v1/sprints/{sprint["id"]}/', {'status': target})
        response = self.client.patch(f'/api/v1/sprints/{sprint["id"]}/', {'status': 'reviewing'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_baseline_approved_can_advance_to_report_ready_and_completed(self):
        sprint = self._create_sprint()
        for target in (
            'collecting', 'processing', 'reviewing', 'scoring', 'baseline_pending',
            'baseline_approved', 'report_ready', 'completed',
        ):
            response = self.client.patch(f'/api/v1/sprints/{sprint["id"]}/', {'status': target})
            self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['status'], 'completed')

    # -- deletion guard -------------------------------------------------------

    def test_cannot_delete_sprint_with_active_status(self):
        sprint = self._create_sprint()
        self.client.patch(f'/api/v1/sprints/{sprint["id"]}/', {'status': 'collecting'})
        response = self.client.delete(f'/api/v1/sprints/{sprint["id"]}/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_can_delete_draft_sprint(self):
        sprint = self._create_sprint()
        response = self.client.delete(f'/api/v1/sprints/{sprint["id"]}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    # -- pagination (opt-in) --------------------------------------------------

    def test_list_is_a_plain_array_without_pagination_params(self):
        for _ in range(3):
            self._create_sprint()
        response = self.client.get('/api/v1/sprints/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.data, list)
        self.assertEqual(len(response.data), 3)

    def test_list_is_paginated_when_page_param_given(self):
        for _ in range(3):
            self._create_sprint()
        response = self.client.get('/api/v1/sprints/', {'page_size': 2, 'page': 1})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('results', response.data)
        self.assertIn('count', response.data)
        self.assertEqual(response.data['count'], 3)
        self.assertEqual(len(response.data['results']), 2)

    # -- filtering & ordering --------------------------------------------------

    def test_filter_by_status_and_mode(self):
        draft = self._create_sprint(mode='quick_cri')
        collecting = self._create_sprint(mode='verified_cri')
        self.client.patch(f'/api/v1/sprints/{collecting["id"]}/', {'status': 'collecting'})

        response = self.client.get('/api/v1/sprints/', {'status': 'collecting'})
        ids = {row['id'] for row in response.data}
        self.assertEqual(ids, {collecting['id']})

        response = self.client.get('/api/v1/sprints/', {'mode': 'quick_cri'})
        ids = {row['id'] for row in response.data}
        self.assertEqual(ids, {draft['id']})

    def test_filter_by_institution_and_created_by(self):
        other_institution = Institution.objects.create(name='Other', city='X', state='Y')
        other_sprint = Sprint.objects.create(institution=other_institution, mode=Sprint.SprintMode.QUICK_CRI)
        self._create_sprint()

        response = self.client.get('/api/v1/sprints/', {'institution': str(other_institution.id)})
        ids = {row['id'] for row in response.data}
        self.assertEqual(ids, {str(other_sprint.id)})

        response = self.client.get('/api/v1/sprints/', {'created_by': str(self.consultant.id)})
        self.assertTrue(all(str(row['created_by']) == str(self.consultant.id) for row in response.data))

    def test_ordering_by_created_at(self):
        first = self._create_sprint()
        second = self._create_sprint()
        response = self.client.get('/api/v1/sprints/', {'ordering': 'created_at'})
        ids = [row['id'] for row in response.data]
        self.assertEqual(ids.index(first['id']) < ids.index(second['id']), True)

    # -- overview --------------------------------------------------------------

    def test_overview_returns_dashboard_summary(self):
        sprint = self._create_sprint()
        response = self.client.get(f'/api/v1/sprints/{sprint["id"]}/overview/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['sprint']['id'], sprint['id'])
        self.assertEqual(response.data['institution']['id'], str(self.institution.id))
        for key in ('documents', 'facts', 'gaps', 'recommendations', 'reports'):
            self.assertIn('total', response.data[key])
        self.assertEqual(response.data['documents']['total'], 0)
        self.assertIsNone(response.data['scorecard'])

    def test_overview_forbidden_for_other_institution(self):
        sprint = self._create_sprint()
        outsider = User.objects.create_user(
            email='outsider@test.edu', username='outsider', password=PASSWORD,
            role=User.Role.INSTITUTION_ADMIN,
            institution=Institution.objects.create(name='Elsewhere', city='X', state='Y'),
        )
        login = self.client.post('/api/v1/auth/login/', {'email': outsider.email, 'password': PASSWORD})
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {login.data["access_token"]}')
        response = self.client.get(f'/api/v1/sprints/{sprint["id"]}/overview/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
