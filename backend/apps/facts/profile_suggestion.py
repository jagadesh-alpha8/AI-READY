"""The institution's benchmark profile, pre-filled from its profile facts (fact_kind = profile).

    match_code(fact)              the closed-list code a profile fact's value names, or '' (no guessing)
    suggestion(sprint)            what the documents say for each profile field, with conflicts and options
    confirm(sprint, user, data)   save the profile the client confirmed (assessments.services.save_profile)

The profile decides which AI-QIF indicators apply (scoring/services/coverage.py). Values are matched only
against the closed lists (institution types, autonomous statuses, approval bodies, programme types); a value
that matches none is shown for the client to pick, never guessed. Nothing is saved until someone confirms.
"""
import re

from apps.benchmarks.models import APPROVAL_BODIES, AUTONOMOUS_STATUSES, InstitutionType, ProgrammeType

from .models import ExtractedFact

Field = ExtractedFact.ProfileField

#: Words that name an autonomous status in a document.
_STATUS_WORDS = {'autonomous': 'autonomous', 'affiliated': 'affiliated', 'constituent': 'constituent',
                 'deemed': 'university', 'university': 'university', 'standalone': 'standalone',
                 'state board': 'standalone'}
_STATUS_PRECEDENCE = ('autonomous', 'constituent', 'affiliated', 'standalone', 'university')


def _norm(text):
    return re.sub(r'[^a-z0-9]+', ' ', str(text or '').lower()).strip()


def _words(text):
    return set(_norm(text).split())


def _match_named(value, options):
    """`options`: [(code, name)]. The one option whose code, name, or a name part in brackets / after '/' is
    named in `value` (whole words); '' when none or more than one matches."""
    words, text = _words(value), f' {_norm(value)} '
    hits = set()
    for code, name in options:
        parts = {_norm(code.replace('_', ' ')), _norm(name)}
        parts |= {_norm(p) for p in re.split(r'[()/,]', name) if len(_norm(p)) > 1}
        parts.discard('')
        if any((f' {p} ' in text) if ' ' in p else (p in words) for p in parts):
            hits.add(code)
    return hits.pop() if len(hits) == 1 else ''


def match_code(fact):
    value = f'{fact.value} {fact.field_name}' if fact.profile_field != Field.PROGRAMME else str(fact.value)
    if fact.profile_field == Field.INSTITUTION_TYPE:
        return _match_named(value, list(InstitutionType.objects.values_list('code', 'name')))
    if fact.profile_field == Field.PROGRAMME:
        return _match_named(value, list(ProgrammeType.objects.values_list('code', 'name')))
    if fact.profile_field == Field.AUTONOMOUS_STATUS:
        text = f' {_norm(fact.value)} '
        found = {code for word, code in _STATUS_WORDS.items() if f' {word} ' in text}
        # "Autonomous college affiliated to Anna University": the college's own status wins -- the affiliating
        # university's name never makes it a university, and an autonomous college is still affiliated.
        for code in _STATUS_PRECEDENCE:
            if code in found:
                return code
        return ''
    if fact.profile_field == Field.APPROVAL_BODY:
        found = [b for b in APPROVAL_BODIES if f' {_norm(b)} ' in f' {_norm(fact.value)} ']
        return found[0] if len(found) == 1 else ''
    return ''


def programme_names(value):
    """A programme fact's value as programme names. Extraction sometimes stores several programmes as one value --
    a list, or text that looks like one ("['B.E. CSE', 'MBA']") -- which is split into its names."""
    import ast
    import json
    items = value
    if isinstance(value, str) and value.strip().startswith('[') and value.strip().endswith(']'):
        for parse in (json.loads, ast.literal_eval):
            try:
                items = parse(value.strip())
                break
            except (ValueError, SyntaxError, TypeError):
                continue
    if not isinstance(items, (list, tuple)):
        items = [items]
    names = [' '.join(str(x).split())[:200] for x in items if x is not None and str(x).strip()]
    return list(dict.fromkeys(names))


def _ref(fact):
    return {'fact_id': str(fact.id), 'value': fact.value, 'field_name': fact.field_name,
            'document': fact.document.original_filename if fact.document_id else '', 'page': fact.source_page}


def suggestion(sprint):
    facts = list(ExtractedFact.objects.filter(sprint=sprint, fact_kind=ExtractedFact.FactKind.PROFILE)
                 .exclude(status=ExtractedFact.Status.REJECTED).select_related('document'))
    by_field = {}
    unmatched = []
    for fact in facts:
        if fact.profile_field in ('', Field.OTHER):
            continue
        if not fact.profile_code:
            unmatched.append({**_ref(fact), 'profile_field': fact.profile_field})
            continue
        by_field.setdefault(fact.profile_field, {}).setdefault(fact.profile_code, []).append(_ref(fact))

    def single(field):
        candidates = by_field.get(field, {})
        codes = sorted(candidates)
        return {'value': codes[0] if len(codes) == 1 else '', 'conflict': len(codes) > 1,
                'candidates': [{'code': c, 'sources': candidates[c]} for c in codes]}

    programmes = {}
    for fact in facts:
        if fact.profile_field == Field.PROGRAMME and fact.profile_code:
            for name in programme_names(fact.value):
                programmes.setdefault(name.lower(), {'name': name, 'programme_type': fact.profile_code,
                                                     'approval_body': '', 'sources': []})['sources'].append(_ref(fact))
    institution = sprint.institution
    current = None
    if hasattr(institution, 'benchmark_profile'):
        p = institution.benchmark_profile
        current = {'institution_type': p.institution_type.code, 'autonomous_status': p.autonomous_status,
                   'approval_bodies': p.approval_bodies,
                   'programmes': [{'name': x.name, 'programme_type': x.programme_type.code,
                                   'approval_body': x.approval_body}
                                  for x in institution.benchmark_programmes.select_related('programme_type')]}
    return {
        'institution': str(institution.pk), 'institution_name': institution.name, 'current': current,
        'suggested': {
            'institution_type': single(Field.INSTITUTION_TYPE),
            'autonomous_status': single(Field.AUTONOMOUS_STATUS),
            'approval_bodies': sorted(by_field.get(Field.APPROVAL_BODY, {})),
            'programmes': sorted(programmes.values(), key=lambda p: p['name'].lower()),
        },
        'unmatched': unmatched,
        'options': {
            'institution_types': [{'code': c, 'name': n} for c, n in InstitutionType.objects.values_list('code', 'name')],
            'autonomous_statuses': [{'code': c, 'name': n} for c, n in AUTONOMOUS_STATUSES],
            'approval_bodies': APPROVAL_BODIES,
            'programme_types': [{'code': c, 'name': n} for c, n in ProgrammeType.objects.values_list('code', 'name')],
        },
    }


def confirm(sprint, user, data):
    """Save the profile as confirmed (validated by save_profile) and recalculate the CRI, so which indicators
    apply -- and so coverage -- follows the confirmed profile."""
    from apps.assessments.services import save_profile
    from apps.scoring.services import run_scoring_engine

    profile = save_profile(sprint.institution, user, data)
    run_scoring_engine(sprint, triggered_by=user)
    return profile
