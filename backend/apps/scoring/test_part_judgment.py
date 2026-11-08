"""Part-level judgment: code, not the model, turns part findings into a state and a credit fraction."""
import json

from django.test import SimpleTestCase, override_settings

from apps.scoring.capability import part_judgment as pj
from apps.scoring.capability.engine import assess, documented, release
from apps.scoring.capability.evaluation import evaluate

QUOTE_PLAN = 'The Strategic Plan 2019-24 approved by the Board of Management lists e-governance as a priority.'
QUOTE_OWNER = 'The Registrar is responsible for implementing the e-governance priority.'
SOURCE = {'id': 'doc:1', 'document_id': 'doc', 'page_number': 1, 'text': QUOTE_PLAN + '\n' + QUOTE_OWNER}


def c11():
    return next(i for i in release()['indicators'] if i['code'] == 'AIQIF-C1.1')


def part(finding, quote=None):
    return {'finding': finding, 'citations': [{'source_id': 'doc:1', 'quote': quote}] if quote else []}


def condition(parts, scope=True, period=True):
    return {'reason': 'Checked.', 'scope_supported': scope, 'period_supported': period, 'parts': parts}


def response(**overrides):
    """Every C1.1 condition not found unless overridden."""
    spec = pj.specification(release())
    rows = {}
    for c in c11()['conditions']:
        ids = [p['id'] for p in spec[c['id']]['parts']]
        rows[c['id']] = overrides.get(c['id'].split('.')[-1], condition({pid: part('not_found') for pid in ids}))
    return {'conditions': rows}


def judged(resp):
    records = pj.judge_rows(c11(), pj.rows(resp), [{**SOURCE, 'text_offset': 0}])
    return {r['condition_id'].split('.')[-1]: r for r in records}


class SpecificationTests(SimpleTestCase):
    def test_every_condition_has_two_to_four_parts_matching_the_rubric(self):
        spec = pj.specification(release())
        self.assertEqual(len(spec), 216)
        self.assertTrue(all(2 <= len(c['parts']) <= 4 for c in spec.values()))
        self.assertTrue(all(p['full'] and p['related'] for c in spec.values() for p in c['parts']))

    def test_schema_requires_every_part(self):
        schema = pj.schema(c11())
        f1 = schema['properties']['conditions']['properties']['AIQIF-C1.1.F1']
        findings = f1['properties']['findings']
        self.assertEqual((findings['minItems'], findings['maxItems']), (2, 2))
        self.assertEqual(findings['items']['properties']['part_id']['enum'], ['p1', 'p2'])

    def test_findings_array_and_duplicate_parts(self):
        r = judged(response(F2={'reason': 'x', 'scope_supported': True, 'period_supported': True, 'findings': [
            {'part_id': 'p1', 'finding': 'full', 'citations': [{'source_id': 'doc:1', 'quote': QUOTE_OWNER}]},
            {'part_id': 'p2', 'finding': 'full', 'citations': [{'source_id': 'doc:1', 'quote': QUOTE_OWNER}]}]}))['F2']
        self.assertEqual((r['state'], r['credit']), ('met', 1.0))
        r = judged(response(F2={'reason': 'x', 'scope_supported': True, 'period_supported': True, 'findings': [
            {'part_id': 'p1', 'finding': 'full', 'citations': [{'source_id': 'doc:1', 'quote': QUOTE_OWNER}]},
            {'part_id': 'p1', 'finding': 'not_found', 'citations': []},
            {'part_id': 'p2', 'finding': 'full', 'citations': [{'source_id': 'doc:1', 'quote': QUOTE_OWNER}]}]}))['F2']
        self.assertEqual((r['state'], r['credit']), ('unknown', 0.0))  # the subject part was reported twice


