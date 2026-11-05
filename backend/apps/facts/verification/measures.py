"""Conservative distinctions lost when several measures share a normalized field key.

Only explicit labels identify a count basis. Unknown or mixed labels stay unknown;
this is not a synonym classifier or proof that a source claim is correct.
"""
import re


def count_basis(label):
    text = ' '.join(re.findall(r'[a-z]+', (label or '').casefold()))
    candidates = set()
    if re.search(r'\b(mous?|memorandums?|memoranda|agreements?)\b', text):
        for pattern, basis in ((r'\bnational\b', 'national_agreements'),
                               (r'\binternational\b', 'international_agreements'),
                               (r'\bindustr(?:y|ial)\b', 'industry_agreements')):
            if re.search(pattern, text):
                candidates.add(basis)
    if re.search(r'\b(students?|candidates?|examinations?|exams?)\b', text):
        for pattern, basis in ((r'\b(passed|qualified)\b', 'exam_passes'),
                               (r'\b(appeared|sat)\b', 'exam_appearances'),
                               (r'\b(benefited|benefitted|beneficiaries)\b', 'beneficiaries'),
                               (r'\b(intake|admitted|admissions|entrants)\b', 'intake'),
                               (r'\bstudent strength\b|\b(?:total|number of) students\b', 'headcount')):
            if re.search(pattern, text):
                candidates.add(basis)
    return next(iter(candidates)) if len(candidates) == 1 else ''
