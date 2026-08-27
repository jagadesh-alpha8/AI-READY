import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import User
from apps.institutions.models import Institution

DEFAULT_DEMO_PASSWORD = 'Password123!'

DEMO_INSTITUTION = {
    'name': 'M. Kumarasamy College of Engineering',
    'short_name': 'MKCE',
    'institution_type': 'Autonomous Engineering College',
    'university_affiliation': 'Anna University',
    'location': 'NH-544, Kuniyamuthur',
    'city': 'Karur',
    'state': 'Tamil Nadu',
    'country': 'India',
    'accreditation_details': 'NAAC A+ / NBA Accredited',
    'contact_email': 'info@mkce.ac.in',
}

# One persona per supported role, reusing the same emails as the frontend's
# quick-login list (src/pages/Login.tsx) wherever that list has an
# equivalent role, so those buttons work against this seed data too.
PERSONAS = [
    {
        'email': 'superadmin@ingage.ai', 'username': 'superadmin',
        'first_name': 'Super', 'last_name': 'Admin',
        'role': User.Role.SUPER_ADMIN, 'institution': False, 'department_name': '',
        'is_staff': True, 'is_superuser': True,
    },
    {
        'email': 'consultant@ingage.ai', 'username': 'consultant',
        'first_name': 'Aarav', 'last_name': 'Mehta',
        'role': User.Role.CONSULTANT, 'institution': False, 'department_name': '',
    },
    {
        'email': 'principal@mkce.ac.in', 'username': 'principal',
        'first_name': 'N.', 'last_name': 'Ramesh',
        'role': User.Role.INSTITUTION_ADMIN, 'institution': True, 'department_name': '',
    },
    {
        'email': 'iqac@mkce.ac.in', 'username': 'iqac_coordinator',
        'first_name': 'S.', 'last_name': 'Kanthaswamy',
        'role': User.Role.IQAC_COORDINATOR, 'institution': True, 'department_name': '',
    },
    {
        'email': 'registrar@mkce.ac.in', 'username': 'registrar',
        'first_name': 'K.', 'last_name': 'Vignesh',
        'role': User.Role.REGISTRAR, 'institution': True, 'department_name': '',
    },
    {
        'email': 'hod_cs@mkce.ac.in', 'username': 'hod_cs',
        'first_name': 'C.', 'last_name': 'Vivek',
        'role': User.Role.HOD, 'institution': True, 'department_name': 'Computer Science',
    },
    {
        'email': 'hr@mkce.ac.in', 'username': 'hr_officer',
        'first_name': 'P.', 'last_name': 'Meenakshi',
        'role': User.Role.HR_OFFICER, 'institution': True, 'department_name': '',
    },
    {
        'email': 'labadmin@mkce.ac.in', 'username': 'lab_admin',
        'first_name': 'S.', 'last_name': 'Karthik',
        'role': User.Role.LAB_ADMIN, 'institution': True, 'department_name': '',
    },
    {
        'email': 'placement@mkce.ac.in', 'username': 'placement_officer',
        'first_name': 'R.', 'last_name': 'Anand',
        'role': User.Role.PLACEMENT_OFFICER, 'institution': True, 'department_name': '',
    },
    {
        'email': 'faculty@mkce.ac.in', 'username': 'faculty_cs',
        'first_name': 'R.', 'last_name': 'Priya',
        'role': User.Role.FACULTY, 'institution': True, 'department_name': 'Computer Science',
    },
    {
        'email': 'viewer@mkce.ac.in', 'username': 'viewer',
        'first_name': 'Trustee', 'last_name': 'Board',
        'role': User.Role.VIEWER, 'institution': True, 'department_name': '',
    },
]


class Command(BaseCommand):
    help = (
        'Seed development-only demo users matching the frontend personas. '
        'Refuses to run unless DEBUG=True, to keep these accounts out of production.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--force', action='store_true',
            help='Allow running even when DEBUG=False. Not recommended.',
        )
        parser.add_argument(
            '--password', default=None,
            help='Override the shared demo password (falls back to the DEMO_USER_PASSWORD '
                 'env var, then a dev-only default).',
        )

    def handle(self, *args, **options):
        if not settings.DEBUG and not options['force']:
            raise CommandError(
                'Refusing to seed demo users because DEBUG=False. These are '
                'development-only accounts sharing one known password -- they must '
                'never exist in a production database. Pass --force to override.'
            )

        password = options['password'] or os.getenv('DEMO_USER_PASSWORD', DEFAULT_DEMO_PASSWORD)

        institution, _ = Institution.objects.get_or_create(
            name=DEMO_INSTITUTION['name'], defaults=DEMO_INSTITUTION,
        )

        created_count = 0
        updated_count = 0

        with transaction.atomic():
            for persona in PERSONAS:
                defaults = {
                    'username': persona['username'],
                    'first_name': persona['first_name'],
                    'last_name': persona['last_name'],
                    'role': persona['role'],
                    'department_name': persona['department_name'],
                    'institution': institution if persona['institution'] else None,
                    'is_active': True,
                    'is_staff': persona.get('is_staff', False),
                    'is_superuser': persona.get('is_superuser', False),
                }
                user, was_created = User.objects.get_or_create(
                    email=persona['email'], defaults=defaults,
                )
                if not was_created:
                    for field, value in defaults.items():
                        setattr(user, field, value)
                user.set_password(password)
                user.save()

                if was_created:
                    created_count += 1
                else:
                    updated_count += 1

        self.stdout.write(self.style.SUCCESS(
            f'Seeded {created_count} new and refreshed {updated_count} existing demo users '
            f'for "{institution.name}".',
        ))
        self.stdout.write('')
        self.stdout.write(self.style.WARNING(
            'Development credentials only. Every account above shares this password:',
        ))
        self.stdout.write(self.style.WARNING(f'  {password}'))
        self.stdout.write('Do not reuse these accounts or this password in production.')
        self.stdout.write('')
        self.stdout.write(f'{"EMAIL":<28}{"ROLE":<20}NAME')
        for persona in PERSONAS:
            full_name = f'{persona["first_name"]} {persona["last_name"]}'
            self.stdout.write(f'{persona["email"]:<28}{persona["role"]:<20}{full_name}')
