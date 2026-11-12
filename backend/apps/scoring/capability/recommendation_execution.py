"""Independent bounded advice execution. Never writes assessment events."""
import json
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.extraction.exceptions import ProviderQuotaExhausted, AIResponseError, RecoverableExtractionError
from apps.extraction.services.ai_service import get_ai_service
from apps.extraction.services.router_pool import get_router_pool, use_lease
from apps.extraction.usage import usage_scope
from apps.scoring.models import CapabilityRun, RecommendationSnapshot, RecommendationExecution, RecommendationEvent
from .execution import policy, AssessmentConflict, AssessmentDisabled, BudgetExceeded, ExecutionDeadlineExceeded, InputBudgetExceeded, ExecutionStopped
from .provider import MeteredService, UnpricedModel, UsageUnavailable
from .recommendations import build_inputs, validate_advice, partition_advice, advice_schema, processing_failure, VERSION, PROMPT, SCHEMA
from .storage import digest


def deterministic_advice(action, inputs, origin, note=''):
    """Advice that needs no model: evidence requests, re-assessment of unevaluated requirements, and the
    labelled fallback for a batch whose model answer failed validation."""
    requirement = action['requirement']
    if origin == 'processing_rerun':
        steps = [f'Re-assess "{requirement}": it was not evaluated ({action["reason"]}). '
                 'This is a processing result, not a finding about the institution.']
    elif action['type'] == 'develop_capability':
        steps = [action['suggestion']]
    elif action['type'] == 'resolve_contradiction':
        steps = [f'Reconcile the conflicting sources for "{requirement}" before choosing an intervention.']
    elif action.get('cause') == 'scope_or_period_unsupported':
        # The passages appeared relevant but did not establish who was covered or when.
        steps = [f'Supply a record for "{requirement}" that states the population or programme it covers '
                 'and the dated period of the activity. The assessed passages did not establish both.']
    elif action.get('cause') == 'review_guard':
        steps = [f'The cited passage for "{requirement}" is tied to a rejected, corrected or disputed review item. '
                 'Resolve that review item or supply independent evidence.']
    else:
        steps = [f"Request evidence for {requirement} covering {inputs['population']} in {inputs['reference_period']}."]
    row = {'condition_id': action['id'], 'operation': action['operation'], 'steps': steps,
           'suggested_role': 'Evidence coordinator (suggested)', 'effort': 'unknown', 'dependencies': [],
           'completion_evidence': action['completion_evidence'], 'basis': action['citations'], 'origin': origin}
    return {**row, 'fallback_reason': note} if note else row


def tailor_batch(service, payload, inputs):
    """Keep valid neighbours; reserve at most one metered corrective call per batch."""
    actions, sources, strengths = payload['actions'], payload['sources'], payload['established_strengths']
    from .request_recovery import request_with_split, failure_code
    def payload_for(group):
        return {**payload, 'actions': group, 'allowed_dependency_ids': [a['id'] for a in actions]}
    try:
        response, response_recovery, provider_errors = request_with_split(service=service, items=actions,
            identity=lambda action: action['id'], payload_for=payload_for,
            schema_for=lambda group: advice_schema(group, sources, strengths, dependency_actions=actions),
            rows_for=lambda response: response.get('advice', []) if isinstance(response, dict) and isinstance(response.get('advice'), list) else [],
            prompt=PROMPT, name='capability_advice', result_key='advice')
    except ProviderQuotaExhausted:
        raise
    except RecoverableExtractionError as exc:
        reason = 'Recommendation provider request failed: ' + failure_code(exc)
        return ([deterministic_advice(a, inputs, 'deterministic_fallback', reason) for a in actions],
                {'initial_invalid': {}, 'repair_attempted': False, 'repaired_ids': [],
                 'final_fallback_ids': [a['id'] for a in actions], 'provider_failure': failure_code(exc)})
    except AIResponseError:
        response, response_recovery, provider_errors = None, {}, {}
    valid, errors = partition_advice(response, actions, strengths, sources)
    errors.update(provider_errors)
    initially_invalid = dict(errors)
    initially_valid = set(valid)
    repair_attempted = False
    repair_failure = None
    if errors and not response_recovery.get('split_attempted') and not provider_errors:
        failed_actions = [a for a in actions if a['id'] in errors]
        repair = {**payload, 'actions': failed_actions, 'validation_errors': errors,
                  'allowed_dependency_ids': [a['id'] for a in actions],
                  'instruction': 'Return corrected advice only for the supplied actions. Preserve allowed operations and exact citations.'}
        repair_attempted = True
        try:
            corrected = service.extract_structured_data(system_prompt=PROMPT, user_content=json.dumps(repair, sort_keys=True),
                response_schema=advice_schema(failed_actions, sources, strengths, dependency_actions=actions),
                schema_name='capability_advice_repair')
        except ProviderQuotaExhausted:
            raise
        except ExecutionDeadlineExceeded:
            raise
        except (BudgetExceeded, AIResponseError, RecoverableExtractionError, InputBudgetExceeded) as exc:
            repair_failure = failure_code(exc) if not isinstance(exc, BudgetExceeded) else 'request_budget_exceeded'
            corrected = None  # A corrective call must never exceed the frozen request/cost cap.
        # Retained rows are trusted only after the same checks as the initial response.
        repaired_rows = corrected.get('advice', []) if isinstance(corrected, dict) else []
        if not isinstance(repaired_rows, list):
            repaired_rows = []
        failed_ids = set(errors)
        repaired_rows = [r for r in repaired_rows if isinstance(r, dict)
                         and isinstance(r.get('condition_id'), str) and r['condition_id'] in failed_ids]
        merged = {'advice': list(valid.values()) + repaired_rows}
        valid, errors = partition_advice(merged, actions, strengths, sources, protected_ids=initially_valid)
    # Fallback has no dependency edges. Final full-batch validation also guards future changes.
    batch = [{**valid[a['id']], 'origin': 'model_tailored'} if a['id'] in valid else
             deterministic_advice(a, inputs, 'deterministic_fallback',
                                  'Model advice failed validation: ' + errors[a['id']][:150]) for a in actions]
    validate_advice({'advice': [{k: v for k, v in row.items() if k not in ('origin', 'fallback_reason')}
                               for row in batch]}, actions, strengths, sources)
    metrics = {'response_recovery': response_recovery, 'provider_errors': provider_errors,
               'repair_failure': repair_failure,
               'provider_failure': 'all_split_requests_failed' if len(provider_errors) == len(actions) else None,
               'initial_invalid': initially_invalid, 'repair_attempted': repair_attempted,
               'repaired_ids': sorted(set(valid) - initially_valid),
               'final_fallback_ids': [a['id'] for a in actions if a['id'] not in valid]}
    return batch, metrics


