from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.institutions.models import Institution
from apps.sprints.models import Sprint

from .models import Document

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
