"""What a prompt ceiling would cut from a finished run's packets, and whether it would cut evidence that earned credit.
No model calls.

    python manage.py capability_prompt_ceiling_check RUN_ID                       # 95,000 tokens at 2.6 bytes/token
    python manage.py capability_prompt_ceiling_check RUN_ID --ceiling 95000 --bytes-per-token 2.9 --json

For each key indicator the run's packet is rebuilt with its own frozen retrieval policy, first as it was (checked
against the run's trace) and then under the ceiling (prompt_ceiling.py: short IDs, then a smaller keyword lane while the
estimated prompt is over). A credited requirement's quotation counts as kept when a passage of the same page in the
rebuilt packet still contains it. Needs the run's frozen pages (in the database) and the frozen embedding model, like
capability_page_use.
"""
import json

from django.core.management.base import BaseCommand, CommandError

from apps.scoring.models import CapabilityRun


def _completed(run):
    event = run.events.filter(state='completed').order_by('-created_at').first()
    if event is None or not (event.payload or {}).get('records'):
        raise CommandError('The run has no completed assessment.')
    return event.payload


def _kept(quote, page_id, packet):
    """True when a window of the page still holds the quotation, compared as the citation validator compares it
    (citations.normalize: stored quotations have their whitespace collapsed). Test 13 at 2.9 bytes per token (23 Nov):
    44 credited parts were reported lost with nothing trimmed, because a quotation spanning a line break is not a
    substring of the raw page text."""
    from apps.scoring.capability.citations import normalize
    quote = normalize(quote or '')
    return bool(quote) and any(e['id'] == page_id and quote in normalize(e.get('text') or '') for e in packet)


def check(run, *, ceiling_tokens, bytes_per_token, indicators=None, ranker=None):
    from apps.scoring.capability import prompt_ceiling
    from apps.scoring.capability.evaluation import _prepare, map_argument
    from apps.scoring.capability.page_use import _structure
    from apps.scoring.capability.semantic_retrieval import ranker_for
    inputs = run.inputs or {}
    policy = inputs.get('retrieval_policy') or {}
    execution = inputs.get('execution_policy') or {}
    sources = inputs.get('sources') or []
    if not sources:
        raise CommandError('The run has no frozen pages in the database.')
    payload = _completed(run)
    traces = {t['indicator']: t for t in payload.get('traces') or []}
    ranker = ranker if ranker is not None else ranker_for(policy)
    ceiling = {'version': prompt_ceiling.VERSION, 'tokens': ceiling_tokens, 'bytes_per_token': bytes_per_token,
               'short_ids': prompt_ceiling.SHORT_IDS_VERSION}
    judgment = execution.get('judgment', 'conditions')
    common = dict(sources=sources, semantic_ranker=ranker, gemini=True, reviewed_evidence=inputs.get('reviewed_evidence'),
                  population=inputs['population'], reference_period=inputs['reference_period'],
                  scope=inputs.get('scope'), structure=_structure(sources, policy),
                  lane_version=policy.get('evidence_lane'), judgment=judgment,
                  keyword_chars=policy.get('keyword_chars'),
                  evidence_map=map_argument(policy, inputs.get('evidence_map')))
    rows = []
    for indicator in inputs['rubric']['indicators']:
        code = indicator['code']
        if indicators and code not in indicators:
            continue
        as_run = _prepare(indicator, **common)
        trimmed = _prepare(indicator, **common, ceiling=ceiling)
        audit = trimmed.get('prompt_ceiling') or {}
        traced = {(e['id'], e.get('text_offset')) for e in (traces.get(code) or {}).get('source_excerpts') or []}
        rebuilt = {(e['id'], e.get('text_offset')) for e in as_run['context']}
        ids = {c['id'] for c in indicator['conditions']}
        lost = []
        for record in payload['records']:
            if record['condition_id'] not in ids or not (record.get('credit') or 0) > 0:
                continue
            for part in record.get('parts') or []:
                if part.get('credited_as') not in ('full', 'related'):
                    continue
                for citation in part.get('citations') or []:
                    if not _kept(citation.get('quote') or '', citation.get('source_id'), trimmed['context']):
                        lost.append({'condition_id': record['condition_id'], 'part_id': part.get('id'),
                                     'credit': record['credit'], 'source_id': citation.get('source_id')})
        whole = {}
        for row in lost:
            whole.setdefault(row['condition_id'], set()).add((row['part_id'], row['source_id']))
        # A requirement is at risk when a credited part lost every quotation it had.
        at_risk = []
        for record in payload['records']:
            if record['condition_id'] not in whole:
                continue
            for part in record.get('parts') or []:
                cites = {(part.get('id'), c.get('source_id')) for c in part.get('citations') or []}
                if part.get('credited_as') in ('full', 'related') and cites and cites <= whole[record['condition_id']]:
                    at_risk.append({'condition_id': record['condition_id'], 'part_id': part.get('id'),
                                    'credit': record['credit']})
        rows.append({'indicator': code, 'reproduced': rebuilt == traced if traced else None,
                     'estimated_tokens_before': audit.get('estimated_tokens_before', audit.get('estimated_tokens')),
                     'estimated_tokens': audit.get('estimated_tokens'), 'over_ceiling': audit.get('over_ceiling', False),
                     'keyword_chars_before': audit.get('keyword_chars_before', audit.get('keyword_chars')),
                     'keyword_chars': audit.get('keyword_chars'), 'dropped_chars': audit.get('dropped_chars', 0),
                     'dropped_passages': len(audit.get('dropped') or []), 'credited_quotations_lost': lost,
                     'credited_parts_left_without_a_quotation': at_risk})
    return {'run_id': str(run.pk), 'ceiling_tokens': ceiling_tokens, 'bytes_per_token': bytes_per_token,
            'indicators': rows,
            'summary': {'indicators': len(rows), 'trimmed': sum(bool(r['dropped_passages']) for r in rows),
                        'still_over': sum(bool(r['over_ceiling']) for r in rows),
                        'reproduced': sum(r['reproduced'] is True for r in rows),
                        'credited_quotations_lost': sum(len(r['credited_quotations_lost']) for r in rows),
                        'credited_parts_left_without_a_quotation':
                            sum(len(r['credited_parts_left_without_a_quotation']) for r in rows)}}


