"""Renders a Report's `report_data` into downloadable PDF/DOCX bytes.

The PDF is the visual layout in pdf_report.py. fpdf2's built-in core fonts (Helvetica) only support Latin-1 --
rather than bundling a Unicode TrueType font (not portable across dev/CI/production), dynamic text there is
passed through a Latin-1 filter: any other character becomes '?' rather than crashing the render. python-docx
has no such restriction (docx/XML is UTF-8), so DOCX rendering uses the real text as-is.
"""
import io

from docx import Document as DocxDocument


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
    data = report.report_data
    doc = DocxDocument()

    doc.add_heading(f"AIOS Discovery Report — {data['institution']['name']}", level=0)
    meta = doc.add_paragraph()
    meta.add_run(
        f"Sprint {data['sprint']['sprint_code']} · Version {report.version} · Generated {data['generated_at']}",
    ).italic = True
    baseline_run = doc.add_paragraph().add_run(f"Baseline status: {data['baseline']['status'].upper()}")
    baseline_run.bold = True
    for text in _processing_lines(data):
        doc.add_paragraph().add_run(text).bold = True
    source = data.get('cri_source') or {}
    if source.get('note'):
        note = doc.add_paragraph().add_run(
            ('RECALCULATED CRI: ' if source.get('differs_from_baseline') else '') + source['note'])
        note.bold = bool(source.get('differs_from_baseline'))

    doc.add_heading('1. Executive Summary', level=1)
    doc.add_paragraph(data['executive_summary'])

    doc.add_heading('2. Overall CRI & Confidence', level=1)
    doc.add_paragraph(f"Raw CRI: {data['overall_cri']:.1f} / 100")
    for text in _coverage_lines(data):
        doc.add_paragraph(text)
    doc.add_paragraph(f"Confidence: {data['confidence_score']:.0%}")

    doc.add_heading('3. Eight Pillar Scorecards', level=1)
    table = doc.add_table(rows=1, cols=5)
    table.style = 'Light Grid Accent 1'
    for cell, label in zip(table.rows[0].cells, ['Pillar', 'Score', 'Status', 'Confidence', 'Evidence']):
        cell.text = label
    for p in data['pillar_scorecards']:
        row = table.add_row().cells
        row[0].text = p['label']
        row[1].text = f"{p['raw_score']:.1f}/100"
        row[2].text = p['status']
        row[3].text = f"{p['confidence_score']:.0%}"
        row[4].text = str(p['evidence_count'])

    _docx_bullets(doc, '4. Strengths', [f"{s['label']} — {s['raw_score']:.1f}/100" for s in data['strengths']])
    _docx_bullets(
        doc, '5. Areas for Improvement',
        [f"{s['label']} — {s['raw_score']:.1f}/100 ({s['status']})" for s in data['areas_for_improvement']],
    )
    _docx_bullets(
        doc, '6. Missing Data Appendix',
        [f"[{g['priority']}] {g['pillar_label']}: {g['title']}" for g in data['missing_data_appendix']],
    )
    _docx_bullets(
        doc, '7. Recommendations',
        [
            f"[{r['priority']}] {r['title']} (+{r['expected_cri_lift']:.1f} CRI lift)"
            for r in data['recommendations']
        ],
    )

    doc.add_heading('8. 90-Day Action Plan', level=1)
    _docx_action_plan(doc, data['ninety_day_action_plan'])

    doc.add_heading('9. 12-Month Roadmap', level=1)
    _docx_action_plan(doc, data['twelve_month_roadmap'])

    _docx_bullets(
        doc, '10. How InGage Can Help',
        [f"{o['offering']} ({o['recommendation_count']} recommendation(s))" for o in data['how_ingage_can_help']],
    )

    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def _docx_bullets(doc, heading, lines):
    doc.add_heading(heading, level=1)
    if not lines:
        doc.add_paragraph('None.')
        return
    for line in lines:
        doc.add_paragraph(line, style='List Bullet')


def _docx_action_plan(doc, buckets):
    if not buckets:
        doc.add_paragraph('No items identified for this horizon.')
        return
    for bucket in buckets:
        doc.add_paragraph().add_run(bucket['timeline']).bold = True
        for item in bucket['items']:
            doc.add_paragraph(item['title'], style='List Bullet')
