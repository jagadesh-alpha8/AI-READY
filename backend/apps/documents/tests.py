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

from .constants import normalize_checklist_type
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
        # The uploader's choice is the assigned type; the AI hasn't read it yet.
        self.assertEqual(data['document_type_source'], Document.TypeSource.UPLOADER)
        self.assertEqual(data['classification_status'], Document.ClassificationStatus.PENDING)
        self.assertEqual((data['ai_document_type'], data['ai_document_type_label'], data['ai_confidence']), ('', None, None))

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
            {'file': make_pdf(name='renamed_ssr_copy.pdf'), 'document_type': 'naac_ssr'}, format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['original_filename'], 'renamed_ssr_copy.pdf')
        self.assertEqual(response.data['checksum'], Document.objects.get(sprint=self.sprint).checksum)
        self.assertEqual(Document.objects.filter(sprint=other_sprint).count(), 1)

    def test_changed_file_content_creates_a_linked_version_in_the_same_sprint(self):
        self._auth(self.iqac)
        first = self._upload(file=make_pdf(name='ssr.pdf', content=b'%PDF-1.4 version one'))
        second = self._upload(file=make_pdf(name='ssr.pdf', content=b'%PDF-1.4 version two'))

        self.assertEqual(first.status_code, status.HTTP_201_CREATED, first.data)
        self.assertEqual(second.status_code, status.HTTP_201_CREATED, second.data)
        old = Document.objects.get(id=first.data['id'])
        new = Document.objects.get(id=second.data['id'])
        self.assertEqual((old.version_number, old.superseded_at), (1, new.uploaded_at))
        self.assertEqual((new.version_number, new.previous_version_id), (2, old.id))
        self.assertNotEqual(old.checksum, new.checksum)

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

    def test_retyping_a_filename_guess_makes_it_the_uploaders_choice(self):
        Document.objects.filter(id=self.document.id).update(document_type_source=Document.TypeSource.FILENAME)
        self._auth(self.uploader)

        self.client.patch(f'/api/v1/documents/{self.document.id}/', {'title': 'Renamed'})
        self.document.refresh_from_db()
        self.assertEqual(self.document.document_type_source, Document.TypeSource.FILENAME)  # type unchanged

        response = self.client.patch(f'/api/v1/documents/{self.document.id}/', {'document_type': 'aqar_report'})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['document_type_source'], Document.TypeSource.UPLOADER)
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


