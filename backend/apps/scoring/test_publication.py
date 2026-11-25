"""The published result and the draft gate (capability/publication.py), on the product's own flow."""
from django.test import override_settings
from rest_framework.test import APIClient, APITestCase

from . import test_next_steps as steps_tests
from . import test_product_flow as flow
from .models import CapabilityExecution, CapabilityExplanation, CapabilityPublication, CapabilityRun


@override_settings(**flow.SETTINGS)
class PublicationTests(APITestCase):
    publication_rules = True   # the real rule: publication_fixtures leaves it in place
    setUp_flow = flow.ProductFlowTests.setUp
    for _name in [n for n in dir(flow.ProductFlowTests) if n.startswith('reply_') or n in (
            'model', 'service', 'assess', 'post', 'run_queued', 'document')]:
        locals()[_name] = getattr(flow.ProductFlowTests, _name)
    del _name
    reply_next_step = steps_tests.NextStepsFlowTests.reply_next_step

    def setUp(self):
        self.setUp_flow()
        from apps.accounts.models import User
        self.staff = User.objects.create_user(username='consultant', email='consultant@example.com',
                                              role=User.Role.CONSULTANT)
        self.staff_client = APIClient()
        self.staff_client.force_authenticate(self.staff)

    # ------------------------------------------------------------------ helpers

    def publish(self, run, client=None, expect=200):
        response = (client or self.staff_client).post(f'{self.base}/publication',
                                                      {'run_id': str(run.pk) if run else None}, format='json')
        self.assertEqual(response.status_code, expect, getattr(response, 'data', None))
        return response

    def report(self, run, client=None, audience='summary', file='html'):
        return (client or self.client).get(f'{self.base}/{run.pk}/report', {'audience': audience, 'file': file})

    def readiness(self, run, client=None):
        return (client or self.staff_client).get(f'{self.base}/{run.pk}/report-readiness')

    def write_text(self, run, final=False):
        options = {'final': True} if final else {}
        for operation in ('explain', 'next_steps'):
            self.post(f'{self.base}/{run.pk}/second-layer/jobs', {'operation': operation, 'options': options},
                      key=f'{operation}-{final}', expect=202)
            self.run_queued()

    # ------------------------------------------------------------------ the published result

    def test_a_college_sees_only_what_staff_publish(self):
        run = self.assess()
        listed = self.client.get(self.base).data
        self.assertIsNone(listed['published'])
        # Completed but not published: the coordinator can't read its score, its evidence or its reports.
        for url in ('', '/evidence', '/report', '/report-readiness', '/recommendations'):
            self.assertEqual(self.client.get(f'{self.base}/{run.pk}{url}').status_code, 403, url)
        # Staff read it, and the coordinator can't publish.
        self.assertEqual(self.staff_client.get(f'{self.base}/{run.pk}').status_code, 200)
        self.publish(run, client=self.client, expect=403)
        self.assertEqual(self.client.get(f'{self.base}/publication').status_code, 403)

        first = self.publish(run).data
        self.assertTrue(first['changed'])
        self.assertEqual(first['published']['run_id'], str(run.pk))
        self.assertEqual(first['published']['stage'], 'provisional')
        self.assertFalse(self.publish(run).data['changed'])   # the same run again changes nothing
        self.assertEqual(CapabilityPublication.objects.count(), 1)

        self.assertEqual(self.client.get(f'{self.base}/{run.pk}').status_code, 200)
        self.assertEqual(self.client.get(self.base).data['published']['run_id'], str(run.pk))

        # Withdrawn: the coordinator is refused again; the history keeps both choices, newest first.
        withdrawn = self.publish(None).data
        self.assertIsNone(withdrawn['published'])
        self.assertEqual([h['withdrawn'] for h in withdrawn['history']], [True, False])
        self.assertEqual(self.client.get(f'{self.base}/{run.pk}').status_code, 403)
        self.assertFalse(self.publish(None).data['changed'])

        row = CapabilityPublication.objects.first()
        with self.assertRaises(ValueError):
            row.save()
        with self.assertRaises(ValueError):
            row.delete()

    def test_only_a_completed_run_of_this_assessment_can_be_published(self):
        from .capability.storage import create_run
        pending = create_run(institution_id=self.institution.pk, sprint_id=self.sprint.pk)
        CapabilityExecution.objects.create(run=pending, sprint=self.sprint, idempotency_key='pending',
                                           request_hash='pending', status='running')
        self.publish(pending, expect=400)
        # A run that has not completed carries no score: the coordinator still sees it in progress.
        self.assertEqual(self.client.get(f'{self.base}/{pending.pk}').status_code, 200)
        from apps.sprints.models import Sprint
        other = Sprint.objects.create(institution=self.institution)
        elsewhere = create_run(institution_id=self.institution.pk, sprint_id=other.pk)
        CapabilityExecution.objects.create(run=elsewhere, sprint=other, idempotency_key='x', request_hash='x',
                                           status='completed')
        self.publish(elsewhere, expect=400)
        self.assertFalse(CapabilityPublication.objects.exists())

    def test_a_final_result_is_published_by_staff_and_brings_its_stage_one(self):
        provisional = self.assess()
        self.publish(provisional)
        jobs_url = f'{self.base}/{provisional.pk}/second-layer/jobs'
        self.post(jobs_url, {'operation': 'rejudge', 'options': {'close': True}}, key='close', expect=202)
        final = CapabilityRun.objects.get(pk=self.run_queued()[0].final_run_id)
        # Never published by itself: the college still sees its Stage 1 result.
        self.assertEqual(self.client.get(self.base).data['published']['run_id'], str(provisional.pk))
        self.assertEqual(self.client.get(f'{self.base}/{final.pk}').status_code, 403)
        published = self.publish(final).data['published']
        self.assertEqual((published['stage'], published['provisional_run_id']), ('final', str(provisional.pk)))
        self.assertEqual(self.client.get(f'{self.base}/{final.pk}').status_code, 200)
        # Its Stage 1 run stays readable: the Reports page offers both, and the questions belong to it.
        self.assertEqual(self.client.get(f'{self.base}/{provisional.pk}').status_code, 200)

    # ------------------------------------------------------------------ the draft gate

    def test_reports_wait_for_their_text_and_staff_see_the_draft(self):
        run = self.assess()
        self.publish(run)
        state = self.readiness(run).data
        self.assertFalse(state['ready'])
        self.assertIn('The score explanations have not been written.', state['reasons'])
        self.assertIn('The next steps have not been written.', state['reasons'])
        # The coordinator reads the same state, and can't download either report yet.
        self.assertEqual(self.readiness(run, client=self.client).data['reasons'], state['reasons'])
        for audience in ('summary', 'detailed'):
            for file in ('html', 'pdf'):
                refused = self.report(run, audience=audience, file=file)
                self.assertEqual((refused.status_code, refused.data['detail'].code), (409, 'report_draft'))
        # The technical appendix and the JSON are InGage's, ready or not.
        for audience, file in (('leadership', 'html'), ('evidence', 'pdf'), ('summary', 'json')):
            self.assertEqual(self.report(run, audience=audience, file=file).status_code, 403, (audience, file))
        # Staff get the draft, marked on every page.
        html = self.report(run, client=self.staff_client)
        self.assertEqual((html.status_code, html['X-Report-Draft']), (200, '1'))
        self.assertIn('DRAFT', html.content.decode())
        pdf = self.report(run, client=self.staff_client, file='pdf')
        self.assertEqual((pdf.status_code, pdf['X-Report-Draft']), (200, '1'))
        self.assertEqual(self.report(run, client=self.staff_client, audience='evidence').status_code, 200)

        self.write_text(run)
        state = self.readiness(run).data
        self.assertTrue(state['ready'], state)
        self.assertEqual(state['next_steps']['written_steps'], state['next_steps']['steps'])
        for audience in ('summary', 'detailed'):
            ready = self.report(run, audience=audience)
            self.assertEqual(ready.status_code, 200, audience)
            self.assertNotIn('X-Report-Draft', ready)
            self.assertNotIn('DRAFT', ready.content.decode())
        self.assertEqual(self.report(run, file='pdf').status_code, 200)

        # An area's text on plain wording makes it a draft again (the newest stored explanations count).
        row = CapabilityExplanation.objects.filter(run=run).order_by('-created_at').first()
        payload = dict(row.payload)
        area = next(iter(payload['areas']))
        payload['areas'] = {**payload['areas'], area: {**payload['areas'][area], 'fallback': True}}
        payload['requirements'] = {k: {**v, 'fallback': True} for k, v in list(payload['requirements'].items())[:2]}
        payload['requirements'].update({k: v for k, v in row.payload['requirements'].items()
                                        if k not in payload['requirements']})
        CapabilityExplanation.objects.create(run=run, event_id=row.event_id, version=row.version, payload=payload)
        state = self.readiness(run).data
        self.assertFalse(state['ready'])
        self.assertEqual(state['explanations']['areas_on_plain_wording'], [area])
        self.assertEqual(state['explanations']['others_on_plain_wording'], 2)
        self.assertEqual(self.report(run).status_code, 409)

    def test_text_written_by_an_earlier_version_is_written_again(self):
        run = self.assess()
        self.write_text(run)
        row = CapabilityExplanation.objects.filter(run=run).order_by('-created_at').first()
        CapabilityExplanation.objects.create(run=run, event_id=row.event_id, version='explanations-0.2',
                                             payload={**row.payload, 'version': 'explanations-0.2'})
        state = self.readiness(run).data
        self.assertFalse(state['ready'])
        self.assertIn('earlier version (explanations-0.2)', state['reasons'][0])
