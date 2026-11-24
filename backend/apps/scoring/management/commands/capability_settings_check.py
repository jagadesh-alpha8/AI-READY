"""Compare what this deployment would score with against what a run was scored with. No model calls.

    python manage.py capability_settings_check RUN_ID          # differences, then exit 1 if any affect scoring
    python manage.py capability_settings_check RUN_ID --json

A rerun is only comparable with RUN_ID (assessment_consistency --compare) when everything that decides a score is
the same: the model, the execution policy (reasoning effort, agreement passes, tie-break, part rule, prompt, schema,
output tokens, input bound), the retrieval policy (mode, embedding model and artifact, allocation, routing), the
assessment protocol, the engine and the rubric. The run froze all of these when it was created
(storage.create_run); this command rebuilds them from the current settings the same way and lists what differs,
with the setting that decides each value. The run's frozen values are the record of what it ran with: a .env file
may have changed since.

Differences are split into:
- scoring: changes what a run would find or credit. Any of these means a new run is not a like-for-like rerun.
- credit rule: the part rule (parts version, hash, related credit). Expected when the rule changed on purpose since
  the run (f5919156 was scored at related credit 0.5): compare with an export rescored under today's rule instead.
- limits only: budgets and timeouts (calls, cost, duration, timeout, concurrency). They stop a run; they don't change
  a judgment, unless they cut it short.

Not frozen with the run, so shown for a person to check: FACT_VERIFICATION_MODE (shadow auto-confirms no facts, so
newly extracted facts reach the judge unconfirmed and all wait for review), AI_TEMPERATURE and AI_SEED.
"""
import hashlib
import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.scoring.models import CapabilityRun

LIMIT_KEYS = {'max_http_calls', 'max_cost_usd', 'max_duration_seconds', 'timeout_seconds', 'indicator_concurrency',
              'cost_policy'}
RULE_KEYS = {'parts_version', 'parts_hash', 'parts_prompt_hash', 'related_credit', 'credit_rule'}
MISSING = '(not set)'
#: The setting that decides each frozen value, so a difference says what to change. Output tokens and the timeout are
#: raised automatically at high reasoning effort when their stage-specific settings are unset (execution.policy).
SETTING = {
    ('depth_policy', 'mode'): 'DEPTH_CREDIT_MODE', ('depth_policy', 'share'): 'DEPTH_CREDIT_SHARE',
    ('execution_policy', 'agreement_passes'): 'CAPABILITY_AGREEMENT_PASSES',
    ('execution_policy', 'gemini_reasoning_effort'): 'CAPABILITY_GEMINI_REASONING_EFFORT (else AI_GEMINI_REASONING_EFFORT)',
    ('execution_policy', 'tie_break'): 'CAPABILITY_TIE_BREAK',
    ('execution_policy', 'part_quote_repair'): 'CAPABILITY_PART_QUOTE_REPAIR',
    ('retrieval_policy', 'evidence_lane'): 'CAPABILITY_EVIDENCE_LANE',
    ('execution_policy', 'judgment'): 'CAPABILITY_JUDGMENT',
    ('execution_policy', 'input_token_bound_limit'): 'CAPABILITY_MAX_INPUT_TOKEN_BOUND',
    ('execution_policy', 'output_tokens'): 'CAPABILITY_ASSESSMENT_OUTPUT_TOKENS (else CAPABILITY_OUTPUT_TOKENS)',
    ('execution_policy', 'timeout_seconds'): 'CAPABILITY_ASSESSMENT_TIMEOUT_SECONDS (else CAPABILITY_REQUEST_TIMEOUT_SECONDS)',
    ('execution_policy', 'max_http_calls'): 'CAPABILITY_MAX_HTTP_CALLS',
    ('execution_policy', 'max_cost_usd'): 'CAPABILITY_MAX_COST_USD',
    ('execution_policy', 'max_duration_seconds'): 'CAPABILITY_MAX_DURATION_SECONDS',
    ('execution_policy', 'indicator_concurrency'): 'CAPABILITY_INDICATOR_CONCURRENCY',
    ('retrieval_policy', 'mode'): 'CAPABILITY_RETRIEVAL_MODE',
    ('retrieval_policy', 'model'): 'CAPABILITY_EMBEDDING_MODEL',
    ('retrieval_policy', 'artifact_hash'): 'CAPABILITY_EMBEDDING_PATH (the embedding model files)',
    ('retrieval_policy', 'allocation'): 'CAPABILITY_RETRIEVAL_ALLOCATION',
    ('retrieval_policy', 'keyword_chars'): 'CAPABILITY_KEYWORD_CHARS (keyword mode; missing means the default 18,000)',
    ('retrieval_policy', 'deduplicate'): 'CAPABILITY_DEDUPLICATE_PAGES',
    ('retrieval_policy', 'structure'): 'CAPABILITY_STRUCTURE_ROUTING',
    ('retrieval_policy', 'repeat_skip'): 'CAPABILITY_REPEAT_SKIP',
    ('retrieval_policy', 'follow_up'): 'CAPABILITY_FOLLOW_UP_SEARCH',
    ('model', 'AI_MODEL'): 'AI_MODEL',
    ('execution_policy', 'model_effort'): 'CAPABILITY_AI_EFFORT',
    ('execution_policy', 'writing_effort'): 'CAPABILITY_AI_WRITING_EFFORT',
    ('retrieval_policy', 'prompt_ceiling'): 'CAPABILITY_PROMPT_TOKEN_CEILING (and CAPABILITY_PROMPT_BYTES_PER_TOKEN)',
    ('retrieval_policy', 'cap_chars'): 'CAPABILITY_MAP_CAP_CHARS (map mode)',
    ('retrieval_policy', 'map_shape'): 'EVIDENCE_MAP_SHAPE (map mode)',
}
#: Recorded from the sprint when a run starts (its evidence map and how much of it was tagged), not set by a setting.
PER_SPRINT = {('retrieval_policy', key) for key in ('map_version', 'map_model', 'map_coverage', 'map_fallback')}


