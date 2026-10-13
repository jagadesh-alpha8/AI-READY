"""A benchmark inside a release that is in review or approved is frozen: what the
reviewer approved is exactly what gets published. Editing resumes when the
release is sent back to draft (or after publishing, via reopen)."""
from ..models import BenchmarkRelease


def review_lock(benchmark):
    """The label of the release currently reviewing this benchmark, or None."""
    item = (benchmark.release_items
            .filter(release__status__in=[BenchmarkRelease.Status.REVIEW, BenchmarkRelease.Status.APPROVED])
            .select_related('release').first())
    return item.release.release_label if item else None


def lock_message(benchmark):
    label = review_lock(benchmark)
    return (f'{benchmark.benchmark_code} is in {label}, which is under review; '
            'send the release back to draft to change it.') if label else None
