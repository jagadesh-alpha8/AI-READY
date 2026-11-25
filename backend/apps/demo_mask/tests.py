import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from rest_framework.test import APITestCase

from . import mask


def _reset():
    mask._compiled.cache_clear()
    from apps.scoring.capability.run_view import code_fingerprint
    code_fingerprint.cache_clear()


@override_settings(DEMO_NAME_MASK='vistas')
class VistasTermListTests(SimpleTestCase):
    """The shipped list catches the forms VISTAS's documents use (collected from test 13's exports)."""

    def setUp(self):
        _reset()
        self.addCleanup(_reset)

    def test_every_form_of_the_name(self):
        cases = {
            'VELS INSTITUTE OF SCIENCE, TECHNOLOGY AND ADVANCED STUDIES(VISTAS)': 'ABC University',
            "Vel's Institute of Science, Technology and Advanced Studies (VISTAS), Chennai": 'ABC University, Chennai',
            'Vels Institute of Science, Technology & Advanced Studies (VISTAS)': 'ABC University',
            'VELS INSTITUTE OF SCIENCE TECHNOLOGY AND ADVANCED STUDIES (VISTAS)': 'ABC University',
            'Vels Institute of Science, Technology and Advanced Studies , Chennai': 'ABC University , Chennai',
            "Vel's Institute of Science, Technology | Intake": 'ABC University | Intake',
            'VELS UNIVERSITY(VISTAS)': 'ABC University',
            'vels university': 'ABC University',
            "VISTAS's faculty": "ABC University's faculty",
            'VISTAS’ Industry Engagement': 'ABC University’ Industry Engagement',
            'VISTAS-NSS volunteers': 'ABC University-NSS volunteers',
            'Vels Medical College': 'ABC Medical College',
            'Vel’s Knowledge Resource Centre': 'ABC Knowledge Resource Centre',
            'Vels Group of Institutions.': 'ABC Group of Institutions.',
            'www.velsuniv.ac.in/AQAR/SSS-Report.pdf': 'www.abc-university.example/AQAR/SSS-Report.pdf',
            'director.iqac@velsuniv.ac.in': 'director.iqac@abc-university.example',
            'Pallavaram Campus': 'Campus A',
            'PALLAVARAM CAMPUS | PROGRAMMES': 'Campus A | PROGRAMMES',
            'VELAN NAGAR, P.V.VAITHIYALINGAM ROAD, PALLAVARAM, CHENNAI': '[campus address], [campus address], Campus A, CHENNAI',
            'Ishari VELAN Mission Hospital': 'ABC Mission Hospital',
            'Thalambur and Periyapalayam': 'Campus B and Campus C',
            '[campus address],\\nPallavaram, Chennai - 600117': '[campus address],\\nCampus A, Chennai - 600 000',
            'VELS INSTITUTE OF SCIENCE, TECHNOLOGY AND ADVANCED STUDIES(VISTA: Examination': 'ABC University: Examination',
            'www.vistas.ac.in': 'www.abc-university.example',
            'Founder Chairman Dr. Ishari\\nK Ganesh, is': 'Founder Chairman Dr. the founder, is',
            'Shri. Isari Velan Mission Hospital': 'Shri. ABC Mission Hospital',
            'The Velan Arangam open auditorium': 'The ABC Arangam open auditorium',
            '(Near Navalur) Chennai - 600 130.': '(Near [campus area]) Chennai - 600 000.',
            'Vel Nursing College (VNC)': 'ABC Nursing College (VNC)',
            'research, VISTASVISTAS narrows': 'research, ABC University narrows',
        }
        for given, expected in cases.items():
            self.assertEqual(mask.text(given), expected, given)

    def test_words_that_only_contain_a_term_are_left_alone(self):
        for word in ('Velachery', 'Velraj', 'Velmurugan', 'VISTASPHERE', 'television', 'Ishwariya Ganesh', 'Ms. Pallavi',
                     'Tel: 6001170', 'level.'):
            self.assertEqual(mask.text(word), word)

    def test_json_escapes_and_html_entities(self):
        self.assertEqual(mask.text('"Vel\\u2019s Institute of Science, Technology"'), '"ABC University"')
        self.assertEqual(mask.text('Science, Technology &amp; Advanced Studies'), 'Science, Technology &amp; Advanced Studies')
        self.assertEqual(mask.text('Vels Institute of Science, Technology &amp; Advanced Studies (VISTAS)'), 'ABC University')

    def test_programme_names_and_facts_are_not_masked(self):
        text = 'B.Tech Artificial Intelligence; 2,760 computers; 135 programmes; NAAC A++ with CGPA 3.52'
        self.assertEqual(mask.text(text), text)

    def test_masking_twice_changes_nothing_more(self):
        once = mask.text('VISTAS (Vels University), Pallavaram')
        self.assertEqual(mask.text(once), once)

    def test_data_walks_nested_values_and_keeps_keys(self):
        self.assertEqual(mask.data({'VISTAS': ['VISTAS', {'n': 'Vels University', 'k': 3}], 'x': None}),
                         {'VISTAS': ['ABC University', {'n': 'ABC University', 'k': 3}], 'x': None})


