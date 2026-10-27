"""Automatic AI-QIF tagging: what kind a fact is, which key indicators it gets, what counts, and the expert queue.

Rule 1 -- every fact has a kind (ExtractedFact.fact_kind), chosen by the extractor and checked here:
    ai_evidence   the fact itself is about AI (an AI course, lab, policy, AI-trained faculty, AI projects/tools)
    context       a number the evidence needs (intake, enrolment, faculty count, pass rates)
    profile       who the institution is (type, approvals, autonomy, programmes) -- pre-fills the benchmark
                  profile (profile_suggestion.py)
  A context/profile fact whose text mentions AI goes to the expert queue (it may be AI evidence), unless a
  Super Admin already decided its kind.

Rule 2 -- which indicators a fact gets, in this order:
    1. a NAAC metric that appears in the text and is in the approved NAAC -> AI-QIF crosswalk: the crosswalk
       decides the indicators and their relationship (source=crosswalk, accepted automatically);
    2. AI evidence otherwise: the AI's suggestions; one is accepted automatically when its confidence is at least
       AIQIF_MAPPING_MIN_CONFIDENCE and it belongs to the fact's own criterion -- else it waits for a Super Admin.
       With a crosswalk metric, AI suggestions are kept only for the AI-specific indicators (no NAAC link);
    3. context/profile facts: their crosswalk links are stored as Contextual only; AI suggestions are not used.
  A tag a person confirmed, rejected or added is kept as they left it (a person's decision always wins).

Rule 3 -- a tag counts toward AI-QIF coverage (counting_q) only when ALL hold: the fact is AI evidence, the
  relationship is Direct or Supporting, the fact is confirmed/corrected, and the tag was accepted (automatically
  or by a Super Admin) and never rejected.

Rule 4 -- fewer manual decisions, both reversible in the expert queue's Reviewed tab:
  - expert precedents (Precedents): a person's earlier decision on the same field (field key without years or
    numbers, any sprint) is applied again -- a confirmed indicator is accepted (or added when the AI did not
    suggest it), a rejected one is rejected; only human decisions count, never an automatic one;
  - AI second opinion (ai_check_pending): an AI tag still waiting is checked once more by the AI against the
    fact's own quote; it is accepted when the check agrees with AIQIF_AI_CHECK_MIN_CONFIDENCE, otherwise it
    keeps waiting, with the check's reason for the expert.

Expert queue (Super Admin): AI tags waiting for a decision, tags a Super Admin reopened or edited without deciding
(`pending_since`), and facts with kind_needs_check (possible AI evidence filed as context/profile, AI evidence
without any indicator, not classified yet). A decided tag leaves the queue but stays on the fact, with its history.

Tag review is separate from fact review: reviewing, editing or reopening a tag never changes the fact's value,
status or kind. Every tag decision, edit and reopen is a FactReviewHistory row holding the decision it replaced
(indicator, relationship, decision, reviewer, time, note), so no earlier decision is ever lost. It never blocks extraction,
review or the CRI; coverage is "provisional" while it is not empty, and a baseline cannot be decided until it is.
"""
import re

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.scoring.constants import AIQIF_INDICATORS

from .models import ExtractedFact, FactAIQIFMapping, FactReviewHistory

Kind = ExtractedFact.FactKind
Rel = FactAIQIFMapping.Relationship
Source = FactAIQIFMapping.Source
AutoDecision = FactAIQIFMapping.AutoDecision
Review = FactAIQIFMapping.ReviewStatus
COUNTING_RELATIONSHIPS = (Rel.DIRECT, Rel.SUPPORTING)
CONFIRMED_FACT = (ExtractedFact.Status.CONFIRMED, ExtractedFact.Status.CORRECTED)

#: Words that make a fact possibly AI evidence (whole words, any case; "AICTE" does not match "AI").
AI_TERMS = re.compile(
    r'\b(ai|a\.i\.|artificial[\s-]+intelligence|machine[\s-]+learning|deep[\s-]+learning|data[\s-]+science|'
    r'generative|gen[\s-]?ai|chat\s?gpt|llms?|large[\s-]+language[\s-]+models?|neural[\s-]+networks?|'
    r'computer[\s-]+vision|natural[\s-]+language[\s-]+processing|nlp)\b', re.IGNORECASE)
#: Field-name hints for classifying facts extracted before kinds existed (no AI call).
_PROFILE_KEY = re.compile(r'(institut\w*_type|type_of_institut|autonom|affiliat|ownership|establish|'
                          r'approval_bod|accreditation_status|naac_grade|programmes?_offered|courses?_offered)')
