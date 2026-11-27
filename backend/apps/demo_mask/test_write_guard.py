"""The write guard (write_guard.py): with the demo mask on, the mask's stand-in names are never saved over real data."""
import json

from django.http import JsonResponse
from django.test import RequestFactory, TestCase, override_settings

from apps.institutions.models import Institution
from apps.sprints.models import Sprint

from . import mask
from .write_guard import MaskedWriteGuardMiddleware

VISTAS = 'VELS INSTITUTE OF SCIENCE, TECHNOLOGY AND ADVANCED STUDIES(VISTAS)'


def _reset():
    mask._compiled.cache_clear()


class WriteGuardTests(TestCase):
    def setUp(self):
        _reset()
        self.addCleanup(_reset)
        self.vistas = Institution.objects.create(name=VISTAS, city='Chennai')
        self.other = Institution.objects.create(name='Synthetic College', city='Pune')
        self.sprint = Sprint.objects.create(institution=self.vistas)
        self.other_sprint = Sprint.objects.create(institution=self.other)
        self.reached = []

    def _send(self, method, path, body):
        def view(request):
            self.reached.append(path)
            return JsonResponse({'ok': True})
        request = getattr(RequestFactory(), method.lower())(path, data=json.dumps(body), content_type='application/json')
        return MaskedWriteGuardMiddleware(view)(request)

    def _refused(self, response):
        return response.status_code == 400 and json.loads(response.content)['code'] == 'demo_mask_write_refused'

    @override_settings(DEMO_NAME_MASK='vistas')
    def test_the_profile_save_that_wrote_the_mask_is_refused(self):
        # What the website's Profile page sends: the displayed (masked) name with every save.
        response = self._send('PATCH', f'/api/v1/institutions/{self.vistas.pk}', {'name': 'ABC University', 'city': 'Chennai'})
        self.assertTrue(self._refused(response))
        self.assertIn('demo name mask', json.loads(response.content)['detail'])
        self.assertEqual(self.reached, [])

    @override_settings(DEMO_NAME_MASK='vistas')
    def test_a_masked_institutions_own_records_are_read_only(self):
        for method, path in (('PATCH', f'/api/v1/institutions/{self.vistas.pk}/'),
                             ('POST', f'/api/v1/institutions/{self.vistas.pk}/departments'),
                             ('PATCH', f'/api/v1/institutions/{self.vistas.pk}/leaders/{self.vistas.pk}'),
                             ('PUT', f'/api/v1/assessments/institutions/{self.vistas.pk}/profile'),
                             ('PATCH', f'/api/v1/sprints/{self.sprint.pk}')):
            self.assertTrue(self._refused(self._send(method, path, {'description': 'Unrelated text'})), path)
        self.assertEqual(self.reached, [])

    @override_settings(DEMO_NAME_MASK='vistas')
    def test_other_institutions_and_a_sprint_status_change_still_work(self):
        for method, path, body in (('PATCH', f'/api/v1/institutions/{self.other.pk}', {'city': 'Mumbai'}),
                                   ('PATCH', f'/api/v1/sprints/{self.other_sprint.pk}', {'description': 'Notes'}),
                                   ('PATCH', f'/api/v1/sprints/{self.sprint.pk}', {'status': 'archived'})):
            self.assertEqual(self._send(method, path, body).status_code, 200, path)
        self.assertEqual(len(self.reached), 3)

    @override_settings(DEMO_NAME_MASK='vistas')
    def test_a_stand_in_name_in_any_other_write_is_refused(self):
        run = '22222222-2222-4222-8222-222222222222'
        answer = f'/api/v1/sprints/{self.sprint.pk}/capability-runs/{run}/questions/{run}/responses'
        response = self._send('POST', answer, {'answer': 'ABC University has an AI policy.', 'document_ids': []})
        self.assertTrue(self._refused(response))
        self.assertIn('"ABC University"', json.loads(response.content)['detail'])
        nested = self._send('POST', f'/api/v1/sprints/{self.sprint.pk}/capability-runs',
                            {'confirmed_source_institution': 'ABC University'})
        self.assertTrue(self._refused(nested))
        self.assertTrue(self._refused(self._send('POST', '/api/v1/things', {'rows': [{'address': '[campus address]'}]})))

    @override_settings(DEMO_NAME_MASK='vistas')
    def test_ordinary_words_and_real_names_pass(self):
        run = '22222222-2222-4222-8222-222222222222'
        answer = f'/api/v1/sprints/{self.sprint.pk}/capability-runs/{run}/questions/{run}/responses'
        for text in (f'{VISTAS} has an AI policy.', 'The founder approved it for Campus A.', 'An abc analysis was done.'):
            self.assertEqual(self._send('POST', answer, {'answer': text}).status_code, 200, text)

    @override_settings(DEMO_NAME_MASK='vistas')
    def test_sign_in_is_never_checked(self):
        self.assertEqual(self._send('POST', '/api/v1/auth/login', {'username': 'u', 'password': 'ABC University 1'}).status_code, 200)

    def test_does_nothing_while_the_mask_is_off(self):
        response = self._send('PATCH', f'/api/v1/institutions/{self.vistas.pk}', {'name': 'ABC University'})
        self.assertEqual(response.status_code, 200)
