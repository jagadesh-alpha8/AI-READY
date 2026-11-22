"""Credit held for depth (depth decision 2, taken 20 Nov 2026: reserve).

A share of every credited requirement's credit is held until the college's follow-up answers show how deep the
evidence goes. The judge's credit (record['credit']) is unchanged; what the headline counts is

    credit x ((1 - share) + share x depth fraction)

with depth fraction 0 for evidenced (the documents show it happened; also "don't know" and no answer), 1/2 for
substantiated and 1 for strong. So a provisional result shows (1 - share) of each requirement's credit, and answers
earn the held share back. A requirement the documents do not show holds nothing.

A depth answer that contradicts the credited evidence ('withdrawn') does not lower credit here: it is held at
evidenced and listed for review. Lowering credit on what a college sends is the re-judging path's job, where two
passes must each find a credited part contradicted and quote the new document (layer2.merge_new_evidence).

The share is frozen into each run's inputs (inputs['depth_policy']) and stamped on each published record
(depth_share, depth_level), so every surface computes the same score from the records alone and runs made before
the reserve keep their scores (no depth_share: nothing held).
"""
from fractions import Fraction

VERSION = 'depth-reserve-v2'
#: v2 (22 Nov 2026): credit is held only on requirements with at least MIN_CREDIT, the ones asked about depth.
#: Test 13 had 51 of 95 credited requirements on related evidence alone (0.125 or 0.25): asking how deep evidence
#: goes that doesn't yet show the requirement is overboard, so they are asked to complete it in the missing-evidence
#: question instead and hold nothing. v1 records (no depth_min_credit) keep v1's rule.
MIN_CREDIT = Fraction(1, 2)
FRACTION = {'evidenced': Fraction(0), 'substantiated': Fraction(1, 2), 'strong': Fraction(1)}
LEVELS = ('evidenced', 'substantiated', 'strong')


def configured_share():
    """The share this deployment holds for depth (DEPTH_CREDIT_MODE=reserve, DEPTH_CREDIT_SHARE), or 0."""
    from django.conf import settings
    if settings.DEPTH_CREDIT_MODE != 'reserve':
        return Fraction(0)
    share = Fraction(str(settings.DEPTH_CREDIT_SHARE or '0'))
    if not 0 <= share < 1:
        raise ValueError('DEPTH_CREDIT_SHARE must be at least 0 and below 1.')
    return share


def frozen_policy():
    """What a new run freezes: the share and this rule's version."""
    share = configured_share()
    return {'version': VERSION, 'mode': 'reserve' if share else 'none', 'share': str(share),
            'min_credit': str(MIN_CREDIT)}


def run_min_credit(inputs):
    policy = (inputs or {}).get('depth_policy') or {}
    return Fraction(str(policy['min_credit'])) if policy.get('min_credit') else Fraction(0)


def run_share(inputs):
    policy = (inputs or {}).get('depth_policy') or {}
    return Fraction(str(policy.get('share') or '0')) if policy.get('mode') == 'reserve' else Fraction(0)


def factor(level, share):
    share = Fraction(str(share or 0))
    if not share:
        return Fraction(1)
    return (1 - share) + share * FRACTION.get(level or 'evidenced', Fraction(0))   # 'withdrawn': held at evidenced


def record_factor(record):
    minimum = record.get('depth_min_credit')
    if minimum and Fraction(str(record.get('credit') or 0)) < Fraction(str(minimum)):
        return Fraction(1)   # not asked about depth: nothing held
    return factor(record.get('depth_level'), record.get('depth_share'))


def holds(record):
    """True when part of this record's credit is held for depth (it is asked about depth)."""
    return bool(record.get('depth_share')) and (record.get('credit') or 0) > 0 and record_factor(
        {**record, 'depth_level': 'evidenced'}) < 1


def scored_credits(records, key='credit'):
    """{condition id: credit the headline counts}. Records without depth_share count in full."""
    out = {}
    for r in records:
        value = r.get(key)
        if value is None and key != 'credit':
            value = r.get('credit')
        out[r['condition_id']] = Fraction(str(value or 0)) * record_factor(r)
    return out


def factors(records):
    """{condition id: factor}, for projections (action plan, plan scenarios): a requirement a plan would establish
    enters at its record's level, evidenced unless a follow-up already showed more."""
    return {r['condition_id']: record_factor(r) for r in records}


def apply(credits, factor_by_id):
    return {cid: Fraction(str(value or 0)) * factor_by_id.get(cid, Fraction(1)) for cid, value in credits.items()}


def stamp(rows, share, levels=None, min_credit=None):
    """Set depth_share (and depth_min_credit) and depth_level on published rows. levels: {condition id: level} from
    depth judgments (the provisional run's, for a final result); otherwise a row keeps the level it carries, else
    evidenced. min_credit None keeps what a row carries."""
    if not share:
        return rows
    levels = levels or {}
    for row in rows:
        row['depth_share'] = str(share)
        if min_credit:
            row['depth_min_credit'] = str(min_credit)
        level = levels.get(row['condition_id'], row.get('depth_level') or 'evidenced')
        if level == 'withdrawn':
            row['depth_review'] = 'A follow-up answer appears to contradict the credited evidence; held at evidenced for review.'
            level = 'evidenced'
        row['depth_level'] = level if level in FRACTION else 'evidenced'
    return rows


def summary(records, rubric):
    """For the result payload: the evidence score (nothing held), the score, what is held and what was earned back."""
    from .engine import documented
    shares = {Fraction(str(r.get('depth_share') or 0)) for r in records}
    share = max(shares) if shares else Fraction(0)
    if not share:
        return None
    raw = {r['condition_id']: Fraction(str(r.get('credit') or 0)) for r in records}
    evidence = documented(raw, rubric)['overall']
    provisional = documented(scored_credits([{**r, 'depth_level': 'evidenced', 'depth_review': None}
                                             for r in records]), rubric)['overall']
    scored = documented(scored_credits(records), rubric)['overall']
    credited = [r for r in records if holds(r)]
    counts = {level: sum(1 for r in credited if (r.get('depth_level') or 'evidenced') == level) for level in LEVELS}
    return {'version': VERSION, 'share': float(share), 'evidence_score': evidence, 'score': scored,
            'held_points': round(evidence - provisional, 2), 'earned_back_points': round(scored - provisional, 2),
            'still_held_points': round(evidence - scored, 2), 'credited_requirements_by_level': counts,
            'held_for_review': sorted(r['condition_id'] for r in records if r.get('depth_review'))}


def follow_up_note(record):
    """One plain sentence for a requirement's explanation about the credit held for it, or None."""
    if not holds(record):
        return None
    if record.get('depth_review'):
        return 'One of your follow-up answers seemed to go against this evidence, so we have kept the credit and will review it.'
    level = record.get('depth_level') or 'evidenced'
    if level == 'strong':
        return 'Your follow-up answers showed the full depth of this, which earned back all of the credit held for it.'
    if level == 'substantiated':
        return 'Your follow-up answers showed more of the depth of this, which earned back half of the credit held for it.'
    return 'Part of this credit is held until your follow-up answers show how far it goes.'
