import os
import tempfile

import openpyxl
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.institutions.models import Institution

from .models import Authority, SourceAuditEvent, SourceDocument, SourceFeed, SourceVersion
from .services.register_import import apply_register, read_register

PASSWORD = 'Str0ng!DevPassw0rd'
SHA = 'a' * 64
HEADERS = ['Row ID', 'Assigned To', 'Category', 'Authority', 'Authority Kind', 'Source Role (suggested)', 'Source Code',
           'Official Title (exact)', 'Document Type', 'Version / Edition', 'Issued On', 'Effective From',
           'Current Status', 'Supersedes / Amends', 'Applies To', 'Programme / Trade Scope', 'Listing Page URL',
           'Direct Document URL', 'Official Domain?', 'Collection Status', 'Local File (folder/name)', 'File Size (KB)',
           'Pages', 'SHA-256 Checksum', 'Licensed Content?', 'Review Cadence (months)', 'Watcher Feed Type',
           'Related Benchmark IDs', 'Collected On', 'Notes']

GOOD = {'Row ID': 'S-001', 'Category': '2. Higher-Education Regulation', 'Authority': 'UGC',
        'Authority Kind': 'regulatory', 'Source Role (suggested)': 'Mandatory', 'Source Code': 'UGC-005',
        'Official Title (exact)': 'UGC Plagiarism Regulations, 2018', 'Document Type': 'Regulation',
        'Version / Edition': '2018', 'Issued On': '23-Jul-2018', 'Current Status': 'Current', 'Applies To': 'HEIs',
        'Listing Page URL': 'https://www.ugc.gov.in/Regulations',
        'Direct Document URL': 'https://www.ugc.gov.in/pdfnews/plagiarism.pdf', 'Collection Status': 'Downloaded',
        'Local File (folder/name)': 'https://drive.google.com/file/d/1AbCdEfGhIjKlMnOp/view', 'File Size (KB)': 300, 'Pages': 8,
        'SHA-256 Checksum': SHA, 'Licensed Content?': 'No', 'Review Cadence (months)': 3,
        'Watcher Feed Type': 'document_index'}


