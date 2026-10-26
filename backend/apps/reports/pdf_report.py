"""The downloadable PDF report, designed to be read at a glance: a branded header, headline score tiles, a pillar
bar chart, gap and recommendation tables with priority tags, a 30-60-90 day timeline and
the support InGage offers. Short labels instead of paragraphs; every value comes from the report's frozen
`report_data` (apps/reports/services.build_report_data) -- nothing is computed or invented here.

fpdf2's core fonts are Latin-1 only, so dynamic text goes through `_t` (see rendering.py).
"""
from datetime import datetime

from fpdf import FPDF
from fpdf.enums import MethodReturnValue

# The app's light theme (frontend/src/index.css), as RGB.
BRAND = (99, 130, 0)          # brand-700
BRAND_LIGHT = (240, 247, 220)  # brand-100
INK = (52, 51, 53)            # ink-900
MUTED = (110, 110, 115)
LINE = (225, 226, 222)
TRACK = (238, 239, 235)
WHITE = (255, 255, 255)
GREEN = (0, 130, 54)
AMBER = (166, 95, 0)
RED = (193, 0, 7)
AMBER_BG = (255, 244, 225)

STATUS = {  # pillar status -> (label, colour)
    'strong': ('Strong', GREEN),
    'developing': ('Developing', BRAND),
    'at_risk': ('At risk', AMBER),
    'not_started': ('Not started', RED),
}
PRIORITY = {  # recommendation / gap priority -> (label, colour)
    'blocking': ('BLOCKING', RED),
    'high': ('HIGH', AMBER),
    'medium': ('MEDIUM', BRAND),
    'optional': ('OPTIONAL', MUTED),
}

M = 14  # page margin (mm)


def _t(text):
    return str(text if text is not None else '').replace('—', '-').replace('–', '-') \
        .replace('’', "'").replace('‘', "'").replace('“', '"').replace('”', '"') \
        .encode('latin-1', 'replace').decode('latin-1')


def _date(value):
    if not value:
        return ''
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00')).strftime('%d %b %Y')
    except ValueError:
        return str(value)[:10]


class _Report(FPDF):
    def __init__(self, title):
        super().__init__(format='A4')
        self.title_text = title
        self.set_margins(M, M, M)
        self.set_auto_page_break(auto=True, margin=16)
        self.alias_nb_pages()

    @property
    def width(self):
        return self.w - 2 * M

    def footer(self):
        self.set_y(-11)
        self.set_draw_color(*LINE)
        self.line(M, self.get_y() - 1, self.w - M, self.get_y() - 1)
        self.set_font('Helvetica', '', 7.5)
        self.set_text_color(*MUTED)
        self.cell(self.width / 2, 5, _t(f'InGage AIOS  |  {self.title_text}'))
        self.cell(self.width / 2, 5, f'Page {self.page_no()} of {{nb}}', align='R')

    # -- building blocks ------------------------------------------------------------------

    def need(self, height):
        """Start a new page when the next block would not fit."""
        if self.get_y() + height > self.h - 18:
            self.add_page()

    def section(self, title, subtitle=''):
        self.need(22)
        self.ln(3)
        self.set_fill_color(*BRAND)
        self.rect(M, self.get_y() + 1, 1.6, 5.2, style='F')
        self.set_x(M + 4)
        self.set_font('Helvetica', 'B', 12.5)
        self.set_text_color(*INK)
        self.cell(0, 7, _t(title), new_x='LMARGIN', new_y='NEXT')
        if subtitle:
            self.set_font('Helvetica', '', 8)
            self.set_text_color(*MUTED)
            self.set_x(M + 4)
            self.cell(0, 4, _t(subtitle), new_x='LMARGIN', new_y='NEXT')
        self.ln(2)

    def pill(self, x, y, text, colour, filled=True, size=7):
        self.set_font('Helvetica', 'B', size)
        w = self.get_string_width(text) + 4
        if filled:
            self.set_fill_color(*colour)
            self.set_text_color(*WHITE)
            self.rect(x, y, w, 4.6, style='F', round_corners=True, corner_radius=1.6)
        else:
            self.set_draw_color(*colour)
            self.set_text_color(*colour)
            self.rect(x, y, w, 4.6, style='D', round_corners=True, corner_radius=1.6)
        self.set_xy(x, y)
        self.cell(w, 4.6, _t(text), align='C')
        return w

    def lines_for(self, w, text, size, style=''):
        self.set_font('Helvetica', style, size)
        return len(self.multi_cell(w, 4, _t(text), align='L', dry_run=True, output=MethodReturnValue.LINES)) or 1


