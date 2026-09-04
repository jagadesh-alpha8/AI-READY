from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.sprints.models import Sprint

from .models import Department, Institution, InstitutionLeader

PASSWORD = 'Str0ng!DevPassw0rd'


class InstitutionCrudTests(APITestCase):
    def setUp(self):
        self.institution_a = Institution.objects.create(name='College A', city='Chennai', state='TN')
        self.institution_b = Institution.objects.create(name='College B', city='Coimbatore', state='TN')

        self.admin_a = self._make_user('admin_a@test.edu', User.Role.INSTITUTION_ADMIN, self.institution_a)
        self.viewer_a = self._make_user('viewer_a@test.edu', User.Role.VIEWER, self.institution_a)
        self.super_admin = self._make_user('root@test.edu', User.Role.SUPER_ADMIN, None)

    @staticmethod
    def _make_user(email, role, institution):
        return User.objects.create_user(
            email=email, username=email.split('@')[0], password=PASSWORD,
            first_name='Test', last_name=role, role=role, institution=institution,
        )

    def _auth(self, user):
        login = self.client.post('/api/v1/auth/login/', {'email': user.email, 'password': PASSWORD})
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {login.data["access_token"]}')

    # -- visibility ------------------------------------------------------

    def test_user_only_sees_own_institution(self):
        self._auth(self.admin_a)
        response = self.client.get('/api/v1/institutions/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {row['id'] for row in response.data}
        self.assertEqual(ids, {str(self.institution_a.id)})

    def test_super_admin_sees_every_institution(self):
        self._auth(self.super_admin)
        response = self.client.get('/api/v1/institutions/')
        ids = {row['id'] for row in response.data}
        self.assertEqual(ids, {str(self.institution_a.id), str(self.institution_b.id)})

    def test_unauthorized_institution_detail_is_forbidden(self):
        self._auth(self.admin_a)
        response = self.client.get(f'/api/v1/institutions/{self.institution_b.id}/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_list_without_trailing_slash_still_matches_frontend_client(self):
        self._auth(self.admin_a)
        response = self.client.get('/api/v1/institutions')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.data, list)

    # -- create / update role gating -----------------------------------------

    def test_institution_admin_can_create_institution(self):
        self._auth(self.admin_a)
        response = self.client.post('/api/v1/institutions/', {
            'name': 'New College', 'short_name': 'NC', 'city': 'Madurai', 'state': 'TN',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(str(response.data['created_by']), str(self.admin_a.id))

    def test_create_accepts_frontend_field_names(self):
        """SprintSetup.tsx (existing, unmodified) posts `affiliation`,
        `accreditation_status`, and `website_url` -- confirm they land on
        the real columns instead of being silently dropped."""
        self._auth(self.admin_a)
        response = self.client.post('/api/v1/institutions/', {
            'name': 'New College', 'city': 'Madurai', 'state': 'TN',
            'affiliation': 'Anna University',
            'accreditation_status': 'NAAC A+ / NBA Accredited',
            'website_url': 'https://newcollege.ac.in',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        institution = Institution.objects.get(id=response.data['id'])
        self.assertEqual(institution.university_affiliation, 'Anna University')
        self.assertEqual(institution.accreditation_details, 'NAAC A+ / NBA Accredited')
        self.assertEqual(institution.website_url, 'https://newcollege.ac.in')
        # And the response echoes both the canonical and alias key.
        self.assertEqual(response.data['university_affiliation'], 'Anna University')
        self.assertEqual(response.data['affiliation'], 'Anna University')

    def test_viewer_cannot_create_institution(self):
        self._auth(self.viewer_a)
        response = self.client.post('/api/v1/institutions/', {'name': 'New College'})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_institution_admin_can_update_own_institution(self):
        self._auth(self.admin_a)
        response = self.client.patch(f'/api/v1/institutions/{self.institution_a.id}/', {
            'contact_email': 'admin@college-a.edu',
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['contact_email'], 'admin@college-a.edu')

    def test_institution_admin_cannot_update_other_institution(self):
        self._auth(self.admin_a)
        response = self.client.patch(f'/api/v1/institutions/{self.institution_b.id}/', {
            'contact_email': 'hacker@example.com',
        })
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # -- delete (hard, cascading) --------------------------------------------

    def test_institution_admin_cannot_delete_institution(self):
        self._auth(self.admin_a)
        response = self.client.delete(f'/api/v1/institutions/{self.institution_a.id}/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_super_admin_delete_removes_the_institution(self):
        self._auth(self.super_admin)
        response = self.client.delete(f'/api/v1/institutions/{self.institution_a.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Institution.objects.filter(id=self.institution_a.id).exists())

    def test_delete_cascades_to_departments_and_leaders(self):
        department = Department.objects.create(institution=self.institution_a, name='CSE')
        leader = InstitutionLeader.objects.create(
            institution=self.institution_a, name='Dr. Rao', role='Principal',
        )
        self._auth(self.super_admin)
        response = self.client.delete(f'/api/v1/institutions/{self.institution_a.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Department.objects.filter(id=department.id).exists())
        self.assertFalse(InstitutionLeader.objects.filter(id=leader.id).exists())

    def test_delete_unlinks_rather_than_deletes_its_users(self):
        """User.institution is SET_NULL, not CASCADE -- a login must survive
        its institution being removed, just pointing at no institution."""
        self._auth(self.super_admin)
        response = self.client.delete(f'/api/v1/institutions/{self.institution_a.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.admin_a.refresh_from_db()
        self.assertIsNone(self.admin_a.institution)

    def test_delete_removes_a_baseline_approved_sprint(self):
        """Regression: Baseline.scoring_run is on_delete=PROTECT. A naive
        cascade delete of the institution would cascade-delete the sprint's
        ScoringRun rows and hit ProtectedError on their still-present
        Baseline rows, even though those Baseline rows are also
        cascade-deleted via the same sprint -- see perform_destroy."""
        from apps.scoring.models import Baseline, ScoringRun

        sprint = Sprint.objects.create(institution=self.institution_a)
        scoring_run = ScoringRun.objects.create(sprint=sprint, calculation_version='v1')
        baseline = Baseline.objects.create(sprint=sprint, scoring_run=scoring_run)

        self._auth(self.super_admin)
        response = self.client.delete(f'/api/v1/institutions/{self.institution_a.id}/')

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Sprint.objects.filter(id=sprint.id).exists())
        self.assertFalse(ScoringRun.objects.filter(id=scoring_run.id).exists())
        self.assertFalse(Baseline.objects.filter(id=baseline.id).exists())

    # -- filtering / ordering / pagination -----------------------------------

    def test_filter_by_state(self):
        Institution.objects.create(name='College C', city='Delhi', state='DL')
        self._auth(self.super_admin)
        response = self.client.get('/api/v1/institutions/', {'state': 'TN'})
        ids = {row['id'] for row in response.data}
        self.assertEqual(ids, {str(self.institution_a.id), str(self.institution_b.id)})

    def test_filter_by_is_active(self):
        self.institution_b.is_active = False
        self.institution_b.save(update_fields=['is_active'])
        self._auth(self.super_admin)
        response = self.client.get('/api/v1/institutions/', {'is_active': 'false'})
        ids = {row['id'] for row in response.data}
        self.assertEqual(ids, {str(self.institution_b.id)})

    def test_ordering_by_name_descending(self):
        self._auth(self.super_admin)
        response = self.client.get('/api/v1/institutions/', {'ordering': '-name'})
        names = [row['name'] for row in response.data]
        self.assertEqual(names, sorted(names, reverse=True))

    def test_pagination_is_opt_in(self):
        self._auth(self.super_admin)
        plain = self.client.get('/api/v1/institutions/')
        self.assertIsInstance(plain.data, list)

        paginated = self.client.get('/api/v1/institutions/', {'page_size': 1, 'page': 1})
        self.assertIn('results', paginated.data)
        self.assertEqual(len(paginated.data['results']), 1)


class InstitutionDnaTests(APITestCase):
    """The three Institution DNA tabs: profile extras, departments, and
    systems. Every sub-resource is nested under its institution, so these
    cover scoping as much as payload shape."""

    def setUp(self):
        self.institution_a = Institution.objects.create(name='College A', city='Chennai', state='TN')
        self.institution_b = Institution.objects.create(name='College B', city='Coimbatore', state='TN')

        self.admin_a = InstitutionCrudTests._make_user(
            'dna_admin@test.edu', User.Role.INSTITUTION_ADMIN, self.institution_a,
        )
        self.viewer_a = InstitutionCrudTests._make_user(
            'dna_viewer@test.edu', User.Role.VIEWER, self.institution_a,
        )

    def _auth(self, user):
        login = self.client.post('/api/v1/auth/login/', {'email': user.email, 'password': PASSWORD})
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {login.data["access_token"]}')

    # -- profile -------------------------------------------------------------

    def test_detail_exposes_dna_fields_and_derived_counts(self):
        Department.objects.create(institution=self.institution_a, name='CSE', program_count=4)
        Department.objects.create(institution=self.institution_a, name='ECE', program_count=3)
        InstitutionLeader.objects.create(
            institution=self.institution_a, name='Dr. Rajesh Kumar', role='Director',
        )
        self.institution_a.digital_maturity_level = Institution.DigitalMaturity.PARTIAL_DIGITAL
        self.institution_a.save(update_fields=['digital_maturity_level'])

        self._auth(self.admin_a)
        response = self.client.get(f'/api/v1/institutions/{self.institution_a.id}')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['department_count'], 2)
        # Summed from the departments themselves, never stored separately.
        self.assertEqual(response.data['program_count'], 7)
        self.assertEqual(response.data['digital_maturity_label'], 'Level 2 — Partial Digital')
        self.assertTrue(response.data['digital_maturity_description'])
        self.assertEqual(response.data['leaders'][0]['initials'], 'DRK')

    def test_program_count_is_zero_not_null_without_departments(self):
        self._auth(self.admin_a)
        response = self.client.get(f'/api/v1/institutions/{self.institution_a.id}')
        self.assertEqual(response.data['program_count'], 0)
        self.assertEqual(response.data['department_count'], 0)

    def test_list_serializer_omits_the_expensive_detail_fields(self):
        """The list endpoint must not pay for leaders or derived counts."""
        self._auth(self.admin_a)
        response = self.client.get('/api/v1/institutions')
        self.assertNotIn('leaders', response.data[0])
        self.assertNotIn('department_count', response.data[0])

    def test_priorities_are_cleaned_of_blanks_and_duplicates(self):
        self._auth(self.admin_a)
        response = self.client.patch(
            f'/api/v1/institutions/{self.institution_a.id}',
            {'priorities': ['NAAC 2025', '  ', 'NAAC 2025', ' NEP 2020 ']},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['priorities'], ['NAAC 2025', 'NEP 2020'])

    def test_priorities_reject_non_text_entries(self):
        self._auth(self.admin_a)
        response = self.client.patch(
            f'/api/v1/institutions/{self.institution_a.id}', {'priorities': [42]}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # -- departments ---------------------------------------------------------

    def test_admin_can_create_and_list_departments(self):
        self._auth(self.admin_a)
        created = self.client.post(
            f'/api/v1/institutions/{self.institution_a.id}/departments',
            {'name': 'Computer Science', 'head_name': 'Prof. Anil Mehta', 'faculty_count': 28},
            format='json',
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)

        listed = self.client.get(f'/api/v1/institutions/{self.institution_a.id}/departments')
        self.assertEqual([row['name'] for row in listed.data], ['Computer Science'])

    def test_duplicate_department_name_is_rejected_case_insensitively(self):
        Department.objects.create(institution=self.institution_a, name='Computer Science')
        self._auth(self.admin_a)
        response = self.client.post(
            f'/api/v1/institutions/{self.institution_a.id}/departments',
            {'name': 'computer science'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_same_department_name_is_fine_in_a_different_institution(self):
        Department.objects.create(institution=self.institution_b, name='Computer Science')
        self._auth(self.admin_a)
        response = self.client.post(
            f'/api/v1/institutions/{self.institution_a.id}/departments',
            {'name': 'Computer Science'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_renaming_a_department_to_its_own_name_is_allowed(self):
        department = Department.objects.create(institution=self.institution_a, name='Civil')
        self._auth(self.admin_a)
        response = self.client.patch(
            f'/api/v1/institutions/{self.institution_a.id}/departments/{department.id}',
            {'name': 'Civil', 'student_count': 250}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['student_count'], 250)

    def test_department_of_another_institution_is_not_reachable(self):
        foreign = Department.objects.create(institution=self.institution_b, name='Mechanical')
        self._auth(self.admin_a)
        response = self.client.get(
            f'/api/v1/institutions/{self.institution_a.id}/departments/{foreign.id}',
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_departments_of_an_unauthorized_institution_are_forbidden(self):
        self._auth(self.admin_a)
        response = self.client.get(f'/api/v1/institutions/{self.institution_b.id}/departments')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_viewer_can_read_but_not_write_departments(self):
        self._auth(self.viewer_a)
        self.assertEqual(
            self.client.get(f'/api/v1/institutions/{self.institution_a.id}/departments').status_code,
            status.HTTP_200_OK,
        )
        blocked = self.client.post(
            f'/api/v1/institutions/{self.institution_a.id}/departments',
            {'name': 'Sneaky'}, format='json',
        )
        self.assertEqual(blocked.status_code, status.HTTP_403_FORBIDDEN)

    def test_department_can_be_deleted(self):
        department = Department.objects.create(institution=self.institution_a, name='Applied Sciences')
        self._auth(self.admin_a)
        response = self.client.delete(
            f'/api/v1/institutions/{self.institution_a.id}/departments/{department.id}',
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Department.objects.filter(pk=department.id).exists())

    # -- systems -------------------------------------------------------------

    def test_system_create_exposes_its_tag_label(self):
        self._auth(self.admin_a)
        response = self.client.post(
            f'/api/v1/institutions/{self.institution_a.id}/systems',
            {'name': 'Custom ERP (2018)', 'tag': 'legacy'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['tag_label'], 'Legacy')

    def test_system_tag_is_optional(self):
        self._auth(self.admin_a)
        response = self.client.post(
            f'/api/v1/institutions/{self.institution_a.id}/systems',
            {'name': 'Moodle LMS'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['tag'], '')

    def test_unknown_system_tag_is_rejected(self):
        self._auth(self.admin_a)
        response = self.client.post(
            f'/api/v1/institutions/{self.institution_a.id}/systems',
            {'name': 'Something', 'tag': 'cloudy'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # -- leaders -------------------------------------------------------------

    def test_leader_initials_are_derived_from_the_name(self):
        self._auth(self.admin_a)
        response = self.client.post(
            f'/api/v1/institutions/{self.institution_a.id}/leaders',
            {'name': 'Prof. Suresh Nair', 'role': 'IQAC Coordinator'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['initials'], 'PSN')
