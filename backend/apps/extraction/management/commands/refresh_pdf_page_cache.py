"""Reparse explicitly selected native-text PDF pages without running extraction AI."""
import hashlib

import pymupdf
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.documents.models import Document
from apps.extraction.models import DocumentPage
from apps.extraction.services.pdf_reader import _page_text


class Command(BaseCommand):
    help = 'Preview or apply a native PDF page cache refresh for one current document.'

    def add_arguments(self, parser):
        parser.add_argument('document_id')
        parser.add_argument('pages', nargs='+', type=int)
        parser.add_argument('--apply', action='store_true')

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.PDF_TABLE_EXTRACTION:
            raise CommandError('Enable PDF table extraction before refreshing pages.')
        try:
            document = Document.objects.select_for_update().get(
                pk=options['document_id'], superseded_at__isnull=True)
        except (Document.DoesNotExist, ValidationError, ValueError) as exc:
            raise CommandError('Current document not found.') from exc
        numbers = set(options['pages'])
        pages = list(DocumentPage.objects.select_for_update().filter(
            document=document, page_number__in=numbers).order_by('page_number'))
        if len(pages) != len(numbers) or any(
            not page.reusable or page.text_source != 'text' for page in pages
        ):
            raise CommandError('Every selected page must already have a successful native-text cache entry.')
        if not document.file or not document.checksum:
            raise CommandError('The stored PDF and its recorded SHA-256 are required.')
        with document.file.open('rb') as file:
            data = file.read()
        if hashlib.sha256(data).hexdigest() != document.checksum:
            raise CommandError('Stored PDF checksum differs from the current document.')
        with pymupdf.open(stream=data) as pdf:
            if not pdf.is_pdf or min(numbers) < 1 or max(numbers) > pdf.page_count:
                raise CommandError('Invalid PDF or selected page range.')
            for page in pages:
                text, tables = _page_text(pdf[page.page_number - 1])
                if not tables:
                    raise CommandError(f'Page {page.page_number} produced no structured tables. No changes applied.')
                changed = (page.text, page.tables) != (text, tables)
                if changed and options['apply']:
                    page.text, page.tables = text, tables
                    page.save(update_fields=['text', 'tables', 'updated_at'])
                self.stdout.write(f'Page {page.page_number}: {"changed" if changed else "identical"}.')
        self.stdout.write('Refresh committed.' if options['apply'] else 'Preview only.')
