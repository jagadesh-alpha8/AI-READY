import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import MagicMock
from django.test import SimpleTestCase,override_settings
from apps.extraction.services.openai_client import OpenAIExtractionService
from apps.facts.test_verification import VerificationBase
from .capability.bounded_probe import prepare,bounded_policy,execute
from .capability.engine import release
from .capability.reviewed_evidence import for_context
from .capability.storage import digest
from .capability.provider import MeteredService
from .models import CapabilityRun,CapabilityExecution


def fixture():
    rubric=release();i=rubric['indicators'][0];indicator={**i,'conditions':i['conditions'][:1]}
    source={'id':'p','document_id':'d','page_number':1,'text':'The approved strategy names the responsible planning office in 2024-25.','text_offset':0}
    ledger={'claims':[],'issues':[]};payload={'sources':[source],'indicator':indicator,
        'reviewed_evidence':for_context(ledger,[source]),'population':'Learners','reference_period':'2024-25'}
    return {'rubric':rubric,'profile':{},'requests':[{'id':'r1','payload':payload,'payload_hash':digest(payload)}]},ledger,[source]


class ProbePreparationTests(SimpleTestCase):
    def test_refreshes_projection_and_discards_cached_model_answers(self):
        plan,ledger,corpus=fixture();plan['requests'][0]['response']={'conditions':[]}
        refreshed=prepare(plan,ledger,corpus)
        self.assertNotIn('response',refreshed['requests'][0])
        self.assertTrue(refreshed['refreshed_against_current_corpus'])
        before=deepcopy(plan)
        bad=deepcopy(corpus);bad[0]['text']='Changed document text'
        with self.assertRaises(ValueError):prepare(plan,ledger,bad)
        self.assertEqual(plan,before)

    @override_settings(CAPABILITY_MAX_HTTP_CALLS=72,CAPABILITY_MAX_COST_USD='2',CAPABILITY_MAX_DURATION_SECONDS=7200)
    def test_probe_only_narrows_configured_bounds(self):
        p=bounded_policy()
        self.assertEqual(p['max_http_calls'],16);self.assertEqual(p['max_cost_usd'],'1')
        self.assertEqual(p['max_duration_seconds'],600)
        with override_settings(CAPABILITY_MAX_HTTP_CALLS=4,CAPABILITY_MAX_COST_USD='0.2',CAPABILITY_MAX_DURATION_SECONDS=40):
            p=bounded_policy();self.assertEqual(p['max_http_calls'],4)
            self.assertEqual(p['max_cost_usd'],'0.2');self.assertEqual(p['max_duration_seconds'],40)


@override_settings(CAPABILITY_ASSESSMENT_ENABLED=True,AI_RATE_LIMIT_ENABLED=False,
    AI_PRICING_JSON='{"test-model":{"input":0.1,"output":0.2}}')