def _current_execution():
    from apps.scoring.capability.execution import policy
    return policy('assessment')


def _current_retrieval():
    from apps.scoring.capability.semantic_retrieval import configured_policy
    return configured_policy()


def _current_protocol():
    from apps.scoring.capability.evaluation import DECISION_SCHEMA, PROMPT_VERSION, RETRIEVAL_VERSION, SYSTEM_PROMPT
    return {'prompt_version': PROMPT_VERSION, 'retrieval_version': RETRIEVAL_VERSION,
            'prompt_hash': hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest(),
            'schema_hash': hashlib.sha256(json.dumps(DECISION_SCHEMA, sort_keys=True).encode()).hexdigest()}


def _current_depth():
    from apps.scoring.capability.reserve import frozen_policy
    return frozen_policy()


def _kind(section, key):
    if section == 'depth_policy':
        return 'credit rule'   # how much credit is held for follow-up answers; the judging is unchanged
    if section == 'execution_policy' and key in LIMIT_KEYS:
        return 'limits only'
    if section == 'execution_policy' and key in RULE_KEYS:
        return 'credit rule'
    return 'scoring'


def _same_file(key, recorded):
    """A specification hash recorded from a checkout with other line endings is the same file."""
    if key == 'parts_hash':
        from apps.scoring.capability.part_judgment import parts_hash_matches
        return parts_hash_matches(recorded)
    if key == 'query_profiles_hash':
        from apps.scoring.capability.query_profiles import profiles_hash_matches
        return profiles_hash_matches(recorded)
    return False


def _compare(section, frozen, current):
    rows = []
    for key in sorted(set(frozen) | set(current)):
        if (section, key) in PER_SPRINT:
            continue
        before, after = frozen.get(key, MISSING), current.get(key, MISSING)
        if before != after and not _same_file(key, before):
            rows.append({'section': section, 'setting': key, 'run': before, 'now': after, 'kind': _kind(section, key),
                         'set_with': SETTING.get((section, key), 'code version (not a setting)')})
    return rows


def run_model(run):
    """(provider, model) the run's assessment was scored with, from its completed event."""
    event = run.events.filter(state='completed', payload__result__isnull=False).last()
    inference = ((event.payload or {}).get('inference') or {}) if event else {}
    model = inference.get('model') or next((c.get('configured_model') for c in inference.get('calls') or []
                                            if c.get('configured_model')), None)
    return inference.get('provider'), model