def make_register(rows):
    """A workbook laid out like the intern tracker: title rows, header on row 4."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Source Register'
    ws['A1'] = 'InGage Source Library - Source Register'
    for i, h in enumerate(HEADERS, start=1):
        ws.cell(row=4, column=i, value=h)
    for r, values in enumerate(rows, start=5):
        for i, h in enumerate(HEADERS, start=1):
            ws.cell(row=r, column=i, value=values.get(h))
    fd, path = tempfile.mkstemp(suffix='.xlsx')
    os.close(fd)
    wb.save(path)
    return path


class ReadRegisterTests(TestCase):
    def _rows(self, *rows):
        path = make_register(rows)
        self.addCleanup(os.remove, path)
        return read_register(path)

    def test_clean_row_has_no_errors_or_warnings(self):
        [row] = self._rows(GOOD)
        self.assertEqual((row.errors, row.warnings), ([], []))
        self.assertEqual(row.data['issued_on'].isoformat(), '2018-07-23')

    def test_rows_without_a_code_or_with_a_bad_checksum_are_skipped(self):
        rows = self._rows({**GOOD, 'Source Code': ''}, {**GOOD, 'Row ID': 'S-002', 'SHA-256 Checksum': 'abc'})
        self.assertIn('Source Code is empty.', rows[0].errors)
        self.assertIn('SHA-256 is not 64 hex characters.', rows[1].errors)

    def test_same_code_and_version_twice_is_a_duplicate(self):
        rows = self._rows(GOOD, {**GOOD, 'Row ID': 'S-002'})
        self.assertTrue(rows[0].ok)
        self.assertIn('Duplicate of S-001', rows[1].errors[0])

    def test_unofficial_site_and_drive_folder_are_flagged(self):
        [row] = self._rows({**GOOD, 'Listing Page URL': 'https://iqac.someuniv.edu/naac.pdf',
                            'Local File (folder/name)': 'https://drive.google.com/drive/folders/xyz'})
        self.assertTrue(row.ok)
        self.assertTrue(any('not an official domain' in w for w in row.warnings))
        self.assertIn('Drive link is a folder, not the file.', row.warnings)

    def test_licensed_standard_never_keeps_its_drive_copy(self):
        [row] = self._rows({**GOOD, 'Authority': 'ISO/IEC', 'Authority Kind': 'standards_body',
                            'Licensed Content?': 'Yes', 'Listing Page URL': 'https://www.iso.org/standard/1.html'})
        self.assertEqual(row.data['drive_url'], '')
        self.assertEqual(row.data['collection'], SourceVersion.Collection.LICENSED)
        self.assertTrue(any('Drive copy is NOT imported' in w for w in row.warnings))

    def test_missing_header_columns_are_rejected(self):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = 'Source Register'
        ws.append(['Row ID', 'Title'])
        fd, path = tempfile.mkstemp(suffix='.xlsx')
        os.close(fd)
        wb.save(path)
        self.addCleanup(os.remove, path)
        with self.assertRaisesMessage(ValueError, 'missing columns'):
            read_register(path)


class ApplyRegisterTests(TestCase):
    def setUp(self):
        self.path = make_register([GOOD, {**GOOD, 'Row ID': 'S-002', 'Source Code': 'NBA-002', 'Authority': 'NBA',
                                          'Authority Kind': 'accreditation', 'Category': '1. Accreditation & Quality',
                                          'Listing Page URL': 'https://www.nbaind.org/Downloads/Documents'}])
        self.addCleanup(os.remove, self.path)

    def test_dry_run_saves_nothing_but_reports_exact_counts(self):
        summary = apply_register(read_register(self.path), actor='t', commit=False)
        self.assertEqual(summary.created['document'], 2)
        self.assertEqual(summary.created['version'], 2)
        self.assertEqual((SourceDocument.objects.count(), SourceAuditEvent.objects.count()), (0, 0))

    def test_commit_creates_drafts_disabled_feeds_and_audit_events(self):
        apply_register(read_register(self.path), actor='intern-import', commit=True)
        version = SourceVersion.objects.get(document__source_code='UGC-005')
        self.assertEqual((version.status, version.version_label, version.checksum_sha256), ('draft', '2018', SHA))
        self.assertEqual(Authority.objects.get(code='UGC').kind, 'regulatory')
        self.assertFalse(SourceFeed.objects.filter(enabled=True).exists())
        self.assertEqual(SourceFeed.objects.count(), 2)
        self.assertTrue(SourceAuditEvent.objects.filter(actor='intern-import', action='import.create').exists())

    def test_rerun_is_idempotent(self):
        apply_register(read_register(self.path), actor='t', commit=True)
        events = SourceAuditEvent.objects.count()
        summary = apply_register(read_register(self.path), actor='t', commit=True)
        self.assertEqual((summary.created['version'], summary.updated['version']), (0, 0))
        self.assertEqual(SourceAuditEvent.objects.count(), events)

    def test_reimport_never_changes_an_approved_version(self):
        apply_register(read_register(self.path), actor='t', commit=True)
        SourceVersion.objects.filter(document__source_code='UGC-005').update(status='active')
        path = make_register([{**GOOD, 'Pages': 99}])
        self.addCleanup(os.remove, path)
        summary = apply_register(read_register(path), actor='t', commit=True)
        self.assertEqual(len(summary.locked), 1)
        self.assertEqual(SourceVersion.objects.get(document__source_code='UGC-005').pages, 8)


class ImmutabilityTests(TestCase):
    def setUp(self):
        path = make_register([GOOD])
        self.addCleanup(os.remove, path)
        apply_register(read_register(path), actor='t', commit=True)
        self.version = SourceVersion.objects.get()

    def test_draft_can_be_edited(self):
        self.version.pages = 9
        self.version.save()

    def test_active_version_content_is_frozen(self):
        self.version.status = 'active'
        self.version.save()
        self.version.checksum_sha256 = 'b' * 64
        with self.assertRaisesMessage(ValidationError, 'cannot change'):
            self.version.save()

    def test_status_moves_only_forward(self):
        self.version.status = 'active'
        self.version.save()
        self.version.status = 'superseded'
        self.version.save()
        self.version.status = 'active'
        with self.assertRaisesMessage(ValidationError, 'cannot move'):
            self.version.save()

    def test_approved_version_cannot_be_deleted(self):
        self.version.status = 'active'
        self.version.save()
        with self.assertRaises(ValidationError):
            self.version.delete()

    def test_audit_log_is_append_only(self):
        event = SourceAuditEvent.objects.first()
        event.reason = 'edited'
        with self.assertRaises(ValidationError):
            event.save()
        with self.assertRaises(ValidationError):
            event.delete()


class SourceLibraryApiTests(APITestCase):
    def setUp(self):
        path = make_register([GOOD])
        self.addCleanup(os.remove, path)
        apply_register(read_register(path), actor='t', commit=True)
        self.institution = Institution.objects.create(name='MKCE', city='Karur', state='TN')

    def _login(self, role):
        user = User.objects.create_user(email=f'{role}@test.edu', username=role, password=PASSWORD,
                                        first_name='T', last_name=role, role=role, institution=self.institution)
        token = self.client.post('/api/v1/auth/login/', {'email': user.email, 'password': PASSWORD}).data['access_token']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

    def test_ingage_staff_can_read_the_library(self):
        self._login(User.Role.CONSULTANT)
        listing = self.client.get('/api/v1/benchmarks/sources')
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data[0]['source_code'], 'UGC-005')
        self.assertEqual(listing.data[0]['latest_version']['version_label'], '2018')
        detail = self.client.get('/api/v1/benchmarks/sources/UGC-005')
        self.assertEqual((detail.status_code, len(detail.data['versions']), len(detail.data['feeds'])), (200, 1, 1))
        summary = self.client.get('/api/v1/benchmarks/sources/summary')
        self.assertEqual((summary.data['documents'], summary.data['by_status']), (1, {'draft': 1}))

    def test_filters(self):
        self._login(User.Role.SUPER_ADMIN)
        self.assertEqual(len(self.client.get('/api/v1/benchmarks/sources?authority=ugc').data), 1)
        self.assertEqual(len(self.client.get('/api/v1/benchmarks/sources?authority=NBA').data), 0)
        self.assertEqual(len(self.client.get('/api/v1/benchmarks/sources?q=plagiarism').data), 1)

    def test_institution_users_cannot_see_the_library(self):
        for role in (User.Role.INSTITUTION_ADMIN, User.Role.IQAC_COORDINATOR, User.Role.VIEWER):
            self._login(role)
            self.assertEqual(self.client.get('/api/v1/benchmarks/sources').status_code, 403, role)

    def test_anonymous_is_rejected(self):
        self.assertEqual(self.client.get('/api/v1/benchmarks/sources').status_code, 401)


# -- stage 1 step 3: file intake ----------------------------------------------

import hashlib  # noqa: E402
import shutil  # noqa: E402
from unittest.mock import patch  # noqa: E402

from django.test import override_settings  # noqa: E402

from .models import Requirement, RequirementCandidate, SourceSection  # noqa: E402
from .services import approval, file_intake  # noqa: E402
from .services.requirement_drafting import (  # noqa: E402
    DraftingError, accept_candidate, build_sections, draft_section, reject_candidate,
)


def pdf_bytes(pages=('First page text.', 'Second page text.')):
    import pymupdf
    doc = pymupdf.open()
    for text in pages:
        doc.new_page().insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


class _VersionMixin:
    def setUp(self):
        super().setUp()
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=self.media)
        override.enable()
        self.addCleanup(override.disable)
        self.content = pdf_bytes()
        self.sha = hashlib.sha256(self.content).hexdigest()
        path = make_register([{**GOOD, 'SHA-256 Checksum': self.sha}])
        self.addCleanup(os.remove, path)
        apply_register(read_register(path), actor='t', commit=True)
        self.version = SourceVersion.objects.get()

    def fetch_ok(self, file_id):
        return self.content, 'plagiarism.pdf'


class FileIntakeTests(_VersionMixin, TestCase):
    def test_matching_checksum_is_verified_and_stored(self):
        result = file_intake.ingest(self.version, fetcher=self.fetch_ok)
        self.version.refresh_from_db()
        self.assertEqual((result.status, self.version.intake_status), ('verified', 'verified'))
        self.assertTrue(os.path.exists(os.path.join(self.media, self.version.file_uri)))
        self.assertIn(self.sha, self.version.file_uri)
        self.assertEqual(self.version.pages, 2)  # corrected from the register's 8
        self.assertIn('pages recorded 8, actual 2', self.version.intake_note)

    def test_missing_checksum_is_computed(self):
        SourceVersion.objects.filter(pk=self.version.pk).update(checksum_sha256='')
        self.version.refresh_from_db()
        self.assertEqual(file_intake.ingest(self.version, fetcher=self.fetch_ok).status, 'computed')
        self.version.refresh_from_db()
        self.assertEqual(self.version.checksum_sha256, self.sha)

    def test_mismatch_is_not_stored(self):
        result = file_intake.ingest(self.version, fetcher=lambda fid: (b'other bytes', 'x.pdf'))
        self.version.refresh_from_db()
        self.assertEqual((result.status, self.version.file_uri), ('mismatch', ''))

    def test_folder_link_and_fetch_errors(self):
        SourceVersion.objects.filter(pk=self.version.pk).update(drive_url='https://drive.google.com/drive/folders/xyz')
        self.version.refresh_from_db()
        self.assertEqual(file_intake.ingest(self.version, fetcher=self.fetch_ok).status, 'skipped')
        SourceVersion.objects.filter(pk=self.version.pk).update(drive_url='https://drive.google.com/file/d/abcdefghijkl/view')
        self.version.refresh_from_db()

        def boom(file_id):
            raise RuntimeError('403 denied')
        self.assertEqual(file_intake.ingest(self.version, fetcher=boom).status, 'failed')

    def test_approved_version_is_never_touched(self):
        SourceVersion.objects.filter(pk=self.version.pk).update(status='active')
        self.version.refresh_from_db()
        result = file_intake.ingest(self.version, fetcher=self.fetch_ok)
        self.version.refresh_from_db()
        self.assertEqual((result.status, self.version.file_uri), ('skipped', ''))

    def test_drive_file_id_parsing(self):
        self.assertEqual(file_intake.drive_file_id('https://drive.google.com/file/d/1AbC_dEf-123456/view?usp=x'),
                         '1AbC_dEf-123456')
        self.assertIsNone(file_intake.drive_file_id('https://drive.google.com/drive/folders/1AbCdEf123456'))


# -- approval -------------------------------------------------------------------

class ApprovalTests(_VersionMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(email='c@ingage.ai', username='c', password=PASSWORD, role='consultant')

    def test_cannot_approve_before_intake(self):
        with self.assertRaisesMessage(approval.ApprovalError, 'run file intake'):
            approval.approve(self.version, self.user)

    def test_open_flags_need_acknowledgement(self):
        file_intake.ingest(self.version, fetcher=self.fetch_ok)
        self.version.refresh_from_db()
        self.version.review_flags = ['Applies To is empty.']
        self.version.save()
        with self.assertRaises(approval.ApprovalError) as ctx:
            approval.approve(self.version, self.user)
        self.assertEqual(ctx.exception.flags, ['Applies To is empty.'])
        approval.approve(self.version, self.user, acknowledge_flags=True, note='checked')
        self.version.refresh_from_db()
        self.assertEqual((self.version.status, self.version.approved_by), ('active', self.user))
        self.assertTrue(SourceAuditEvent.objects.filter(action='version.approved', actor='c@ingage.ai').exists())

    def test_new_edition_supersedes_the_active_one(self):
        file_intake.ingest(self.version, fetcher=self.fetch_ok)
        self.version.refresh_from_db()
        approval.approve(self.version, self.user)
        new = SourceVersion.objects.create(document=self.version.document, version_label='2024',
                                           collection_status='downloaded', file_uri='x', intake_status='verified')
        approval.approve(new, self.user)
        self.version.refresh_from_db()
        new.refresh_from_db()
        self.assertEqual((self.version.status, new.status, new.supersedes_id), ('superseded', 'active', self.version.pk))

    def test_withdraw_needs_a_reason(self):
        file_intake.ingest(self.version, fetcher=self.fetch_ok)
        self.version.refresh_from_db()
        approval.approve(self.version, self.user)
        with self.assertRaisesMessage(approval.ApprovalError, 'reason'):
            approval.withdraw(self.version, self.user, note=' ')
        approval.withdraw(self.version, self.user, note='Replaced by gazette correction')
        self.assertEqual(SourceVersion.objects.get(pk=self.version.pk).status, 'withdrawn')


# -- stage 2: sections, drafts, review -----------------------------------------

PAGES = [{'page_number': 1, 'text': 'Chapter 1. Every university shall establish an Academic Integrity Panel '
                                    'chaired by the Pro-Vice Chancellor to review plagiarism cases.'},
         {'page_number': 2, 'text': 'Institutions should conduct awareness programmes on academic integrity '
                                    'for students and faculty every year.'}]


class FakeAI:
    model = 'fake-model'

    def __init__(self, items):
        self.items = items

    def extract_structured_data(self, **kwargs):
        return {'requirements': self.items}


class DraftingTests(_VersionMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(email='e@ingage.ai', username='e', password=PASSWORD, role='consultant')
        build_sections(self.version, pages=PAGES)
        self.section = SourceSection.objects.get(version=self.version)

    def test_sections_keep_page_ranges(self):
        self.assertEqual((self.section.page_start, self.section.page_end), (1, 2))
        self.assertIn('[Page 2]', self.section.text)

    def test_only_drafts_quoting_the_source_are_kept(self):
        good = {'statement': 'The institution establishes an Academic Integrity Panel.', 'kind': 'mandatory',
                'page': 1, 'source_quote': 'Every university shall establish an Academic Integrity Panel',
                'confidence': 0.9, 'rationale': 'shall'}
        invented = {**good, 'source_quote': 'Every university shall appoint a Chief AI Officer within six months'}
        wrong_page = {**good, 'page': 7}
        kept, dropped = draft_section(self.section, FakeAI([good, invented, wrong_page]))
        self.assertEqual((kept, dropped), (1, 2))
        self.assertEqual(RequirementCandidate.objects.get().kind, 'mandatory')

    def _candidate(self):
        draft_section(self.section, FakeAI([{
            'statement': 'The institution runs yearly integrity awareness programmes.', 'kind': 'recommended',
            'page': 2, 'source_quote': 'Institutions should conduct awareness programmes on academic integrity',
            'confidence': 0.8, 'rationale': 'should'}]))
        return RequirementCandidate.objects.get()

    def test_accept_with_edit_creates_a_traceable_requirement(self):
        cand = self._candidate()
        req = accept_candidate(cand, self.user, statement='The institution runs academic-integrity awareness yearly.')
        self.assertEqual(req.code, 'UGC-005-R001')
        self.assertEqual((req.page, req.version, req.approved_by), (2, self.version, self.user))
        self.assertIn('awareness programmes', req.source_quote)
        cand.refresh_from_db()
        self.assertEqual(cand.status, 'accepted')
        with self.assertRaises(DraftingError):
            accept_candidate(cand, self.user)
        self.assertTrue(SourceAuditEvent.objects.filter(action='requirement.accepted').exists())

    def test_reject(self):
        cand = self._candidate()
        reject_candidate(cand, self.user, note='duplicate')
        cand.refresh_from_db()
        self.assertEqual((cand.status, Requirement.objects.count()), ('rejected', 0))

    def test_sections_are_kept_once_drafts_were_reviewed(self):
        reject_candidate(self._candidate(), self.user)
        with self.assertRaises(DraftingError):
            build_sections(self.version, pages=PAGES)


@override_settings(AI_PROCESSING_MODE='single')
class DraftingTaskTests(_VersionMixin, TestCase):
    def test_runs_only_when_queued(self):
        from .tasks import draft_source_requirements
        with patch('apps.benchmarks.services.requirement_drafting.draft_version', return_value=(3, 1)) as run:
            draft_source_requirements.apply(args=[str(self.version.pk)])
            run.assert_not_called()  # not queued -> skipped
            SourceVersion.objects.filter(pk=self.version.pk).update(extraction_status='queued')
            draft_source_requirements.apply(args=[str(self.version.pk)])
        self.version.refresh_from_db()
        self.assertEqual(self.version.extraction_status, 'done')
        self.assertIn('3 draft requirement(s)', self.version.extraction_note)
        self.assertIn('1 AI suggestion(s) dropped', self.version.extraction_note)

    def test_failure_is_recorded(self):
        from .tasks import draft_source_requirements
        SourceVersion.objects.filter(pk=self.version.pk).update(extraction_status='queued')
        with patch('apps.benchmarks.services.requirement_drafting.draft_version', side_effect=DraftingError('no file')):
            draft_source_requirements.apply(args=[str(self.version.pk)])
        self.version.refresh_from_db()
        self.assertEqual((self.version.extraction_status, self.version.extraction_note), ('failed', 'no file'))


class ActionApiTests(_VersionMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.institution = Institution.objects.create(name='MKCE', city='Karur', state='TN')

    def _login(self, role):
        user = User.objects.create_user(email=f'{role}@x.edu', username=role, password=PASSWORD, role=role,
                                        institution=self.institution)
        token = self.client.post('/api/v1/auth/login/', {'email': user.email, 'password': PASSWORD}).data['access_token']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

    def test_approve_flow_over_the_api(self):
        self._login('consultant')
        url = f'/api/v1/benchmarks/versions/{self.version.pk}'
        self.assertEqual(self.client.post(f'{url}/approve', {}).status_code, 400)  # no intake yet
        with patch('apps.benchmarks.services.file_intake.fetch_from_drive', side_effect=self.fetch_ok):
            r = self.client.post(f'{url}/intake')
        self.assertEqual(r.data['result'], 'verified')
        SourceVersion.objects.filter(pk=self.version.pk).update(review_flags=['x'])
        blocked = self.client.post(f'{url}/approve', {})
        self.assertEqual((blocked.status_code, blocked.data['flags']), (400, ['x']))
        ok = self.client.post(f'{url}/approve', {'acknowledge_flags': True, 'note': 'ok'}, format='json')
        self.assertEqual((ok.status_code, ok.data['status'], ok.data['approved_by']), (200, 'active', 'consultant@x.edu'))

    def test_drafting_and_review_over_the_api(self):
        self._login('super_admin')
        url = f'/api/v1/benchmarks/versions/{self.version.pk}'
        self.assertEqual(self.client.post(f'{url}/draft-requirements').status_code, 400)  # no stored file
        SourceVersion.objects.filter(pk=self.version.pk).update(file_uri='source_library/x.pdf')
        with patch('apps.benchmarks.tasks.draft_source_requirements.delay') as delay:
            self.assertEqual(self.client.post(f'{url}/draft-requirements').status_code, 202)
            self.assertEqual(self.client.post(f'{url}/draft-requirements').status_code, 409)  # already queued
            delay.assert_called_once()
        build_sections(self.version, pages=PAGES) if not self.version.sections.exists() else None
        section = SourceSection.objects.get(version=self.version)
        cand = RequirementCandidate.objects.create(version=self.version, section=section, statement='S', kind='mandatory',
                                                   page=1, source_quote='q', confidence=0.5)
        listed = self.client.get(f'{url}/candidates?status=pending')
        self.assertEqual(len(listed.data), 1)
        r = self.client.post(f'/api/v1/benchmarks/candidates/{cand.pk}/review',
                             {'decision': 'accept', 'statement': 'The institution does S.'}, format='json')
        self.assertEqual((r.status_code, r.data['status'], r.data['requirement_code']), (200, 'accepted', 'UGC-005-R001'))
        reqs = self.client.get('/api/v1/benchmarks/requirements?source_code=UGC-005')
        self.assertEqual(reqs.data[0]['statement'], 'The institution does S.')

    def test_actions_are_staff_only(self):
        self._login('iqac_coordinator')
        url = f'/api/v1/benchmarks/versions/{self.version.pk}'
        for path in ('intake', 'approve', 'draft-requirements'):
            self.assertEqual(self.client.post(f'{url}/{path}').status_code, 403, path)


class IncompleteDownloadTests(_VersionMixin, TestCase):
    def test_unfinished_browser_download_is_refused(self):
        result = file_intake.ingest(self.version, fetcher=lambda fid: (b'partial', 'Unconfirmed 807153.crdownload'))
        self.version.refresh_from_db()
        self.assertEqual((result.status, self.version.file_uri), ('failed', ''))
        self.assertIn('incomplete', result.note)


# -- stage 3.1: catalogue import ----------------------------------------------------

from .models import Benchmark, MaturityDefinition  # noqa: E402
from .services.catalogue_import import apply_catalogue, benchmark_kind, read_catalogue  # noqa: E402

TEMPLATE = {'L3': 'Policy/owner/process and baseline evidence exist.', 'L2': 'Operates across scope.',
            'L1': 'Institution-wide and measured.'}


def make_source_pack(benchmarks, title='InGage Benchmark Source Pack v0.2 | Expanded'):
    wb = openpyxl.Workbook()
    rm = wb.active
    rm.title = 'Read Me'
    rm.append([title])
    rm.append(['Purpose', 'x'])
    rm.append(['Pillar ID', 'Pillar', 'Coverage statement', 'Benchmark domains', 'Mandatory', 'Guidance',
               'Proposed', 'Status'])
    rm.append(['P01', 'Governance', 'Leadership', 2, 1, 0, 1, 'Catalogue built'])
    rm.append(['P08', 'AI transformation', 'AI', 1, 0, 0, 1, 'Catalogue built'])
    ev = wb.create_sheet('Evidence Catalogue')
    ev.append(['Evidence Type ID', 'Evidence Family', 'Examples', 'Minimum Validation', 'Assessment Use'])
    ev.append(['EV-01', 'Authority and policy', 'Policies', 'Authenticity and date', 'Mapped'])
    ev.append(['EV-10', 'AI system and model', 'Model cards', 'Reproducibility', 'Mapped'])
    bc = wb.create_sheet('Benchmark Catalogue')
    bc.append(['Benchmark ID', 'Pillar ID', 'Benchmark Domain', 'Capability / Requirement Scope', 'Benchmark Class',
               'Applicability', 'Source Basis', 'L3 Foundational', 'L2 Operating', 'L1 Advanced', 'Evidence Types',
               'Scoring Dimensions', 'Activation Status'])
    for b in benchmarks:
        bc.append(b)
    fd, path = tempfile.mkstemp(suffix='.xlsx')
    os.close(fd)
    wb.save(path)
    return path


MANDATORY_CLASS = 'Mandatory/authoritative source mapping plus maturity benchmark'
PROPOSED_CLASS = 'Proposed InGage maturity benchmark'


def bench_row(code, pillar='P01', cls=MANDATORY_CLASS, levels=None, evidence='EV-01', title=None):
    levels = levels or TEMPLATE
    return [code, pillar, title or f'Domain {code}', f'Scope {code}', cls, 'University; ITI', 'NAAC C6',
            levels['L3'], levels['L2'], levels['L1'], evidence, 'Compliance; maturity', 'Pending extraction']


class CatalogueImportTests(TestCase):
    def _cat(self, rows, **kw):
        path = make_source_pack(rows, **kw)
        self.addCleanup(os.remove, path)
        return read_catalogue(path)

    def test_kinds_from_benchmark_class(self):
        self.assertEqual(benchmark_kind(MANDATORY_CLASS), 'mandatory')
        self.assertEqual(benchmark_kind(PROPOSED_CLASS), 'proposed')
        self.assertEqual(benchmark_kind('Guidance-backed maturity benchmark'), 'guidance')
        self.assertIsNone(benchmark_kind('Something else'))

    def test_import_creates_the_catalogue_as_drafts(self):
        cat = self._cat([bench_row('GOV-01'), bench_row('GOV-02', cls=PROPOSED_CLASS),
                         bench_row('AIX-01', pillar='P08', evidence='EV-01; EV-10')])
        self.assertEqual((cat.version_label, len(cat.pillars), len(cat.evidence_types), len(cat.benchmarks)),
                         ('v0.2', 2, 2, 3))
        summary = apply_catalogue(cat, actor='t', commit=True)
        self.assertEqual(summary.created['benchmark'], 3)
        aix = Benchmark.objects.get(benchmark_code='AIX-01')
        self.assertEqual((aix.pillar.code, aix.status, aix.version_label), ('P08', 'draft', 'v0.2'))
        self.assertEqual(sorted(aix.evidence_types.values_list('code', flat=True)), ['EV-01', 'EV-10'])
        self.assertEqual(Benchmark.objects.get(benchmark_code='GOV-02').benchmark_kind, 'proposed')
        self.assertEqual(MaturityDefinition.objects.count(), 9)

    def test_shared_template_levels_are_marked_placeholders(self):
        real = {'L3': 'A named AI policy exists.', 'L2': 'Policy reviewed yearly.', 'L1': 'Outcomes audited.'}
        cat = self._cat([bench_row('GOV-01'), bench_row('GOV-02'), bench_row('GOV-03'),
                         bench_row('AIX-01', pillar='P08', levels=real)])
        apply_catalogue(cat, actor='t', commit=True)
        self.assertEqual(MaturityDefinition.objects.filter(benchmark__benchmark_code='GOV-01',
                                                           is_placeholder=True).count(), 3)
        self.assertFalse(MaturityDefinition.objects.filter(benchmark__benchmark_code='AIX-01',
                                                           is_placeholder=True).exists())
        self.assertTrue(any('placeholder' in w for w in cat.warnings))

    def test_bad_rows_are_skipped_with_a_reason(self):
        cat = self._cat([bench_row('GOV-01', pillar='P99'), bench_row('GOV-02', cls='??'),
                         bench_row('GOV-03', evidence='EV-77'), bench_row('GOV-04'), bench_row('GOV-04')])
        self.assertEqual([b['code'] for b in cat.benchmarks], ['GOV-04'])
        self.assertEqual(len(cat.errors), 4)

    def test_dry_run_and_idempotent_rerun_and_locked_benchmarks(self):
        cat = self._cat([bench_row('GOV-01')])
        apply_catalogue(cat, actor='t', commit=False)
        self.assertEqual(Benchmark.objects.count(), 0)
        apply_catalogue(cat, actor='t', commit=True)
        again = apply_catalogue(cat, actor='t', commit=True)
        self.assertEqual((dict(again.created), dict(again.updated)), ({}, {}))
        Benchmark.objects.update(status='active')
        locked = apply_catalogue(self._cat([bench_row('GOV-01', title='Renamed')]), actor='t', commit=True)
        self.assertEqual(len(locked.locked), 1)
        self.assertEqual(Benchmark.objects.get().title, 'Domain GOV-01')


class CatalogueApiTests(APITestCase):
    def setUp(self):
        path = make_source_pack([bench_row('GOV-01'), bench_row('GOV-02', cls=PROPOSED_CLASS),
                                 bench_row('AIX-01', pillar='P08')])
        self.addCleanup(os.remove, path)
        apply_catalogue(read_catalogue(path), actor='t', commit=True)
        self.institution = Institution.objects.create(name='MKCE', city='Karur', state='TN')

    def _login(self, role):
        user = User.objects.create_user(email=f'{role}@x.edu', username=role, password=PASSWORD, role=role,
                                        institution=self.institution)
        token = self.client.post('/api/v1/auth/login/', {'email': user.email, 'password': PASSWORD}).data['access_token']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

    def test_catalogue_endpoints(self):
        self._login('consultant')
        listing = self.client.get('/api/v1/benchmarks/catalogue')
        self.assertEqual([b['benchmark_code'] for b in listing.data], ['AIX-01', 'GOV-01', 'GOV-02'])
        gov = listing.data[1]
        self.assertEqual(([lv['level'] for lv in gov['maturity_levels']], gov['levels_defined']),
                         (['L3', 'L2', 'L1'], False))
        self.assertEqual(len(self.client.get('/api/v1/benchmarks/catalogue?kind=proposed').data), 1)
        self.assertEqual(len(self.client.get('/api/v1/benchmarks/catalogue?pillar=P08').data), 1)
        self.assertEqual(self.client.get('/api/v1/benchmarks/catalogue/GOV-02').data['kind_label'], 'Proposed')
        pillars = self.client.get('/api/v1/benchmarks/pillars').data
        self.assertEqual((pillars[0]['code'], pillars[0]['benchmark_count'], pillars[0]['proposed_count']),
                         ('P01', 2, 1))
        self.assertEqual(len(self.client.get('/api/v1/benchmarks/evidence-types').data), 12)  # seeded EV-01..12 (migration 0014)

    def test_catalogue_is_staff_only(self):
        self._login('institution_admin')
        for url in ('/api/v1/benchmarks/catalogue', '/api/v1/benchmarks/pillars', '/api/v1/benchmarks/evidence-types'):
            self.assertEqual(self.client.get(url).status_code, 403, url)


# -- stage 3.2: linking requirements to benchmarks ----------------------------------

from django.utils import timezone as _tz  # noqa: E402

from .models import BenchmarkRequirement  # noqa: E402
from .services import linking  # noqa: E402


class _LinkFixture:
    def setUp(self):
        super().setUp()
        reg = make_register([GOOD])  # UGC-005, UGC Plagiarism Regulations, 2018
        pack = make_source_pack([
            bench_row('ACA-05', title='Assessment, examination and academic integrity'),
            bench_row('GOV-01', title='Strategic direction and institutional development'),
            bench_row('AI-04', pillar='P08', title='AI security, safety and adversarial resilience'),
        ])
        for p in (reg, pack):
            self.addCleanup(os.remove, p)
        apply_register(read_register(reg), actor='t', commit=True)
        apply_catalogue(read_catalogue(pack), actor='t', commit=True)
        Benchmark.objects.filter(benchmark_code='ACA-05').update(source_basis='NAAC C2; UGC plagiarism; NBA/DGT')
        Benchmark.objects.filter(benchmark_code='GOV-01').update(source_basis='UGC Institutional Development Plans; NAAC C6')
        Benchmark.objects.filter(benchmark_code='AI-04').update(source_basis='NIST AI RMF/GenAI Profile; CERT-In')
        self.user = User.objects.create_user(email='x@ingage.ai', username='x', password=PASSWORD, role='consultant')
        self.version = SourceVersion.objects.get()
        self.req = Requirement.objects.create(
            code='UGC-005-R001', version=self.version, statement='The institution checks every thesis for '
            'plagiarism with an approved similarity tool before evaluation.', kind='mandatory', page=3,
            source_quote='every thesis shall be checked for plagiarism using a similarity tool',
            approved_by=self.user, approved_at=_tz.now())


class LinkingTests(_LinkFixture, TestCase):
    def test_suggestions_rank_the_matching_benchmark_first_and_explain_why(self):
        suggestions = linking.suggest_benchmarks(self.req)
        self.assertEqual(suggestions[0]['benchmark'].benchmark_code, 'ACA-05')
        reasons = ' '.join(suggestions[0]['reasons'])
        self.assertIn('UGC', reasons)
        self.assertIn('plagiarism', reasons)
        self.assertNotIn('AI-04', [s['benchmark'].benchmark_code for s in suggestions])

    def test_link_update_unlink_are_audited(self):
        aca = Benchmark.objects.get(benchmark_code='ACA-05')
        linking.link(aca, self.req, self.user, relationship='primary')
        linking.link(aca, self.req, self.user, relationship='supporting', note='partly')
        self.assertEqual(BenchmarkRequirement.objects.get().relationship, 'supporting')
        self.assertNotIn('ACA-05', [s['benchmark'].benchmark_code for s in linking.suggest_benchmarks(self.req)])
        linking.unlink(aca, self.req, self.user)
        self.assertFalse(BenchmarkRequirement.objects.exists())
        actions = list(SourceAuditEvent.objects.filter(action__startswith='benchmark.').values_list('action', flat=True))
        self.assertEqual(sorted(actions), ['benchmark.link_changed', 'benchmark.linked', 'benchmark.unlinked'])

    def test_released_benchmark_and_withdrawn_source_are_refused(self):
        aca = Benchmark.objects.get(benchmark_code='ACA-05')
        with self.assertRaises(linking.LinkError):
            linking.link(aca, self.req, self.user, relationship='primary-ish')
        SourceVersion.objects.filter(pk=self.version.pk).update(status='withdrawn')
        self.req.refresh_from_db()
        with self.assertRaisesMessage(linking.LinkError, 'withdrawn'):
            linking.link(aca, self.req, self.user, relationship='primary')
        SourceVersion.objects.filter(pk=self.version.pk).update(status='active')
        self.req.refresh_from_db()
        aca.status = 'active'
        aca.save()
        with self.assertRaisesMessage(linking.LinkError, 'new draft'):
            linking.link(aca, self.req, self.user, relationship='primary')


class LinkingApiTests(_LinkFixture, APITestCase):
    def _login(self, role):
        user = User.objects.create_user(email=f'{role}@y.edu', username=f'{role}y', password=PASSWORD, role=role)
        token = self.client.post('/api/v1/auth/login/', {'email': user.email, 'password': PASSWORD}).data['access_token']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

    def test_link_flow(self):
        self._login('consultant')
        sug = self.client.get('/api/v1/benchmarks/requirements/UGC-005-R001/suggestions')
        self.assertEqual(sug.data[0]['benchmark_code'], 'ACA-05')
        self.assertEqual(len(self.client.get('/api/v1/benchmarks/requirements?unlinked=1').data), 1)
        r = self.client.post('/api/v1/benchmarks/catalogue/ACA-05/requirements',
                             {'requirement_code': 'UGC-005-R001', 'relationship': 'primary'}, format='json')
        self.assertEqual((r.status_code, r.data[0]['requirement_code'], r.data[0]['linked_by']),
                         (201, 'UGC-005-R001', 'consultant@y.edu'))
        self.assertEqual(self.client.get('/api/v1/benchmarks/catalogue/ACA-05').data['requirement_count'], 1)
        reqs = self.client.get('/api/v1/benchmarks/requirements').data
        self.assertEqual(reqs[0]['benchmarks'], [{'benchmark_code': 'ACA-05', 'relationship': 'primary'}])
        self.assertEqual(len(self.client.get('/api/v1/benchmarks/requirements?unlinked=1').data), 0)
        bad = self.client.post('/api/v1/benchmarks/catalogue/ACA-05/requirements',
                               {'requirement_code': 'UGC-005-R001', 'relationship': 'nope'}, format='json')
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(self.client.delete('/api/v1/benchmarks/catalogue/ACA-05/requirements/UGC-005-R001').status_code, 204)
        self.assertEqual(self.client.delete('/api/v1/benchmarks/catalogue/ACA-05/requirements/UGC-005-R001').status_code, 400)

    def test_staff_only(self):
        self._login('hod')
        self.assertEqual(self.client.get('/api/v1/benchmarks/catalogue/ACA-05/requirements').status_code, 403)
        self.assertEqual(self.client.get('/api/v1/benchmarks/requirements/UGC-005-R001/suggestions').status_code, 403)


class TitleAcronymTests(TestCase):
    def test_acronyms(self):
        self.assertEqual(linking.title_acronym('The Digital Personal Data Protection Act, 2023 (No. 22 of 2023)'), 'dpdp')
        self.assertEqual(linking.title_acronym('National Credit Framework (NCrF)'), 'ncf')
        self.assertEqual(linking.title_acronym('Policy'), '')


# -- stage 3.3: writing L3/L2/L1 -------------------------------------------------------

from .services import authoring  # noqa: E402

REAL_L3 = ('An academic integrity policy and a plagiarism-detection tool exist and are used for PhD theses; '
           'a named officer owns them.')
REAL_L2 = ('The integrity policy covers all programmes and assessments; panels decide cases on time and records '
           'are kept for every case.')
REAL_L1 = ('Integrity data is reviewed every year, trends drive training and assessment redesign, and outcomes '
           'are reported publicly.')


class _CataloguePack:
    def setUp(self):
        super().setUp()
        pack = make_source_pack([bench_row('ACA-05', title='Assessment and integrity'), bench_row('GOV-01'),
                                 bench_row('GOV-02', cls=PROPOSED_CLASS)])
        self.addCleanup(os.remove, pack)
        self.pack = pack
        apply_catalogue(read_catalogue(pack), actor='t', commit=True)
        self.user = User.objects.create_user(email='expert@ingage.ai', username='expert', password=PASSWORD,
                                             role='consultant')
        self.aca = Benchmark.objects.get(benchmark_code='ACA-05')


class AuthoringTests(_CataloguePack, TestCase):
    def test_saving_a_real_level_clears_the_placeholder_and_is_audited(self):
        md = authoring.save_level(self.aca, 'L3', self.user, {
            'definition': REAL_L3, 'non_examples': ['A policy document nobody has adopted', ' '],
            'minimum_evidence': ['Approved policy', 'Tool licence'], 'requires_manual_review': True})
        self.assertEqual((md.is_placeholder, md.edited_by, md.non_examples), (False, self.user,
                                                                             ['A policy document nobody has adopted']))
        event = SourceAuditEvent.objects.get(action='benchmark.level_saved')
        self.assertEqual((event.before['is_placeholder'], event.after['definition']), (True, REAL_L3))

    def test_template_short_and_duplicate_text_are_refused(self):
        with self.assertRaisesMessage(authoring.AuthoringError, 'template'):
            authoring.save_level(self.aca, 'L3', self.user, {'definition': TEMPLATE['L3'] + ' ' * 3 + ''})
        with self.assertRaisesMessage(authoring.AuthoringError, 'at least'):
            authoring.save_level(self.aca, 'L3', self.user, {'definition': 'Too short.'})
        authoring.save_level(self.aca, 'L3', self.user, {'definition': REAL_L3})
        with self.assertRaisesMessage(authoring.AuthoringError, 'own definition'):
            authoring.save_level(self.aca, 'L2', self.user, {'definition': REAL_L3})
        with self.assertRaisesMessage(authoring.AuthoringError, 'list'):
            authoring.save_level(self.aca, 'L2', self.user, {'definition': REAL_L2, 'non_examples': 'not a list'})

    def test_only_drafts_can_be_edited(self):
        self.aca.status = 'active'
        self.aca.save()
        with self.assertRaisesMessage(authoring.AuthoringError, 'new draft'):
            authoring.save_level(self.aca, 'L3', self.user, {'definition': REAL_L3})
        with self.assertRaises(authoring.AuthoringError):
            authoring.update_benchmark(self.aca, self.user, {'expert_owner': 'x'})

    def test_readiness_checklist(self):
        r = authoring.readiness(self.aca)
        checks = {c['key']: c for c in r['checks']}
        self.assertFalse(r['ready_for_review'])
        self.assertEqual(checks['levels']['detail'], '0/3 defined (others are placeholders)')
        self.assertEqual(checks['scoring']['severity'], 'pending')
        for lvl, text in (('L3', REAL_L3), ('L2', REAL_L2), ('L1', REAL_L1)):
            authoring.save_level(self.aca, lvl, self.user, {'definition': text})
        checks = {c['key']: c for c in authoring.readiness(self.aca)['checks']}
        self.assertTrue(checks['levels']['ok'])
        self.assertFalse(checks['requirements']['ok'])  # mandatory benchmark: a primary requirement is required
        gov02 = Benchmark.objects.get(benchmark_code='GOV-02')
        owner = {c['key']: c for c in authoring.readiness(gov02)['checks']}['owner']
        self.assertEqual((owner['severity'], owner['ok']), ('required', False))  # proposed -> owner required
        authoring.update_benchmark(gov02, self.user, {'expert_owner': 'Dr. A. Expert'})
        self.assertTrue({c['key']: c for c in authoring.readiness(gov02)['checks']}['owner']['ok'])

    def test_reimporting_the_catalogue_keeps_expert_levels(self):
        authoring.save_level(self.aca, 'L3', self.user, {'definition': REAL_L3})
        summary = apply_catalogue(read_catalogue(self.pack), actor='t', commit=True)
        self.assertIn('ACA-05 L3 - written by an expert, kept', summary.locked)
        self.assertEqual(MaturityDefinition.objects.get(benchmark=self.aca, level='L3').definition, REAL_L3)


class AuthoringApiTests(_CataloguePack, APITestCase):
    def setUp(self):
        super().setUp()
        token = self.client.post('/api/v1/auth/login/', {'email': 'expert@ingage.ai', 'password': PASSWORD}).data['access_token']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

    def test_edit_flow(self):
        base = '/api/v1/benchmarks/catalogue/ACA-05'
        bad = self.client.put(f'{base}/levels/L3', {'definition': 'short'}, format='json')
        self.assertEqual(bad.status_code, 400)
        ok = self.client.put(f'{base}/levels/l3', {'definition': REAL_L3, 'non_examples': ['Unadopted draft policy']},
                             format='json')
        self.assertEqual((ok.status_code, ok.data['is_placeholder'], ok.data['edited_by']),
                         (200, False, 'expert@ingage.ai'))
        p = self.client.patch(base, {'expert_owner': 'Dr. A. Expert'}, format='json')
        self.assertEqual(p.data['expert_owner'], 'Dr. A. Expert')
        readiness = self.client.get(f'{base}/readiness').data
        self.assertEqual({c['key']: c['ok'] for c in readiness['checks']}['owner'], True)
        history = self.client.get(f'{base}/history').data
        self.assertEqual([h['action'] for h in history[:2]], ['benchmark.updated', 'benchmark.level_saved'])
        detail = self.client.get(base).data
        l3 = [lv for lv in detail['maturity_levels'] if lv['level'] == 'L3'][0]
        self.assertEqual(l3['non_examples'], ['Unadopted draft policy'])

    def test_staff_only(self):
        hod = User.objects.create_user(email='hod@x.edu', username='hodx', password=PASSWORD, role='hod')
        token = self.client.post('/api/v1/auth/login/', {'email': hod.email, 'password': PASSWORD}).data['access_token']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        self.assertEqual(self.client.put('/api/v1/benchmarks/catalogue/ACA-05/levels/L3', {}, format='json').status_code, 403)


# -- stage 3.4: evidence rules ---------------------------------------------------------------

from .models import EvidenceRule  # noqa: E402
from .services import evidence_rules  # noqa: E402

RULE = {'evidence_type': 'EV-01', 'title': 'Approved academic integrity policy', 'mandatory': True,
        'minimum_count': 1, 'minimum_currency_months': 36, 'validation_method': 'manual_review',
        'privacy_classification': 'internal'}


class EvidenceRuleTests(_CataloguePack, TestCase):
    def test_benchmark_rule_with_and_without_level(self):
        r1 = evidence_rules.create_rule(self.user, {**RULE, 'level': 'L3'}, benchmark=self.aca)
        r2 = evidence_rules.create_rule(self.user, {**RULE, 'title': 'Similarity reports for theses', 'level': ''},
                                        benchmark=self.aca)
        self.assertEqual((r1.level, r2.level, r1.minimum_currency_months), ('L3', '', 36))
        self.assertEqual(evidence_rules.level_coverage(self.aca), {'L3': 2, 'L2': 1, 'L1': 1})
        self.assertEqual(SourceAuditEvent.objects.filter(action='evidence_rule.created').count(), 2)

    def test_new_evidence_type_is_added_to_the_benchmark(self):
        self.assertFalse(self.aca.evidence_types.filter(code='EV-10').exists())
        evidence_rules.create_rule(self.user, {**RULE, 'evidence_type': 'ev-10', 'title': 'Model card for any AI grader'},
                                   benchmark=self.aca)
        self.assertTrue(self.aca.evidence_types.filter(code='EV-10').exists())
        self.assertTrue(SourceAuditEvent.objects.filter(action='benchmark.evidence_type_added').exists())

    def test_validation(self):
        for bad, msg in ((dict(RULE, evidence_type='EV-99'), 'EV code'), (dict(RULE, title='x'), 'title'),
                         (dict(RULE, minimum_count=0), 'between 1 and 100'),
                         (dict(RULE, minimum_currency_months=500), 'between 1 and 120'),
                         (dict(RULE, validation_method='magic'), 'validation_method'),
                         (dict(RULE, level='L9'), 'level')):
            with self.assertRaisesMessage(evidence_rules.EvidenceRuleError, msg):
                evidence_rules.create_rule(self.user, bad, benchmark=self.aca)

    def test_update_delete_and_released_benchmark(self):
        rule = evidence_rules.create_rule(self.user, RULE, benchmark=self.aca)
        evidence_rules.update_rule(rule, self.user, {'minimum_count': 3, 'minimum_currency_months': ''})
        rule.refresh_from_db()
        self.assertEqual((rule.minimum_count, rule.minimum_currency_months), (3, None))
        self.aca.status = 'active'
        self.aca.save()
        with self.assertRaisesMessage(evidence_rules.EvidenceRuleError, 'new draft'):
            evidence_rules.update_rule(rule, self.user, {'minimum_count': 2})
        with self.assertRaises(evidence_rules.EvidenceRuleError):
            evidence_rules.delete_rule(rule, self.user)
        self.aca.status = 'draft'
        self.aca.save()
        rule = EvidenceRule.objects.get(pk=rule.pk)  # fresh copy: its cached benchmark was the 'active' one
        evidence_rules.delete_rule(rule, self.user)
        self.assertFalse(EvidenceRule.objects.exists())
        self.assertTrue(SourceAuditEvent.objects.filter(action='evidence_rule.deleted').exists())

    def test_readiness_counts_evidence_rules(self):
        checks = {c['key']: c for c in authoring.readiness(self.aca)['checks']}
        self.assertEqual((checks['evidence_rules']['severity'], checks['evidence_rules']['ok']), ('required', False))
        evidence_rules.create_rule(self.user, RULE, benchmark=self.aca)  # any level -> covers all three
        checks = {c['key']: c for c in authoring.readiness(self.aca)['checks']}
        self.assertTrue(checks['evidence_rules']['ok'])


class RequirementEvidenceRuleTests(_LinkFixture, TestCase):
    def test_requirement_rules_follow_the_schema(self):
        rule = evidence_rules.create_rule(self.user, {**RULE, 'evidence_type': 'EV-01'}, requirement=self.req)
        self.assertEqual((rule.requirement, rule.benchmark, rule.level), (self.req, None, ''))
        with self.assertRaisesMessage(evidence_rules.EvidenceRuleError, 'already has a rule'):
            evidence_rules.create_rule(self.user, RULE, requirement=self.req)
        with self.assertRaisesMessage(evidence_rules.EvidenceRuleError, 'leave level empty'):
            evidence_rules.create_rule(self.user, {**RULE, 'evidence_type': 'EV-10', 'level': 'L3'}, requirement=self.req)

    def test_requirement_in_a_released_benchmark_is_locked(self):
        aca = Benchmark.objects.get(benchmark_code='ACA-05')
        linking.link(aca, self.req, self.user, relationship='primary')
        aca.status = 'active'
        aca.save()
        with self.assertRaisesMessage(evidence_rules.EvidenceRuleError, 'released'):
            evidence_rules.create_rule(self.user, RULE, requirement=self.req)


class EvidenceRuleApiTests(_CataloguePack, APITestCase):
    def setUp(self):
        super().setUp()
        token = self.client.post('/api/v1/auth/login/', {'email': 'expert@ingage.ai', 'password': PASSWORD}).data['access_token']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

    def test_flow(self):
        url = '/api/v1/benchmarks/catalogue/ACA-05/evidence-rules'
        created = self.client.post(url, {**RULE, 'level': 'L2'}, format='json')
        self.assertEqual((created.status_code, created.data['evidence_type'], created.data['level']), (201, 'EV-01', 'L2'))
        self.assertEqual(self.client.post(url, {**RULE, 'title': 'x'}, format='json').status_code, 400)
        listing = self.client.get(url).data
        self.assertEqual((len(listing['benchmark_rules']), listing['level_coverage']), (1, {'L3': 0, 'L2': 1, 'L1': 0}))
        rid = created.data['id']
        patched = self.client.patch(f'/api/v1/benchmarks/evidence-rules/{rid}', {'mandatory': False}, format='json')
        self.assertFalse(patched.data['mandatory'])
        self.assertEqual(self.client.delete(f'/api/v1/benchmarks/evidence-rules/{rid}').status_code, 204)


# -- stage 3.5: applicability -----------------------------------------------------------------

from .models import ApplicabilityRule  # noqa: E402
from .services import applicability  # noqa: E402
from .services.applicability import Profile  # noqa: E402

ENGINEERING = Profile('engineering', 'autonomous', {'ug_engineering', 'mba_pgdm'}, {'AICTE', 'NBA', 'NAAC'})
POLYTECHNIC = Profile('polytechnic', 'standalone', {'diploma_engineering'}, {'AICTE'})
ARTS = Profile('arts_science', 'affiliated', {'ug_arts_science'}, {'UGC', 'NAAC'})
ITI = Profile('iti', 'standalone', {'iti_trade'}, {'DGT', 'NCVET'})


class ApplicabilityTests(_CataloguePack, TestCase):
    def setUp(self):
        super().setUp()
        self.gov01 = Benchmark.objects.get(benchmark_code='GOV-01')
        self.gov02 = Benchmark.objects.get(benchmark_code='GOV-02')

    def test_no_rules_means_review_not_applies(self):
        d = applicability.evaluate([], ENGINEERING)
        self.assertEqual(d.result, 'requires_review')
        self.assertIn('No applicability rules', d.reason)

    def test_first_matching_rule_decides_with_a_reason(self):
        # ACA-05: accredited-programme rule first, then HEIs in general, ITIs excluded
        applicability.create_rule(self.user, {'result': 'applies', 'priority': 10, 'approval_bodies': ['NBA'],
                                              'reason': 'NBA-accredited programmes must show integrity controls.'},
                                  benchmark=self.aca)
        applicability.create_rule(self.user, {'result': 'applies', 'priority': 20,
                                              'institution_types': ['engineering', 'polytechnic', 'arts_science', 'university']},
                                  benchmark=self.aca)
        applicability.create_rule(self.user, {'result': 'does_not_apply', 'priority': 30, 'institution_types': ['iti'],
                                              'reason': 'ITIs follow DGT assessment norms instead.'}, benchmark=self.aca)
        rules = list(self.aca.applicability_rules.all())
        eng = applicability.evaluate(rules, ENGINEERING)
        self.assertEqual((eng.result, eng.reason), ('applies', 'NBA-accredited programmes must show integrity controls.'))
        arts = applicability.evaluate(rules, ARTS)
        self.assertEqual(arts.result, 'applies')
        self.assertIn('institution type is', arts.reason)
        iti = applicability.evaluate(rules, ITI)
        self.assertEqual((iti.result, iti.reason), ('does_not_apply', 'ITIs follow DGT assessment norms instead.'))

    def test_unmatched_profile_gets_an_exclusion_reason(self):
        applicability.create_rule(self.user, {'result': 'applies', 'programme_types': ['iti_trade']}, benchmark=self.aca)
        d = applicability.evaluate(list(self.aca.applicability_rules.all()), ARTS)
        self.assertEqual(d.result, 'does_not_apply')
        self.assertIn('needs offers ITI craftsman trade', d.reason)

    def test_four_pilot_profiles_get_different_lists(self):
        """Developer guide, pilot done-criterion 3."""
        applicability.create_rule(self.user, {'result': 'applies', 'approval_bodies': ['AICTE']}, benchmark=self.aca)
        applicability.create_rule(self.user, {'result': 'applies', 'institution_types': ['iti']}, benchmark=self.gov01)
        applicability.create_rule(self.user, {'result': 'applies', 'approval_bodies': ['UGC', 'NBA']}, benchmark=self.gov02)

        def applying(profile):
            return frozenset(r['benchmark'].benchmark_code for r in applicability.resolve_benchmarks(profile)
                             if r['decision'].result == 'applies')
        lists = {name: applying(p) for name, p in
                 (('eng', ENGINEERING), ('poly', POLYTECHNIC), ('arts', ARTS), ('iti', ITI))}
        self.assertEqual(lists['eng'], {'ACA-05', 'GOV-02'})
        self.assertEqual(lists['poly'], {'ACA-05'})
        self.assertEqual(lists['arts'], {'GOV-02'})
        self.assertEqual(lists['iti'], {'GOV-01'})
        self.assertEqual(len(set(lists.values())), 4)

    def test_validation_and_guards(self):
        for bad, msg in (({'result': 'maybe'}, 'result'), ({'institution_types': ['spaceport']}, 'institution type'),
                         ({'autonomous_statuses': ['private']}, 'autonomous_statuses'),
                         ({'approval_bodies': ['FIFA']}, 'approval bodies'), ({'priority': 5000}, 'priority')):
            with self.assertRaisesMessage(applicability.ApplicabilityError, msg):
                applicability.create_rule(self.user, bad, benchmark=self.aca)
        rule = applicability.create_rule(self.user, {'result': 'optional'}, benchmark=self.aca)
        applicability.update_rule(rule, self.user, {'priority': 5, 'institution_types': ['iti']})
        rule.refresh_from_db()
        self.assertEqual((rule.priority, list(rule.institution_types.values_list('code', flat=True))), (5, ['iti']))
        self.aca.status = 'active'
        self.aca.save()
        rule = ApplicabilityRule.objects.get(pk=rule.pk)
        with self.assertRaisesMessage(applicability.ApplicabilityError, 'new draft'):
            applicability.delete_rule(rule, self.user)
        actions = set(SourceAuditEvent.objects.filter(action__startswith='applicability_rule').values_list('action', flat=True))
        self.assertEqual(actions, {'applicability_rule.created', 'applicability_rule.updated'})

    def test_readiness_needs_rules(self):
        checks = {c['key']: c for c in authoring.readiness(self.aca)['checks']}
        self.assertFalse(checks['applicability']['ok'])
        self.assertIn('Source Pack text', checks['applicability']['detail'])
        applicability.create_rule(self.user, {'result': 'applies'}, benchmark=self.aca)
        self.assertTrue({c['key']: c for c in authoring.readiness(self.aca)['checks']}['applicability']['ok'])


class ApplicabilityApiTests(_CataloguePack, APITestCase):
    def setUp(self):
        super().setUp()
        token = self.client.post('/api/v1/auth/login/', {'email': 'expert@ingage.ai', 'password': PASSWORD}).data['access_token']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

    def test_flow(self):
        ref = self.client.get('/api/v1/benchmarks/applicability/reference').data
        self.assertIn('iti', [t['code'] for t in ref['institution_types']])
        self.assertIn('NCVET', ref['approval_bodies'])
        url = '/api/v1/benchmarks/catalogue/ACA-05/applicability-rules'
        r = self.client.post(url, {'result': 'does_not_apply', 'institution_types': ['iti'],
                                   'reason': 'Not for ITIs.'}, format='json')
        self.assertEqual((r.status_code, r.data['institution_types']), (201, ['iti']))
        self.assertEqual(self.client.post(url, {'result': 'nope'}, format='json').status_code, 400)
        preview = self.client.post('/api/v1/benchmarks/applicability/preview',
                                   {'institution_type': 'iti', 'programme_types': ['iti_trade']}, format='json').data
        aca = [b for b in preview['benchmarks'] if b['benchmark_code'] == 'ACA-05'][0]
        self.assertEqual((aca['result'], aca['reason']), ('does_not_apply', 'Not for ITIs.'))
        self.assertEqual(preview['counts'], {'does_not_apply': 1, 'requires_review': 2})
        bad = self.client.post('/api/v1/benchmarks/applicability/preview', {'institution_type': 'spaceport'}, format='json')
        self.assertEqual(bad.status_code, 400)
        rid = r.data['id']
        self.assertEqual(self.client.patch(f'/api/v1/benchmarks/applicability-rules/{rid}', {'priority': 1},
                                           format='json').data['priority'], 1)
        self.assertEqual(self.client.delete(f'/api/v1/benchmarks/applicability-rules/{rid}').status_code, 204)


# -- stage 3.6: releases ------------------------------------------------------------------

from django.core.exceptions import ValidationError as DjangoValidationError  # noqa: E402

from .models import BenchmarkRelease, BenchmarkReleaseItem  # noqa: E402
from .services import releases  # noqa: E402


def make_ready(benchmark, user, requirement):
    """Everything readiness requires: 3 levels, an evidence rule, an applicability rule, a primary requirement."""
    for lvl, text in (('L3', REAL_L3), ('L2', REAL_L2), ('L1', REAL_L1)):
        authoring.save_level(benchmark, lvl, user, {'definition': text})
    evidence_rules.create_rule(user, RULE, benchmark=benchmark)
    applicability.create_rule(user, {'result': 'applies', 'institution_types': ['engineering']}, benchmark=benchmark)
    linking.link(benchmark, requirement, user, relationship='primary')


class ReleaseTests(_LinkFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.aca = Benchmark.objects.get(benchmark_code='ACA-05')
        self.approver = User.objects.create_user(email='approver@ingage.ai', username='approver', password=PASSWORD,
                                                 role='super_admin')

    def _publish_first(self):
        make_ready(self.aca, self.user, self.req)
        rel = releases.create_release('Release 1.0', self.user, 'Pilot')
        releases.add_item(rel, self.aca, self.user)
        releases.submit(rel, self.user)
        releases.approve(rel, self.approver)
        return releases.publish(rel, self.approver)

    def test_not_ready_benchmarks_block_review_with_reasons(self):
        rel = releases.create_release('Release 1.0', self.user)
        with self.assertRaises(releases.ReleaseError) as ctx:
            releases.submit(rel, self.user)
        self.assertIn('no benchmarks', ctx.exception.problems[0])
        releases.add_item(rel, self.aca, self.user)
        with self.assertRaises(releases.ReleaseError) as ctx:
            releases.submit(rel, self.user)
        self.assertIn('ACA-05: L3, L2 and L1 written', ctx.exception.problems[0])

    def test_full_lifecycle_and_four_eyes(self):
        make_ready(self.aca, self.user, self.req)
        rel = releases.create_release('Release 1.0', self.user)
        releases.add_item(rel, self.aca, self.user, impact_summary='First version')
        warnings = releases.submit(rel, self.user)
        self.assertIn('20-30 pilot benchmarks', warnings[0])
        with self.assertRaisesMessage(releases.ReleaseError, 'four-eyes'):
            releases.approve(rel, self.user)
        releases.approve(rel, self.approver)
        releases.publish(rel, self.approver)
        rel.refresh_from_db()
        self.aca.refresh_from_db()
        item = rel.items.get()
        self.assertEqual((rel.status, self.aca.status, item.change_type), ('published', 'active', 'added'))
        self.assertEqual((len(rel.content_hash), len(item.snapshot_hash)), (64, 64))
        self.assertEqual(item.snapshot['levels']['L3']['definition'], REAL_L3)
        self.assertEqual(item.snapshot['requirements'][0]['code'], 'UGC-005-R001')
        self.assertEqual(releases.current_release(), rel)
        with self.assertRaisesMessage(authoring.AuthoringError, 'active'):
            authoring.save_level(self.aca, 'L3', self.user, {'definition': REAL_L3 + ' Changed.'})
        item.impact_summary = 'tampered'
        with self.assertRaises(DjangoValidationError):
            item.save()

    def test_benchmarks_are_frozen_while_in_review(self):
        make_ready(self.aca, self.user, self.req)
        rel = releases.create_release('Release 1.0', self.user)
        releases.add_item(rel, self.aca, self.user)
        releases.submit(rel, self.user)
        with self.assertRaisesMessage(authoring.AuthoringError, 'under review'):
            authoring.save_level(self.aca, 'L3', self.user, {'definition': REAL_L3 + ' Edited during review.'})
        with self.assertRaisesMessage(evidence_rules.EvidenceRuleError, 'under review'):
            evidence_rules.create_rule(self.user, {**RULE, 'title': 'Another rule'}, benchmark=self.aca)
        with self.assertRaisesMessage(releases.ReleaseError, 'Say what'):
            releases.send_back(rel, self.approver, '')
        releases.send_back(rel, self.approver, 'Tighten L3')
        authoring.save_level(self.aca, 'L3', self.user, {'definition': REAL_L3 + ' Edited after send-back.'})

    def test_second_release_carries_forward_and_keeps_history(self):
        first = self._publish_first()
        self.aca.refresh_from_db()  # publish made it active
        first_hash = first.items.get().snapshot_hash
        gov = Benchmark.objects.get(benchmark_code='GOV-01')
        make_ready(gov, self.user, self.req)
        second = releases.create_release('Release 1.1', self.user)
        self.assertEqual(second.items.get(benchmark=self.aca).change_type, 'unchanged')
        releases.add_item(second, gov, self.user)
        with self.assertRaisesMessage(releases.ReleaseError, 'carried forward'):
            releases.remove_item(second, self.aca, self.user)
        with self.assertRaisesMessage(releases.ReleaseError, 'reopen'):
            releases.add_item(second, self.aca, self.user)
        releases.reopen_benchmark(self.aca, self.user, 'Clarify L1 outcomes')
        self.aca.refresh_from_db()
        self.assertEqual((self.aca.status, self.aca.version_label), ('draft', 'v0.2.r1'))
        authoring.save_level(self.aca, 'L1', self.user, {'definition': REAL_L1 + ' Reported every semester.'})
        releases.add_item(second, self.aca, self.user)
        self.assertEqual(second.items.get(benchmark=self.aca).change_type, 'updated')
        changes = {d['benchmark_code']: d for d in releases.diff(second)}
        self.assertEqual((changes['ACA-05']['changed'], changes['GOV-01']['change_type']), (['levels'], 'added'))
        releases.submit(second, self.user)
        releases.approve(second, self.approver)
        releases.publish(second, self.approver)
        first.refresh_from_db()
        self.assertEqual(first.status, 'retired')
        self.assertEqual(first.items.get().snapshot_hash, first_hash)  # history untouched
        self.assertNotEqual(second.items.get(benchmark=self.aca).snapshot_hash, first_hash)
        self.assertEqual(releases.current_release(), second)

    def test_only_one_release_in_progress_and_unique_labels(self):
        releases.create_release('Release 1.0', self.user)
        with self.assertRaisesMessage(releases.ReleaseError, 'in progress'):
            releases.create_release('Release 2.0', self.user)
        with self.assertRaisesMessage(releases.ReleaseError, 'label'):
            releases.create_release('bad/label!', self.user)


class ReleaseApiTests(_LinkFixture, APITestCase):
    def _login(self, email):
        token = self.client.post('/api/v1/auth/login/', {'email': email, 'password': PASSWORD}).data['access_token']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

    def test_api_flow(self):
        aca = Benchmark.objects.get(benchmark_code='ACA-05')
        make_ready(aca, self.user, self.req)
        User.objects.create_user(email='boss@ingage.ai', username='boss', password=PASSWORD, role='super_admin')
        self._login('x@ingage.ai')
        self.assertEqual(self.client.get('/api/v1/benchmarks/releases/current').status_code, 404)
        r = self.client.post('/api/v1/benchmarks/releases', {'release_label': 'Release 1.0'}, format='json')
        self.assertEqual((r.status_code, r.data['status']), (201, 'draft'))
        base = '/api/v1/benchmarks/releases/Release%201.0'
        r = self.client.post(f'{base}/items', {'benchmark_code': 'ACA-05'}, format='json')
        self.assertEqual(r.data['items'][0]['change_type'], 'added')
        self.assertEqual(self.client.post(f'{base}/submit').data['status'], 'review')
        refused = self.client.post(f'{base}/approve')
        self.assertIn('four-eyes', refused.data['detail'])
        self._login('boss@ingage.ai')
        self.assertEqual(self.client.post(f'{base}/approve', {'note': 'ok'}, format='json').data['status'], 'approved')
        pub = self.client.post(f'{base}/publish').data
        self.assertEqual((pub['status'], pub['published_by'], len(pub['content_hash'])), ('published', 'boss@ingage.ai', 64))
        self.assertEqual(self.client.get('/api/v1/benchmarks/releases/current').data['release_label'], 'Release 1.0')
        self.assertEqual(self.client.get(f'{base}/diff').data[0]['change_type'], 'added')
        reopened = self.client.post('/api/v1/benchmarks/catalogue/ACA-05/reopen', {'reason': 'fix'}, format='json')
        self.assertEqual((reopened.data['status'], reopened.data['version_label']), ('draft', 'v0.2.r1'))

    def test_staff_only(self):
        User.objects.create_user(email='hod@z.edu', username='hodz', password=PASSWORD, role='hod')
        self._login('hod@z.edu')
        self.assertEqual(self.client.get('/api/v1/benchmarks/releases').status_code, 403)


# -- Stage 4: daily watcher ---------------------------------------------------------------
from .models import SourceChangeEvent, SourceSnapshot, WatcherRun  # noqa: E402
from .services import watcher  # noqa: E402
from .services.watcher import FetchError, Fetched  # noqa: E402


def index_page(*links, footer='Last updated: 12 Oct 2026 10:41'):
    rows = ''.join(f'<li><a href="{href}">{text}</a></li>' for text, href in links)
    return (f'<!doctype html><html><body><h1>Regulations</h1><ul>{rows}</ul>'
            f'<a href="/about">About</a><p>{footer}</p><script>var t=1;</script></body></html>').encode()


def fake(*responses):
    """A fetcher that returns (or raises) the given responses in order."""
    queue = list(responses)

    def _fetch(url):
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        content, ctype = item if isinstance(item, tuple) else (item, 'text/html; charset=utf-8')
        return Fetched(url=url, status=200, content=content, content_type=ctype, headers={'Content-Type': ctype})
    return _fetch


PLAG = ('UGC Plagiarism Regulations, 2018', '/pdfnews/plagiarism.pdf')
NEW = ('UGC (Minimum Standards) Regulations amendment 2026', '/pdfnews/minimum-standards-2026.pdf')


class _WatcherFixture(_LinkFixture):
    def setUp(self):
        super().setUp()
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=self.media)
        override.enable()
        self.addCleanup(override.disable)
        self.feed = SourceFeed.objects.get(document__source_code='UGC-005', feed_type='document_index')
        self.feed.enabled = True
        self.feed.save()


class WatcherTests(_WatcherFixture, TestCase):
    def test_first_check_is_a_baseline_and_noise_is_ignored(self):
        r = watcher.check_feed(self.feed, fetcher=fake(index_page(PLAG)))
        self.assertEqual((r['result'], r['events']), ('baseline', 0))
        snap = SourceSnapshot.objects.get()
        self.assertEqual(snap.normalized['links'], [[PLAG[0], 'https://www.ugc.gov.in/pdfnews/plagiarism.pdf']])
        self.assertTrue(os.path.exists(os.path.join(self.media, snap.content_uri)))
        # Different date, script and non-document link: still "unchanged".
        r = watcher.check_feed(self.feed, fetcher=fake(index_page(PLAG, footer='Last updated: 13 Oct 2026 02:00')))
        self.assertEqual(r['result'], 'unchanged')
        self.assertEqual((SourceSnapshot.objects.count(), SourceChangeEvent.objects.count()), (1, 0))
        self.feed.refresh_from_db()
        self.assertEqual(self.feed.last_result, 'unchanged')

    def test_new_document_link_raises_an_event_with_impact_and_changes_nothing_else(self):
        aca = Benchmark.objects.get(benchmark_code='ACA-05')
        BenchmarkRequirement.objects.create(benchmark=aca, requirement=self.req, relationship='primary')
        before = (Requirement.objects.count(), aca.status, SourceVersion.objects.get().status)
        watcher.check_feed(self.feed, fetcher=fake(index_page(PLAG)))
        r = watcher.check_feed(self.feed, fetcher=fake(index_page(PLAG, NEW)))
        self.assertEqual((r['result'], r['events']), ('changed', 1))
        event = SourceChangeEvent.objects.get()
        self.assertEqual((event.change_kind, event.status), ('new_document', 'triaged'))
        self.assertGreaterEqual(event.materiality_score, 55)  # "Regulations" is a key term
        self.assertEqual(event.details['added'][0][1], 'https://www.ugc.gov.in/pdfnews/minimum-standards-2026.pdf')
        self.assertEqual(event.impact['requirements'], ['UGC-005-R001'])
        self.assertEqual(event.impact['benchmarks'], ['ACA-05'])
        self.assertIsNotNone(event.previous_snapshot)
        self.assertIsNotNone(event.current_snapshot)
        aca.refresh_from_db()
        self.assertEqual((Requirement.objects.count(), aca.status, SourceVersion.objects.get().status), before)

    def test_removed_link_is_a_withdrawal(self):
        watcher.check_feed(self.feed, fetcher=fake(index_page(PLAG, NEW)))
        watcher.check_feed(self.feed, fetcher=fake(index_page(NEW)))
        event = SourceChangeEvent.objects.get()
        self.assertEqual(event.change_kind, 'withdrawal')
        self.assertEqual(event.details['removed'][0][0], PLAG[0])

    def test_web_page_text_change(self):
        self.feed.feed_type = 'web_page'
        self.feed.save()
        page = '<html><body><p>Directions under section 70B</p><p>Visitors: {}</p></body></html>'
        watcher.check_feed(self.feed, fetcher=fake(page.format(10).encode()))
        self.assertEqual(watcher.check_feed(self.feed, fetcher=fake(page.format(99).encode()))['result'], 'unchanged')
        changed = page.replace('</body>', '<p>New guideline on incident reporting issued</p></body>')
        watcher.check_feed(self.feed, fetcher=fake(changed.format(99).encode()))
        event = SourceChangeEvent.objects.get()
        self.assertEqual(event.change_kind, 'content_change')
        self.assertEqual(event.details['added_lines'], ['New guideline on incident reporting issued'])

    def test_changed_file_is_a_new_version(self):
        watcher.check_feed(self.feed, fetcher=fake((b'%PDF-1.4 one', 'application/pdf')))
        watcher.check_feed(self.feed, fetcher=fake((b'%PDF-1.4 two', 'application/pdf')))
        self.assertEqual(SourceChangeEvent.objects.get().change_kind, 'new_version')

    def test_page_gone_raises_one_withdrawal_not_one_per_day(self):
        watcher.check_feed(self.feed, fetcher=fake(index_page(PLAG)))
        gone = FetchError('HTTP 404', status=404, kind='http')
        self.assertEqual(watcher.check_feed(self.feed, fetcher=fake(gone))['result'], 'failed')
        watcher.check_feed(self.feed, fetcher=fake(gone))
        event = SourceChangeEvent.objects.get()
        self.assertEqual((event.change_kind, event.current_snapshot), ('withdrawal', None))
        self.feed.refresh_from_db()
        self.assertEqual((self.feed.last_result, self.feed.last_error), ('failed', 'HTTP 404'))

    def test_blocked_access_is_an_access_change(self):
        watcher.check_feed(self.feed, fetcher=fake(index_page(PLAG)))
        watcher.check_feed(self.feed, fetcher=fake(FetchError('HTTP 403', status=403, kind='http')))
        self.assertEqual(SourceChangeEvent.objects.get().change_kind, 'access_change')

    def test_dry_run_saves_nothing(self):
        r = watcher.check_feed(self.feed, fetcher=fake(index_page(PLAG)), dry_run=True)
        self.assertEqual(r['result'], 'baseline')
        self.feed.refresh_from_db()
        self.assertEqual((SourceSnapshot.objects.count(), self.feed.last_checked_at), (0, None))

    def test_run_checks_only_enabled_feeds_and_records_failures(self):
        other = SourceFeed.objects.create(document=self.feed.document, feed_type='web_page', enabled=True,
                                          endpoint_url='https://www.ugc.gov.in/other')
        SourceFeed.objects.create(document=self.feed.document, feed_type='web_page', enabled=False,
                                  endpoint_url='https://www.ugc.gov.in/off')

        def fetcher(url):
            if url == other.endpoint_url:
                raise FetchError('ConnectTimeout', kind='network')
            return fake(index_page(PLAG))(url)
        run, results = watcher.run_watcher(trigger='manual', fetcher=fetcher)
        self.assertEqual((run.feeds_checked, run.status), (2, 'partial_failure'))
        self.assertEqual(run.failure_detail[0]['url'], 'https://www.ugc.gov.in/other')
        self.assertIsNotNone(run.completed_at)

    def test_manual_upload_feeds_are_never_fetched(self):
        self.feed.feed_type = 'manual_upload'
        self.feed.save()
        self.assertEqual(watcher.check_feed(self.feed, fetcher=fake())['result'], 'skipped')

    def test_review_is_audited_and_needs_a_real_decision(self):
        watcher.check_feed(self.feed, fetcher=fake(index_page(PLAG)))
        watcher.check_feed(self.feed, fetcher=fake(index_page(PLAG, NEW)))
        event = SourceChangeEvent.objects.get()
        with self.assertRaises(ValueError):
            watcher.review_event(event, self.user, 'triaged')
        watcher.review_event(event, self.user, 'accepted', 'New regulation; start a new source version.')
        event.refresh_from_db()
        self.assertEqual((event.status, event.reviewed_by), ('accepted', self.user))
        self.assertTrue(SourceAuditEvent.objects.filter(action='watcher.event_reviewed', object_id=str(event.pk)).exists())

    def test_task_runs_and_releases_its_lock(self):
        from django.core.cache import cache

        from .tasks import run_source_watcher
        cache.add('benchmarks:watcher:lock', 'other', 60)
        self.assertIsNone(run_source_watcher(trigger='manual'))  # another run holds the lock
        cache.delete('benchmarks:watcher:lock')
        real = watcher.run_watcher
        with patch.object(watcher, 'run_watcher', lambda **kw: real(fetcher=fake(index_page(PLAG)), **kw)):
            run_id = run_source_watcher(trigger='manual')
        self.assertEqual(WatcherRun.objects.get(pk=run_id).status, 'complete')
        self.assertEqual(SourceSnapshot.objects.count(), 1)
        self.assertFalse(cache.get('benchmarks:watcher:lock'))


class WatcherApiTests(_WatcherFixture, APITestCase):
    def _login(self, email):
        token = self.client.post('/api/v1/auth/login/', {'email': email, 'password': PASSWORD}).data['access_token']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

    def test_feeds_events_and_review(self):
        self._login('x@ingage.ai')
        feeds = self.client.get('/api/v1/benchmarks/watcher/feeds?enabled=true').data
        self.assertEqual([f['source_code'] for f in feeds], ['UGC-005'])
        off = self.client.post(f'/api/v1/benchmarks/watcher/feeds/{self.feed.pk}/enable', {'enabled': False,
                               'note': 'pause'}, format='json')
        self.assertFalse(off.data['enabled'])
        self.assertTrue(SourceAuditEvent.objects.filter(action='watcher.feed_disabled').exists())
        watcher.check_feed(self.feed, fetcher=fake(index_page(PLAG)))
        watcher.check_feed(self.feed, fetcher=fake(index_page(PLAG, NEW)))
        summary = self.client.get('/api/v1/benchmarks/watcher/summary').data
        self.assertEqual((summary['open_events'], summary['feeds_enabled']), (1, 0))
        [event] = self.client.get('/api/v1/benchmarks/watcher/events').data
        url = f'/api/v1/benchmarks/watcher/events/{event["id"]}/review'
        self.assertEqual(self.client.post(url, {'status': 'ignored'}, format='json').status_code, 400)  # note needed
        done = self.client.post(url, {'status': 'ignored', 'note': 'Duplicate of an existing file.'}, format='json')
        self.assertEqual((done.status_code, done.data['status'], done.data['reviewed_by']), (200, 'ignored', 'x@ingage.ai'))
        self.assertEqual(self.client.get('/api/v1/benchmarks/watcher/events').data, [])
        self.assertEqual(len(self.client.get('/api/v1/benchmarks/watcher/events?status=all').data), 1)

    def test_run_now_needs_an_enabled_feed(self):
        self._login('x@ingage.ai')
        SourceFeed.objects.update(enabled=False)
        self.assertEqual(self.client.post('/api/v1/benchmarks/watcher/runs').status_code, 400)

    def test_college_users_cannot_see_the_watcher(self):
        inst = Institution.objects.create(name='MKCE', city='Karur', state='TN')
        User.objects.create_user(email='c@test.edu', username='c', password=PASSWORD, role='institution_admin',
                                 institution=inst)
        self._login('c@test.edu')
        self.assertEqual(self.client.get('/api/v1/benchmarks/watcher/feeds').status_code, 403)


# -- Stage 4b: benchmark candidates from watcher changes ---------------------------------
from .models import BenchmarkCandidate  # noqa: E402
from .services import candidates as candidate_svc  # noqa: E402

NEW2 = ('UGC Regulations on Academic Integrity amendment 2027', '/pdfnews/integrity-2027.pdf')


class CandidateTests(_WatcherFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.aca = Benchmark.objects.get(benchmark_code='ACA-05')
        BenchmarkRequirement.objects.create(benchmark=self.aca, requirement=self.req, relationship='primary')
        self.legal = User.objects.create_user(email='legal@ingage.ai', username='legal', password=PASSWORD,
                                              role='consultant')

    def _change(self, *links):
        watcher.check_feed(self.feed, fetcher=fake(index_page(PLAG)))
        return watcher.check_feed(self.feed, fetcher=fake(index_page(PLAG, *links)))

    def test_material_change_creates_one_review_candidate_per_linked_benchmark(self):
        r = self._change(NEW)
        self.assertEqual(r['candidates'], 1)
        c = BenchmarkCandidate.objects.get()
        self.assertEqual((c.candidate_type, c.status, c.benchmark, c.created_by),
                         ('update_benchmark', 'review', self.aca, 'watcher'))
        self.assertEqual(c.required_roles, ['accreditation', 'legal'])  # UGC = regulatory authority
        self.assertIn('minimum-standards-2026.pdf', c.source_rationale)
        self.aca.refresh_from_db()
        self.assertEqual(self.aca.status, 'draft')  # nothing about the benchmark changed

    def test_an_open_candidate_is_not_duplicated(self):
        self._change(NEW)
        r = watcher.check_feed(self.feed, fetcher=fake(index_page(PLAG, NEW, NEW2)))
        self.assertEqual((r['events'], r['candidates']), (1, 0))
        self.assertEqual(BenchmarkCandidate.objects.count(), 1)

    def test_unlinked_source_gets_a_review_source_candidate(self):
        BenchmarkRequirement.objects.all().delete()
        self._change(NEW)
        c = BenchmarkCandidate.objects.get()
        self.assertEqual((c.candidate_type, c.benchmark), ('source_update', None))

    def test_low_authority_is_rejected_automatically(self):
        self.feed.authority_trust_score = 20
        self.feed.save()
        self._change(NEW)
        self.assertEqual(BenchmarkCandidate.objects.get().status, 'rejected')

    def test_minor_changes_make_no_candidate(self):
        self.feed.feed_type = 'web_page'
        self.feed.save()
        page = '<html><body>' + ''.join(f'<p>Line number {i} of the regulation text</p>' for i in range(60)) + '{}</body></html>'
        watcher.check_feed(self.feed, fetcher=fake(page.format('').encode()))
        r = watcher.check_feed(self.feed, fetcher=fake(page.format('<p>Office closed on Friday</p>').encode()))
        self.assertEqual((r['events'], r['candidates']), (1, 0))

    def test_review_rules_and_revision(self):
        self._change(NEW)
        c = BenchmarkCandidate.objects.get()
        with self.assertRaisesMessage(candidate_svc.CandidateError, 'needs reviews from'):
            candidate_svc.review(c, self.user, 'ai_governance', 'approve')
        candidate_svc.review(c, self.user, 'accreditation', 'approve')
        with self.assertRaisesMessage(candidate_svc.CandidateError, 'different person'):
            candidate_svc.review(c, self.user, 'legal', 'approve')
        with self.assertRaisesMessage(candidate_svc.CandidateError, 'Say why'):
            candidate_svc.review(c, self.legal, 'legal', 'reject')
        candidate_svc.review(c, self.legal, 'legal', 'approve', 'Amendment changes the integrity rules.')
        c.refresh_from_db()
        self.assertEqual(c.status, 'approved')
        Benchmark.objects.filter(pk=self.aca.pk).update(status='active', version_label='v0.2')
        c.benchmark.refresh_from_db()
        candidate_svc.reopen_for_revision(c, self.user)
        self.aca.refresh_from_db()
        self.assertEqual((self.aca.status, self.aca.version_label), ('draft', 'v0.2.r1'))

    def test_a_reject_rejects_and_needs_research_goes_back(self):
        self._change(NEW)
        c = BenchmarkCandidate.objects.get()
        candidate_svc.review(c, self.user, 'accreditation', 'needs_research', 'Find the gazette copy first.')
        c.refresh_from_db()
        self.assertEqual(c.status, 'research')
        candidate_svc.submit(c, self.user)
        candidate_svc.review(c, self.legal, 'legal', 'reject', 'Not applicable to HEIs.')
        c.refresh_from_db()
        self.assertEqual(c.status, 'rejected')

    def test_watcher_run_counts_candidates(self):
        watcher.check_feed(self.feed, fetcher=fake(index_page(PLAG)))
        run, _ = watcher.run_watcher(trigger='manual', fetcher=fake(index_page(PLAG, NEW)))
        self.assertEqual(run.candidates_created, 1)


class CandidateApiTests(_WatcherFixture, APITestCase):
    def _login(self, email):
        token = self.client.post('/api/v1/auth/login/', {'email': email, 'password': PASSWORD}).data['access_token']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

    def test_manual_candidate_and_listing(self):
        self._login('x@ingage.ai')
        r = self.client.post('/api/v1/benchmarks/benchmark-candidates', {
            'candidate_type': 'new_benchmark', 'title': 'Generative-AI use policy for assessment',
            'source_rationale': 'UNESCO 2023 guidance recommends an institutional GenAI policy.'}, format='json')
        self.assertEqual((r.status_code, r.data['status']), (201, 'research'))
        self.assertIn('ai_governance', r.data['required_roles'])
        cid = r.data['id']
        self.assertEqual(self.client.post(f'/api/v1/benchmarks/benchmark-candidates/{cid}/submit').data['status'],
                         'review')
        self.assertEqual(len(self.client.get('/api/v1/benchmarks/benchmark-candidates').data), 1)
        inst = Institution.objects.create(name='C', city='X', state='TN')
        User.objects.create_user(email='c@college.edu', username='c', password=PASSWORD, role='institution_admin',
                                 institution=inst)
        self._login('c@college.edu')
        self.assertEqual(self.client.get('/api/v1/benchmarks/benchmark-candidates').status_code, 403)


# -- AI-QIF v1.0 framework import ---------------------------------------------------

from decimal import Decimal  # noqa: E402

from .models import Framework, Pillar  # noqa: E402
from .services import authoring as _authoring  # noqa: E402
from .services.aiqif_import import apply_aiqif, read_aiqif  # noqa: E402

_LV = ('L3 — Foundational', 'L2 — Good / Recommended', 'L1 — Advanced / Aspirational')


def _aiqif_workbook(rows=None, crosswalk=None):
    """A small AI-QIF master: criterion C1 (60 = 30 + 30) and C2 (40, one KI) -- total 100, not 1000."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'AI Benchmark Master'
    ws.append(['AI-QIF Benchmark ID', 'Criterion ID', 'Criterion', 'Criterion Weight (of 1000)', 'KI ID',
               'Key Indicator', 'KI Provisional Weight', 'What AI Readiness Capability Is Being Benchmarked?',
               'Why It Matters for AI Readiness', *_LV, 'Applicability', 'Target Rule', 'Status'])
    tmpl = ('capability is defined and owned.', 'capability is systematic and measured.', 'capability is advanced.')
    for code, crit, cname, cw, ki, kw in rows or [
            ('AIQIF-C1.1', 'AIQIF-C1', 'Strategy', 60, 'AI Vision', 30),
            ('AIQIF-C1.2', 'AIQIF-C1', 'Strategy', 60, 'AI Governance', 30),
            ('AIQIF-C2.1', 'AIQIF-C2', 'Responsible AI', 40, 'Responsible AI Policy', 40)]:
        ws.append([code, crit, cname, cw, 1, ki, kw, f'Ability for {ki}.', 'Turns AI into a capability.',
                   *[f'{ki}: {t}' for t in tmpl], 'Institution-specific.', 'Target engine picks the level.',
                   'Proposed v1.0 - requires expert validation'])
    m = wb.create_sheet('AI-QIF Maturity')
    m.append(['Dimension', *_LV])
    m.append(['Strategy', 'Intent defined.', 'Integrated in planning.', 'Dynamic strategy.'])
    c = wb.create_sheet('NAAC → AI-QIF Crosswalk')
    c.append(['NAAC Metric ID', 'NAAC Criterion', 'NAAC Key Indicator', 'NAAC Requirement', 'NAAC Source Framework',
              'AI-QIF Mapping', 'AI-QIF Key Indicator', 'Relationship', 'How NAAC Evidence Can Be Reused',
              'AI-Specific Additional Evidence Needed'])
    for metric, ki in crosswalk or [('1.1.1', 'AIQIF-C1.1 / C1.2'), ('6.2.1', 'AIQIF-C1.1')]:
        c.append([metric, 'Criterion 1', '1.1', f'Requirement {metric}', 'NAAC', 'AIQIF-C1', ki, 'Supporting', 'x', 'y'])
    p = wb.create_sheet('AI-QIF Principles')
    p.append(['Principle', 'Rule'])
    p.append(['NAAC relationship', 'NAAC is supporting evidence, not AI readiness.'])
    a = wb.create_sheet('Scoring Architecture')
    a.append(['Layer', 'Definition', 'Authority'])
    a.append(['AI-QIF Criteria', '9 domains totaling 1000', 'InGage methodology'])
    fd, path = tempfile.mkstemp(suffix='.xlsx')
    os.close(fd)
    wb.save(path)
    return path


