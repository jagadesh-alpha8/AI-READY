"""IQAC Coordinator onboarding at Institution DNA creation (apps/institutions/coordinator.py).

Emails go to Django's in-memory test outbox (mail.outbox) -- nothing is ever sent for real.
"""
import re
from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.sprints.models import Sprint

from .models import CoordinatorEvent, CoordinatorInvitation, Institution

PASSWORD = 'Str0ng!DevPassw0rd'
NEW_PASSWORD = 'Brand-new!Passw0rd'


def _token(message):
    return re.search(r'activate-account\?token=([\w-]+)', message.body).group(1)


class CoordinatorBase(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(email='admin@ingage.ai', username='admin', password=PASSWORD,
                                              role=User.Role.SUPER_ADMIN)
        self.consultant = User.objects.create_user(email='c@ingage.ai', username='consult', password=PASSWORD,
                                                   role=User.Role.CONSULTANT)
        self.client.force_authenticate(self.admin)

    def _create(self, **over):
        body = {'name': 'MKCE', 'city': 'Karur', 'coordinator_name': 'Dr. S. Priya',
                'coordinator_email': 'Priya@MKCE.ac.in', **over}
        return self.client.post('/api/v1/institutions', body, format='json')

    def _accept(self, token, password=NEW_PASSWORD):
        self.client.force_authenticate(None)
        return self.client.post('/api/v1/auth/invitation/accept', {'token': token, 'new_password': password},
                                format='json')


class CreationAndValidationTests(CoordinatorBase):
    def test_name_and_email_are_required_and_validated(self):
        cases = {
            'missing name': ({'coordinator_name': ''}, 'coordinator_name'),
            'missing email': ({'coordinator_email': ''}, 'coordinator_email'),
            'bad email': ({'coordinator_email': 'priya@'}, 'coordinator_email'),
            'digits in name': ({'coordinator_name': 'R2D2'}, 'coordinator_name'),
            'markup in name': ({'coordinator_name': '<b>x</b>'}, 'coordinator_name'),
        }
        for label, (over, field) in cases.items():
            r = self._create(**over)
            self.assertEqual(r.status_code, 400, label)
            self.assertIn(field, r.data, label)
        r = self.client.post('/api/v1/institutions', {'name': 'X'}, format='json')
        self.assertEqual(set(r.data), {'coordinator_name', 'coordinator_email'})
        self.assertFalse(Institution.objects.exists())  # nothing is created on invalid input
        self.assertEqual((len(mail.outbox), User.objects.count()), (0, 2))

    def test_creation_stores_the_coordinator_and_emails_a_single_use_activation_link(self):
        r = self._create()
        self.assertEqual(r.status_code, 201, r.data)
        self.assertTrue(r.data['invitation_email_sent'])
        self.assertEqual((r.data['coordinator']['name'], r.data['coordinator']['email'], r.data['coordinator']['state']),
                         ('Dr. S. Priya', 'priya@mkce.ac.in', 'invited'))
        institution = Institution.objects.get()
        user = User.objects.get(email='priya@mkce.ac.in')
        # A deactivated IQAC Coordinator of this college, with no usable password until they choose one.
        self.assertEqual((user.role, user.institution_id, user.is_active, user.has_usable_password()),
                         (User.Role.IQAC_COORDINATOR, institution.id, False, False))
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ['priya@mkce.ac.in'])
        token = _token(message)
        self.assertNotRegex(message.body, r'(?i)(temporary|initial|your) password (is|:)')  # only a link, no credential
        invitation = CoordinatorInvitation.objects.get()
        self.assertNotEqual(invitation.token_hash, token)  # only a hash is stored
        self.assertNotIn(token, str(r.data))  # never in the API response
        self.assertEqual([e.action for e in CoordinatorEvent.objects.order_by('created_at')], ['invited', 'email_sent'])

    def test_only_ingage_staff_create_institutions(self):
        college = Institution.objects.create(name='Other', coordinator_name='A B', coordinator_email='a@b.in')
        iqac = User.objects.create_user(email='iqac@other.in', username='iqac', password=PASSWORD,
                                        role=User.Role.IQAC_COORDINATOR, institution=college)
        self.client.force_authenticate(iqac)
        self.assertEqual(self._create().status_code, 403)
        self.client.force_authenticate(self.consultant)
        self.assertEqual(self._create(name='Consultant College').status_code, 201)

    def test_a_plain_update_cannot_change_the_coordinator(self):
        institution_id = self._create().data['id']
        r = self.client.patch(f'/api/v1/institutions/{institution_id}', {'coordinator_email': 'evil@x.in'},
                              format='json')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(Institution.objects.get().coordinator_email, 'priya@mkce.ac.in')


