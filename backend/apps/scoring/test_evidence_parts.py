from unittest import TestCase

from .capability.engine import release
from .capability.evaluation import select_context, validate_decisions


def indicator(code):
    return next(i for i in release()['indicators'] if i['code'] == code)


def source(identifier, page, text, document='syllabus'):
    return {'id': identifier, 'document_id': document, 'page_number': page, 'text': text}


class EvidencePartsTests(TestCase):
    def test_approval_guard_requires_recorded_approval_for_same_edition(self):
        code = 'AIQIF-C3.1'
        item = indicator(code)
        cohort = 'Applicable to candidates admitted from academic year 2023–24 onwards.'
        cover = source('cover', 1, 'Regulations 2023\n' + cohort)
        course = source('course', 3, 'Students learn to train machine learning classifiers.')
        for quote, doc, expected in (
            ('List of members of the Academic Council', 'syllabus', 'unknown'),
            ('The Academic Council may approve the syllabus under Regulations 2023.', 'syllabus', 'unknown'),
            ('The Academic Council approved the syllabus under Regulations 2024.', 'syllabus', 'unknown'),
            ('The Academic Council approved the syllabus under Regulations 2023.', 'another', 'unknown'),
            ('The Academic Council approved the syllabus under Regulations 2023.', 'syllabus', 'met'),
        ):
            with self.subTest(quote=quote, document=doc):
                approval = source('approval', 2, quote, doc)
                edition = [cover, approval, course]
                if doc != 'syllabus':
                    edition.append(source('p2', 2, 'Course list'))
                packet = [course, approval]
                response = {'conditions': [{'condition_id': code + '.F1', 'state': 'met', 'reason': 'Synthetic',
                    'scope_supported': True, 'period_supported': True,
                    'citations': [{'source_id': s['id'], 'quote': s['text']} for s in packet]}]}
                rows = validate_decisions(item, response, packet, edition_sources=edition)
                self.assertEqual(next(r for r in rows if r['condition_id'] == code + '.F1')['state'], expected)

    def test_distinct_hardware_and_workload_candidates_survive_competition(self):
        item = indicator('AIQIF-C6.1')
        hardware = source('hardware', 7, '2019 | Installed 25 Core i5 desktops with 4GB RAM in the CSE Lab.', 'annex')
        workload = source('workload', 1, 'Introductory machine learning task: train a classifier on a 1,000-row dataset.', 'manual')
        distractors = [source(f'topic-{n}', n, 'Computing cloud access AI workload course. ' * 45)
                       for n in range(1, 12)]
        sources = [hardware, workload, *distractors]
        selected = select_context(item, sources, max_chars=4000)
        self.assertLessEqual(sum(len(s['text']) for s in selected), 4000)
        self.assertEqual([s['id'] for s in selected[:2]], ['hardware', 'workload'])
        for row in selected[:2]:
            self.assertEqual(row['text_offset'], 0)
            self.assertEqual(row['text'], next(s['text'] for s in sources if s['id'] == row['id']))
        partial = select_context(item, [hardware, *distractors], max_chars=4000)
        self.assertEqual(partial[0]['id'], 'hardware')
