from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.institutions.models import Institution
from apps.sprints.models import Sprint
from .models import Document, DriveImportJob
from .services import create_document_from_file
from io import StringIO
import json
from django.core.management import call_command
from django.core.management.base import CommandError


class SourceIdentityTests(TestCase):
    def setUp(self):
        self.sprint = Sprint.objects.create(institution=Institution.objects.create(name='College'))

    def upload(self, name, content, drive_id=''):
        return create_document_from_file(
            sprint=self.sprint, file_obj=SimpleUploadedFile(name, content, content_type='application/pdf'),
            document_type='unclassified', drive_file_id=drive_id, source_path=name)

    def test_same_drive_id_keeps_lineage_after_rename(self):
        old = self.upload('a.pdf', b'%PDF-1.4 first', 'drive-1')
        new = self.upload('renamed.pdf', b'%PDF-1.4 changed', 'drive-1')
        old.refresh_from_db()
        self.assertEqual(new.previous_version_id, old.pk)
        self.assertEqual(new.version_number, 2)
        self.assertIsNotNone(old.superseded_at)

    def test_manual_upload_does_not_supersede_drive_file_with_same_name(self):
        self.upload('a.pdf', b'%PDF-1.4 imported', 'drive-1')
        self.upload('a.pdf', b'%PDF-1.4 manual')
        self.assertEqual(Document.objects.filter(superseded_at__isnull=True).count(), 2)

    def test_legacy_source_without_drive_identity_is_not_guessed_to_be_a_match(self):
        self.upload('a.pdf', b'%PDF-1.4 legacy')
        new = self.upload('a.pdf', b'%PDF-1.4 drive', 'drive-1')
        self.assertIsNone(new.previous_version_id)

    def test_inventory_reports_lineage_without_changing_documents(self):
        self.upload('a.pdf', b'%PDF-1.4 old', 'drive-1')
        self.upload('b.pdf', b'%PDF-1.4 new', 'drive-1')
        before = list(Document.objects.order_by('pk').values())
        output = StringIO()
        call_command('audit_evidence', sprint=str(self.sprint.pk), stdout=output)
        report = json.loads(output.getvalue())
        self.assertEqual((report['documents_total'], report['current_documents'],
                          report['superseded_documents']), (2, 1, 1))
        self.assertEqual(report['documents'][0]['drive_file_id'], 'drive-1')
        self.assertEqual(list(Document.objects.order_by('pk').values()), before)

    def test_inventory_rejects_invalid_sprint_identifier(self):
        with self.assertRaises(CommandError):
            call_command('audit_evidence', sprint='invalid')

    def test_inventory_omits_raw_import_errors_and_retains_source_identity(self):
        DriveImportJob.objects.create(
            sprint=self.sprint, drive_url='https://drive.google.com/drive/folders/root',
            error_message='request failed https://example.invalid?key=SECRET-KEY',
            results={
                'skipped_files': [{'filename': 'a.pdf', 'drive_file_id': 'drive-1',
                    'source_path': 'Folder/a.pdf', 'reason': 'provider body SECRET-BODY',
                    'reason_code': 'download_failed'},
                    {'filename': 'old.pdf', 'reason': 'legacy SECRET-OLD'}],
                'progress': {'processed': 2, 'total': 2, 'current_file': 'SECRET-CURRENT'},
                'provider_response': 'SECRET-RESPONSE',
            })
        output = StringIO()
        call_command('audit_evidence', sprint=str(self.sprint.pk), stdout=output)
        self.assertNotIn('SECRET', output.getvalue())
        record = json.loads(output.getvalue())['imports'][0]
        self.assertTrue(record['error_present'])
        self.assertEqual(record['results']['skipped_files'][0], {
            'filename': 'a.pdf', 'drive_file_id': 'drive-1', 'source_path': 'Folder/a.pdf',
            'reason_code': 'download_failed'})
        self.assertEqual(record['results']['skipped_files'][1]['reason_code'], 'legacy_unspecified')