class ActivationTests(CoordinatorBase):
    def setUp(self):
        super().setUp()
        self.institution_id = self._create().data['id']
        self.token = _token(mail.outbox[0])

    def test_the_coordinator_chooses_a_password_through_the_link_once(self):
        self.client.force_authenticate(None)
        check = self.client.post('/api/v1/auth/invitation', {'token': self.token}, format='json')
        self.assertEqual((check.status_code, check.data['institution_name'], check.data['needs_password']),
                         (200, 'MKCE', True))
        self.assertEqual(self._accept(self.token, password='123').status_code, 400)  # password rules apply
        r = self._accept(self.token)
        self.assertEqual(r.status_code, 200, r.data)
        user = User.objects.get(email='priya@mkce.ac.in')
        self.assertTrue(user.is_active and user.check_password(NEW_PASSWORD))
        login = self.client.post('/api/v1/auth/login', {'email': 'priya@mkce.ac.in', 'password': NEW_PASSWORD})
        self.assertEqual(login.status_code, 200)
        # Single use: the same link never works again.
        self.assertEqual(self._accept(self.token, password='Another!Passw0rd9').status_code, 400)
        user.refresh_from_db()
        self.assertTrue(user.check_password(NEW_PASSWORD))
        institution = Institution.objects.get()
        self.assertEqual(institution.coordinator_user_id, user.id)
        self.assertEqual(CoordinatorEvent.objects.filter(action='activated').count(), 1)

    def test_invalid_and_expired_links_are_refused(self):
        self.assertEqual(self._accept('not-a-real-token').status_code, 400)
        self.assertEqual(self._accept('').status_code, 400)
        CoordinatorInvitation.objects.update(expires_at=timezone.now() - timedelta(minutes=1))
        r = self._accept(self.token)
        self.assertEqual(r.status_code, 400)
        self.assertIn('expired', str(r.data['token']))
        self.assertFalse(User.objects.get(email='priya@mkce.ac.in').is_active)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get(f'/api/v1/institutions/{self.institution_id}/coordinator').data['state'],
                         'expired')

    def test_resend_rotates_the_link_on_the_same_invitation(self):
        r = self.client.post(f'/api/v1/institutions/{self.institution_id}/coordinator/resend')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(len(mail.outbox), 2)
        fresh = _token(mail.outbox[1])
        self.assertNotEqual(fresh, self.token)
        self.assertEqual(self._accept(self.token).status_code, 400)  # the previous link is dead
        self.assertEqual(self._accept(fresh).status_code, 200)
        self.assertEqual((CoordinatorInvitation.objects.count(), User.objects.filter(email='priya@mkce.ac.in').count()),
                         (1, 1))
        self.client.force_authenticate(self.admin)
        r = self.client.post(f'/api/v1/institutions/{self.institution_id}/coordinator/resend')
        self.assertEqual(r.status_code, 400)  # accepted: nothing to resend


