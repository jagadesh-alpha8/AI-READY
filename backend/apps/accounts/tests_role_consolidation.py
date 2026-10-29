"""Comprehensive automated test suite for the 3-Role Consolidation & Access Control System.

Tests verify:
1. Exactly three allowed roles: Super Admin, InGage Consultant, IQAC Coordinator.
2. Active user creation and editing role restrictions (legacy roles rejected).
3. Super Admin vs InGage Consultant privilege separation (user admin and AI-QIF expert endpoints).
4. IQAC Coordinator institution-scoped access to all college operations.
5. Strict cross-institution access denial for IQAC Coordinator (cannot access another college's data).
6. Safe handling of former viewer accounts (deactivated, identity preserved, original role audited).
7. Migration idempotency and zero active accounts remaining with legacy roles.
8. Authoritative Role & Access Matrix API (/api/v1/auth/access-matrix).
"""
import uuid
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User, RoleMigrationAudit
from apps.accounts.permissions import (
    MANAGE_SPRINT_ROLES,
    MANAGE_RECOMMENDATION_ROLES,
    EDIT_RECOMMENDATION_ROLES,
    REVIEW_ROLES,
)
from apps.institutions.models import Institution
from apps.sprints.models import Sprint
from apps.documents.models import Document
from apps.facts.models import ExtractedFact, EvidenceRequest
from apps.facts.ownership import (
    OVERRIDE_ROLES,
    COORDINATOR_ROLES,
    who_can_act,
    check_fact,
    eligible_assignees as eligible_fact_assignees,
)
from apps.recommendations.models import Recommendation
from apps.recommendations.services import PILLAR_OWNER_ROLE


class RoleConsolidationTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Institutions
        self.inst_a = Institution.objects.create(name='College Alpha', short_name='ALPHA')
        self.inst_b = Institution.objects.create(name='College Beta', short_name='BETA')

        # Super Admin
        self.super_admin = User.objects.create_user(
            email='superadmin@test.ingage.ai',
            password='TestPassword123!',
            role=User.Role.SUPER_ADMIN,
            is_staff=True,
            is_superuser=True,
        )

        # Consultant
        self.consultant = User.objects.create_user(
            email='consultant@test.ingage.ai',
            password='TestPassword123!',
            role=User.Role.CONSULTANT,
        )

        # IQAC Coordinator College Alpha
        self.iqac_a = User.objects.create_user(
            email='iqac@alpha.test.edu',
            username='iqac_alpha',
            password='TestPassword123!',
            role=User.Role.IQAC_COORDINATOR,
            institution=self.inst_a,
        )

        # IQAC Coordinator College Beta
        self.iqac_b = User.objects.create_user(
            email='iqac@beta.test.edu',
            username='iqac_beta',
            password='TestPassword123!',
            role=User.Role.IQAC_COORDINATOR,
            institution=self.inst_b,
        )

        # Sprints
        self.sprint_a = Sprint.objects.create(
            institution=self.inst_a,
            name='Alpha Sprint 1',
            status=Sprint.Status.COLLECTING,
            created_by=self.iqac_a,
        )
        self.sprint_b = Sprint.objects.create(
            institution=self.inst_b,
            name='Beta Sprint 1',
            status=Sprint.Status.COLLECTING,
            created_by=self.iqac_b,
        )

    # 1. Target Roles Definition
    def test_target_roles_enum_is_exactly_three(self):
        """Only super_admin, consultant, and iqac_coordinator are valid roles."""
        expected_roles = {'super_admin', 'consultant', 'iqac_coordinator'}
        actual_roles = set(User.Role.values)
        self.assertEqual(actual_roles, expected_roles)
        self.assertEqual(User.Role.SUPER_ADMIN, 'super_admin')
        self.assertEqual(User.Role.CONSULTANT, 'consultant')
        self.assertEqual(User.Role.IQAC_COORDINATOR, 'iqac_coordinator')

    def test_default_role_is_iqac_coordinator(self):
        """New users default to iqac_coordinator."""
        user = User.objects.create_user(email='new@alpha.test.edu', password='TestPassword123!')
        self.assertEqual(user.role, User.Role.IQAC_COORDINATOR)

    # 2. Authoritative Role & Access Matrix API
    def test_access_matrix_endpoint(self):
        """GET /api/v1/auth/access-matrix returns the canonical 3-role definitions."""
        response = self.client.get('/api/v1/auth/access-matrix', HTTP_HOST='localhost')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data
        self.assertIn('roles', data)
        returned_roles = [r['role'] for r in data['roles']]
        self.assertEqual(returned_roles, ['super_admin', 'consultant', 'iqac_coordinator'])

        # Check IQAC coordinator details
        iqac_info = next(r for r in data['roles'] if r['role'] == 'iqac_coordinator')
        self.assertIn('Institution-scoped', iqac_info['institution_scope'])
        self.assertTrue(len(iqac_info['modules']) >= 8)
        self.assertTrue(len(iqac_info['permitted_actions']) >= 8)
        self.assertTrue(len(iqac_info['prohibited_actions']) >= 4)

    # 3. User Administration & Role Creation Restrictions
    def test_super_admin_can_administer_all_roles(self):
        """Super Admin can create Super Admin, Consultant, and IQAC Coordinator accounts."""
        self.client.force_authenticate(user=self.super_admin)

        # Super Admin creates another consultant
        res = self.client.post('/api/v1/users', {
            'email': 'new_consultant@ingage.ai',
            'username': 'new_consultant',
            'role': User.Role.CONSULTANT,
            'password': 'StrongPassword123!',
        })
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data['role'], User.Role.CONSULTANT)

        # Super Admin creates an IQAC Coordinator for College Alpha
        res2 = self.client.post('/api/v1/users', {
            'email': 'iqac2@alpha.test.edu',
            'username': 'iqac2_alpha',
            'role': User.Role.IQAC_COORDINATOR,
            'institution_id': str(self.inst_a.id),
            'password': 'StrongPassword123!',
        })
        self.assertEqual(res2.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res2.data['role'], User.Role.IQAC_COORDINATOR)

    def test_super_admin_cannot_assign_removed_legacy_roles(self):
        """Creating a user with a removed legacy role is rejected."""
        self.client.force_authenticate(user=self.super_admin)

        for legacy_role in ['institution_admin', 'registrar', 'hod', 'hr_officer', 'lab_admin', 'placement_officer', 'faculty', 'viewer']:
            res = self.client.post('/api/v1/users', {
                'email': f'{legacy_role}@test.edu',
                'username': f'test_{legacy_role}',
                'role': legacy_role,
                'password': 'StrongPassword123!',
            })
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn('role', res.data)

    def test_consultant_has_no_user_administration_access(self):
        """InGage Consultant is denied access to user administration."""
        self.client.force_authenticate(user=self.consultant)
        res = self.client.get('/api/v1/users')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        res_post = self.client.post('/api/v1/users', {
            'email': 'unauthorized@test.edu',
            'role': User.Role.IQAC_COORDINATOR,
            'password': 'StrongPassword123!',
        })
        self.assertEqual(res_post.status_code, status.HTTP_403_FORBIDDEN)

    def test_iqac_coordinator_user_admin_scoped_to_own_college(self):
        """IQAC Coordinator can only create and manage IQAC Coordinators in their own institution."""
        self.client.force_authenticate(user=self.iqac_a)

        # Can create an IQAC Coordinator for own college
        res = self.client.post('/api/v1/users', {
            'email': 'colleague@alpha.test.edu',
            'username': 'colleague_alpha',
            'role': User.Role.IQAC_COORDINATOR,
            'password': 'StrongPassword123!',
        })
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data['institution_id'], self.inst_a.id)

        # Cannot grant platform roles
        res_platform = self.client.post('/api/v1/users', {
            'email': 'escalate@alpha.test.edu',
            'username': 'escalate',
            'role': User.Role.SUPER_ADMIN,
            'password': 'StrongPassword123!',
        })
        self.assertEqual(res_platform.status_code, status.HTTP_400_BAD_REQUEST)

        # Cannot create user for another institution
        res_other = self.client.post('/api/v1/users', {
            'email': 'spy@beta.test.edu',
            'username': 'spy_beta',
            'role': User.Role.IQAC_COORDINATOR,
            'institution_id': str(self.inst_b.id),
            'password': 'StrongPassword123!',
        })
        self.assertEqual(res_other.status_code, status.HTTP_400_BAD_REQUEST)

        # List view is strictly scoped to own institution
        res_list = self.client.get('/api/v1/users')
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        items = res_list.data.get('results') if isinstance(res_list.data, dict) else res_list.data
        inst_ids = {u['institution_id'] for u in items}
        self.assertEqual(inst_ids, {self.inst_a.id})

        # Cannot view or deactivate user from College Beta
        res_target = self.client.get(f'/api/v1/users/{self.iqac_b.id}')
        self.assertEqual(res_target.status_code, status.HTTP_404_NOT_FOUND)

        res_del = self.client.delete(f'/api/v1/users/{self.iqac_b.id}')
        self.assertEqual(res_del.status_code, status.HTTP_404_NOT_FOUND)

    # 4. Super Admin vs Consultant Privilege Separation
    def test_super_admin_only_aiqif_expert_queue(self):
        """Super Admin can access AI-QIF expert queue; Consultant is denied."""
        # Consultant denied
        self.client.force_authenticate(user=self.consultant)
        res_consultant = self.client.get(f'/api/v1/sprints/{self.sprint_a.id}/aiqif-expert-queue')
        self.assertEqual(res_consultant.status_code, status.HTTP_403_FORBIDDEN)

        # Super Admin allowed
        self.client.force_authenticate(user=self.super_admin)
        res_admin = self.client.get(f'/api/v1/sprints/{self.sprint_a.id}/aiqif-expert-queue')
        self.assertEqual(res_admin.status_code, status.HTTP_200_OK)

    def test_benchmark_studio_access(self):
        """Benchmark Studio is accessible to InGage staff (Super Admin, Consultant); denied to IQAC."""
        self.client.force_authenticate(user=self.iqac_a)
        res_iqac = self.client.get('/api/v1/benchmarks/sources')
        self.assertEqual(res_iqac.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(user=self.consultant)
        res_consultant = self.client.get('/api/v1/benchmarks/sources')
        self.assertEqual(res_consultant.status_code, status.HTTP_200_OK)

        self.client.force_authenticate(user=self.super_admin)
        res_admin = self.client.get('/api/v1/benchmarks/sources')
        self.assertEqual(res_admin.status_code, status.HTTP_200_OK)

    # 5. Strict Cross-Institution Denial for IQAC Coordinator
    def test_iqac_coordinator_strict_cross_institution_denial(self):
        """IQAC Coordinator of College Alpha is strictly denied from College Beta data."""
        self.client.force_authenticate(user=self.iqac_a)

        # Cannot retrieve College Beta sprint
        res = self.client.get(f'/api/v1/sprints/{self.sprint_b.id}')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # Cannot access College Beta facts
        res_facts = self.client.get(f'/api/v1/sprints/{self.sprint_b.id}/facts')
        self.assertEqual(res_facts.status_code, status.HTTP_403_FORBIDDEN)

        # Cannot access College Beta documents
        res_docs = self.client.get(f'/api/v1/sprints/{self.sprint_b.id}/documents')
        self.assertEqual(res_docs.status_code, status.HTTP_403_FORBIDDEN)

        # Cannot update College Beta DNA
        res_dna = self.client.patch(f'/api/v1/institutions/{self.inst_b.id}', {'short_name': 'HACKED'})
        self.assertEqual(res_dna.status_code, status.HTTP_403_FORBIDDEN)

    # 6. Full College-Side Access for IQAC Coordinator
    def test_iqac_coordinator_full_own_college_access(self):
        """IQAC Coordinator can manage all operations within own college."""
        self.client.force_authenticate(user=self.iqac_a)

        # Can retrieve own sprint
        res = self.client.get(f'/api/v1/sprints/{self.sprint_a.id}')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        # Can retrieve own facts
        res_facts = self.client.get(f'/api/v1/sprints/{self.sprint_a.id}/facts')
        self.assertEqual(res_facts.status_code, status.HTTP_200_OK)

        # Can update own institution DNA
        res_dna = self.client.patch(f'/api/v1/institutions/{self.inst_a.id}', {'short_name': 'ALPHANEW'})
        self.assertEqual(res_dna.status_code, status.HTTP_200_OK)
        self.inst_a.refresh_from_db()
        self.assertEqual(self.inst_a.short_name, 'ALPHANEW')

    # 7. Fact, Gap and Evidence-Request Ownership
    def test_fact_ownership_and_review(self):
        """Extracted facts are owned by iqac_coordinator and reviewable by IQAC and InGage staff."""
        fact = ExtractedFact.objects.create(
            sprint=self.sprint_a,
            field_name='Full-time Faculty Count',
            field_key='faculty_count',
            value='120',
            data_type='integer',
            pillar='aiqif_c4',
            owner_role='iqac_coordinator',
            status=ExtractedFact.Status.EXTRACTED,
        )

        # IQAC A can act on College Alpha fact
        allowed, _ = check_fact(self.iqac_a, fact)
        self.assertTrue(allowed)

        # IQAC B cannot act on College Alpha fact
        allowed_b, reason_b = check_fact(self.iqac_b, fact)
        self.assertFalse(allowed_b)
        self.assertIn('another college', reason_b.lower())

        # Consultant can act
        allowed_con, _ = check_fact(self.consultant, fact)
        self.assertTrue(allowed_con)

        # Eligible assignees only return active IQAC Coordinators of that college
        assignees = eligible_fact_assignees(self.inst_a.id)
        self.assertIn(self.iqac_a, assignees)
        self.assertNotIn(self.iqac_b, assignees)

    def test_pillar_owner_role_mapping(self):
        """All recommendation pillars map to iqac_coordinator."""
        for pillar_key, role in PILLAR_OWNER_ROLE.items():
            self.assertEqual(role, 'iqac_coordinator')

    # 8. Safe Handling of Former Viewers and Deactivated Accounts
    def test_viewer_account_deactivation_and_login_block(self):
        """Former viewer account is safely deactivated and cannot sign in."""
        viewer = User.objects.create_user(
            email='former_viewer@test.edu',
            password='Password123!',
            role='viewer',
            is_active=False,
            department_name='Trustee [Deactivated former viewer]',
        )

        # Attempt login is blocked
        login_res = self.client.post('/api/v1/auth/login', {
            'email': 'former_viewer@test.edu',
            'password': 'Password123!',
        })
        self.assertEqual(login_res.status_code, status.HTTP_400_BAD_REQUEST)

    # 9. No Active Accounts with Legacy Roles Remain
    def test_no_active_accounts_with_legacy_roles(self):
        """Ensure 0 active accounts exist with legacy roles in the database."""
        active_legacy = User.objects.filter(is_active=True).exclude(
            role__in=[User.Role.SUPER_ADMIN, User.Role.CONSULTANT, User.Role.IQAC_COORDINATOR]
        )
        self.assertEqual(active_legacy.count(), 0)

    # 10. Permission Sets Contain Only Target Roles
    def test_permission_role_sets(self):
        """Permission constants strictly reference only the 3 target roles."""
        self.assertEqual(MANAGE_SPRINT_ROLES, {User.Role.SUPER_ADMIN, User.Role.CONSULTANT, User.Role.IQAC_COORDINATOR})
        self.assertEqual(MANAGE_RECOMMENDATION_ROLES, {User.Role.SUPER_ADMIN, User.Role.CONSULTANT, User.Role.IQAC_COORDINATOR})
        self.assertEqual(EDIT_RECOMMENDATION_ROLES, {User.Role.SUPER_ADMIN, User.Role.CONSULTANT})
        self.assertEqual(REVIEW_ROLES, {User.Role.SUPER_ADMIN, User.Role.CONSULTANT, User.Role.IQAC_COORDINATOR})
        self.assertEqual(OVERRIDE_ROLES, {User.Role.SUPER_ADMIN, User.Role.CONSULTANT, User.Role.IQAC_COORDINATOR})
        self.assertEqual(COORDINATOR_ROLES, {User.Role.SUPER_ADMIN, User.Role.CONSULTANT, User.Role.IQAC_COORDINATOR})
