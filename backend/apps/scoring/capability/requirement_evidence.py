"""Record-form candidates for the five-condition requirement evidence pilot."""
import hashlib
import json
import re
from copy import deepcopy
from functools import lru_cache
from pathlib import Path

# These patterns nominate excerpts. The assessor uses the frozen rubric to judge
# sufficiency and linkage. A hit has no effect on scoring by itself.
RECORD_FORMS = {
    'ai_guidance': (r'\b(?:AI|artificial intelligence|machine learning)\b', r'\b(?:guidance|policy|acceptable use|academic integrity|permitted|prohibited|must)\b'),
    'effective_status': (r'\b(?:effective(?: date| from)?|adopted|entered into force|in force|commenced)\b', r'\b20\d{2}\b'),
    'policy_requirement': (r'\b(?:AI|artificial intelligence)\b', r'\b(?:policy|provision|clause|requirement)\b'),
    'ai_deployment': (r'\b(?:AI|artificial intelligence|machine learning|chatbot)\b', r'\b(?:deployment|deployed|onboarding|rollout|system|pilot)\b'),
    'completed_policy_check': (r'\b(?:checked|completed|verified|approved|signed off|passed)\b', r'\b(?:deployment|onboarding|checklist|sign.off|risk review|policy)\b'),
    'service_measurement': (r'\b(?:measured|observed|recorded|actual|achieved|monitoring)\b', r'\b(?:capacity|availability|uptime|concurrent|throughput|utilization)\b'),
    'service_target': (r'\b(?:target|SLA|service.level|threshold)\b', r'\b(?:capacity|availability|uptime|concurrent|throughput|utilization)\b'),
    'service_comparison': (r'\b(?:compared|against|exceeded|fell short|missed|met the target)\b', r'\b(?:review|target|SLA|capacity|availability|uptime)\b'),
    'corrective_action': (r'\b(?:corrective action|action register|action plan|remediation|remedial action)\b',),
    'completion_check': (r'\b(?:verified|inspected|confirmed|checked)\b', r'\b(?:closure|closed|completed|completion|implemented|carried out)\b'),
    'feedback_finding': (r'\b(?:feedback|survey|consultation)\b', r'\b(?:reported|identified|found|finding|respondents|complaints)\b'),
    'implemented_change': (r'\b(?:implemented|introduced|changed|revised|rolled out|deployed)\b', r'\b(?:feedback|response|finding|complaints|survey)\b'),
    'subsequent_result': (r'\b(?:follow.up|subsequent|post.implementation|after the change)\b', r'\b(?:result|reported|measured|survey|review|found)\b'),
}
RECORD_FORMS = {name: tuple(re.compile(pattern, re.I) for pattern in patterns)
                for name, patterns in RECORD_FORMS.items()}


def requirement_rows(indicator, sources, allowance):
    """Yield compact, exact excerpts for distinct requested record forms."""
    parts = list(dict.fromkeys(
        part for condition in indicator.get('conditions', ())
        for part in condition.get('evidence_parts', {}) if part in RECORD_FORMS
    ))
    if not parts:
        return
    size = min(600, allowance // len(parts))
    if size < 100:
        return
    best = {}
    for source in sources:
        for offset in range(0, len(source['text']), size // 2):
            excerpt = source['text'][offset:offset + size]
            for part in parts:
                hits = [len(pattern.findall(excerpt)) for pattern in RECORD_FORMS[part]]
                if all(hits):
                    key = (-sum(min(2, count) for count in hits), excerpt, source['id'], offset)
                    if part not in best or key < best[part][0]:
                        best[part] = (key, (source, offset, excerpt, None))
    for part in parts:
        if part in best:
            yield best[part][1]


@lru_cache(maxsize=1)
def pilot_specs():
    return json.loads(Path(__file__).with_name('requirement_evidence_pilot_v1.json').read_bytes())


def apply_pilot(rubric):
    """Build a separately identified rubric for explicit, non-publication testing."""
    rubric = deepcopy(rubric)
    specs = pilot_specs()
    for indicator in rubric['indicators']:
        for condition in indicator['conditions']:
            if condition['id'] in specs:
                condition.update(deepcopy(specs[condition['id']]))
    rubric['evidence_pilot'] = 'requirement-evidence-1'
    rubric.pop('content_hash', None)
    rubric['content_hash'] = hashlib.sha256(json.dumps(rubric, sort_keys=True).encode()).hexdigest()
    return rubric