class Command(BaseCommand):
    help = 'What a prompt ceiling would cut from a run\'s packets, and whether that evidence earned credit (no model calls).'

    def add_arguments(self, parser):
        parser.add_argument('run_id')
        parser.add_argument('--ceiling', type=int, default=95000)
        parser.add_argument('--bytes-per-token', type=float, default=2.6)
        parser.add_argument('--indicator', action='append')
        parser.add_argument('--json', action='store_true')

    def handle(self, *args, **options):
        run = CapabilityRun.objects.filter(pk=options['run_id']).first()
        if run is None:
            raise CommandError('No such run.')
        result = check(run, ceiling_tokens=options['ceiling'], bytes_per_token=options['bytes_per_token'],
                       indicators=options['indicator'])
        if options['json']:
            self.stdout.write(json.dumps(result, indent=1, default=str))
            return
        s = result['summary']
        self.stdout.write(f"Ceiling {result['ceiling_tokens']} tokens at {result['bytes_per_token']} bytes per token.")
        self.stdout.write(f"Packets rebuilt as the run had them: {s['reproduced']} of {s['indicators']} "
                          '(fewer means ranks differ from the run: treat the rest as indicative).')
        self.stdout.write(f"Trimmed: {s['trimmed']} key indicators; still over the ceiling at the floor: {s['still_over']}.")
        self.stdout.write(f"Credited quotations no longer in the packet: {s['credited_quotations_lost']}; credited parts "
                          f"left with no quotation: {s['credited_parts_left_without_a_quotation']}.")
        for row in result['indicators']:
            if row['dropped_passages'] or row['credited_quotations_lost']:
                self.stdout.write(f"  {row['indicator']}: ~{row['estimated_tokens_before']} -> ~{row['estimated_tokens']} "
                                  f"tokens; keyword lane {row['keyword_chars_before']} -> {row['keyword_chars']} chars; "
                                  f"{row['dropped_passages']} passages dropped; credited parts at risk: "
                                  f"{', '.join(r['condition_id'] + ' ' + str(r['part_id']) for r in row['credited_parts_left_without_a_quotation']) or 'none'}")