def _rows(response):
    data = response.json()
    return data.get('results', data) if isinstance(data, dict) else data


class AiQifImportTests(TestCase):
    def setUp(self):
        self.path = _aiqif_workbook()
        self.addCleanup(os.remove, self.path)

    def test_reads_criteria_weights_and_crosswalk(self):
        data = read_aiqif(self.path)
        self.assertTrue(data.ok)
        self.assertEqual([(c['code'], c['weight'], c['kis']) for c in data.criteria],
                         [('AIQIF-C1', Decimal(60), 2), ('AIQIF-C2', Decimal(40), 1)])
        by_code = {b['code']: b for b in data.benchmarks}
        # "AIQIF-C1.1 / C1.2" supports both key indicators.
        self.assertEqual([x['metric'] for x in by_code['AIQIF-C1.1']['crosswalk']], ['1.1.1', '6.2.1'])
        self.assertEqual(by_code['AIQIF-C1.2']['crosswalk'][0]['shared_with'], ['AIQIF-C1.1'])
        self.assertTrue(any('add up to 100' in w for w in data.warnings))  # not 1000
        self.assertTrue(any('no NAAC crosswalk' in w and 'AIQIF-C2.1' in w for w in data.warnings))
        # Same level wording on every KI once its name is removed = template.
        self.assertTrue(all(all(b['placeholder'].values()) for b in data.benchmarks))

    def test_kis_not_adding_up_to_their_criterion_are_reported(self):
        path = _aiqif_workbook(rows=[('AIQIF-C1.1', 'AIQIF-C1', 'Strategy', 60, 'AI Vision', 25)])
        self.addCleanup(os.remove, path)
        self.assertTrue(any('AIQIF-C1: key indicator weights add up to 25' in w for w in read_aiqif(path).warnings))

    def test_dry_run_saves_nothing(self):
        apply_aiqif(read_aiqif(self.path), actor='test', commit=False)
        self.assertFalse(Benchmark.objects.exists())
        self.assertFalse(Pillar.objects.exists())

    def test_commit_creates_drafts_with_weights_levels_and_framework(self):
        apply_aiqif(read_aiqif(self.path), actor='test', commit=True)
        b = Benchmark.objects.get(benchmark_code='AIQIF-C1.1')
        self.assertEqual((b.status, b.benchmark_kind, b.version_label), ('draft', 'proposed', 'AI-QIF v1.0'))
        self.assertEqual((b.weight, b.pillar.code, b.pillar.weight), (Decimal(30), 'AIQIF-C1', Decimal(60)))
        self.assertEqual(b.framework.code, 'AIQIF-V1.0')
        self.assertIn('NAAC is supporting evidence', b.framework.purpose)
        self.assertEqual(b.target_guidance, 'Target engine picks the level.')
        self.assertEqual(len(b.naac_crosswalk), 2)
        l3 = b.maturity_levels.get(level='L3')
        self.assertTrue(l3.is_placeholder)
        self.assertEqual(l3.definition, 'AI Vision: capability is defined and owned.')
        self.assertEqual(l3.observable_requirements, ['Strategy: Intent defined.'])
        self.assertFalse(_authoring.readiness(b)['ready_for_review'])  # experts still have to confirm

    def test_rerun_keeps_expert_work_and_withdraws_old_drafts(self):
        apply_aiqif(read_aiqif(self.path), actor='test', commit=True)
        expert = User.objects.create_user(email='x@ingage.ai', username='x', password='Str0ng!Pass', role='consultant')
        b = Benchmark.objects.get(benchmark_code='AIQIF-C1.1')
        _authoring.save_level(b, 'L3', expert, {'definition': 'A written, approved AI vision with named owners '
                                                              'and a funded roadmap for the next three years.'})
        _authoring.update_benchmark(b, expert, {'target_guidance': 'Expert target note.'})
        old = Benchmark.objects.create(benchmark_code='ACA-01', title='Old', capability=b.capability, pillar=b.pillar,
                                       benchmark_kind='guidance', version_label='v0.2')
        summary = apply_aiqif(read_aiqif(self.path), actor='test', commit=True, withdraw_others=True)
        b.refresh_from_db()
        old.refresh_from_db()
        self.assertTrue(b.maturity_levels.get(level='L3').definition.startswith('A written, approved'))
        self.assertEqual(b.target_guidance, 'Expert target note.')
        self.assertIn('AIQIF-C1.1 L3 - written by an expert, kept', summary.locked)
        self.assertEqual(old.status, 'withdrawn')
        self.assertEqual(summary.withdrawn, ['ACA-01'])
        self.assertEqual(Framework.objects.filter(code='AIQIF-V1.0').count(), 1)