_NAAC_METRIC = re.compile(r'(?<![\d.])([1-7]\.\d{1,2}(?:\.\d{1,2}){0,2})(?![\d.])')
#: In running text only full metric numbers ("2.1.2"), so a CGPA or "1.5 lakh" is never taken for one.
_NAAC_METRIC_IN_TEXT = re.compile(r'(?<![\d.])([1-7]\.\d{1,2}\.\d{1,2})(?![\d.])')


def mentions_ai(*texts):
    return any(AI_TERMS.search(str(t or '').replace('_', ' ')) for t in texts)


def _fact_texts(fact):
    get = (lambda k: fact.get(k)) if isinstance(fact, dict) else (lambda k: getattr(fact, k, ''))
    return get('field_name'), get('field_key'), get('value'), get('source_snippet')


def guess_kind(fact):
    """A kind without asking the AI: AI terms -> AI evidence; profile-like field names -> profile; else context.
    Used when the AI gave no valid kind, and for facts extracted before kinds existed."""
    texts = _fact_texts(fact)
    if mentions_ai(*texts):
        return Kind.AI_EVIDENCE
    if _PROFILE_KEY.search(str(texts[1] or '').lower()):
        return Kind.PROFILE
    return Kind.CONTEXT


def normalize_metric(text):
    """'NAAC metric 2.1.2' / '2.1.2.' -> '2.1.2'; '' when it is not a NAAC metric number."""
    match = _NAAC_METRIC.search(str(text or ''))
    return match.group(1) if match else ''


def metrics_in(text):
    return {m.group(1) for m in _NAAC_METRIC_IN_TEXT.finditer(str(text or ''))}


def metric_in_text(metric, text):
    """True when `metric` is printed in `text` as a number of its own (not part of 12.1.25)."""
    return bool(metric) and re.search(rf'(?<![\d.]){re.escape(metric)}(?![\d])', str(text or '')) is not None


# -- the crosswalk ----------------------------------------------------------------------------------

def _relationship(text):
    """The crosswalk's wording -> ours. Conservative: anything mentioning Contextual is Contextual."""
    t = (text or '').lower()
    if 'contextual' in t:
        return Rel.CONTEXTUAL
    if 'direct' in t:
        return Rel.DIRECT
    return Rel.SUPPORTING


def crosswalk_rows():
    """[(indicator_code, [crosswalk link], version)] from the published release when it carries the crosswalk,
    else from the imported AI-QIF benchmarks."""
    from apps.benchmarks.models import Benchmark, BenchmarkReleaseItem
    from apps.benchmarks.services.releases import current_release

    release = current_release()
    if release is not None:
        rows = []
        for item in release.items.exclude(change_type=BenchmarkReleaseItem.ChangeType.RETIRED):
            snap = item.snapshot or {}
            if snap.get('benchmark_code') in AIQIF_INDICATORS and snap.get('naac_crosswalk'):
                rows.append((snap['benchmark_code'], snap['naac_crosswalk'], release.release_label))
        if rows:
            return rows
    qs = (Benchmark.objects.filter(benchmark_code__in=list(AIQIF_INDICATORS), framework__isnull=False)
          .exclude(status__in=[Benchmark.Status.WITHDRAWN, Benchmark.Status.SUPERSEDED]).exclude(naac_crosswalk=[]))
    return [(b.benchmark_code, b.naac_crosswalk, b.version_label) for b in qs]


class Crosswalk:
    """NAAC metric -> [(indicator_code, relationship, version)]."""

    def __init__(self, rows=None):
        self.by_metric, self.by_key_indicator = {}, {}
        for code, links, version in (crosswalk_rows() if rows is None else rows):
            for link in links or []:
                entry = (code, _relationship(link.get('relationship')), version)
                metric = normalize_metric(link.get('metric'))
                if metric:
                    self.by_metric.setdefault(metric, []).append(entry)
                ki = (link.get('naac_key_indicator') or '').strip()
                if ki:
                    self.by_key_indicator.setdefault(ki, []).append(entry)
        self.linked_codes = {code for entries in self.by_metric.values() for code, _r, _v in entries}

    @property
    def loaded(self):
        return bool(self.by_metric)

    def lookup(self, metric):
        """Links for '2.1.2' (also '2.1.2.1' -> '2.1.2', and a key indicator '2.1' -> all of its metrics)."""
        if not metric:
            return []
        parts = metric.split('.')
        if len(parts) > 3:
            metric = '.'.join(parts[:3])
        found = self.by_metric.get(metric) or (self.by_key_indicator.get(metric) if len(parts) == 2 else None) or []
        best = {}
        for code, rel, version in found:  # one row per indicator; the strongest relationship wins
            rank = {Rel.DIRECT: 0, Rel.SUPPORTING: 1, Rel.CONTEXTUAL: 2}[rel]
            if code not in best or rank < best[code][0]:
                best[code] = (rank, rel, version)
        return [(code, rel, version) for code, (_rank, rel, version) in sorted(best.items())]


