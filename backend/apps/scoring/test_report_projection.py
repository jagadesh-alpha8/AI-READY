from copy import deepcopy
from types import SimpleNamespace

from django.test import SimpleTestCase

from .capability.engine import assess, release
from .capability.diagnostics import explain
from .capability.report_projection import advisory_state, build_report_view
from .capability.report_views import ReportIntegrityError, validate_report_identity
from .capability.storage import digest


def report_fixture(overrides=None, default='unknown'):
    """Synthetic presentation fixture; not an institutional validity judgement."""
    rubric = release()
    states = {c['id']: default for i in rubric['indicators'] for c in i['conditions']}
    states.update(overrides or {})
    manifest = [{'filename': 'Synthetic curriculum.pdf', 'version': 1, 'document_id': 'doc1',
                 'checksum': 'test', 'status': 'processed', 'expected_pages': 1,
                 'pages': [{'page_id': 'page1', 'number': 1}]}]
    records, actions = [], []
    for item in rubric['indicators']:
        for condition in item['conditions']:
            cid = condition['id']
            row = {'condition_id': cid, 'state': states[cid], 'reason': 'Synthetic scoped fixture',
                   'citations': [], 'validation_issue': ''}
            records.append(row)
            if states[cid] != 'met':
                actions.append({'id': cid, 'indicator': item['code'], 'state': states[cid],
                                'requirement': condition['text'],
                                'completion_evidence': condition['completion_evidence'],
                                'citations': [], 'advice': None})
    report = {'profile': {'name': 'Illustrative College - synthetic example'},
              'population': 'BBA students in the assessed programme only',
              'reference_period': '2024 regulation; delivery period not established',
              'source_manifest': manifest, 'recommendation': None,
              'assessment': {'records': records, 'result': assess(states, rubric)}}
    report['diagnostics'] = explain({'rubric': rubric, 'manifest': manifest, 'sources': [{'id': 'page1'}]}, report['assessment'])
    return report, actions