class AiQifApiTests(APITestCase):
    def setUp(self):
        path = _aiqif_workbook()
        self.addCleanup(os.remove, path)
        apply_aiqif(read_aiqif(path), actor='test', commit=True)
        b = Benchmark.objects.get(benchmark_code='AIQIF-C1.1')
        old_pillar = Pillar.objects.create(code='P01', name='Old pillar')
        Benchmark.objects.create(benchmark_code='ACA-01', title='Old', capability=b.capability, pillar=old_pillar,
                                 benchmark_kind='guidance', version_label='v0.2', status='withdrawn')
        self.client.force_authenticate(User.objects.create_user(email='c@ingage.ai', username='c',
                                                                password='Str0ng!Pass', role='consultant'))

    def test_catalogue_hides_withdrawn_and_shows_weights(self):
        rows = _rows(self.client.get('/api/v1/benchmarks/catalogue'))
        self.assertEqual([r['benchmark_code'] for r in rows], ['AIQIF-C1.1', 'AIQIF-C1.2', 'AIQIF-C2.1'])
        self.assertEqual((rows[0]['weight'], rows[0]['pillar_weight'], rows[0]['framework']),
                         ('30.00', '60.00', 'AIQIF-V1.0'))
        self.assertEqual(rows[0]['naac_crosswalk'][0]['metric'], '1.1.1')
        all_rows = _rows(self.client.get('/api/v1/benchmarks/catalogue?status=all'))
        self.assertIn('ACA-01', [r['benchmark_code'] for r in all_rows])

    def test_pillars_are_the_aiqif_criteria(self):
        pillars = self.client.get('/api/v1/benchmarks/pillars').json()
        self.assertEqual([(p['code'], p['weight'], p['benchmark_count']) for p in pillars],
                         [('AIQIF-C1', '60.00', 2), ('AIQIF-C2', '40.00', 1)])


