"""Database side of the follow-up stage (depth.py holds the logic). Each function works from an assessment export
(the same JSON assessment_consistency reads), so the stage can run on a frozen corpus without a live run.

    plan = create_questions(export, model, commit=False)     # dry run: questions are returned, nothing saved
    load_responses(rows, commit=True)
    result = judge_run(export, model, commit=True)
    print(depth_report(export))
"""
import uuid
from decimal import Decimal

from django.conf import settings
from django.db import transaction

from apps.scoring.models import DepthJudgment, DepthPastCase, DepthPlan, DepthQuestion, DepthResponse

from . import depth
from .engine import documented

PAST_CASES = 3


class DepthError(Exception):
    pass


def _records(export):
    try:
        return export['run_id'], export['rubric'], export['assessment']['records']
    except (KeyError, TypeError):
        raise DepthError('Not an assessment export: needs run_id, rubric and assessment.records.')


def policy():
    """The open decisions as currently configured, recorded with every judgment."""
    mode = settings.DEPTH_CREDIT_MODE
    share = settings.DEPTH_CREDIT_SHARE or None
    if mode == 'reserve' and share is None:
        raise DepthError('DEPTH_CREDIT_MODE=reserve needs DEPTH_CREDIT_SHARE.')
    return {'lowering': settings.DEPTH_ANSWERS_CAN_LOWER, 'unsupported': settings.DEPTH_UNSUPPORTED_ANSWERS,
            'credit_mode': mode, 'credit_share': share}


# ------------------------------------------------------------------ questions


def create_questions(export, model, *, commit=False, replace=False, max_calls=None, guard=None, concurrency=1):
    """Plan the run's questions (model calls for depth questions) and, with commit, save them. guard, when given, is
    called inside the saving transaction before anything is written (a background job uses it to save nothing once it
    has been cancelled); the refusals are checked again there, since the planning calls take time."""
    from .layer2 import Layer2Error
    from .layer2_service import refuse_old_rule
    run_ref, rubric, records = _records(export)
    try:
        refuse_old_rule(export)   # its answers could never be re-judged into a final result
    except Layer2Error as exc:
        raise DepthError(str(exc))
    existing = DepthQuestion.objects.filter(run_ref=run_ref)
    if existing.exists() and not replace:
        raise DepthError(f'Run {run_ref} already has questions; pass replace to plan them again.')
    if replace and DepthResponse.objects.filter(question__run_ref=run_ref).exists():
        raise DepthError(f'Run {run_ref} has responses; its questions cannot be replaced.')
    spec = depth.spec()
    from fractions import Fraction
    share = max([Fraction(str(r.get('depth_share') or 0)) for r in records] or [Fraction(0)])
    planned, notes, shown = depth.plan_all(records, rubric, model, max_questions=settings.DEPTH_MAX_QUESTIONS,
                                           max_calls=max_calls, concurrency=concurrency, depth_spec=spec, share=share)
    if commit:
        with transaction.atomic():
            if guard is not None:
                guard()
            if replace and DepthResponse.objects.filter(question__run_ref=run_ref).exists():
                raise DepthError(f'Run {run_ref} has responses; its questions cannot be replaced.')
            if not replace and DepthQuestion.objects.filter(run_ref=run_ref).exists():
                raise DepthError(f'Run {run_ref} already has questions; pass replace to plan them again.')
            DepthQuestion.objects.filter(run_ref=run_ref).delete()
            DepthPlan.objects.update_or_create(run_ref=run_ref, defaults={
                'version': depth.PLAN_VERSION, 'shown_by_evidence': shown, 'notes': notes,
                'model': getattr(model, 'model_name', '')})
            DepthQuestion.objects.bulk_create([
                DepthQuestion(run_ref=run_ref, kind=q['kind'], indicator_code=q['indicator'],
                              condition_ids=q['condition_ids'], dimension_ids=q['dimension_ids'], text=q['text'],
                              rank=q['rank'], answered_by_evidence=q.get('answered_by_evidence', []),
                              points_at_stake=Decimal(str(q.get('points_at_stake') or 0)),
                              spec_version=spec['version'], model=getattr(model, 'model_name', ''))
                for q in planned])
    return {'run_ref': run_ref, 'questions': planned, 'notes': notes, 'shown_by_evidence': shown, 'saved': commit}