# ---------------------------------------------------------------------------------------- sections

def _header(pdf, data, report):
    inst = data['institution'].get('name', '')
    sprint = data['sprint']
    pdf.set_fill_color(*BRAND)
    pdf.rect(0, 0, pdf.w, 38, style='F')
    pdf.set_xy(M, 9)
    pdf.set_font('Helvetica', 'B', 8.5)
    pdf.set_text_color(*BRAND_LIGHT)
    pdf.cell(0, 4, 'AI READINESS DISCOVERY REPORT', new_x='LMARGIN', new_y='NEXT')
    pdf.set_font('Helvetica', 'B', 22)
    pdf.set_text_color(*WHITE)
    pdf.cell(pdf.width - 50, 11, _t(inst), new_x='LMARGIN', new_y='NEXT')
    pdf.set_font('Helvetica', '', 9)
    pdf.set_text_color(*BRAND_LIGHT)
    pdf.cell(0, 5, _t(f"Sprint {sprint.get('sprint_code', '')}   |   Version {report.version}   |   "
                      f"{_date(data.get('generated_at'))}"))
    baseline = (data.get('baseline') or {}).get('status') or 'not submitted'
    label = f'BASELINE: {str(baseline).upper()}'
    pdf.set_font('Helvetica', 'B', 8)
    w = pdf.get_string_width(label) + 8
    pdf.set_fill_color(*WHITE)
    pdf.rect(pdf.w - M - w, 14, w, 7, style='F', round_corners=True, corner_radius=2)
    pdf.set_xy(pdf.w - M - w, 14)
    pdf.set_text_color(*BRAND)
    pdf.cell(w, 7, _t(label), align='C')
    pdf.set_y(44)


def _notices(pdf, data):
    """Only what changes how the numbers should be read, in one short line each."""
    out = []
    source = data.get('cri_source') or {}
    if source.get('differs_from_baseline'):
        out.append(f"This report's Live CRI is {data.get('overall_cri', 0):.1f}; the {source.get('baseline_status')} "
                   f"baseline stays {source.get('baseline_cri') or 0:.1f} (see below).")
    processing = data.get('processing') or {}
    if processing and not processing.get('complete', True):
        out.append('Document processing incomplete: some facts may be missing.')
    if processing.get('baseline_override'):
        out.append('Baseline approved with incomplete processing (reason on record).')
    for text in out:
        pdf.set_fill_color(*AMBER_BG)
        pdf.set_text_color(*AMBER)
        pdf.set_font('Helvetica', 'B', 8)
        pdf.cell(pdf.width, 6, _t(f'  !  {text}'), fill=True, new_x='LMARGIN', new_y='NEXT')
        pdf.ln(1)
    if out:
        pdf.ln(2)


def _baseline_strip(pdf, data):
    """The decided baseline snapshot this report is compared with, next to the report's own Live CRI."""
    source = data.get('cri_source') or {}
    if not source.get('baseline_scoring_run_id'):
        return
    conf = source.get('baseline_confidence')
    parts = [f"Approved baseline ({source.get('baseline_status')}): CRI {source.get('baseline_cri') or 0:.1f}",
             f'confidence {conf * 100:.0f}%' if conf is not None else '',
             f"calculated {_date(source.get('baseline_calculated_at'))}",
             f"run {str(source.get('baseline_scoring_run_id'))[:8]}",
             f"Live CRI in this report: {data.get('overall_cri', 0):.1f}"]
    pdf.set_fill_color(*BRAND_LIGHT)
    pdf.set_text_color(*BRAND)
    pdf.set_font('Helvetica', 'B', 8)
    pdf.cell(pdf.width, 6.5, _t('  ' + '   |   '.join(p for p in parts if p)), fill=True,
             new_x='LMARGIN', new_y='NEXT')
    pdf.ln(2)