def check(run):
    """{'differences': [...], 'errors': [...], 'unfrozen': {...}} for a run against this deployment."""
    inputs = run.inputs or {}
    differences, errors = [], []
    _, model = run_model(run)
    from apps.scoring.capability.model_choice import scoring_model, switched_on
    current, model_setting = scoring_model(), ('CAPABILITY_AI_MODEL' if switched_on() else 'AI_MODEL')
    if model and model != current:
        differences.append({'section': 'model', 'setting': model_setting, 'run': model, 'now': current or MISSING,
                            'kind': 'scoring', 'set_with': model_setting})
    elif not model:
        errors.append('The run records no model (no completed assessment, or an export from before models were '
                      'recorded): check the scoring model (AI_MODEL, or CAPABILITY_AI_MODEL when switched on) by hand.')
    for section, build in (('execution_policy', _current_execution), ('retrieval_policy', _current_retrieval),
                           ('assessment_protocol', _current_protocol), ('depth_policy', _current_depth)):
        try:
            current = build()
        except Exception as exc:   # an invalid budget, or hybrid retrieval with its model missing
            errors.append(f'{section}: this deployment cannot build it: {getattr(exc, "detail", exc)}')
            continue
        differences += _compare(section, inputs.get(section) or {}, current)
    from apps.scoring.capability.engine import ENGINE_VERSION, release
    from apps.scoring.capability.storage import digest
    if inputs.get('engine_version') != ENGINE_VERSION:
        differences.append({'section': 'engine', 'setting': 'engine_version', 'run': inputs.get('engine_version'),
                            'now': ENGINE_VERSION, 'kind': 'scoring', 'set_with': 'code version (not a setting)'})
    if inputs.get('rubric_snapshot_hash') != digest(release()):
        differences.append({'section': 'rubric', 'setting': 'rubric_snapshot_hash',
                            'run': inputs.get('rubric_snapshot_hash'), 'now': digest(release()), 'kind': 'scoring',
                            'set_with': 'code version (not a setting)'})
    unfrozen = {'FACT_VERIFICATION_MODE': settings.FACT_VERIFICATION_MODE, 'AI_TEMPERATURE': settings.AI_TEMPERATURE,
                'AI_SEED': settings.AI_SEED}
    return {'run_id': str(run.pk), 'differences': differences, 'errors': errors, 'unfrozen': unfrozen}


class Command(BaseCommand):
    help = 'List what differs between the settings a run was scored with and this deployment (no model calls).'

    def add_arguments(self, parser):
        parser.add_argument('run_id')
        parser.add_argument('--json', action='store_true')

    def handle(self, *args, **options):
        run = CapabilityRun.objects.filter(pk=options['run_id']).first()
        if run is None:
            raise CommandError('Run not found.')
        result = check(run)
        scoring = [d for d in result['differences'] if d['kind'] == 'scoring']
        if options['json']:
            self.stdout.write(json.dumps(result, indent=2, default=str))
        else:
            self.stdout.write(f"Run {result['run_id']} against this deployment:")
            for kind in ('scoring', 'credit rule', 'limits only'):
                rows = [d for d in result['differences'] if d['kind'] == kind]
                self.stdout.write(f'\n{kind.capitalize()}: ' + ('none' if not rows else f'{len(rows)} different'))
                for d in rows:
                    self.stdout.write(f"  {d['section']}.{d['setting']}: run {d['run']!r}, now {d['now']!r}"
                                      f"  [{d['set_with']}]")
            for error in result['errors']:
                self.stdout.write(self.style.WARNING(f'\nCould not check: {error}'))
            self.stdout.write('\nNot frozen with the run (check by hand): ' + ', '.join(
                f'{k}={v!r}' for k, v in result['unfrozen'].items()))
            if result['unfrozen']['FACT_VERIFICATION_MODE'] != 'enforce':
                self.stdout.write(self.style.WARNING(
                    '  FACT_VERIFICATION_MODE is not enforce: newly extracted facts are not auto-confirmed.'))
        if scoring or result['errors']:
            raise SystemExit(1)