# -- what counts, what waits -----------------------------------------------------------------------

def counting_q(prefix=''):
    """Q for FactAIQIFMapping rows that count toward coverage (rule 3). `prefix` for a related lookup."""
    p = prefix
    return (Q(**{f'{p}fact__fact_kind': Kind.AI_EVIDENCE, f'{p}fact__status__in': CONFIRMED_FACT,
                 f'{p}relationship__in': COUNTING_RELATIONSHIPS})
            & ~Q(**{f'{p}review_status': Review.REJECTED})
            & (Q(**{f'{p}review_status': Review.CONFIRMED}) | Q(**{f'{p}auto_accepted': True})))


def _accepted(m):
    return m.review_status == Review.CONFIRMED or (m.auto_accepted and m.review_status != Review.REJECTED)


def _queued(m, fact):
    if m.review_status != Review.UNREVIEWED:
        return False
    if m.pending_since:  # reopened / edited by a Super Admin: waits whatever its kind or relationship
        return True
    return (fact.fact_kind == Kind.AI_EVIDENCE and not m.auto_accepted and m.relationship != Rel.CONTEXTUAL
            and m.auto_decision != AutoDecision.REJECTED_PRECEDENT)


def queued_tags_q():
    automatic = (Q(fact__fact_kind=Kind.AI_EVIDENCE, auto_accepted=False) & ~Q(relationship=Rel.CONTEXTUAL)
                 & ~Q(auto_decision=AutoDecision.REJECTED_PRECEDENT))
    return (Q(review_status=Review.UNREVIEWED) & (automatic | Q(pending_since__isnull=False))
            & ~Q(fact__status=ExtractedFact.Status.REJECTED))


def count_reason(m, fact):
    """Whether the tag counts toward AI-QIF coverage now, and why not (rule 3) -- one short phrase."""
    if m.review_status == Review.REJECTED:
        return False, 'rejected by an expert'
    if m.review_status == Review.UNREVIEWED and m.auto_decision == AutoDecision.REJECTED_PRECEDENT and not m.pending_since:
        return False, 'rejected automatically: an expert rejected it for this field before'
    if m.review_status == Review.UNREVIEWED and (m.pending_since or not m.auto_accepted):
        return False, 'waiting for an expert decision'
    if m.relationship not in COUNTING_RELATIONSHIPS:
        return False, 'contextual link (never counts)'
    if fact.fact_kind != Kind.AI_EVIDENCE:
        return False, 'the fact is not AI evidence'
    if fact.status not in CONFIRMED_FACT:
        return False, 'the fact is not confirmed yet'
    return True, 'counts toward coverage'


def needs_expert_q():
    """Facts waiting for a Super Admin: flagged by the rules, or not classified yet (extracted before kinds
    existed -- `retag_aiqif_facts` classifies them). Rejected facts never wait."""
    return (Q(kind_needs_check=True) | Q(fact_kind='')) & ~Q(status=ExtractedFact.Status.REJECTED)


def queue_counts(sprint):
    tags = FactAIQIFMapping.objects.filter(queued_tags_q(), fact__sprint=sprint).count()
    facts = ExtractedFact.objects.filter(needs_expert_q(), sprint=sprint).count()
    return {'tags': tags, 'facts': facts, 'total': tags + facts}


def refresh_state(fact, save=True):
    """Recompute the fact's summary status and whether it needs a Super Admin, from its kind and tags."""
    S = ExtractedFact.AIQIFMappingStatus
    tags = list(fact.aiqif_mappings.all())
    counting = [m for m in tags if _accepted(m) and m.relationship in COUNTING_RELATIONSHIPS]
    queued = [m for m in tags if _queued(m, fact)]
    if not fact.fact_kind:
        status, check = S.PENDING, True
    elif fact.fact_kind == Kind.CONTEXT:
        status, check = S.CONTEXT, False
    elif fact.fact_kind == Kind.PROFILE:
        status, check = S.PROFILE, False
    else:
        status = S.MAPPED if counting else (S.NEEDS_REVIEW if queued else S.UNMAPPED)
        check = not counting and not queued  # AI evidence that covers nothing: a Super Admin adds the indicator
    if fact.fact_kind in (Kind.CONTEXT, Kind.PROFILE) and not fact.kind_reviewed_by_id:
        # Possibly AI evidence filed as context/profile: its text mentions AI, or the backfill saw a confident tag.
        check = mentions_ai(*_fact_texts(fact)) or any(n.get('kind') == 'check_kind' for n in fact.tagging_notes or [])
    if fact.status == ExtractedFact.Status.REJECTED:
        check = False
    fact.aiqif_mapping_status, fact.kind_needs_check = status, check
    if save:
        fact.save(update_fields=['aiqif_mapping_status', 'kind_needs_check', 'updated_at'])
    return fact


