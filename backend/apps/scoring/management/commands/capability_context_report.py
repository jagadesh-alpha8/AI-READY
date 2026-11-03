"""Measure one saved assessment's request construction offline; no inference or database writes."""
import csv
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.scoring.capability import context_diagnostics as diag
from apps.scoring.capability import pipeline_diagnostics as stages

COMPONENTS = ('instructions', 'schema_in_instructions', 'response_schema', 'rubric_indicator', 'population_and_period',
              'scope', 'source_passages', 'current_quotations', 'original_quotations', 'passage_references',
              'review_history', 'claim_records', 'conflicts', 'other_issues', 'case_details', 'packet_instruction',
              'user_framing')


class Command(BaseCommand):
    help = 'Per-batch request-size diagnostics for a capability export; writes only to a new directory outside the repository.'
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument('export', help='Path to a capability assessment JSON export.')
        parser.add_argument('--output-dir', required=True, help='New directory for the report; must be outside the repository.')
        parser.add_argument('--database', action='store_true',
                            help="Also read this run's frozen page text, stored tables and AI-QIF tags from the configured "
                                 "database (read-only) to replay retrieval and diagnose each pipeline stage.")
        parser.add_argument('--gold', help='Private JSON list of person-labelled evidence: '
                                           '[{"condition_id", "page", "quote", "document"?, "note"?}]. Needs --database.')

    def handle(self, *args, **options):
        out = Path(options['output_dir']).resolve()
        repository = Path(settings.BASE_DIR).resolve().parent
        if out == repository or repository in out.parents:
            raise CommandError('Institutional diagnostics must be written outside the repository.')
        try:
            export = json.loads(Path(options['export']).read_text(encoding='utf-8'))
            gold = json.loads(Path(options['gold']).read_text(encoding='utf-8')) if options['gold'] else None
        except (OSError, ValueError) as exc:
            raise CommandError('Could not read the capability export or gold evidence file.') from exc
        if gold is not None and not options['database']:
            raise CommandError('--gold needs --database: matching labelled quotations requires the frozen page text.')
        sources = rendered = tags = None
        if options['database']:
            from apps.scoring.models import CapabilityRun
            run = CapabilityRun.objects.filter(pk=export['run_id']).first()
            if run is None or run.inputs_hash != export['inputs_hash']:
                raise CommandError('The database does not hold this run with matching frozen inputs.')
            sources = run.inputs['sources']
            rendered, tags, unchanged = self.current_state(run)
        analysis = diag.analyse(export, sources=sources)
        pipeline = {'interval': stages.interval_attribution(export)}
        if sources is not None:
            pipeline.update(
                current_state_note=f'Tables and tags read from the database now; {unchanged} of {len(sources)} '
                                   'pages still have the text frozen in this run.',
                ingestion=stages.ingestion_health(sources, rendered, export['source_manifest']),
                extraction=(extraction := stages.extraction_health(export['reviewed_evidence'], sources, rendered)),
                extraction_fidelity=stages.extraction_fidelity(extraction),
                retrieval=stages.retrieval_against_tags(export['rubric'], export['assessment']['traces'], tags, rendered=rendered),
                retrieval_sweep=stages.retrieval_sweep(export['rubric'], tags, sources, rendered=rendered),
                gold=stages.gold_funnel(export, sources, gold, rendered=rendered) if gold is not None else None)
        report = {
            'pipeline': pipeline,
            'analysis': analysis,
            'causes': diag.cause_summary(export, sources=sources),
            'scoring': diag.replay_scoring(export, sources=sources),
            # Advice batches select their own windows, which needs the frozen page text.
            'recommendations': diag.recommendation_requests(export['deterministic_plan'], sources, export['rubric'])
                               if sources is not None else None,
            'recommendation_in_export': export.get('recommendation') is not None,
            'traces': {kind: diag.trace_requirement(export, analysis, cid, sources=sources)
                       for kind, cid in diag.representative_requirements(export).items()},
        }
        try:
            out.mkdir(parents=True, exist_ok=False)
        except OSError as exc:
            raise CommandError('Choose a new output directory; existing reports are never overwritten.') from exc
        (out / 'diagnostics.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        rows = [self.row(b) for b in analysis['batches']]
        with (out / 'batches.csv').open('w', newline='', encoding='utf-8') as target:
            writer = csv.DictWriter(target, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        (out / 'batches.md').write_text(self.markdown(report), encoding='utf-8')
        (out / 'pipeline.md').write_text(self.pipeline_markdown(analysis['run_id'], pipeline), encoding='utf-8')
        self.stdout.write(f'Wrote offline diagnostics for {len(rows)} batches; no inference or database writes performed.')

    @staticmethod
    def current_state(run):
        """Canonical evidence text and AI-QIF tags for this run's documents, read now (not frozen with the run)."""
        from apps.extraction.models import DocumentPage
        from apps.facts.models import FactAIQIFMapping
        sources = run.inputs['sources']
        documents = {s['document_id'] for s in sources}
        pages = [{'id': str(p.pk), 'document_id': str(p.document_id), 'page_number': p.page_number, 'text': p.text,
                  'tables': p.tables} for p in DocumentPage.objects.filter(document_id__in=documents)]
        rendered = stages.rendered_sources(sources, pages)
        stored = {p['id']: p['text'] for p in pages}
        # Older runs froze stored text; newer runs freeze the canonical rendering.
        unchanged = sum(s['text'] in (stored.get(s['id']), r['text']) for s, r in zip(sources, rendered))
        tags = stages.tagged_pages([
            {'indicator_code': m.indicator_code, 'relationship': m.relationship, 'review_status': m.review_status,
             'document_id': str(m.fact.source_document_id or m.fact.document_id), 'page': m.fact.source_page}
            for m in FactAIQIFMapping.objects.filter(fact__sprint_id=run.sprint_id).select_related('fact')])
        return rendered, tags, unchanged

    @staticmethod
    def pipeline_markdown(run_id, pipeline):
        interval = pipeline['interval']
        lines = [f'# Where evidence is lost: run {run_id}', '',
                 '## Score interval', '',
                 f"Reported {interval['lower']}–{interval['upper']} (width {interval['width']} points). "
                 f"Upper falls below 100 only through not_met decisions: {interval['not_met_decisions']} here, "
                 f"costing {interval['upper_lost_to_not_met']} points. The width is the weight of unresolved requirements.", '',
                 '| Cause of unresolved requirement | Points of width |', '|---|---|']
        lines += [f'| {k} | {v} |' for k, v in interval['width_by_cause'].items()]
        lines += ['', 'By requirement level: ' + ', '.join(f'{k} {v}' for k, v in interval['width_by_level'].items()) + '.']
        if 'ingestion' not in pipeline:
            return '\n'.join(lines + ['', 'Stage checks need `--database`.']) + '\n'
        ing, ext, ret = pipeline['ingestion'], pipeline['extraction'], pipeline['retrieval']
        lines += ['', '## 1. Ingestion: text that reaches assessment', '', pipeline['current_state_note'], '',
                  f"- Pages: {ing['pages']}; with table placeholders: {ing['pages_with_table_placeholders']} "
                  f"({ing['table_placeholders']} tables); under 300 characters: {ing['pages_under_300_chars']}.",
                  f"- Characters assessed: {ing['assessed_chars']:,} of {ing['rendered_chars']:,} once tables are rendered "
                  f"({ing['share_of_text_missing']:.0%} missing).",
                  f"- Text sources: {ing['text_sources']}; manifest statuses: {ing.get('manifest_page_statuses')}.",
                  '', '## 2. Extraction: where claim quotations occur', '',
                  f"- {ext['claims']} claims: {ext['quotation_location']}.", f"- By kind: {ext['by_kind']}.",
                  f"- Stored grounding status: {ext['grounding_status']}.", f"- {ext['note']}",
                  f"- Fidelity gate (≥{pipeline['extraction_fidelity']['threshold']:.0%} of quotations in assessed text): "
                  f"{'PASS' if pipeline['extraction_fidelity']['passes'] else 'FAIL'} at {pipeline['extraction_fidelity']['rate']:.0%}; "
                  f"{pipeline['extraction_fidelity']['rate_with_tables']:.0%} once tables are rendered.",
                  '', '## 3. Retrieval against the extraction layer\'s own AI-QIF tags', '', ret['note'], '',
                  f"Tagged evidence pages selected: {ret['tagged_pages_selected']} of {ret['tagged_pages']}; "
                  f"with tables rendered back in: {ret['tagged_pages_selected_with_tables']}.", '',
                  '| Indicator | Tagged pages | Selected pages | Tagged selected | … with tables |', '|---|---|---|---|---|']
        lines += ['', 'Budget sweep (tagged pages reached; chance = selecting that share of text at random):', '',
                  '| Budget chars | Frozen text | Chance | With tables | Chance |', '|---|---|---|---|---|']
        for r in pipeline['retrieval_sweep']:
            f, t = r['frozen'], r.get('with_tables', {})
            lines.append(f"| {r['budget_chars']:,} | {f['tagged_pages_selected']} | {f['chance_expectation']} "
                         f"| {t.get('tagged_pages_selected')} | {t.get('chance_expectation')} |")
        lines += ['', '| Indicator | Tagged pages | Selected pages | Tagged selected | … with tables |', '|---|---|---|---|---|']
        lines += [f"| {r['indicator']} | {r['tagged_pages']} | {r['selected_pages']} | {r['tagged_pages_selected']} "
                  f"| {r.get('tagged_pages_selected_with_tables')} |" for r in ret['indicators']]
        gold = pipeline.get('gold')
        lines += ['', '## 4. Labelled evidence funnel', '']
        if gold is None:
            lines.append('No `--gold` file given. A short list of requirement → page → quotation you know to be evidence '
                         'turns this section into a per-item first-failure report.')
        else:
            lines += [f"First failure counts: {gold['first_failure_counts']}. "
                      f"Reached by retrieval once tables are rendered: {gold['retrieved_with_tables']}.", '',
                      '| Requirement or indicator | Page | First failing stage | Retrieval budget needed | Retrieved with tables | Note |',
                      '|---|---|---|---|---|---|']
            lines += [f"| {r['condition_id'] or r['indicator']} | {r['page']} | {r['stage']} | {r['retrieval_budget_needed'] or '—'} "
                      f"| {r['retrieved_with_tables']} | {r['note']} |" for r in gold['items']]
        return '\n'.join(lines) + '\n'

    @staticmethod
    def row(batch):
        tokens = batch['tokens']
        row = {'indicator': batch['indicator'], 'windows': batch['windows'], 'pages': batch['pages'],
               'claims': batch['claims'], 'anchored_claims': batch['anchoring']['anchored_claims'],
               'page_only_claims': batch['anchoring']['page_only_claims'], 'issues': batch['issues'],
               'conflicts': batch['conflicts'], 'review_cases': batch['review_cases'],
               'ledger_chars_as_gated': batch['ledger_chars_as_gated'], 'system_chars': batch['system_chars'],
               'user_chars': batch['user_chars'],
               'original_equals_current_quotes': batch['repetition']['original_quotation_equals_current'],
               'quotes_inside_windows': batch['repetition']['current_quotation_inside_supplied_window'],
               'repeated_quotes': batch['repetition']['repeated_quotations'],
               'duplicate_claim_records': batch['repetition']['duplicate_claim_records'],
               'actual_prompt_tokens': tokens['actual_prompt_tokens'], 'actual_completion_tokens': tokens['actual_completion_tokens'],
               'estimated_prompt_tokens': tokens['estimated_prompt_tokens'],
               'estimated_prompt_tokens_generic_4_chars': tokens['estimated_prompt_tokens_generic_4_chars'],
               'bound_input_tokens': tokens['bound_input_tokens'], 'bound_output_tokens': tokens['bound_output_tokens'],
               'provider_requests': len(batch['provider_requests']),
               'request_hashes_match': all(e.get('request_hash_matches') for e in batch['provider_requests']) if batch['provider_requests'] else '',
               'input_hash_matches': batch['input_hash_matches'], 'retrieval_replayed': batch['retrieval_replayed'],
               'model_call_attempted': batch['model_call_attempted'], 'pre_request_limit': batch['pre_request_limit'] or '',
               'decisions': ' '.join(f'{k}={v}' for k, v in sorted(batch['decisions'].items())),
               'causes': ' '.join(f'{k}={v}' for k, v in sorted(batch['causes'].items())),
               'prompt_version': batch['prompt_version'], 'prompt_reproduced': batch['prompt_reproduced']}
        row.update({f'chars_{k}': batch['components'][k] for k in COMPONENTS})
        today = batch['current_construction']
        row.update({'current_ledger_chars_as_gated': today['ledger_chars_as_gated'],
                    'current_pre_request_limit': today['pre_request_limit'] or '', 'current_claims': today['claims'],
                    'current_unsupported_conflict_alternatives': today['anchoring']['unsupported_conflict_alternatives'],
                    'current_user_chars': today['user_chars']})
        return row

    @staticmethod
    def markdown(report):
        analysis = report['analysis']
        cal = analysis['calibration'] or {}
        lines = [f"# Capability request diagnostics: run {analysis['run_id']}", '',
                 'Token columns: **actual** = provider usage telemetry; **est.** = system+user bytes / '
                 f"{cal.get('bytes_per_token')} bytes per token ({cal.get('basis', 'no calibration samples')}); "
                 '**bound** = the application reservation envelope (UTF-8 request bytes + 4096). '
                 'Blocked batches show the estimate and bound of the request they would have sent.', '',
                 '| Batch | Win/pages | Claims (anchored / page-only) | Issues (conflicts) | Cases | Ledger chars (gate 32,000) | System + user chars | Actual prompt tok | Est. tok | Bound in tok | Orig = current quotes | Quotes in windows | Limit / attempted | Decisions |',
                 '|---|---|---|---|---|---|---|---|---|---|---|---|---|---|']
        for b in analysis['batches']:
            t = b['tokens']
            lines.append(f"| {b['indicator']} | {b['windows']}/{b['pages']} | {b['claims']} ({b['anchoring']['anchored_claims']} / {b['anchoring']['page_only_claims']}) "
                         f"| {b['issues']} ({b['conflicts']}) | {b['review_cases']} | {b['ledger_chars_as_gated']:,} | {b['system_chars'] + b['user_chars']:,} "
                         f"| {t['actual_prompt_tokens'] or '—'} | {t['estimated_prompt_tokens']} | {t['bound_input_tokens'] or '—'} "
                         f"| {b['repetition']['original_quotation_equals_current']} | {b['repetition']['current_quotation_inside_supplied_window']} "
                         f"| {b['pre_request_limit'] or 'none'} / {'yes' if b['model_call_attempted'] else 'no'} "
                         f"| {', '.join(f'{k} {v}' for k, v in sorted(b['decisions'].items()))} |")
        lines += ['', '## Characters by request part (as the run was built)', '', '| Batch | ' + ' | '.join(COMPONENTS) + ' |',
                  '|---|' + '---|' * len(COMPONENTS)]
        for b in analysis['batches']:
            lines.append(f"| {b['indicator']} | " + ' | '.join(f"{b['components'][k]:,}" for k in COMPONENTS) + ' |')
        lines += ['', '## Same saved windows, current construction', '',
                  'What the code on this branch would send for each batch, with retrieval and windows unchanged.', '',
                  '| Batch | Ledger chars then → now | Claims then → now | Unsupported claims now (conflict alternatives / other) | User chars then → now | Limit then → now |',
                  '|---|---|---|---|---|---|']
        for b in analysis['batches']:
            t = b['current_construction']
            lines.append(f"| {b['indicator']} | {b['ledger_chars_as_gated']:,} → {t['ledger_chars_as_gated']:,} | {b['claims']} → {t['claims']} "
                         f"| {t['anchoring']['unsupported_conflict_alternatives']} / {t['anchoring']['unsupported_unconnected_claims']} "
                         f"| {b['user_chars']:,} → {t['user_chars']:,} | {b['pre_request_limit'] or 'none'} → {t['pre_request_limit'] or 'none'} |")
        rec = report['recommendations']
        if rec is None:
            lines += ['', '## Recommendation requests', '', 'Not rebuilt: needs the frozen page text (`--database`).']
        else:
            lines += ['', '## Recommendation requests (rebuilt with current construction; not sent)', '',
                      f"Model actions: {rec['model_actions']}; deterministic-only actions: {rec['deterministic_actions']}; strengths supplied: {rec['strengths_supplied']}. "
                      f"Tailored recommendation in export: {report['recommendation_in_export']}.", '',
                      '| Batch | Actions (unknown) | Windows | User chars | Ledger chars / claims | Unsupported (conflict alt. / other) | Previous whole-ledger chars / claims |',
                      '|---|---|---|---|---|---|---|']
            for r in rec['batches']:
                lines.append(f"| {r['indicator']} | {r['actions']} ({r['unknown_actions']}) | {r['source_windows']} | {r['user_chars']:,} "
                             f"| {r['ledger_chars']:,} / {r['ledger_claims']} | {r['unsupported_conflict_alternatives']} / {r['unsupported_unconnected_claims']} "
                             f"| {r['page_projection_ledger_chars']:,} / {r['page_projection_ledger_claims']} |")
        c = report['causes']
        lines += ['', '## Why requirements are unknown', '',
                  'First stage that explains each saved decision. `scope_or_period_heuristic` is a keyword reading of the model reason; '
                  'the retrieval signal is lexical term coverage of unselected pages, not a recall measurement.', '']
        lines += [f'- {k}: {v}' for k, v in sorted(c['causes'].items())]
        lines += [f"- Retrieval signal for model unknowns: {c['retrieval_signal_for_model_unknowns']}",
                  f"- Validation issues repaired by a correction request: {c['validation_issues_repaired_by_correction']}"]
        s = report['scoring']
        lines += ['', '## Scoring replay', '', f"Engine replay matches saved result: {s['matches_saved_result']} "
                  f"(bounds {s['lower']}–{s['upper']}; saved {s['saved_lower']}–{s['saved_upper']}). "
                  f"Publication revalidation matches saved records: {s['revalidation_matches_saved_records']}.", '']
        return '\n'.join(lines) + '\n'
