"""Apply the automatic AI-QIF tagging rules (apps/facts/aiqif_tagging.py) to facts that already exist.

    python manage.py retag_aiqif_facts                      # dry run, every sprint: what would change
    python manage.py retag_aiqif_facts --sprint <uuid>      # dry run, one sprint
    python manage.py retag_aiqif_facts --commit             # apply, and recalculate each changed sprint's CRI

No AI call. For each fact (values and reviews are never changed):
- a fact with no kind is classified by aiqif_tagging.guess_kind;
- a NAAC metric is taken from its own quote when exactly one full metric number ("2.1.2") is printed there and
  the crosswalk knows it;
- its tags are rebuilt by the rules -- the AI tags it already has are re-judged (accepted automatically or left
  for the Super Admin), crosswalk tags are added, and every tag a person confirmed, rejected or added is kept;
- a fact classified as context or profile that has a tag a person confirmed (so it counted toward coverage
  before) is sent to the expert queue: the backfill never silently removes coverage. Old unreviewed AI tags
  never counted, so dropping them from a context/profile fact removes nothing.
Refuses to run when the NAAC -> AI-QIF crosswalk is not loaded.
Run it again after a new benchmark release is published, to tag against that release.
"""
from collections import Counter

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.facts.aiqif_tagging import (
    Crosswalk, Precedents, ai_check_pending, apply_tags, guess_kind, metrics_in, refresh_state,
)
from apps.facts.models import ExtractedFact, FactAIQIFMapping
from apps.facts.profile_suggestion import match_code


class _DryRun(Exception):
    pass


class Command(BaseCommand):
    help = 'Re-tag existing facts with the automatic AI-QIF rules (dry run unless --commit).'

    def add_arguments(self, parser):
        parser.add_argument('--sprint', help='Only this sprint (uuid). Without it: every sprint.')
        parser.add_argument('--commit', action='store_true', help='Apply the changes (default: dry run).')
        parser.add_argument('--ai-check', action='store_true',
                            help='Also run the AI second opinion on tags still waiting (makes AI calls; with --commit only).')

    def handle(self, *args, **options):
        crosswalk = Crosswalk()
        if not crosswalk.loaded:
            raise CommandError('The NAAC -> AI-QIF crosswalk is not loaded (import the AI-QIF framework first: '
                               'python manage.py import_aiqif <workbook>). Nothing was changed.')
        facts = ExtractedFact.objects.prefetch_related('aiqif_mappings').order_by('sprint_id', 'created_at')
        if options['sprint']:
            facts = facts.filter(sprint_id=options['sprint'])
        stats, sprints = Counter(), set()
        precedents = Precedents()  # earlier expert decisions on the same fields (aiqif_tagging rule 4)
        try:
            with transaction.atomic():
                for fact in facts:
                    self._retag(fact, crosswalk, stats, precedents)
                    sprints.add(fact.sprint_id)
                if not options['commit']:
                    raise _DryRun
        except _DryRun:
            pass
        verb = 'Re-tagged' if options['commit'] else 'Would re-tag'
        self.stdout.write(f'{verb} {stats["facts"]} fact(s) in {len(sprints)} sprint(s).')
        for key in sorted(k for k in stats if k != 'facts'):
            self.stdout.write(f'  {key}: {stats[key]}')
        if options['commit'] and options['ai_check']:
            for sprint_id in sprints:
                result = ai_check_pending(list(ExtractedFact.objects.filter(sprint_id=sprint_id)), limit=1000)
                self.stdout.write(f'  AI check, sprint {sprint_id}: {result["checked"]} checked, '
                                  f'{result["accepted"]} accepted.')
        if options['commit'] and sprints:
            from apps.scoring.services import run_scoring_engine
            from apps.sprints.models import Sprint
            for sprint in Sprint.objects.filter(id__in=sprints):
                run_scoring_engine(sprint)
            self.stdout.write(f'Recalculated the CRI of {len(sprints)} sprint(s).')
        elif not options['commit']:
            self.stdout.write('Dry run: nothing was changed. Add --commit to apply.')

    @staticmethod
    def _retag(fact, crosswalk, stats, precedents=None):
        stats['facts'] += 1
        if not fact.fact_kind:
            fact.fact_kind = guess_kind(fact)
            stats[f'classified as {fact.fact_kind}'] += 1
        if not fact.naac_metric:
            found = [m for m in metrics_in(fact.source_snippet) if crosswalk.lookup(m)]
            if len(found) == 1:
                fact.naac_metric = found[0]
                stats['NAAC metric found in quote'] += 1
        if fact.fact_kind == ExtractedFact.FactKind.PROFILE and fact.profile_field in ('', None):
            fact.profile_field = ExtractedFact.ProfileField.OTHER
        fact.profile_code = match_code(fact) if fact.fact_kind == ExtractedFact.FactKind.PROFILE else ''
        fact.save(update_fields=['fact_kind', 'naac_metric', 'profile_field', 'profile_code', 'updated_at'])
        existing = [m for m in fact.aiqif_mappings.all()
                    if m.review_status == FactAIQIFMapping.ReviewStatus.UNREVIEWED
                    and m.source == FactAIQIFMapping.Source.AI]
        had_confirmed = fact.aiqif_mappings.filter(review_status=FactAIQIFMapping.ReviewStatus.CONFIRMED).exists()
        suggestions = [{'indicator_code': m.indicator_code, 'criterion': m.criterion, 'reason': m.reason,
                        'confidence': m.confidence} for m in existing]
        apply_tags(fact, suggestions, crosswalk, precedents)
        if fact.fact_kind != ExtractedFact.FactKind.AI_EVIDENCE and had_confirmed and not fact.kind_reviewed_by_id:
            # A person confirmed one of its tags (it counted before): a Super Admin decides (kept until decided).
            fact.tagging_notes = [*(fact.tagging_notes or []), {
                'kind': 'check_kind', 'detail': 'Classified as not AI evidence by the backfill, but a person had '
                                                'confirmed one of its AI-QIF tags: an expert decides.'}]
            fact.save(update_fields=['tagging_notes', 'updated_at'])
            refresh_state(fact)
        stats['crosswalk tags'] += fact.aiqif_mappings.filter(source=FactAIQIFMapping.Source.CROSSWALK).count()
        stats['decided by an expert precedent'] += fact.aiqif_mappings.filter(
            auto_decision__in=['accepted_precedent', 'rejected_precedent']).count()
        stats['sent to the expert queue'] += int(fact.kind_needs_check)
