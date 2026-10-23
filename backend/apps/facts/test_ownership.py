"""Role-based ownership of facts and gaps (apps/facts/ownership.py): who may act, assignment, closing gaps
through the underlying fix, evidence submitter/reviewer separation, and sprint-wide readiness."""
import tempfile
from unittest.mock import patch
from datetime import date, timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.documents.constants import humanize_document_type
from apps.documents.models import Document
from apps.gaps.models import GapEvent, GapItem
from apps.gaps.services import generate_gaps_for_sprint
from apps.institutions.models import Institution
from apps.sprints.models import Sprint

from .models import EvidenceRequest, ExtractedFact, FactReviewHistory

R = User.Role


class _Base(APITestCase):
    def setUp(self):
        self.college = Institution.objects.create(name='MKCE', city='Karur', state='TN')
        self.other = Institution.objects.create(name='Other', city='X', state='Y')
        self.sprint = Sprint.objects.create(institution=self.college, mode=Sprint.SprintMode.VERIFIED_CRI)
        mk = self._user
        self.hod, self.hod2 = mk('hod', R.HOD), mk('hod2', R.HOD)
        self.registrar, self.iqac = mk('registrar', R.REGISTRAR), mk('iqac', R.IQAC_COORDINATOR)
        self.admin, self.viewer = mk('admin', R.INSTITUTION_ADMIN), mk('viewer', R.VIEWER)
        self.consultant = mk('consultant', R.CONSULTANT, institution=None)
        self.outsider_admin = mk('outadmin', R.INSTITUTION_ADMIN, institution=self.other)
        self.inactive_hod = mk('oldhod', R.HOD)
        self.inactive_hod.is_active = False
        self.inactive_hod.save()

    def _user(self, name, role, institution='default'):
        return User.objects.create_user(
            email=f'{name}@test.edu', username=name, password='Str0ng!DevPassw0rd', first_name=name.title(),
            last_name='User', role=role, institution=self.college if institution == 'default' else institution)

    def _fact(self, **over):
        values = {'sprint': self.sprint, 'field_name': 'Faculty certification %', 'field_key': 'fdp_pct',
                  'value': 62.5, 'owner_role': 'HOD', 'source_page': '45', 'confidence_score': 0.9,
                  'source_snippet': '120 out of 192 faculty completed the FDP.', **over}
        return ExtractedFact.objects.create(**values)

    def _as(self, user):
        self.client.force_authenticate(user)

    def _post(self, user, url, body=None):
        self._as(user)
        return self.client.post(url, body or {}, format='json')


