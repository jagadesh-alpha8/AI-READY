"""Material, scoped, persisted questions. No provider calls and no work on GET.

The initial batch is a lifetime set of <=25 presented questions, including scope
and identity. Overflow and newly discovered evidence are explicit optional detail.
A conservative lexical link is a candidate affected requirement, never score impact.
"""
import hashlib
import json
import re
from collections import Counter

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.sprints.models import Sprint
from .models import ExtractedFact, FactReviewHistory, ReviewBatch
from .verification import engine, policy
from .verification.normalize import comparable_value
from .verification.scope import read_scope


def fingerprint(fact):
    return hashlib.sha256(json.dumps([str(fact.pk), fact.value, fact.status, fact.scope,
        str(fact.source_document_id or fact.document_id), fact.source_page, fact.source_snippet,
        fact.updated_at.isoformat()], sort_keys=True, default=str).encode()).hexdigest()


def _key(fact):
    # Exact scoped grouping, deliberately stricter than conflict candidates.
    scope = read_scope(fact)
    stated = fact.scope or {}
    identity = {k: stated.get(k) for k in ('entity', 'institution', 'department', 'programme', 'population')}
    return json.dumps([fact.field_key.lower(), scope, identity], sort_keys=True)


def affected(fact, rubric):
    words = set(re.findall(r'[a-z]{4,}', f'{fact.field_name} {fact.field_key} {fact.source_snippet}'.lower()))
    stop = {'institution', 'college', 'university', 'students', 'faculty', 'there', 'their', 'with', 'that',
            'from', 'have', 'been', 'this', 'number', 'total', 'during', 'year', 'department'}
    words -= stop
    tags = {m.indicator_code for m in fact.aiqif_mappings.all() if m.review_status != 'rejected'}
    result = []
    for indicator in rubric['indicators']:
        for condition in indicator['conditions']:
            tokens = set(re.findall(r'[a-z]{4,}', condition['text'].lower())) - stop
            if indicator['code'] in tags or len(tokens & words) >= 2:
                result.append(condition['id'])
    return result


def candidates(sprint):
    from apps.scoring.capability.engine import release
    rubric = release()
    groups = {}
    facts = ExtractedFact.objects.filter(sprint=sprint, status__in=['extracted', 'evidence_requested', 'confirmed', 'corrected']).select_related(
        'source_document', 'document').prefetch_related('aiqif_mappings').order_by('id')
    for f in facts:
        doc = f.source_document or f.document
        if doc and (doc.sprint_id != sprint.pk or doc.superseded_at or doc.status == 'rejected'):
            continue
        if f.status == 'extracted' and f.grounding_status in ('not_found', 'page_missing', 'wrong_sprint'):
            continue  # bounded repair failed: system recovery detail, not a human parsing task
        requirements = affected(f, rubric)
        essential = f.fact_kind == 'profile' and f.profile_field in ('institution_type', 'programme', 'other')
        if not requirements and not essential:
            continue  # searchable supporting detail, not primary human work
        row = groups.setdefault(_key(f), {'facts': [], 'requirements': set(), 'essential': essential})
        row['facts'].append(f)
        row['requirements'].update(requirements)
    cases = []
    identity = identity_case(sprint)
    if identity:
        cases.append(identity)
    for key, group in groups.items():
        rows = group['facts']
        if not any(f.status in ('extracted', 'evidence_requested') for f in rows):
            continue
        alternatives = {}
        for f in rows:
            value_key = comparable_value(f.value, f.data_type)
            alt = alternatives.setdefault(value_key, {'value': f.value, 'fact_ids': [], 'excerpts': []})
            alt['fact_ids'].append(str(f.pk))
            doc = f.source_document or f.document
            alt['excerpts'].append({'fact_id': str(f.pk), 'document_id': str(doc.pk) if doc else None,
                'filename': doc.original_filename if doc else '', 'version': doc.version_number if doc else None,
                'page': f.source_page, 'quote': f.source_snippet, 'verification': f.verification_status})
        first = rows[0]
        conflict = len(alternatives) > 1
        case_id = hashlib.sha256(key.encode()).hexdigest()[:24]
        cases.append({'id': case_id, 'question': f'Which value can you establish for {first.field_name or first.field_key}?'
                      if conflict else f'Can you establish {first.field_name or first.field_key}?',
            'scope': {**read_scope(first), 'stated': first.scope}, 'alternatives': list(alternatives.values()),
            'fact_ids': [str(f.pk) for f in rows], 'revisions': {str(f.pk): fingerprint(f) for f in rows},
            'affected_requirements': sorted(group['requirements']), 'essential_scope': group['essential'],
            'suggestion': 'Choose the supported alternative; compare its scope and source. If uncertain, defer.'
                          if conflict else 'Confirm only if the excerpt supports this scoped value; otherwise correct with a basis or leave it unknown.',
            'reason': 'Sources disagree on the same scoped attribute.' if conflict else 'May affect the listed capability findings or subsequent advice.',
            'conflict': conflict})
    cases.sort(key=lambda c: (c.get('kind') != 'identity', not c['essential_scope'], not c['conflict'], -len(c['affected_requirements']), c['id']))
    for index, case in enumerate(cases):
        case['initial'] = index < 25
    return cases


