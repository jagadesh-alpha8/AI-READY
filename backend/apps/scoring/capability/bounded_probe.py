"""Diagnostic requests through the production meter; never publishes an assessment."""
import json
from copy import deepcopy
from decimal import Decimal
from .storage import digest
from .reviewed_evidence import for_context
from .evaluation import SYSTEM_PROMPT, indicator_schema
from .evidence_audit import audit_request


def prepare(plan, ledger, corpus):
    """Bind every supplied window to a fresh disposable-copy corpus before inference."""
    lookup={s['id']:s for s in corpus}
    if len(lookup)!=len(corpus) or not 1<=len(plan['requests'])<=12:
        raise ValueError('Probe needs unique corpus IDs and 1–12 requests.')
    requests=[]
    for original in plan['requests']:
        if original.get('payload_hash') and digest(original['payload']) != original['payload_hash']:
            raise ValueError('Prepared probe payload hash mismatch.')
        request=deepcopy(original);payload=request['payload']
        for window in payload['sources']:
            source=lookup.get(window['id']);offset=window.get('text_offset',0)
            if (not source or type(offset) is not int or offset<0 or not window['text']
                    or window['document_id']!=source['document_id'] or window['page_number']!=source['page_number']
                    or window['text']!=source['text'][offset:offset+len(window['text'])]):
                raise ValueError('Probe window no longer matches the current corpus.')
        payload['reviewed_evidence']=for_context(ledger,payload['sources'])
        request['system_prompt']=SYSTEM_PROMPT
        request['response_schema']=indicator_schema(payload['indicator'],payload['sources'])
        request['original_payload_hash']=original.get('payload_hash')
        request['payload_hash']=digest(payload)
        # A prepared plan can never inject a cached answer into the live result.
        request.pop('response',None);request.pop('advice',None)
        audit_request(request,ledger,plan['rubric'])
        requests.append(request)
    if len({r['id'] for r in requests})!=len(requests):
        raise ValueError('Probe request IDs must be unique.')
    return {**plan,'reviewed_evidence':ledger,'requests':requests,'refreshed_against_current_corpus':True}


def bounded_policy():
    from .execution import policy
    result=policy()
    advice=policy('recommendation')
    result['output_tokens']=min(result['output_tokens'],advice['output_tokens'])
    result['timeout_seconds']=min(result['timeout_seconds'],advice['timeout_seconds'])
    result.update(stage='bounded_evidence_probe',max_http_calls=min(16,result['max_http_calls']),
        max_cost_usd=str(min(Decimal('1'),Decimal(result['max_cost_usd']))),
        max_duration_seconds=min(600,result['max_duration_seconds']))
    return result


def decision_preflight(plan, meter):
    """Size all initial decision requests before spending; runtime guards remain.

    This is the meter's conservative byte-derived bound, not model tokenization.
    Client format repairs may add content later and are checked at runtime too.
    """
    from django.conf import settings
    from apps.extraction.services.openai_client import OpenAIExtractionService, _JSON_INSTRUCTIONS, _sampling
    from apps.extraction.services.provider_features import direct_gemini, gemini_thinking
    if not isinstance(meter.service, OpenAIExtractionService):
        return [{'id': r['id'], 'available': False, 'eligible': True,
                 'note': 'Initial sizing unavailable for this client; runtime meter still applies.'}
                for r in plan['requests']]
    rows=[]
    for request in plan['requests']:
        system=request['system_prompt']
        base_url=meter.service.base_url
        schema=request['response_schema']
        if base_url and not direct_gemini(base_url):
            system += _JSON_INSTRUCTIONS.format(schema=json.dumps(schema,separators=(',',':')))
        kwargs={'model':meter.model,
            'messages':[{'role':'system','content':system},
                        {'role':'user','content':json.dumps(request['payload'],sort_keys=True)}],
            'response_format':{'type':'json_schema','json_schema':{
                'name':'capability_probe_condition','schema':schema,'strict':True}},
            'max_tokens':meter.policy['output_tokens'],'timeout':meter.policy['timeout_seconds'],
            **_sampling()}
        if gemini_thinking(base_url,meter.model) and meter.policy['gemini_reasoning_effort']!='default':
            kwargs['reasoning_effort']=meter.policy['gemini_reasoning_effort']
        bound,_=meter.envelope(kwargs)
        rows.append({'id':request['id'],'available':True,
            'input_token_bound':bound,'input_token_bound_limit':meter.policy['input_token_bound_limit'],
            'eligible':bound<=meter.policy['input_token_bound_limit'],
            'bound_basis':'serialized_utf8_bytes_plus_4096_not_actual_model_tokens'})
    return rows