# -- tagging ----------------------------------------------------------------------------------------

def apply_tags(fact, ai_mappings, crosswalk=None, precedents=None):
    """Replace the automatic tags of `fact` per rule 2 (`ai_mappings`: the extractor's validated suggestions)
    and refresh its state. Tags a person reviewed or added are kept, and the new run's tag for that indicator
    is dropped."""
    crosswalk = crosswalk if crosswalk is not None else Crosswalk()
    (fact.aiqif_mappings.filter(review_status=Review.UNREVIEWED, pending_since__isnull=True)
     .exclude(source=Source.EXPERT).delete())
    kept = {m.indicator_code for m in fact.aiqif_mappings.all()}
    notes = [n for n in (fact.tagging_notes or []) if n.get('kind') != 'crosswalk_not_loaded']
    rows = []

    def add(code, **fields):
        if code in kept or code not in AIQIF_INDICATORS:
            return
        kept.add(code)
        rows.append(FactAIQIFMapping(fact=fact, indicator_code=code, criterion=AIQIF_INDICATORS[code][0], **fields))

    links = crosswalk.lookup(fact.naac_metric)
    is_evidence = fact.fact_kind == Kind.AI_EVIDENCE
    for code, rel, version in links:
        rel = rel if is_evidence else Rel.CONTEXTUAL
        add(code, relationship=rel, source=Source.CROSSWALK, auto_accepted=True, framework_version=version,
            confidence=1.0, status=FactAIQIFMapping.Status.MAPPED, auto_decision=AutoDecision.CROSSWALK,
            reason=f'NAAC {fact.naac_metric} is linked to {code} ({rel}) in the {version} NAAC -> AI-QIF crosswalk.')
    if is_evidence:
        threshold = settings.AIQIF_MAPPING_MIN_CONFIDENCE
        for m in ai_mappings or []:
            if links and m['indicator_code'] in crosswalk.linked_codes:
                continue  # the crosswalk decides the NAAC-linked indicators
            confident = m['confidence'] >= threshold
            accepted = confident and crosswalk.loaded and m['criterion'] == fact.pillar
            add(m['indicator_code'], relationship=Rel.SUPPORTING, source=Source.AI, confidence=m['confidence'],
                reason=m['reason'], status=(FactAIQIFMapping.Status.MAPPED if confident
                                            else FactAIQIFMapping.Status.NEEDS_REVIEW),
                auto_accepted=accepted, auto_decision=AutoDecision.RULES if accepted else '')
    elif ai_mappings:
        notes.append({'kind': 'ai_tags_not_used',
                      'detail': f'{len(ai_mappings)} AI tag(s) not used: a {fact.get_fact_kind_display().lower()} '
                                'fact is not AI evidence.'})
    if not crosswalk.loaded:
        notes.append({'kind': 'crosswalk_not_loaded',
                      'detail': 'The NAAC -> AI-QIF crosswalk is not loaded, so no tag was accepted automatically.'})
    FactAIQIFMapping.objects.bulk_create(rows)
    fact.tagging_notes = notes[-20:]
    fact.save(update_fields=['tagging_notes', 'updated_at'])
    if precedents is not None:
        apply_precedents(fact, precedents, refresh=False)
    return refresh_state(fact)


# -- rule 4: expert precedents --------------------------------------------------------------------

_YEARS = re.compile(r'(?:19|20)\d{2}(?:_?\d{2,4})?')


def precedent_key(field_key):
    """'mba_approved_intake_2024_25_course_2' -> 'mba_approved_intake_course': the field without years or numbers,
    so the same field of another year or sprint matches."""
    key = _YEARS.sub(' ', str(field_key or '').lower())
    return re.sub(r'[^a-z]+', '_', key).strip('_')


