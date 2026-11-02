from copy import deepcopy
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from rest_framework.test import APITestCase
from apps.accounts.models import User
from apps.institutions.models import Institution
from apps.sprints.models import Sprint
from apps.documents.models import Document
from apps.extraction.models import DocumentPage
from .models import CapabilityExecution, CapabilityRunEvent
from .capability.scope import intent, resolve
from .capability.storage import digest


class ScopeContractTests(SimpleTestCase):
    def test_source_local_declarations_preserve_distinct_dates_and_identity_issue(self):
        text = 'Institution name: Other College\nProgramme: BBA\nAcademic year: 2018-19\nPolicy effective: 2024 onwards\nCurriculum regulation: 2020\n'
        other = 'Reporting period: 2022-23\n'
        scope = resolve(profile={'name': 'College'}, mode='default', requested={'scope_mode': 'default'},
                        sources=[{'id': 'p1', 'text': text}, {'id': 'p2', 'text': other}])
        self.assertIn('Mixed', scope['period_label'])
        self.assertEqual(scope['institution']['name'], 'College')
        self.assertEqual(scope['institution']['identity_status'], 'mismatch_requires_review')
        for d in scope['source_declarations']:
            source = text if d['source_id'] == 'p1' else other
            self.assertEqual(source[d['start']:d['end']], d['quote'])
        self.assertEqual({d['kind'] for d in scope['source_declarations']},
            {'population', 'activity_period', 'policy_interval', 'curriculum_regulation', 'institution_identity'})
        self.assertIn('BBA', [d['value'] for d in scope['source_declarations']])
        self.assertNotIn('2026', scope['period_label'])

    def test_empty_labels_never_take_the_next_line_as_a_value(self):
        scope = resolve(profile={'name': 'College'}, mode='default', requested={'scope_mode': 'default'},
            sources=[{'id': 'p1', 'text': 'Institution name:\nProgramme:   \nAcademic year: 2024-25\nPolicy effective:\r\nCurriculum regulation: 2020'}])
        self.assertEqual([(d['kind'], d['value']) for d in scope['source_declarations']],
            [('activity_period', '2024-25'), ('curriculum_regulation', '2020')])
        self.assertEqual(scope['institution']['identity_status'], 'unconfirmed')

    def test_standard_ssr_header_is_an_identity_claim_not_an_automatic_profile_rename(self):
        source = {'id': 'page1', 'text': '   Self Study Report of SYNTHETIC UNIVERSITY\nOther ordinary text.'}
        scope = resolve(profile={'name': 'Placeholder College'}, mode='default', requested={'scope_mode': 'default'}, sources=[source])
        self.assertEqual(scope['institution']['name'], 'Placeholder College')
        self.assertEqual(scope['institution']['identity_status'], 'mismatch_requires_review')
        self.assertTrue(any(q['code'] == 'institution_identity_mismatch' for q in scope['questions']))
        declaration = next(d for d in scope['source_declarations'] if d['kind'] == 'institution_identity')
        self.assertEqual(declaration['value'], 'SYNTHETIC UNIVERSITY')
        self.assertEqual(source['text'][declaration['start']:declaration['end']], declaration['quote'])

    def test_intent_rejects_partial_and_preserves_legacy_digest(self):
        self.assertEqual(intent('All', '2025-26')[1], {'population': 'All', 'reference_period': '2025-26'})
        for args in [('BBA', None, None), ('All', '2025', 'default'), (None, None, 'custom')]:
            with self.assertRaises(ValueError):
                intent(*args)


