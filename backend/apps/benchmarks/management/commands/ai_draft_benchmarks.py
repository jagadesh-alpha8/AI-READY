"""AI-write the content of draft benchmarks (levels, evidence rules, applicability,
target guidance, owner) -- fully automatic, see services/ai_drafting.py.

    python manage.py ai_draft_benchmarks                    # every AI-QIF draft still on template levels
    python manage.py ai_draft_benchmarks AIQIF-C1.1 AIQIF-C2.3
    python manage.py ai_draft_benchmarks --redo             # also redo ones the AI already wrote
    python manage.py ai_draft_benchmarks --queue            # one background job each, run in parallel on the routers
"""
from django.core.management.base import BaseCommand

from ...models import Benchmark
from ...services.ai_drafting import draft_with_router


class Command(BaseCommand):
    help = 'AI-write draft benchmark content (fully automatic). Only DRAFT benchmarks are touched.'

    def add_arguments(self, parser):
        parser.add_argument('codes', nargs='*')
        parser.add_argument('--framework', default='AIQIF-V1.0')
        parser.add_argument('--redo', action='store_true', help='Also redo benchmarks the AI already wrote.')
        parser.add_argument('--queue', action='store_true', help='Queue one background job per benchmark.')

    def handle(self, *args, codes, framework, redo, queue, **opts):
        qs = Benchmark.objects.filter(status=Benchmark.Status.DRAFT).select_related('pillar', 'capability')
        if codes:
            qs = qs.filter(benchmark_code__in=codes)
        else:
            qs = qs.filter(framework__code=framework)
            if not redo:
                qs = qs.filter(maturity_levels__is_placeholder=True).distinct()
        benchmarks = list(qs.order_by('benchmark_code'))
        self.stdout.write(f'{len(benchmarks)} draft benchmark(s) to write.')
        if not benchmarks:
            return
        if queue:
            from ...tasks import ai_draft_benchmark
            for b in benchmarks:
                ai_draft_benchmark.delay(str(b.pk))
            self.stdout.write(self.style.SUCCESS(f'Queued {len(benchmarks)} job(s); results appear in the Studio and the logs.'))
            return

        results = [draft_with_router(b) for b in benchmarks]
        for r in results:
            style = self.style.SUCCESS if r.ok else self.style.ERROR
            kept = f' (kept: {", ".join(r.kept_human)})' if r.kept_human else ''
            self.stdout.write(style(f'  {r.code}: {"OK " + r.detail if r.ok else r.detail}{kept}'))
        ok = sum(r.ok for r in results)
        self.stdout.write(f'{ok} of {len(results)} written.')