# -- AI drafting of benchmark content (fully automatic) ---------------------------------

from .models import ApplicabilityRule, EvidenceRule  # noqa: E402
from .services import ai_drafting  # noqa: E402


def _good_draft():
    def level(lv, text):
        return {'level': lv, 'definition': text, 'measurement_rule': f'{lv}: all listed evidence is accepted.',
                'observable_requirements': [f'{lv} observable'], 'minimum_evidence': [f'{lv} record'],
                'outcome_expectations': [f'{lv} outcome'], 'non_examples': [f'{lv} non-example'],
                'requires_manual_review': False}

    def rule(lv, ev, mandatory=True):
        return {'level': lv, 'evidence_type': ev, 'title': f'{lv} {ev} evidence', 'description': 'What to submit.',
                'scope_rule': 'Whole institution', 'mandatory': mandatory, 'minimum_count': 1,
                'minimum_currency_months': 24, 'validation_method': 'manual_review',
                'privacy_classification': 'internal'}

    return {
        'levels': [
            level('L3', 'A governing-body approved AI vision names owners and an initial portfolio of use cases.'),
            level('L2', 'The AI vision drives an annual plan with KPIs that are reviewed each semester and acted on.'),
            level('L1', 'AI strategy is adapted yearly from outcome data and peer benchmarks, with sustained impact.'),
        ],
        'evidence_rules': [rule('L3', 'EV-01'), rule('L2', 'EV-01'), rule('L1', 'EV-12'), rule('L2', 'EV-03', False)],
        'applicability_rules': [{'result': 'applies', 'priority': 100, 'institution_types': [], 'programme_types': [],
                                 'autonomous_statuses': [], 'approval_bodies': [], 'reason': 'Every institution.'}],
        'target_guidance': 'Most colleges should target L2 within two years.',
        'rationale': 'Built from the AI-QIF template and NAAC crosswalk.',
    }


