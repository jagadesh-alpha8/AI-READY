"""Matched local reranker arms on a private frozen replay corpus."""
import json
from pathlib import Path
from time import perf_counter
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Offline BM25 baseline vs lexical/combined candidates with one local reranker; never changes live retrieval.'

    def add_arguments(self, parser):
        parser.add_argument('--replay-inputs', required=True)
        parser.add_argument('--evidence-cases', required=True)
        parser.add_argument('--reranker-path', required=True)
        parser.add_argument('--output', required=True)
        parser.add_argument('--budget', type=int, default=18000)
        parser.add_argument('--depth', type=int, default=60)
        parser.add_argument('--max-pairs', type=int, default=30000)
        parser.add_argument('--max-seconds', type=int, default=1200)

    def handle(self, *args, **options):
        from apps.scoring.capability.evaluation import select_context, _normal
        from apps.scoring.capability.evidence_cases import validate_cases, packet_coverage
        from apps.scoring.capability.pipeline_diagnostics import retrieval_recall
        from apps.scoring.capability.semantic_retrieval import configured_policy, ranker_for, artifact_hash
        from apps.scoring.capability.selection_experiment import compare_pools, candidate_pools
        from apps.scoring.capability.storage import digest
        output = Path(options['output']).resolve()
        repo = Path(settings.BASE_DIR).resolve().parent
        if output.exists() or output == repo or repo in output.parents:
            raise CommandError('Choose a new private output outside the repository.')
        if not (100 <= options['budget'] <= 100000 and 1 <= options['depth'] <= 100
                and 1 <= options['max_pairs'] <= 100000 and 1 <= options['max_seconds'] <= 3600):
            raise CommandError('Invalid packet, candidate, pair or time bound.')
        replay = json.loads(Path(options['replay_inputs']).read_text())['replay_inputs']
        sources, rubric = replay['sources'], replay['rubric']
        pack = json.loads(Path(options['evidence_cases']).read_text())
        cases = validate_cases(pack, rubric, sources)
        labelled = {c['condition_id'] for c in cases}
        # Full indicator conditions participate in packing, including unlabelled companions.
        indicators = [i for i in rubric['indicators'] if any(c['id'] in labelled for c in i['conditions'])]
        ranker = ranker_for(configured_policy(mode='hybrid'))
        from fastembed.rerank.cross_encoder import TextCrossEncoder
        from tokenizers import Tokenizer
        model_name = 'Xenova/ms-marco-MiniLM-L-6-v2'
        reranker = TextCrossEncoder(model_name=model_name, specific_model_path=options['reranker_path'],
            local_files_only=True, threads=4, providers=['CPUExecutionProvider'])
        tokenizer = Tokenizer.from_str(reranker.model.tokenizer.to_str())
        tokenizer.no_truncation(); tokenizer.no_padding()
        started, pairs, longest = perf_counter(), 0, 0
        def score(query, texts):
            nonlocal pairs, longest
            if perf_counter() - started > options['max_seconds'] or pairs + len(texts) > options['max_pairs']:
                raise CommandError('Offline time/pair allowance reached; no production setting changed.')
            pair_tokens = max((len(tokenizer.encode(query, text).ids) for text in texts), default=0)
            longest = max(longest, pair_tokens)
            if pair_tokens > 512:
                raise CommandError('Reranker input would truncate; no scores accepted.')
            pairs += len(texts)
            return list(reranker.rerank(query, texts, batch_size=16))
        packets = {name:{} for name in ('bm25', 'lexical_reranked', 'combined_reranked')}
        experiments = {}
        for indicator in indicators:
            trace = {}
            select_context(indicator, sources, semantic_ranker=ranker, diagnostics=trace)
            expected_pairs = len(candidate_pools(trace, options['depth'])['combined']) * len(trace['requirements'])
            if pairs + expected_pairs > options['max_pairs']:
                raise CommandError('Total pair allowance would be exceeded.')
            exp = compare_pools(trace, score, budget=options['budget'], depth=options['depth'], max_pairs=options['max_pairs']-pairs)
            code = indicator['code']
            experiments[code] = exp
            packets['bm25'][code] = select_context(indicator, sources, max_chars=options['budget'])
            for arm in ('lexical','combined'):
                packets[arm+'_reranked'][code] = exp['arms'][arm]['sources']
            self.stdout.write(f"Completed {code}: {exp['actual_scored_pairs']} shared pairs.")
            self.stdout.flush()
        gold = [g for rows in replay['gold_sets'].values() for g in rows]
        measured = {}
        for name, by_code in packets.items():
            selector = lambda indicator, sources, **kwargs: by_code[indicator['code']]
            measured[name] = {'quotation_targets':retrieval_recall(rubric, sources, gold, selector=selector),
                'support_bundles':packet_coverage(cases, rubric, sources, selector=selector, budget=options['budget'])}
        contribution = []
        mapping = {c['id']:i['code'] for i in indicators for c in i['conditions']}
        for n,g in enumerate(gold):
            code = mapping[g['condition_id']]
            def found(name):
                return any(s['document_id']==g['document_id'] and s['page_number']==g['page']
                    and _normal(g['quote']) in _normal(s['text']) for s in packets[name][code])
            hits = {name:found(name) for name in packets}
            contribution.append({'target':n, 'condition_id':g['condition_id'], 'page':g['page'], **hits,
                'combined_gain_over_lexical_reranked':hits['combined_reranked'] and not hits['lexical_reranked'],
                'combined_loss_vs_lexical_reranked':hits['lexical_reranked'] and not hits['combined_reranked']})
        result = {'version':'matched-selection-experiment-1', 'no_provider_calls':True,
            'source_corpus_hash':digest(sources), 'rubric_hash':digest(rubric), 'case_pack_hash':digest(pack),
            'reranker':{'model':model_name, 'artifact_hash':artifact_hash(options['reranker_path']), 'max_pair_tokens':longest},
            'budget':options['budget'], 'depth':options['depth'], 'scored_pairs':pairs,
            'elapsed_seconds':perf_counter()-started, 'measurements':measured, 'target_contributions':contribution,
            'experiments':experiments,
            'limitations':['Inspected cases are regression evidence, not independent ground truth.',
                'Lexical arm uses profiled lexical candidates on the same token-aware passages as the combined arm; plain corrected BM25 remains a separate baseline.',
                'All companion conditions are reranked and packed; labels do not select candidates or order.',
                'Shared inference latency is not a separately timed lexical-only run. No model decisions are tested.']}
        with output.open('x') as handle:
            json.dump(result, handle, indent=2)
        self.stdout.write(f'Private experiment written; {pairs} pairs, no evaluator requests.')
