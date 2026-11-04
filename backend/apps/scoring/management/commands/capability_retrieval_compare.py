"""Offline ablation on a frozen corpus; neither evaluation nor database writes."""
import json
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Compare BM25 and local hybrid retrieval against private gold evidence at the same character budget.'

    def add_arguments(self, parser):
        parser.add_argument('run_id')
        parser.add_argument('--gold', required=True)
        parser.add_argument('--holdout-gold', help='Separate held-out labels; never used to fit retrieval.')
        parser.add_argument('--output', required=True, help='A new private JSON file outside the repository.')
        parser.add_argument('--budget', type=int, default=18000)

    def handle(self, *args, **options):
        from apps.scoring.models import CapabilityRun
        from apps.scoring.capability.evaluation import select_context
        from apps.scoring.capability.pipeline_diagnostics import retrieval_recall
        from apps.scoring.capability.semantic_retrieval import configured_policy, ranker_for
        from apps.scoring.capability.storage import digest
        output = Path(options['output']).resolve()
        repository = Path(settings.BASE_DIR).resolve().parent
        if output == repository or repository in output.parents or output.exists():
            raise CommandError('Choose a new private output file outside the repository.')
        if not 100 <= options['budget'] <= 100000:
            raise CommandError('Budget must be between 100 and 100000 characters.')
        run = CapabilityRun.objects.get(pk=options['run_id'])
        if digest(run.inputs) != run.inputs_hash:
            raise CommandError('Frozen input integrity mismatch.')
        # Explicit offline candidate policy; the running application can remain BM25.
        policy = configured_policy(mode='hybrid')
        ranker = ranker_for(policy)
        sources, rubric = run.inputs['sources'], run.inputs['rubric']
        conditions = {c['id'] for i in rubric['indicators'] for c in i['conditions']}
        names = {}
        for document in run.inputs['manifest']:
            names.setdefault(document['filename'], set()).add(document['document_id'])
        def labels(path):
            rows = json.loads(Path(path).read_text())
            if not isinstance(rows, list) or not rows:
                raise CommandError('Gold must be a nonempty list.')
            result = []
            for n, row in enumerate(rows, 1):
                if row.get('condition_id') not in conditions or not str(row.get('quote', '')).strip():
                    raise CommandError(f'Invalid requirement/quotation in gold item {n}.')
                document = row.get('document_id') or row.get('document')
                if document in names:
                    if len(names[document]) != 1:
                        raise CommandError(f'Gold item {n} needs a document UUID; filename is ambiguous.')
                    document = next(iter(names[document]))
                try:
                    candidates = [s for s in sources if s['page_number'] == int(row['page'])
                                  and (not document or s['document_id'] == document)]
                except (KeyError, ValueError) as exc:
                    raise CommandError(f'Invalid page in gold item {n}.') from exc
                documents = {s['document_id'] for s in candidates}
                if len(documents) != 1:
                    raise CommandError(f'Gold item {n} needs an unambiguous document identifier.')
                quote = ' '.join(row['quote'].split())
                if not any(quote in ' '.join(s['text'].split()) for s in candidates):
                    raise CommandError(f'Gold item {n} does not match its frozen page. Use a fresh table-inclusive run.')
                result.append({**row, 'document_id': next(iter(documents))})
            return result
        sets = {'development': labels(options['gold'])}
        if options['holdout_gold']:
            sets['holdout'] = labels(options['holdout_gold'])
            identity = lambda item: (item['condition_id'], item['document_id'], int(item['page']), ' '.join(item['quote'].split()))
            if {identity(i) for i in sets['development']} & {identity(i) for i in sets['holdout']}:
                raise CommandError('Development and holdout labels must not overlap.')
        result = {'run_id': str(run.pk), 'inputs_hash': run.inputs_hash, 'hybrid_policy': policy,
                  'no_model_evaluation': True, 'sets': {}}
        methods = {'bm25_1800': lambda i, s, max_chars: select_context(i, s, max_chars=max_chars),
                   'bm25_1200': lambda i, s, max_chars: select_context(i, s, max_chars=max_chars, window_chars=1200),
                   'hybrid_1200': lambda i, s, max_chars: select_context(i, s, max_chars=max_chars, semantic_ranker=ranker)}
        from apps.scoring.capability.retrieval_diagnostics import gold_traces
        result['gold_traces'] = {}
        for split, gold in sets.items():
            result['sets'][split] = {name: retrieval_recall(rubric, sources, gold, selector=selector, budget=options['budget'])
                                    for name, selector in methods.items()}
            result['gold_traces'][split] = gold_traces(rubric, sources, gold, ranker, options['budget'])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2))
        self.stdout.write('Wrote local retrieval ablation; no evaluation requests or database writes.')