class FakeDraftAI:
    model = 'fake-model-1'

    def __init__(self, draft=None, error=None):
        self.draft, self.error, self.calls = draft, error, []

    def extract_structured_data(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.draft


class AiDraftingTests(TestCase):
    def setUp(self):
        path = _aiqif_workbook()
        self.addCleanup(os.remove, path)
        apply_aiqif(read_aiqif(path), actor='test', commit=True)
        self.b = Benchmark.objects.get(benchmark_code='AIQIF-C1.1')

    def test_good_draft_is_saved_labelled_and_ready_for_release(self):
        ai = FakeDraftAI(_good_draft())
        result = ai_drafting.draft_benchmark(self.b, ai)
        self.assertTrue(result.ok, result.detail)
        self.b.refresh_from_db()
        levels = {m.level: m for m in self.b.maturity_levels.all()}
        self.assertTrue(all(not m.is_placeholder and m.ai_model == 'fake-model-1' for m in levels.values()))
        self.assertTrue(levels['L3'].definition.startswith('A governing-body approved'))
        self.assertEqual(levels['L3'].non_examples, ['L3 non-example'])
        self.assertEqual(EvidenceRule.objects.filter(benchmark=self.b, ai_model='fake-model-1').count(), 4)
        self.assertEqual(ApplicabilityRule.objects.filter(benchmark=self.b, ai_model='fake-model-1').count(), 1)
        self.assertEqual(self.b.expert_owner, 'AI (auto) - fake-model-1')
        self.assertTrue(_authoring.readiness(self.b)['ready_for_review'])
        # The AI was given the real catalogues and the indicator.
        prompt = ai.calls[0]['user_content']
        self.assertIn('AIQIF-C1.1', prompt)
        self.assertIn('EV-01', prompt)
        self.assertIn('1.1.1', prompt)  # NAAC crosswalk
        drafter = ai_drafting.ai_user()
        self.assertFalse(drafter.is_active)
        self.assertFalse(drafter.has_usable_password())
        self.assertTrue(SourceAuditEvent.objects.filter(action='benchmark.ai_drafted', object_id=str(self.b.pk)).exists())

    def test_draft_missing_a_mandatory_rule_saves_nothing(self):
        bad = _good_draft()
        bad['evidence_rules'] = [r for r in bad['evidence_rules'] if r['level'] != 'L1']
        result = ai_drafting.draft_benchmark(self.b, FakeDraftAI(bad))
        self.assertFalse(result.ok)
        self.assertIn('L1', result.detail)
        self.assertTrue(all(m.is_placeholder for m in self.b.maturity_levels.all()))
        self.assertFalse(EvidenceRule.objects.filter(benchmark=self.b).exists())

    def test_template_text_or_identical_levels_are_refused(self):
        bad = _good_draft()
        bad['levels'][1]['definition'] = bad['levels'][0]['definition']
        self.assertFalse(ai_drafting.draft_benchmark(self.b, FakeDraftAI(bad)).ok)
        self.assertFalse(EvidenceRule.objects.filter(benchmark=self.b).exists())

    def test_ai_failure_changes_nothing(self):
        result = ai_drafting.draft_benchmark(self.b, FakeDraftAI(error=RuntimeError('router down')))
        self.assertFalse(result.ok)
        self.assertIn('router down', result.detail)

    def test_rerun_replaces_ai_work_but_keeps_what_a_person_wrote(self):
        ai_drafting.draft_benchmark(self.b, FakeDraftAI(_good_draft()))
        person = User.objects.create_user(email='e@ingage.ai', username='e', password='Str0ng!Pass', role='consultant')
        _authoring.save_level(self.b, 'L2', person, {'definition': 'An expert-written L2 that names the review '
                                                                   'board, KPIs and the corrective-action log.'})
        from .services import evidence_rules
        evidence_rules.create_rule(person, {'evidence_type': 'EV-09', 'title': 'Expert data rule', 'level': 'L2'},
                                   benchmark=self.b)
        result = ai_drafting.draft_benchmark(self.b, FakeDraftAI(_good_draft()))
        self.assertTrue(result.ok, result.detail)
        self.assertIn('L2 level', result.kept_human)
        self.assertTrue(self.b.maturity_levels.get(level='L2').definition.startswith('An expert-written'))
        self.assertEqual(EvidenceRule.objects.filter(benchmark=self.b, ai_model='').count(), 1)  # the expert's
        self.assertEqual(EvidenceRule.objects.filter(benchmark=self.b).exclude(ai_model='').count(), 4)  # not 8

    def test_only_drafts_are_written(self):
        Benchmark.objects.filter(pk=self.b.pk).update(status='active')
        self.b.refresh_from_db()
        ai = FakeDraftAI(_good_draft())
        self.assertFalse(ai_drafting.draft_benchmark(self.b, ai).ok)
        self.assertEqual(ai.calls, [])
