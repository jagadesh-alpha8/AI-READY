"""Keep each assessment request under a prompt-token ceiling, for models priced by prompt length.

Claude Haiku 5.5 charges five times as much for a whole request once its prompt is over 100,000 tokens (GPT-6 models
over 272,000). Test 13's assessment prompts were 79,000-95,000 Gemini tokens, and Claude counts the same text as more
tokens, so most would cross. Switched on with CAPABILITY_PROMPT_TOKEN_CEILING and frozen in the run's retrieval policy
(retrieval_policy.prompt_ceiling), it does two things, in this order:

1. Short IDs. Every long ID in an assessment request (page IDs, document IDs, reviewed-evidence IDs) is sent as a short
   label (S1, S2... for packet pages, R1, R2... for the rest) and mapped back in the answer before validation. Nothing
   the judge reads is lost: test 13's requests carried about 190 bytes of IDs and metadata per passage.
2. A smaller keyword lane, only if still over. The packet is rebuilt by retrieval itself with a smaller keyword-lane
   budget, so the passages dropped are the ones retrieval ranks lowest; the discovery lane and the extracted-evidence
   lane are untouched. Cutting the end of a built packet would not do: it is grouped by page, not ordered by rank, and
   in test 13 the last 10% of packet text held 36 of the 132 passages that earned credit.

Tokens are estimated from the request's UTF-8 bytes (CAPABILITY_PROMPT_BYTES_PER_TOKEN, conservative by default;
Gemini measured 3.36 bytes per token on test 13). Every request still records its actual prompt tokens, so the
estimate can be checked after the first run. Re-judging packets (fixed, provisional plus new pages) get short IDs and a
recorded estimate, but are not trimmed.
"""
import copy
import json
import re

VERSION = 'prompt-ceiling-v1'
SHORT_IDS_VERSION = 'short-ids-v1'
UUID = re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')
#: Smallest keyword lane the ceiling may cut to, as a share of the configured one.
FLOOR = 0.4
MAX_REBUILDS = 6
#: The request around the payload: message framing and the answer format's wrapper.
FRAMING_BYTES = 600


def configured():
    """The ceiling to freeze in a new run's retrieval policy, or None when switched off."""
    from django.conf import settings
    tokens = getattr(settings, 'CAPABILITY_PROMPT_TOKEN_CEILING', None)
    if not tokens:
        return None
    per_token = float(getattr(settings, 'CAPABILITY_PROMPT_BYTES_PER_TOKEN', 2.6) or 2.6)
    if type(tokens) is not int or not 20000 <= tokens <= 1000000 or not 1.0 <= per_token <= 6.0:
        from .semantic_retrieval import SemanticRetrievalUnavailable
        raise SemanticRetrievalUnavailable('CAPABILITY_PROMPT_TOKEN_CEILING must be 20000-1000000 tokens and '
                                           'CAPABILITY_PROMPT_BYTES_PER_TOKEN 1.0-6.0.')
    return {'version': VERSION, 'tokens': tokens, 'bytes_per_token': per_token, 'short_ids': SHORT_IDS_VERSION}


# ------------------------------------------------------------------ short IDs


def _packet_ids(data):
    return [s.get('id') for s in data.get('sources') or [] if isinstance(s, dict) and isinstance(s.get('id'), str)]


def aliases(data, schema=None):
    """{long id: short label} for every long ID in a request's payload (and answer format): packet pages first, in
    packet order, as S1..; any other ID as R1.. in order of appearance."""
    table = {}
    for value in _packet_ids(data):
        if UUID.match(value) and value not in table:
            table[value] = f'S{len(table) + 1}'
    others = []

    def walk(node):
        if isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
        elif isinstance(node, str) and UUID.match(node) and node not in table and node not in others:
            others.append(node)
    walk(data)
    walk(schema)
    for n, value in enumerate(others, 1):
        table[value] = f'R{n}'
    return table


def replace(node, table):
    """`node` with every string that is a key of `table` replaced by its value (dict keys too)."""
    if isinstance(node, dict):
        return {table.get(k, k) if isinstance(k, str) else k: replace(v, table) for k, v in node.items()}
    if isinstance(node, list):
        return [replace(v, table) for v in node]
    if isinstance(node, str):
        return table.get(node, node)
    return node


