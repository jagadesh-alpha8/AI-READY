"""Embed a sprint's evidence into the passage cache before an assessment, so the run does not spend hours on it.

Builds packets for one indicator through the same path an assessment uses (same sources, same deduplication
setting, same footer handling and passage construction), which embeds every eligible passage into
CAPABILITY_EMBEDDING_CACHE_DIR. Cached vectors equal fresh ones, so the later run's packets are unchanged.
No model calls to any provider, no run created. Rerunning it only embeds pages that changed.
"""
import time

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.scoring.capability.engine import release
from apps.scoring.capability.evaluation import select_context
from apps.scoring.capability.semantic_retrieval import configured_policy, ranker_for
from apps.scoring.capability.storage import evidence_snapshot
from apps.sprints.models import Sprint


class Command(BaseCommand):
    help = "Embed a sprint's evidence passages into the embedding cache ahead of an assessment."

    def add_arguments(self, parser):
        parser.add_argument('sprint_id')

    def handle(self, *args, **options):
        if not settings.CAPABILITY_EMBEDDING_CACHE_DIR:
            raise CommandError('Set CAPABILITY_EMBEDDING_CACHE_DIR first; without a cache nothing is kept.')
        try:
            sprint = Sprint.objects.get(pk=options['sprint_id'])
        except (Sprint.DoesNotExist, ValidationError, ValueError) as exc:
            raise CommandError('Sprint not found.') from exc
        policy = configured_policy()
        ranker = ranker_for(policy)
        if ranker is None:
            raise CommandError('CAPABILITY_RETRIEVAL_MODE is bm25; there is nothing to embed.')
        _, sources = evidence_snapshot(sprint)
        if policy.get('deduplicate'):
            from apps.scoring.capability.structure import deduplicate
            sources, _ = deduplicate(sources)
        started = time.monotonic()
        select_context(release()['indicators'][0], sources, semantic_ranker=ranker)
        stats = ranker.stats
        self.stdout.write(f"{len(sources)} pages: {stats.get('embedded_passages', 0)} passages embedded, "
                          f"{stats.get('cached_passages', 0)} already cached, in {time.monotonic() - started:.0f} s.")
