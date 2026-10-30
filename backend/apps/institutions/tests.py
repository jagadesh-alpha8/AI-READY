from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.sprints.models import Sprint

from .models import Department, Institution, InstitutionLeader, InstitutionSystem

PASSWORD = 'Str0ng!DevPassw0rd'


class InstitutionCrudTests(APITestCase):
    def setUp(self):
        self.institution_a = Institution.objects.create(name='College A', city='Chennai', state='TN')
        self.institution_b = Institution.objects.create(name='College B', city='Coimbatore', state='TN')

        self.admin_a = self._make_user('admin_a@test.edu', User.Role.IQAC_COORDINATOR, self.institution_a)
        self.viewer_a = self._make_user('viewer_a@test.edu', User.Role.IQAC_COORDINATOR, self.institution_b)
        self.super_admin = self._make_user('root@test.edu', User.Role.SUPER_ADMIN, None)
        self.consultant = self._make_user('consultant@test.edu', User.Role.CONSULTANT, None)

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

    def test_only_ingage_staff_create_institutions(self):
        # Creating a college names and invites its IQAC Coordinator (apps/institutions/coordinator.py).
        body = {'name': 'New College', 'short_name': 'NC', 'city': 'Madurai', 'state': 'TN',
                'coordinator_name': 'New Coordinator', 'coordinator_email': 'iqac@newcollege.ac.in'}
        self._auth(self.admin_a)
        self.assertEqual(self.client.post('/api/v1/institutions/', body).status_code, status.HTTP_403_FORBIDDEN)
        self._auth(self.super_admin)
        response = self.client.post('/api/v1/institutions/', body)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(str(response.data['created_by']), str(self.super_admin.id))

    def test_create_accepts_frontend_field_names(self):
        """SprintSetup.tsx (existing, unmodified) posts `affiliation`,
        `accreditation_status`, and `website_url` -- confirm they land on
        the real columns instead of being silently dropped."""
        self._auth(self.super_admin)
        response = self.client.post('/api/v1/institutions/', {
            'name': 'New College', 'city': 'Madurai', 'state': 'TN',
            'coordinator_name': 'New Coordinator', 'coordinator_email': 'iqac@newcollege.ac.in',
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
        """Regression / Policy: An institution with an approved baseline and sprint contains
        protected assessment evidence and audit history. Deletion must be blocked with 409 Conflict,
        not silently cascaded."""
        from apps.scoring.models import Baseline, ScoringRun

        sprint = Sprint.objects.create(institution=self.institution_a)
        scoring_run = ScoringRun.objects.create(sprint=sprint, calculation_version='v1')
        baseline = Baseline.objects.create(sprint=sprint, scoring_run=scoring_run)

        self._auth(self.super_admin)
        response = self.client.delete(f'/api/v1/institutions/{self.institution_a.id}/')

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data['error_code'], 'INSTITUTION_DELETE_BLOCKED')
        self.assertFalse(response.data['can_delete'])
        self.assertTrue(Institution.objects.filter(id=self.institution_a.id).exists())
        self.assertTrue(Sprint.objects.filter(id=sprint.id).exists())
        self.assertTrue(Baseline.objects.filter(id=baseline.id).exists())

    def test_deletion_preview_and_blocked_delete_for_institution_with_sprints(self):
        sprint = Sprint.objects.create(institution=self.institution_a, name='Sprint Alpha')
        self._auth(self.super_admin)

        # 1. Preview
        preview_res = self.client.get(f'/api/v1/institutions/{self.institution_a.id}/deletion-preview/')
        self.assertEqual(preview_res.status_code, status.HTTP_200_OK)
        self.assertFalse(preview_res.data['can_delete'])
        self.assertTrue(preview_res.data['is_blocked'])
        self.assertIn('sprint', preview_res.data['block_reason'].lower())
        self.assertEqual(preview_res.data['dependencies']['sprints'], 1)
        self.assertEqual(preview_res.data['recommended_action'], 'archive')

        # 2. Blocked delete
        del_res = self.client.delete(f'/api/v1/institutions/{self.institution_a.id}/')
        self.assertEqual(del_res.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(del_res.data['error_code'], 'INSTITUTION_DELETE_BLOCKED')
        self.assertTrue(Institution.objects.filter(id=self.institution_a.id).exists())

    def test_deletion_preview_and_blocked_delete_with_evidence_submission_dependency(self):
        from apps.documents.models import Document
        from apps.facts.models import ExtractedFact, EvidenceRequest, EvidenceRequestDocument

        sprint = Sprint.objects.create(institution=self.institution_a, name='Sprint Evidence')
        doc = Document.objects.create(sprint=sprint, original_filename='audit_report.pdf', file_size=2048)
        fact = ExtractedFact.objects.create(sprint=sprint, document=doc, field_name='Student Count', value='1500')
        req = EvidenceRequest.objects.create(sprint=sprint, fact=fact)
        sub = EvidenceRequestDocument.objects.create(request=req, document=doc)

        self._auth(self.super_admin)

        # Preview reflects evidence submission dependency
        preview_res = self.client.get(f'/api/v1/institutions/{self.institution_a.id}/deletion-preview/')
        self.assertEqual(preview_res.status_code, status.HTTP_200_OK)
        self.assertFalse(preview_res.data['can_delete'])
        self.assertEqual(preview_res.data['dependencies']['evidence_submissions'], 1)
        self.assertEqual(preview_res.data['dependencies']['documents'], 1)
        self.assertEqual(preview_res.data['dependencies']['facts'], 1)

        # Attempt delete -> 409 Conflict, preserving evidence and document lineage
        del_res = self.client.delete(f'/api/v1/institutions/{self.institution_a.id}/')
        self.assertEqual(del_res.status_code, status.HTTP_409_CONFLICT)
        self.assertTrue(Institution.objects.filter(id=self.institution_a.id).exists())
        self.assertTrue(EvidenceRequestDocument.objects.filter(id=sub.id).exists())
        self.assertTrue(Document.objects.filter(id=doc.id).exists())

    def test_deletable_institution_with_no_protected_records(self):
        clean_inst = Institution.objects.create(name='Clean University', city='Pune', state='MH')
        dept = Department.objects.create(institution=clean_inst, name='Mathematics')
        leader = InstitutionLeader.objects.create(institution=clean_inst, name='Dr. Sharma', role='Director')
        system = InstitutionSystem.objects.create(institution=clean_inst, name='Moodle LMS')

        self._auth(self.super_admin)

        # Preview indicates safe to delete
        preview_res = self.client.get(f'/api/v1/institutions/{clean_inst.id}/deletion-preview/')
        self.assertEqual(preview_res.status_code, status.HTTP_200_OK)
        self.assertTrue(preview_res.data['can_delete'])
        self.assertFalse(preview_res.data['is_blocked'])
        self.assertIsNone(preview_res.data['block_reason'])
        self.assertEqual(preview_res.data['recommended_action'], 'delete')
        self.assertEqual(preview_res.data['dependencies']['sprints'], 0)
        self.assertEqual(preview_res.data['dependencies']['departments'], 1)

        # Delete succeeds transactionally with 204
        del_res = self.client.delete(f'/api/v1/institutions/{clean_inst.id}/')
        self.assertEqual(del_res.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Institution.objects.filter(id=clean_inst.id).exists())
        self.assertFalse(Department.objects.filter(id=dept.id).exists())
        self.assertFalse(InstitutionLeader.objects.filter(id=leader.id).exists())
        self.assertFalse(InstitutionSystem.objects.filter(id=system.id).exists())

    def test_permission_denial_on_institution_deletion(self):
        # 1. Consultant is denied permanent deletion (only Super Admin)
        self._auth(self.consultant)
        del_res = self.client.delete(f'/api/v1/institutions/{self.institution_a.id}/')
        self.assertEqual(del_res.status_code, status.HTTP_403_FORBIDDEN)

        # 2. IQAC Coordinator is denied
        self._auth(self.admin_a)
        del_res = self.client.delete(f'/api/v1/institutions/{self.institution_a.id}/')
        self.assertEqual(del_res.status_code, status.HTTP_403_FORBIDDEN)

        # 3. Unauthenticated is denied
        self.client.credentials()
        del_res = self.client.delete(f'/api/v1/institutions/{self.institution_a.id}/')
        self.assertEqual(del_res.status_code, status.HTTP_401_UNAUTHORIZED)

        self.assertTrue(Institution.objects.filter(id=self.institution_a.id).exists())

    def test_race_condition_dependency_appearing_between_preview_and_deletion(self):
        clean_inst = Institution.objects.create(name='Race Test College', city='Jaipur', state='RJ')
        self._auth(self.super_admin)

        # Initial preview says safe to delete
        preview_res = self.client.get(f'/api/v1/institutions/{clean_inst.id}/deletion-preview/')
        self.assertEqual(preview_res.status_code, status.HTTP_200_OK)
        self.assertTrue(preview_res.data['can_delete'])

        # Concurrent action adds a sprint before user clicks final delete
        Sprint.objects.create(institution=clean_inst, name='Concurrent Sprint')

        # DELETE catches the newly added protected dependency and returns 409
        del_res = self.client.delete(f'/api/v1/institutions/{clean_inst.id}/')
        self.assertEqual(del_res.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(del_res.data['error_code'], 'INSTITUTION_DELETE_BLOCKED')
        self.assertTrue(Institution.objects.filter(id=clean_inst.id).exists())

    def test_archive_and_unarchive_institution(self):
        self._auth(self.super_admin)
        self.assertTrue(self.institution_a.is_active)

        # Archive
        arc_res = self.client.post(f'/api/v1/institutions/{self.institution_a.id}/archive/')
        self.assertEqual(arc_res.status_code, status.HTTP_200_OK)
        self.institution_a.refresh_from_db()
        self.assertFalse(self.institution_a.is_active)

        # Unarchive
        unarc_res = self.client.post(f'/api/v1/institutions/{self.institution_a.id}/unarchive/')
        self.assertEqual(unarc_res.status_code, status.HTTP_200_OK)
        self.institution_a.refresh_from_db()
        self.assertTrue(self.institution_a.is_active)

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
            'dna_admin@test.edu', User.Role.IQAC_COORDINATOR, self.institution_a,
        )
        self.viewer_a = InstitutionCrudTests._make_user(
            'dna_viewer@test.edu', User.Role.IQAC_COORDINATOR, self.institution_b,
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

    def test_another_college_can_neither_read_nor_write_departments(self):
        self._auth(self.viewer_a)  # an IQAC Coordinator of College B
        self.assertEqual(
            self.client.get(f'/api/v1/institutions/{self.institution_a.id}/departments').status_code,
            status.HTTP_403_FORBIDDEN,
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