class DeliveryFailureTests(CoordinatorBase):
    def test_a_failed_email_keeps_the_institution_and_a_retry_never_duplicates(self):
        with patch('apps.institutions.coordinator.send_mail', side_effect=ConnectionRefusedError('smtp down')):
            r = self._create()
        self.assertEqual(r.status_code, 201, r.data)
        self.assertFalse(r.data['invitation_email_sent'])
        self.assertEqual(r.data['coordinator']['state'], 'email_failed')
        self.assertTrue(r.data['coordinator']['can_resend'])
        self.assertNotIn('smtp down', str(r.data))  # the raw provider error is not shown
        institution_id = r.data['id']
        for _ in range(2):  # retried twice: still one account, one invitation
            r = self.client.post(f'/api/v1/institutions/{institution_id}/coordinator/resend')
            self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['state'], 'invited')
        self.assertEqual(User.objects.filter(email='priya@mkce.ac.in').count(), 1)
        self.assertEqual(CoordinatorInvitation.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(self._accept(_token(mail.outbox[0])).status_code, 400)  # superseded by the newer link
        self.assertEqual(self._accept(_token(mail.outbox[1])).status_code, 200)
        actions = list(CoordinatorEvent.objects.order_by('created_at').values_list('action', flat=True))
        self.assertEqual(actions, ['invited', 'email_failed', 'resent', 'email_sent', 'resent', 'email_sent',
                                   'activated'])

    def test_nothing_is_emailed_when_the_records_are_not_saved(self):
        with patch('apps.institutions.coordinator._prepare_account', side_effect=RuntimeError('db down')):
            with self.assertRaises(RuntimeError):
                self._create()
        self.assertEqual((Institution.objects.count(), len(mail.outbox)), (0, 0))


class ExistingAccountTests(CoordinatorBase):
    def test_an_unassigned_coordinator_account_joins_only_on_acceptance_and_keeps_its_password(self):
        existing = User.objects.create_user(email='priya@mkce.ac.in', username='priya', password=PASSWORD,
                                            role=User.Role.IQAC_COORDINATOR, institution=None)
        r = self._create()
        self.assertEqual(r.data['coordinator']['state'], 'invited')  # the same answer as for a new person
        existing.refresh_from_db()
        self.assertIsNone(existing.institution_id)  # not before the owner accepts
        token = _token(mail.outbox[0])
        self.client.force_authenticate(None)
        self.assertFalse(self.client.post('/api/v1/auth/invitation', {'token': token}, format='json')
                         .data['needs_password'])
        self.assertEqual(self._accept(token, password='').status_code, 200)
        existing.refresh_from_db()
        self.assertEqual(existing.institution_id, Institution.objects.get().id)
        self.assertTrue(existing.check_password(PASSWORD))  # never changed

    def test_an_account_of_another_college_is_never_moved_and_staff_are_told_what_to_do(self):
        other = Institution.objects.create(name='Other', coordinator_name='A B', coordinator_email='a@b.in')
        elsewhere = User.objects.create_user(email='priya@mkce.ac.in', username='priya', password=PASSWORD,
                                             role=User.Role.IQAC_COORDINATOR, institution=other)
        r = self._create()
        coordinator = r.data['coordinator']
        self.assertEqual((r.status_code, coordinator['state'], coordinator['can_resend']),
                         (201, 'account_unavailable', False))
        self.assertIn('No activation link was created', coordinator['state_label'])
        self.assertNotIn('Other', str(r.data['coordinator']))  # never which account or where it belongs
        elsewhere.refresh_from_db()
        self.assertEqual((elsewhere.institution_id, elsewhere.check_password(PASSWORD)), (other.id, True))
        self.assertNotIn('activate-account', mail.outbox[0].body)  # told whom to contact, no link
        self.assertEqual(CoordinatorInvitation.objects.get().token_hash, '')
        self.assertEqual(User.objects.filter(email__iexact='priya@mkce.ac.in').count(), 1)

    def test_a_staff_account_is_never_turned_into_a_coordinator(self):
        r = self._create(coordinator_email='c@ingage.ai')
        self.assertEqual(r.status_code, 201)
        self.consultant.refresh_from_db()
        self.assertEqual((self.consultant.role, self.consultant.institution_id), (User.Role.CONSULTANT, None))


class ChangeAndIsolationTests(CoordinatorBase):
    def setUp(self):
        super().setUp()
        self.institution_id = self._create().data['id']
        self._accept(_token(mail.outbox[0]))
        self.client.force_authenticate(self.admin)
        self.url = f'/api/v1/institutions/{self.institution_id}/coordinator'

    def test_correcting_the_name_of_the_same_person_changes_no_account(self):
        r = self.client.post(self.url, {'coordinator_name': 'Dr. S. Priya Raman',
                                        'coordinator_email': 'priya@mkce.ac.in'}, format='json')
        self.assertEqual((r.status_code, r.data['state'], r.data['name']), (200, 'active', 'Dr. S. Priya Raman'))
        self.assertEqual(len(mail.outbox), 1)  # no new invitation
        self.assertTrue(CoordinatorEvent.objects.filter(action='name_updated').exists())

    def test_a_new_person_gets_access_only_by_accepting_and_the_previous_account_is_untouched(self):
        old = User.objects.get(email='priya@mkce.ac.in')
        r = self.client.post(self.url, {'coordinator_name': 'K. Arun', 'coordinator_email': 'arun@mkce.ac.in'},
                             format='json')
        self.assertEqual((r.status_code, r.data['state']), (200, 'invited'))
        institution = Institution.objects.get()
        self.assertEqual((institution.coordinator_email, institution.coordinator_user_id), ('arun@mkce.ac.in', None))
        new = User.objects.get(email='arun@mkce.ac.in')
        self.assertFalse(new.is_active)  # no access until accepted
        old.refresh_from_db()
        self.assertTrue(old.is_active and old.institution_id == institution.id)  # never silently removed
        changed = CoordinatorEvent.objects.get(action='changed')
        self.assertEqual(changed.data['previous']['email'], 'priya@mkce.ac.in')

    def test_only_staff_manage_the_coordinator_and_another_college_sees_nothing(self):
        coordinator = User.objects.get(email='priya@mkce.ac.in')
        self.client.force_authenticate(coordinator)
        self.assertEqual(self.client.get(self.url).status_code, 200)  # their own college
        self.assertEqual(self.client.post(self.url, {'coordinator_name': 'X Y', 'coordinator_email': 'x@y.in'},
                                          format='json').status_code, 403)
        other = Institution.objects.create(name='Other', coordinator_name='A B', coordinator_email='a@b.in')
        self.assertEqual(self.client.get(f'/api/v1/institutions/{other.id}/coordinator').status_code, 403)
        self.assertEqual(self.client.get(f'/api/v1/institutions/{other.id}').status_code, 403)
        listed = self.client.get('/api/v1/institutions').data
        rows = listed['results'] if isinstance(listed, dict) else listed
        self.assertEqual([row['id'] for row in rows], [self.institution_id])


class SprintGateTests(CoordinatorBase):
    def test_a_sprint_needs_the_institutions_coordinator(self):
        bare = Institution.objects.create(name='No Coordinator College')
        r = self.client.post('/api/v1/sprints', {'institution_id': str(bare.id), 'academic_year': '2026-27'},
                             format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('no IQAC Coordinator', str(r.data['institution_id']))
        self.assertFalse(Sprint.objects.exists())
        ready_id = self._create().data['id']  # invited, not yet accepted: configured is enough to start
        r = self.client.post('/api/v1/sprints', {'institution_id': ready_id, 'academic_year': '2026-27'},
                             format='json')
        self.assertEqual(r.status_code, 201, r.data)

    def test_each_institution_shows_its_own_coordinator(self):
        a = self._create(name='College A', coordinator_name='Anu Devi', coordinator_email='anu@a.in').data
        b = self._create(name='College B', coordinator_name='Bala Kumar', coordinator_email='bala@b.in').data
        rows = {row['id']: row['coordinator'] for row in self.client.get('/api/v1/institutions').data}
        self.assertEqual((rows[a['id']]['name'], rows[b['id']]['name']), ('Anu Devi', 'Bala Kumar'))


@override_settings(COORDINATOR_INVITATION_HOURS=1)
class ExpiryWindowTests(CoordinatorBase):
    def test_the_link_lives_for_the_configured_hours(self):
        self._create()
        invitation = CoordinatorInvitation.objects.get()
        self.assertAlmostEqual((invitation.expires_at - timezone.now()).total_seconds(), 3600, delta=60)


class CoordinatorPanelTests(CoordinatorBase):
    """The Institution DNA coordinator panel: POST/GET /institutions/<id>/coordinator and .../resend."""

    def setUp(self):
        super().setUp()
        self.institution_id = self._create().data['id']
        self.url = f'/api/v1/institutions/{self.institution_id}/coordinator'
        self.client.force_authenticate(self.consultant)

    def _set(self, name='K. Arun', email='arun@mkce.ac.in'):
        return self.client.post(self.url, {'coordinator_name': name, 'coordinator_email': email}, format='json')

    def test_staff_change_the_coordinator_and_a_new_invitation_is_emailed(self):
        r = self._set()
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual((r.data['state'], r.data['invitation_email_sent'], r.data['changed'], r.data['can_resend']),
                         ('invited', True, True, True))
        self.assertEqual(mail.outbox[-1].to, ['arun@mkce.ac.in'])
        self.assertIn('activate-account?token=', mail.outbox[-1].body)
        panel = self.client.get(self.url).data
        self.assertEqual((panel['name'], panel['email']), ('K. Arun', 'arun@mkce.ac.in'))
        self.assertIn('changed', [e['action'] for e in panel['events']])

    def test_field_errors_name_their_field_and_change_nothing(self):
        for body, field in (({'name': 'R2'}, 'coordinator_name'), ({'email': 'arun@'}, 'coordinator_email'),
                            ({'name': ''}, 'coordinator_name')):
            r = self._set(**body)
            self.assertEqual(r.status_code, 400, body)
            self.assertIn(field, r.data, body)
        self.assertEqual(Institution.objects.get().coordinator_email, 'priya@mkce.ac.in')

    def test_an_unavailable_email_is_refused_before_anything_changes(self):
        other = Institution.objects.create(name='Other College', coordinator_name='A B', coordinator_email='a@b.in')
        User.objects.create_user(email='taken@other.in', username='taken', password=PASSWORD,
                                 role=User.Role.IQAC_COORDINATOR, institution=other)
        outbox = len(mail.outbox)
        for email in ('taken@other.in', 'c@ingage.ai'):  # another college's account; InGage staff
            r = self._set(email=email)
            self.assertEqual(r.status_code, 400, email)
            message = r.data['coordinator_email'][0]
            self.assertIn('No activation link was created', message)
            self.assertNotIn('Other College', message)  # nothing about the account
        institution = Institution.objects.get(pk=self.institution_id)
        self.assertEqual(institution.coordinator_email, 'priya@mkce.ac.in')  # unchanged
        self.assertEqual(CoordinatorInvitation.objects.filter(institution=institution, status='pending').count(), 1)
        self.assertEqual(len(mail.outbox), outbox)  # nothing sent
        self.assertEqual(User.objects.get(email='taken@other.in').institution_id, other.id)  # never moved

    def test_resend_rotates_the_link_and_a_failed_email_says_so(self):
        first = _token(mail.outbox[-1])
        with patch('apps.institutions.coordinator.send_mail', side_effect=OSError('smtp down')):
            r = self.client.post(f'{self.url}/resend')
        self.assertEqual((r.status_code, r.data['state'], r.data['invitation_email_sent'], r.data['can_resend']),
                         (200, 'email_failed', False, True))
        self.assertNotIn('smtp down', str(r.data))
        r = self.client.post(f'{self.url}/resend')
        self.assertEqual((r.data['state'], r.data['invitation_email_sent']), ('invited', True))
        self.assertEqual(self._accept(first).status_code, 400)  # the earlier link no longer works
        self.assertEqual(self._accept(_token(mail.outbox[-1])).status_code, 200)
        self.client.force_authenticate(self.consultant)
        self.assertFalse(self.client.get(self.url).data['can_resend'])  # accepted: nothing to resend

    def test_only_staff_edit_and_only_the_college_reads(self):
        college = Institution.objects.get(pk=self.institution_id)
        member = User.objects.create_user(email='member@mkce.ac.in', username='member', password=PASSWORD,
                                          role=User.Role.IQAC_COORDINATOR, institution=college)
        other = Institution.objects.create(name='Other', coordinator_name='A B', coordinator_email='a@b.in')
        outsider = User.objects.create_user(email='o@other.in', username='outsider', password=PASSWORD,
                                            role=User.Role.IQAC_COORDINATOR, institution=other)
        self.client.force_authenticate(member)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(self._set().status_code, 403)
        self.assertEqual(self.client.post(f'{self.url}/resend').status_code, 403)
        self.client.force_authenticate(outsider)
        for response in (self.client.get(self.url), self._set(), self.client.post(f'{self.url}/resend')):
            self.assertEqual(response.status_code, 403)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.url).status_code, 401)
        self.assertEqual(Institution.objects.get(pk=self.institution_id).coordinator_email, 'priya@mkce.ac.in')

    def test_college_users_never_see_the_staff_only_unavailable_state(self):
        other = Institution.objects.create(name='Other', coordinator_name='A B', coordinator_email='a@b.in')
        User.objects.create_user(email='taken@other.in', username='taken', password=PASSWORD,
                                 role=User.Role.IQAC_COORDINATOR, institution=other)
        self.client.force_authenticate(self.admin)
        created = self._create(name='Third College', coordinator_email='taken@other.in').data
        member = User.objects.create_user(email='m@third.in', username='m3', password=PASSWORD,
                                          role=User.Role.IQAC_COORDINATOR,
                                          institution=Institution.objects.get(pk=created['id']))
        self.client.force_authenticate(member)
        response = self.client.get(f"/api/v1/institutions/{created['id']}/coordinator")
        state = response.data['state']
        self.assertEqual(state, 'pending_setup')