class DocumentConfirmCategoryTests(APITestCase):
    """POST /documents/{id}/confirm-category: a person settles a document's AI category."""

    setUp_detail = DocumentDetailTests.setUp
    _make_user = staticmethod(DocumentDetailTests._make_user)
    _auth = DocumentDetailTests._auth

    def setUp(self):
        self.setUp_detail()
        # The AI read it as a low-confidence NAAC SSR.
        Document.objects.filter(id=self.document.id).update(
            classification_status=Document.ClassificationStatus.NEEDS_REVIEW, ai_document_type='naac_ssr',
            ai_confidence=0.45, ai_reasoning='Mentions criteria, but no SSR title page.',
        )

    def _confirm(self, body, user=None):
        if user is not None:
            self._auth(user)
        return self.client.post(f'/api/v1/documents/{self.document.id}/confirm-category', body, format='json')

    def _assert_unchanged(self):
        self.document.refresh_from_db()
        self.assertEqual(
            (self.document.classification_status, self.document.ai_document_type, self.document.category_confirmed_at),
            (Document.ClassificationStatus.NEEDS_REVIEW, 'naac_ssr', None),
        )

    def test_choosing_a_category_classifies_it_and_records_who_and_when(self):
        response = self._confirm({'category': 'aqar_report'}, user=self.other_hod)

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['classification_status'], 'classified')
        self.assertEqual(response.data['ai_document_type'], 'aqar_report')
        self.assertEqual(response.data['ai_document_type_label'], 'AQAR / Annual Quality Assurance Report')
        self.assertEqual(response.data['category_confirmed_by'], self.other_hod.id)
        self.assertEqual(response.data['category_confirmed_by_name'], self.other_hod.get_full_name())
        self.assertIsNotNone(response.data['category_confirmed_at'])

        self.document.refresh_from_db()
        self.assertTrue(self.document.category_manually_confirmed)
        self.assertEqual(self.document.category_confirmed_by, self.other_hod)
        # The AI's own verdict and the assigned type are kept for the record.
        self.assertEqual(self.document.ai_confidence, 0.45)
        self.assertEqual(self.document.ai_reasoning, 'Mentions criteria, but no SSR title page.')
        self.assertEqual((self.document.document_type, self.document.document_type_source), ('naac_ssr', 'uploader'))

    def test_null_marks_it_not_a_checklist_document(self):
        response = self._confirm({'category': None}, user=self.uploader)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.document.refresh_from_db()
        self.assertEqual(self.document.classification_status, Document.ClassificationStatus.UNCLASSIFIED)
        self.assertEqual(self.document.ai_document_type, '')
        self.assertEqual(self.document.category_confirmed_by, self.uploader)

    def test_an_ai_classified_document_can_be_overridden(self):
        Document.objects.filter(id=self.document.id).update(
            classification_status=Document.ClassificationStatus.CLASSIFIED, ai_confidence=0.92,
        )
        response = self._confirm({'category': 'faculty_master'}, user=self.institution_admin)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(
            (response.data['classification_status'], response.data['ai_document_type']), ('classified', 'faculty_master'),
        )

    def test_aliases_are_normalized_to_the_checklist_slug(self):
        response = self._confirm({'category': 'AQAR'}, user=self.uploader)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['ai_document_type'], 'aqar_report')

    def test_anything_but_a_checklist_category_or_null_is_rejected(self):
        self._auth(self.uploader)
        for body in ({'category': 'campus_brochure'}, {'category': 'supporting_document'}, {'category': ''}, {}):
            with self.subTest(body=body):
                response = self._confirm(body)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn('category', response.data)
        self._assert_unchanged()

    def test_a_viewer_cannot_confirm(self):
        response = self._confirm({'category': 'aqar_report'}, user=self.viewer)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self._assert_unchanged()

    def test_another_institution_cannot_confirm(self):
        response = self._confirm({'category': 'aqar_report'}, user=self.outsider)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self._assert_unchanged()

    def test_requires_authentication(self):
        self.client.credentials()
        self.assertEqual(self._confirm({'category': 'aqar_report'}).status_code, status.HTTP_401_UNAUTHORIZED)
        self._assert_unchanged()

    def test_the_document_list_shows_who_confirmed(self):
        self._confirm({'category': 'aqar_report'}, user=self.other_hod)
        row = self.client.get(f'/api/v1/sprints/{self.sprint.id}/documents').data[0]
        self.assertEqual(row['category_confirmed_by_name'], self.other_hod.get_full_name())
        self.assertEqual(row['classification_status'], 'classified')

    def test_the_document_api_still_cannot_write_the_confirmation(self):
        self._auth(self.uploader)
        response = self.client.patch(f'/api/v1/documents/{self.document.id}/', {
            'category_confirmed_by': str(self.uploader.id), 'category_confirmed_at': '2026-01-01T00:00:00Z',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self._assert_unchanged()


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


class NormalizeChecklistTypeTests(SimpleTestCase):
    def test_checklist_slugs_and_aliases_are_recognised(self):
        cases = {
            'naac_ssr': 'naac_ssr', ' AQAR_Report ': 'aqar_report', 'aqar': 'aqar_report',
            'faculty_master_list': 'faculty_master', 'research publication report': 'research_publications',
            'ai-policy-doc': 'ai_policy_doc',
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(normalize_checklist_type(value), expected)

    def test_anything_else_is_not_a_category(self):
        for value in (None, '', 'supporting_document', 'unclassified', 'campus_brochure', 42):
            with self.subTest(value=value):
                self.assertIsNone(normalize_checklist_type(value))


class BackfillTypeSourceMigrationTests(TestCase):
    """0004's data step labels documents earlier Drive imports created."""

    def test_drive_imported_documents_get_their_real_source(self):
        from importlib import import_module

        from django.apps import apps as django_apps

        sprint = Sprint.objects.create(
            institution=Institution.objects.create(name='MKCE', city='Karur', state='TN'),
            mode=Sprint.SprintMode.VERIFIED_CRI,
        )
        slot_doc, extra_doc, manual_doc = (
            create_document_from_file(
                sprint=sprint, file_obj=make_pdf(name=name, content=name.encode()), document_type=doc_type,
            )
            for name, doc_type in (('ssr.pdf', 'naac_ssr'), ('brochure.pdf', 'supporting_document'),
                                   ('aqar.pdf', 'aqar_report'))
        )
        DriveImportJob.objects.create(sprint=sprint, drive_url='https://drive.google.com/drive/folders/x', results={
            'naac_ssr': {'status': 'found', 'filename': 'ssr.pdf', 'document_id': str(slot_doc.id)},
            'aqar_report': {'status': 'missing', 'filename': None, 'document_id': None},
            'additional_files': [{'filename': 'brochure.pdf', 'folder': '', 'document_id': str(extra_doc.id)}],
            'skipped_files': [], 'progress': {'processed': 2, 'total': 2, 'current_file': ''},
        })

        import_module('apps.documents.migrations.0004_document_ai_classification').backfill_type_source(
            django_apps, None,
        )

        sources = dict(Document.objects.values_list('original_filename', 'document_type_source'))
        self.assertEqual(sources, {'ssr.pdf': 'filename', 'brochure.pdf': 'none', 'aqar.pdf': 'uploader'})
        self.assertEqual(Document.objects.get(id=extra_doc.id).document_type, 'supporting_document')  # label kept


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
        self.assertEqual({(f['id'], f['folder_path']) for f in files}, {('f1', ''), ('f2', 'Sub')})

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

    @patch('apps.documents.drive_import.requests.get')
    def test_stop_when_halts_the_walk_early(self, mock_get):
        """Once `stop_when` is satisfied, a folder deeper in the tree must
        never be requested at all -- that early exit is the whole point."""
        mock_get.side_effect = _make_fake_drive_get(
            files_by_folder={
                'root': [
                    {'id': 'f1', 'name': 'a.pdf', 'mimeType': 'application/pdf'},
                    {'id': 'deep', 'name': 'Deep', 'mimeType': 'application/vnd.google-apps.folder'},
                ],
                'deep': [{'id': 'f2', 'name': 'b.pdf', 'mimeType': 'application/pdf'}],
            },
        )
        files = list_drive_folder_files(
            'root', 'test-key', max_files=200, stop_when=lambda found: len(found) >= 1,
        )
        self.assertEqual([f['id'] for f in files], ['f1'])
        requested = [str(call.kwargs.get('params', {}).get('q', '')) for call in mock_get.call_args_list]
        self.assertFalse(
            any('deep' in q for q in requested),
            'the walk stopped, so the subfolder should never have been listed',
        )

    @patch('apps.documents.drive_import.requests.get')
    def test_concurrent_level_preserves_listing_order(self, mock_get):
        """Folders in a level are fetched concurrently, but the files come back
        in folder order regardless of which request finished first. The
        importer claims a checklist slot with the FIRST matching filename, so a
        reordered listing would silently change which file wins."""
        mock_get.side_effect = _make_fake_drive_get(
            files_by_folder={
                'root': [
                    {'id': 's1', 'name': 'S1', 'mimeType': 'application/vnd.google-apps.folder'},
                    {'id': 's2', 'name': 'S2', 'mimeType': 'application/vnd.google-apps.folder'},
                    {'id': 's3', 'name': 'S3', 'mimeType': 'application/vnd.google-apps.folder'},
                ],
                's1': [{'id': 'a', 'name': 'a.pdf', 'mimeType': 'application/pdf'}],
                's2': [{'id': 'b', 'name': 'b.pdf', 'mimeType': 'application/pdf'}],
                's3': [{'id': 'c', 'name': 'c.pdf', 'mimeType': 'application/pdf'}],
            },
        )
        for _ in range(5):
            files = list_drive_folder_files('root', 'test-key', max_files=200)
            self.assertEqual([f['id'] for f in files], ['a', 'b', 'c'])


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
        self.assertEqual(
            job.results['skipped_files'], [{'filename': 'Random_Notes.txt', 'reason': 'Unsupported file type.'}],
        )
        self.assertEqual(job.results['additional_files'], [])
        self.assertEqual(Document.objects.filter(sprint=self.sprint).count(), 2)

    @patch('apps.documents.drive_import.requests.get')
    def test_imports_every_file_from_root_and_subfolders_not_just_checklist_matches(self, mock_get):
        mock_get.side_effect = _make_fake_drive_get(
            files_by_folder={
                'abc123folder': [
                    {'id': 'f1', 'name': 'NAAC_SSR_2025.pdf', 'mimeType': 'application/pdf'},
                    {'id': 'f2', 'name': 'Campus_Brochure.pdf', 'mimeType': 'application/pdf'},
                    {'id': 'sub1', 'name': 'Misc', 'mimeType': 'application/vnd.google-apps.folder'},
                ],
                'sub1': [
                    # Second SSR match -- slot already claimed, still imported.
                    {'id': 'f3', 'name': 'NAAC_SSR_2024.pdf', 'mimeType': 'application/pdf'},
                    {'id': 'f4', 'name': 'Budget.xlsx', 'mimeType': 'application/octet-stream'},
                ],
            },
            downloads={
                'f1': b'%PDF-1.4 ssr 2025', 'f2': b'%PDF-1.4 brochure',
                'f3': b'%PDF-1.4 ssr 2024', 'f4': b'PK budget',
            },
        )
        response = self._start_import()
        job = DriveImportJob.objects.get(id=response.data['id'])
        self.assertEqual(job.status, DriveImportJob.Status.COMPLETED)
        self.assertEqual(job.files_scanned, 4)
        self.assertEqual(job.files_imported, 4)
        self.assertEqual(job.results['naac_ssr']['filename'], 'NAAC_SSR_2025.pdf')
        self.assertEqual(
            [(f['folder'], f['filename']) for f in job.results['additional_files']],
            [('', 'Campus_Brochure.pdf'), ('Misc', 'NAAC_SSR_2024.pdf'), ('Misc', 'Budget.xlsx')],
        )
        # No silent 'supporting_document': a filename keyword match is kept as
        # a hint (even for an already-claimed slot); no match is 'unclassified'
        # until the AI reads the content during extraction.
        self.assertEqual(
            sorted(Document.objects.filter(sprint=self.sprint).values_list(
                'original_filename', 'document_type', 'document_type_source', 'classification_status',
            )),
            [
                ('Budget.xlsx', 'unclassified', 'none', 'pending'),
                ('Campus_Brochure.pdf', 'unclassified', 'none', 'pending'),
                ('NAAC_SSR_2024.pdf', 'naac_ssr', 'filename', 'pending'),
                ('NAAC_SSR_2025.pdf', 'naac_ssr', 'filename', 'pending'),
            ],
        )
        self.assertFalse(Document.objects.filter(document_type='supporting_document').exists())
        # Progress is written per file while importing; it ends fully processed.
        self.assertEqual(job.results['progress'], {'processed': 4, 'total': 4, 'current_file': ''})

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
    def test_stop_mid_import_keeps_imported_files_and_imports_no_more(self, mock_get):
        mock_get.side_effect = _make_fake_drive_get(
            files=[
                {'id': 'f1', 'name': 'NAAC_SSR_2025.pdf', 'mimeType': 'application/pdf'},
                {'id': 'f2', 'name': 'AQAR_Report.pdf', 'mimeType': 'application/pdf'},
                {'id': 'f3', 'name': 'AICTE_Approval.pdf', 'mimeType': 'application/pdf'},
            ],
            downloads={'f1': b'%PDF-1.4 a', 'f2': b'%PDF-1.4 b', 'f3': b'%PDF-1.4 c'},
        )
        calls = {'n': 0}

        def stop_after_first_file(job):
            # Simulates the user pressing Stop once the first file has landed.
            calls['n'] += 1
            if calls['n'] == 2:
                DriveImportJob.objects.filter(id=job.id).update(status=DriveImportJob.Status.CANCELLED)
                return True
            return False

        with patch('apps.documents.tasks._is_cancelled', side_effect=stop_after_first_file):
            response = self._start_import()
        job = DriveImportJob.objects.get(id=response.data['id'])
        self.assertEqual(job.status, DriveImportJob.Status.CANCELLED)
        self.assertEqual(job.files_imported, 1)
        self.assertEqual(Document.objects.filter(sprint=self.sprint).count(), 1)

    def test_stop_endpoint_cancels_active_job(self):
        job = DriveImportJob.objects.create(
            sprint=self.sprint, drive_url='https://drive.google.com/drive/folders/abc123folder',
            status=DriveImportJob.Status.DOWNLOADING,
        )
        response = self.client.post(f'/api/v1/sprints/{self.sprint.id}/drive-import-jobs/{job.id}/stop')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['status'], 'cancelled')

    def test_stop_endpoint_rejects_finished_job(self):
        job = DriveImportJob.objects.create(
            sprint=self.sprint, drive_url='https://drive.google.com/drive/folders/abc123folder',
            status=DriveImportJob.Status.COMPLETED,
        )
        response = self.client.post(f'/api/v1/sprints/{self.sprint.id}/drive-import-jobs/{job.id}/stop')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        job.refresh_from_db()
        self.assertEqual(job.status, DriveImportJob.Status.COMPLETED)

    @patch('apps.documents.drive_import.requests.get')
    def test_transient_network_error_reschedules_via_celery_retry(self, mock_get):
        mock_get.side_effect = requests.exceptions.ConnectionError('boom')
        response = self._start_import()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        job = DriveImportJob.objects.get(id=response.data['id'])
        self.assertEqual(job.status, DriveImportJob.Status.SCANNING)
        self.assertIn('Network error', job.error_message)

    @patch('apps.documents.drive_import.requests.get')
    def test_automated_traffic_block_while_listing_is_retried_not_failed(self, mock_get):
        mock_get.return_value = _FakeDriveResponse(403, text=_SORRY_PAGE)
        response = self._start_import()
        job = DriveImportJob.objects.get(id=response.data['id'])
        self.assertEqual(job.status, DriveImportJob.Status.SCANNING)  # rescheduled, like a network error
        self.assertIn('automated traffic', job.error_message)
        self.assertNotIn('Anyone with the link', job.error_message)

    @patch('apps.documents.drive_import._sleep')
    @patch('apps.documents.drive_import.requests.get')
    def test_a_file_blocked_on_every_try_is_skipped_with_googles_reason(self, mock_get, _sleep):
        listing = _make_fake_drive_get(files=[
            {'id': 'f1', 'name': 'NAAC_SSR_2024.pdf', 'mimeType': 'application/pdf'}])

        def fake_get(url, params=None, timeout=None):
            if url == f'{DRIVE_API_BASE}/files':
                return listing(url, params=params, timeout=timeout)
            return _FakeDriveResponse(403, text=_SORRY_PAGE)
        mock_get.side_effect = fake_get
        response = self._start_import()
        job = DriveImportJob.objects.get(id=response.data['id'])
        self.assertEqual((job.status, job.files_imported), (DriveImportJob.Status.COMPLETED, 0))
        reason = job.results['skipped_files'][0]['reason']
        self.assertTrue(reason.startswith('Google is temporarily blocking requests from this network'), reason)
        self.assertEqual(_sleep.call_count, 2)  # tried 3 times


_SORRY_PAGE = ('<html><head><title>Sorry...</title></head><body><h1>We\'re sorry...</h1><p>... but your computer '
               'or network may be sending automated queries. To protect our users, we can\'t process your request '
               'right now.</p></body></html>')


def _drive_error(code, reason, message):
    return _FakeDriveResponse(code, json_data={'error': {'code': code, 'message': message,
                                                         'errors': [{'reason': reason, 'message': message}]}})


class DriveErrorReasonTests(SimpleTestCase):
    """Google's own reason is shown, and only what can clear up by itself is retried."""

    def _raise(self, resp):
        from .drive_import import _raise_for_drive_status
        _raise_for_drive_status(resp, context="downloading 'ssr.pdf'")

    def test_the_automated_traffic_page_is_recoverable_and_says_so(self):
        with self.assertRaises(RecoverableDriveImportError) as ctx:
            self._raise(_FakeDriveResponse(403, text=_SORRY_PAGE))
        self.assertIn('blocking requests from this network as automated traffic', str(ctx.exception))
        self.assertIn('switch to another network', str(ctx.exception))

    def test_rate_limits_are_recoverable(self):
        for resp in (_drive_error(403, 'userRateLimitExceeded', 'User rate limit exceeded.'),
                     _FakeDriveResponse(429, text='Too Many Requests')):
            with self.assertRaises(RecoverableDriveImportError) as ctx:
                self._raise(resp)
            self.assertIn('rate-limiting', str(ctx.exception))

    def test_googles_reason_and_message_are_shown_with_what_to_do(self):
        cases = {
            'cannotDownloadFile': ('The user does not have sufficient permissions for file x.', 'turned off downloading'),
            'downloadQuotaExceeded': ('The download quota for this file has been exceeded.', 'resets within about a day'),
            'keyInvalid': ('API key not valid. Please pass a valid API key.', 'GOOGLE_DRIVE_API_KEY'),
        }
        for reason, (message, hint) in cases.items():
            with self.assertRaises(PermanentDriveImportError) as ctx:
                self._raise(_drive_error(403, reason, message))
            text = str(ctx.exception)
            self.assertIn(f'HTTP 403 {reason}', text)
            self.assertIn(message, text)
            self.assertIn(hint, text)
            self.assertNotIn('Anyone with the link', text)

    def test_a_bare_403_still_points_at_sharing(self):
        with self.assertRaises(PermanentDriveImportError) as ctx:
            self._raise(_FakeDriveResponse(403, text='Forbidden'))
        self.assertIn('Anyone with the link', str(ctx.exception))

    @patch('apps.documents.drive_import._sleep')
    @patch('apps.documents.drive_import.requests.get')
    def test_a_download_is_retried_after_a_block_and_then_succeeds(self, mock_get, sleep):
        from .drive_import import download_drive_file
        mock_get.side_effect = [_FakeDriveResponse(403, text=_SORRY_PAGE),
                                _drive_error(403, 'userRateLimitExceeded', 'Slow down.'),
                                _FakeDriveResponse(200, content=b'%PDF-1.4')]
        content, name, _mime = download_drive_file({'id': 'f1', 'name': 'ssr.pdf', 'mimeType': 'application/pdf'}, 'k')
        self.assertEqual((content, name, mock_get.call_count), (b'%PDF-1.4', 'ssr.pdf', 3))
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [5, 10])

    @patch('apps.documents.drive_import._sleep')
    @patch('apps.documents.drive_import.requests.get')
    def test_a_permanent_refusal_is_not_retried(self, mock_get, sleep):
        from .drive_import import download_drive_file
        mock_get.return_value = _drive_error(403, 'cannotDownloadFile', 'Download disabled.')
        with self.assertRaises(PermanentDriveImportError):
            download_drive_file({'id': 'f1', 'name': 'ssr.pdf', 'mimeType': 'application/pdf'}, 'k')
        self.assertEqual((mock_get.call_count, sleep.call_count), (1, 0))


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


class ViewerIsReadOnlyTests(APITestCase):
    """A viewer can read a sprint's documents but not upload, import or run AI processing."""

    setUp = DocumentUploadTests.setUp
    _make_user = staticmethod(DocumentUploadTests._make_user)
    _auth = DocumentUploadTests._auth
    _upload = DocumentUploadTests._upload

    def test_viewer_cannot_upload_but_hod_can(self):
        self._auth(self.viewer)
        self.assertEqual(self._upload().status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.get(f'/api/v1/sprints/{self.sprint.id}/documents').status_code, status.HTTP_200_OK)
        self._auth(self.hod)
        self.assertEqual(self._upload().status_code, status.HTTP_201_CREATED)

    def test_viewer_cannot_import_from_drive_or_start_extraction(self):
        self._auth(self.viewer)
        drive = self.client.post(f'/api/v1/sprints/{self.sprint.id}/drive-import-jobs',
                                 {'folder_url': 'https://drive.google.com/drive/folders/abc'}, format='json')
        self.assertEqual(drive.status_code, status.HTTP_403_FORBIDDEN)
        start = self.client.post(f'/api/v1/sprints/{self.sprint.id}/extraction-jobs', {}, format='json')
        self.assertEqual(start.status_code, status.HTTP_403_FORBIDDEN)
        cancel = self.client.post(f'/api/v1/extraction-jobs/sprints/{self.sprint.id}/cancel', {}, format='json')
        self.assertEqual(cancel.status_code, status.HTTP_403_FORBIDDEN)
