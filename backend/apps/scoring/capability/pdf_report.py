"""Portable PDF of the same authorized frozen payload used by HTML/JSON exports.

No network, inference, active HTML or external resources. Bundle licensed fonts so
production does not depend on host fonts. Unsupported glyphs are escaped, not lost.
"""
from pathlib import Path
from fractions import Fraction

from fpdf import FPDF

LABELS = {'met': 'Demonstrated', 'not_met': 'Documented shortfall',
          'unknown': 'Evidence needed', 'conflicting': 'Contradictory evidence'}


class Report(FPDF):
    def __init__(self, run_id):
        super().__init__(format='A4')
        self.run_id = run_id
        self.set_margins(18, 16, 18)
        self.set_auto_page_break(True, 17)
        fonts = Path(__file__).with_name('fonts')
        self.add_font('Evidence', '', str(fonts / 'DejaVuSans.ttf'))
        self.add_font('Evidence', 'B', str(fonts / 'DejaVuSans-Bold.ttf'))
        self.alias_nb_pages()
        self.set_title('Pinned institutional AI capability assessment')
        self.set_author('InGage')
        self.add_page()

    def footer(self):
        self.set_y(-12)
        self.set_font('Evidence', '', 7)
        self.set_text_color(90, 100, 110)
        self.cell(0, 5, f'Assessment {self.run_id} | Page {self.page_no()} of {{nb}}', align='C')

    def paragraph(self, value, *, heading=False, small=False):
        self.set_font('Evidence', 'B' if heading else '', 12 if heading else 8 if small else 9)
        self.set_text_color(30, 55, 65)
        if heading and self.get_y() > 255:
            self.add_page()
        cmap = self.current_font.cmap
        value = str(value if value is not None else '')
        # Preserve unsupported text explicitly. Never silently substitute '?' in evidence.
        value = ''.join(c if c in '\n\t' or ord(c) in cmap else
                        (f'\\u{ord(c):04x}' if ord(c) <= 65535 else f'\\U{ord(c):08x}') for c in value)
        self.multi_cell(0, 6 if heading else 4.5, value, new_x='LMARGIN', new_y='NEXT')
        self.ln(2 if heading else 1)

    def section(self, title):
        self.ln(3)
        self.paragraph(title, heading=True)