@transaction.atomic
def start(sprint):
    Sprint.objects.select_for_update().get(pk=sprint.pk)
    existing = ReviewBatch.objects.filter(sprint=sprint).first()
    if existing:
        return existing, False
    # Diagnose and apply existing policy, never change shadow to enforce or relax checks.
    for fact in ExtractedFact.objects.filter(sprint=sprint, status='extracted').select_related('source_document', 'document'):
        engine.verify_fact(fact, source='reverify', apply_policy=False)
        repair_source(fact)
        engine.verify_fact(fact, source='reverify', apply_policy=True)
    return ReviewBatch.objects.create(sprint=sprint, cases=candidates(sprint)), True


def view(sprint):
    batch = ReviewBatch.objects.filter(sprint=sprint).first()
    if not batch:
        return {'started': False, 'initial_limit': 25, 'cases': [], 'overflow': [], 'decisions': {}, 'mode': policy.mode()}
    facts = {str(f.pk): f for f in ExtractedFact.objects.filter(sprint=sprint)}
    cases = []
    for case in batch.cases:
        decision = batch.decisions.get(case['id'])
        changed = (case.get('kind') == 'identity' and (identity_case(sprint) or {}).get('source_hash') != case.get('source_hash')) or any(fid not in facts or fingerprint(facts[fid]) != rev for fid, rev in case['revisions'].items())
        resolved_elsewhere = bool(case['fact_ids']) and all(fid in facts and facts[fid].status in ('confirmed', 'corrected', 'rejected') for fid in case['fact_ids'])
        state = decision['action'] if decision else 'resolved_elsewhere' if resolved_elsewhere else 'stale' if changed else 'awaiting'
        cases.append({**case, 'state': state, 'changed': changed})
    known = {fid for c in batch.cases for fid in c['fact_ids']}
    new = list(ExtractedFact.objects.filter(sprint=sprint, status='extracted').exclude(pk__in=known).values_list('id', flat=True))
    further = fresh_candidates(sprint, batch)
    return {'started': True, 'id': str(batch.pk), 'initial_limit': 25, 'mode': policy.mode(),
            'cases': [c for c in cases if c['initial']], 'overflow': [c for c in cases if not c['initial']],
            'decisions': batch.decisions, 'new_unbatched_fact_count': len(new), 'new_material_case_count': len(further),
            'note': 'The initial questions never refill. Deferred issues remain unknown where evidence is insufficient. New evidence can be assessed in a fresh run; optional follow-up does not alter the initial budget.'}


