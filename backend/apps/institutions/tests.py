from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User

from .models import Institution

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

    # -- delete (soft) -----------------------------------------------------

    def test_institution_admin_cannot_delete_institution(self):
        self._auth(self.admin_a)
        response = self.client.delete(f'/api/v1/institutions/{self.institution_a.id}/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_super_admin_delete_is_a_soft_delete(self):
        self._auth(self.super_admin)
        response = self.client.delete(f'/api/v1/institutions/{self.institution_a.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.institution_a.refresh_from_db()
        self.assertFalse(self.institution_a.is_active)

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
