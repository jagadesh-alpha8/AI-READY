from unittest import TestCase

from .capability.engine import release
from .capability.evaluation import select_context
from .capability.requirement_evidence import apply_pilot, requirement_rows
from .capability.query_profiles import evidence_query

# Excerpts represent independently located records. Linkage is an assessor
# decision and is deliberately not inferred from the presence of these parts.
CASES = {
    'C2.1.F1': (
        'AI acceptable use guidance G-17 for instructors prohibits uploading identifiable student work.',
        'Guidance G-17 was adopted for instructors and is effective from 1 October 2025.',
    ),
    'C2.1.A1': (
        'AI policy provision 4 requires consent before using student data.',
        'AI chatbot deployment S-17 for course advising began in October 2025.',
        'The deployment checklist for S-17 was completed and verified consent against provision 4.',
    ),
    'C6.1.O1': (
        'Monitoring measured 97% uptime for the Research Compute Service in October 2025.',
        'The SLA target is 99% uptime for the Research Compute Service for October 2025.',
        'The completed capacity review compared Research Compute Service uptime against the SLA and recorded a shortfall.',
    ),
    'C9.4.A2': (
        'The action register records corrective action A-17 to remove duplicate workshop registration prompts.',
        'The follow-up minute verified completion of action A-17 by inspecting the updated registration form.',
    ),
    'C9.4.O1': (
        'Workshop registration feedback identified that duplicate prompts were confusing.',
        'The team implemented a single registration prompt in response to workshop feedback in May.',
        'The June follow-up survey found fewer duplicate workshop registrations after the change.',
    ),
}


def fixtures(condition, variant):
    excerpts = list(CASES[condition['id'].removeprefix('AIQIF-')])
    if variant == 'missing':
        excerpts.pop()
    if variant == 'mismatch':
        original, unrelated = {
            'C2.1.F1': ('G-17', 'G-81'),
            'C2.1.A1': ('S-17', 'S-81'),
            'C6.1.O1': ('Research Compute Service', 'Admissions Service'),
            'C9.4.A2': ('A-17', 'A-81'),
            'C9.4.O1': ('workshop', 'orientation'),
        }[condition['id'].removeprefix('AIQIF-')]
        excerpts[-1] = excerpts[-1].replace(original, unrelated)
    sources = [{'id': f'part-{n}', 'text': text} for n, text in enumerate(excerpts)]
    # High topical overlap, with no affirmative record for any of the pilot parts.
    noise = ' '.join(condition['text'].lower().split()[:5])
    return sources + [{'id': f'noise-{n}', 'text': (noise + ' ') * 70} for n in range(16)]


class RequirementEvidenceTests(TestCase):
    def test_pilot_delivers_exact_record_parts_in_fifteen_cases(self):
        for indicator in apply_pilot(release())['indicators']:
            for condition in indicator['conditions']:
                if condition['id'].removeprefix('AIQIF-') not in CASES:
                    continue
                for variant in ('complete', 'missing', 'mismatch'):
                    with self.subTest(condition=condition['id'], variant=variant):
                        scoped = {**indicator, 'conditions': [condition]}
                        sources = fixtures(condition, variant)
                        packet = select_context(scoped, sources, max_chars=4000)
                        self.assertLessEqual(sum(len(s['text']) for s in packet), 4000)
                        self.assertEqual({s['id'] for s in sources if s['id'].startswith('part-')},
                                         {s['id'] for s in packet if s['id'].startswith('part-')})
                        for excerpt in packet:
                            original = next(s['text'] for s in sources if s['id'] == excerpt['id'])
                            start = excerpt['text_offset']
                            self.assertEqual(excerpt['text'], original[start:start + len(excerpt['text'])])
                        self.assertTrue(condition['evidence_link_rule'])

    def test_pilot_changes_only_five_conditions_and_preserves_baseline_queries(self):
        baseline = release()
        pilot = apply_pilot(baseline)
        originals = {c['id']: c for i in baseline['indicators'] for c in i['conditions']}
        changes = [c for i in pilot['indicators'] for c in i['conditions'] if c != originals[c['id']]]
        self.assertEqual({c['id'].removeprefix('AIQIF-') for c in changes}, set(CASES))
        self.assertNotEqual(baseline['content_hash'], pilot['content_hash'])
        for condition in changes:
            self.assertTrue(evidence_query(originals[condition['id']]))
            self.assertEqual(evidence_query(condition), ' '.join(condition['evidence_parts'].values()))
        self.assertEqual(baseline, release())

    def test_small_allowance_leaves_existing_ranker_in_charge(self):
        item = next(i for i in apply_pilot(release())['indicators'] if i['code'] == 'AIQIF-C9.4')
        self.assertEqual(list(requirement_rows(item, [{'id': 'empty', 'text': ''}], 100)), [])
