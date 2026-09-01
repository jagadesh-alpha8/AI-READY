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


#: Mirrors frontend/src/pages/documents/UploadDataPack.tsx's REQUIRED_CHECKLIST
#: (slug, label, owner) EXACTLY -- these slugs are intentionally different
#: from DOCUMENT_TYPES/REQUIRED_DOCUMENT_TYPES above (e.g. 'aqar_report' vs
#: 'aqar'); that divergence already exists between this backend and the
#: frontend checklist and is out of scope to fix here. Keep this list in sync
#: with UploadDataPack.tsx BY HAND if that checklist ever changes -- there is
#: no shared source of truth between the two today.
#: `keywords`: lowercase substrings checked against a Drive filename
#: (case-insensitive) by apps.documents.drive_import.classify_filename().
DRIVE_IMPORT_CHECKLIST = [
    {'type': 'naac_ssr', 'label': 'NAAC SSR / Latest Self-Study Report', 'owner': 'IQAC_COORDINATOR',
     'keywords': ['ssr', 'self study', 'self-study', 'naac']},
    {'type': 'aqar_report', 'label': 'AQAR / Annual Quality Assurance Report', 'owner': 'IQAC_COORDINATOR',
     'keywords': ['aqar', 'annual quality']},
    {'type': 'aicte_approval', 'label': 'AICTE Approval / University Affiliation', 'owner': 'REGISTRAR',
     'keywords': ['aicte', 'affiliation', 'approval']},
    {'type': 'faculty_master', 'label': 'Faculty Master List & Qualifications', 'owner': 'HR_OFFICER',
     'keywords': ['faculty', 'qualification']},
    {'type': 'student_strength', 'label': 'Student Enrolment & Strength Report', 'owner': 'REGISTRAR',
     'keywords': ['enrolment', 'enrollment', 'student strength', 'admission']},
    {'type': 'placement_report', 'label': 'Placement & Industry Internship Report', 'owner': 'PLACEMENT_OFFICER',
     'keywords': ['placement', 'internship']},
    {'type': 'syllabi_curriculum', 'label': 'Syllabi & BOS Curriculum Minutes', 'owner': 'HOD',
     'keywords': ['syllabus', 'syllabi', 'curriculum', 'bos']},
    {'type': 'lab_inventory', 'label': 'Lab Infrastructure & Software Inventory', 'owner': 'LAB_ADMIN',
     'keywords': ['lab inventory', 'laboratory', 'equipment']},
    {'type': 'research_publications', 'label': 'Research Publications & Patents Log', 'owner': 'RESEARCH_CELL',
     'keywords': ['research', 'publication', 'patent']},
    {'type': 'ai_policy_doc', 'label': 'Institutional AI Strategy & Policy', 'owner': 'INSTITUTION_ADMIN',
     'keywords': ['ai policy', 'ai strategy']},
]