class SharedProbeMeterTests(VerificationBase):
    def setup_meter(self,calls):
        policy=bounded_policy();policy.update(max_http_calls=calls,output_tokens=1024)
        run=CapabilityRun.objects.create(sprint=self.sprint,inputs={'execution_policy':policy},inputs_hash='test')
        execution=CapabilityExecution.objects.create(run=run,sprint=self.sprint,status='running',idempotency_key='probe',request_hash='test')
        sdk=MagicMock();sdk.with_options.return_value=sdk
        def response(**kwargs):
            payload=json.loads(kwargs['messages'][1]['content'])
            data={'advice':[]} if 'actions' in payload else {'conditions':{c['id']:{'state':'unknown',
                'reason':'No approved strategy is established.','scope_supported':False,'period_supported':False,'citations':[]}
                for c in payload['indicator']['conditions']}}
            return SimpleNamespace(model='test-model',usage=SimpleNamespace(prompt_tokens=100,completion_tokens=100,
                prompt_tokens_details=None,completion_tokens_details=None,total_tokens=200),
                choices=[SimpleNamespace(finish_reason='stop',message=SimpleNamespace(content=json.dumps(data),refusal=None))])
        sdk.chat.completions.create.side_effect=response
        service=OpenAIExtractionService(api_key='sk-test',model='test-model',client=sdk)
        return MeteredService(service,execution),execution,sdk

    def test_advice_repair_and_decision_use_same_meter_cap(self):
        plan,ledger,corpus=fixture();plan=prepare(plan,ledger,corpus)
        meter,execution,sdk=self.setup_meter(2)
        result=execute(plan,meter,advice_cases=1)
        execution.refresh_from_db()
        self.assertEqual(execution.requests_reserved,2)
        self.assertEqual(sdk.chat.completions.create.call_count,2)
        advice=result['requests'][0]['live_advice'][0]
        self.assertEqual(advice['advice'][0]['origin'],'deterministic_fallback')
        self.assertEqual(advice['validation']['repair_failure'],'request_budget_exceeded')
        self.assertTrue(result['requests'][0]['model_execution_verified'])

    def test_stop_preserves_partial_results_and_no_assessment_publication(self):
        plan,ledger,corpus=fixture();second=deepcopy(plan['requests'][0]);second['id']='r2';plan['requests'].append(second)
        meter,execution,sdk=self.setup_meter(1)
        result=execute(prepare(plan,ledger,corpus),meter,advice_cases=0)
        self.assertFalse(result['execution_completed']);self.assertEqual(result['stop_reason'],'BudgetExceeded')
        self.assertEqual(len(result['requests']),1)
        self.assertEqual(sdk.chat.completions.create.call_count,1)
        self.assertFalse(execution.run.events.filter(state='completed',payload__result__isnull=False).exists())