def _tiles(pdf, data):
    metrics = data.get('evidence_metrics') or {}
    adjusted = data.get('coverage_adjusted_cri')
    tiles = [
        ('LIVE CRI', f"{data.get('overall_cri', 0):.1f}", '/ 100', (data.get('overall_cri') or 0) / 100),
        ('COVERAGE-ADJUSTED', '-' if adjusted is None else f'{adjusted:.1f}', '/ 100',
         0 if adjusted is None else adjusted / 100),
        ('EVIDENCE CONFIDENCE', f"{(data.get('confidence_score') or 0) * 100:.0f}%", '', data.get('confidence_score') or 0),
        ('OPEN DATA GAPS', str(len(data.get('missing_data_appendix') or [])), '', None),
    ]
    gap, y = 4, pdf.get_y()
    w = (pdf.width - gap * 3) / 4
    for i, (label, value, unit, ratio) in enumerate(tiles):
        x = M + i * (w + gap)
        pdf.set_fill_color(*WHITE)
        pdf.set_draw_color(*LINE)
        pdf.rect(x, y, w, 27, style='DF', round_corners=True, corner_radius=2.5)
        pdf.set_xy(x + 4, y + 3.5)
        pdf.set_font('Helvetica', 'B', 6.8)
        pdf.set_text_color(*MUTED)
        pdf.cell(w - 8, 4, label)
        pdf.set_xy(x + 4, y + 8.5)
        pdf.set_font('Helvetica', 'B', 20)
        pdf.set_text_color(*(RED if label == 'OPEN DATA GAPS' and value != '0' else INK))
        pdf.cell(pdf.get_string_width(value) + 1, 10, _t(value))
        pdf.set_font('Helvetica', '', 8)
        pdf.set_text_color(*MUTED)
        pdf.cell(10, 11, unit)
        if ratio is not None:
            pdf.set_fill_color(*TRACK)
            pdf.rect(x + 4, y + 21, w - 8, 2.2, style='F', round_corners=True, corner_radius=1.1)
            filled = max(0.0, min(1.0, ratio)) * (w - 8)
            if filled > 0.5:
                pdf.set_fill_color(*BRAND)
                pdf.rect(x + 4, y + 21, filled, 2.2, style='F', round_corners=True, corner_radius=1.1)
        else:
            pdf.set_xy(x + 4, y + 20)
            pdf.set_font('Helvetica', '', 7)
            pdf.cell(w - 8, 4, f"{metrics.get('documents_processed', 0)} documents processed")
    pdf.set_y(y + 31)
    strong = len(data.get('strengths') or [])
    total = len(data.get('pillar_scorecards') or [])
    facts = (metrics.get('confirmed_facts') or 0) + (metrics.get('corrected_facts') or 0)
    pdf.set_font('Helvetica', '', 8.5)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 5, _t(f'{strong} of {total} pillars strong   |   {facts} confirmed facts   |   '
                      f"{len(data.get('recommendations') or [])} recommendations"),
             new_x='LMARGIN', new_y='NEXT')


