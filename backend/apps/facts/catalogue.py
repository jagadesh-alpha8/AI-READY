"""Reviewed concept aliases, not an automatically expanding ontology or a fact quota.

Keep the model's field key for provenance. Exact aliases supply a canonical type;
unrecognised keys remain additional observations until a reviewed catalogue release.
Identity includes scope AND value, so contradictory observations never compete on
model confidence. Missing scope remains unknown; page identity prevents unsafe merges.
"""
import hashlib
import json
import re

VERSION = 'institution-facts-0.1'
TYPES = {
    'faculty_count': ('total_faculty', 'total_faculty_count', 'number_of_faculty', 'faculty_strength'),
    'student_count': ('total_students', 'student_enrolment', 'student_enrollment', 'student_strength'),
    'ai_certified_faculty_count': ('ai_certified_faculty', 'number_of_ai_certified_faculty'),
    'ai_course_count': ('number_of_ai_courses', 'total_ai_courses'),
    'ai_lab_count': ('number_of_ai_labs', 'total_ai_labs'),
    'placement_rate': ('placement_percentage', 'student_placement_rate'),
    'research_publication_count': ('total_publications', 'publication_count'),
    'ai_policy': ('institutional_ai_policy',),
}
ALIASES = {alias: key for key, values in TYPES.items() for alias in (key, *values)}


def normalize_key(key):
    return re.sub(r'[^a-z0-9]+', '_', str(key).lower()).strip('_')


def canonical_type(key):
    return ALIASES.get(normalize_key(key), '')


def matching_keys(key):
    concept = canonical_type(key)
    return (concept, *TYPES[concept]) if concept else (key,)


def _get(observation, key, default=None):
    return observation.get(key, default) if isinstance(observation, dict) else getattr(observation, key, default)


def identity(observation, *, include_value=True):
    key = _get(observation, 'field_key', '')
    scope = _get(observation, 'scope', {}) or {}
    def normalized(value):
        if isinstance(value, list):
            return sorted(normalized(v) for v in value)
        if isinstance(value, dict):
            return {k: normalized(v) for k, v in value.items()}
        return ' '.join(str(value or '').lower().split())
    scoped = {k: normalized(scope.get(k)) for k in ('period', 'population', 'unit', 'includes', 'excludes')}
    # Do not equate unscoped figures on different pages. Never infer a period/population.
    page = str(_get(observation, 'source_page', '')) if not scoped['period'] or not scoped['population'] else ''
    value = _get(observation, 'normalized_value')
    if value is None:
        value = _get(observation, 'value')
    payload = [canonical_type(key) or normalize_key(key), scoped,
               _get(observation, 'data_type', 'string') or 'string', value if include_value else None, page]
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def extraction_guidance():
    return ('\nCanonical fact vocabulary (' + VERSION + '): ' + ', '.join(TYPES) + '. '
            'Use these exact field keys only when their meaning fits. Other supported observations are allowed. '
            'There is no required number of facts. Keep different periods, populations, units and contradictory '
            'values as separate observations with their own scope and citations. Do not fill missing types.\n')