def execute(plan, meter, *, advice_cases=3, on_result=None):
    """One shared meter/deadline for decisions, retries and normal advice repair."""
    if type(advice_cases) is not int or not 0<=advice_cases<=3:
        raise ValueError('At most three advice cases are allowed.')
    from .execution import InputBudgetExceeded
    from .recommendations import KINDS,OPERATIONS,processing_failure
    from .recommendation_execution import tailor_batch,deterministic_advice,bounded_strengths
    result={'version':'bounded-evidence-probe-2','diagnostic_only':True,'requests':[],
            'case_errors':[], 'execution_completed':False, 'advice_stage_completed':False}
    result['decision_preflight']=decision_preflight(plan,meter)
    preflight={row['id']:row for row in result['decision_preflight']}
    try:
        for request in plan['requests']:
            check=preflight[request['id']]
            if not check['eligible']:
                failure={'id':request['id'],'status':'not_evaluated_input_budget',
                    'error_type':'InputBudgetExceeded','stage':'initial_preflight',
                    'provider_requests_reserved_for_case':0,'preflight':check}
                result['case_errors'].append(failure)
                if on_result:on_result(failure)
                continue
            before=sum(c.get('kind')=='request_reserved' for c in meter.metadata()['calls'])
            try:
                response=meter.extract_structured_data(system_prompt=request['system_prompt'],
                    user_content=json.dumps(request['payload'],sort_keys=True),response_schema=request['response_schema'],
                    schema_name='capability_probe_condition')
            except InputBudgetExceeded:
                after=sum(c.get('kind')=='request_reserved' for c in meter.metadata()['calls'])
                failure={'id':request['id'],'status':'not_evaluated_input_budget',
                    'error_type':'InputBudgetExceeded','stage':'runtime_input_guard',
                    'provider_requests_reserved_for_case':after-before}
                result['case_errors'].append(failure)
                if on_result:on_result(failure)
                continue
            replay={**request,'response':response}
            audited=audit_request(replay,plan['reviewed_evidence'],plan['rubric'])
            audited.update(status='live_response_validated',model_execution_verified=True,
                note='Live metered response; local validation checks grounding and shape, not semantic correctness.',
                system_prompt=request['system_prompt'],
                payload=request['payload'],response_schema=request['response_schema'])
            result['requests'].append(audited)
            if on_result:on_result(audited)
        strengths=bounded_strengths([{'condition_id':v['condition_id'],'basis':v['citations'],'reason':v['reason']}
            for r in result['requests'] for v in r['validated'] if v['state']=='met'])
        remaining=advice_cases
        for audited in result['requests']:
            advice=[]
            for record in audited['validated']:
                if record['state']=='met':continue
                condition=next(c for i in plan['rubric']['indicators'] for c in i['conditions'] if c['id']==record['condition_id'])
                kind=KINDS[record['state']]
                action={'id':record['condition_id'],'type':kind,'operation':OPERATIONS[kind],
                    'requirement':condition['text'],'completion_evidence':condition['completion_evidence'],
                    'suggestion':condition['improvement_pattern'],'state':record['state'],
                    'reason':record['reason'],'citations':record['citations']}
                payload={**{k:audited['payload'][k] for k in ('population','reference_period','sources','reviewed_evidence')},
                    'profile':plan.get('profile',{}),'actions':[action],'established_strengths':strengths,
                    'foundation_goals':[],'scope':audited['payload'].get('scope',{})}
                if processing_failure(record):
                    batch=[deterministic_advice(action,payload,'processing_rerun')];validation={'processing_failure':True}
                elif remaining:
                    remaining-=1
                    batch,validation=tailor_batch(meter,payload,payload)
                else:
                    continue
                advice.append({'condition_id':record['condition_id'],'advice':batch,'validation':validation})
            audited['live_advice']=advice
            if advice and on_result:on_result(audited)
        result['advice_stage_completed']=True
        result['execution_completed']=not result['case_errors']
        if result['case_errors']:
            result['stop_reason']='InputBudgetExceeded'
            result['partial_result_reason']='One or more decision packets exceeded the local input bound; other completed cases remain eligible for advice.'
    except Exception as exc:
        # Provider exception strings can contain confidential inputs or credentials.
        result['stop_reason']=type(exc).__name__
    result['inference']=meter.metadata()
    result['provider_calls_attempted']=any(c.get('kind')=='request_reserved' for c in result['inference']['calls'])
    return result