def _pillar_chart(pdf, data):
    pillars = data.get('pillar_scorecards') or []
    pdf.section('Pillar scores', 'Score out of 100 per AI readiness pillar')
    if not pillars:
        _empty(pdf, 'No pillar scores yet.')
        return
    label_w, score_w, status_w = 82, 12, 22
    bar_w = pdf.width - label_w - score_w - status_w - 4
    for p in pillars:
        pdf.need(8)
        y = pdf.get_y()
        name, colour = STATUS.get(p.get('status'), (str(p.get('status') or ''), MUTED))
        score = p.get('raw_score') or 0
        pdf.set_xy(M, y)
        pdf.set_font('Helvetica', '', 8.5)
        pdf.set_text_color(*INK)
        text = _t(p.get('label') or p.get('pillar'))
        while pdf.get_string_width(text) > label_w - 2 and len(text) > 4:
            text = text[:-4] + '...'
        pdf.cell(label_w, 6, text)
        bx = M + label_w
        pdf.set_fill_color(*TRACK)
        pdf.rect(bx, y + 1.4, bar_w, 3.4, style='F', round_corners=True, corner_radius=1.7)
        if score > 0:
            pdf.set_fill_color(*colour)
            pdf.rect(bx, y + 1.4, max(2.0, bar_w * min(score, 100) / 100), 3.4, style='F',
                     round_corners=True, corner_radius=1.7)
        pdf.set_xy(bx + bar_w + 1, y)
        pdf.set_font('Helvetica', 'B', 9)
        pdf.cell(score_w, 6, f'{score:.0f}', align='R')
        pdf.set_xy(bx + bar_w + score_w + 4, y + 0.7)
        pdf.set_font('Helvetica', 'B', 7)
        pdf.set_text_color(*colour)
        pdf.cell(status_w, 4.6, name)
        pdf.set_y(y + 7)


def _table(pdf, title, subtitle, headers, widths, rows):
    """rows: [(priority, [cell texts])] -- the first column is the priority tag."""
    pdf.section(title, subtitle)
    if not rows:
        _empty(pdf, 'None.')
        return

    def head():
        pdf.set_fill_color(*BRAND_LIGHT)
        pdf.set_text_color(*BRAND)
        pdf.set_font('Helvetica', 'B', 7.5)
        for h, w in zip(headers, widths):
            pdf.cell(w, 6.5, f'  {h}', fill=True)
        pdf.ln(6.5)

    head()
    for n, (priority, cells) in enumerate(rows):
        height = max(pdf.lines_for(w - 3, c, 8.2) for c, w in zip(cells, widths[1:])) * 4 + 3
        if pdf.get_y() + height > pdf.h - 18:
            pdf.add_page()
            head()
        y = pdf.get_y()
        if n % 2:
            pdf.set_fill_color(250, 250, 248)
            pdf.rect(M, y, sum(widths), height, style='F')
        label, colour = PRIORITY.get(priority, (str(priority or '').upper(), MUTED))
        pdf.pill(M + 1.5, y + (height - 4.6) / 2, label, colour, size=6.3)
        x = M + widths[0]
        for c, w in zip(cells, widths[1:]):
            pdf.set_xy(x + 1.5, y + 1.5)
            pdf.set_font('Helvetica', '', 8.2)
            pdf.set_text_color(*INK)
            pdf.multi_cell(w - 3, 4, _t(c), align='L')
            x += w
        pdf.set_draw_color(*LINE)
        pdf.line(M, y + height, M + sum(widths), y + height)
        pdf.set_y(y + height)


def _timeline(pdf, data):
    buckets = list(data.get('ninety_day_action_plan') or []) + list(data.get('twelve_month_roadmap') or [])
    pdf.section('Action timeline', 'What to do first, from the recommendations above')
    if not buckets:
        _empty(pdf, 'No actions scheduled yet.')
        return
    cols = buckets[:4]
    gap = 4
    w = (pdf.width - gap * (len(cols) - 1)) / len(cols)
    heights = [8 + sum(pdf.lines_for(w - 7, i['title'], 7.8) * 3.8 + 2 for i in b['items']) for b in cols]
    pdf.need(min(max(heights) + 4, 200))
    y0 = pdf.get_y()
    for k, b in enumerate(cols):
        x = M + k * (w + gap)
        pdf.set_fill_color(*BRAND)
        pdf.rect(x, y0, w, 7, style='F', round_corners=True, corner_radius=1.8)
        pdf.set_xy(x, y0)
        pdf.set_font('Helvetica', 'B', 8.5)
        pdf.set_text_color(*WHITE)
        pdf.cell(w, 7, _t(b.get('timeline') or 'Unscheduled'), align='C')
        y = y0 + 9
        for item in b['items']:
            label, colour = PRIORITY.get(item.get('priority'), ('', MUTED))
            h = pdf.lines_for(w - 7, item['title'], 7.8) * 3.8 + 1
            pdf.set_fill_color(*colour)
            pdf.rect(x, y + 0.6, 1.4, h - 1, style='F')
            pdf.set_xy(x + 3.5, y)
            pdf.set_font('Helvetica', '', 7.8)
            pdf.set_text_color(*INK)
            pdf.multi_cell(w - 7, 3.8, _t(item['title']), align='L')
            y += h + 1
    pdf.set_y(y0 + max(heights) + 2)