class Precedents:
    """Human decisions on AI-QIF tags, by precedent_key and indicator: the latest decision wins. Built once per
    extraction / backfill run. Only a person's confirm / reject (or a tag an expert added) counts -- never an
    automatic acceptance, so the rules never reinforce themselves."""

    def __init__(self, rows=None):
        from .auto_confirm import AUTO_CONFIRM_EMAIL
        if rows is None:
            rows = (FactAIQIFMapping.objects
                    .filter(review_status__in=[Review.CONFIRMED, Review.REJECTED], reviewed_by__isnull=False)
                    .exclude(reviewed_by__email=AUTO_CONFIRM_EMAIL)
                    .values_list('fact__field_key', 'fact_id', 'indicator_code', 'review_status', 'relationship',
                                 'reviewed_at'))
        self.by_key = {}
        for field_key, fact_id, code, decision, relationship, at in rows:
            key = precedent_key(field_key)
            if not key:
                continue
            current = self.by_key.setdefault(key, {}).get(code)
            if current is None or (at and (current['at'] is None or at > current['at'])):
                self.by_key[key][code] = {'decision': decision, 'relationship': relationship, 'at': at,
                                          'fact_id': str(fact_id), 'field_key': field_key}

    def lookup(self, fact):
        """{indicator: decision} for this fact's field, its own earlier decisions excluded."""
        return {code: d for code, d in self.by_key.get(precedent_key(fact.field_key), {}).items()
                if d['fact_id'] != str(fact.id)}


def _precedent_reason(d):
    when = d['at'].date().isoformat() if d['at'] else 'earlier'
    verb = 'confirmed' if d['decision'] == Review.CONFIRMED else 'rejected'
    return f'An expert {verb} this indicator for the field "{d["field_key"]}" ({when}).'


def apply_precedents(fact, precedents, refresh=True):
    """Rule 4a on the fact's undecided automatic tags. Returns how many tags it decided or added."""
    if fact.fact_kind != Kind.AI_EVIDENCE:
        return 0
    decisions = precedents.lookup(fact)
    if not decisions:
        return 0
    changed = 0
    tags = {m.indicator_code: m for m in fact.aiqif_mappings.all()}
    for code, d in decisions.items():
        m = tags.get(code)
        if m is None:
            if d['decision'] == Review.CONFIRMED and code in AIQIF_INDICATORS:
                FactAIQIFMapping.objects.create(
                    fact=fact, indicator_code=code, criterion=AIQIF_INDICATORS[code][0], relationship=d['relationship'],
                    source=Source.PRECEDENT, confidence=1.0, status=FactAIQIFMapping.Status.MAPPED, auto_accepted=True,
                    auto_decision=AutoDecision.PRECEDENT, auto_reason=_precedent_reason(d),
                    reason='Added from an earlier expert decision on the same field.')
                changed += 1
            continue
        if m.review_status != Review.UNREVIEWED or m.pending_since or m.source == Source.EXPERT:
            continue  # a person's decision / a reopened tag: never overridden
        if d['decision'] == Review.CONFIRMED and not (m.auto_accepted and m.relationship == d['relationship']):
            m.auto_accepted, m.relationship = True, d['relationship']
            m.auto_decision, m.auto_reason = AutoDecision.PRECEDENT, _precedent_reason(d)
        elif d['decision'] == Review.REJECTED and m.auto_decision != AutoDecision.REJECTED_PRECEDENT:
            m.auto_accepted = False
            m.auto_decision, m.auto_reason = AutoDecision.REJECTED_PRECEDENT, _precedent_reason(d)
        else:
            continue
        m.save(update_fields=['auto_accepted', 'relationship', 'auto_decision', 'auto_reason'])
        changed += 1
    if changed and refresh:
        refresh_state(fact)
    return changed


# -- rule 4: AI second opinion ----------------------------------------------------------------------

_CHECK_PROMPT = (
    'You check one proposed AI-QIF key-indicator tag on one fact extracted from an institution\'s document. '
    'Decide only from the fact and its quoted evidence, not from general knowledge. "supports" is true only when '
    'the quote is evidence about AI at the institution for exactly this indicator. relationship: direct (the quote '
    'is evidence for the indicator), supporting (it supports it partly), contextual (background only). confidence '
    '0-1 says how clearly the quote supports it. reason: one short sentence.')
_CHECK_SCHEMA = {
    'type': 'object',
    'properties': {
        'supports': {'type': 'boolean'},
        'relationship': {'type': 'string', 'enum': ['direct', 'supporting', 'contextual']},
        'confidence': {'type': 'number'},
        'reason': {'type': 'string'},
    },
    'required': ['supports', 'relationship', 'confidence', 'reason'],
    'additionalProperties': False,
}


