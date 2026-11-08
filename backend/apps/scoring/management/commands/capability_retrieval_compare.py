"""Offline ablation on a frozen corpus; neither evaluation nor database writes."""
import json
from time import perf_counter
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from apps.scoring.capability.storage import frozen_sources


class Command(BaseCommand):
    help = 'Compare protected hybrid, profile discovery and BM25 at base and expanded budgets, without evaluator calls.'

    def add_arguments(self, parser):
        parser.add_argument('run_id', nargs='?')
        parser.add_argument('--gold')
        parser.add_argument('--replay-inputs', help='Private comparison JSON containing replay_inputs; bypasses database access.')
        parser.add_argument('--evidence-cases', help='Private requirement-level support bundles and insufficient-evidence controls.')
        parser.add_argument('--holdout-gold', help='Additional labelled set; an inspected former holdout is a regression set.')
        parser.add_argument('--output', required=True, help='A new private JSON file outside the repository.')
        parser.add_argument('--budget', type=int, default=18000)
        parser.add_argument('--expansion-budget', type=int, default=6000)
        parser.add_argument('--matched-routes', action='store_true',
                            help='Also compare lexical, dense and fused ranking with the same packer and base budget.')
        parser.add_argument('--include-replay-inputs', action='store_true', help='Include the private frozen corpus and labels for offline replay; never commit this output.')

    def handle(self, *args, **options):
        from apps.scoring.models import CapabilityRun
        from apps.scoring.capability.evaluation import select_context
        from apps.scoring.capability.pipeline_diagnostics import retrieval_recall
        from apps.scoring.capability.semantic_retrieval import configured_policy, ranker_for
        from apps.scoring.capability.storage import digest
        output = Path(options['output']).resolve()
        repository = Path(settings.BASE_DIR).resolve().parent
        readable = output.with_suffix('.md')
        if output.suffix != '.json' or readable.exists():
            raise CommandError('Choose a new .json output and an unused matching .md path.')
        if output == repository or repository in output.parents or output.exists():
            raise CommandError('Choose a new private output file outside the repository.')
        if not 100 <= options['budget'] <= 100000:
            raise CommandError('Budget must be between 100 and 100000 characters.')
        if not 0 <= options['expansion_budget'] <= 18000 or options['budget'] + options['expansion_budget'] > 100000:
            raise CommandError('Expansion must be 0–18000 characters and total budget at most 100000.')
        replay = None
        if options['replay_inputs']:
            if options['run_id'] or options['gold'] or options['holdout_gold']:
                raise CommandError('Replay uses embedded labels; omit run_id and gold options.')
            payload = json.loads(Path(options['replay_inputs']).read_text())
            replay = payload['replay_inputs']
            sources, rubric = replay['sources'], replay['rubric']
            if (not isinstance(sources, list) or not sources or any(not isinstance(s, dict)
                    or not isinstance(s.get('id'), str) or not isinstance(s.get('document_id'), str)
                    or not isinstance(s.get('text'), str) or type(s.get('page_number')) is not int
                    or s['page_number'] < 1 for s in sources)):
                raise CommandError('Replay source records are invalid.')
            if len({s['id'] for s in sources}) != len(sources):
                raise CommandError('Replay source IDs must be unique.')
            manifest = [{'document_id': did, 'filename': did} for did in sorted({s['document_id'] for s in sources})]
            run_id, inputs_hash = payload.get('run_id'), payload.get('inputs_hash')
        else:
            if not options['run_id'] or not options['gold']:
                raise CommandError('Provide run_id and --gold, or --replay-inputs.')
            run = CapabilityRun.objects.get(pk=options['run_id'])
            if digest(run.inputs) != run.inputs_hash:
                raise CommandError('Frozen input integrity mismatch.')
            sources, rubric, manifest = frozen_sources(run), run.inputs['rubric'], run.inputs['manifest']
            run_id, inputs_hash = str(run.pk), run.inputs_hash
        case_pack = cases = None
        if options['evidence_cases']:
            from apps.scoring.capability.evidence_cases import validate_cases
            case_pack = json.loads(Path(options['evidence_cases']).read_text())
            try:
                cases = validate_cases(case_pack, rubric, sources)
            except ValueError as exc:
                raise CommandError(str(exc)) from exc
        # Explicit offline candidate policy; the running application can remain BM25.
        model_started = perf_counter()
        policy = configured_policy(mode='hybrid')
        ranker = ranker_for(policy)
        ranker.baseline_chars = options['budget']  # explicit diagnostic override, never a live setting change
        model_load_seconds = round(perf_counter() - model_started, 4)
        conditions = {c['id'] for i in rubric['indicators'] for c in i['conditions']}
        names = {}
        for document in manifest:
            names.setdefault(document['filename'], set()).add(document['document_id'])
        def labels(rows):
            if not isinstance(rows, list) or not rows:
                raise CommandError('Gold must be a nonempty list.')
            result = []
            for n, row in enumerate(rows, 1):
                if (not isinstance(row, dict) or row.get('condition_id') not in conditions
                        or not isinstance(row.get('quote'), str) or not row['quote'].strip()):
                    raise CommandError(f'Invalid requirement/quotation in gold item {n}.')
                document = row.get('document_id') or row.get('document')
                if document in names:
                    if len(names[document]) != 1:
                        raise CommandError(f'Gold item {n} needs a document UUID; filename is ambiguous.')
                    document = next(iter(names[document]))
                try:
                    page = int(row['page'])
                    if page < 1:
                        raise ValueError()
                except (KeyError, ValueError, TypeError) as exc:
                    raise CommandError(f'Invalid page in gold item {n}.') from exc
                manifest_ids = {d['document_id'] for d in manifest}
                candidates = [s for s in sources if s['page_number'] == page]
                documents = {s['document_id'] for s in candidates}
                if document:
                    if document not in manifest_ids:
                        raise CommandError(f'Unknown document in gold item {n}.')
                    documents = {document}
                elif len(manifest_ids) == 1:
                    documents = manifest_ids
                if len(documents) != 1:
                    raise CommandError(f'Gold item {n} needs an unambiguous document identifier.')
                result.append({**row, 'document_id': next(iter(documents))})
            return result
        if replay is not None:
            if not isinstance(replay.get('gold_sets'), dict) or not replay['gold_sets']:
                raise CommandError('Replay needs nonempty labelled sets.')
            sets = {name: labels(rows) for name, rows in replay['gold_sets'].items()}
        else:
            sets = {'development': labels(json.loads(Path(options['gold']).read_text()))}
            if options['holdout_gold']:
                sets['holdout'] = labels(json.loads(Path(options['holdout_gold']).read_text()))
        seen = set()
        for gold in sets.values():
            identities = {(i['condition_id'], i['document_id'], int(i['page']), ' '.join(i['quote'].split())) for i in gold}
            if seen & identities:
                raise CommandError('Labelled sets must not overlap.')
            seen.update(identities)
        result = {'run_id': run_id, 'inputs_hash': inputs_hash, 'hybrid_policy': policy,
                  'no_model_evaluation': True, 'model_load_seconds': model_load_seconds, 'sets': {}}
        result['input_verification'] = 'replay_content_hash' if replay is not None else 'frozen_run_hash'
        if replay is not None:
            result['replay_content_hash'] = digest(replay)
        result['comparison_policy'] = {'baseline_chars': options['budget'], 'expansion_chars': options['expansion_budget']}
        if options['include_replay_inputs']:
            result['replay_inputs'] = {'sources': sources, 'rubric': rubric, 'gold_sets': sets}
        expanded = options['budget'] + options['expansion_budget']
        from apps.scoring.capability.evidence_retrieval import retrieve_evidence
        methods = {'bm25_1800': lambda i, s, max_chars: select_context(i, s, max_chars=max_chars),
                   'bm25_1200': lambda i, s, max_chars: select_context(i, s, max_chars=max_chars, window_chars=1200),
                   'profiled_bm25': lambda i, s, max_chars: retrieve_evidence(i, s, ranker, max_chars=max_chars, include_semantic=False),
                   'hybrid_passages': lambda i, s, max_chars: select_context(i, s, max_chars=max_chars, semantic_ranker=ranker),
                   'bm25_expanded': lambda i, s, max_chars: select_context(i, s, max_chars=expanded),
                   'protected_profiled_expanded': lambda i, s, max_chars: retrieve_evidence(i, s, ranker,
                       max_chars=expanded, include_semantic=False, protect_baseline=True),
                   'hybrid_expanded': lambda i, s, max_chars: select_context(i, s, max_chars=expanded, semantic_ranker=ranker)}
        if options['matched_routes']:
            methods.update({
                f'matched_{route}': lambda i, s, max_chars, route=route: retrieve_evidence(
                    i, s, ranker, max_chars=max_chars, comparison_route=route)
                for route in ('lexical', 'semantic', 'fused')
            })
        from apps.scoring.capability.retrieval_diagnostics import gold_traces, trace_summary, readable_report, labelled_packet_oracle
        result['gold_traces'] = {}
        result['trace_summary'] = {}
        result['labelled_packet_oracle'] = {}
        started = perf_counter()
        for split, gold in sets.items():
            result['sets'][split] = {}
            for name, selector in methods.items():
                method_started = perf_counter()
                measured = retrieval_recall(rubric, sources, gold, selector=selector, budget=options['budget'])
                measured['elapsed_seconds'] = round(perf_counter() - method_started, 4)
                measured['budget_chars'] = expanded if name.endswith('_expanded') else options['budget']
                result['sets'][split][name] = measured
            baseline = result['sets'][split]['bm25_1800']['items']
            for name, measured in result['sets'][split].items():
                measured['versus_bm25_1800'] = {
                    kind: [{'gold_item': n + 1, **row} for n, (old, row) in enumerate(zip(baseline, measured['items']))
                           if (row['retrieved'] and not old['retrieved'] if kind == 'gained' else old['retrieved'] and not row['retrieved'])]
                    for kind in ('gained', 'lost')}
                if name in {'hybrid_passages', 'hybrid_expanded', 'protected_profiled_expanded'} and measured['versus_bm25_1800']['lost']:
                    raise CommandError('Protected retrieval lost baseline evidence; do not enable this build.')
            result['gold_traces'][split] = gold_traces(rubric, sources, gold, ranker, expanded)
            result['trace_summary'][split] = trace_summary(result['gold_traces'][split])
            result['labelled_packet_oracle'][split] = labelled_packet_oracle(result['gold_traces'][split], expanded)
        result['aggregate_requirement_coverage'] = {}
        for name in methods:
            rows = [row for measured in result['sets'].values() for row in measured[name]['items']]
            result['aggregate_requirement_coverage'][name] = {
                'labelled_requirements': len({row['condition_id'] for row in rows}),
                'requirements_with_any_target_retrieved': len({row['condition_id'] for row in rows if row['retrieved']})}
        if cases is not None:
            from apps.scoring.capability.evidence_cases import packet_coverage
            result['evidence_case_review_status'] = case_pack.get('review_status', 'unspecified')
            result['evidence_case_pack_hash'] = digest(case_pack)
            result['evidence_case_coverage'] = {name: packet_coverage(cases, rubric, sources,
                selector=selector, budget=options['budget']) for name, selector in methods.items()}
        result['elapsed_seconds'] = round(perf_counter() - started, 3)
        result['embedding_cache'] = ranker.stats
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2), encoding='utf-8')
        readable.write_text(readable_report(result), encoding='utf-8')
        self.stdout.write('Wrote local retrieval ablation; no evaluation requests or database writes.')
