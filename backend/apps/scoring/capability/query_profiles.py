"""Versioned retrieval descriptions; never scoring criteria or institutional facts."""
import hashlib
import json
from functools import lru_cache
from pathlib import Path

VERSION = 'evidence-record-profiles-1'


def validate_profiles(pack, rubric):
    expected = {c['id']: c['text'] for i in rubric['indicators'] for c in i['conditions']}
    profiles = pack.get('profiles')
    if pack.get('version') != VERSION or not isinstance(profiles, dict) or set(profiles) != set(expected):
        raise ValueError('Retrieval profiles must cover the current rubric exactly.')
    queries = set()
    for cid, assertion in expected.items():
        profile = profiles[cid]
        if (not isinstance(profile, dict) or profile.get('assertion') != assertion
                or not isinstance(profile.get('query'), str) or not 30 <= len(profile['query']) <= 700
                or profile['query'].strip() != profile['query'] or '\n' in profile['query']):
            raise ValueError('Retrieval profile assertion or query is invalid: ' + cid)
        if profile['query'] in queries:
            raise ValueError('Each retrieval profile needs its own evidence description.')
        queries.add(profile['query'])
    return profiles


@lru_cache(maxsize=1)
def _load():
    from .engine import release
    raw = Path(__file__).with_name('retrieval_profiles_v1.json').read_bytes()
    pack = json.loads(raw)
    profiles = validate_profiles(pack, release())
    return profiles, hashlib.sha256(raw).hexdigest()


def profile_metadata():
    return {'query_profiles_version': VERSION, 'query_profiles_hash': _load()[1]}


def evidence_query(condition):
    cid = condition.get('id', '')
    # Synthetic/custom indicators retain the generic assertion path. Canonical IDs
    # must match the versioned profile; no stale or unprofiled requirement is guessed.
    if not cid.startswith('AIQIF-'):
        return ''
    if 'evidence_parts' in condition:
        from .requirement_evidence import pilot_specs
        spec = pilot_specs().get(cid)
        if spec and all(condition.get(key) == value for key, value in spec.items()):
            return ' '.join(spec['evidence_parts'].values())
    profile = _load()[0].get(cid)
    if profile is None or profile['assertion'] != condition['text']:
        raise ValueError('Requirement differs from its retrieval profile: ' + cid)
    return profile['query']