def _checkable_q():
    """AI tags still waiting for an expert that have not had a second opinion yet."""
    return (queued_tags_q() & Q(source=Source.AI, pending_since__isnull=True)
            & ~Q(auto_reason__startswith='AI check'))


def ai_check_pending(facts, *, service=None, limit=None):
    """Rule 4b: one AI check per waiting AI tag of `facts` (at most `limit`). Accepted when the check supports the
    tag (Direct or Supporting) with at least AIQIF_AI_CHECK_MIN_CONFIDENCE; otherwise it keeps waiting, the check's
    reason noted for the expert. A failed AI call leaves the tag waiting. Returns {checked, accepted}."""
    from apps.extraction.exceptions import RecoverableExtractionError
    tags = list(FactAIQIFMapping.objects.filter(_checkable_q(), fact__in=facts).select_related('fact')
                .order_by('fact_id', '-confidence')[:limit or settings.AIQIF_AI_CHECK_MAX_PER_DOCUMENT])
    if not tags:
        return {'checked': 0, 'accepted': 0}
    if service is None:
        from apps.extraction.services.ai_service import get_ai_service
        service = get_ai_service()
    threshold = settings.AIQIF_AI_CHECK_MIN_CONFIDENCE
    checked = accepted = 0
    touched = {}
    for m in tags:
        fact = m.fact
        content = '\n'.join([
            f'Fact: {fact.field_name} ({fact.field_key}) = {fact.value!r}',
            f'Quote: "{fact.source_snippet}"',
            f'Proposed indicator: {m.indicator_code} {AIQIF_INDICATORS.get(m.indicator_code, ("", ""))[1]}',
            f'The AI that proposed it said: {m.reason}',
        ])
        try:
            answer = service.extract_structured_data(system_prompt=_CHECK_PROMPT, user_content=content,
                                                     response_schema=_CHECK_SCHEMA, schema_name='aiqif_tag_check')
        except RecoverableExtractionError:
            break  # rate limit / timeout: the rest keep waiting, checked another time
        except Exception as exc:  # an unusable answer: this tag keeps waiting
            import logging
            logging.getLogger(__name__).warning('aiqif.ai_check_failed tag=%s error=%s', m.id, exc)
            continue
        checked += 1
        supports = answer.get('supports') is True
        relationship = answer.get('relationship') if answer.get('relationship') in Rel.values else ''
        confidence = answer.get('confidence') if isinstance(answer.get('confidence'), (int, float)) else 0
        reason = str(answer.get('reason') or '')[:300]
        if supports and relationship in COUNTING_RELATIONSHIPS and confidence >= threshold:
            m.auto_accepted, m.relationship, m.auto_decision = True, relationship, AutoDecision.AI_CHECK
            m.auto_reason = f'AI check agreed ({round(confidence * 100)}%): {reason}'
            accepted += 1
        else:
            m.auto_reason = (f'AI check disagreed ({round(confidence * 100)}%, {relationship or "no relationship"}): '
                             f'{reason}')
        m.save(update_fields=['auto_accepted', 'relationship', 'auto_decision', 'auto_reason'])
        touched[fact.id] = fact
    for fact in touched.values():
        refresh_state(fact)
    return {'checked': checked, 'accepted': accepted}


def auto_check_sprint(sprint, *, ai=True):
    """Run rule 4 on a sprint's waiting tags now (the expert queue's "Decide automatically"): precedents, then the
    AI second opinion. Returns counts."""
    precedents = Precedents()
    facts = list(ExtractedFact.objects.filter(sprint=sprint, fact_kind=Kind.AI_EVIDENCE)
                 .exclude(status=ExtractedFact.Status.REJECTED).prefetch_related('aiqif_mappings'))
    by_precedent = sum(apply_precedents(f, precedents) for f in facts)
    result = {'precedent_decisions': by_precedent, 'checked': 0, 'accepted': 0}
    if ai and settings.AIQIF_AI_CHECK_ENABLED:
        from apps.extraction.models import AIUsage
        from apps.extraction.usage import usage_scope
        with usage_scope(sprint=sprint, stage=AIUsage.Stage.AIQIF_CHECK):
            result.update(ai_check_pending(facts, limit=500))
    return result


# -- Super Admin decisions --------------------------------------------------------------------------

class TaggingError(Exception):
    pass


def _history(fact, action, user, reason, new_value=None):
    FactReviewHistory.objects.create(fact=fact, action=action, original_value=fact.value, new_value=new_value,
                                     user=user, reason=reason)