class JudgeTests(SimpleTestCase):
    def test_all_parts_full_is_met_with_full_credit(self):
        r = judged(response(F1=condition({'p1': part('full', QUOTE_PLAN), 'p2': part('full', QUOTE_PLAN)})))['F1']
        self.assertEqual((r['state'], r['credit']), ('met', 1.0))
        self.assertEqual(r['citations'], [{'source_id': 'doc:1', 'quote': QUOTE_PLAN}])

    def test_related_and_missing_parts_give_partial_credit_and_unknown(self):
        r = judged(response(A1=condition({'p1': part('full', QUOTE_PLAN), 'p2': part('related', QUOTE_PLAN),
                                          'p3': part('not_found')})))['A1']
        self.assertEqual(r['state'], 'unknown')
        self.assertEqual(r['credit'], 0.5)  # (1 + 0.5 + 0) / 3
        self.assertTrue(r['citations'])

    def test_unverifiable_quote_counts_as_not_found(self):
        r = judged(response(F2=condition({'p1': part('full', QUOTE_OWNER),
                                          'p2': part('full', 'An invented passage that is not on the page at all.')})))['F2']
        self.assertEqual((r['state'], r['credit']), ('unknown', 0.5))
        self.assertEqual([p['finding'] for p in r['parts']], ['full', 'not_found'])
        self.assertTrue(r['part_issues'])

    def test_unsupported_period_caps_full_parts_at_related(self):
        r = judged(response(F2=condition({'p1': part('full', QUOTE_OWNER), 'p2': part('full', QUOTE_OWNER)},
                                         period=False)))['F2']
        self.assertEqual((r['state'], r['credit']), ('unknown', 0.5))

    def test_contradicted_part_is_not_met(self):
        r = judged(response(F2=condition({'p1': part('full', QUOTE_OWNER), 'p2': part('contradicted', QUOTE_OWNER)})))['F2']
        self.assertEqual((r['state'], r['credit']), ('not_met', 0.5))

    def test_missing_condition_is_unknown_with_no_credit(self):
        resp = response()
        del resp['conditions']['AIQIF-C1.1.O2']
        r = judged(resp)['O2']
        self.assertEqual((r['state'], r['credit']), ('unknown', 0.0))


class CombineTests(SimpleTestCase):
    def test_parts_average_and_disagreement_goes_to_review(self):
        first = pj.judge_rows(c11(), pj.rows(response(F2=condition({'p1': part('full', QUOTE_OWNER),
                                                                     'p2': part('full', QUOTE_OWNER)}))),
                              [{**SOURCE, 'text_offset': 0}])
        second = pj.judge_rows(c11(), pj.rows(response(F2=condition({'p1': part('full', QUOTE_OWNER),
                                                                      'p2': part('not_found')}))),
                               [{**SOURCE, 'text_offset': 0}])
        combined, disagreements = pj.combine(first, second)
        f2 = next(r for r in combined if r['condition_id'].endswith('F2'))
        self.assertEqual(f2['state'], 'unknown')
        self.assertEqual(f2['cause'], 'assessor_disagreement')
        self.assertEqual(f2['credit'], 0.75)  # (1 + 0.5) / 2
        self.assertEqual(disagreements, [{'condition_id': 'AIQIF-C1.1.F2', 'first': 'met', 'second': 'unknown'}])

    def test_identical_passes_are_unchanged(self):
        resp = response(F2=condition({'p1': part('full', QUOTE_OWNER), 'p2': part('related', QUOTE_OWNER)}))
        first = pj.judge_rows(c11(), pj.rows(resp), [{**SOURCE, 'text_offset': 0}])
        second = pj.judge_rows(c11(), pj.rows(resp), [{**SOURCE, 'text_offset': 0}])
        combined, disagreements = pj.combine(first, second)
        self.assertEqual(disagreements, [])
        self.assertEqual([r['credit'] for r in combined], [r['credit'] for r in first])
        self.assertEqual([r['state'] for r in combined], [r['state'] for r in first])


class DocumentedScoreTests(SimpleTestCase):
    def test_full_credit_everywhere_equals_all_met(self):
        rubric = release()
        ids = [c['id'] for i in rubric['indicators'] for c in i['conditions']]
        self.assertEqual(documented({cid: 1 for cid in ids}, rubric)['overall'], assess({cid: 'met' for cid in ids}, rubric)['lower'])
        self.assertEqual(documented({}, rubric)['overall'], 0.0)

    def test_documented_lies_between_lower_and_upper(self):
        rubric = release()
        ids = [c['id'] for i in rubric['indicators'] for c in i['conditions']]
        decisions = {cid: 'met' for cid in ids[:20]}
        credits = {**{cid: 1 for cid in ids[:20]}, **{cid: 0.5 for cid in ids[20:60]}}
        result = assess(decisions, rubric)
        score = documented(credits, rubric)['overall']
        self.assertGreater(score, result['lower'])
        self.assertLessEqual(score, result['upper'])


