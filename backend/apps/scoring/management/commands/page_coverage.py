"""Account for every expected page of a sprint's current documents before an assessment, and optionally
recreate page rows that were never saved.

Read-only by default: it builds the same evidence snapshot an assessment freezes (nothing is written) and
lists, per document, pages with no stored row, pages stored but unreadable, and pages left blank by
header/footer cleanup. Exits non-zero while any expected page has no stored row, so it can gate a run.

--repair --apply recreates missing rows. Native-text PDF pages are read locally at no model cost. A missing
page that needs OCR or vision is skipped unless --allow-model-reads is given. Image and office files with no
rows are re-read with the local reader (local OCR for images; no model calls). The stored file must still
match its recorded SHA-256.
"""
import hashlib
import json
import os

import pymupdf
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.documents.models import Document
from apps.extraction.services import office_reader
from apps.extraction.services.evidence_text import _with_tables
from apps.extraction.services.pdf_reader import PDFPageReader, _page_text, _save_page
from apps.extraction.services.text_cleaning import is_meaningful_text
from apps.scoring.capability.pipeline_diagnostics import page_coverage
from apps.scoring.capability.storage import evidence_snapshot
from apps.sprints.models import Sprint


def _ranges(numbers):
    """[3, 4, 5, 9] -> '3-5, 9'"""
    out, start, prev = [], None, None
    for n in sorted(numbers):
        if start is None:
            start = prev = n
        elif n == prev + 1:
            prev = n
        else:
            out.append(f'{start}-{prev}' if prev != start else str(start))
            start = prev = n
    if start is not None:
        out.append(f'{start}-{prev}' if prev != start else str(start))
    return ', '.join(out)


class Command(BaseCommand):
    help = 'Account for every expected page of a sprint (read-only); optionally recreate missing page rows.'

    def add_arguments(self, parser):
        parser.add_argument('sprint_id')
        parser.add_argument('--repair', action='store_true', help='Plan recreation of missing page rows.')
        parser.add_argument('--apply', action='store_true', help='With --repair: write the recreated rows.')
        parser.add_argument('--allow-model-reads', action='store_true',
                            help='With --repair: also re-read missing pages that need OCR or vision (may cost).')
        parser.add_argument('--json', action='store_true', help='Print the coverage as JSON.')

    def handle(self, *args, **options):
        try:
            sprint = Sprint.objects.get(pk=options['sprint_id'])
        except (Sprint.DoesNotExist, ValidationError, ValueError) as exc:
            raise CommandError('Sprint not found.') from exc
        coverage = self._coverage(sprint)
        self._print(coverage, options['json'])
        if options['repair'] and not coverage['complete']:
            self._repair(sprint, coverage, apply=options['apply'], allow_model=options['allow_model_reads'])
            if options['apply']:
                coverage = self._coverage(sprint)
                self.stdout.write('\nAfter repair:')
                self._print(coverage, options['json'])
        if not coverage['complete']:
            raise CommandError(f"{coverage['totals']['missing_rows']} expected page(s) have no stored page row; "
                               'they cannot reach an assessment.')

    @staticmethod
    def _coverage(sprint):
        manifest, sources = evidence_snapshot(sprint)
        return page_coverage(manifest, sources)

    def _print(self, coverage, as_json):
        if as_json:
            self.stdout.write(json.dumps(coverage, indent=1))
            return
        self.stdout.write(f"{'document':44}  expected  rows  frozen  missing rows / not ok / blank after cleanup")
        for d in sorted(coverage['documents'], key=lambda d: (-len(d['missing_rows']), d['filename'])):
            notes = ' / '.join(_ranges(d[k]) or '-' for k in ('missing_rows', 'not_ok', 'blank_after_cleanup'))
            self.stdout.write(f"{d['filename'][:44]:44}  {d['expected']:8}  {d['rows']:4}  {d['frozen']:6}  {notes}")
        t = coverage['totals']
        self.stdout.write(f"\nexpected {t['expected']} | rows {t['rows']} | frozen {t['frozen']} | "
                          f"missing rows {t['missing_rows']} | not ok {t['not_ok']} | "
                          f"blank after cleanup {t['blank_after_cleanup']} | "
                          f"{'COMPLETE' if coverage['complete'] else 'INCOMPLETE'}")

    def _repair(self, sprint, coverage, *, apply, allow_model):
        reader = PDFPageReader()
        for entry in coverage['documents']:
            if not entry['missing_rows']:
                continue
            document = Document.objects.get(pk=entry['document_id'])
            label = f"{entry['filename']}: pages {_ranges(entry['missing_rows'])}"
            data = self._verified_bytes(document)
            if data is None:
                self.stdout.write(f'SKIP {label} (stored file missing or checksum differs)')
                continue
            ext = os.path.splitext(document.original_filename or document.file.name or '')[1].lower()
            if ext == '.pdf':
                self._repair_pdf(document, data, entry['missing_rows'], reader, label, apply, allow_model)
            elif ext in office_reader.IMAGE_EXTENSIONS | office_reader.OFFICE_EXTENSIONS:
                if apply:
                    reader.read_pages(document)  # stores a row per page (local reading only)
                self.stdout.write(f"{'REREAD' if apply else 'WOULD REREAD'} {label} (local reader)")
            else:
                self.stdout.write(f'SKIP {label} (unsupported format {ext or "(none)"})')

    def _repair_pdf(self, document, data, numbers, reader, label, apply, allow_model):
        native, needs_model, saved, failed = [], [], [], []
        with pymupdf.open(stream=data, filetype='pdf') as pdf:
            for number in numbers:
                if number > pdf.page_count:
                    failed.append(number)
                    continue
                page = pdf.load_page(number - 1)
                text, tables = _page_text(page)
                is_native = is_meaningful_text(_with_tables(text, tables, number), reader.min_text_chars_per_page)
                (native if is_native else needs_model).append(number)
                if not apply or (not is_native and not allow_model):
                    continue
                read = reader._read_page(document, page, number)
                (saved if _save_page(document, number, read) else failed).append(number)
        self.stdout.write(f'{label}: native text {_ranges(native) or "-"}; needs OCR/vision {_ranges(needs_model) or "-"}')
        if needs_model and not allow_model:
            self.stdout.write(f'  skipped {_ranges(needs_model)}: pass --allow-model-reads to re-read them')
        if apply:
            self.stdout.write(f'  saved {_ranges(saved) or "-"}; failed {_ranges(failed) or "-"}')

    @staticmethod
    def _verified_bytes(document):
        if not document.file or not document.checksum:
            return None
        try:
            with document.file.open('rb') as fh:
                data = fh.read()
        except OSError:
            return None
        return data if hashlib.sha256(data).hexdigest() == document.checksum else None
