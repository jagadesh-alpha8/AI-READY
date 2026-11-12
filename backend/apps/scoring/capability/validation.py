"""Offline evaluation: numerical replay, condition accuracy and cold-run agreement are distinct."""
from collections import Counter

from .engine import STATES, assess


def decisions_from(records, rubric, *, require_full=True):
    expected = {c['id'] for i in rubric['indicators'] for c in i['conditions']}
    if not isinstance(records, list):
        raise ValueError('Expected a list of condition records.')
    states = {}
    for record in records:
        cid, state = record.get('condition_id'), record.get('state')
        if cid not in expected or cid in states or state not in STATES:
            raise ValueError('Unknown, duplicated or invalid condition decision.')
        states[cid] = state
    if require_full and set(states) != expected:
        raise ValueError('Evaluation requires all 216 decisions.')
    if not states:
        raise ValueError('No human-labelled conditions supplied.')
    return states


def compare_export(export, *, rubric, gold=None, repeat=None):
    assessment = export['assessment']
    rows = assessment['records']
    predicted = decisions_from(rows, rubric)
    replay = assess(predicted, rubric)
    # Compare every deterministic result field, not only its headline number.
    report = {'condition_count': len(predicted), 'numerical_replay_matches': replay == assessment['result'],
              'prediction_states': dict(Counter(predicted.values())),
              'accuracy': None, 'cold_run_agreement': None,
              'note': 'Replay is not semantic accuracy. Human labels and repeated independent runs must use the same frozen inputs and rubric.'}
    if gold is not None:
        if gold.get('inputs_hash') != export['inputs_hash'] or gold.get('rubric_hash') != replay['rubric_hash']:
            raise ValueError('Human labels must identify the exact frozen inputs and rubric hash.')
        truth = decisions_from(gold['records'], rubric, require_full=False)
        matrix = {s: {p: 0 for p in sorted(STATES)} for s in sorted(STATES)}
        for cid, state in truth.items():
            matrix[state][predicted[cid]] += 1
        report['accuracy'] = {'labelled_conditions': len(truth), 'total_conditions': len(predicted),
            'label_coverage': len(truth) / len(predicted),
            'exact_state_accuracy': sum(predicted[cid] == state for cid, state in truth.items()) / len(truth),
            'unsupported_met': sum(predicted[cid] == 'met' and state != 'met' for cid, state in truth.items()),
            'unknown_recall': (sum(predicted[cid] == 'unknown' and state == 'unknown' for cid, state in truth.items()) /
                sum(state == 'unknown' for state in truth.values())) if 'unknown' in truth.values() else None,
            'confusion_matrix': matrix}
    if repeat is not None:
        if repeat.get('inputs_hash') != export.get('inputs_hash') or repeat['assessment']['result']['rubric_hash'] != replay['rubric_hash']:
            raise ValueError('Repeated runs must use the same frozen inputs and rubric.')
        other = decisions_from(repeat['assessment']['records'], rubric)
        report['cold_run_agreement'] = sum(predicted[cid] == other[cid] for cid in predicted) / len(predicted)
    return report