class Parts:
    """Fake service: C1.1.F2 fully evidenced, everything else not found; records the prompt used."""

    def __init__(self):
        self.prompts = set()

    def extract_structured_data(self, **kwargs):
        self.prompts.add(kwargs['system_prompt'])
        payload = json.loads(kwargs['user_content'])
        rows = {}
        for c in payload['indicator']['conditions']:
            ids = [p['id'] for p in c['parts']]
            found = c['id'] == 'AIQIF-C1.1.F2'
            rows[c['id']] = {'reason': 'Checked.', 'scope_supported': True, 'period_supported': True,
                             'findings': [{'part_id': pid, **(part('full', QUOTE_OWNER) if found else part('not_found'))}
                                          for pid in ids]}
        return {'conditions': rows}


class EvaluateTests(SimpleTestCase):
    def test_part_judgment_end_to_end(self):
        service = Parts()
        result = evaluate([SOURCE], service=service, population='All programmes', reference_period='2025-26',
                          judgment='parts', agreement_passes=2)
        self.assertEqual(service.prompts, {pj.PART_PROMPT})
        records = {r['condition_id']: r for r in result['records']}
        self.assertEqual(records['AIQIF-C1.1.F2']['state'], 'met')
        self.assertEqual(records['AIQIF-C1.1.F2']['credit'], 1.0)
        self.assertEqual(sum(r['credit'] for r in result['records']), 1.0)
        self.assertEqual(result['traces'][0]['judgment']['judgment'], pj.JUDGMENT)

    def test_unknown_judgment_is_refused(self):
        with self.assertRaises(ValueError):
            evaluate([SOURCE], service=Parts(), population='All programmes', reference_period='2025-26', judgment='other')


class PolicyTests(SimpleTestCase):
    @override_settings(CAPABILITY_JUDGMENT='parts', CAPABILITY_ASSESSMENT_ENABLED=True)
    def test_policy_freezes_part_judgment(self):
        from apps.scoring.capability.execution import policy
        frozen = policy()
        self.assertEqual(frozen['judgment'], 'parts')
        self.assertEqual(frozen['parts_version'], pj.VERSION)

    @override_settings(CAPABILITY_JUDGMENT='conditions')
    def test_default_policy_has_no_part_judgment(self):
        from apps.scoring.capability.execution import policy
        self.assertNotIn('judgment', policy())


class ReportTests(SimpleTestCase):
    def test_documented_readiness_reaches_view_html_and_pdf(self):
        import pymupdf
        from django.template.loader import render_to_string
        from apps.scoring.capability.leadership_pdf import render_leadership_pdf
        from apps.scoring.capability.report_projection import build_report_view
        from apps.scoring.test_report_projection import report_fixture
        report, actions = report_fixture({'AIQIF-C6.1.F1': 'met'})
        rubric = release()
        credits = {'AIQIF-C6.1.F1': 1, 'AIQIF-C6.1.F2': 0.5}
        report['assessment']['result']['documented'] = documented(credits, rubric)
        view = build_report_view(report, actions)
        self.assertTrue(view['documented_score'].startswith('Documented readiness'))
        self.assertIn('documented_score', view['pillars'][0])
        html = render_to_string('scoring/leadership_report.html', {'view': view, 'report': report})
        self.assertIn('Documented readiness', html)
        text = ''.join(page.get_text() for page in pymupdf.open(stream=render_leadership_pdf(view), filetype='pdf'))
        self.assertIn('Documented readiness', text)

    def test_reports_without_part_judgment_are_unchanged(self):
        from apps.scoring.capability.report_projection import build_report_view
        from apps.scoring.test_report_projection import report_fixture
        report, actions = report_fixture({'AIQIF-C6.1.F1': 'met'})
        view = build_report_view(report, actions)
        self.assertNotIn('documented_score', view)