def _support(pdf, data):
    offers = data.get('how_ingage_can_help') or []
    pdf.section('How InGage can help')
    if not offers:
        _empty(pdf, 'No support offerings linked yet.')
        return
    gap, per_row = 4, 3
    w = (pdf.width - gap * (per_row - 1)) / per_row
    for i, o in enumerate(offers):
        if i % per_row == 0:
            pdf.need(20)
            y = pdf.get_y()
        x = M + (i % per_row) * (w + gap)
        pdf.set_fill_color(*BRAND_LIGHT)
        pdf.rect(x, y, w, 16, style='F', round_corners=True, corner_radius=2.5)
        pdf.set_xy(x + 3, y + 2.5)
        pdf.set_font('Helvetica', 'B', 8.5)
        pdf.set_text_color(*INK)
        pdf.multi_cell(w - 6, 4, _t(o.get('offering')), align='L')
        pdf.set_xy(x + 3, y + 11)
        pdf.set_font('Helvetica', '', 7.5)
        pdf.set_text_color(*BRAND)
        pdf.cell(w - 6, 4, f"{o.get('recommendation_count', 0)} recommendation(s)")
        if i % per_row == per_row - 1 or i == len(offers) - 1:
            pdf.set_y(y + 20)


def _empty(pdf, text):
    pdf.set_font('Helvetica', '', 8.5)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 6, _t(text), new_x='LMARGIN', new_y='NEXT')


def _coverage_note(pdf, data):
    coverage = data.get('evidence_coverage') or {}
    if not coverage:
        return
    pdf.ln(2)
    pdf.set_font('Helvetica', '', 7)
    pdf.set_text_color(*MUTED)
    pdf.multi_cell(0, 3.6, align='L', text=_t(f"Coverage-adjusted CRI = CRI x AI-QIF evidence coverage. {coverage.get('summary', '')}"))


# ---------------------------------------------------------------------------------------- entry point

def build_pdf(report):
    data = report.report_data
    pdf = _Report(f"{data['institution'].get('name', '')} - AI Readiness Discovery Report")
    pdf.add_page()
    _header(pdf, data, report)
    _notices(pdf, data)
    _baseline_strip(pdf, data)
    _tiles(pdf, data)
    _pillar_chart(pdf, data)

    gaps = data.get('missing_data_appendix') or []
    if any(g.get('pillar_label') for g in gaps):
        _table(pdf, 'Priority data gaps', 'Documents or data still needed', ['PRIORITY', 'GAP', 'PILLAR'],
               [24, pdf.width - 24 - 62, 62],
               [(g.get('priority'), [g.get('title'), g.get('pillar_label') or '-']) for g in gaps])
    else:  # gaps not tied to a pillar (missing documents): no empty column
        _table(pdf, 'Priority data gaps', 'Documents or data still needed', ['PRIORITY', 'GAP'],
               [24, pdf.width - 24], [(g.get('priority'), [g.get('title')]) for g in gaps])

    recs = sorted(data.get('recommendations') or [], key=lambda r: -(r.get('expected_cri_lift') or 0))
    _table(pdf, 'Recommendations', 'Sorted by expected CRI lift', ['PRIORITY', 'ACTION', 'CRI LIFT', 'TIMELINE'],
           [24, pdf.width - 24 - 20 - 28, 20, 28],
           [(r.get('priority'), [r.get('title'), f"+{r.get('expected_cri_lift') or 0:.1f}", r.get('timeline') or '-'])
            for r in recs])

    _timeline(pdf, data)
    _support(pdf, data)
    _coverage_note(pdf, data)
    return bytes(pdf.output())