class ReadableProjectionTests(SimpleTestCase):
    def test_pdf_handles_supported_long_scope_and_institution_names(self):
        import pymupdf
        from .capability.leadership_pdf import render_leadership_pdf
        report, actions = report_fixture()
        view = build_report_view(report, actions)
        view['institution'] = 'W' * 255
        view['population'] = 'W' * 2000
        document = pymupdf.open(stream=render_leadership_pdf(view), filetype='pdf')
        self.assertIn('Not established', ''.join(page.get_text() for page in document))
        for page in document:
            for block in page.get_text('blocks'):
                self.assertLess(block[3], page.rect.height - 10)

    def test_scope_identity_and_refinement_notices_survive_html_and_pdf(self):
        import pymupdf
        from django.template.loader import render_to_string
        from .capability.leadership_pdf import render_leadership_pdf
        report, actions = report_fixture(default='met')
        report['scope'] = {'mode': 'default', 'limitations': 'Source labels are unverified.', 'questions': [
            {'code': 'institution_identity_mismatch', 'severity': 'review', 'message': 'A source names a different institution.'}]}
        report['refines_run_id'] = 'older-scope'
        frozen = deepcopy(report)
        view = build_report_view(report, actions)
        self.assertEqual(view['assessment_state'], 'Provisional findings')
        self.assertEqual(view['score'], '100 / 100')
        self.assertEqual(report, frozen)
        html = render_to_string('scoring/leadership_report.html', {'view': view, 'report': report})
        self.assertIn('Scope needs review', html)
        self.assertIn('A source names a different institution.', html)
        self.assertIn('does not by itself show institutional improvement', html)
        document = pymupdf.open(stream=render_leadership_pdf(view), filetype='pdf')
        first_page = document[0].get_text()
        self.assertIn('Scope needs review', first_page)
        self.assertIn('different institution', first_page)
        self.assertIn('Universal coverage', first_page)

    def test_sparse_evidence_is_unknown_and_never_a_zero_score(self):
        report, actions = report_fixture()
        original = deepcopy(report)
        view = build_report_view(report, actions)
        self.assertEqual(view['score'], 'Not established')
        self.assertEqual(view['advisory']['kind'], 'basic')
        self.assertEqual(len(view['areas']), 36)
        self.assertTrue(all(area['score'] == 'Not established' for area in view['areas']))
        self.assertLessEqual(len(view['priorities']), 5)
        self.assertEqual(report, original)
        self.assertNotIn('does not have', ' '.join(view['limitations']))

    def test_documented_curriculum_does_not_establish_delivery_or_mastery(self):
        report, actions = report_fixture({'AIQIF-C3.1.F1': 'met', 'AIQIF-C3.1.F2': 'met'})
        view = build_report_view(report, actions)
        area = next(a for a in view['areas'] if a['key'] == 'AIQIF-C3.1')
        self.assertEqual(area['score'], 'Not established')
        self.assertEqual([s['status'] for s in area['stages']], ['Demonstrated', 'Not established', 'Not established'])
        self.assertEqual(view['population'], report['population'])
        self.assertEqual(view['period'], report['reference_period'])

    def test_planned_work_only_retains_the_satisfied_planning_requirement(self):
        report, actions = report_fixture({'AIQIF-C1.1.F2': 'met'})
        view = build_report_view(report, actions)
        area = next(a for a in view['areas'] if a['key'] == 'AIQIF-C1.1')
        self.assertEqual(area['stages'][0]['status'], 'Not established')
        self.assertIn('Some requirements are demonstrated', area['finding'])
        self.assertEqual(report['assessment']['result']['exact_score'], None)

    def test_documented_absence_is_distinct_from_unknowns(self):
        report, actions = report_fixture({'AIQIF-C4.1.F1': 'not_met'})
        view = build_report_view(report, actions)
        known = next(a for a in view['areas'] if a['key'] == 'AIQIF-C4.1')
        unknown = next(a for a in view['areas'] if a['key'] == 'AIQIF-C4.2')
        self.assertEqual(known['score'], '0 / 100')
        self.assertIn('documented shortfall', known['finding'])
        self.assertEqual(unknown['score'], 'Not established')

    def test_conflicting_sources_are_not_chosen_arbitrarily(self):
        report, actions = report_fixture({'AIQIF-C3.1.F1': 'conflicting'})
        view = build_report_view(report, actions)
        area = next(a for a in view['areas'] if a['key'] == 'AIQIF-C3.1')
        self.assertIn('contradictory', area['finding'])
        self.assertTrue(area['next_step'].startswith('Reconcile'))
        self.assertEqual(view['priorities'][0]['area_key'], 'AIQIF-C3.1')

    def test_earlier_steps_precede_high_weight_outcome_scenarios(self):
        report, actions = report_fixture({'AIQIF-C1.1.O1': 'unknown', 'AIQIF-C9.4.F1': 'unknown'}, default='met')
        view = build_report_view(report, actions)
        self.assertEqual(view['priorities'][0]['area_key'], 'AIQIF-C9.4')
        self.assertEqual(view['priorities'][1]['area_key'], 'AIQIF-C1.1')

    def test_failed_pending_deterministic_and_empty_advice_are_basic(self):
        for status in ('queued', 'running', 'failed', 'cancelled'):
            self.assertEqual(advisory_state({'status': status, 'tailoring': None})['kind'], 'basic')
        for tailoring in ({'mode': 'deterministic', 'advice': []}, {'mode': 'tailored', 'advice': []}):
            self.assertEqual(advisory_state({'status': 'completed', 'tailoring': tailoring})['kind'], 'basic')
        state = advisory_state({'status': 'completed', 'tailoring': {'mode': 'tailored', 'advice': [
            {'condition_id': 'AIQIF-C1.1.F1', 'steps': ['Confirm the current plan.']}]}})
        self.assertEqual(state['kind'], 'tailored')

    def test_generated_codes_are_readable_but_original_quotes_are_preserved(self):
        report, actions = report_fixture()
        actions[0]['advice'] = {'steps': ['Review AIQIF-C1.1.F1'], 'suggested_role': 'Academic lead',
            'effort': 'unknown', 'completion_evidence': 'Confirm AIQIF-C1.1.F1',
            'dependencies': [], 'basis': [{'source_id': 'page1', 'quote': 'Original AIQIF-C1.1.F1 text'}]}
        view = build_report_view(report, actions)
        self.assertNotIn('AIQIF-', view['priorities'][0]['steps'][0])
        self.assertEqual(view['priorities'][0]['sources'][0]['quote'], 'Original AIQIF-C1.1.F1 text')


class ReportIdentityTests(SimpleTestCase):
    def fixture(self):
        run = SimpleNamespace(pk='run1', inputs={'sources': []}, inputs_hash=digest({'sources': []}))
        event = SimpleNamespace(pk=7, payload={'inputs_hash': run.inputs_hash, 'result': {}})
        plan = {'assessment_event_id': 7, 'assessment_hash': digest(event.payload), 'run_inputs_hash': run.inputs_hash}
        snapshot = SimpleNamespace(run_id=run.pk, inputs=plan, inputs_hash=digest(plan), assessment_event_id=7)
        completed = SimpleNamespace(payload={'inputs_hash': snapshot.inputs_hash})
        return run, event, snapshot, completed

    def test_matching_version_is_accepted(self):
        validate_report_identity(*self.fixture())

    def test_integrity_and_semantic_linkage_both_required(self):
        run, event, snapshot, completed = self.fixture()
        snapshot.inputs['assessment_hash'] = 'other assessment'
        snapshot.inputs_hash = digest(snapshot.inputs)
        completed.payload['inputs_hash'] = snapshot.inputs_hash
        with self.assertRaises(ReportIntegrityError):
            validate_report_identity(run, event, snapshot, completed)
        run, event, snapshot, completed = self.fixture()
        snapshot.run_id = 'other run'
        with self.assertRaises(ReportIntegrityError):
            validate_report_identity(run, event, snapshot, completed)
        run, event, snapshot, completed = self.fixture()
        completed.payload['inputs_hash'] = 'other advice version'
        with self.assertRaises(ReportIntegrityError):
            validate_report_identity(run, event, snapshot, completed)
        run, event, snapshot, completed = self.fixture()
        run.inputs['sources'].append('changed after freeze')
        with self.assertRaises(ReportIntegrityError):
            validate_report_identity(run, event, snapshot, completed)
