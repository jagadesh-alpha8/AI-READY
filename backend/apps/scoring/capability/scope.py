"""Versioned, conservative scope resolution at explicit assessment start only.

The page adapter inventories explicit declarations, not inferred universal coverage.
Dates remain verbatim and typed; filenames and upload times never establish currency.
"""
import re

VERSION = 'source-local-scope-0.5'
DEFAULT_POPULATION = 'Institutional overview; coverage established separately for each finding'
DEFAULT_PERIOD = 'Source-specific evidence periods; currency not presumed'
PATTERNS = {
    'population': r'(?im)^[ \t]*(?:population|cohort|programme|program|beneficiaries)[ \t]*:[ \t]*([^\r\n]{1,250})',
    'activity_period': r'(?im)^[ \t]*(?:activity period|academic year|reporting period)[ \t]*:[ \t]*([^\r\n]{1,150})',
    'policy_interval': r'(?im)^[ \t]*(?:policy effective|effective from|effective period)[ \t]*:[ \t]*([^\r\n]{1,150})',
    'curriculum_regulation': r'(?im)^[ \t]*(?:curriculum regulation|regulation year)[ \t]*:[ \t]*([^\r\n]{1,150})',
    'report_claim_date': r'(?im)^[ \t]*(?:report generated(?: on)?|publication date|report date)[ \t]*:[ \t]*([^\r\n]{1,150})',
    'institution_identity': r'(?im)^[ \t]*(?:(?:institution name|name of (?:the )?institution)[ \t]*:[ \t]*|self[ \t]+study[ \t]+report[ \t]+of[ \t]+)([^\r\n]{1,250})',
}


def intent(population=None, reference_period=None, scope_mode=None, refines_run_id=None, confirmed_source_institution=None):
    """Normalize legacy explicit inputs without changing their historical request digest."""
    population = population.strip() if isinstance(population, str) else ''
    reference_period = reference_period.strip() if isinstance(reference_period, str) else ''
    mode = scope_mode or ('custom' if population or reference_period else 'default')
    if mode not in {'default', 'custom'}:
        raise ValueError('Choose default or custom scope.')
    if mode == 'custom' and (not population or not reference_period):
        raise ValueError('Custom scope needs both a population and reference period.')
    if mode == 'default' and (population or reference_period):
        raise ValueError('Default scope does not accept population or reference period overrides.')
    if len(population) > 2000 or len(reference_period) > 200:
        raise ValueError('Scope input is too long.')
    value = {'population': population, 'reference_period': reference_period}
    if mode == 'default':
        value = {'scope_mode': 'default'}
    if refines_run_id:
        value['refines_run_id'] = str(refines_run_id)
    if confirmed_source_institution is not None:
        if not isinstance(confirmed_source_institution, str) or not confirmed_source_institution.strip() or len(confirmed_source_institution) > 250:
            raise ValueError('Choose an explicit source institution to confirm.')
        value['confirmed_source_institution'] = confirmed_source_institution.strip()
    return mode, value


def _declarations(source):
    for kind, pattern in PATTERNS.items():
        for match in re.finditer(pattern, source['text']):
            if match.group(1).strip():
                yield {'kind': kind, 'value': match.group(1).strip(), 'source_id': source['id'],
                       'start': match.start(1), 'end': match.end(1), 'quote': match.group(1),
                       'interpretation': 'explicit_label_candidate_unverified'}
    yield from report_timestamps(source)


SSR_FOOTER = re.compile(
    r'(?im)^[ \t]*Page[ \t]+\d+[ \t]*/[ \t]*\d+[ \t]*(?:\r?\n[ \t]*)?'
    r'(\d{2}-\d{2}-\d{4} \d{2}:\d{2}:\d{2})[ \t]*$'
)


def report_timestamps(source):
    text = source['text']
    if re.search(r'(?i)self\s+study\s+report\s+of', text):
        for match in SSR_FOOTER.finditer(text):
            yield {'kind': 'report_claim_date', 'value': match[1], 'source_id': source['id'],
                   'start': match.start(1), 'end': match.end(1), 'quote': match[1],
                   'interpretation': 'report_timestamp_only_not_activity_or_current_operation'}