@override_settings(SECURE_SSL_REDIRECT=False, CAPABILITY_ASSESSMENT_ENABLED=True)
class ScopeAPITests(APITestCase):
    def setUp(self):
        self.institution = Institution.objects.create(name='College')
        self.sprint = Sprint.objects.create(institution=self.institution)
        self.user = User.objects.create_user(username='scope', email='scope@example.com', role=User.Role.IQAC_COORDINATOR, institution=self.institution)
        self.client.force_authenticate(self.user)
        doc = Document.objects.create(sprint=self.sprint, document_type='naac_ssr')
        self.page = DocumentPage.objects.create(document=doc, page_number=1, text='Programme: BBA\nAcademic year: 2018-19')
        self.url = f'/api/v1/sprints/{self.sprint.pk}/capability-runs'

    def post(self, body, key='scope1'):
        with patch('apps.scoring.capability.execution.dispatch'):
            return self.client.post(self.url, body, format='json', HTTP_IDEMPOTENCY_KEY=key)

    def test_default_retry_does_not_resolve_again_after_evidence_changes(self):
        response = self.post({})
        self.assertEqual(response.status_code, 202, response.data)
        execution = CapabilityExecution.objects.get(run_id=response.data['id'])
        original = deepcopy(execution.run.inputs)
        self.page.text = 'Programme: All students\nAcademic year: 2026-27'
        self.page.save()
        with patch('apps.scoring.capability.storage.evidence_snapshot', side_effect=AssertionError('must not resolve')):
            retry = self.post({'scope_mode': 'default'})
        self.assertEqual(retry.status_code, 200, retry.data)
        self.assertTrue(retry.data['reused'])
        execution.run.refresh_from_db()
        self.assertEqual(execution.run.inputs, original)
        self.assertEqual(digest(original), execution.run.inputs_hash)
        self.assertEqual(self.post({'population': 'All', 'reference_period': '2026'}).status_code, 409)

    def test_custom_validation_and_new_refinement_preserve_old_run(self):
        for body in [{'population': 'BBA'}, {'scope_mode': 'custom'}, {'scope_mode': 'default', 'population': 'BBA'}]:
            self.assertEqual(self.post(body).status_code, 400)
        first = self.post({'population': 'All', 'reference_period': '2025-26'})
        execution = CapabilityExecution.objects.get(run_id=first.data['id'])
        frozen = deepcopy(execution.run.inputs)
        execution.status = 'completed'
        execution.save()
        CapabilityRunEvent.objects.create(run=execution.run, state='completed', payload={'result': {}})
        response = self.post({'scope_mode': 'custom', 'population': 'BBA', 'reference_period': '2018-19',
                              'refines_run_id': first.data['id']}, key='scope2')
        self.assertEqual(response.status_code, 202, response.data)
        self.assertNotEqual(response.data['id'], first.data['id'])
        self.assertEqual(response.data['refines_run_id'], first.data['id'])
        execution.run.refresh_from_db()
        self.assertEqual(execution.run.inputs, frozen)
        self.assertEqual(response.data['scope']['rubric_scope_policy'], 'original_requirement_scope_unchanged_even_for_custom_cohort')

    def test_cross_sprint_refinement_is_rejected(self):
        first = self.post({})
        execution = CapabilityExecution.objects.get(run_id=first.data['id'])
        execution.status = 'completed'
        execution.save()
        other = Sprint.objects.create(institution=self.institution)
        url = f'/api/v1/sprints/{other.pk}/capability-runs'
        response = self.client.post(url, {'scope_mode': 'custom', 'population': 'All', 'reference_period': '2025',
            'refines_run_id': first.data['id']}, format='json', HTTP_IDEMPOTENCY_KEY='foreign')
        self.assertEqual(response.status_code, 400)

    def test_identity_mismatch_is_reviewed_before_model_dispatch_or_run_creation(self):
        self.page.text = 'Self Study Report of Synthetic University\nReporting period: 2023-24'
        self.page.save()
        with patch('apps.scoring.capability.execution.dispatch') as send:
            response = self.client.post(self.url, {}, format='json', HTTP_IDEMPOTENCY_KEY='identity')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['code'], 'source_identity_confirmation_required')
        self.assertEqual(response.data['source_institutions'], ['Synthetic University'])
        self.assertFalse(send.called)
        self.assertFalse(CapabilityExecution.objects.exists())
        response = self.post({'confirmed_source_institution': 'Synthetic University'}, key='identity-confirmed')
        self.assertEqual(response.status_code, 202, response.data)
        self.assertEqual(response.data['scope']['institution']['identity_status'], 'user_confirmed_for_this_run')
        self.assertEqual(response.data['scope']['institution']['assessed_name'], 'Synthetic University')
        self.institution.refresh_from_db()
        self.assertEqual(self.institution.name, 'College')
        retry = self.post({'confirmed_source_institution': 'Synthetic University'}, key='identity-confirmed')
        self.assertEqual(retry.status_code, 200)
        self.assertTrue(retry.data['reused'])
        changed = self.post({}, key='identity-confirmed')
        self.assertEqual(changed.status_code, 409)

    def test_confirmation_cannot_name_an_institution_absent_from_sources(self):
        response = self.post({'confirmed_source_institution': 'Invented institution'})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(CapabilityExecution.objects.exists())

    def test_report_timestamp_is_not_promoted_to_an_activity_year(self):
        text = 'Self Study Report of College\nComputing resources are available.\nPage 4/80\n03-04-2024 11:12:13\n'
        scope = resolve(profile={'name': 'College'}, mode='default', requested={'scope_mode': 'default'},
                        sources=[{'id': 'p1', 'text': text}])
        dates = [d for d in scope['source_declarations'] if d['kind'] == 'report_claim_date']
        self.assertEqual(len(dates), 1)
        self.assertEqual(dates[0]['interpretation'], 'report_timestamp_only_not_activity_or_current_operation')
        self.assertFalse(any(d['kind'] == 'activity_period' for d in scope['source_declarations']))
        self.assertNotIn('2024', scope['period_label'])
        unrelated = resolve(profile={'name': 'College'}, mode='default', requested={'scope_mode': 'default'},
                            sources=[{'id': 'p1', 'text': 'Event log\n03-04-2024 11:12:13\n'}])
        self.assertFalse(any(d['kind'] == 'report_claim_date' for d in unrelated['source_declarations']))