class ProbeCommandGuardTests(SimpleTestCase):
    def input_file(self,folder):
        from pathlib import Path
        plan,ledger,corpus=fixture();plan['reviewed_evidence']=ledger
        source=Path(folder)/'plan.json';source.write_text(json.dumps(plan));return source

    def test_default_mode_has_no_database_or_provider_access(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from io import StringIO
        from django.core.management import call_command
        from unittest.mock import patch
        with TemporaryDirectory() as folder:
            source=self.input_file(folder);output=Path(folder)/'out.json'
            with patch('apps.extraction.services.ai_service.get_ai_service') as provider:
                call_command('capability_bounded_probe',str(source),output=str(output),stdout=StringIO())
                provider.assert_not_called()
            self.assertFalse(output.exists())

    @override_settings(CAPABILITY_ASSESSMENT_ENABLED=True,CAPABILITY_RECOMMENDATIONS_ENABLED=True,AI_API_KEY='',OPENAI_API_KEY='')
    def test_missing_credentials_fail_before_provider_and_database_reads(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from django.core.management import call_command
        from django.core.management.base import CommandError
        from django.db import connection
        from unittest.mock import patch
        with TemporaryDirectory() as folder:
            source=self.input_file(folder)
            with patch('apps.extraction.services.ai_service.get_ai_service') as provider:
                with self.assertRaisesMessage(CommandError,'No provider key'):
                    call_command('capability_bounded_probe',str(source),output=str(Path(folder)/'out.json'),
                        execute=True,disposable_database=str(connection.settings_dict['NAME']),sprint_id='unused')
                provider.assert_not_called()


@override_settings(CAPABILITY_ASSESSMENT_ENABLED=True,AI_RATE_LIMIT_ENABLED=False,
    AI_PRICING_JSON='{"test-model":{"input":0.1,"output":0.2}}')
class OversizedProbeCaseTests(SharedProbeMeterTests):
    def test_oversized_case_is_preflighted_before_calls_and_does_not_cancel_advice(self):
        plan,ledger,corpus=fixture()
        large=deepcopy(plan['requests'][0]);large['id']='oversized'
        corpus=deepcopy(corpus)
        full_text=corpus[0]['text']*5000
        corpus[0]['text']=full_text
        large['payload']['sources'][0]['text']=full_text
        large['payload_hash']=digest(large['payload'])
        plan['requests'].append(large)
        meter,execution,sdk=self.setup_meter(2)
        result=execute(prepare(plan,ledger,corpus),meter,advice_cases=1)
        self.assertEqual(result['requests'][0]['status'],'live_response_validated')
        self.assertFalse(result['execution_completed'])
        self.assertTrue(result['advice_stage_completed'])
        self.assertEqual(result['case_errors'][0]['id'],'oversized')
        self.assertEqual(result['case_errors'][0]['provider_requests_reserved_for_case'],0)
        self.assertIn('not_actual_model_tokens',result['decision_preflight'][1]['bound_basis'])
        self.assertTrue(result['requests'][0]['live_advice'])
        self.assertEqual(sdk.chat.completions.create.call_count,2)
        execution.refresh_from_db();self.assertEqual(execution.requests_reserved,2)

    def test_runtime_input_guard_is_local_but_global_budget_still_stops(self):
        from unittest.mock import patch
        from .capability.execution import InputBudgetExceeded
        plan,ledger,corpus=fixture();second=deepcopy(plan['requests'][0]);second['id']='runtime_oversize'
        plan['requests'].append(second)
        meter,execution,sdk=self.setup_meter(2)
        original=meter.extract_structured_data;calls=0
        def send(**kwargs):
            nonlocal calls
            calls+=1
            if calls==2:raise InputBudgetExceeded()
            return original(**kwargs)
        with patch.object(meter,'extract_structured_data',side_effect=send):
            result=execute(prepare(plan,ledger,corpus),meter,advice_cases=1)
        self.assertEqual(result['case_errors'][0]['stage'],'runtime_input_guard')
        self.assertTrue(result['advice_stage_completed'])
        self.assertTrue(result['requests'][0]['live_advice'])


class ScopeProjectionProbeTests(SimpleTestCase):
    def test_whole_document_scope_is_projected_to_the_actual_windows(self):
        plan,ledger,corpus=fixture()
        scope={k:'source-specific' for k in ('version','mode','institution','population_label','period_label',
            'coverage_policy','rubric_scope_policy','limitations')}
        scope['questions']=[]
        scope['source_declarations']=[{'source_id':'unselected-'+str(n),'kind':'report_claim_date','value':'2024-01-01'} for n in range(374)]
        scope['source_declarations'].append({'source_id':'p','kind':'report_claim_date','value':'2024-02-01'})
        plan['requests'][0]['payload']['scope']=scope
        plan['requests'][0]['payload_hash']=digest(plan['requests'][0]['payload'])
        old_hash=plan['requests'][0]['payload_hash']
        result=prepare(plan,ledger,corpus)['requests'][0]
        self.assertEqual(result['payload']['scope']['source_declarations'],[scope['source_declarations'][-1]])
        self.assertTrue(result['payload']['scope']['declarations_are_subset'])
        self.assertEqual(result['original_payload_hash'],old_hash)
        self.assertNotEqual(result['payload_hash'],old_hash)
        self.assertEqual(len(plan['requests'][0]['payload']['scope']['source_declarations']),375)


@override_settings(CAPABILITY_ASSESSMENT_ENABLED=True,AI_RATE_LIMIT_ENABLED=False,
    AI_PRICING_JSON='{"test-model":{"input":0.1,"output":0.2}}',
    AI_SEND_SAMPLING_PARAMS=False,AI_TEMPERATURE=0,AI_SEED=42)
class SamplingOptOutProbeTests(SharedProbeMeterTests):
    def test_explicit_endpoint_opt_out_reaches_sdk_on_first_attempt_and_matches_preflight(self):
        plan,ledger,corpus=fixture();meter,execution,sdk=self.setup_meter(1)
        result=execute(prepare(plan,ledger,corpus),meter,advice_cases=0)
        self.assertTrue(result['execution_completed'])
        self.assertEqual(sdk.chat.completions.create.call_count,1)
        kwargs=sdk.chat.completions.create.call_args.kwargs
        self.assertNotIn('temperature',kwargs);self.assertNotIn('seed',kwargs)
        reserved=next(c for c in result['inference']['calls'] if c['kind']=='request_reserved')
        self.assertEqual(result['decision_preflight'][0]['input_token_bound'],reserved['input_token_bound'])
