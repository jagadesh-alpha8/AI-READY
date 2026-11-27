"""The standard version a result was scored under (past cases design, "Versions and fairness"; build-order step 4).

One plain name per result ("AI-READY Standard 1.0 (November 2026)") for everything that can move a score: the rubric
and part wording, the prompts, the credit rule and tie-break, the model, the follow-up rubric, the depth reserve,
the three re-judge settings, whether the check after judging is on, the past-case release and lookup, and the
extraction and evidence-map versions. Each new run freezes the name and the bundle behind it (inputs.standard).

The name is a setting (AI_READY_STANDARD_NAME), so it can be changed without code. The name and the wording are
open decision 2 (Harsha or Vijay): until they settle it, the placeholder below is used and marked pending.
The plain list of what changed between versions is a JSON file (AI_READY_STANDARD_CHANGES_FILE, default
standard_changes.json beside this module), newest last.
"""
import hashlib
import json
from pathlib import Path

from django.conf import settings

PLACEHOLDER = 'AI-READY Standard 1.0 (November 2026)'
CHANGES_FILE = Path(__file__).with_name('standard_changes.json')
OLDER = ('Scored under {old}. We have since updated how we score: see what changed in {new}. Your next assessment '
         'will use the current standard, so some results may differ even where your documents have not changed.')
UNNAMED = ('Scored before we named our scoring standard. We have since updated how we score: see what changed in '
           '{new}. Your next assessment will use the current standard, so some results may differ even where your '
           'documents have not changed.')


def name():
    return (getattr(settings, 'AI_READY_STANDARD_NAME', '') or PLACEHOLDER).strip()


def pending():
    """True while the name is the placeholder awaiting Harsha's or Vijay's wording."""
    return bool(getattr(settings, 'AI_READY_STANDARD_PENDING', True))


def changes():
    """[{'name', 'changes': [plain line]}], oldest first."""
    path = Path(getattr(settings, 'AI_READY_STANDARD_CHANGES_FILE', '') or CHANGES_FILE)
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return []


def bundle():
    """Everything a new run would be scored under, by version."""
    from apps.evidence_map import spec as map_spec
    from . import compact, depth_spec, part_judgment, reserve
    from .engine import ENGINE_VERSION, release
    from .model_choice import effort, scoring_model
    from .past_cases import current_release
    rubric = release()
    meta = part_judgment.metadata()
    return {'rubric': rubric.get('version'), 'rubric_hash': rubric.get('content_hash'), 'engine': ENGINE_VERSION,
            'parts_version': meta['parts_version'], 'parts_hash': meta['parts_hash'],
            'parts_prompt_hash': meta['parts_prompt_hash'], 'credit_rule': meta['credit_rule'],
            'tie_break': part_judgment.TIE_BREAK_RULE, 'model': scoring_model() or '', 'effort': effort(),
            'follow_up_rubric': getattr(depth_spec, 'VERSION', None) or getattr(depth_spec, 'RUBRIC', None),
            'depth_reserve': reserve.VERSION, 'rejudge': compact.current_settings(), 'check_after_judging': 'off',
            'past_case_release': current_release(), 'lookup': None, 'evidence_map': map_spec.SPEC_VERSION}


def frozen():
    """What a new run freezes: the name, the bundle and its hash."""
    values = bundle()
    return {'name': name(), 'pending': pending(), 'bundle': values,
            'bundle_hash': hashlib.sha256(json.dumps(values, sort_keys=True, default=str).encode()).hexdigest()}


def for_run(inputs):
    """{'name', 'current', 'older', 'line', 'changes'} for a result page or report. older: a newer standard exists
    than the one this result was scored under; `line` then says so (it names versions and changes, never another
    college). A run from before standards were named is older by definition."""
    current = name()
    mine = ((inputs or {}).get('standard') or {}).get('name')
    older = mine != current
    listed = {row.get('name'): row.get('changes') or [] for row in changes()}
    return {'name': mine, 'current': current, 'older': older, 'pending': pending(),
            'line': (OLDER.format(old=mine, new=current) if mine else UNNAMED.format(new=current)) if older else None,
            'changes': listed.get(current, [])}
