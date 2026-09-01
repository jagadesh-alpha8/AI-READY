import re
from unittest.mock import MagicMock, patch

import requests
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.institutions.models import Institution
from apps.sprints.models import Sprint

from .drive_import import DRIVE_API_BASE, classify_filename, list_drive_folder_files, parse_drive_folder_id
from .exceptions import PermanentDriveImportError, RecoverableDriveImportError
from .models import Document, DriveImportJob
from .services import DocumentValidationError, create_document_from_file
from .tasks import _handle_recoverable

PASSWORD = 'Str0ng!DevPassw0rd'


def make_pdf(name='naac_ssr.pdf', content=b'%PDF-1.4 fake ssr content'):
    return SimpleUploadedFile(name, content, content_type='application/pdf')


class DocumentUploadTests(APITestCase):
    def setUp(self):
        self.institution = Institution.objects.create(name='MKCE', city='Karur', state='TN')
        self.other_institution = Institution.objects.create(name='Other', city='X', state='Y')

        self.iqac = self._make_user('iqac@test.edu', User.Role.IQAC_COORDINATOR, self.institution)
        self.hod = self._make_user('hod@test.edu', User.Role.HOD, self.institution)
        self.viewer = self._make_user('viewer@test.edu', User.Role.VIEWER, self.institution)
        self.institution_admin = self._make_user(
            'admin@test.edu', User.Role.INSTITUTION_ADMIN, self.institution,
        )
        self.outsider = self._make_user('outsider@test.edu', User.Role.HOD, self.other_institution)

        self.sprint = Sprint.objects.create(institution=self.institution, mode=Sprint.SprintMode.VERIFIED_CRI)

    @staticmethod
    def _make_user(email, role, institution):
        return User.objects.create_user(
            email=email, username=email.split('@')[0], password=PASSWORD,
            first_name='Test', last_name=role, role=role, institution=institution,
        )

    def _auth(self, user):
        login = self.client.post('/api/v1/auth/login/', {'email': user.email, 'password': PASSWORD})
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {login.data["access_token"]}')

    def _upload(self, **overrides):
        payload = {
            'file': make_pdf(),
            'document_type': 'naac_ssr',
            'owner_role': 'IQAC_COORDINATOR',
        }
        payload.update(overrides)
        return self.client.post(
            f'/api/v1/sprints/{self.sprint.id}/upload-file/', payload, format='multipart',
        )

    # -- valid upload ------------------------------------------------------

    def test_valid_upload_populates_real_metadata(self):
        self._auth(self.iqac)
        response = self._upload()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        data = response.data
        self.assertEqual(data['document_type'], 'naac_ssr')
        self.assertEqual(data['document_type_label'], 'NAAC Self-Study Report (SSR)')
        self.assertEqual(data['original_filename'], 'naac_ssr.pdf')
        self.assertEqual(data['mime_type'], 'application/pdf')
        self.assertGreater(data['file_size'], 0)
        self.assertEqual(len(data['checksum']), 64)
        self.assertEqual(data['status'], Document.Status.UPLOADED)
        self.assertTrue(data['ocr_required'])
        self.assertTrue(data['has_file'])
        self.assertIsNotNone(data['download_url'])
        self.assertIsNotNone(data['uploaded_at'])

    def test_valid_upload_moves_sprint_from_draft_to_collecting(self):
        self._auth(self.iqac)
        self.assertEqual(self.sprint.status, Sprint.Status.DRAFT)
        self._upload()
        self.sprint.refresh_from_db()
        self.assertEqual(self.sprint.status, Sprint.Status.COLLECTING)

    def test_upload_without_trailing_slash_matches_frontend_client(self):
        self._auth(self.iqac)
        response = self.client.post(
            f'/api/v1/sprints/{self.sprint.id}/upload-file',
            {'file': make_pdf(), 'document_type': 'naac_ssr'}, format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_upload_with_future_document_type_is_accepted(self):
        self._auth(self.iqac)
        response = self._upload(document_type='ai_ethics_charter_2027')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['document_type'], 'ai_ethics_charter_2027')
        self.assertEqual(response.data['document_type_label'], 'Ai Ethics Charter 2027')

    def test_invalid_document_type_format_rejected(self):
        self._auth(self.iqac)
        response = self._upload(document_type='Not A Valid Slug!')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # -- invalid file --------------------------------------------------------

    def test_disallowed_file_extension_rejected(self):
        self._auth(self.iqac)
        bad_file = SimpleUploadedFile('virus.exe', b'MZ...', content_type='application/x-msdownload')
        response = self._upload(file=bad_file)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('file', response.data)

    @override_settings(MAX_DOCUMENT_UPLOAD_SIZE=10)
    def test_oversized_file_rejected(self):
        self._auth(self.iqac)
        response = self._upload()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('file', response.data)

    def test_no_document_created_when_upload_invalid(self):
        self._auth(self.iqac)
        self._upload(file=SimpleUploadedFile('bad.exe', b'x', content_type='application/x-msdownload'))
        self.assertEqual(Document.objects.count(), 0)

    # -- duplicate checksum ------------------------------------------------

    def test_duplicate_checksum_within_same_sprint_rejected(self):
        self._auth(self.iqac)
        first = self._upload()
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)

        duplicate = self._upload(file=make_pdf(name='naac_ssr_copy.pdf'))
        self.assertEqual(duplicate.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('file', duplicate.data)
        self.assertEqual(Document.objects.count(), 1)

    def test_same_file_can_be_uploaded_to_a_different_sprint(self):
        self._auth(self.iqac)
        self._upload()
        other_sprint = Sprint.objects.create(institution=self.institution, mode=Sprint.SprintMode.QUICK_CRI)
        response = self.client.post(
            f'/api/v1/sprints/{other_sprint.id}/upload-file/',
            {'file': make_pdf(), 'document_type': 'naac_ssr'}, format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    # -- unauthorized upload -------------------------------------------------

    def test_unauthenticated_upload_rejected(self):
        response = self._upload()
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_upload_from_outside_institution_rejected(self):
        self._auth(self.outsider)
        response = self._upload()
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Document.objects.count(), 0)

    # -- listing -------------------------------------------------------------

    def test_document_listing_scoped_to_sprint_and_institution(self):
        self._auth(self.iqac)
        self._upload()
        response = self.client.get(f'/api/v1/sprints/{self.sprint.id}/documents/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_document_listing_forbidden_for_outsider(self):
        self._auth(self.iqac)
        self._upload()
        self._auth(self.outsider)
        response = self.client.get(f'/api/v1/sprints/{self.sprint.id}/documents/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_documents_endpoint_is_read_only(self):
        self._auth(self.iqac)
        response = self.client.post(f'/api/v1/sprints/{self.sprint.id}/documents/', {
            'document_type': 'naac_ssr', 'original_filename': 'sneaky.pdf',
        })
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


class DocumentDetailTests(APITestCase):
    def setUp(self):
        self.institution = Institution.objects.create(name='MKCE', city='Karur', state='TN')
        self.other_institution = Institution.objects.create(name='Other', city='X', state='Y')
        self.sprint = Sprint.objects.create(institution=self.institution, mode=Sprint.SprintMode.VERIFIED_CRI)

        self.uploader = self._make_user('hod@test.edu', User.Role.HOD, self.institution)
        self.viewer = self._make_user('viewer@test.edu', User.Role.VIEWER, self.institution)
        self.other_hod = self._make_user('other_hod@test.edu', User.Role.HOD, self.institution)
        self.institution_admin = self._make_user(
            'admin@test.edu', User.Role.INSTITUTION_ADMIN, self.institution,
        )
        self.outsider = self._make_user('outsider@test.edu', User.Role.HOD, self.other_institution)

        self._auth(self.uploader)
        upload = self.client.post(
            f'/api/v1/sprints/{self.sprint.id}/upload-file/',
            {'file': make_pdf(), 'document_type': 'naac_ssr'}, format='multipart',
        )
        self.document = Document.objects.get(id=upload.data['id'])

    @staticmethod
    def _make_user(email, role, institution):
        return User.objects.create_user(
            email=email, username=email.split('@')[0], password=PASSWORD,
            first_name='Test', last_name=role, role=role, institution=institution,
        )

    def _auth(self, user):
        login = self.client.post('/api/v1/auth/login/', {'email': user.email, 'password': PASSWORD})
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {login.data["access_token"]}')

    # -- retrieve --------------------------------------------------------

    def test_retrieve_document(self):
        self._auth(self.uploader)
        response = self.client.get(f'/api/v1/documents/{self.document.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], str(self.document.id))

    def test_retrieve_forbidden_for_outsider(self):
        self._auth(self.outsider)
        response = self.client.get(f'/api/v1/documents/{self.document.id}/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # -- patch permissions -------------------------------------------------

    def test_owner_can_patch_own_document(self):
        self._auth(self.uploader)
        response = self.client.patch(f'/api/v1/documents/{self.document.id}/', {'title': 'Renamed'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], 'Renamed')

    def test_non_owner_non_viewer_can_patch(self):
        self._auth(self.other_hod)
        response = self.client.patch(f'/api/v1/documents/{self.document.id}/', {'title': 'Reclassified'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_viewer_cannot_patch_someone_elses_document(self):
        self._auth(self.viewer)
        response = self.client.patch(f'/api/v1/documents/{self.document.id}/', {'title': 'Nope'})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_file_integrity_fields_are_read_only(self):
        self._auth(self.uploader)
        original_checksum = self.document.checksum
        response = self.client.patch(f'/api/v1/documents/{self.document.id}/', {
            'checksum': 'deadbeef', 'file_size': 999999,
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.document.refresh_from_db()
        self.assertEqual(self.document.checksum, original_checksum)

    # -- delete permissions -------------------------------------------------

    def test_owner_can_delete_own_document(self):
        self._auth(self.uploader)
        response = self.client.delete(f'/api/v1/documents/{self.document.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Document.objects.filter(id=self.document.id).exists())

    def test_unrelated_non_manager_cannot_delete(self):
        self._auth(self.other_hod)
        response = self.client.delete(f'/api/v1/documents/{self.document.id}/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Document.objects.filter(id=self.document.id).exists())

    def test_institution_admin_can_delete_others_document(self):
        self._auth(self.institution_admin)
        response = self.client.delete(f'/api/v1/documents/{self.document.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_outsider_cannot_delete(self):
        self._auth(self.outsider)
        response = self.client.delete(f'/api/v1/documents/{self.document.id}/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_deleting_document_removes_stored_file(self):
        self._auth(self.uploader)
        file_field = self.document.file
        self.assertTrue(file_field.storage.exists(file_field.name))
        self.client.delete(f'/api/v1/documents/{self.document.id}/')
        self.assertFalse(file_field.storage.exists(file_field.name))

    # -- secure download -----------------------------------------------------

    def test_download_requires_authentication(self):
        self.client.credentials()
        response = self.client.get(f'/api/v1/documents/{self.document.id}/download')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_download_forbidden_for_outsider(self):
        self._auth(self.outsider)
        response = self.client.get(f'/api/v1/documents/{self.document.id}/download')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_download_returns_file_content_for_authorized_user(self):
        self._auth(self.uploader)
        response = self.client.get(f'/api/v1/documents/{self.document.id}/download')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn('attachment', response['Content-Disposition'])
        content = b''.join(response.streaming_content)
        self.assertIn(b'fake ssr content', content)

    def test_media_is_not_publicly_served(self):
        self.client.credentials()
        file_field = self.document.file
        response = self.client.get(f'/media/{file_field.name}')
        self.assertNotEqual(response.status_code, status.HTTP_200_OK)


# -- Google Drive Link data source --------------------------------------


class DriveImportUrlParsingTests(SimpleTestCase):
    def test_parses_standard_folder_link(self):
        self.assertEqual(
            parse_drive_folder_id('https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOp'),
            '1AbCdEfGhIjKlMnOp',
        )

    def test_parses_folder_link_with_user_index(self):
        self.assertEqual(
            parse_drive_folder_id('https://drive.google.com/drive/u/0/folders/1AbCdEfGhIjKlMnOp'),
            '1AbCdEfGhIjKlMnOp',
        )

    def test_parses_folder_link_with_query_string(self):
        self.assertEqual(
            parse_drive_folder_id('https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOp?usp=sharing'),
            '1AbCdEfGhIjKlMnOp',
        )

    def test_accepts_bare_folder_id(self):
        self.assertEqual(parse_drive_folder_id('1AbCdEfGhIjKlMnOp'), '1AbCdEfGhIjKlMnOp')

    def test_rejects_unrecognizable_input(self):
        with self.assertRaises(PermanentDriveImportError):
            parse_drive_folder_id('https://example.com/not-a-drive-link')

    def test_rejects_empty_input(self):
        with self.assertRaises(PermanentDriveImportError):
            parse_drive_folder_id('')


class ClassifyFilenameTests(SimpleTestCase):
    def test_matches_each_checklist_entry(self):
        cases = {
            '2025_NAAC_SSR_Final.pdf': 'naac_ssr',
            'AQAR_2024_Report.pdf': 'aqar_report',
            'AICTE_Approval_Letter.pdf': 'aicte_approval',
            'Faculty_Qualification_List.xlsx': 'faculty_master',
            'Student_Enrolment_Report.xlsx': 'student_strength',
            'Placement_Internship_Summary.pdf': 'placement_report',
            'BOS_Syllabus_2025.pdf': 'syllabi_curriculum',
            'Lab_Equipment_Inventory.xlsx': 'lab_inventory',
            'Research_Publication_Log.pdf': 'research_publications',
            'AI Policy Strategy Document.pdf': 'ai_policy_doc',
        }
        for filename, expected_type in cases.items():
            with self.subTest(filename=filename):
                self.assertEqual(classify_filename(filename), expected_type)

    def test_case_insensitive(self):
        self.assertEqual(classify_filename('naac_SSR_final.PDF'), 'naac_ssr')

    def test_returns_none_for_unrelated_filename(self):
        self.assertIsNone(classify_filename('Random_Notes.txt'))


class CreateDocumentFromFileTests(TestCase):
    """apps.documents.services.create_document_from_file() is the shared
    path both the manual upload endpoint and the Drive-import task go
    through -- these exercise it directly, with no HTTP request involved."""

    def setUp(self):
        self.institution = Institution.objects.create(name='MKCE', city='Karur', state='TN')
        self.sprint = Sprint.objects.create(institution=self.institution, mode=Sprint.SprintMode.VERIFIED_CRI)

    def test_creates_document_and_moves_sprint_to_collecting(self):
        self.assertEqual(self.sprint.status, Sprint.Status.DRAFT)
        document = create_document_from_file(
            sprint=self.sprint, file_obj=make_pdf(), document_type='naac_ssr', owner_role='IQAC_COORDINATOR',
        )
        self.assertEqual(document.status, Document.Status.UPLOADED)
        self.assertTrue(document.ocr_required)
        self.sprint.refresh_from_db()
        self.assertEqual(self.sprint.status, Sprint.Status.COLLECTING)

    def test_disallowed_extension_raises_validation_error(self):
        bad_file = SimpleUploadedFile('virus.exe', b'MZ...', content_type='application/x-msdownload')
        with self.assertRaises(DocumentValidationError):
            create_document_from_file(sprint=self.sprint, file_obj=bad_file, document_type='naac_ssr')

    def test_duplicate_checksum_within_sprint_raises_validation_error(self):
        create_document_from_file(sprint=self.sprint, file_obj=make_pdf(), document_type='naac_ssr')
        with self.assertRaises(DocumentValidationError):
            create_document_from_file(
                sprint=self.sprint, file_obj=make_pdf(name='copy.pdf'), document_type='naac_ssr',
            )


class _FakeDriveResponse:
    def __init__(self, status_code=200, json_data=None, content=b'', text=''):
        self.status_code = status_code
        self._json_data = json_data if json_data is not None else {}
        self.content = content
        self.text = text

    def json(self):
        return self._json_data


def _make_fake_drive_get(files=None, files_by_folder=None, downloads=None, list_status=200):
    """A `requests.get` side_effect. For files.list: pass `files` for a
    single flat listing regardless of which folder is queried, or
    `files_by_folder` ({folder_id: [file_dict, ...]}) to give each folder in
    a recursive scan (top-level + subfolders) its own response, keyed by the
    folder id embedded in the `q` parameter. `downloads` maps file id ->
    content bytes for both alt=media and /export requests."""
    downloads = downloads or {}

    def fake_get(url, params=None, timeout=None):
        if url == f'{DRIVE_API_BASE}/files':
            if list_status != 200:
                return _FakeDriveResponse(list_status, text='error')
            if files_by_folder is not None:
                match = re.search(r"'([^']+)' in parents", (params or {}).get('q', ''))
                folder_id = match.group(1) if match else None
                return _FakeDriveResponse(200, json_data={'files': files_by_folder.get(folder_id, [])})
            return _FakeDriveResponse(200, json_data={'files': files or []})
        file_id = url.rsplit('/', 2)[-2] if url.endswith('/export') else url.rsplit('/', 1)[-1]
        content = downloads.get(file_id)
        if content is None:
            return _FakeDriveResponse(404, text='not found')
        return _FakeDriveResponse(200, content=content)
    return fake_get


class ListDriveFolderFilesTests(SimpleTestCase):
    """Unit tests for the recursive folder walk itself, isolated from the
    Celery task and HTTP layer."""

    @patch('apps.documents.drive_import.requests.get')
    def test_recurses_into_subfolders(self, mock_get):
        mock_get.side_effect = _make_fake_drive_get(
            files_by_folder={
                'root': [
                    {'id': 'f1', 'name': 'a.pdf', 'mimeType': 'application/pdf'},
                    {'id': 'sub', 'name': 'Sub', 'mimeType': 'application/vnd.google-apps.folder'},
                ],
                'sub': [{'id': 'f2', 'name': 'b.pdf', 'mimeType': 'application/pdf'}],
            },
        )
        files = list_drive_folder_files('root', 'test-key', max_files=200)
        self.assertEqual({f['id'] for f in files}, {'f1', 'f2'})

    @patch('apps.documents.drive_import.requests.get')
    def test_respects_max_files_cap_across_folders(self, mock_get):
        mock_get.side_effect = _make_fake_drive_get(
            files_by_folder={
                'root': [{'id': f'f{i}', 'name': f'{i}.pdf', 'mimeType': 'application/pdf'} for i in range(5)],
            },
        )
        files = list_drive_folder_files('root', 'test-key', max_files=3)
        self.assertEqual(len(files), 3)

    @patch('apps.documents.drive_import.requests.get')
    def test_respects_max_folders_cap(self, mock_get):
        """root has 2 subfolders, each with one file; max_folders=2 means
        only root + one subfolder ever get visited."""
        mock_get.side_effect = _make_fake_drive_get(
            files_by_folder={
                'root': [
                    {'id': 'sub1', 'name': 'Sub1', 'mimeType': 'application/vnd.google-apps.folder'},
                    {'id': 'sub2', 'name': 'Sub2', 'mimeType': 'application/vnd.google-apps.folder'},
                ],
                'sub1': [{'id': 'f1', 'name': 'a.pdf', 'mimeType': 'application/pdf'}],
                'sub2': [{'id': 'f2', 'name': 'b.pdf', 'mimeType': 'application/pdf'}],
            },
        )
        files = list_drive_folder_files('root', 'test-key', max_files=200, max_folders=2)
        self.assertEqual(len(files), 1)


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True, GOOGLE_DRIVE_API_KEY='test-key')
class DriveImportTaskTests(APITestCase):
    def setUp(self):
        self.institution = Institution.objects.create(name='MKCE', city='Karur', state='TN')
        self.user = self._make_user('iqac@test.edu', User.Role.IQAC_COORDINATOR, self.institution)
        self.sprint = Sprint.objects.create(institution=self.institution, mode=Sprint.SprintMode.VERIFIED_CRI)
        self._auth(self.user)

    @staticmethod
    def _make_user(email, role, institution):
        return User.objects.create_user(
            email=email, username=email.split('@')[0], password=PASSWORD,
            first_name='Test', last_name=role, role=role, institution=institution,
        )

    def _auth(self, user):
        login = self.client.post('/api/v1/auth/login/', {'email': user.email, 'password': PASSWORD})
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {login.data["access_token"]}')

    def _start_import(self, drive_url='https://drive.google.com/drive/folders/abc123folder'):
        return self.client.post(
            f'/api/v1/sprints/{self.sprint.id}/drive-import-jobs/', {'drive_url': drive_url},
        )

    @patch('apps.documents.drive_import.requests.get')
    def test_happy_path_imports_matched_files_and_records_unmatched(self, mock_get):
        mock_get.side_effect = _make_fake_drive_get(
            files=[
                {'id': 'f1', 'name': 'NAAC_SSR_2025.pdf', 'mimeType': 'application/pdf'},
                {'id': 'f2', 'name': 'AQAR_Report.pdf', 'mimeType': 'application/pdf'},
                {'id': 'f3', 'name': 'Random_Notes.txt', 'mimeType': 'text/plain'},
            ],
            downloads={'f1': b'%PDF-1.4 ssr content', 'f2': b'%PDF-1.4 aqar content'},
        )
        response = self._start_import()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        job = DriveImportJob.objects.get(id=response.data['id'])
        self.assertEqual(job.status, DriveImportJob.Status.COMPLETED)
        self.assertEqual(job.files_scanned, 3)
        self.assertEqual(job.files_imported, 2)
        self.assertEqual(job.results['naac_ssr']['status'], 'found')
        self.assertEqual(job.results['aqar_report']['status'], 'found')
        self.assertEqual(job.results['aicte_approval']['status'], 'missing')
        self.assertIn('Random_Notes.txt', job.results['unmatched_files'])
        self.assertEqual(job.results['skipped_files'], [])
        self.assertEqual(Document.objects.filter(sprint=self.sprint).count(), 2)

    @patch('apps.documents.drive_import.requests.get')
    def test_scans_subfolders_recursively(self, mock_get):
        mock_get.side_effect = _make_fake_drive_get(
            files_by_folder={
                'abc123folder': [
                    {'id': 'f1', 'name': 'NAAC_SSR_2025.pdf', 'mimeType': 'application/pdf'},
                    {'id': 'sub1', 'name': 'Reports', 'mimeType': 'application/vnd.google-apps.folder'},
                ],
                'sub1': [
                    {'id': 'f2', 'name': 'AQAR_Report.pdf', 'mimeType': 'application/pdf'},
                    {'id': 'sub2', 'name': 'Nested', 'mimeType': 'application/vnd.google-apps.folder'},
                ],
                'sub2': [
                    {'id': 'f3', 'name': 'AICTE_Approval.pdf', 'mimeType': 'application/pdf'},
                ],
            },
            downloads={
                'f1': b'%PDF-1.4 ssr content', 'f2': b'%PDF-1.4 aqar content', 'f3': b'%PDF-1.4 aicte content',
            },
        )
        response = self._start_import()
        job = DriveImportJob.objects.get(id=response.data['id'])
        self.assertEqual(job.status, DriveImportJob.Status.COMPLETED)
        # The two folder entries themselves aren't counted as files -- only
        # the 3 real files across all three folder levels.
        self.assertEqual(job.files_scanned, 3)
        self.assertEqual(job.files_imported, 3)
        self.assertEqual(job.results['naac_ssr']['status'], 'found')
        self.assertEqual(job.results['aqar_report']['status'], 'found')
        self.assertEqual(job.results['aicte_approval']['status'], 'found')

    @patch('apps.documents.drive_import.requests.get')
    def test_google_doc_is_exported_and_imported_as_pdf(self, mock_get):
        mock_get.side_effect = _make_fake_drive_get(
            files=[
                {
                    'id': 'gdoc1', 'name': 'Faculty Qualification List',
                    'mimeType': 'application/vnd.google-apps.document',
                },
            ],
            downloads={'gdoc1': b'%PDF-1.4 exported content'},
        )
        response = self._start_import()
        job = DriveImportJob.objects.get(id=response.data['id'])
        self.assertEqual(job.status, DriveImportJob.Status.COMPLETED)
        self.assertEqual(job.results['faculty_master']['status'], 'found')

        document = Document.objects.get(sprint=self.sprint)
        self.assertEqual(document.original_filename, 'Faculty Qualification List.pdf')
        self.assertEqual(document.mime_type, 'application/pdf')

    @patch('apps.documents.drive_import.requests.get')
    def test_matched_file_failing_validation_is_skipped_not_fatal(self, mock_get):
        mock_get.side_effect = _make_fake_drive_get(
            files=[{'id': 'eq1', 'name': 'Equipment_List.exe', 'mimeType': 'application/x-msdownload'}],
            downloads={'eq1': b'MZ...'},
        )
        response = self._start_import()
        job = DriveImportJob.objects.get(id=response.data['id'])
        self.assertEqual(job.status, DriveImportJob.Status.COMPLETED)
        self.assertEqual(job.files_imported, 0)
        self.assertEqual(job.results['lab_inventory']['status'], 'missing')
        self.assertEqual(len(job.results['skipped_files']), 1)
        self.assertEqual(job.results['skipped_files'][0]['filename'], 'Equipment_List.exe')

    @patch('apps.documents.drive_import.requests.get')
    def test_private_folder_403_fails_with_actionable_message(self, mock_get):
        mock_get.return_value = _FakeDriveResponse(403, text='Forbidden')
        response = self._start_import()
        job = DriveImportJob.objects.get(id=response.data['id'])
        self.assertEqual(job.status, DriveImportJob.Status.FAILED)
        self.assertIn('Anyone with the link', job.error_message)

    @patch('apps.documents.drive_import.requests.get')
    def test_empty_folder_fails_with_clear_message(self, mock_get):
        mock_get.return_value = _FakeDriveResponse(200, json_data={'files': []})
        response = self._start_import()
        job = DriveImportJob.objects.get(id=response.data['id'])
        self.assertEqual(job.status, DriveImportJob.Status.FAILED)
        self.assertIn('No files were found', job.error_message)

    @override_settings(GOOGLE_DRIVE_API_KEY='')
    @patch('apps.documents.drive_import.requests.get')
    def test_missing_api_key_fails_immediately_without_network_call(self, mock_get):
        response = self._start_import()
        job = DriveImportJob.objects.get(id=response.data['id'])
        self.assertEqual(job.status, DriveImportJob.Status.FAILED)
        self.assertIn('not configured', job.error_message)
        mock_get.assert_not_called()

    @patch('apps.documents.drive_import.requests.get')
    def test_transient_network_error_reschedules_via_celery_retry(self, mock_get):
        mock_get.side_effect = requests.exceptions.ConnectionError('boom')
        response = self._start_import()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        job = DriveImportJob.objects.get(id=response.data['id'])
        self.assertEqual(job.status, DriveImportJob.Status.SCANNING)
        self.assertIn('Network error', job.error_message)


class DriveImportRetryDecisionLogicTests(TestCase):
    """Unit tests for the retry/backoff/exhaustion decision logic itself --
    same rationale as apps.extraction.tests.RetryDecisionLogicTests: eager
    mode runs a task once per `.delay()` and doesn't loop through retries,
    so exhaustion is tested by driving `_handle_recoverable` directly."""

    def setUp(self):
        institution = Institution.objects.create(name='MKCE', city='Karur', state='TN')
        sprint = Sprint.objects.create(institution=institution, mode=Sprint.SprintMode.VERIFIED_CRI)
        self.job = DriveImportJob.objects.create(
            sprint=sprint, drive_url='https://drive.google.com/drive/folders/abc123folder',
        )

    @staticmethod
    def _fake_task(retries):
        task = MagicMock()
        task.request.retries = retries

        def _raise(*args, **kwargs):
            raise RuntimeError('celery would reschedule here')
        task.retry.side_effect = _raise
        return task

    def test_schedules_a_retry_while_attempts_remain(self):
        task = self._fake_task(retries=0)
        with self.assertRaises(RuntimeError):
            _handle_recoverable(task, self.job, RecoverableDriveImportError('flaky'))

        self.job.refresh_from_db()
        self.assertEqual(self.job.status, DriveImportJob.Status.SCANNING)
        task.retry.assert_called_once()
        self.assertEqual(
            task.retry.call_args.kwargs['countdown'], settings.GOOGLE_DRIVE_IMPORT_RETRY_BACKOFF_SECONDS,
        )

    def test_gives_up_once_retries_are_exhausted(self):
        task = self._fake_task(retries=settings.GOOGLE_DRIVE_IMPORT_MAX_RETRIES)
        _handle_recoverable(task, self.job, RecoverableDriveImportError('never recovers'))

        self.job.refresh_from_db()
        self.assertEqual(self.job.status, DriveImportJob.Status.FAILED)
        self.assertIn('Failed after', self.job.error_message)
        task.retry.assert_not_called()


class DriveImportJobEndpointTests(APITestCase):
    """Auth/validation around the endpoint itself -- none of these reach
    run_drive_import_job.delay(), so no Celery/broker setup is needed."""

    def setUp(self):
        self.institution = Institution.objects.create(name='MKCE', city='Karur', state='TN')
        self.other_institution = Institution.objects.create(name='Other', city='X', state='Y')
        self.user = self._make_user('iqac@test.edu', User.Role.IQAC_COORDINATOR, self.institution)
        self.outsider = self._make_user('outsider@test.edu', User.Role.HOD, self.other_institution)
        self.sprint = Sprint.objects.create(institution=self.institution, mode=Sprint.SprintMode.VERIFIED_CRI)

    @staticmethod
    def _make_user(email, role, institution):
        return User.objects.create_user(
            email=email, username=email.split('@')[0], password=PASSWORD,
            first_name='Test', last_name=role, role=role, institution=institution,
        )

    def _auth(self, user):
        login = self.client.post('/api/v1/auth/login/', {'email': user.email, 'password': PASSWORD})
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {login.data["access_token"]}')

    def test_invalid_drive_url_rejected_with_400(self):
        self._auth(self.user)
        response = self.client.post(
            f'/api/v1/sprints/{self.sprint.id}/drive-import-jobs/', {'drive_url': 'not a drive link'},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(DriveImportJob.objects.count(), 0)

    def test_unauthenticated_cannot_start_import(self):
        response = self.client.post(
            f'/api/v1/sprints/{self.sprint.id}/drive-import-jobs/',
            {'drive_url': 'https://drive.google.com/drive/folders/abc123folder'},
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_outsider_cannot_start_import(self):
        self._auth(self.outsider)
        response = self.client.post(
            f'/api/v1/sprints/{self.sprint.id}/drive-import-jobs/',
            {'drive_url': 'https://drive.google.com/drive/folders/abc123folder'},
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(DriveImportJob.objects.count(), 0)

    def test_list_scoped_to_sprint_newest_first(self):
        self._auth(self.user)
        older = DriveImportJob.objects.create(
            sprint=self.sprint, drive_url='https://drive.google.com/drive/folders/older',
        )
        newer = DriveImportJob.objects.create(
            sprint=self.sprint, drive_url='https://drive.google.com/drive/folders/newer',
        )
        response = self.client.get(f'/api/v1/sprints/{self.sprint.id}/drive-import-jobs/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([j['id'] for j in response.data], [str(newer.id), str(older.id)])