class FactOwnershipTests(_Base):
    def test_only_the_owner_role_an_admin_or_staff_may_act(self):
        for user, code in ((self.registrar, 403), (self.iqac, 403), (self.viewer, 403), (self.outsider_admin, 403),
                           (self.hod, 200)):
            fact = self._fact(field_key=f'k_{user.username}')
            r = self._post(user, f'/api/v1/facts/{fact.id}/confirm')
            self.assertEqual(r.status_code, code, (user.role, r.data))
        r = self._post(self.registrar, f'/api/v1/facts/{self._fact(field_key="k2").id}/correct', {'new_value': 1})
        self.assertIn('Head of Department, an Institution Admin or InGage staff', r.data['detail'])
        for user in (self.admin, self.consultant):
            fact = self._fact(field_key=f'over_{user.username}')
            self.assertEqual(self._post(user, f'/api/v1/facts/{fact.id}/confirm').status_code, 200)

    def test_owner_role_is_matched_case_insensitively_and_unowned_facts_go_to_coordinators(self):
        self.assertEqual(self._post(self.hod, f'/api/v1/facts/{self._fact(owner_role="hod").id}/confirm').status_code, 200)
        unowned = self._fact(field_key='campus', owner_role='')
        self.assertEqual(self._post(self.hod, f'/api/v1/facts/{unowned.id}/confirm').status_code, 403)
        self.assertEqual(self._post(self.iqac, f'/api/v1/facts/{unowned.id}/confirm').status_code, 200)

    def test_the_list_says_who_may_act_for_the_requesting_user(self):
        self._fact()
        self._as(self.registrar)
        row = self.client.get(f'/api/v1/sprints/{self.sprint.id}/facts').data['results'][0]
        self.assertEqual((row['can_act'], row['owner_role_label']), (False, 'Head of Department'))
        self.assertIn('Only the Head of Department', row['act_blocked_reason'])
        self._as(self.hod)
        self.assertTrue(self.client.get(f'/api/v1/sprints/{self.sprint.id}/facts').data['results'][0]['can_act'])

    def test_a_rejection_needs_a_reason_and_turns_the_gap_into_needs_replacement(self):
        fact = self._fact()
        generate_gaps_for_sprint(self.sprint)
        gap = GapItem.objects.get(source_fact=fact, gap_type='unconfirmed_fact')
        self.assertEqual(self._post(self.hod, f'/api/v1/facts/{fact.id}/reject').status_code, 400)
        self.assertEqual(self._post(self.hod, f'/api/v1/facts/{fact.id}/reject',
                                    {'reason': 'Counts only one campus.'}).status_code, 200)
        gap.refresh_from_db()
        self.assertEqual(gap.status, 'needs_replacement')  # still active: its CRI penalty stays
        self.assertIn('needs_replacement', GapItem.ACTIVE_STATUSES)
        self.assertEqual(GapEvent.objects.get(gap=gap).note, 'Counts only one campus.')
        # The rejected value can't be "resolved" away; a confirmed replacement closes it.
        self.assertEqual(self._post(self.hod, f'/api/v1/gaps/{gap.id}/resolve').status_code, 400)
        replacement = self._fact(value=64.0, source_page='46')
        self._post(self.hod, f'/api/v1/facts/{replacement.id}/confirm')
        gap.refresh_from_db()
        self.assertEqual(gap.status, 'resolved')
        self.assertIn('Replaced', gap.resolution)


class AssignmentTests(_Base):
    def test_coordinators_assign_and_reassign_to_people_who_may_act(self):
        fact = self._fact()
        due = str(date.today() + timedelta(days=7))
        r = self._post(self.iqac, f'/api/v1/facts/{fact.id}/assign', {'assigned_to': str(self.hod.id), 'due_date': due,
                                                                       'note': 'Department data.'})
        self.assertEqual((r.status_code, r.data['assigned_to_name'], r.data['due_date']), (200, 'Hod User', due))
        r = self._post(self.admin, f'/api/v1/facts/{fact.id}/assign', {'assigned_to': str(self.hod2.id)})
        self.assertEqual(r.data['assigned_to_name'], 'Hod2 User')
        rows = FactReviewHistory.objects.filter(fact=fact, action='assigned').order_by('created_at')
        self.assertEqual([(h.new_value['from'], h.new_value['to']['name']) for h in rows],
                         [(None, 'Hod User'), ({'id': str(self.hod.id), 'name': 'Hod User'}, 'Hod2 User')])
        # Unassign: the work stays in the queue, visible to coordinators.
        self.assertIsNone(self._post(self.iqac, f'/api/v1/facts/{fact.id}/assign', {'assigned_to': None}).data['assigned_to'])

    def test_assignment_is_refused_to_the_wrong_people_and_by_non_coordinators(self):
        fact = self._fact()
        url = f'/api/v1/facts/{fact.id}/assign'
        for who in (self.registrar, self.inactive_hod, self.outsider_admin, self.viewer):
            r = self._post(self.iqac, url, {'assigned_to': str(who.id)})
            self.assertEqual(r.status_code, 400, who.username)
        self.assertEqual(self._post(self.hod, url, {'assigned_to': str(self.hod2.id)}).status_code, 400)  # not a coordinator
        self.assertEqual(self._post(self.outsider_admin, url, {'assigned_to': str(self.hod.id)}).status_code, 403)
        past = str(date.today() - timedelta(days=1))
        self.assertEqual(self._post(self.iqac, url, {'assigned_to': str(self.hod.id), 'due_date': past}).status_code, 400)
        self.assertEqual(self._post(self.iqac, url, {'assigned_to': str(self.admin.id)}).status_code, 200)

    def test_assigning_never_widens_who_may_act(self):
        fact = self._fact()
        self._post(self.iqac, f'/api/v1/facts/{fact.id}/assign', {'assigned_to': str(self.hod.id)})
        self.assertEqual(self._post(self.iqac, f'/api/v1/facts/{fact.id}/confirm').status_code, 403)  # IQAC assigns, can't confirm

    def test_gaps_are_assigned_too_with_their_history(self):
        fact = self._fact()
        generate_gaps_for_sprint(self.sprint)
        gap = GapItem.objects.get(source_fact=fact, gap_type='unconfirmed_fact')
        r = self._post(self.iqac, f'/api/v1/gaps/{gap.id}/assign', {'assigned_to': str(self.hod.id), 'note': 'Please.'})
        self.assertEqual((r.status_code, r.data['assigned_to_name']), (200, 'Hod User'))
        self.assertEqual([e['action'] for e in r.data['events']], ['assigned'])
        self.assertEqual(self._post(self.iqac, f'/api/v1/gaps/{gap.id}/assign',
                                    {'assigned_to': str(self.registrar.id)}).status_code, 400)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix='ownership-tests-'))