class ForgotPasswordBeforeActivationTests(CoordinatorBase):
    def test_forgot_password_sends_a_fresh_activation_link_to_an_invited_coordinator(self):
        self._create()
        first = _token(mail.outbox[0])
        self.client.force_authenticate(None)
        r = self.client.post('/api/v1/auth/password-reset', {'email': 'PRIYA@mkce.ac.in'}, format='json')
        unknown = self.client.post('/api/v1/auth/password-reset', {'email': 'nobody@mkce.ac.in'}, format='json')
        self.assertEqual((r.status_code, r.data), (unknown.status_code, unknown.data))  # the same reply
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(mail.outbox[1].to, ['priya@mkce.ac.in'])
        fresh = _token(mail.outbox[1])
        self.assertEqual(self._accept(first).status_code, 400)  # the earlier link is replaced
        self.assertEqual(self._accept(fresh).status_code, 200)
        self.assertEqual(CoordinatorInvitation.objects.count(), 1)


class CollegeUserBoundaryTests(CoordinatorBase):
    """A college's own IQAC Coordinator edits the institution's basic information -- never the coordinator's name
    or email, and never sends or resends an invitation (only InGage staff do)."""

    def test_basic_information_yes_coordinator_and_invitations_no(self):
        institution_id = self._create().data['id']
        college = Institution.objects.get(pk=institution_id)
        member = User.objects.create_user(email='member@mkce.ac.in', username='member', password=PASSWORD,
                                          role=User.Role.IQAC_COORDINATOR, institution=college)
        self.client.force_authenticate(member)
        outbox = len(mail.outbox)

        r = self.client.patch(f'/api/v1/institutions/{institution_id}', {'city': 'Coimbatore'}, format='json')
        self.assertEqual(r.status_code, 200, r.data)  # basic information: allowed

        for body in ({'coordinator_name': 'Someone Else'}, {'coordinator_email': 'other@mkce.ac.in'},
                     {'city': 'Salem', 'coordinator_email': 'other@mkce.ac.in'}):
            r = self.client.patch(f'/api/v1/institutions/{institution_id}', body, format='json')
            self.assertEqual(r.status_code, 400, body)  # not through the profile update
        url = f'/api/v1/institutions/{institution_id}/coordinator'
        self.assertEqual(self.client.post(url, {'coordinator_name': 'Someone Else',
                                                'coordinator_email': 'other@mkce.ac.in'}, format='json').status_code, 403)
        self.assertEqual(self.client.post(f'{url}/resend').status_code, 403)
        self.assertEqual(self.client.get(url).status_code, 200)  # they can see who it is

        college.refresh_from_db()
        self.assertEqual((college.city, college.coordinator_name, college.coordinator_email),
                         ('Coimbatore', 'Dr. S. Priya', 'priya@mkce.ac.in'))
        self.assertEqual(len(mail.outbox), outbox)  # no invitation was sent
        self.assertFalse(User.objects.filter(email='other@mkce.ac.in').exists())
