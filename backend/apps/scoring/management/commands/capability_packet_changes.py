"""Which of a finished run's packets would be different under today's packet rules? No model calls.

    python manage.py capability_packet_changes RUN_ID [--indicator AIQIF-C1.2 ...] [--json]

For each key indicator the run's packet is rebuilt twice with its own frozen retrieval policy: once as the run had it
(checked against its trace, so a rebuild that does not reproduce the run is flagged), and once with today's
extracted-evidence lane (the only packet rule changed since test 13: extracted-evidence-lane-2, 22 Nov). A key
indicator whose packet is unchanged lets a later run on another model be compared with this run on identical
evidence; one whose packet changed can only be compared with care.

Written for test 14 (23 Nov): test 13 (Gemini) is the reference for the Claude and OpenAI runs, compared only on the
key indicators whose packets did not change. Needs the run's frozen pages (in the database) and the frozen embedding
model, like capability_page_use.
"""
import json

from django.core.management.base import BaseCommand, CommandError

from apps.scoring.models import CapabilityRun


def changes(run, *, indicators=None, ranker=None, lane_version=None):
    from apps.scoring.capability.evaluation import _prepare
    from apps.scoring.capability.page_use import _completed_payload, _structure, compare_packets, retrieval_sources
    from apps.scoring.capability.reviewed_evidence import LANE_VERSION_2
    from apps.scoring.capability.semantic_retrieval import ranker_for
    inputs = run.inputs or {}
    policy = inputs.get('retrieval_policy') or {}
    execution = inputs.get('execution_policy') or {}
    sources = retrieval_sources(run)
    if not sources:
        raise CommandError('The run has no frozen pages in the database.')
    payload = _completed_payload(run)
    traces = {t['indicator']: t for t in payload.get('traces') or []}
    records = payload.get('records') or []
    ranker = ranker if ranker is not None else ranker_for(policy)
    today = lane_version or LANE_VERSION_2
    common = dict(sources=sources, semantic_ranker=ranker, gemini=True, reviewed_evidence=inputs.get('reviewed_evidence'),
                  population=inputs.get('population') or '', reference_period=inputs.get('reference_period') or '',
                  scope=inputs.get('scope'), structure=_structure(sources, policy),
                  ceiling=policy.get('prompt_ceiling'), judgment=execution.get('judgment', 'conditions'),
                  keyword_chars=policy.get('keyword_chars'))
    rows = []
    for indicator in inputs['rubric']['indicators']:
        code = indicator['code']
        if indicators and code not in indicators:
            continue
        packet = (traces.get(code) or {}).get('source_excerpts') or []
        as_run = _prepare(indicator, **common, lane_version=policy.get('evidence_lane'))
        reproduced, _ = compare_packets(packet, as_run['context'])
        if policy.get('evidence_lane') == today:
            same, diff = reproduced, None
        else:
            rebuilt = _prepare(indicator, **common, lane_version=today)
            same, diff = compare_packets(packet, rebuilt['context'])
        ids = {c['id'] for c in indicator['conditions']}
        credited = sorted(r['condition_id'] for r in records if r['condition_id'] in ids and (r.get('credit') or 0) > 0)
        rows.append({'indicator': code, 'name': indicator['name'], 'reproduced': reproduced, 'unchanged': same,
                     'requirements': len(ids), 'credited_requirements': credited,
                     **({} if same else {'differences': diff})})
    usable = [r for r in rows if r['reproduced'] and r['unchanged']]
    return {'run_id': str(run.pk), 'run_lane': policy.get('evidence_lane') or 'extracted-evidence-lane-1',
            'today_lane': today, 'indicators': rows,
            'summary': {'indicators': len(rows), 'reproduced': sum(r['reproduced'] for r in rows),
                        'unchanged': len(usable), 'changed': sum(not r['unchanged'] for r in rows),
                        'usable_for_comparison': [r['indicator'] for r in usable],
                        'requirements_usable': sum(r['requirements'] for r in usable)}}


class Command(BaseCommand):
    help = "Which of a run's packets today's packet rules would change (no model calls)."

    def add_arguments(self, parser):
        parser.add_argument('run_id')
        parser.add_argument('--indicator', action='append')
        parser.add_argument('--json', action='store_true')

    def handle(self, *args, **options):
        run = CapabilityRun.objects.filter(pk=options['run_id']).first()
        if run is None:
            raise CommandError('No such run.')
        try:
            result = changes(run, indicators=options['indicator'])
        except ValueError as exc:
            raise CommandError(str(exc))
        if options['json']:
            self.stdout.write(json.dumps(result, indent=1, default=str))
            return
        s = result['summary']
        self.stdout.write(f"Lane: the run used {result['run_lane']}; today's is {result['today_lane']}.")
        self.stdout.write(f"Packets rebuilt exactly as the run had them: {s['reproduced']} of {s['indicators']}.")
        self.stdout.write(f"Unchanged under today's rules: {s['unchanged']} key indicators ({s['requirements_usable']} "
                          f"requirements); changed: {s['changed']}.")
        for row in result['indicators']:
            if not row['reproduced']:
                self.stdout.write(f"  {row['indicator']} {row['name']}: not reproduced as the run had it; leave it out")
            elif not row['unchanged']:
                d = row['differences']['counts']
                self.stdout.write(f"  {row['indicator']} {row['name']}: changed ({d['only_in_run']} passages only in the "
                                  f"run, {d['only_in_rebuild']} only today); credited: "
                                  f"{', '.join(row['credited_requirements']) or 'none'}")