# ------------------------------------------------------------------ responses


def _uuid(value):
    try:
        return str(uuid.UUID(str(value)))
    except ValueError:
        return None


def load_responses(rows, *, commit=False, via='file'):
    """rows: [{'question_id', 'kind': 'answer'|'upload'|'dont_know', 'answer', 'document_ids', 'supported'}].
    The file path is consultant-attested: a consultant who has read the documents loads the rows, and they are saved as
    checked (no second-layer search or check). An upload is supported by definition; an answer is supported only when
    the row says so AND names its documents (decision 3: a typed answer without a supporting document counts for
    nothing), and a row marked supported without documents is refused. Every row is checked before anything is
    saved."""
    kinds = set(DepthResponse.Kind.values)
    ids = [i for i in (_uuid(r.get('question_id')) for r in rows) if i]
    questions = {str(k): v for k, v in DepthQuestion.objects.in_bulk(ids).items()}
    problems, responses = [], []
    for n, row in enumerate(rows, 1):
        question = questions.get(_uuid(row.get('question_id')) or '')
        if question is None:
            problems.append(f'row {n}: unknown question {row.get("question_id")!r}')
            continue
        kind = row.get('kind')
        if kind not in kinds:
            problems.append(f'row {n}: kind must be one of {sorted(kinds)}')
            continue
        documents = list(row.get('document_ids') or [])
        if kind == 'upload' and not documents:
            problems.append(f'row {n}: an upload needs document_ids')
            continue
        if kind == 'answer' and not (row.get('answer') or '').strip():
            problems.append(f'row {n}: an answer needs text')
            continue
        if kind == 'answer' and row.get('supported') and not documents:
            problems.append(f'row {n}: an answer marked supported needs the document_ids that support it')
            continue
        supported = kind == 'upload' or bool(row.get('supported') and kind == 'answer')
        responses.append(DepthResponse(question=question, kind=kind, answer=(row.get('answer') or '').strip(),
                                       document_ids=documents, supported=supported, submitted_via=via,
                                       status=DepthResponse.Status.CHECKED))
    if problems:
        raise DepthError('Responses not loaded:\n' + '\n'.join(problems))
    if commit:
        with transaction.atomic():
            DepthResponse.objects.bulk_create(responses)
            DepthQuestion.objects.filter(pk__in={r.question_id for r in responses}).update(
                status=DepthQuestion.Status.ANSWERED)
    return len(responses)


# ------------------------------------------------------------------ judging


def _exchanges(questions):
    """The college's checked responses, follow-up answers included. A response checked in the second layer
    (layer2.py) carries what its documents were found to support; one still waiting for its check is left out."""
    from . import layer2
    out = []
    for question in questions:
        for response in question.responses.all():
            if response.status != DepthResponse.Status.CHECKED:
                continue
            row = {'question': response.parent.follow_up_text if response.parent_id else question.text,
                   'kind': response.kind, 'answer': response.answer, 'documents': len(response.document_ids),
                   'supported': response.supported}
            if response.support_check:
                row['checked_against_documents'] = layer2.evidence_for_judge(response.support_check)
            out.append(row)
    return out


def _shown_by_evidence(run_ref):
    plan = DepthPlan.objects.filter(run_ref=run_ref).first()
    return list(plan.shown_by_evidence) if plan else []


def approved_past_cases(condition_id, spec_version, limit=PAST_CASES):
    cases = (DepthPastCase.objects.filter(condition_id=condition_id, spec_version=spec_version,
                                          status=DepthPastCase.Status.APPROVED)
             .order_by('-reviewed_at', '-created_at')[:limit])
    return [{'id': str(c.pk), 'level': c.level, 'dimension_findings': c.dimension_findings, 'reasoning': c.reasoning}
            for c in cases]


