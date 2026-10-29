"""`/api/v1/users` — the three rules that make this API safe to expose.

Institution scoping, no privilege escalation, and no self-lockout. Each is a
real attack surface: without them, "add a user" is a path to owning the
platform or to locking everyone out of it.

Kept in its own module because `tests.py` covers the authentication flow, and
these are about administering other people rather than signing in.
"""
from rest_framework import status
from rest_framework.test import APITestCase

from apps.institutions.models import Institution

from .models import User

PASSWORD = 'Str0ng!DevPassw0rd'


class UserAdministrationTests(APITestCase):
    def setUp(self):
        self.alpha = Institution.objects.create(name='Alpha College', city='Chennai', state='TN')
        self.beta = Institution.objects.create(name='Beta College', city='Madurai', state='TN')

        self.super_admin = User.objects.create_user(
            email='super@ingage.ai', username='super', password=PASSWORD,
            role=User.Role.SUPER_ADMIN,
        )
        self.alpha_admin = User.objects.create_user(
            email='admin@alpha.edu', username='alpha_admin', password=PASSWORD,
            role=User.Role.IQAC_COORDINATOR, institution=self.alpha,
        )
        self.alpha_faculty = User.objects.create_user(
            email='faculty@alpha.edu', username='alpha_faculty', password=PASSWORD,
            role=User.Role.IQAC_COORDINATOR, institution=self.alpha,
        )
        self.beta_faculty = User.objects.create_user(
            email='faculty@beta.edu', username='beta_faculty', password=PASSWORD,
            role=User.Role.IQAC_COORDINATOR, institution=self.beta,
        )

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    # --- access ---------------------------------------------------------
    def test_a_coordinator_sees_only_their_own_colleges_users(self):
        # 3-role model: every college user is an IQAC Coordinator, who administers their own college's users.
        self._auth(self.alpha_faculty)
        response = self.client.get('/api/v1/users')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn('faculty@beta.edu', {row['email'] for row in response.data})

    def test_super_admin_sees_every_institution(self):
        self._auth(self.super_admin)
        response = self.client.get('/api/v1/users')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        emails = {row['email'] for row in response.data}
        self.assertIn('faculty@alpha.edu', emails)
        self.assertIn('faculty@beta.edu', emails)

    # --- rule 1: institution scoping ------------------------------------
    def test_institution_admin_sees_only_their_own_college(self):
        self._auth(self.alpha_admin)
        response = self.client.get('/api/v1/users')
        emails = {row['email'] for row in response.data}
        self.assertIn('faculty@alpha.edu', emails)
        self.assertNotIn('faculty@beta.edu', emails)

    def test_another_colleges_user_is_unreachable_by_id(self):
        """Not merely hidden from the list — a direct fetch must miss too."""
        self._auth(self.alpha_admin)
        response = self.client.get(f'/api/v1/users/{self.beta_faculty.id}')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_cannot_edit_another_colleges_user(self):
        self._auth(self.alpha_admin)
        response = self.client.patch(
            f'/api/v1/users/{self.beta_faculty.id}', {'first_name': 'Hijacked'},
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.beta_faculty.refresh_from_db()
        self.assertNotEqual(self.beta_faculty.first_name, 'Hijacked')

    def test_created_user_is_forced_into_the_admins_own_institution(self):
        self._auth(self.alpha_admin)
        response = self.client.post('/api/v1/users', {
            'email': 'new@alpha.edu', 'username': 'new_alpha', 'password': PASSWORD,
            'role': User.Role.IQAC_COORDINATOR, 'institution_id': str(self.beta.id),
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # --- rule 2: no privilege escalation --------------------------------
    def test_institution_admin_cannot_create_a_super_admin(self):
        self._auth(self.alpha_admin)
        response = self.client.post('/api/v1/users', {
            'email': 'evil@alpha.edu', 'username': 'evil', 'password': PASSWORD,
            'role': User.Role.SUPER_ADMIN,
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(User.objects.filter(email='evil@alpha.edu').exists())

    def test_institution_admin_cannot_promote_someone_to_consultant(self):
        self._auth(self.alpha_admin)
        response = self.client.patch(
            f'/api/v1/users/{self.alpha_faculty.id}', {'role': User.Role.CONSULTANT},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.alpha_faculty.refresh_from_db()
        self.assertEqual(self.alpha_faculty.role, User.Role.IQAC_COORDINATOR)

    def test_super_admin_may_create_a_consultant(self):
        self._auth(self.super_admin)
        response = self.client.post('/api/v1/users', {
            'email': 'consultant@ingage.ai', 'username': 'consultant1', 'password': PASSWORD,
            'role': User.Role.CONSULTANT,
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    # --- rule 3: no self-lockout ----------------------------------------
    def test_cannot_deactivate_yourself(self):
        self._auth(self.super_admin)
        response = self.client.delete(f'/api/v1/users/{self.super_admin.id}')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.super_admin.refresh_from_db()
        self.assertTrue(self.super_admin.is_active)

    def test_cannot_change_your_own_role(self):
        self._auth(self.alpha_admin)
        response = self.client.patch(
            f'/api/v1/users/{self.alpha_admin.id}', {'role': User.Role.CONSULTANT},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # --- create / update / deactivate -----------------------------------
    def test_admin_creates_a_user_who_can_then_sign_in(self):
        self._auth(self.alpha_admin)
        response = self.client.post('/api/v1/users', {
            'email': 'registrar@alpha.edu', 'username': 'alpha_registrar',
            'password': PASSWORD, 'role': User.Role.IQAC_COORDINATOR, 'first_name': 'New',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.client.force_authenticate(user=None)
        login = self.client.post('/api/v1/auth/login', {
            'email': 'registrar@alpha.edu', 'password': PASSWORD,
        })
        self.assertEqual(login.status_code, status.HTTP_200_OK)

    def test_weak_password_is_rejected(self):
        self._auth(self.alpha_admin)
        response = self.client.post('/api/v1/users', {
            'email': 'weak@alpha.edu', 'username': 'weak', 'password': '12345',
            'role': User.Role.IQAC_COORDINATOR,
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_delete_deactivates_and_blocks_login_without_destroying_the_row(self):
        self._auth(self.alpha_admin)
        response = self.client.delete(f'/api/v1/users/{self.alpha_faculty.id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.alpha_faculty.refresh_from_db()
        self.assertFalse(self.alpha_faculty.is_active)
        # The row survives, so audit trails naming this user still resolve.
        self.assertTrue(User.objects.filter(pk=self.alpha_faculty.pk).exists())

        self.client.force_authenticate(user=None)
        login = self.client.post('/api/v1/auth/login', {
            'email': 'faculty@alpha.edu', 'password': PASSWORD,
        })
        self.assertEqual(login.status_code, status.HTTP_400_BAD_REQUEST)

    def test_admin_can_reset_a_colleagues_password(self):
        self._auth(self.alpha_admin)
        new_password = 'An0ther!Str0ngPass'
        response = self.client.patch(
            f'/api/v1/users/{self.alpha_faculty.id}', {'password': new_password},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.client.force_authenticate(user=None)
        login = self.client.post('/api/v1/auth/login', {
            'email': 'faculty@alpha.edu', 'password': new_password,
        })
        self.assertEqual(login.status_code, status.HTTP_200_OK)


class InstitutionlessAdminTests(APITestCase):
    """An institution admin with no institution on their profile.

    `filter(institution_id=actor.institution_id)` with a None actor becomes
    `filter(institution_id=None)`, which matches every platform-staff user
    rather than none of them -- so this admin could see, and DELETE
    (deactivate), a super admin. The queryset must be empty instead.
    """

    def setUp(self):
        self.super_admin = User.objects.create_user(
            email='super@ingage.ai', username='super', password=PASSWORD,
            role=User.Role.SUPER_ADMIN,
        )
        self.orphan_admin = User.objects.create_user(
            email='orphan@nowhere.edu', username='orphan', password=PASSWORD,
            role=User.Role.IQAC_COORDINATOR,
        )
        self.client.force_authenticate(user=self.orphan_admin)

    def test_cannot_see_platform_staff(self):
        response = self.client.get('/api/v1/users')
        emails = {row['email'] for row in response.data}
        self.assertNotIn('super@ingage.ai', emails)

    def test_cannot_deactivate_a_super_admin(self):
        response = self.client.delete(f'/api/v1/users/{self.super_admin.id}')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.super_admin.refresh_from_db()
        self.assertTrue(self.super_admin.is_active)
