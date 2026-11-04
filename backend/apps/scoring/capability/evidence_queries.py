"""Bounded deterministic requirement queries; relevance is not an entailment decision."""
import re

REFERENCE = re.compile(r'\b(that|this|these|those|such|its|their|same|it)\b', re.I)


def requirement_queries(indicator, ranker):
    result = []
    previous = None
    for condition in indicator.get('conditions', []):
        assertion = condition['text'].strip()
        variants = [assertion]
        anchor = previous['text'] if previous and REFERENCE.search(assertion) else ''
        allowance = min(192, ranker.token_limit - 32)
        def clipped(text, limit):
            offsets = ranker.token_offsets(text)
            return text[:offsets[limit - 1][1]] if limit and len(offsets) > limit else text if limit else ''
        if anchor:
            current = clipped(assertion, min(128, allowance))
            context = clipped(anchor, min(48, max(0, allowance - len(ranker.token_offsets(current)))))
            variants.insert(0, (context + ' ' + current).strip())
        explicit = condition.get('evidence_queries') or condition.get('evidence_examples') or []
        if isinstance(explicit, list):
            variants.extend(x.strip() for x in explicit if isinstance(x, str) and x.strip())
        bounded = []
        for variant in dict.fromkeys(variants):
            offsets = ranker.token_offsets(variant)
            query = variant[:offsets[allowance - 1][1]] if len(offsets) > allowance else variant
            if query and query not in bounded:
                bounded.append(query)
            if len(bounded) == 2:
                break
        result.append({'condition_id': condition.get('id', str(len(result))), 'assertion': assertion,
                       'anchor': anchor, 'queries': bounded,
                       'query_clipped': any(len(ranker.token_offsets(v)) > allowance for v in variants) or
                           bool(anchor and context != anchor)})
        previous = condition
    return result or [{'condition_id': indicator['code'], 'assertion': indicator['name'],
                       'anchor': '', 'queries': [indicator['name']]}]
