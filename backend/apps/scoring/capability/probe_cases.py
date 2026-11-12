"""Bind private diagnostic cases by stable bundle IDs, never list positions.

Expectations remain outside the model payload. This builder cannot award credit;
source dates, scope and semantic sufficiency still need adjudication.
"""
import re
from .evidence_cases import validate_cases
from .reviewed_evidence import for_context
from .scope import context_scope
from .evaluation import SYSTEM_PROMPT, indicator_schema
from .storage import digest


def request_from_bundle(replay, pack, condition_id, bundle_id, *, ledger, scope, population, reference_period):
    cases=validate_cases(pack,replay['rubric'],replay['sources'])
    case=next((c for c in cases if c['condition_id']==condition_id),None)
    if case is None:
        raise ValueError('Unknown probe requirement.')
    choices=[(kind,b) for kind in ('positive_bundles','insufficient_controls') for b in case[kind] if b['id']==bundle_id]
    if len(choices)!=1:
        raise ValueError('Probe bundle ID must identify exactly one reviewed bundle.')
    kind,bundle=choices[0]
    sources=[]
    for cite in bundle['citations']:
        pages=[s for s in replay['sources'] if s['document_id']==cite['document_id'] and s['page_number']==cite['page']]
        if len(pages)!=1:
            raise ValueError('Probe citation must identify exactly one frozen page.')
        page=pages[0]
        matches=list(re.finditer(r'\s+'.join(re.escape(w) for w in cite['quote'].split()),page['text']))
        if len(matches)!=1:
            raise ValueError('Probe quotation must have one unambiguous source span.')
        match=matches[0]
        sources.append({**{k:v for k,v in page.items() if k!='retrieval_hints'},
            'text':page['text'][match.start():match.end()],'text_offset':match.start()})
    full=next(i for i in replay['rubric']['indicators'] if any(c['id']==condition_id for c in i['conditions']))
    indicator={**full,'conditions':[c for c in full['conditions'] if c['id']==condition_id]}
    payload={'indicator':indicator,'sources':sources,'reviewed_evidence':for_context(ledger,sources),
        'population':population,'reference_period':reference_period,'scope':context_scope(scope,sources)}
    return {'id':condition_id+':'+bundle_id,'condition_id':condition_id,
        'evidence_bundle_id':bundle_id,'bundle_kind':kind,'selection_method':'reviewed_bundle_id',
        'expected_interpretation':bundle.get('reason','Potential content support only; scope and applicable period must be established separately.'),
        'limited_packet_expectation':bundle.get('expected_on_this_packet','scope_and_period_conditional'),
        'payload':payload,'payload_hash':digest(payload),'system_prompt':SYSTEM_PROMPT,
        'response_schema':indicator_schema(indicator,sources)}