@transaction.atomic
def decide(sprint, user, case_id, data):
    from . import ownership, evidence_requests
    from apps.gaps.services import after_fact_review
    Sprint.objects.select_for_update().get(pk=sprint.pk)
    batch = ReviewBatch.objects.select_for_update().get(sprint=sprint)
    case = next((c for c in batch.cases if c['id'] == case_id), None)
    if not case:
        raise ValidationError('Unknown case.')
    if not case['initial'] and data.get('optional_follow_up') is not True:
        raise ValidationError('This is optional follow-up outside the initial batch.')
    action = data.get('action')
    if action not in ('identity', 'confirm', 'choose', 'correct', 'defer', 'cannot_establish'):
        raise ValidationError('Choose a supported decision action.')
    canonical = {k: data.get(k) for k in ('action', 'fact_id', 'value', 'reason', 'source_document_id', 'source_page', 'source_snippet', 'source_institution')}
    previous = batch.decisions.get(case_id)
    if previous:
        if previous['request'] != canonical:
            raise ValidationError('This case has already been decided. Later evidence requires a new assessment/review revision.')
        return previous
    facts = list(ExtractedFact.objects.select_for_update().filter(sprint=sprint, pk__in=case['fact_ids']).order_by('id'))
    if len(facts) != len(case['fact_ids']) or any(fingerprint(f) != case['revisions'][str(f.pk)] for f in facts):
        raise ValidationError('Evidence changed after this question was prepared. Inspect supporting detail; the initial batch will not silently refill.')
    for f in facts:
        allowed, why = ownership.check_fact(user, f)
        if not allowed:
            raise PermissionDenied(why)
        if evidence_requests.open_request_for(f):
            raise ValidationError('Decide the existing evidence request first.')
    reason = (data.get('reason') or '').strip()
    if action in ('correct', 'cannot_establish', 'defer') and not reason:
        raise ValidationError('Provide the basis or reason for this decision.')
    chosen = next((a for a in case['alternatives'] if data.get('fact_id') in a['fact_ids']), None)
    if case.get('kind') == 'identity':
        current = identity_case(sprint)
        if not current or current['source_hash'] != case['source_hash']:
            raise ValidationError('Source identity evidence changed; inspect the new documents.')
        if action not in ('identity', 'defer', 'cannot_establish'):
            raise ValidationError('Choose the source institution or leave attribution unresolved.')
        if action == 'identity' and data.get('source_institution') not in [a['value'] for a in case['alternatives']]:
            raise ValidationError('Choose an institution named by the current sources.')
    elif action == 'identity':
        raise ValidationError('This question does not concern institution identity.')
    if action in ('confirm', 'choose'):
        if not chosen and len(case['alternatives']) == 1:
            chosen = case['alternatives'][0]
        if not chosen or (action == 'confirm' and case['conflict']):
            raise ValidationError('Choose one scoped alternative explicitly.')
        # Human resolution can settle a cross-source discrepancy but cannot fabricate grounding.
        for f in facts:
            if str(f.pk) in chosen['fact_ids']:
                check = engine.verify_snapshot(engine.Snapshot.of(f), exclude_ids=[x.pk for x in facts])
                if check.grounding.get('citation') != 'ok' or check.grounding.get('quote') not in ('exact', 'ocr_variant') or check.grounding.get('value_support') != 'in_quote' or check.validation.get('status') == 'fail':
                    raise ValidationError('This alternative needs a supported correction or additional evidence; its source checks have not passed.')
    if action == 'correct' and 'value' not in data:
        raise ValidationError('Supply a corrected value, including null if unknown.')
    now = timezone.now()
    if action not in ('identity', 'defer', 'cannot_establish'):
        for f in facts:
            before = f.value
            if action == 'correct':
                if f.original_value is None:
                    f.original_value = f.value
                if not f.original_source_snippet:
                    f.original_source_document_id = f.source_document_id or f.document_id
                    f.original_source_page, f.original_source_snippet = f.source_page, f.source_snippet
                f.value, f.normalized_value = data['value'], None
                f.value_origin = 'corrected'
                from apps.documents.models import Document
                doc_id = data.get('source_document_id')
                doc = Document.objects.filter(sprint=sprint, pk=doc_id).first() if doc_id else None
                if doc_id and doc is None:
                    raise ValidationError('The correction source must belong to this sprint.')
                f.source_document = doc
                f.source_page = data.get('source_page') or ''
                f.source_snippet = data.get('source_snippet') or ''
                f.status = 'corrected'
            else:
                f.status = 'confirmed' if str(f.pk) in chosen['fact_ids'] else 'rejected'
            FactReviewHistory.objects.create(fact=f, action=f.status, original_value=before,
                new_value=f.value if action == 'correct' else None, user=user, reason=reason,
                decision_source='person', details={'review_batch_id': str(batch.pk), 'case_id': case_id,
                                                  'affected_claim_ids': case['fact_ids']})
            f.reviewed_by, f.reviewed_at = user, now
            f.save()
            if action == 'correct':
                engine.verify_fact(f, source='correction', apply_policy=False)
            after_fact_review(f, user=user, reason=reason)
    decision = {'id': f'{batch.pk}:{case_id}', 'action': action, 'request': canonical,
                'actor_id': str(user.pk), 'timestamp': now.isoformat(), 'claim_ids': case['fact_ids'],
                'scope': case['scope'], 'rationale': reason}
    batch.decisions = {**batch.decisions, case_id: decision}
    batch.save(update_fields=['decisions', 'updated_at'])
    return decision