def enabled():
    return settings.CAPABILITY_RECOMMENDATIONS_ENABLED


@transaction.atomic
def start(*, run, user, key):
    CapabilityRun.objects.select_for_update().get(pk=run.pk)
    signature = digest({'run': str(run.pk), 'operation': 'tailor_recommendations'})
    existing = RecommendationExecution.objects.filter(run=run, idempotency_key=key).first()
    if existing:
        if existing.request_hash != signature:
            raise AssessmentConflict()
        return existing, False
    if not enabled():
        raise AssessmentDisabled('Recommendation inference is not enabled.')
    event = run.events.filter(state='completed', payload__result__isnull=False).last()
    if event is None:
        raise ValidationError('Recommendations require a completed assessment.')
    if RecommendationExecution.objects.filter(run=run, status__in=['queued', 'running']).exists():
        raise AssessmentConflict('Recommendation generation is already active for this assessment.')
    budget = policy(stage='recommendation')
    budget.update(prompt_version=VERSION, prompt_hash=digest(PROMPT), schema_hash=digest(SCHEMA))
    inputs = build_inputs(run, event, budget)
    snapshot = RecommendationSnapshot.objects.create(run=run, assessment_event=event, inputs=inputs, inputs_hash=digest(inputs))
    execution = RecommendationExecution.objects.create(snapshot=snapshot, run=run, requested_by=user,
                                                       idempotency_key=key, request_hash=signature)
    transaction.on_commit(lambda: dispatch(str(snapshot.pk), str(execution.task_id)))
    return execution, True


def dispatch(snapshot_id, task_id):
    try:
        generate_recommendations.apply_async(args=[snapshot_id, task_id], task_id=task_id, retry=False)
    except Exception:
        finish(snapshot_id, 'failed', 'dispatch_failed')


@transaction.atomic
def finish(snapshot_id, status, error_code):
    execution = RecommendationExecution.objects.select_for_update().get(snapshot_id=snapshot_id)
    if execution.status not in {'queued', 'running'}:
        return False
    execution.status = status
    execution.heartbeat_at = timezone.now()
    execution.save(update_fields=['status', 'heartbeat_at'])
    RecommendationEvent.objects.create(snapshot_id=snapshot_id, payload={'kind': 'terminal', 'status': status,
        'error_code': error_code, 'next_action': 'Use the pinned deterministic plan. Review configuration, billing and limits before explicitly starting a new version.'})
    return True


