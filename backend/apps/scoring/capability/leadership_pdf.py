"""Compact leadership PDF from the same read-only report projection as HTML."""
import textwrap

from .pdf_report import Report


class LeadershipReport(Report):
    def header(self):
        self.set_fill_color(7, 111, 115)
        self.rect(0, 0, self.w, 4, style='F')

    def paragraph(self, value, *, heading=False, small=False):
        return super().paragraph(value, heading=heading, small=small, align='L')

    def display(self, value, size=22):
        self.set_font('Evidence', 'B', size)
        self.set_text_color(7, 100, 106)
        cmap = self.current_font.cmap
        text = ''.join(c if c in '\n\t' or ord(c) in cmap else
                       (f'\\u{ord(c):04x}' if ord(c) <= 65535 else f'\\U{ord(c):08x}') for c in str(value))
        self.multi_cell(0, size * 0.48, text, align='L', new_x='LMARGIN', new_y='NEXT')
        self.ln(3)

    def footer(self):
        self.set_y(-12)
        self.set_draw_color(210, 225, 227)
        self.line(18, self.get_y() - 2, self.w - 18, self.get_y() - 2)
        self.set_font('Evidence', '', 7)
        self.set_text_color(90, 100, 110)
        self.cell(0, 5, f'Institutional AI assessment | Page {self.page_no()} of {{nb}}', align='C')


def brief(value, width=220):
    return textwrap.shorten(str(value), width=width, placeholder=' ... [full text in supporting evidence]')


def render_leadership_pdf(view):
    pdf = LeadershipReport('leadership')
    pdf.set_title('Institutional AI assessment - leadership report')
    pdf.paragraph('INSTITUTIONAL AI ASSESSMENT', heading=True)
    pdf.display(view['institution'])
    pdf.paragraph(f"People covered: {view['population']}")
    pdf.paragraph(f"Reporting period: {view['period']}")
    pdf.section(view['assessment_state'])
    pdf.paragraph(view['advisory']['label'], heading=True)
    pdf.paragraph(view['advisory']['explanation'])
    for notice in view.get('scope_notices', []):
        pdf.paragraph('Scope needs review' if notice['severity'] == 'review' else 'Scope and interpretation', heading=True)
        pdf.paragraph(notice['message'])
    if pdf.will_page_break(55):
        pdf.add_page()
    pdf.section('Overall capability result')
    panel_y = pdf.get_y()
    pdf.set_fill_color(235, 245, 245)
    pdf.rect(16, panel_y, pdf.w - 32, 36, style='F')
    pdf.set_y(panel_y + 3)
    pdf.display(view['score'], 24)
    pdf.paragraph(view['score_explanation'])
    pdf.set_y(max(pdf.get_y(), panel_y + 39))
    pdf.paragraph(view['evidence_summary'])
    pdf.paragraph(view['methodology_notice'])
    foundation = view.get('foundation_plan')
    if foundation:
        pdf.section('Proposed foundation pathway')
        pdf.paragraph(foundation['destination'] + '. Current achievement level is not verified; no badge is awarded.')
        for route in foundation['routes']:
            pdf.paragraph(route['name'] + ': ' + route['indicative_duration'] + ' (illustrative). ' + ' '.join(route['assumptions']))
    pdf.section('Where to begin')
    for i, item in enumerate(view['priorities'], 1):
        pdf.paragraph(f"{i}. {item['title']}")
    if not view['priorities']:
        pdf.paragraph('Maintain the demonstrated capability and retain supporting evidence.')
    pdf.paragraph(view['priority_note'], small=True)

    pdf.add_page()
    pdf.section('Results across nine readiness areas')
    for pillar in view['pillars']:
        pdf.paragraph(pillar['title'], heading=True)
        pdf.paragraph(pillar['score'])
        candidates = [a for a in view['priorities'] if any(c['key'] == a['area_key'] for c in pillar['areas'])]
        if candidates:
            pdf.paragraph('Start with: ' + candidates[0]['title'])
        else:
            # Use the pillar's actual next step even when it is outside the first five.
            pdf.paragraph(brief(pillar['next_step'], 190))

    pdf.add_page()
    pdf.section('First actions to consider')
    pdf.paragraph(f"{len(view['priorities'])} starting points are shown from {view['followup_count']} areas with follow-ups.")
    pdf.paragraph('These summaries show selected instructions. The printable HTML and supporting-evidence exports retain the full stored steps and evidence.')
    for i, item in enumerate(view['priorities'], 1):
        if pdf.get_y() > 180:
            pdf.add_page()
        pdf.section(f"{i}. {item['title']}")
        pdf.paragraph(item['guidance'], small=True)
        pdf.paragraph(item['reason'])
        for number, step in enumerate(item['steps'][:2], 1):
            pdf.paragraph(f'{number}. {brief(step)}')
        pdf.paragraph('Suggested responsible role: ' + item['suggested_role'])
        pdf.paragraph('Effort: ' + item['effort'])
        pdf.paragraph('Completion evidence: ' + brief(item['completion']))
        if item['dependencies']:
            pdf.paragraph('Dependencies: ' + brief('; '.join(item['dependencies'])))
    if not view['priorities']:
        pdf.paragraph('No additional follow-up is identified from the stored requirements.')

    for index, pillar in enumerate(view['pillars']):
        if index % 3 == 0:
            pdf.add_page()
            pdf.section('Subarea findings and next steps')
        pdf.section(pillar['title'])
        for area in pillar['areas']:
            pdf.set_font('Evidence', 'B', 9)
            pdf.set_text_color(30, 55, 65)
            pdf.multi_cell(0, 4.5, area['title'], new_x='LMARGIN', new_y='NEXT')
            pdf.paragraph(area['score'] + '. ' + area['finding'])
            # Stage status remains explicit without turning unknown into a negative.
            stage = next((s for s in area['stages'] if s['status'] != 'Demonstrated'), None)
            pdf.paragraph((f"Next check: {stage['title'].lower()} - {stage['status'].lower()}. "
                           'Full next step: supporting report.') if stage else
                          'Next step: maintain provision and review updated evidence.', small=True)

    pdf.add_page()
    pdf.section('Scope, evidence and interpretation')
    for limitation in view['limitations']:
        pdf.paragraph(limitation)
    pdf.section('How to use the supporting detail')
    pdf.paragraph('The printable HTML provides readable subarea findings and full selected action instructions. The supporting-evidence export contains all original requirement decisions, source references, conditional calculations and remaining actions.')
    pdf.paragraph('Source detail and the leadership report use the same saved assessment and selected recommendation version. No model is called when exporting either report.')
    pdf.paragraph('Method used: ' + view['methodology'])
    pdf.paragraph(view['methodology_notice'])
    return bytes(pdf.output())
