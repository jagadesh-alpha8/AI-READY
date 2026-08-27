"""Known AIOS document types and upload rules.

`document_type` on the Document model is a free-text, validated slug (see
`apps.documents.models.document_type_validator`), not a Django `choices=`
enum -- so a brand-new document type can be introduced by whoever is
uploading without a migration or code change. The registry below only
supplies human-readable labels for the types InGage's workflow already
knows about; `humanize_document_type` falls back to a readable guess for
anything else, so unrecognized-but-valid types still get sane
"frontend-friendly" metadata instead of an error.
"""

DOCUMENT_TYPES = [
    ('naac_ssr', 'NAAC Self-Study Report (SSR)'),
    ('aqar', 'AQAR / Annual Quality Assurance Report'),
    ('aicte_approval', 'AICTE Approval / University Affiliation'),
    ('faculty_master_list', 'Faculty Master List & Qualifications'),
    ('student_strength', 'Student Enrolment & Strength Report'),
    ('placement_report', 'Placement & Industry Internship Report'),
    ('research_publication_report', 'Research Publications & Patents Report'),
    ('lab_inventory', 'Lab Infrastructure & Software Inventory'),
    ('mou_industry_engagement', 'MoU & Industry Engagement List'),
    ('certification_summary', 'Certification Summary'),
    ('ai_faculty_certifications', 'AI Faculty Certification List'),
    ('ai_software_licenses', 'AI Software / Tools Licence List'),
]

DOCUMENT_TYPE_LABELS = dict(DOCUMENT_TYPES)

#: The subset of DOCUMENT_TYPES that must be present for a verified CRI
#: baseline -- matches the frontend's "Required Core" checklist category.
#: Used by apps.gaps.services to raise a `missing_document` gap for
#: whichever of these a sprint doesn't have yet.
REQUIRED_DOCUMENT_TYPES = frozenset({
    'naac_ssr', 'aqar', 'aicte_approval', 'faculty_master_list', 'student_strength', 'placement_report',
})

#: Extensions accepted by the upload endpoint. Matches the frontend's stated
#: "PDF, DOCX, XLSX, CSV, or ZIP" plus common variants (legacy Office
#: formats, images for scanned pages).
ALLOWED_UPLOAD_EXTENSIONS = {
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.csv', '.zip', '.png', '.jpg', '.jpeg',
}

#: Formats that aren't already machine-readable text/data and would need an
#: OCR pass in the (separate, not-yet-built) extraction pipeline.
OCR_REQUIRED_EXTENSIONS = {'.pdf', '.doc', '.docx', '.png', '.jpg', '.jpeg'}


def humanize_document_type(document_type):
    return DOCUMENT_TYPE_LABELS.get(document_type, document_type.replace('_', ' ').strip().title())