def judge_run(export, model, *, commit=False, max_calls=None, guard=None):
    """Judge every credited condition of the run that has answered depth questions.

    Conditions whose questions got no response stay evidenced (listed in 'unanswered'). A condition with any response
    still waiting for its second-layer check is not judged yet (listed in 'awaiting_check'): judging it on half its
    answers would save a judgment and a past case that the rest could change. Under decision 3 ('ignore'), typed
    answers without a supporting document are not sent to the judge; a condition with nothing else stays evidenced
    without a model call (listed in 'answers_without_documents'). Missing-evidence questions answered with documents
    are listed in 'awaiting_reassessment': they go to the credit path (layer2_rejudge), not to a depth judgment.
    guard: as for create_questions."""
    run_ref, rubric, records = _records(export)
    rules = policy()
    spec = depth.spec()
    by_id = {r['condition_id']: r for r in records}
    questions = list(DepthQuestion.objects.filter(run_ref=run_ref).prefetch_related('responses', 'responses__parent'))
    if not questions:
        raise DepthError(f'Run {run_ref} has no questions.')
    per_condition, unanswered, awaiting, without_documents, awaiting_check = {}, [], [], [], []
    for question in questions:
        answered = question.responses.all()
        if question.kind == DepthQuestion.Kind.MISSING:
            if any(r.kind == DepthResponse.Kind.UPLOAD or r.document_ids for r in answered):
                awaiting.append({'rank': question.rank, 'conditions': question.condition_ids})
            continue
        cid = question.condition_ids[0]
        per_condition.setdefault(cid, []).append(question)
    # A fact asked once for two requirements of the same key indicator counts for both (questions-0.2): a requirement
    # also reads the answers to questions on its indicator's other requirements that asked about its dimensions.
    depth_questions = [q for q in questions if q.kind == DepthQuestion.Kind.DEPTH]
    for cid in list(per_condition) + [c for c in _shown_by_evidence(run_ref) if c not in per_condition]:
        if cid not in by_id:
            continue
        # Only for the dimensions it was not asked about itself (the planner left them out because they were asked
        # under another requirement).
        mine = set(spec['indicators'][cid.rsplit('.', 1)[0]]['conditions'][cid]['dimensions'])
        own = [q for q in per_condition.get(cid, []) if q.condition_ids[0] == cid]
        mine -= {d for q in own for d in (q.dimension_ids or [])}
        mine -= {a.get('dimension_id') for q in own for a in (q.answered_by_evidence or [])}
        shared = [q for q in depth_questions if q.condition_ids[0] != cid
                  and q.indicator_code == cid.rsplit('.', 1)[0] and mine & set(q.dimension_ids or [])]
        per_condition.setdefault(cid, []).extend(shared)
    shown = set(_shown_by_evidence(run_ref))
    judged = []
    for cid, condition_questions in per_condition.items():
        if any(r.status == DepthResponse.Status.PENDING for q in condition_questions for r in q.responses.all()):
            awaiting_check.append(cid)
            continue
        exchanges = _exchanges(condition_questions)
        if not exchanges and cid not in shown:
            unanswered.append(cid)
            continue
        if rules['unsupported'] == 'ignore':
            exchanges = depth.counted_exchanges(exchanges)
            if not exchanges and cid not in shown:
                without_documents.append(cid)
                continue
        if exchanges and all(e['kind'] == 'dont_know' for e in exchanges) and cid not in shown:
            # "Don't know" leaves the requirement at evidenced (JUDGE_PROMPT says so): no model call is needed, and
            # the credit held for depth stays held (reserve.py).
            provisional = by_id[cid].get('credit') or 0
            judged.append({'condition_id': cid, 'level': 'evidenced', 'contradicts_evidence': False,
                           'relies_on_unsupported': False, 'dimension_findings': [],
                           'reason': 'You told us you do not have records for this yet, so it stays as your documents show it.',
                           'final_level': 'evidenced', 'provisional_credit': provisional,
                           'final_credit': float(depth.depth_credit(provisional, 'evidenced', mode=rules['credit_mode'],
                                                                    share=rules['credit_share'])),
                           'past_case_ids': [], 'model_called': False})
            continue
        if max_calls is not None and sum(1 for j in judged if j.get('model_called', True)) >= max_calls:
            unanswered.append(cid)
            continue
        cases = approved_past_cases(cid, spec['version'])
        result = depth.judge_depth(cid, by_id[cid], exchanges, cases, model, depth_spec=spec)
        final = depth.apply_policy(result, lowering=rules['lowering'], unsupported=rules['unsupported'])
        provisional = by_id[cid].get('credit') or 0
        credit = depth.depth_credit(provisional, final, mode=rules['credit_mode'], share=rules['credit_share'])
        judged.append({'condition_id': cid, **result, 'final_level': final, 'provisional_credit': provisional,
                       'final_credit': float(credit), 'past_case_ids': [c['id'] for c in cases],
                       'model_called': True, **({'on_own_quotes': True} if not exchanges else {})})
    if commit:
        with transaction.atomic():
            if guard is not None:
                guard()
            for row in judged:
                judgment = DepthJudgment.objects.create(
                    run_ref=run_ref, condition_id=row['condition_id'],
                    provisional_credit=Decimal(str(row['provisional_credit'])), judged_level=row['level'],
                    contradicts_evidence=row['contradicts_evidence'],
                    relies_on_unsupported=row['relies_on_unsupported'], final_level=row['final_level'],
                    final_credit=Decimal(str(round(row['final_credit'], 4))),
                    dimension_findings=row['dimension_findings'], reason=row['reason'], policy=rules,
                    past_case_ids=row['past_case_ids'], spec_version=spec['version'],
                    model=getattr(model, 'model_name', ''))
                if not row.get('model_called', True):
                    continue   # a "don't know" placement is not a past case to learn from
                DepthPastCase.objects.create(judgment=judgment, condition_id=row['condition_id'],
                                             level=row['final_level'], dimension_findings=row['dimension_findings'],
                                             reasoning=row['reason'], spec_version=spec['version'])
    return {'run_ref': run_ref, 'policy': rules, 'judged': judged, 'unanswered': sorted(unanswered),
            'answers_without_documents': sorted(without_documents), 'awaiting_check': sorted(awaiting_check),
            'awaiting_reassessment': awaiting, 'saved': commit}


