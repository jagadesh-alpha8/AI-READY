"""25 Nov audit fixes (claude/ai-ready-fable-audit-findings-25-nov.md): retries that survive a rate limit, exports
inside the Docker image, the settings check by short id, a failed run's outline, the mask, next-steps wording."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.http import HttpResponse, JsonResponse
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings

from apps.extraction.exceptions import ProviderRateLimited, ProviderUnavailable
from apps.scoring.capability import private_output
from apps.scoring.capability.provider import RETRY_WAITS, retry_wait
from apps.scoring.tasks import failure_outline


class RetryWaitTests(SimpleTestCase):
    def test_rate_limit_without_retry_after_backs_off_three_times_then_gives_up(self):
        exc = ProviderRateLimited('429')
        self.assertEqual([retry_wait(exc, n) for n in range(4)], [*RETRY_WAITS, None])

    def test_overload_follows_retry_after_up_to_a_minute(self):
        self.assertEqual(retry_wait(ProviderUnavailable('529', kind='server_error', retry_after=20), 0), 20)
        self.assertIsNone(retry_wait(ProviderRateLimited('429', retry_after=120), 0))

    def test_timeout_is_retried_once(self):
        exc = ProviderUnavailable('timeout', kind='timeout')
        self.assertIsNotNone(retry_wait(exc, 0))
        self.assertIsNone(retry_wait(exc, 1))


class MeteredRetryTests(SimpleTestCase):
    """The metered service's loop: a 429, a 529 and then an answer is one answered request, not an unknown indicator."""

    def service(self, outcomes, remaining=10_000):
        from apps.scoring.capability.provider import MeteredService
        metered = MeteredService.__new__(MeteredService)
        metered.answers, metered.limit_breach = None, False
        metered._call = SimpleNamespace()
        metered.remaining_time = lambda: remaining
        calls = iter(outcomes)

        def extract(**kwargs):
            outcome = next(calls)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        metered.service = SimpleNamespace(extract_structured_data=extract)
        metered.policy = {'timeout_seconds': 60}
        return metered

    @patch('apps.scoring.capability.provider.time.sleep')
    def test_recovers_after_rate_limit_and_overload(self, sleep):
        metered = self.service([ProviderRateLimited('429'), ProviderUnavailable('529', kind='server_error'), {'ok': 1}])
        self.assertEqual(metered.extract_structured_data(schema_name='x'), {'ok': 1})
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [5, 20])

    @patch('apps.scoring.capability.provider.time.sleep')
    def test_gives_up_after_four_attempts(self, sleep):
        metered = self.service([ProviderRateLimited('429')] * 5)
        with self.assertRaises(ProviderRateLimited):
            metered.extract_structured_data(schema_name='x')
        self.assertEqual(sleep.call_count, 3)

    @patch('apps.scoring.capability.provider.time.sleep')
    def test_does_not_wait_past_the_run_deadline(self, sleep):
        metered = self.service([ProviderRateLimited('429'), {'ok': 1}], remaining=3)
        with self.assertRaises(ProviderRateLimited):
            metered.extract_structured_data(schema_name='x')
        sleep.assert_not_called()


class PrivateOutputTests(SimpleTestCase):
    def test_in_the_image_the_code_is_app_and_tmp_is_outside(self):
        with override_settings(BASE_DIR=Path('/app')):
            self.assertEqual(private_output.code_root(), Path('/app'))
            self.assertFalse(private_output.inside_code('/tmp/vistas-map.json'))
            self.assertTrue(private_output.inside_code('/app/vistas-map.json'))

    def test_in_a_checkout_the_whole_repository_is_inside(self):
        with override_settings(BASE_DIR=Path('/home/dev/ai-ready/backend')):
            self.assertTrue(private_output.inside_code('/home/dev/ai-ready/frontend-new/x.json'))
            self.assertFalse(private_output.inside_code('/home/dev/exports/x.json'))