class GapClosureTests(_Base):
    def test_gap_actions_follow_the_owner_of_their_fact_or_document(self):
        fact = self._fact()
        generate_gaps_for_sprint(self.sprint)
        gap = GapItem.objects.get(source_fact=fact, gap_type='unconfirmed_fact')
        self.assertEqual(self._post(self.registrar, f'/api/v1/gaps/{gap.id}/skip', {'resolution': 'n/a'}).status_code, 403)
        self.assertEqual(self._post(self.hod, f'/api/v1/gaps/{gap.id}/skip', {'resolution': 'Not collected.'}).status_code, 200)
        doc = Document.objects.create(sprint=self.sprint, document_type='hr_records', owner_role='registrar',
                                      original_filename='old.pdf', uploaded_at=timezone.now() - timedelta(days=900))
        generate_gaps_for_sprint(self.sprint)
        stale = GapItem.objects.get(related_document=doc, gap_type='stale_data')
        self.assertEqual(self._post(self.hod, f'/api/v1/gaps/{stale.id}/skip', {'resolution': 'x'}).status_code, 403)
        missing = GapItem.objects.get(gap_type='missing_document', title=f'Missing {humanize_document_type("naac_ssr")}')
        self._as(self.hod)
        row = self.client.get(f'/api/v1/gaps/{missing.id}').data
        self.assertEqual((row['owner_role'], row['can_act']), ('iqac_coordinator', False))  # the checklist owner

    def test_a_needs_confirmation_gap_closes_by_confirming_the_fact_not_by_resolve(self):
        fact = self._fact()
        generate_gaps_for_sprint(self.sprint)
        gap = GapItem.objects.get(source_fact=fact, gap_type='unconfirmed_fact')
        r = self._post(self.hod, f'/api/v1/gaps/{gap.id}/resolve', {'resolution': 'done'})
        self.assertEqual(r.status_code, 400)
        self.assertIn('Confirm or correct the fact', r.data['detail'])
        self.assertEqual(self._post(self.hod, f'/api/v1/gaps/{gap.id}/skip').status_code, 400)  # needs a reason
        self._post(self.hod, f'/api/v1/facts/{fact.id}/confirm')
        gap.refresh_from_db()
        self.assertEqual(gap.status, 'resolved')
        self.assertEqual(GapEvent.objects.get(gap=gap).action, 'auto_resolved')

    def _conflict(self):
        a = self._fact(value=62.5)
        b = self._fact(value=58.0, source_page='12', source_snippet='112 of 192 completed.')
        gap = GapItem.objects.create(sprint=self.sprint, gap_type='conflict', title='Conflicting values for FDP %',
                                     priority='high', source_fact=a, conflict_fact_b=b, conflict_value_a=62.5,
                                     conflict_value_b=58.0)
        return a, b, gap

    def test_a_conflict_closes_only_when_reconciled_or_explicitly_unresolved_with_a_reason(self):
        a, b, gap = self._conflict()
        r = self._post(self.hod, f'/api/v1/gaps/{gap.id}/resolve', {'resolution': 'Looked at it.'})
        self.assertIn('still disagree', r.data['detail'])
        self.assertIn('Say why', self._post(self.hod, f'/api/v1/gaps/{gap.id}/skip').data['detail'])
        self._post(self.hod, f'/api/v1/facts/{b.id}/correct', {'new_value': 62.5})
        gap.refresh_from_db()
        self.assertEqual(gap.status, 'resolved')  # the values agree now
        self.assertIn('Reconciled', gap.resolution)

        c, d = self._fact(field_key='labs', value=10), self._fact(field_key='labs', value=12)
        other = GapItem.objects.create(sprint=self.sprint, gap_type='conflict', title='Conflicting values for labs',
                                       priority='high', source_fact=c, conflict_fact_b=d)
        r = self._post(self.hod, f'/api/v1/gaps/{other.id}/skip', {'resolution': 'Closed unresolved: two campuses.'})
        self.assertEqual(r.status_code, 200)
        other.refresh_from_db()
        self.assertEqual((other.status, other.resolution), ('skipped', 'Closed unresolved: two campuses.'))

    def test_rejecting_one_side_reconciles_the_conflict(self):
        _a, b, gap = self._conflict()
        self._post(self.hod, f'/api/v1/facts/{b.id}/reject', {'reason': 'Draft figure.'})
        gap.refresh_from_db()
        self.assertEqual(gap.status, 'resolved')

    def test_missing_and_stale_document_gaps_close_after_the_document_is_reviewed(self):
        generate_gaps_for_sprint(self.sprint)
        missing = GapItem.objects.get(gap_type='missing_document', title=f'Missing {humanize_document_type("naac_ssr")}')
        self.assertIn('Upload the', self._post(self.iqac, f'/api/v1/gaps/{missing.id}/resolve').data['detail'])
        doc = Document.objects.create(sprint=self.sprint, document_type='unclassified', original_filename='ssr.pdf',
                                      uploaded_at=timezone.now())
        self.assertEqual(self._post(self.iqac, f'/api/v1/documents/{doc.id}/confirm-category',
                                    {'category': 'naac_ssr'}).status_code, 200)
        missing.refresh_from_db()
        self.assertEqual(missing.status, 'resolved')
        generate_gaps_for_sprint(self.sprint)  # and the detector doesn't raise it again
        self.assertFalse(GapItem.objects.filter(gap_type='missing_document', title=f'Missing {humanize_document_type("naac_ssr")}',
                                                status__in=GapItem.ACTIVE_STATUSES).exists())

        old = Document.objects.create(sprint=self.sprint, document_type='aqar', owner_role='iqac_coordinator',
                                      original_filename='aqar-2019.pdf', uploaded_at=timezone.now() - timedelta(days=900))
        generate_gaps_for_sprint(self.sprint)
        stale = GapItem.objects.get(related_document=old, gap_type='stale_data')
        self.assertIn('newer version', self._post(self.iqac, f'/api/v1/gaps/{stale.id}/resolve').data['detail'])
        new = Document.objects.create(sprint=self.sprint, document_type='unclassified', original_filename='aqar-2025.pdf',
                                      uploaded_at=timezone.now())
        self._post(self.iqac, f'/api/v1/documents/{new.id}/confirm-category', {'category': 'aqar_report'})
        stale.refresh_from_db()
        self.assertEqual(stale.status, 'resolved')
        generate_gaps_for_sprint(self.sprint)
        self.assertFalse(GapItem.objects.filter(related_document=old, status__in=GapItem.ACTIVE_STATUSES).exists())


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix='ownership-evidence-'))
class EvidenceSeparationTests(_Base):
    def test_only_the_assignee_submits_and_only_a_different_owner_side_reviewer_decides(self):
        fact = self._fact()
        r = self._post(self.iqac, f'/api/v1/facts/{fact.id}/request-evidence',
                       {'description': 'Signed register.', 'assigned_to': str(self.hod.id)})
        self.assertEqual(r.status_code, 200, r.data)  # a coordinator may chase evidence
        req = EvidenceRequest.objects.get(fact=fact)
        upload = lambda user: self._post_file(user, req)  # noqa: E731
        self.assertEqual(upload(self.hod2).status_code, 400)  # not the assignee
        self.assertEqual(upload(self.hod).status_code, 200)
        link = req.evidence.get()
        decide = lambda user, **b: self._post(user, f'/api/v1/evidence-requests/{req.id}/review',  # noqa: E731
                                              {'decision': 'accept', 'evidence_id': str(link.id), **b})
        self.assertIn('other than the person who submitted', decide(self.hod).data['detail'])
        self.assertIn('Only the Head of Department', decide(self.registrar).data['detail'])  # not an owner
        self.assertIn('Only the Head of Department', decide(self.iqac).data['detail'])  # requester, not an owner
        self.assertEqual(decide(self.hod2).status_code, 200)  # another HOD: same role, different person
        fact.refresh_from_db()
        self.assertEqual(fact.status, 'confirmed')
        self.assertEqual([e.action for e in req.events.order_by('created_at')],
                         ['created', 'assigned', 'evidence_submitted', 'fact_updated', 'accepted'])

    def _post_file(self, user, req):
        self._as(user)
        f = SimpleUploadedFile('register.pdf', b'%PDF-1.4 register', content_type='application/pdf')
        # Don't queue the upload's extraction (no Celery broker in tests / CI), as the other evidence tests do.
        with patch('apps.extraction.views.dispatch_job', side_effect=lambda job: job):
            return self.client.post(f'/api/v1/evidence-requests/{req.id}/submit', {'file': f, 'source_page': '3'},
                                    format='multipart')

    def test_reassigning_the_request_is_kept_in_its_history(self):
        fact = self._fact()
        self._post(self.iqac, f'/api/v1/facts/{fact.id}/request-evidence', {'description': 'x', 'assigned_to': str(self.hod.id)})
        req = EvidenceRequest.objects.get(fact=fact)
        self._post(self.iqac, f'/api/v1/evidence-requests/{req.id}/assign', {'assigned_to': str(self.hod2.id)})
        moves = [e.data['to']['name'] for e in req.events.filter(action='assigned').order_by('created_at')]
        self.assertEqual(moves, ['Hod User', 'Hod2 User'])