# ------------------------------------------------------------------ report


def latest_levels(run_ref):
    levels = {}
    for judgment in DepthJudgment.objects.filter(run_ref=run_ref).order_by('condition_id', '-created_at'):
        levels.setdefault(judgment.condition_id, judgment.final_level)
    return levels


def depth_report(export):
    """Depth results for a run: level counts, the depth index, and -- only when decision 2 is set to 'reserve' --
    the headline score with depth applied beside the provisional one. Never written into the assessment reports."""
    run_ref, rubric, records = _records(export)
    rules = policy()
    levels = latest_levels(run_ref)
    counts = {level: 0 for level in depth.LEVELS}
    for record in records:
        if (record.get('credit') or 0) > 0:
            counts[levels.get(record['condition_id'], 'evidenced')] += 1
    from .reserve import scored_credits
    provisional = documented(scored_credits(records), rubric)['overall']
    report = {'run_ref': run_ref, 'policy': rules, 'credited_conditions_by_level': counts,
              'depth_index': depth.depth_index(levels, records, rubric), 'provisional_score': provisional,
              'questions': DepthQuestion.objects.filter(run_ref=run_ref).count(),
              'answered_questions': DepthQuestion.objects.filter(run_ref=run_ref,
                                                                 status=DepthQuestion.Status.ANSWERED).count()}
    if rules['credit_mode'] == 'reserve':
        from .reserve import stamp
        shared = [dict(r) for r in records]
        share = next((r.get('depth_share') for r in records if r.get('depth_share')), rules['credit_share'])
        report['score_with_depth'] = documented(scored_credits(stamp(shared, share, levels)), rubric)['overall']
    else:
        report['score_with_depth'] = None
        report['note'] = ('Decision 2 (how much credit depth carries) is not set to reserve, so depth changes no '
                          'credit; only the depth index is reported.')
    return report