class OffByDefaultTests(SimpleTestCase):
    def test_off_changes_nothing(self):
        _reset()
        with override_settings(DEMO_NAME_MASK=''):
            self.assertFalse(mask.active())
            self.assertEqual(mask.text('VISTAS'), 'VISTAS')
            self.assertEqual(mask.data({'a': 'VISTAS'}), {'a': 'VISTAS'})
            self.assertEqual(mask.fingerprint(), '')

    def test_unknown_list_is_refused(self):
        _reset()
        with override_settings(DEMO_NAME_MASK='no-such-list'), self.assertRaises(ValueError):
            mask.text('x')


class ApiMaskTests(APITestCase):
    """The mask on real responses: run detail, reports (JSON, HTML, PDF) and refused original-file downloads. Uses the
    report tests' run, whose institution is "College", with a term list mapping it to "ABC University"."""

    def setUp(self):
        from apps.scoring import test_capability_reports as reports
        self.tmp = tempfile.TemporaryDirectory()
        Path(self.tmp.name, 'testlist.json').write_text(json.dumps([{'find': 'College', 'replace': 'ABC University'}]))
        patcher = patch.object(mask, 'TERMS_DIR', Path(self.tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)
        _reset()
        self.addCleanup(_reset)
        self.settings_override = override_settings(SECURE_SSL_REDIRECT=False, CAPABILITY_RECOMMENDATIONS_ENABLED=True,
                                                   CAPABILITY_ASSESSMENT_ENABLED=True)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.case = reports.CapabilityReportTests
        self.case.setUp(self)
        self.run_url = f'/api/v1/sprints/{self.sprint.pk}/capability-runs/{self.run.pk}'

    # CapabilityReportTests.setUp calls these through `self`.
    def prepare_run(self):
        self.case.prepare_run(self)

    @property
    def rows(self):
        return self.case.rows

    @property
    def response(self):
        return self.case.response

    def test_reports_and_screens_are_masked_only_when_switched_on(self):
        plain = self.client.get(self.report_url, {'file': 'json'})
        self.assertEqual(json.loads(plain.content)['profile']['name'], 'College')
        detail_off = self.client.get(self.run_url)
        _reset()
        with override_settings(DEMO_NAME_MASK='testlist'):
            masked = self.client.get(self.report_url, {'file': 'json'})
            self.assertEqual(json.loads(masked.content)['profile']['name'], 'ABC University')
            self.assertNotIn(b'College', masked.content)
            html = self.client.get(self.report_url, {'audience': 'evidence'})
            self.assertEqual(html.status_code, 200)
            self.assertNotIn(b'College', html.content)
            detail_on = self.client.get(self.run_url)
            self.assertEqual(detail_on.status_code, 200)
            # The version marker changes, so a screen holding an unmasked copy fetches the masked one.
            self.assertNotEqual(detail_off['ETag'], detail_on['ETag'])
            self.assertNotIn(b'College', detail_on.content)
        _reset()

    def test_pdf_is_rendered_from_masked_data(self):
        import pymupdf
        _reset()
        with override_settings(DEMO_NAME_MASK='testlist'):
            for audience in ('evidence', 'leadership', 'summary', 'detailed'):
                response = self.client.get(self.report_url, {'file': 'pdf', 'audience': audience})
                self.assertEqual(response.status_code, 200, audience)
                self.assertEqual(response['X-Name-Mask'], 'applied')
                text = ''.join(page.get_text() for page in pymupdf.open(stream=response.content, filetype='pdf'))
                self.assertNotIn('College', text, audience)
        _reset()

    def test_original_files_are_refused_while_on(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from apps.documents.models import Document
        document = Document.objects.create(sprint=self.sprint, document_type='naac_ssr', status='processed',
                                           original_filename='College SSR.pdf',
                                           file=SimpleUploadedFile('ssr.pdf', b'%PDF-1.4 College letterhead'))
        url = f'/api/v1/documents/{document.pk}/download'
        before = self.client.get(url)
        _reset()
        with override_settings(DEMO_NAME_MASK='testlist'):
            blocked = self.client.get(url)
        _reset()
        self.assertEqual(before.status_code, 200)
        self.assertEqual(blocked.status_code, 403)
        self.assertEqual(blocked.json()['code'], 'demo_mask_download_blocked')