@transaction.atomic
def claim(snapshot_id, task_id):
    execution = RecommendationExecution.objects.select_for_update(of=('self',)).select_related('snapshot__run__sprint', 'snapshot__assessment_event').get(snapshot_id=snapshot_id)
    if execution.status != 'queued' or str(execution.task_id) != str(task_id):
        return None
    if not enabled():
        finish(snapshot_id, 'failed', 'inference_disabled')
        return None
    execution.status = 'running'
    execution.heartbeat_at = timezone.now()
    execution.save(update_fields=['status', 'heartbeat_at'])
    return execution


class RecommendationMeter(MeteredService):
    execution_model = RecommendationExecution
    execution_key = 'snapshot_id'

    def __init__(self, service, execution):
        super().__init__(service, execution, execution_policy=execution.snapshot.inputs['execution_policy'], ledger_id=execution.snapshot_id)

    def enabled(self):
        return enabled()

    def event(self, state, payload):
        return RecommendationEvent.objects.create(snapshot_id=self.run_id, payload={'ledger_status': state, **payload})

    def events(self):
        return RecommendationEvent.objects.filter(snapshot_id=self.run_id)


@transaction.atomic
def save_batch(snapshot_id, indicator, advice, validation=None):
    execution = RecommendationExecution.objects.select_for_update().get(snapshot_id=snapshot_id)
    if execution.status != 'running' or not enabled():
        raise ExecutionStopped()
    RecommendationEvent.objects.create(snapshot_id=snapshot_id, payload={'kind': 'advice_batch', 'indicator': indicator, 'advice': advice, 'validation': validation or {}})
    execution.heartbeat_at = timezone.now()
    execution.save(update_fields=['heartbeat_at'])



def bounded_strengths(assets):
    """Keep cross-capability grounding within a small explicit request budget."""
    result, used = [], 0
    for asset in sorted(assets, key=lambda a: ('FAO'.index(a['condition_id'].rsplit('.', 1)[-1][0]), a['condition_id'])):
        basis = asset.get('basis', [])
        size = sum(len(c.get('quote', '')) for c in basis)
        if not basis or len(basis) > 2 or size > 1600 or used + size > 6000:
            continue
        result.append({**asset, 'reason': asset.get('reason', '')[:500]})
        used += size
        if len(result) == 8:
            break
    return result

