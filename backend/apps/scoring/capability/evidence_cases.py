"""Private, reviewed support bundles: packet inclusion is not assessment truth."""
from .evaluation import _normal

VERSION = 'requirement-evidence-cases-1'


def validate_cases(pack, rubric, sources):
    from .storage import digest
    if not isinstance(pack, dict) or pack.get('version') != VERSION:
        raise ValueError('Unsupported evidence-case format.')
    if pack.get('source_corpus_hash') != digest(sources) or pack.get('rubric_hash') != digest(rubric):
        raise ValueError('Evidence cases do not match this frozen corpus and rubric.')
    cases = pack.get('cases')
    if not isinstance(cases, list) or not cases:
        raise ValueError('Evidence cases must be a nonempty list.')
    assertions = {c['id']: c['text'] for i in rubric['indicators'] for c in i['conditions']}
    seen = set()
    for case in cases:
        if not isinstance(case, dict) or case.get('condition_id') not in assertions:
            raise ValueError('Evidence case has an unknown requirement.')
        cid = case['condition_id']
        if cid in seen or case.get('assertion') != assertions[cid]:
            raise ValueError('Evidence-case requirements must be unique and assertions unchanged.')
        seen.add(cid)
        positive, controls = case.get('positive_bundles'), case.get('insufficient_controls')
        if not isinstance(positive, list) or not isinstance(controls, list) or not (positive or controls):
            raise ValueError('Each evidence case needs support bundles or explicit controls.')
        bundle_ids = set()
        for bundle in positive + controls:
            if (not isinstance(bundle, dict) or not isinstance(bundle.get('id'), str)
                    or not bundle['id'] or bundle['id'] in bundle_ids):
                raise ValueError('Evidence bundle IDs must be nonempty and unique within a case.')
            bundle_ids.add(bundle['id'])
            citations = bundle.get('citations')
            if not isinstance(citations, list) or not citations:
                raise ValueError('An evidence bundle needs at least one source quotation.')
            for citation in citations:
                if (not isinstance(citation, dict) or not isinstance(citation.get('quote'), str)
                        or not citation['quote'].strip() or type(citation.get('page')) is not int
                        or not any(s['document_id'] == citation.get('document_id')
                            and s['page_number'] == citation['page']
                            and _normal(citation['quote']) in _normal(s['text']) for s in sources)):
                    raise ValueError('Evidence-case quotation is absent from its frozen source page.')
        for control in controls:
            if control.get('expected_on_this_packet') not in {'unknown', 'adjudication_needed'} or not control.get('reason'):
                raise ValueError('Controls need an explicit limited-packet expectation and reason.')
    return cases


def packet_coverage(cases, rubric, sources, *, selector, budget):
    """AND within a support bundle; OR across alternatives. Never awards credit.

    An absent known bundle is not proof that a packet has no acceptable evidence.
    Controls describe isolated test packets; their presence alongside positive
    evidence cannot turn a production packet into an expected unknown.
    """
    indicators = {c['id']: i for i in rubric['indicators'] for c in i['conditions']}
    packets, rows = {}, []
    for case in cases:
        indicator = indicators[case['condition_id']]
        if indicator['code'] not in packets:
            packets[indicator['code']] = selector(indicator, sources, max_chars=budget)
        packet = packets[indicator['code']]
        def matches(citation):
            return any(s['document_id'] == citation['document_id'] and s['page_number'] == citation['page']
                       and _normal(citation['quote']) in _normal(s['text']) for s in packet)
        matched = [b['id'] for b in case['positive_bundles'] if all(matches(c) for c in b['citations'])]
        rows.append({'condition_id': case['condition_id'], 'matched_bundle_ids': matched,
            'known_positive_bundle_present': bool(matched) if case['positive_bundles'] else None,
            'positive_bundle_count': len(case['positive_bundles']),
            'insufficient_control_count': len(case['insufficient_controls']),
            'adjudication_needed': any(c['expected_on_this_packet'] == 'adjudication_needed'
                                     for c in case['insufficient_controls'])})
    return {'cases': rows, 'positive_cases': sum(bool(c['positive_bundles']) for c in cases),
        'positive_cases_with_known_support': sum(r['known_positive_bundle_present'] is True for r in rows),
        'cases_without_verified_positive': sum(not c['positive_bundles'] for c in cases),
        'assessment_decisions_tested': False,
        'note': 'Presence measures supplied, provisionally reviewed support bundles, not met decisions. '
                'Alternatives are not exhaustive; scope/period and semantic sufficiency still require evaluation.'}
