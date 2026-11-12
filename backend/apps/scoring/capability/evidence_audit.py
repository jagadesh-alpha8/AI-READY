"""Replay prepared evidence requests locally; missing responses remain unexecuted."""
from copy import deepcopy
from .reviewed_evidence import for_context
from .evaluation import validate_decisions, response_audit
from .engine import assess
from .recommendations import KINDS, OPERATIONS, processing_failure
from .storage import digest


def audit_request(request, ledger, rubric):
    payload = request['payload']
    if request.get('payload_hash') and digest(payload) != request['payload_hash']:
        raise ValueError('Prepared payload hash mismatch.')
    indicator, sources = payload['indicator'], payload['sources']
    canonical = next((i for i in rubric['indicators'] if i['code'] == indicator['code']), None)
    assertions = {c['id']: c for c in (canonical or {}).get('conditions', [])}
    ids = [c['id'] for c in indicator['conditions']]
    if (not canonical or not ids or len(ids) != len(set(ids))
            or any(c != assertions.get(c['id']) for c in indicator['conditions'])
            or indicator != {**canonical, 'conditions': indicator['conditions']}):
        raise ValueError('Prepared indicator or assertions differ from the frozen rubric.')
    attachments = {}
    rebuilt = for_context(ledger, sources, diagnostics=attachments)
    result = {'id': request['id'], 'payload_hash': digest(payload), 'sources': sources,
              'reviewed_evidence_packet': payload.get('reviewed_evidence'),
              'attachment_audit': attachments,
              'review_packet_matches_current_projection': rebuilt == payload.get('reviewed_evidence'),
              'response_present': 'response' in request,
              'model_execution_verified': False,
              'note': 'A supplied response is replay input, not proof of a provider call. Attachment is not assertion sufficiency.'}
    if 'response' not in request:
        result['status'] = 'prepared_unexecuted'
        return result
    if not result['review_packet_matches_current_projection']:
        raise ValueError('Review packet differs from the supplied validation ledger projection.')
    response = deepcopy(request['response'])
    validated = validate_decisions(indicator, response, sources, reviewed_evidence=ledger)
    result.update(status='response_replayed', raw_response=response,
                  response_audit=response_audit(indicator, response, validated), validated=validated)
    states = {r['condition_id']: r['state'] for r in validated}
    result['score_with_all_other_requirements_unknown'] = assess(states, rubric)
    base = assess({}, rubric)
    result['demonstrated_points_from_this_packet'] = round(
        result['score_with_all_other_requirements_unknown']['lower'] - base['lower'], 2)
    advice = []
    for record in validated:
        state = record['state']
        kind = KINDS.get(state)
        advice.append({'condition_id': record['condition_id'], 'state': state,
            'kind': kind, 'operation': OPERATIONS.get(kind),
            'processing_failure': processing_failure(record),
            'validation_issue': record['validation_issue'],
            'basis': record['citations'],
            'supplied_advice': [a for a in request.get('advice', []) if a['condition_id'] == record['condition_id']],
            'advice_generated': False})
    result['recommendation_audit'] = advice
    return result