class FailureOutlineTests(SimpleTestCase):
    def test_names_classes_status_and_place_without_message_text(self):
        class BadRequest(Exception):
            status_code = 400
        try:
            try:
                raise BadRequest('secret document text')
            except BadRequest as inner:
                raise ProviderUnavailable('more secret text') from inner
        except ProviderUnavailable as exc:
            outline = failure_outline(exc)
        self.assertIn('ProviderUnavailable <- BadRequest (status 400)', outline)
        self.assertNotIn('secret', outline)


@override_settings(DEMO_NAME_MASK='vistas')
class MaskTests(SimpleTestCase):
    def setUp(self):
        from apps.demo_mask import mask
        mask._compiled.cache_clear()
        self.mask = mask

    def test_joined_and_numbered_forms(self):
        self.assertEqual(self.mask.text('VISTAS2021 report'), 'ABC University2021 report')
        self.assertEqual(self.mask.text('VelsUniversity and @VelsUniv'), 'ABC University and @ABC University')
        self.assertEqual(self.mask.text('levels and novels'), 'levels and novels')

    def test_json_numbers_are_left_alone_and_strings_masked(self):
        from apps.demo_mask.middleware import NameMaskMiddleware
        body = {'duration_ms': 600117, 'quote': 'Chennai 600117, VISTAS', 'n': [600130]}
        middleware = NameMaskMiddleware(lambda request: JsonResponse(body))
        response = middleware(RequestFactory().get('/api/v1/x'))
        data = json.loads(response.content)
        self.assertEqual(data['duration_ms'], 600117)
        self.assertEqual(data['n'], [600130])
        self.assertEqual(data['quote'], 'Chennai 600 000, ABC University')

    def test_html_is_still_masked_as_text(self):
        from apps.demo_mask.middleware import NameMaskMiddleware
        middleware = NameMaskMiddleware(lambda request: HttpResponse('<p>VISTAS</p>', content_type='text/html'))
        self.assertEqual(middleware(RequestFactory().get('/api/v1/x')).content, b'<p>ABC University</p>')


class NextStepsWordsTests(SimpleTestCase):
    """A college's own "credit course" is not rubric talk; "credited" and "indicator" still are."""

    def check(self, action, passage_text):
        from apps.scoring.capability import next_steps as ns
        from apps.scoring.test_next_steps import given, good
        packet = given()
        packet['passages'][1]['text'] = passage_text
        output = good()
        output['action'] = action
        return ns.validate(packet, output)[1]

    def test_credit_course_passes_when_the_passages_say_it(self):
        problems = self.check('Add a credit course on AI to the Choice Based Credit System electives.',
                              'The Internal Quality Assurance Cell reviews the Choice Based Credit System; each credit '
                              'course is reviewed every semester.')
        self.assertFalse(any('internal words' in p for p in problems), problems)

    def test_credit_is_refused_when_the_passages_never_say_it(self):
        problems = self.check('Add a credit course on AI.', 'The Internal Quality Assurance Cell reviews feedback.')
        self.assertTrue(any('internal words' in p for p in problems), problems)

    def test_credited_and_indicator_are_always_refused(self):
        problems = self.check('This indicator was credited.', 'Each credit course was credited by the indicator.')
        self.assertTrue(any('internal words' in p for p in problems), problems)


class SettingsCheckShortIdTests(TestCase):
    def test_short_id_finds_the_run(self):
        from apps.scoring.management.commands.capability_settings_check import _find_run
        from apps.scoring.models import CapabilityRun
        with patch.object(CapabilityRun.objects, 'only', return_value=[SimpleNamespace(pk='f9587aca-0000-0000-0000-000000000001')]), \
                patch.object(CapabilityRun.objects, 'get', side_effect=lambda pk: SimpleNamespace(pk=pk)):
            self.assertEqual(str(_find_run('f9587aca').pk), 'f9587aca-0000-0000-0000-000000000001')

    def test_unknown_id(self):
        from apps.scoring.management.commands.capability_settings_check import _find_run
        with self.assertRaises(CommandError):
            _find_run('deadbeef')
