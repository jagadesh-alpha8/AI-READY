"""Per-chunk progress and results of one extraction job (ExtractionChunk rows).

A document's text is split into chunks (openai_fact_extractor._build_chunks). For each chunk the store keeps
its page range, status, attempt count, error, and the validated facts the AI returned, keyed by the hash of
the exact text and versioned extraction protocol. On a retry, a continuation or "Process again" of a failed / partial job:

- a COMPLETED chunk with the same text is reused -- no AI call, its saved facts are merged as before;
- a FAILED or never-finished chunk is sent to the AI again;
- a chunk whose text changed (e.g. a page that was unreadable is now OCR'd) is a new chunk.

Facts still reach the database only through ExtractionPipeline._persist_facts (scoped observations,
reviewed facts never overwritten), so reusing a chunk never duplicates a fact.

The number of NEW AI chunk calls one attempt makes is capped by OPENAI_FACT_EXTRACTION_MAX_CHUNKS (0 = no
cap): past it the attempt stops with ExtractionContinues and the task carries on in the next attempt, so a very
large document is finished in bounded steps instead of being cut off.
"""
import hashlib
import logging

from django.conf import settings
from django.utils import timezone

from ..exceptions import ExtractionContinues

logger = logging.getLogger(__name__)


def chunk_text(chunk_pages):
    return '\n\n'.join(f'--- Page {page["page_number"]} ---\n{page.get("text") or ""}' for page in chunk_pages)


def chunk_hash(chunk_pages):
    from ..observations import digest, protocol
    return digest({'text': chunk_text(chunk_pages), 'protocol': protocol()})


class ChunkStore:
    def __init__(self, job, *, max_new_calls=None):
        self.job = job
        self.max_new_calls = settings.OPENAI_FACT_EXTRACTION_MAX_CHUNKS if max_new_calls is None else max_new_calls
        self.new_calls = 0
        self.rows = {}      # chunk index -> ExtractionChunk
        self.total = 0

    def prepare(self, chunks):
        """Create / refresh one row per chunk; drop rows of chunks that no longer exist (the text changed)."""
        from ..models import ExtractionChunk

        existing = {row.content_hash: row for row in ExtractionChunk.objects.filter(job=self.job)}
        keep = set()
        for index, pages in enumerate(chunks, start=1):
            digest = chunk_hash(pages)
            numbers = [p['page_number'] for p in pages]
            row = existing.get(digest)
            if row is None:
                row = ExtractionChunk.objects.create(
                    job=self.job, index=index, content_hash=digest, page_numbers=numbers,
                    page_start=numbers[0], page_end=numbers[-1])
                existing[digest] = row
            elif row.index != index:
                row.index = index
                row.save(update_fields=['index', 'updated_at'])
            self.rows[index] = row
            keep.add(digest)
        ExtractionChunk.objects.filter(job=self.job).exclude(content_hash__in=keep).delete()
        self.total = len(chunks)
        self._sync_progress()

    def reusable(self, index):
        row = self.rows.get(index)
        return row if row is not None and row.status == row.Status.COMPLETED else None

    def before_call(self, index):
        """About to send chunk `index` to the AI: enforce the per-attempt cap, then mark it running."""
        if self.max_new_calls and self.new_calls >= self.max_new_calls:
            done = sum(1 for r in self.rows.values() if r.status == r.Status.COMPLETED)
            logger.info('extraction.chunks.continue job_id=%s done=%d total=%d', self.job.id, done, self.total)
            raise ExtractionContinues(done, self.total)
        self.new_calls += 1
        row = self.rows[index]
        row.status, row.attempts, row.error = row.Status.RUNNING, row.attempts + 1, ''
        row.save(update_fields=['status', 'attempts', 'error', 'updated_at'])
        _heartbeat(self.job)

    def completed(self, index, facts, classification=None):
        row = self.rows[index]
        row.status, row.facts, row.completed_at, row.error = row.Status.COMPLETED, facts, timezone.now(), ''
        fields = ['status', 'facts', 'completed_at', 'error', 'updated_at']
        if classification is not None:
            row.classification = classification
            fields.append('classification')
        row.save(update_fields=fields)
        self._sync_progress()

    def failed(self, index, error):
        row = self.rows[index]
        row.status, row.error = row.Status.FAILED, str(error)[:1000]
        row.save(update_fields=['status', 'error', 'updated_at'])
        self._sync_progress()

    def _sync_progress(self):
        """Live chunk counts and progress on the job, for the monitor (extracting facts: 45% -> 60%)."""
        from ..models import ExtractionJob

        done = sum(1 for r in self.rows.values() if r.status == r.Status.COMPLETED)
        fields = {'chunks_total': self.total, 'chunks_completed': done, 'heartbeat_at': timezone.now()}
        if self.total and self.job.current_step == ExtractionJob.Step.EXTRACTING_FACTS:
            fields['progress_percentage'] = 45 + int(15 * done / self.total)
        ExtractionJob.objects.filter(id=self.job.id).update(**fields)
        for name, value in fields.items():
            setattr(self.job, name, value)


def _heartbeat(job):
    from ..models import ExtractionJob

    now = timezone.now()
    ExtractionJob.objects.filter(id=job.id).update(heartbeat_at=now)
    job.heartbeat_at = now
