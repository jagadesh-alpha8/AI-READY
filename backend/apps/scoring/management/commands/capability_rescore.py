"""Rescore a saved assessment export under today's credit rule, from its stored part findings (no model calls).

    python manage.py capability_rescore assessment-f5919156.json --out f5919156-rescored.json
    python manage.py assessment_consistency new.json --compare f5919156-rescored.json

A run keeps each requirement's part findings for both judging passes, so its credit can be recomputed when the rule
that turns findings into credit changes (layer2._recredit: related evidence's value, the subject as a gate). That is
how f5919156, scored at related credit 0.5 with the subject as a share, compares with a run on today's rule: the
judgments are the same, only the arithmetic is today's. Withheld requirements (validation_issue) and records without
parts keep their credit. The output's own within-run figures are not meaningful for a requirement a third pass
decided (its other passes' parts are not kept); use it with --compare.
"""
import json

from django.core.management.base import BaseCommand, CommandError


def rescore(report):
    """(rescored export, changes): every part-judged requirement's credit recomputed under today's rule."""
    from apps.scoring.capability.engine import documented
    from apps.scoring.capability.layer2 import _recredit
    from apps.scoring.capability.part_judgment import metadata
    out = json.loads(json.dumps(report))
    changes = []
    for record in out['assessment']['records']:
        if record.get('validation_issue') or not record.get('parts') or 'credit' not in record:
            continue
        credit = _recredit(record['parts'], record['condition_id'])
        if abs(credit - float(record['credit'])) > 1e-9:
            changes.append({'condition_id': record['condition_id'], 'before': record['credit'], 'after': credit})
            record['credit'] = credit
    credits = {r['condition_id']: float(r.get('credit', 1.0 if r.get('state') == 'met' else 0.0))
               for r in out['assessment']['records']}
    scores = documented(credits, out['rubric'])
    result = out['assessment'].setdefault('result', {})
    before = result.get('score')
    result['score'] = round(scores['overall'], 2)
    out['rescored'] = {'rule': metadata(), 'score_before': before, 'score_after': result['score'],
                       'changed_requirements': len(changes)}
    return out, changes


class Command(BaseCommand):
    help = "Rescore an assessment export under today's credit rule from its stored part findings (no model calls)."

    def add_arguments(self, parser):
        parser.add_argument('export')
        parser.add_argument('--out', required=True)

    def handle(self, *args, **options):
        try:
            with open(options['export'], encoding='utf-8') as f:
                report = json.load(f)
        except (OSError, ValueError) as exc:
            raise CommandError(f'Could not read the export: {exc}')
        out, changes = rescore(report)
        with open(options['out'], 'w', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False)
        r = out['rescored']
        self.stdout.write(f"Score {r['score_before']} -> {r['score_after']} under today's rule "
                          f"(related credit {r['rule']['related_credit']}); {len(changes)} requirements changed.")
