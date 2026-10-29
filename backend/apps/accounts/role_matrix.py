"""Authoritative Role and Access Matrix definition and API endpoint.

Provides the canonical, synchronized definition of the 3-role platform access model:
1. Super Admin (Platform-wide / Cross-institution)
2. InGage Consultant (InGage Operational / Cross-institution)
3. IQAC Coordinator (Institution-scoped / Own College)
"""
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

ROLE_ACCESS_MATRIX = {
    'roles': [
        {
            'role': 'super_admin',
            'name': 'Super Admin',
            'institution_scope': 'Platform-wide / Cross-institution (All Institutions)',
            'description': (
                'Full platform administration, cross-institution access, platform user administration, '
                'benchmark library administration, and platform-only AI-QIF expert validation functions.'
            ),
            'modules': [
                {'name': 'Platform Administration', 'access': 'Full Access', 'description': 'Configure platform settings, manage and delete institutions across the system.'},
                {'name': 'User Administration', 'access': 'Platform-wide', 'description': 'Create, edit, and deactivate users across all institutions; can assign Super Admin, Consultant, and IQAC Coordinator roles.'},
                {'name': 'Discovery Sprints', 'access': 'Cross-institution Full', 'description': 'Create, configure, execute, calculate CRI, and approve baselines for any institution.'},
                {'name': 'Documents & Extraction', 'access': 'Cross-institution Full', 'description': 'Upload documents, run extraction pipelines, manage chunk stores, and inspect OCR/vision fallbacks.'},
                {'name': 'Facts & Evidence Review', 'access': 'Cross-institution Full', 'description': 'Review, confirm, correct, reject facts and manage evidence requests across any college.'},
                {'name': 'AI-QIF Expert Studio', 'access': 'Exclusive Super Admin', 'description': 'Review and accept/reject indicator tags, fact classifications, and run automated queue checks.'},
                {'name': 'Benchmark Studio', 'access': 'Full Staff Access', 'description': 'Inspect benchmark catalog, sources, standards, and import audit rubrics.'},
                {'name': 'Recommendations & Transformation', 'access': 'Cross-institution Full', 'description': 'Generate, edit, accept, and hide recommendations; manage transformation plans and milestones.'},
                {'name': 'AI Usage & Billing', 'access': 'Platform-wide', 'description': 'Inspect token usage, model distribution, and cost metrics across all institutions.'},
            ],
            'permitted_actions': [
                'Administer platform-wide users (create/update Super Admin, Consultant, IQAC Coordinator)',
                'Create, edit, and delete institution profiles and DNA',
                'Create, manage, and approve discovery sprints for any institution',
                'Upload and process documents across any institution',
                'Confirm, correct, and reject extracted facts and data gaps',
                'Assign facts, gaps, and evidence requests',
                'Access AI-QIF expert validation queue and trigger automated checks',
                'Inspect Benchmark Studio catalog and sources',
                'Generate, edit, accept, and hide recommendations',
                'Inspect platform-wide AI usage and billing statistics',
            ],
            'prohibited_actions': [
                'Deactivate own account or demote own role (self-lockout prevention)',
            ],
        },
        {
            'role': 'consultant',
            'name': 'InGage Consultant',
            'institution_scope': 'InGage Operational / Cross-institution (All Institutions)',
            'description': (
                'Cross-institution operational lead for AI readiness audits, scoring, recommendations, '
                'and transformation planning. Does not possess platform user administration or Super Admin-only expert functions.'
            ),
            'modules': [
                {'name': 'Platform Administration', 'access': 'Operational Access', 'description': 'View all institutions, update DNA and profile fields; cannot delete institutions.'},
                {'name': 'User Administration', 'access': 'None', 'description': 'No user administration access; cannot create or edit user accounts.'},
                {'name': 'Discovery Sprints', 'access': 'Cross-institution Full', 'description': 'Create, lead, configure, and approve discovery sprints and CRI baselines for all colleges.'},
                {'name': 'Documents & Extraction', 'access': 'Cross-institution Full', 'description': 'Upload and inspect documents, start/stop extraction pipelines, monitor progress.'},
                {'name': 'Facts & Evidence Review', 'access': 'Cross-institution Full', 'description': 'Review, confirm, correct, and reject facts; assign and review evidence across all colleges.'},
                {'name': 'AI-QIF Expert Studio', 'access': 'None', 'description': 'Super Admin-only; cannot access expert queue or trigger AI auto-checks.'},
                {'name': 'Benchmark Studio', 'access': 'Read / Inspection', 'description': 'Inspect standard benchmarks, criteria, and source documents.'},
                {'name': 'Recommendations & Transformation', 'access': 'Cross-institution Full', 'description': 'Generate, edit, customize, accept, and hide recommendations; build transformation roadmaps.'},
                {'name': 'AI Usage & Billing', 'access': 'Cross-institution Metrics', 'description': 'Inspect AI token consumption and audit usage metrics.'},
            ],
            'permitted_actions': [
                'Cross-institution operational access to all college sprints and datasets',
                'Create, manage, lead, and approve sprints and baselines',
                'Review, confirm, correct, and reject facts and gaps across institutions',
                'Assign facts, gaps, and evidence requests',
                'Generate, edit, accept, and hide recommendations',
                'Confirm institutional profiles read from documents',
                'Inspect Benchmark Studio catalog',
                'Inspect AI usage and token metrics',
            ],
            'prohibited_actions': [
                'Administer or create user accounts',
                'Delete institutions',
                'Access Super Admin-only AI-QIF expert validation queue or auto-check',
            ],
        },
        {
            'role': 'iqac_coordinator',
            'name': 'IQAC Coordinator',
            'institution_scope': 'Institution-scoped (Own College Only)',
            'description': (
                'Sole active college-side role. Full operational access to own college operations: profile/DNA, '
                'sprint management, document upload and processing, fact review, gap resolution, evidence '
                'requests and submissions, assignments, baseline approval, recommendations, transformation plans, '
                'goals/tasks, reports, and college user administration. Strictly denied access to other institutions '
                'or InGage-only benchmark administration.'
            ),
            'modules': [
                {'name': 'Institution DNA & Profile', 'access': 'Full (Own College)', 'description': 'Manage institution profile, departments, leadership, and operational systems for own college.'},
                {'name': 'User Administration', 'access': 'Scoped (Own College)', 'description': 'Administer users within own institution; can create and manage only IQAC Coordinator accounts.'},
                {'name': 'Discovery Sprints', 'access': 'Full (Own College)', 'description': 'Create and manage discovery sprints, calculate CRI, and approve baselines for own college.'},
                {'name': 'Documents & Extraction', 'access': 'Full (Own College)', 'description': 'Upload institutional documents, import data packs, and monitor extraction and OCR progress.'},
                {'name': 'Facts & Evidence Review', 'access': 'Full (Own College)', 'description': 'Review, confirm, correct, and reject facts; resolve gaps; request and submit supporting evidence.'},
                {'name': 'AI-QIF Expert Studio', 'access': 'None', 'description': 'Platform internal expert queue; no college access.'},
                {'name': 'Benchmark Studio', 'access': 'None', 'description': 'InGage proprietary benchmark catalog; no college access.'},
                {'name': 'Recommendations & Transformation', 'access': 'Full (Own College)', 'description': 'Generate recommendations, manage transformation plans, milestones, and goals/tasks.'},
                {'name': 'AI Usage & Billing', 'access': 'None', 'description': 'InGage internal billing metrics; no college access.'},
            ],
            'permitted_actions': [
                'Institution-scoped access to all own-college discovery sprints and data',
                'Administer users strictly within own college (only IQAC Coordinator accounts)',
                'Create and update own institution profile, DNA, departments, and systems',
                'Upload and delete own college documents, import data pack checklists',
                'Review, confirm, correct, and reject extracted facts for own college',
                'Resolve, skip, and close data gaps for own college',
                'Assign tasks, facts, and evidence requests to college coordinators',
                'Submit supporting evidence documents for open requests',
                'Approve and submit CRI baseline for own college',
                'Generate recommendations, manage transformation plans, and track goals/tasks',
            ],
            'prohibited_actions': [
                'Access, view, or modify any other institution\'s data (strict 403 / scoped querysets)',
                'Assign platform-wide roles (Super Admin, Consultant)',
                'Access InGage Benchmark Studio catalog',
                'Access Super Admin-only AI-QIF expert validation queue',
                'Delete institutions',
                'Inspect platform-wide AI usage or billing',
            ],
        },
    ],
}


class RoleAccessMatrixView(APIView):
    """GET /api/v1/auth/access-matrix -- Authoritative Role & Access Matrix."""
    permission_classes = [AllowAny]

    def get(self, request):
        return Response(ROLE_ACCESS_MATRIX)