def shorten(user_content, schema):
    """(user content, answer format, {short label: long id}) with long IDs replaced by short labels."""
    try:
        data = json.loads(user_content)
    except (TypeError, ValueError):
        return user_content, schema, {}
    table = aliases(data, schema)
    if not table:
        return user_content, schema, {}
    return (json.dumps(replace(data, table), sort_keys=True), replace(schema, table),
            {short: long for long, short in table.items()})


class ShortIds:
    """A scoring client that sends short IDs and maps them back in the answer; everything else passes through."""

    def __init__(self, service):
        self._service = service

    def __getattr__(self, name):
        return getattr(self._service, name)

    def extract_structured_data(self, **kwargs):
        content, schema, back = shorten(kwargs.get('user_content'), kwargs.get('response_schema'))
        if not back:
            return self._service.extract_structured_data(**kwargs)
        result = self._service.extract_structured_data(**{**kwargs, 'user_content': content,
                                                          'response_schema': schema})
        return replace(result, back)


# ------------------------------------------------------------------ the estimate and the smaller keyword lane


def request_bytes(system_prompt, user_content, schema, *, short_ids=True):
    if short_ids:
        user_content, schema, _ = shorten(user_content, schema)
    return (len(system_prompt.encode()) + len(user_content.encode())
            + len(json.dumps(schema, separators=(',', ':')).encode()) + FRAMING_BYTES)


def estimate(policy, system_prompt, user_content, schema):
    """Estimated prompt tokens of one request under the frozen ceiling policy."""
    size = request_bytes(system_prompt, user_content, schema, short_ids=bool(policy.get('short_ids')))
    return int(size / policy['bytes_per_token']) + 1


def smaller(ranker, keyword_chars):
    """A copy of the frozen ranker (same model and cache) with a smaller keyword lane; the discovery lane keeps its
    budget."""
    expansion = ranker.context_chars - ranker.baseline_chars
    trimmed = copy.copy(ranker)
    trimmed.baseline_chars = keyword_chars
    trimmed.context_chars = keyword_chars + expansion
    return trimmed


def fit(policy, ranker, build, measure):
    """(context, extras, audit): the packet from `build(ranker)`, rebuilt with a smaller keyword lane while
    `measure(context, extras)` (estimated prompt tokens) is over the ceiling.

    build(ranker) -> (context, extras); measure(context, extras) -> tokens."""
    context, extras = build(ranker)
    tokens = before = measure(context, extras)
    audit = {'version': policy['version'], 'ceiling_tokens': policy['tokens'], 'estimated_tokens': before,
             'keyword_chars': ranker.baseline_chars if ranker is not None else None, 'rebuilds': 0}
    if ranker is None or tokens <= policy['tokens']:
        return context, extras, audit
    original, keyword = context, ranker.baseline_chars
    floor = int(ranker.baseline_chars * FLOOR)
    while tokens > policy['tokens'] and audit['rebuilds'] < MAX_REBUILDS and keyword > floor:
        excess_chars = int((tokens - policy['tokens']) * policy['bytes_per_token'] * 1.05) + 500
        keyword = max(floor, keyword - excess_chars)
        context, extras = build(smaller(ranker, keyword))
        tokens = measure(context, extras)
        audit['rebuilds'] += 1
    kept = {(e['id'], e.get('text_offset'), len(e.get('text') or '')) for e in context}
    dropped = [e for e in original if (e['id'], e.get('text_offset'), len(e.get('text') or '')) not in kept]
    audit.update(estimated_tokens_before=before, estimated_tokens=tokens, keyword_chars=keyword,
                 keyword_chars_before=ranker.baseline_chars, over_ceiling=tokens > policy['tokens'],
                 dropped_chars=sum(len(e.get('text') or '') for e in dropped),
                 dropped=[{'id': e['id'], 'document_id': e.get('document_id'), 'page_number': e.get('page_number'),
                           'text_offset': e.get('text_offset'), 'chars': len(e.get('text') or '')} for e in dropped])
    return context, extras, audit