@shared_task(acks_late=True, max_retries=0, reject_on_worker_lost=False)
def generate_recommendations(snapshot_id, task_id):
    try:
        execution = claim(snapshot_id, task_id)
    except RecommendationExecution.DoesNotExist:
        return
    if execution is None:
        return
    pool = lease = service = None
    try:
        snapshot = execution.snapshot
        inputs = snapshot.inputs
        if (digest(inputs) != snapshot.inputs_hash or inputs['version'] != VERSION
                or inputs['prompt_hash'] != digest(PROMPT) or inputs['schema_hash'] != digest(SCHEMA)
                or digest(snapshot.assessment_event.payload) != inputs['assessment_hash']):
            finish(snapshot_id, 'failed', 'snapshot_or_methodology_mismatch')
            return
        # Verified strengths can ground tailored evidence checks without asserting that unknown capability is absent.
        foundation = inputs.get('foundation_plan') or {}
        strengths = bounded_strengths(foundation.get('existing_strengths', []))
        # A requirement the assessment never evaluated (or whose output failed validation) is a processing
        # result, not an institutional shortcoming: it is re-assessed, never advised as missing evidence.
        unevaluated = {a['id'] for a in inputs['actions'] if processing_failure(a)}
        # Every planned action is development advice (establish or complete); only reruns stay deterministic.
        model_actions = [a for a in inputs['actions'] if a['id'] not in unevaluated]
        needs_model = bool(model_actions and snapshot.run.inputs['sources'])
        if needs_model:
            pool = get_router_pool()
            if pool is not None:
                lease = pool.acquire()
        # Unknown actions remain evidence checks. Grounded conditional foundation proposals
        # are separate from verified baseline changes and from mandatory development advice.
        model_ids = {a['id'] for a in model_actions}
        validation_batches = []
        provider_failure_streak = 0
        advice = [deterministic_advice(a, inputs, 'processing_rerun') for a in inputs['actions'] if a['id'] in unevaluated]
        advice += [deterministic_advice(a, inputs, 'deterministic_evidence_request') for a in inputs['actions']
                   if a['type'] == 'supply_evidence' and a['id'] not in model_ids | unevaluated]
        from .semantic_retrieval import ranker_for
        semantic_ranker = ranker_for(inputs.get('retrieval_policy')) if needs_model else None
        with use_lease(lease):
            service = RecommendationMeter(get_ai_service(), execution) if needs_model else None
            with usage_scope(sprint=snapshot.run.sprint, stage='capability_recommendations',
                             capability_run=snapshot.run, recommendation_snapshot=snapshot):
                if service:
                    for indicator in dict.fromkeys(a['indicator'] for a in model_actions):
                        actions = [a for a in model_actions if a['indicator'] == indicator]
                        payload = {k: inputs[k] for k in ('profile', 'population', 'reference_period')}
                        from .reviewed_evidence import for_context
                        from .evaluation import select_context
                        rubric_indicator = next(i for i in snapshot.run.inputs['rubric']['indicators'] if i['code'] == indicator)
                        selected_sources = select_context(rubric_indicator, snapshot.run.inputs['sources'], semantic_ranker=semantic_ranker)
                        payload['sources'] = selected_sources
                        payload['reviewed_evidence'] = for_context(inputs.get('reviewed_evidence'), selected_sources)
                        payload['actions'] = actions
                        payload['established_strengths'] = strengths
                        payload['foundation_goals'] = [{k: g[k] for k in ('id', 'title', 'depends_on', 'status', 'conditional')} for g in foundation.get('goals', [])]
                        scope = inputs.get('scope') or {}
                        payload['scope'] = {k: scope[k] for k in ('institution', 'mode', 'population_label', 'period_label', 'limitations') if k in scope}
                        if provider_failure_streak >= 2:
                            batch = [deterministic_advice(a, inputs, 'deterministic_fallback',
                                'Recommendation provider circuit open; basic assessment guidance retained.') for a in actions]
                            validation = {'initial_invalid': {}, 'repair_attempted': False, 'repaired_ids': [],
                                'final_fallback_ids': [a['id'] for a in actions], 'provider_failure': 'circuit_open'}
                        else:
                            batch, validation = tailor_batch(service, payload, inputs)
                        provider_failure_streak = provider_failure_streak + 1 if validation.get('provider_failure') else 0
                        save_batch(snapshot_id, indicator, batch, validation)
                        validation_batches.append({'indicator': indicator, **validation})
                        advice.extend(batch)
            with transaction.atomic():
                locked = RecommendationExecution.objects.select_for_update().get(snapshot_id=snapshot_id)
                if locked.status != 'running' or not enabled():
                    if locked.status == 'running':
                        finish(snapshot_id, 'failed', 'inference_disabled')
                    return
                RecommendationEvent.objects.create(snapshot=snapshot, payload={'kind': 'completed',
                    'advice': advice, 'inputs_hash': snapshot.inputs_hash,
                    'validation': {'initial_invalid_items': sum(len(b['initial_invalid']) for b in validation_batches),
                        'repair_attempted_batches': sum(b['repair_attempted'] for b in validation_batches),
                        'repaired_items': sum(len(b['repaired_ids']) for b in validation_batches),
                        'fallback_items': sum(len(b['final_fallback_ids']) for b in validation_batches),
                        'split_batches': sum(bool(b.get('response_recovery', {}).get('split_attempted')) for b in validation_batches),
                        'provider_failed_batches': sum(bool(b.get('provider_failure')) for b in validation_batches),
                        'batches': validation_batches},
                    'mode': 'tailored' if service else 'deterministic',
                    'inference': service.metadata() if service else {'provider': 'none', 'model': 'none', 'calls': []}})
                locked.status = 'completed'
                locked.heartbeat_at = timezone.now()
                locked.save(update_fields=['status', 'heartbeat_at'])
    except ExecutionStopped:
        finish(snapshot_id, 'cancelled', 'inference_stopped')
    except ExecutionDeadlineExceeded:
        finish(snapshot_id, 'failed', 'execution_deadline_exceeded')
    except BudgetExceeded:
        finish(snapshot_id, 'failed', 'budget_exhausted')
    except UnpricedModel:
        finish(snapshot_id, 'failed', 'model_pricing_required')
    except UsageUnavailable:
        finish(snapshot_id, 'failed', 'usage_telemetry_missing')
    except ProviderQuotaExhausted:
        if pool is not None and lease is not None:
            pool.mark_exhausted(lease.router, 'Recommendation provider quota exhausted')
        finish(snapshot_id, 'failed', 'provider_quota_exhausted')
    except Exception:
        finish(snapshot_id, 'failed', 'tailoring_failed')
    finally:
        if pool is not None and lease is not None:
            pool.release(lease)


def summary(execution):
    return {'id': str(execution.snapshot_id), 'run_id': str(execution.run_id), 'status': execution.status,
            'requests_reserved': execution.requests_reserved, 'reserved_cost_usd': str(execution.usd_reserved),
            'created_at': execution.created_at, 'heartbeat_at': execution.heartbeat_at,
            'stalled': execution.status in {'queued', 'running'} and execution.heartbeat_at < timezone.now() - timedelta(seconds=settings.CAPABILITY_STALE_SECONDS)}
