"""Renders a Report's `report_data` into downloadable PDF/DOCX bytes.

The PDF is the visual layout in pdf_report.py. fpdf2's built-in core fonts (Helvetica) only support Latin-1 --
rather than bundling a Unicode TrueType font (not portable across dev/CI/production), dynamic text there is
passed through a Latin-1 filter: any other character becomes '?' rather than crashing the render. python-docx
has no such restriction (docx/XML is UTF-8), so DOCX rendering uses the real text as-is.
"""
import io



def _processing_lines(data):
    """Incomplete document processing, said plainly (older reports have no "processing" key)."""
    processing = data.get('processing') or {}
    lines = []
    if processing and not processing.get('complete', True):
        lines.append(f"INCOMPLETE DOCUMENT PROCESSING: {processing.get('description', '')} Facts from those "
                     'documents may be missing from this report.')
    override = processing.get('baseline_override')
    if override:
        lines.append(f"The baseline was approved with incomplete processing ({override.get('description', '')}). "
                     f"Reason recorded: {override.get('reason', '')}")
    return lines


def _coverage_lines(data):
    """Coverage-adjusted CRI and AI-QIF evidence coverage, shown apart from the Raw CRI.
    Older reports (before coverage) have neither key and show nothing extra."""
    coverage = data.get('evidence_coverage')
    if not coverage:
        return []
    if not coverage.get('available'):
        return [coverage.get('summary', '')]
    adjusted = data.get('coverage_adjusted_cri')
    first = (f'Coverage-adjusted CRI: {adjusted:.1f} / 100 (Raw CRI x coverage, {coverage["formula_version"]})'
             if adjusted is not None else 'Coverage-adjusted CRI: not available (no applicable indicator weight)')
    return [first, f'AI-QIF evidence coverage: {coverage["summary"]}']


# ---------------------------------------------------------------- PDF -----

def render_pdf_bytes(report):
    """The visual PDF (apps/reports/pdf_report.py): tiles, charts and tables instead of paragraphs."""
    from .pdf_report import build_pdf
    return build_pdf(report)


# --------------------------------------------------------------- DOCX -----

def render_docx_bytes(report):
    """The Word report, laid out like the PDF (apps/reports/docx_report.py)."""
    from .docx_report import build_docx
    return build_docx(report)
