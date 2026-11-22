"""Why was (or wasn't) a page used in a run? No model calls (capability/page_use.py).

    python manage.py capability_page_use RUN_ID --page PAGE_ID [--page PAGE_ID ...]
    python manage.py capability_page_use RUN_ID --document DOCUMENT_ID [--page-number 12]
        [--indicator AIQIF-C4.1 ...] [--no-recompute] [--json]

Per key indicator: whether the page reached the judge, whether a credited requirement cites it, and (unless
--no-recompute) where it ranked for each requirement under the run's frozen retrieval, and whether that recompute
reproduces the run's packet.
"""
import json

from django.core.management.base import BaseCommand, CommandError

from apps.scoring.capability.page_use import page_use, resolve_pages
from apps.scoring.models import CapabilityRun


class Command(BaseCommand):
    help = "Explain whether and why a run's page reached each key indicator's judge (no model calls)."

    def add_arguments(self, parser):
        parser.add_argument('run_id')
        parser.add_argument('--page', action='append', dest='pages')
        parser.add_argument('--document')
        parser.add_argument('--page-number')
        parser.add_argument('--indicator', action='append', dest='indicators')
        parser.add_argument('--no-recompute', action='store_true')
        parser.add_argument('--json', action='store_true')

    def handle(self, *args, **options):
        run = CapabilityRun.objects.filter(pk=options['run_id']).first()
        if run is None:
            raise CommandError('Run not found.')
        if not options['pages'] and not options['document']:
            raise CommandError('Give --page or --document.')
        try:
            pages = resolve_pages(run, page_ids=options['pages'], document_id=options['document'],
                                  page_number=options['page_number'])
            ranker = None
            if not options['no_recompute']:
                from apps.scoring.capability.layer2_service import ranker_for_run
                ranker, ranking, note = ranker_for_run(str(run.pk))
                if note:
                    self.stderr.write(f'Ranking: {ranking}. {note}')
            result = page_use(run, pages, indicators=options['indicators'], ranker=ranker,
                              recompute=not options['no_recompute'])
        except ValueError as exc:
            raise CommandError(str(exc))
        if options['json']:
            self.stdout.write(json.dumps(result, indent=1, ensure_ascii=False))
            return
        s = result['summary']
        self.stdout.write(f"{len(result['pages'])} page(s). In the packet of {s['indicators_with_page_in_packet']} of "
                          f"{s['indicators']} key indicators; cited by credited requirements in {s['indicators_citing_it']}.")
        for dropped, kept in result['read_as_identical_copy_of'].items():
            self.stdout.write(f'{dropped} is an identical copy; it was read as {kept}.')
        for row in result['indicators']:
            line = f"{row['indicator']} {row['name']}: " + (
                f"in the packet ({row['packet_chars_from_page']} characters; {', '.join(row['roles'])})"
                if row['in_packet'] else 'not in the packet')
            if row['credited_requirements_citing_it']:
                line += '; cited by ' + ', '.join(row['credited_requirements_citing_it'])
            self.stdout.write(line)
            recompute = row.get('recompute')
            if recompute:
                if not recompute['reproduced']:
                    self.stdout.write("   recompute does not reproduce the run's packet: ranks are indicative only")
                for r in recompute['requirements']:
                    if r['best_rank'] is None:
                        continue
                    self.stdout.write(f"   {r['condition_id']}: best rank {r['best_rank']} of {r['candidates_ranked']}"
                                      f" ({r['route']}); packet took down to {r['deepest_rank_taken']}"
                                      + (f"; tried: {', '.join(r['target_attempt_outcomes'])}"
                                         if r['target_attempt_outcomes'] else ''))