def decision_snapshot(m):
    """The tag's current decision, as kept in history when it is replaced (never the fact's value)."""
    return {'indicator_code': m.indicator_code, 'relationship': m.relationship, 'source': m.source,
            'decision': m.review_status, 'auto_accepted': m.auto_accepted, 'auto_decision': m.auto_decision,
            'auto_reason': m.auto_reason,
            'reviewer': str(m.reviewed_by_id) if m.reviewed_by_id else None,
            'reviewer_name': (m.reviewed_by.get_full_name() or m.reviewed_by.email) if m.reviewed_by_id else '',
            'reviewed_at': m.reviewed_at.isoformat() if m.reviewed_at else None, 'note': m.review_note}


def _lock(mapping):
    # of=('self',): lock only the tag row. reviewed_by is nullable (an outer join), and PostgreSQL refuses
    # FOR UPDATE on the nullable side of an outer join -- a 500 on any tag nobody has reviewed yet. (SQLite, used
    # locally and in CI, ignores FOR UPDATE, so only PostgreSQL showed it.)
    return (FactAIQIFMapping.objects.select_for_update(of=('self',)).select_related('fact', 'reviewed_by')
            .get(pk=mapping.pk))


def _clear_pending(m):
    m.pending_since, m.pending_by, m.pending_reason = None, None, ''


def review_tag(mapping, user, decision, note=''):
    """Confirm or reject one tag (Super Admin). Ends a reopened / edited tag's wait. The fact is not touched."""
    with transaction.atomic():
        mapping = _lock(mapping)
        before = decision_snapshot(mapping)
        mapping.review_status = Review.CONFIRMED if decision == 'confirm' else Review.REJECTED
        mapping.reviewed_by, mapping.reviewed_at, mapping.review_note = user, timezone.now(), (note or '').strip()
        _clear_pending(mapping)
        mapping.save(update_fields=['review_status', 'reviewed_by', 'reviewed_at', 'review_note', 'pending_since',
                                    'pending_by', 'pending_reason'])
        _history(mapping.fact, FactReviewHistory.Action.AIQIF_TAG_REVIEWED, user,
                 f'{mapping.indicator_code} {mapping.get_review_status_display().lower()}. {note}'.strip(),
                 new_value={'indicator_code': mapping.indicator_code, 'relationship': mapping.relationship,
                            'decision': decision, 'previous': before})
        refresh_state(mapping.fact)
    return mapping


def reopen_tag(mapping, user, reason):
    """Send a decided tag back to the expert queue (Super Admin). Its decision so far is kept in the history row;
    the tag stops counting until it is decided again. The fact is not touched."""
    reason = (reason or '').strip()
    if not reason:
        raise TaggingError('Give a reason for reopening the review.')
    with transaction.atomic():
        mapping = _lock(mapping)
        if mapping.review_status == Review.UNREVIEWED and mapping.pending_since:
            raise TaggingError('This tag is already waiting for an expert decision.')
        before = decision_snapshot(mapping)
        mapping.review_status, mapping.auto_accepted = Review.UNREVIEWED, False
        mapping.auto_decision, mapping.auto_reason = '', ''  # kept in the history row's `previous`
        mapping.reviewed_by, mapping.reviewed_at, mapping.review_note = None, None, ''
        mapping.pending_since, mapping.pending_by, mapping.pending_reason = timezone.now(), user, reason
        mapping.save(update_fields=['review_status', 'auto_accepted', 'auto_decision', 'auto_reason', 'reviewed_by',
                                    'reviewed_at', 'review_note', 'pending_since', 'pending_by', 'pending_reason'])
        _history(mapping.fact, FactReviewHistory.Action.AIQIF_TAG_REOPENED, user,
                 f'{mapping.indicator_code} review reopened: {reason}',
                 new_value={'indicator_code': mapping.indicator_code, 'previous': before})
        refresh_state(mapping.fact)
    return mapping


