"""Bounded deterministic requirement queries; relevance is not an entailment decision."""
import re
from .query_profiles import evidence_query

REFERENCE = re.compile(r'\b(that|this|these|those|such|its|their|same|it)\b', re.I)


def requirement_queries(indicator, ranker):
    result = []
    previous = None
    for condition in indicator.get('conditions', []):
        assertion = condition['text'].strip()
        variants = [assertion]
        roles = ['assertion']
        profile = evidence_query(condition)
        anchor = previous['text'] if previous and REFERENCE.search(assertion) else ''
        allowance = min(192, ranker.token_limit - 32)
        def clipped(text, limit):
            offsets = ranker.token_offsets(text)
            return text[:offsets[limit - 1][1]] if limit and len(offsets) > limit else text if limit else ''
        if anchor:
            current = clipped(assertion, min(128, allowance))
            context = clipped(anchor, min(48, max(0, allowance - len(ranker.token_offsets(current)))))
            variants = [(context + ' ' + current).strip()]
            roles = ['contextual_assertion']
        if profile:
            variants.insert(0, profile)
            roles.insert(0, 'evidence_records')
        explicit = condition.get('evidence_queries') or condition.get('evidence_examples') or []
        if isinstance(explicit, list):
            for value in explicit:
                if isinstance(value, str) and value.strip():
                    variants.append(value.strip())
                    roles.append('supplied_evidence_query')
        bounded, bounded_roles = [], []
        for variant, role in zip(variants, roles):
            offsets = ranker.token_offsets(variant)
            query = variant[:offsets[allowance - 1][1]] if len(offsets) > allowance else variant
            if query and query not in bounded:
                bounded.append(query)
                bounded_roles.append(role)
            if len(bounded) == 2:
                break
        result.append({'condition_id': condition.get('id', str(len(result))), 'assertion': assertion,
                       'anchor': anchor, 'queries': bounded, 'query_roles': bounded_roles,
                       'evidence_query': profile,
                       'query_clipped': any(len(ranker.token_offsets(v)) > allowance for v in variants) or
                           bool(anchor and context != anchor)})
        previous = condition
    return result or [{'condition_id': indicator['code'], 'assertion': indicator['name'],
                       'anchor': '', 'queries': [indicator['name']], 'query_roles': ['indicator_fallback'],
                       'evidence_query': '', 'query_clipped': False}]