def render_pdf(report, indicators, actions):
    pdf = Report(report['run_id'])
    result = report['assessment']['result']
    source_labels = {str(p['page_id']): f"{d['filename']} v{d['version']}, page {p.get('number', '?')}"
                     for d in report['source_manifest'] for p in d.get('pages', [])}
    pdf.paragraph('INSTITUTIONAL AI CAPABILITY', heading=True)
    pdf.paragraph(report['profile']['name'], heading=True)
    pdf.paragraph(f"Population: {report['population']} | Period: {report['reference_period']}")
    pdf.paragraph(f"Methodology: {result['methodology']}")
    pdf.paragraph(report['notice'])
    pdf.section('Current standing')
    score = (f"{result['exact_score']:.2f}" if result['exact_score'] is not None else
             f"{result['lower']:.2f} - {result['upper']:.2f}")
    pdf.paragraph(f'{score} / 100', heading=True)
    if result['exact_score'] is None:
        pdf.paragraph('The lower bound is demonstrated capability. The upper bound is not demonstrated capability.')
    pdf.paragraph(f"Resolved indicator weight: {result['assessment_coverage']}%. "
                  f"Decided conditions: {result['condition_decision_coverage']}%. These are evidence-resolution measures.")
    for tier in result['tiers']:
        pdf.paragraph(f"{tier['name']}: {tier['eligibility'].replace('_', ' ')} | "
                      f"Threshold {tier['threshold']} | Pillar floor {float(Fraction(str(tier['pillar_floor']))):.2f}")
    diagnostics = report['diagnostics']
    pdf.section('Understanding this result')
    pdf.paragraph(diagnostics['explanation'])
    pdf.paragraph(f"{diagnostics['source_documents']} documents; {diagnostics['readable_pages']} readable pages.")
    pdf.paragraph('; '.join(f"{LABELS[state]}: {count}" for state, count in diagnostics['state_counts'].items()))
    for issue in diagnostics['validation_issues']:
        pdf.paragraph(f"{issue['count']} decisions: {issue['reason']}")
    pdf.paragraph(diagnostics['limitations'], small=True)
    pdf.section('Assessment identity and frozen sources')
    for label in ('run_id', 'assessment_event_id', 'inputs_hash', 'exported_at'):
        pdf.paragraph(f'{label}: {report[label]}', small=True)
    for source in report['source_manifest']:
        pdf.paragraph(f"{source['filename']} | Version {source['version']} | {source['status']}")
        pdf.paragraph(f"Document {source['document_id']} | Checksum {source['checksum']}", small=True)
    pdf.paragraph('Text outside the bundled font is preserved using Unicode escape notation.', small=True)
    pdf.add_page()
    pdf.section('All indicators and requirement evidence')
    for indicator in indicators:
        pdf.section(f"{indicator['code']} - {indicator['name']}")
        pdf.paragraph(f"Level {indicator['lower_level']} - {indicator['upper_level']} | "
                      f"{indicator['lower']} - {indicator['upper']} / 100")
        for condition in indicator['requirements']:
            decision = condition['decision']
            pdf.paragraph(f"{condition['id']} | {LABELS[decision['state']]}", heading=True)
            pdf.paragraph(condition['text'])
            pdf.paragraph('Decision: ' + decision['reason'])
            pdf.paragraph('Completion evidence: ' + condition['completion_evidence'])
            for cite in decision['citations']:
                pdf.paragraph('Source quote: ' + cite['quote'])
                pdf.paragraph(source_labels.get(cite['source_id'], 'Frozen source') + ' | Page ID: ' + cite['source_id'], small=True)
    pdf.add_page()
    pdf.section('Next improvements and conditional tier pathways')
    for path in report['assessment']['pathways']:
        pdf.paragraph(path['target'], heading=True)
        pdf.paragraph(path['note'])
        pdf.paragraph(f"Scenario sufficient: {path['scenario_sufficient']}. Already demonstrated: {path['already_demonstrated']}.")
        pdf.paragraph('Requirements: ' + (', '.join(path['requirement_ids']) or 'None additional in this scenario.'))
    next_step = report['deterministic_plan']['next_overall']
    pdf.section('Next overall threshold')
    pdf.paragraph(f"Target: {next_step['target']} | Policy: {next_step['policy']['version']}")
    pdf.paragraph(next_step['policy']['basis'])
    if report['recommendation']:
        pdf.paragraph(f"Recommendation version: {report['recommendation']['id']} | {report['recommendation']['status']}")
    for action in actions:
        pdf.section(f"{action['id']} | {action['type']}")
        pdf.paragraph(action['requirement'])
        pdf.paragraph(action['suggestion'])
        pdf.paragraph('Canonical completion evidence: ' + action['completion_evidence'])
        advice = action.get('advice')
        if advice:
            pdf.paragraph(f"Suggested role: {advice['suggested_role']} | Effort: {advice['effort']}")
            for index, step in enumerate(advice['steps'], 1):
                pdf.paragraph(f'{index}. {step}')
            pdf.paragraph('Suggested completion evidence: ' + advice['completion_evidence'])
            pdf.paragraph('Dependencies: ' + (', '.join(advice['dependencies']) or 'None proposed'))
            for cite in advice['basis']:
                pdf.paragraph(cite['quote'])
                pdf.paragraph(source_labels.get(cite['source_id'], 'Frozen source') + ' | Page ID: ' + cite['source_id'], small=True)
    if report['recommendation'] and report['recommendation']['workflow_at_export']:
        pdf.section('User workflow at export')
        pdf.paragraph('Mutable workflow status is separate from the historical assessment and advice.')
        for row in report['recommendation']['workflow_at_export']:
            pdf.paragraph(f"{row['condition_id']} | Owner: {row['owner']} | Feasibility: {row['feasibility']} | Status: {row['status']}")
    return bytes(pdf.output())