def edit_tag(mapping, user, *, indicator_code=None, relationship=None, note='', decision=None):
    """Change a tag's indicator, relationship or note (Super Admin). A new indicator or relationship is a new
    mapping: the earlier approval is never carried over -- it waits for a decision unless `decision`
    ('confirm' / 'reject') is given in the same request, which is recorded as this expert's own decision.
    A note-only edit keeps the decision. The fact is not touched."""
    code = (indicator_code or mapping.indicator_code).strip().upper()
    if code and not code.startswith('AIQIF-'):
        code = f'AIQIF-{code}'
    if code not in AIQIF_INDICATORS:
        raise TaggingError(f'{indicator_code!r} is not an AI-QIF key indicator.')
    relationship = relationship or mapping.relationship
    if relationship not in Rel.values:
        raise TaggingError(f'relationship must be one of {Rel.values}.')
    if decision not in (None, '', 'confirm', 'reject'):
        raise TaggingError("decision must be 'confirm' or 'reject'.")
    note = (note or '').strip()
    with transaction.atomic():
        mapping = _lock(mapping)
        if code != mapping.indicator_code and FactAIQIFMapping.objects.filter(
                fact_id=mapping.fact_id, indicator_code=code).exists():
            raise TaggingError(f'This fact already has a tag for {code}; edit or reopen that one instead.')
        changed = code != mapping.indicator_code or relationship != mapping.relationship
        if not changed and not note and not decision:
            raise TaggingError('Nothing to change.')
        before = decision_snapshot(mapping)
        mapping.indicator_code, mapping.criterion, mapping.relationship = code, AIQIF_INDICATORS[code][0], relationship
        fields = ['indicator_code', 'criterion', 'relationship', 'review_note']
        if changed:
            # A different mapping now: no earlier approval (a person's or the rules') carries over.
            mapping.source, mapping.auto_accepted, mapping.confidence = Source.EXPERT, False, 1.0
            mapping.auto_decision, mapping.auto_reason = '', ''
            mapping.review_status, mapping.reviewed_by, mapping.reviewed_at = Review.UNREVIEWED, None, None
            mapping.pending_since, mapping.pending_by, mapping.pending_reason = timezone.now(), user, note or 'Edited.'
            mapping.reason = note or f'Edited by an expert from {before["indicator_code"]} ({before["relationship"]}).'
            fields += ['source', 'auto_accepted', 'auto_decision', 'auto_reason', 'confidence', 'review_status', 'reviewed_by', 'reviewed_at',
                       'pending_since', 'pending_by', 'pending_reason', 'reason']
        mapping.review_note = note if note else ('' if changed else mapping.review_note)
        mapping.save(update_fields=fields)
        _history(mapping.fact, FactReviewHistory.Action.AIQIF_TAG_EDITED, user,
                 f'{before["indicator_code"]} ({before["relationship"]}) -> {code} ({relationship}). {note}'.strip(),
                 new_value={'indicator_code': code, 'relationship': relationship, 'previous': before,
                            'decision_carried_over': not changed})
        refresh_state(mapping.fact)
    if decision:
        mapping = review_tag(mapping, user, decision, note)
    return mapping


def add_tag(fact, user, indicator_code, relationship=Rel.SUPPORTING, note=''):
    code = (indicator_code or '').strip().upper()
    if code and not code.startswith('AIQIF-'):
        code = f'AIQIF-{code}'
    if code not in AIQIF_INDICATORS:
        raise TaggingError(f'{indicator_code!r} is not an AI-QIF key indicator.')
    if relationship not in Rel.values:
        raise TaggingError(f'relationship must be one of {Rel.values}.')
    with transaction.atomic():
        mapping, _created = FactAIQIFMapping.objects.update_or_create(fact=fact, indicator_code=code, defaults={
            'criterion': AIQIF_INDICATORS[code][0], 'relationship': relationship, 'source': Source.EXPERT,
            'confidence': 1.0, 'status': FactAIQIFMapping.Status.MAPPED, 'auto_accepted': False,
            'reason': (note or '').strip() or 'Added by an expert.', 'review_status': Review.CONFIRMED,
            'reviewed_by': user, 'reviewed_at': timezone.now(), 'review_note': (note or '').strip(),
            'pending_since': None, 'pending_by': None, 'pending_reason': ''})
        _history(fact, FactReviewHistory.Action.AIQIF_TAG_ADDED, user, f'{code} ({relationship}) added. {note}'.strip(),
                 new_value={'indicator_code': code, 'relationship': relationship})
        refresh_state(fact)
    return mapping


def decide_kind(fact, user, kind, note=''):
    if kind not in Kind.values:
        raise TaggingError(f'fact_kind must be one of {Kind.values}.')
    with transaction.atomic():
        before = fact.fact_kind
        fact.fact_kind, fact.kind_reviewed_by, fact.kind_reviewed_at = kind, user, timezone.now()
        fact.save(update_fields=['fact_kind', 'kind_reviewed_by', 'kind_reviewed_at', 'updated_at'])
        _history(fact, FactReviewHistory.Action.FACT_KIND_CHANGED, user,
                 f'Kind: {before or "not classified"} -> {kind}. {note}'.strip(), new_value={'from': before, 'to': kind})
        refresh_state(fact)
    return fact