def resolve(*, profile, sources, requested, mode):
    declarations = [declaration for source in sources for declaration in _declarations(source)]
    questions = []
    identity = [d for d in declarations if d['kind'] == 'institution_identity']
    normalize = lambda name: ' '.join(re.findall(r'\w+', name.casefold()))
    mismatches = [d for d in identity if normalize(d['value']) != normalize(profile['name'])]
    confirmed = requested.get('confirmed_source_institution')
    if confirmed and normalize(confirmed) not in {normalize(d['value']) for d in identity}:
        raise ValueError('Confirmed institution must match a name declared in the current source documents.')
    if confirmed:
        questions.append({'code': 'source_identity_confirmed', 'severity': 'limitation',
            'message': f'The user confirmed that this assessment concerns the source institution: {confirmed}. The saved profile name is unchanged.',
            'source_ids': sorted({d['source_id'] for d in identity if normalize(d['value']) == normalize(confirmed)})})
    if mismatches and not confirmed:
        questions.append({'code': 'institution_identity_mismatch', 'severity': 'review',
            'message': 'A labelled source institution differs from the saved profile. Confirm ownership before relying on it.',
            'source_ids': sorted({d['source_id'] for d in mismatches})})
    if not identity:
        questions.append({'code': 'institution_identity_unconfirmed', 'severity': 'review',
            'message': 'Source institution identity is not confirmed by this conservative adapter.', 'source_ids': []})
    periods = {d['value'] for d in declarations if d['kind'] == 'activity_period'}
    questions.append({'code': 'finding_scope_and_currency_required', 'severity': 'limitation',
        'message': 'Each finding must establish its own beneficiaries and applicable dates. Source mentions do not establish universal coverage or present operation.',
        'source_ids': []})
    default = mode == 'default'
    return {'version': VERSION, 'mode': mode, 'requested_intent': requested,
        'institution': {'name': profile['name'], 'basis': 'explicit_user_identity_confirmation' if confirmed else 'saved_profile_not_source_verified',
                        'assessed_name': confirmed or profile['name'],
                        'identity_status': 'user_confirmed_for_this_run' if confirmed else 'mismatch_requires_review' if mismatches else 'source_label_matches_profile_unverified' if identity else 'unconfirmed'},
        'population_label': DEFAULT_POPULATION if default else requested['population'],
        'period_label': ('Mixed source periods; no common reporting year established' if len(periods) > 1
                         else DEFAULT_PERIOD) if default else requested['reference_period'],
        'coverage_policy': 'source_specific_no_universal_or_current_inference',
        'rubric_scope_policy': 'original_requirement_scope_unchanged_even_for_custom_cohort',
        'source_declarations': declarations, 'questions': questions,
        'source_ids': [s['id'] for s in sources],
        'user_override': None if default else {'population': requested['population'], 'reference_period': requested['reference_period']},
        'limitations': 'Conservative explicit-label inventory, not a complete semantic extraction or reviewed-fact adapter. Dates are verbatim source claims, not validated currency.'}


def context_scope(scope, sources):
    """Project frozen declarations onto exact spans of the supplied evidence text."""
    if scope is None:
        return None
    def key(declaration):
        return (declaration['source_id'], declaration['kind'], ' '.join(declaration['value'].split()))

    frozen = {key(declaration) for declaration in scope['source_declarations']}
    selected = {}
    for source in sources:
        offset = source.get('text_offset', 0)
        declarations = list(_declarations(source))
        if source.get('evidence_role') == 'report_timestamp':
            declarations.append({'kind': 'report_claim_date', 'value': source['text'], 'quote': source['text'],
                                 'source_id': source['id'], 'start': 0, 'end': len(source['text']),
                                 'interpretation': 'report_timestamp_only_not_activity_or_current_operation'})
        for declaration in declarations:
            if key(declaration) in frozen:
                declaration['start'] += offset
                declaration['end'] += offset
                selected.setdefault((key(declaration), declaration['start']), declaration)
    return {**{k: scope[k] for k in ('version', 'mode', 'institution', 'population_label', 'period_label',
                                    'coverage_policy', 'rubric_scope_policy', 'limitations')},
            'questions': [{k: q[k] for k in ('code', 'message')} for q in scope['questions']],
            'source_declarations': list(selected.values())[:100],
            'declarations_are_subset': True}