def identity_case(sprint):
    from apps.scoring.capability.storage import evidence_snapshot, digest
    from apps.scoring.capability.scope import resolve
    manifest, sources = evidence_snapshot(sprint)
    scope = resolve(profile={'name': sprint.institution.name}, sources=sources, requested={}, mode='default')
    if scope['institution']['identity_status'] != 'mismatch_requires_review':
        return None
    names = sorted({d['value'] for d in scope['source_declarations'] if d['kind'] == 'institution_identity'})
    by_id = {s['id']: s for s in sources}
    return {'id': 'source-institution-identity', 'kind': 'identity',
            'source_hash': digest(manifest), 'question': 'Which institution do these source records concern?',
            'scope': {'profile_name': sprint.institution.name}, 'fact_ids': [], 'revisions': {},
            'alternatives': [{'value': name, 'fact_ids': [], 'excerpts': [
                {'filename': next((m['filename'] for m in manifest if m['document_id'] == by_id[d['source_id']]['document_id']), ''),
                 'page': str(by_id[d['source_id']]['page_number']), 'quote': d['quote'], 'verification': 'explicit source label, identity unconfirmed'}
                for d in scope['source_declarations'] if d['kind'] == 'institution_identity' and d['value'] == name]} for name in names],
            'affected_requirements': [], 'essential_scope': True, 'conflict': True,
            'suggestion': 'Select the institution named in these records. The saved profile is not renamed.',
            'reason': 'Source attribution differs from the selected institution profile.'}


def fresh_candidates(sprint, batch):
    known = {(c['id'].split(':revision:')[0], json.dumps(c['revisions'], sort_keys=True), c.get('source_hash')) for c in batch.cases}
    return [c for c in candidates(sprint) if (c['id'], json.dumps(c['revisions'], sort_keys=True), c.get('source_hash')) not in known]


@transaction.atomic
def follow_up(sprint):
    Sprint.objects.select_for_update().get(pk=sprint.pk)
    batch = ReviewBatch.objects.select_for_update().get(sprint=sprint)
    extra = fresh_candidates(sprint, batch)
    for case in extra:
        revision = hashlib.sha256(json.dumps([case['revisions'], case.get('source_hash')], sort_keys=True).encode()).hexdigest()[:12]
        case['id'] += ':revision:' + revision
        case['initial'] = False
    batch.cases = [*batch.cases, *extra]
    batch.save(update_fields=['cases', 'updated_at'])
    return batch


def repair_source(fact):
    """One bounded deterministic attempt, only for unreviewed extraction errors.

    Reuse a unique exact line on the cited page with the value and >=2 attribute
    words. Never invent text, change a value, accept a fact or weaken verification.
    Ambiguous/failed repairs remain recorded system limitations.
    """
    from .verification import grounding, normalize
    if fact.status != 'extracted' or fact.grounding_status in ('exact', 'ocr_variant'):
        return False
    doc = fact.source_document or fact.document
    pages = grounding.parse_pages(fact.source_page)
    if not doc or doc.sprint_id != fact.sprint_id or len(pages) != 1:
        return False
    text = grounding.page_text(doc, pages[0]) or ''
    words = set(normalize.tokens(fact.field_name + ' ' + fact.field_key.replace('_', ' ')))
    words -= {'the', 'of', 'in', 'to', 'number', 'total'}
    matches = []
    for line in text.splitlines()[:1000]:
        if len(set(normalize.tokens(line)) & words) < 2:
            continue
        support, _, _ = grounding.value_support(fact.value, fact.data_type, line)
        if support == 'in_quote':
            candidate = engine.verify_snapshot(engine.Snapshot.of(fact, source_snippet=line))
            if candidate.grounding['quote'] in ('exact', 'ocr_variant') and candidate.validation['status'] != 'fail':
                matches.append(line)
    if len(set(matches)) != 1:
        return False
    before = fact.source_snippet
    if not fact.original_source_snippet:
        fact.original_source_document_id = fact.source_document_id or fact.document_id
        fact.original_source_page, fact.original_source_snippet = fact.source_page, before
    fact.source_snippet = matches[0]
    fact.save()
    FactReviewHistory.objects.create(fact=fact, action='source_repaired', original_value=fact.value,
        decision_source='rule', reason='Recovered one unique exact source line; full verification still required.',
        details={'before_quote': before, 'after_quote': fact.source_snippet, 'bounded_attempts': 1})
    return True
