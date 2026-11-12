"""Conservative evidence-part seeds for the first production slice."""
import hashlib
import re

from .syllabus_structure import COHORT, course_companions

APPROVAL_ID = 'AIQIF-C3.1.F1'
APPROVAL_MISSING = 'Evidence does not establish formal approval of the applicable syllabus edition.'
APPROVAL = re.compile(
    r'\b(?:syllabus|curriculum)\b[^.!?;]{0,110}\b(?:was|were|has been) approved by\b'
    r'[^.!?;]{0,30}\b(?:academic council|board of management|board of studies)\b'
    r'|\b(?:academic council|board of management|board of studies)\b'
    r'\s+approved\b[^.!?;]{0,90}\b(?:syllabus|curriculum)\b', re.I,
)
EDITION_YEAR = re.compile(r'\b(?:regulations?|edition|academic year)\s+(20\d{2})\b', re.I)
SPEC = re.compile(r'\b(?:core\s+i[3579]|ryzen\s+\d|(?:\d+\s*(?:gb|tb)\s+(?:ram|ssd|hdd))|'
                  r'(?:ram|vram|storage)\s*[:=]?\s*\d+\s*(?:gb|tb))\b', re.I)
ASSET = re.compile(r'\b(?:installed|inventory|workstations?|desktops?|laptops?|servers?|lab(?:oratory)?)\b', re.I)
LABELLED_ROW = re.compile(r'(?im)^Year:\s*20\d{2}[^\r\n]*\|\s*Remarks:')
WORKLOAD_TOPIC = re.compile(r'\b(?:AI|artificial intelligence|machine learning|deep learning|neural networks)\b', re.I)
WORKLOAD = re.compile(r'\b(?:train(?:ing)?|fine[- ]tun(?:e|ing)|run(?:ning)?|execut(?:e|ing)|inference)\b'
                      r'[^.!?;]{0,100}\b(?:model|classifier|regression|neural network|dataset)\b', re.I)

# The predicates identify candidate record forms. They do not establish suitability,
# ownership, currency or that two records refer to the same resources.
PARTS = {
    'AIQIF-C3.1': {'recorded_approval': (APPROVAL,)},
    'AIQIF-C6.1': {'hardware_specification': (SPEC, ASSET), 'stated_workload': (WORKLOAD_TOPIC, WORKLOAD)},
}


def candidate_rows(code, windows):
    """Yield one ranked exact window per available part, with no shared topic bonus."""
    for part, patterns in PARTS.get(code, {}).items():
        best, best_key = None, None
        for row in windows:
            source, offset, text, _ = row
            hits = [len(pattern.findall(text)) for pattern in patterns]
            if not all(hits):
                continue
            # A count is capped so a long repeated table cannot swamp an exact hit.
            # Labelled rows give specifications, asset descriptions and dates a common
            # record boundary. Unlabelled records still compete if they match.
            structured = part == 'hardware_specification' and any(
                LABELLED_ROW.match(line) and SPEC.search(line) and ASSET.search(line)
                for line in text.splitlines()
            )
            key = (-structured, -sum(min(3, count) for count in hits), hashlib.sha256(text.encode()).digest(), offset, source['id'])
            if best_key is None or key < best_key:
                best, best_key = row, key
        if best is not None:
            yield best


def supports_approval(citations, edition_sources):
    """Require a recorded approval and cited course tied to the same explicit edition."""
    approvals = []
    for citation in citations:
        for clause in re.split(r'[;!?]|\.(?=\s|$)', citation['quote']):
            years = set(EDITION_YEAR.findall(clause))
            if len(years) == 1 and APPROVAL.search(clause) and not re.search(
                r'\b(?:if|unless|may|would|could|whether|proposed|pending|not|never)\b', clause, re.I
            ):
                approvals.append((citation['source_id'], next(iter(years))))
    if not approvals:
        return False
    links = course_companions(edition_sources)
    for citation in citations:
        course_id = citation['source_id']
        if not WORKLOAD_TOPIC.search(citation['quote']) or APPROVAL.search(citation['quote']) or course_id not in links:
            continue
        declaration, _, quote, _ = links[course_id]
        year = COHORT.fullmatch(quote)[1]
        for approval_id, approved_year in approvals:
            if approved_year != year:
                continue
            # Match edition source identity, not just the same year across PDFs.
            approval_edition = links.get(approval_id)
            if approval_id == declaration['id'] or (approval_edition and approval_edition[0]['id'] == declaration['id']):
                return True
    return False