class SprintReadinessTests(_Base):
    def test_readiness_covers_every_owner_role_whoever_asks(self):
        hod_fact = self._fact()
        reg_fact = self._fact(field_key='students', field_name='Students', value=1200, owner_role='registrar')
        generate_gaps_for_sprint(self.sprint)
        self._post(self.iqac, f'/api/v1/facts/{hod_fact.id}/assign', {'assigned_to': str(self.hod.id),
                                                                       'due_date': str(date.today())})
        self._as(self.hod)  # an HOD sees the whole sprint's state, not just their own share
        s = self.client.get(f'/api/v1/sprints/{self.sprint.id}/work-summary').data
        self.assertFalse(s['ready_for_baseline_review'])
        roles = {r['role']: r for r in s['by_role']}
        self.assertEqual((roles['hod']['pending_facts'], roles['registrar']['pending_facts']), (1, 1))
        people = {r['name']: r for r in s['by_assignee']}
        self.assertEqual((people['Hod User']['pending_facts'], people['Hod User']['overdue']), (1, 0))
        self.assertEqual(people['Unassigned']['pending_facts'], 1)  # the registrar's fact: unassigned, still counted
        # The HOD's own work done is not enough: the registrar's fact still blocks.
        self._post(self.hod, f'/api/v1/facts/{hod_fact.id}/confirm')
        self.assertFalse(self.client.get(f'/api/v1/sprints/{self.sprint.id}/work-summary').data['ready_for_baseline_review'])
        self._post(self.registrar, f'/api/v1/facts/{reg_fact.id}/confirm')
        self._as(self.hod)
        s = self.client.get(f'/api/v1/sprints/{self.sprint.id}/work-summary').data
        self.assertTrue(s['ready_for_baseline_review'], s['blockers'])

    def test_another_college_cannot_read_it(self):
        self._as(self.outsider_admin)
        self.assertIn(self.client.get(f'/api/v1/sprints/{self.sprint.id}/work-summary').status_code, (403, 404))

