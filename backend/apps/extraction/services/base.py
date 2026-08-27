"""Pluggable interfaces for each extraction pipeline stage.

Each interface takes a `Document` (and whatever the previous stage produced)
and returns plain data -- no interface here depends on Celery, DRF, or the
ExtractionJob model, so a real implementation can be developed and unit
tested in isolation, then swapped in via `ExtractionPipeline(...)` without
touching the orchestration or task-retry logic in `pipeline.py`/`tasks.py`.

`apps.extraction.services.stub` provides the current, honest default for
each of these: real bookkeeping where that's possible without AI, and empty
results (not fabricated ones) everywhere it isn't yet.
"""
from abc import ABC, abstractmethod


class DocumentClassifier(ABC):
    """Confirms/derives a document's type and structural characteristics."""

    @abstractmethod
    def classify(self, document):
        """Return a dict of classification metadata for `document`."""


class PageReader(ABC):
    """Reads a document's content into page-level text (OCR for scans,
    direct extraction for machine-readable formats)."""

    @abstractmethod
    def read_pages(self, document, max_pages=None):
        """Return a dict describing the pages read, e.g. {'pages': [...], 'page_count': N}.

        `max_pages` limits how many pages are actually read (e.g. a
        classifier that only needs a short text sample) without changing
        the reported total `page_count`. `None` means read every page.
        """


class OCRProvider(ABC):
    """Extracts text from a page a `PageReader` found to have little/no
    machine-readable text (a scanned image rather than real text layout).

    Kept separate from `PageReader` so a real OCR backend (Tesseract, a
    cloud OCR API, ...) can be built and swapped in independently of how
    PDFs are opened and parsed -- see `apps.extraction.services.stub.
    NullOCRProvider` for the current, honest default (performs no OCR)."""

    @abstractmethod
    def extract_text(self, document, page_number):
        """Return the OCR'd text for one page of `document`, or `None` if
        OCR could not be performed (e.g. no OCR backend configured yet) --
        never a fabricated guess at what the page might say."""


class FactExtractor(ABC):
    """Extracts candidate facts (raw values + source snippets) from read pages."""

    @abstractmethod
    def extract_facts(self, document, pages):
        """Return a list of raw fact dicts."""


class AuditFieldMapper(ABC):
    """Maps candidate facts onto the CRI audit field schema."""

    @abstractmethod
    def map_fields(self, document, facts):
        """Return a list of dicts shaped for `apps.facts.models.ExtractedFact`
        creation -- at minimum `field_name`, `field_key`, and `value`."""


class GapDetector(ABC):
    """Flags missing or weak evidence implied by a document's mapped facts."""

    @abstractmethod
    def detect_gaps(self, document, mapped_facts):
        """Return a list of dicts shaped for `apps.gaps.models.GapItem` creation."""


class ConflictChecker(ABC):
    """Flags mapped facts that contradict other documents in the same sprint."""

    @abstractmethod
    def check_conflicts(self, document, mapped_facts):
        """Return a list of conflict descriptors."""
