"""Source for depth_spec_v0.json: what a human auditor would ask about the evidence behind each rubric condition.

DRAFT v0.1 -- written by a model (Claude) from the rubric's condition texts, audited and revised 12 Nov 2026 (no
proof dimension, since every answer needs a document anyway; every dimension asks for something a document can
show; two dimensions per condition, up to the openness cap; where colleges usually file the evidence), for the rubric
reviewers to correct. It is not an approved standard. Every entry is a starting point: reviewers should add, remove and reword
dimensions, evidence forms and level descriptions, and change openness levels, as we learn how colleges
actually present evidence. Run `python -m apps.scoring.capability.depth_spec` to regenerate the JSON after editing.

Why this exists (see the "Follow-up questions to assess the depth of evidence" proposal): the part judge decides
whether evidence for a condition exists; it cannot tell a three-session local workshop from a 300-hour accredited
programme. The ways a college can satisfy a condition are endless, but the things an auditor asks about any of them
are few. This file lists those things ("quality dimensions") per key indicator, so that follow-up questions are
bespoke in wording but fixed in structure.

Per key indicator:
* where -- where colleges usually file this evidence (NAAC criteria; ABET criteria for programme-level indicators),
  so questions can point to documents the college already has. A draft mapping for the reviewers to check.
* openness -- how predictable the evidence is:
    standard: evidence takes a predictable form (a syllabus, a policy, an inventory); few questions, close to a checklist.
    moderate: some variety in form; a handful of dimensions.
    open:     many valid forms (faculty development, adoption, outcomes); more questions, more judgement, more reliance
              on approved past cases.
  QUESTIONS_PER_CONDITION caps how many follow-up questions one condition can generate at each level.
* dimensions -- the quality dimensions for the indicator: shared ones from DIMENSIONS by id, plus any defined inline
  as (id, name, ask).
* levels -- in words, what "substantiated" and "strong" mean for this indicator. "Evidenced" is always the same: the
  part judge credited the condition. Numeric thresholds are deliberately absent until we have assessed enough
  colleges to see the real spread.
* conditions -- per condition (F1..O2): the forms of evidence colleges typically present for it, and which of the
  indicator's dimensions matter for it. Conditions with no credited evidence get a "do you have anything?" question
  built from the assertion and these forms.
"""
import json
from pathlib import Path

VERSION = 'AIQIF-DEPTH-0.1'
RUBRIC = 'AIQIF-CAP-0.3'
STATUS = 'draft-audited'

STANDARD, MODERATE, OPEN = 'standard', 'moderate', 'open'
QUESTIONS_PER_CONDITION = {STANDARD: 2, MODERATE: 3, OPEN: 4}

# Shared quality dimensions: id -> (name, what the auditor asks). The question generator rewrites the ask around
# the college's own evidence ("how many hours did the 'AI for Educators' programme run per participant?").
DIMENSIONS = {
    'coverage': ('Coverage', 'How many people in the relevant group took part or are covered, out of how many in '
                             'total, and how was that group counted?'),
    'scope': ('Scope', 'Which departments, programmes or functions does it cover, out of the institution\'s total?'),
    'intensity': ('Intensity', 'How many hours, sessions or weeks did it run, per participant?'),
    'provider': ('Provider', 'Who designed or delivered it, and what accreditation, certification or standing does that '
                             'provider have?'),
    'content': ('Content depth', 'What did it actually cover? Is there a syllabus, agenda or specification, and at '
                                 'what depth?'),
    'ai_specificity': ('AI specificity', 'Which part of it involves artificial intelligence or machine learning '
                                         'specifically, as opposed to general digital or IT work?'),
    'recency': ('Recency', 'When did it happen, and is it still in force or running?'),
    'continuity': ('Continuity', 'Is this a one-off or does it recur? How many cycles or years has it run?'),
    'investment': ('Investment', 'What was spent or allocated: money, staff time, equipment?'),
    'owner': ('Ownership', 'Who is responsible, by name or role, and which order, circular or minutes assigns that '
                           'responsibility?'),
    'authority': ('Formal standing', 'Which body approved or adopted it, and when?'),
    'usage': ('Usage', 'How often is it used, by how many people, over what period?'),
    'measurement': ('Measurement method', 'What was measured, how, and against what target or baseline?'),
    'result': ('Result', 'What was the measured result, and how does it compare with the target or baseline?'),
    'independence': ('Independence', 'Who carried out the review or check, and were they separate from the people who '
                                     'delivered the work?'),
    'action': ('Action taken', 'What changed as a result, and was the change checked afterwards?'),
    'external': ('External validation', 'Has anyone outside the institution (an accreditor, partner, funder, journal or '
                                         'client) reviewed or validated it?'),
}

# Shared evidence forms, to keep the per-condition lists short.
IQAC = 'IQAC or governing-body minutes'
AQAR = 'AQAR or NAAC self-study report narrative'
CIRCULAR = 'an institutional circular or office order'

SPEC = {
    # ================================================================ C1 Strategy, governance and investment
    'AIQIF-C1.1': {  # Digital and AI Strategy Readiness
        'openness': MODERATE,
        'where': ('NAAC Criterion 6 (Governance, Leadership and Management): perspective or strategic plan, IQAC '
                  'minutes'),
        'dimensions': ['authority', 'ai_specificity', 'owner', 'investment', 'scope', 'measurement', 'result',
                       'action',
                       ('targets', 'Targets', 'Does the plan set dated, measurable targets for the AI priority, or only state an intention?')],
        'levels': ('The AI priority sits in an adopted plan with a named owner, a stated budget or resource line and '
                   'at least one dated target; delivery records show the initiative operating in a named function.',
                   'The plan is reviewed on a schedule; reviews record measured results against its targets and '
                   'decisions to continue, expand or stop AI initiatives, and later records show the effect of those '
                   'decisions.'),
        'conditions': {
            'F1': (['strategic or perspective plan', 'institutional development plan', IQAC], ['authority', 'ai_specificity', 'targets']),
            'F2': (['plan section naming a responsible office', CIRCULAR, IQAC], ['owner', 'authority']),
            'A1': (['deployment report or go-live note', 'usage summary for an AI system', AQAR], ['ai_specificity', 'scope', 'investment']),
            'A2': (['portfolio or project review minutes', IQAC], ['authority', 'action']),
            'O1': (['annual plan review against targets', 'AQAR outcome section'], ['measurement', 'result', 'targets']),
            'O2': (['later review assessing an earlier decision', IQAC], ['result', 'action']),
        },
    },
    'AIQIF-C1.2': {  # AI Governance & Accountability
        'openness': MODERATE,
        'where': ('NAAC Criterion 6 (Governance, Leadership and Management): committee terms of reference and '
                  'minutes, IQAC minutes'),
        'dimensions': ['authority', 'owner', 'ai_specificity', 'continuity', 'action', 'independence', 'result'],
        'levels': ('A constituted body with written terms of reference covering AI or digital decisions meets on a '
                   'schedule, and its minutes show at least one dated decision about an actual AI use.',
                   'Decisions are tracked to completion, the body reviews its own performance against incidents or '
                   'delivery results, and revised rules are checked for implementation.'),
        'conditions': {
            'F1': (['terms of reference of a committee or cell', CIRCULAR, IQAC], ['authority', 'ai_specificity']),
            'F2': (['governance or delegation document', 'escalation matrix'], ['owner', 'authority']),
            'A1': (['committee minutes with a dated decision', IQAC], ['ai_specificity', 'authority']),
            'A2': (['action-taken report', 'minutes of a later meeting'], ['action', 'continuity']),
            'O1': (['governance review report', 'IQAC annual review'], ['independence', 'result']),
            'O2': (['follow-up audit or action-taken report'], ['action', 'result']),
        },
    },
    'AIQIF-C1.3': {  # AI Investment & Resource Planning
        'openness': MODERATE,
        'where': ('NAAC Criterion 4 (Infrastructure and Learning Resources); NAAC Criterion 6 (Governance, Leadership '
                  'and Management): budget and finance committee records; ABET Criterion 8 (Institutional Support)'),
        'dimensions': ['investment', 'ai_specificity', 'coverage', 'authority', 'continuity', 'measurement', 'result',
                       'action'],
        'levels': ('A dated budget or resource commitment names its amount, its intended users and what it buys for '
                   'computing, teaching or innovation, approved by a named body.',
                   'Commitments recur across years, are compared with documented needs, and a later review reports '
                   'the capacity or benefit delivered against the cost.'),
        'conditions': {
            'F1': (['budget statement or finance committee minutes', 'purchase order or grant sanction', AQAR], ['investment', 'ai_specificity', 'authority']),
            'F2': (['allocation note naming beneficiaries', 'finance committee minutes'], ['coverage', 'investment', 'continuity']),
            'A1': (['needs assessment or gap analysis', 'budget review minutes'], ['measurement', 'investment']),
            'A2': (['capacity shortfall report and resulting sanction'], ['investment', 'action']),
            'O1': (['utilisation or outcome report for a purchase or grant'], ['result', 'measurement']),
            'O2': (['later review of a reallocation'], ['result', 'action']),
        },
    },
    'AIQIF-C1.4': {  # AI Adoption, Change & Institutional Alignment
        'openness': OPEN,
        'where': ('NAAC Criterion 6 (Governance, Leadership and Management): e-governance and service records'),
        'dimensions': ['usage', 'coverage', 'scope', 'owner', 'continuity', 'measurement', 'result', 'action'],
        'levels': ('A defined introduction process and support contact exist, and usage records show repeated use of '
                   'the service or tool by a stated group over a stated period.',
                   'Adoption is measured against an explicit target across most of the intended users, barriers are '
                   'documented and addressed, and the effect of changes is checked.'),
        'conditions': {
            'F1': (['SOP for introducing a tool or service', CIRCULAR], ['owner', 'scope']),
            'F2': (['help-desk or support contact notice', 'user guide'], ['owner', 'coverage']),
            'A1': (['LMS or platform usage report', 'login or activity statistics'], ['usage', 'coverage', 'continuity']),
            'A2': (['support ticket summary with response', 'training held in response to a barrier'], ['action', 'owner']),
            'O1': (['adoption review against a target'], ['measurement', 'result']),
            'O2': (['later review of a change to the tool or its support'], ['result', 'action']),
        },
    },
    # ================================================================ C2 Responsible AI, risk and assurance
    'AIQIF-C2.1': {  # Responsible AI Policy & Principles
        'openness': STANDARD,
        'where': ('NAAC Criterion 6 (Governance, Leadership and Management); NAAC Criterion 7 (Institutional Values '
                  'and Best Practices): policies and codes of conduct'),
        'dimensions': ['authority', 'ai_specificity', 'scope', 'recency', 'action', 'independence'],
        'levels': ('An approved, dated policy addresses AI use explicitly, states at least one restriction, and '
                   'applies to named groups (students, faculty, staff).',
                   'The policy is applied in onboarding or deployment checks, exceptions are reviewed and recorded, '
                   'and the policy is revised after incidents or assurance findings.'),
        'conditions': {
            'F1': (['AI use policy or guidelines', 'academic integrity policy with an AI section', CIRCULAR], ['authority', 'ai_specificity']),
            'F2': (['policy clause listing prohibited or restricted uses'], ['ai_specificity', 'scope']),
            'A1': (['deployment checklist or onboarding form'], ['scope', 'recency']),
            'A2': (['exception register or sampled-use review'], ['action', 'recency']),
            'O1': (['policy review minutes citing an incident or finding'], ['action', 'recency']),
            'O2': (['follow-up review of a revised control'], ['action', 'independence']),
        },
    },
    'AIQIF-C2.2': {  # AI Risk, Privacy & Security Governance
        'openness': STANDARD,
        'where': ('NAAC Criterion 4 (Infrastructure and Learning Resources): IT and data protection policies; NAAC '
                  'Criterion 6 (Governance, Leadership and Management)'),
        'dimensions': ['owner', 'scope', 'authority', 'ai_specificity', 'measurement', 'action'],
        'levels': ('Data protection responsibility is assigned by name or role, an access-control procedure covers '
                   'the relevant systems, and at least one deployed use has a dated risk assessment.',
                   'Risk decisions are recorded when access or suppliers change, reviews measure exposure against '
                   'stated criteria, and remediations are tested afterwards.'),
        'conditions': {
            'F1': (['data protection or privacy policy naming an officer', CIRCULAR], ['owner', 'authority']),
            'F2': (['access-control SOP', 'IT policy section on user access'], ['scope', 'authority']),
            'A1': (['risk assessment or data protection impact assessment'], ['ai_specificity', 'scope']),
            'A2': (['risk decision record for a vendor or access change'], ['action', 'owner']),
            'O1': (['risk review against a stated criterion'], ['measurement', 'scope']),
            'O2': (['remediation test report'], ['action', 'measurement']),
        },
    },
    'AIQIF-C2.3': {  # AI Model, Data & Lifecycle Governance
        'openness': MODERATE,
        'where': ('NAAC Criterion 4 (Infrastructure and Learning Resources): IT and software registers'),
        'dimensions': ['scope', 'owner', 'ai_specificity', 'measurement', 'continuity',
                       ('provenance', 'Data provenance', 'Where does the data behind the AI service come from, and is that recorded for each change?'),
                       'action'],
        'levels': ('An inventory lists the AI services in use with an owner for each, and at least one release or '
                   'change has an evaluation record.',
                   'Changes record data provenance, releases are monitored against stated evaluation criteria, and a '
                   'rollback or retirement has been exercised and its result recorded.'),
        'conditions': {
            'F1': (['AI or software inventory', 'IT asset register'], ['scope', 'ai_specificity']),
            'F2': (['inventory with owner column', CIRCULAR], ['owner', 'scope']),
            'A1': (['evaluation or test report for a release'], ['measurement', 'ai_specificity']),
            'A2': (['change record or release note naming data sources'], ['provenance', 'continuity']),
            'O1': (['monitoring report against an evaluation criterion'], ['measurement', 'continuity']),
            'O2': (['rollback or retirement record'], ['action', 'measurement']),
        },
    },
    'AIQIF-C2.4': {  # Human Oversight, Ethics & AI Assurance
        'openness': MODERATE,
        'where': ('NAAC Criterion 7 (Institutional Values and Best Practices); NAAC Criterion 2 (Teaching-Learning '
                  'and Evaluation): grievance and appeal procedures'),
        'dimensions': ['owner', 'ai_specificity', 'scope', 'independence', 'measurement', 'action', 'usage'],
        'levels': ('A consequential AI use (admissions, grading, proctoring, student support) has a defined human '
                   'intervention route and an appeal route, and records show oversight actually exercised.',
                   'Assurance tests examine specified failure or fairness risks, an independent reviewer evaluates '
                   'harms, and oversight changes are tested for effect.'),
        'conditions': {
            'F1': (['SOP naming a human review step for an AI use'], ['owner', 'ai_specificity']),
            'F2': (['grievance or appeal procedure covering the AI use'], ['scope', 'owner']),
            'A1': (['override or review log', 'committee record of a reviewed AI decision'], ['usage', 'scope']),
            'A2': (['fairness or failure test report'], ['measurement', 'independence']),
            'O1': (['independent review of an AI use'], ['independence', 'measurement']),
            'O2': (['follow-up test after an oversight change'], ['action', 'measurement']),
        },
    },
    # ================================================================ C3 Curriculum and pedagogy
    'AIQIF-C3.1': {  # AI Curriculum Integration & Programme Design
        'openness': STANDARD,
        'where': ('NAAC Criterion 1 (Curricular Aspects): Board of Studies and Academic Council minutes; ABET '
                  'Criterion 5 (Curriculum)'),
        'dimensions': ['content', 'coverage', 'intensity', 'recency',
                       ('credits', 'Credit weight', 'How many credits or contact hours does the AI content carry, and is it core or elective?')],
        'levels': ('A syllabus approved by the Board of Studies or Academic Council includes AI or ML units with '
                   'stated learning objectives, credits and contact hours, delivered to a named programme.',
                   'AI content is core (not only elective) in the relevant programmes, attainment is assessed against '
                   'the AI objectives, and course reviews revise the content and check the effect.'),
        'conditions': {
            'F1': (['approved syllabus or course structure', 'Board of Studies minutes'], ['content', 'credits']),
            'F2': (['course outcomes (COs) in the syllabus'], ['content', 'intensity']),
            'A1': (['timetable, lesson plan or course file', 'attendance register'], ['coverage', 'intensity']),
            'A2': (['marked assessments or CO attainment sheet'], ['coverage', 'content']),
            'O1': (['course exit survey or CO-PO attainment review'], ['content', 'coverage']),
            'O2': (['assessment results after a syllabus revision'], ['recency', 'content']),
        },
    },
    'AIQIF-C3.2': {  # AI Literacy Across Disciplines
        'openness': MODERATE,
        'where': ('NAAC Criterion 1 (Curricular Aspects): value-added and open elective courses'),
        'dimensions': ['coverage', 'scope', 'intensity', 'content', 'continuity', 'measurement', 'result'],
        'levels': ('A defined AI literacy offer (course, module or value-added programme) reaches learners in at '
                   'least one discipline outside computing, with delivery records and stated hours.',
                   'The offer reaches most disciplines on a recurring basis, attainment is assessed per discipline, '
                   'and gaps are targeted with support whose effect is measured.'),
        'conditions': {
            'F1': (['value-added or open elective course description', CIRCULAR], ['content', 'intensity']),
            'F2': (['enrolment notice or elective list for a learner group'], ['scope', 'coverage']),
            'A1': (['attendance or completion list for a discipline'], ['coverage', 'scope', 'continuity']),
            'A2': (['remedial or bridge session record'], ['coverage', 'content']),
            'O1': (['assessment results by discipline'], ['measurement', 'result']),
            'O2': (['follow-up assessment after targeted support'], ['measurement', 'result']),
        },
    },
    'AIQIF-C3.3': {  # AI-Enabled Pedagogy & Assessment
        'openness': OPEN,
        'where': ('NAAC Criterion 2 (Teaching-Learning and Evaluation): ICT-enabled teaching; ABET Criterion 3 '
                  '(Student Outcomes)'),
        'dimensions': ['scope', 'usage', 'continuity', 'content', 'measurement', 'result', 'action',
                       ('guidance', 'Learner guidance', 'Are students told what AI use is acceptable for this activity, and how is that enforced?')],
        'levels': ('A course design specifies an AI-supported learning or feedback activity, learners are told what '
                   'AI use is acceptable, and course records show the activity used repeatedly.',
                   'The activity runs across several courses or semesters, assessment checks for inappropriate '
                   'dependence on AI, and results are compared with a baseline and the design revised.'),
        'conditions': {
            'F1': (['course plan or lesson plan describing the AI activity'], ['content', 'scope']),
            'F2': (['assignment brief or course policy on AI use'], ['guidance', 'scope']),
            'A1': (['LMS activity records', 'course file entries across sessions'], ['usage', 'continuity', 'scope']),
            'A2': (['assessment rubric or viva record checking AI dependence'], ['guidance', 'measurement']),
            'O1': (['evaluation comparing results with a baseline'], ['measurement', 'result']),
            'O2': (['later evaluation after a design change'], ['result', 'action']),
        },
    },
    'AIQIF-C3.4': {  # Experiential, Project & Applied AI Learning
        'openness': MODERATE,
        'where': ('NAAC Criterion 1 (Curricular Aspects): projects, field work and internships; NAAC Criterion 2 '
                  '(Teaching-Learning and Evaluation); ABET Criterion 5 (Curriculum)'),
        'dimensions': ['coverage', 'content', 'continuity', 'external',
                       ('mentoring', 'Mentoring', 'Who mentors the work, how often, and with what expertise?'),
                       ('individual', 'Individual contribution', "How is each student's own contribution checked?")],
        'levels': ('A project or lab route requires substantive AI work, mentors are assigned, and assessed projects '
                   'show an implemented AI application for a named student group.',
                   'Individual contribution is moderated, projects are evaluated against an explicit capability '
                   'criterion (ideally with external reviewers or real users), and mentoring changes are evaluated.'),
        'conditions': {
            'F1': (['project or lab course description', 'list of AI project titles'], ['content', 'coverage']),
            'F2': (['mentor allocation list'], ['mentoring', 'coverage']),
            'A1': (['project reports, demos or evaluation sheets'], ['coverage', 'content']),
            'A2': (['viva or moderation record'], ['individual', 'external']),
            'O1': (['project review against a capability criterion', 'hackathon or competition results'], ['external', 'content']),
            'O2': (['later cohort evaluated after a mentoring change'], ['continuity', 'mentoring']),
        },
    },
    # ================================================================ C4 Faculty and staff capability
    'AIQIF-C4.1': {  # Faculty AI Literacy & Awareness
        'openness': OPEN,
        'where': ('NAAC Criterion 6 (Governance, Leadership and Management): faculty development and training '
                  'programmes; NAAC Criterion 2 (Teaching-Learning and Evaluation); ABET Criterion 6 (Faculty)'),
        'dimensions': ['coverage', 'intensity', 'provider', 'content', 'recency', 'continuity', 'investment',
                       ('assessed', 'Assessment', 'Was what faculty learned assessed (a test, a task, a certification exam), and what were the results?')],
        'levels': ('A defined AI programme with a stated syllabus reached a stated share of faculty, with hours per '
                   'participant and completion records; for example a multi-day programme with a published agenda '
                   'rather than a single talk.',
                   'A sustained, credentialed programme (an accredited provider or a certification with an '
                   'assessment) reached most of the relevant faculty, with substantial hours per person, assessed '
                   'results, and gaps followed up; for example a long programme at a recognised institution with a '
                   'rigorous syllabus, rather than a few sessions at a local institute.'),
        'conditions': {
            'F1': (['FDP or workshop brochure with session topics', 'training calendar', 'NPTEL or ATAL FDP course page'], ['content', 'provider', 'intensity', 'investment']),
            'F2': (['attendance list or participation certificates', AQAR], ['coverage', 'intensity', 'recency']),
            'A1': (['quiz, test or certification results', 'completion certificates with an assessment component'], ['assessed', 'coverage', 'provider']),
            'A2': (['follow-up session targeting a documented gap', 'needs analysis and resulting training'], ['content', 'coverage']),
            'O1': (['competency assessment against a framework'], ['assessed', 'coverage']),
            'O2': (['repeat assessment after a programme revision'], ['assessed', 'continuity']),
        },
    },
    'AIQIF-C4.2': {  # Role-Based Faculty AI Capability
        'openness': OPEN,
        'where': ('NAAC Criterion 6 (Governance, Leadership and Management): faculty development and training '
                  'programmes; ABET Criterion 6 (Faculty)'),
        'dimensions': ['coverage', 'intensity', 'provider', 'content', 'continuity',
                       ('role_fit', 'Role fit', 'Which academic role is it designed for (course designer, researcher, assessor, mentor), and what skill does it build for that role?'),
                       ('applied', 'Applied in work', 'Is there a sample of faculty work showing the skill applied?')],
        'levels': ('A learning offer targets a named academic role, includes a practice task that builds a specific '
                   'AI skill, and an assessed task shows faculty demonstrating it.',
                   'Role pathways cover most relevant faculty, skill gaps are documented and addressed, and work '
                   'samples show the skill applied in real academic work, with the pathway revised and re-evaluated.'),
        'conditions': {
            'F1': (['role-specific programme description'], ['role_fit', 'content', 'provider']),
            'F2': (['practice task or assignment within the programme'], ['role_fit', 'intensity']),
            'A1': (['assessed task results'], ['coverage', 'content']),
            'A2': (['gap analysis and resulting support'], ['role_fit', 'coverage']),
            'O1': (['work samples: course material, research output, assessment design'], ['applied', 'role_fit']),
            'O2': (['later task evaluation after a pathway change'], ['continuity', 'applied']),
        },
    },
    'AIQIF-C4.3': {  # AI-Enabled Teaching, Research & Academic Practice
        'openness': OPEN,
        'where': ('NAAC Criterion 2 (Teaching-Learning and Evaluation); NAAC Criterion 3 (Research, Innovations and '
                  'Extension); ABET Criterion 6 (Faculty)'),
        'dimensions': ['usage', 'coverage', 'continuity', 'measurement', 'result', 'action',
                       ('review_step', 'Human review', 'Who checks the AI-supported work before it is used, and how?')],
        'levels': ('Faculty work records show AI used in a named academic task (course material, research analysis, '
                   'grading support), with a defined human review step, repeated across sessions or faculty.',
                   'AI-supported practice is widespread in a department, quality checks evaluate the work, and an '
                   'evaluation compares quality, time or research results with a baseline.'),
        'conditions': {
            'F1': (['faculty work record or course file showing AI use'], ['usage', 'coverage']),
            'F2': (['guideline defining review of AI-supported work'], ['review_step', 'coverage']),
            'A1': (['several work samples across time or faculty'], ['usage', 'coverage', 'continuity']),
            'A2': (['quality check or peer review of AI-supported work'], ['review_step', 'measurement']),
            'O1': (['evaluation against a baseline'], ['measurement', 'result']),
            'O2': (['practice change after an identified failure'], ['action', 'result']),
        },
    },
    'AIQIF-C4.4': {  # Staff AI Capability, FDP & Change Enablement
        'openness': OPEN,
        'where': ('NAAC Criterion 6 (Governance, Leadership and Management): training for non-teaching staff'),
        'dimensions': ['coverage', 'intensity', 'provider', 'content', 'measurement', 'result',
                       ('role_fit', 'Role fit', 'Which non-teaching role is it for (office, library, accounts, IT), and which task does it improve?'),
                       'action'],
        'levels': ('A digital or AI learning offer targets a named non-teaching role, a support route exists, and an '
                   'assessed task shows the skill in that role.',
                   'Most staff in the targeted roles are covered, task performance is compared with a role criterion, '
                   'and training or support changes are evaluated for effect.'),
        'conditions': {
            'F1': (['staff training programme description', 'administrative staff training list in the AQAR'], ['role_fit', 'content', 'intensity', 'provider']),
            'F2': (['help desk or mentor contact for staff'], ['coverage', 'role_fit']),
            'A1': (['assessed task or skill test for staff'], ['coverage', 'measurement']),
            'A2': (['error log and resulting support action'], ['role_fit', 'action']),
            'O1': (['performance evaluation against a role criterion'], ['measurement', 'result']),
            'O2': (['follow-up evaluation after a training change'], ['result', 'measurement']),
        },
    },
    # ================================================================ C5 Students
    'AIQIF-C5.1': {  # Student AI Literacy Provision and Attainment
        'openness': MODERATE,
        'where': ('NAAC Criterion 1 (Curricular Aspects): value-added courses; NAAC Criterion 5 (Student Support and '
                  'Progression)'),
        'dimensions': ['coverage', 'scope', 'intensity', 'content', 'continuity', 'measurement', 'result'],
        'levels': ('An AI literacy offer with stated objectives and hours reaches a named student cohort, with '
                   'delivery records.',
                   'The offer reaches most students across programmes each year, attainment is assessed against an '
                   'explicit criterion, and participation or attainment gaps are addressed and re-measured.'),
        'conditions': {
            'F1': (['course or programme description open to a student group'], ['scope', 'content']),
            'F2': (['learning objectives in the course description'], ['content', 'intensity']),
            'A1': (['enrolment and completion records for a cohort'], ['coverage', 'intensity', 'continuity']),
            'A2': (['remedial or outreach action after low participation'], ['coverage', 'scope']),
            'O1': (['assessment results against a criterion'], ['measurement', 'result']),
            'O2': (['follow-up results after a change'], ['result', 'measurement']),
        },
    },
    'AIQIF-C5.2': {  # Advanced & Role-Specific AI Skills
        'openness': MODERATE,
        'where': ('NAAC Criterion 1 (Curricular Aspects): programmes, minors and electives; ABET Criterion 5 '
                  '(Curriculum)'),
        'dimensions': ['coverage', 'content', 'intensity', 'external', 'measurement', 'result',
                       ('practical', 'Practical assessment', 'Is there a hands-on task (a model built, a deployment, a project) assessed against a stated criterion?')],
        'levels': ('A defined advanced pathway (a specialisation, minor or honours track) for a named student group '
                   'includes a practical assessment, and student work shows the skill against an explicit criterion.',
                   'The pathway is revised in response to employer or disciplinary feedback, progression or skill '
                   'results are reviewed, and revisions are evaluated.'),
        'conditions': {
            'F1': (['specialisation, minor or honours scheme', 'AICTE-approved programme in AI and ML'], ['content', 'coverage']),
            'F2': (['practical or lab component in the scheme'], ['practical', 'intensity']),
            'A1': (['assessed student work against a rubric'], ['practical', 'coverage']),
            'A2': (['curriculum change citing employer feedback', 'industry advisory board minutes'], ['external', 'content']),
            'O1': (['pathway review of skills or progression'], ['measurement', 'result']),
            'O2': (['later task evaluation after a revision'], ['result', 'practical']),
        },
    },
    'AIQIF-C5.3': {  # Student AI Projects, Portfolio & Practice
        'openness': MODERATE,
        'where': ('NAAC Criterion 1 (Curricular Aspects): student projects; NAAC Criterion 3 (Research, Innovations '
                  'and Extension)'),
        'dimensions': ['coverage', 'content', 'external', 'continuity',
                       ('individual', 'Individual contribution', "How is each student's own contribution identified and checked?"),
                       'result'],
        'levels': ('An AI project or portfolio opportunity is available to a named student group, and reviewed '
                   "portfolios identify each student's substantive AI contribution.",
                   'Projects are moderated and evaluated against an explicit quality or real-user-value criterion, '
                   'ideally with external reviewers, and mentoring changes are evaluated.'),
        'conditions': {
            'F1': (['project scheme or portfolio requirement'], ['coverage', 'content']),
            'F2': (['evaluation rubric with an individual contribution criterion'], ['individual', 'content']),
            'A1': (['reviewed portfolios or project reports'], ['individual', 'coverage']),
            'A2': (['moderation record'], ['individual', 'external']),
            'O1': (['evaluation of quality or real-user value'], ['external', 'content']),
            'O2': (['later evaluation after a change'], ['continuity', 'result']),
        },
    },
    'AIQIF-C5.4': {  # AI Employability, Internships & Career Outcomes
        'openness': MODERATE,
        'where': ('NAAC Criterion 5 (Student Support and Progression): placement and progression records'),
        'dimensions': ['coverage', 'ai_specificity', 'external', 'measurement', 'result', 'scope'],
        'levels': ('AI-relevant internships or career opportunities are documented with eligibility rules, and '
                   'verified records (offer letters, completion certificates) show participation.',
                   'Participation and AI-related career results are reported against a cohort denominator and a '
                   'target, and pathway changes are evaluated.'),
        'conditions': {
            'F1': (['internship or placement notice for an AI role'], ['ai_specificity', 'external']),
            'F2': (['eligibility criteria in the notice or policy'], ['coverage', 'scope']),
            'A1': (['offer letters, internship certificates', 'placement records'], ['ai_specificity', 'external']),
            'A2': (['cohort register', 'placement statistics with totals'], ['coverage', 'measurement']),
            'O1': (['placement review against a target'], ['measurement', 'result', 'coverage']),
            'O2': (['later review after a pathway change'], ['result', 'measurement']),
        },
    },
    # ================================================================ C6 Infrastructure and data
    'AIQIF-C6.1': {  # Computing Provision and AI Workload Suitability
        'openness': STANDARD,
        'where': ('NAAC Criterion 4 (Infrastructure and Learning Resources): IT infrastructure; ABET Criterion 7 '
                  '(Facilities)'),
        'dimensions': ['coverage', 'usage', 'investment', 'measurement',
                       ('specification', 'Specification', 'What hardware or cloud capacity is provided (GPUs, memory, cloud credits), and which AI workload does it support?'),
                       'action'],
        'levels': ('Named computing resources with stated specifications support an introductory AI workload, and '
                   'usage records show them serving a named user group.',
                   'Capacity is monitored against availability targets, shortfalls are addressed, and continuity or '
                   'recovery has been exercised.'),
        'conditions': {
            'F1': (['lab or HPC facility description', 'cloud platform access notice'], ['coverage', 'specification']),
            'F2': (['hardware specification sheet', 'purchase order with specifications'], ['specification', 'investment']),
            'A1': (['usage logs or booking records'], ['usage', 'coverage']),
            'A2': (['support ticket and resolution', 'upgrade after a reported shortfall'], ['action', 'specification']),
            'O1': (['service performance review'], ['measurement', 'usage']),
            'O2': (['continuity or recovery exercise record'], ['measurement', 'action']),
        },
    },
    'AIQIF-C6.2': {  # Institutional Data Readiness
        'openness': MODERATE,
        'where': ('NAAC Criterion 6 (Governance, Leadership and Management): e-governance; NAAC Criterion 4 '
                  '(Infrastructure and Learning Resources)'),
        'dimensions': ['scope', 'owner', 'measurement', 'result', 'action', 'ai_specificity'],
        'levels': ('A register lists relevant datasets or systems with a custodian for each, and a data-quality check '
                   'operates for an identified AI use or preparation activity.',
                   'Data-quality issues are tracked to disposition, quality is reviewed against a fitness criterion, '
                   'and the effect of data-quality changes on downstream work is measured.'),
        'conditions': {
            'F1': (['data or system register', 'ERP module list'], ['scope', 'ai_specificity']),
            'F2': (['register with custodians', CIRCULAR], ['owner', 'scope']),
            'A1': (['data-quality check report'], ['ai_specificity', 'measurement']),
            'A2': (['issue log with dispositions'], ['action', 'owner']),
            'O1': (['data-quality review against a criterion'], ['measurement', 'result']),
            'O2': (['follow-up measurement after a change'], ['result', 'action']),
        },
    },
    'AIQIF-C6.3': {  # AI Cybersecurity & Resilience
        'openness': STANDARD,
        'where': ('NAAC Criterion 4 (Infrastructure and Learning Resources): IT policy and security'),
        'dimensions': ['owner', 'scope', 'ai_specificity', 'measurement', 'action', 'independence'],
        'levels': ('Security responsibility for the AI or computing environment is assigned, a recovery procedure '
                   'covers it, and a security test has examined an AI-related threat.',
                   'Incidents and exercises record response actions, reviews compare remediation or recovery against '
                   'a stated criterion, and control changes are tested.'),
        'conditions': {
            'F1': (['IT security policy naming an officer', CIRCULAR], ['owner', 'scope']),
            'F2': (['backup and recovery SOP'], ['scope', 'measurement']),
            'A1': (['security test or audit report naming an AI-related threat'], ['ai_specificity', 'independence']),
            'A2': (['incident report or drill record'], ['action', 'measurement']),
            'O1': (['security review against a criterion'], ['measurement', 'independence']),
            'O2': (['follow-up test after a control change'], ['action', 'measurement']),
        },
    },
    'AIQIF-C6.4': {  # AI Labs, Digital Learning Environment & Accessibility
        'openness': STANDARD,
        'where': ('NAAC Criterion 4 (Infrastructure and Learning Resources): laboratories and ICT facilities; ABET '
                  'Criterion 7 (Facilities)'),
        'dimensions': ['coverage', 'usage', 'scope', 'measurement', 'action',
                       ('access', 'Access route', 'How do learners get access (timetabled slots, booking, remote login), and who is excluded?')],
        'levels': ('A named environment supports a specified introductory AI activity, learners have a defined access '
                   'route, and usage records show learners using it.',
                   'Access is reviewed against a service or equity criterion, accessibility or capacity issues are '
                   'addressed, and improvements are evaluated.'),
        'conditions': {
            'F1': (['lab description with the AI activity it supports'], ['scope', 'coverage']),
            'F2': (['lab timetable or access policy'], ['access', 'coverage']),
            'A1': (['lab usage or login records'], ['usage', 'coverage']),
            'A2': (['response to an accessibility or capacity complaint'], ['action', 'access']),
            'O1': (['access review against a criterion'], ['measurement', 'access']),
            'O2': (['follow-up after an improvement'], ['action', 'measurement']),
        },
    },
    # ================================================================ C7 Research and innovation
    'AIQIF-C7.1': {  # AI Research Capability & Agenda
        'openness': MODERATE,
        'where': ('NAAC Criterion 3 (Research, Innovations and Extension): research projects, publications and '
                  'patents'),
        'dimensions': ['owner', 'investment', 'external', 'ai_specificity', 'continuity', 'result',
                       ('output_quality', 'Output quality', 'Where did the output appear (indexed journal, conference tier, granted patent, deployed tool), and how was it reviewed?')],
        'levels': ('An AI research project has a defined objective and a named lead, and an active project has a '
                   'reviewed output (a peer-reviewed paper, a filed patent, a working prototype).',
                   'Several active projects with funding produce externally reviewed outputs (indexed publications, '
                   'granted patents, sponsored work), progress is reviewed with recorded decisions, and agenda '
                   'changes are evaluated.'),
        'conditions': {
            'F1': (['project proposal or sanction letter', 'research centre project list'], ['ai_specificity', 'investment']),
            'F2': (['project with principal investigator named'], ['owner', 'investment']),
            'A1': (['publication list', 'patent filing', 'project progress report'], ['output_quality', 'external']),
            'A2': (['research committee minutes'], ['continuity', 'result']),
            'O1': (['completed project report against objectives'], ['result', 'output_quality']),
            'O2': (['review after a change in agenda or resources'], ['result', 'continuity']),
        },
    },
    'AIQIF-C7.2': {  # AI Innovation and Mentoring Support
        'openness': OPEN,
        'where': ('NAAC Criterion 3 (Research, Innovations and Extension): innovation ecosystem and incubation'),
        'dimensions': ['owner', 'investment', 'usage', 'coverage', 'continuity', 'result', 'action', 'external'],
        'levels': ('An AI centre, innovation cell or incubator has a defined remit and a project or mentoring '
                   'service, and service records show engagements.',
                   'The function serves many projects over several years, reviews its service against use and '
                   'delivery evidence, and reports outputs or institutional benefit against its objective.'),
        'conditions': {
            'F1': (['centre of excellence or innovation cell charter', CIRCULAR], ['owner', 'investment']),
            'F2': (['service or mentoring offer notice'], ['coverage', 'usage']),
            'A1': (['engagement log or mentoring records'], ['usage', 'coverage']),
            'A2': (['service review minutes'], ['action', 'continuity']),
            'O1': (['annual report of outputs and benefits'], ['result', 'external']),
            'O2': (['follow-up review after a service change'], ['result', 'action']),
        },
    },
    'AIQIF-C7.3': {  # AI Funding, IP & Entrepreneurship
        'openness': MODERATE,
        'where': ('NAAC Criterion 3 (Research, Innovations and Extension): research funding, IPR and start-ups'),
        'dimensions': ['investment', 'coverage', 'external', 'result',
                       ('stage', 'Stage reached', 'How far has the project progressed: filed, granted, funded, incorporated, revenue?'),
                       'continuity'],
        'levels': ('A funding, IP or incubation route is available with a contact or application process, and a '
                   'project record shows an AI project using it.',
                   'Funding or translation decisions are recorded, and verified progression (granted IP, external '
                   'funding, incorporation, revenue) is reviewed against milestones.'),
        'conditions': {
            'F1': (['seed fund or IPR cell policy', 'incubation centre description'], ['investment', 'coverage']),
            'F2': (['application form or contact notice'], ['coverage', 'continuity']),
            'A1': (['funded project list', 'patent filing', 'incubation agreement'], ['stage', 'external']),
            'A2': (['funding committee minutes'], ['investment', 'stage']),
            'O1': (['progress review against milestones'], ['stage', 'external', 'result']),
            'O2': (['follow-up after a support change'], ['result', 'stage']),
        },
    },
    'AIQIF-C7.4': {  # AI Collaboration, Knowledge Transfer & Societal Impact
        'openness': OPEN,
        'where': ('NAAC Criterion 3 (Research, Innovations and Extension): collaborations, MoUs and extension'),
        'dimensions': ['ai_specificity', 'owner', 'external', 'result', 'continuity',
                       ('beyond_mou', 'Delivery beyond the agreement', 'What has actually been delivered under the collaboration, beyond signing the MoU?')],
        'levels': ('A collaboration work plan specifies substantive AI work with partner responsibilities, and a '
                   'delivery record shows AI work delivered beyond the agreement itself.',
                   'Partners or beneficiaries evaluate the delivered contribution, and a review reports knowledge '
                   'transfer or a beneficiary result against a stated objective.'),
        'conditions': {
            'F1': (['MoU with an AI work plan'], ['ai_specificity', 'owner']),
            'F2': (['work plan with partner responsibilities'], ['owner', 'continuity']),
            'A1': (['joint project report, workshop delivered, tool handed over'], ['beyond_mou', 'external']),
            'A2': (['partner or beneficiary feedback'], ['external', 'result']),
            'O1': (['impact review against objectives'], ['result', 'external']),
            'O2': (['follow-up after a collaboration change'], ['continuity', 'result']),
        },
    },
    # ================================================================ C8 Operations, industry and outcomes
    'AIQIF-C8.1': {  # Digital Services and AI-Enabled Operations
        'openness': OPEN,
        'where': ('NAAC Criterion 6 (Governance, Leadership and Management): e-governance'),
        'dimensions': ['owner', 'ai_specificity', 'usage', 'scope', 'continuity', 'measurement', 'result', 'action'],
        'levels': ('An institutional service with a defined purpose and owner uses AI repeatedly, shown by '
                   'operational records (e.g. chatbot logs, automated timetabling, analytics dashboards).',
                   'AI-related exceptions are monitored, benefits are compared with a baseline with quality '
                   'limitations disclosed, and workflow changes are tested.'),
        'conditions': {
            'F1': (['service description', 'ERP or portal module description'], ['scope', 'ai_specificity']),
            'F2': (['service owner named in an order or SOP'], ['owner', 'scope']),
            'A1': (['operational logs or usage statistics for the AI feature'], ['ai_specificity', 'usage', 'continuity']),
            'A2': (['exception or monitoring report'], ['measurement', 'action']),
            'O1': (['evaluation against a baseline'], ['measurement', 'result']),
            'O2': (['follow-up after a workflow change'], ['action', 'result']),
        },
    },
    'AIQIF-C8.2': {  # Industry Integration & AI Partnerships
        'openness': MODERATE,
        'where': ('NAAC Criterion 3 (Research, Innovations and Extension): industry collaborations and MoUs'),
        'dimensions': ['ai_specificity', 'coverage', 'external', 'result', 'continuity',
                       ('contribution', 'Partner contribution', 'What did the partner contribute: trainers, curriculum, projects, internships, equipment?')],
        'levels': ('An industry work plan specifies an AI activity with a defined contribution to skills, curriculum '
                   'or projects, and a delivery record shows it happened with the partner.',
                   "The partner's contribution is reviewed, outcomes are evaluated against stated objectives, and "
                   'jointly agreed changes are evaluated.'),
        'conditions': {
            'F1': (['industry MoU with an AI activity'], ['ai_specificity', 'contribution']),
            'F2': (['work plan stating the partner contribution'], ['contribution', 'coverage']),
            'A1': (['delivery record: training held, projects run, interns hosted'], ['coverage', 'contribution']),
            'A2': (['partnership review'], ['contribution', 'external']),
            'O1': (['partnership outcome review'], ['result', 'external']),
            'O2': (['follow-up after a jointly agreed change'], ['continuity', 'result']),
        },
    },
    'AIQIF-C8.3': {  # AI Entrepreneurship, Placement & Workforce Outcomes
        'openness': MODERATE,
        'where': ('NAAC Criterion 5 (Student Support and Progression): placements; NAAC Criterion 3 (Research, '
                  'Innovations and Extension): start-ups'),
        'dimensions': ['ai_specificity', 'coverage', 'measurement', 'result', 'scope', 'external'],
        'levels': ('A pathway explicitly addresses AI skills with a referral route, and verified records link '
                   'participants to opportunities or ventures.',
                   'Reviews relate participation to results with a denominator, and progression or enterprise results '
                   'are evaluated against stated objectives.'),
        'conditions': {
            'F1': (['pathway or programme description'], ['ai_specificity', 'coverage']),
            'F2': (['referral or application route'], ['coverage', 'scope']),
            'A1': (['verified placement or venture records'], ['ai_specificity', 'external']),
            'A2': (['review of participation versus results'], ['coverage', 'measurement']),
            'O1': (['outcome review against objectives'], ['result', 'coverage']),
            'O2': (['follow-up after a portfolio change'], ['result', 'measurement']),
        },
    },
    'AIQIF-C8.4': {  # Measured AI Business/Educational Outcomes
        'openness': OPEN,
        'where': ('NAAC Criterion 7 (Institutional Values and Best Practices): best practices; NAAC Criterion 2 '
                  '(Teaching-Learning and Evaluation): student performance and learning outcomes; ABET Criterion 4 '
                  '(Continuous Improvement)'),
        'dimensions': ['ai_specificity', 'measurement', 'result', 'independence', 'action',
                       ('baseline', 'Baseline', 'What was the situation before the intervention, and how was it measured?'),
                       ('limits', 'Limitations', 'What else could explain the result, and which review or report examined that and any harms?')],
        'levels': ('An AI intervention has an explicit intended outcome and a defined measurement method, and '
                   'recorded results compare the outcome with a baseline.',
                   'Alternative explanations and harms are examined, benefits are reported within stated limitations, '
                   'and intervention changes are measured again.'),
        'conditions': {
            'F1': (['intervention plan stating the intended outcome'], ['ai_specificity', 'baseline']),
            'F2': (['measurement plan'], ['measurement', 'baseline']),
            'A1': (['results compared with a baseline'], ['baseline', 'result']),
            'A2': (['review of confounders or harms'], ['limits', 'independence']),
            'O1': (['measurement review with limitations'], ['limits', 'result']),
            'O2': (['later measurement after a change'], ['action', 'result']),
        },
    },
    # ================================================================ C9 Measurement and improvement
    'AIQIF-C9.1': {  # Institutional Measurement and Readiness Review
        'openness': MODERATE,
        'where': ('NAAC Criterion 6 (Governance, Leadership and Management): IQAC and AQAR; ABET Criterion 4 '
                  '(Continuous Improvement)'),
        'dimensions': ['owner', 'continuity', 'measurement', 'action',
                       ('reproducible', 'Reproducibility', "Which records do the review's figures come from, and are those records listed or attached?"),
                       'authority',
                       ('method_change', 'Method changes', 'Which changes were made to the review method, when and why, and are results before and after the change kept apart?')],
        'levels': ('An institutional review uses defined indicators, someone is responsible for producing it, and it '
                   'has been repeated with traceable evidence.',
                   'Calculations are reproducible, method changes are distinguished from real changes, and results '
                   'drive improvement priorities that are later evaluated.'),
        'conditions': {
            'F1': (['IQAC review framework with indicators', AQAR], ['measurement', 'owner']),
            'F2': (['IQAC composition or order assigning the review'], ['owner', 'authority']),
            'A1': (['two or more cycles of the review with cited evidence'], ['continuity', 'reproducible']),
            'A2': (['change log for the review method'], ['method_change', 'continuity']),
            'O1': (['review stating improvement priorities from results'], ['action', 'measurement']),
            'O2': (['follow-up after a method revision'], ['action', 'measurement']),
        },
    },
    'AIQIF-C9.2': {  # Evidence, Traceability & Auditability
        'openness': STANDARD,
        'where': ('NAAC Criterion 6 (Governance, Leadership and Management): IQAC documentation'),
        'dimensions': ['owner', 'independence', 'continuity',
                       ('traceable', 'Traceability', 'Is there an index linking each finding to the requirement it supports and the exact source record?'),
                       'authority',
                       ('versions', 'Earlier versions', 'Are earlier versions kept, with the date of and reason for each correction or reassessment?')],
        'levels': ('An evidence index lists the source records used for assessment, a custodian preserves them, and '
                   'sampled findings are traceable to their sources.',
                   'Corrections preserve earlier records with reasons, audits check traceability with an explicit '
                   'procedure, and process improvements are measured.'),
        'conditions': {
            'F1': (['evidence index or document register'], ['traceable', 'owner']),
            'F2': (['custodian named in an order or SOP'], ['owner', 'authority']),
            'A1': (['sampled trace from finding to source'], ['traceable', 'independence']),
            'A2': (['correction log keeping prior versions'], ['versions', 'continuity']),
            'O1': (['traceability audit'], ['independence', 'traceable']),
            'O2': (['follow-up after a process improvement'], ['continuity', 'independence']),
        },
    },
    'AIQIF-C9.3': {  # Benchmark Evolution & AI Readiness Drift
        'openness': MODERATE,
        'where': ('NAAC Criterion 6 (Governance, Leadership and Management): IQAC'),
        'dimensions': ['owner', 'continuity', 'measurement', 'action', 'recency',
                       ('versions', 'Earlier versions', 'Are earlier versions kept, with the date of and reason for each correction or reassessment?')],
        'levels': ('A process monitors relevant accreditation, curriculum or technology changes on a defined '
                   'schedule, and a change review has identified an affected requirement.',
                   'Reassessments are versioned with prior results preserved, timeliness of detection is reviewed, '
                   'and the monitoring process is revised and re-evaluated.'),
        'conditions': {
            'F1': (['monitoring process description', 'IQAC agenda item on regulatory updates'], ['owner', 'continuity']),
            'F2': (['review schedule'], ['continuity', 'recency']),
            'A1': (['change review naming an affected requirement'], ['recency', 'action']),
            'A2': (['versioned reassessment record'], ['versions', 'continuity']),
            'O1': (['timeliness review'], ['measurement', 'recency']),
            'O2': (['follow-up after a process revision'], ['action', 'measurement']),
        },
    },
    'AIQIF-C9.4': {  # Outcome Learning, UAT & Continuous Improvement
        'openness': MODERATE,
        'where': ('NAAC Criterion 6 (Governance, Leadership and Management): IQAC; NAAC Criterion 1 (Curricular '
                  'Aspects): feedback system; ABET Criterion 4 (Continuous Improvement)'),
        'dimensions': ['owner', 'coverage', 'measurement', 'result', 'action', 'continuity', 'scope'],
        'levels': ('A feedback process covers a digital or learning initiative, a register assigns owners to '
                   'resulting actions, and an acceptance or outcome review evaluates a deployed initiative.',
                   'Corrective actions are checked for completion, results of feedback-driven changes are evaluated, '
                   'and later initiatives demonstrably apply the lessons.'),
        'conditions': {
            'F1': (['feedback survey or user acceptance procedure'], ['coverage', 'scope']),
            'F2': (['action register with owners'], ['owner', 'action']),
            'A1': (['user acceptance or outcome review'], ['measurement', 'result']),
            'A2': (['corrective action closure record'], ['action', 'owner']),
            'O1': (['review of a feedback-driven change'], ['result', 'measurement']),
            'O2': (['later initiative citing the lesson'], ['action', 'continuity']),
        },
    },
    # ---- END OF SPEC
}


def _dimension(entry):
    if isinstance(entry, str):
        name, ask = DIMENSIONS[entry]
        return {'id': entry, 'name': name, 'ask': ask}
    dim_id, name, ask = entry
    return {'id': dim_id, 'name': name, 'ask': ask}


def build():
    """The JSON form of SPEC, checked against the rubric: every condition present, every dimension reference known."""
    rubric = json.loads((Path(__file__).parent / 'rubric_v0_3.json').read_text(encoding='utf-8'))
    indicators = {}
    problems = []
    for indicator in rubric['indicators']:
        code = indicator['code']
        entry = SPEC.get(code)
        if entry is None:
            problems.append(f'{code}: no depth entry')
            continue
        dims = [_dimension(d) for d in entry['dimensions']]
        known = {d['id'] for d in dims}
        if entry['openness'] not in QUESTIONS_PER_CONDITION:
            problems.append(f'{code}: unknown openness {entry["openness"]!r}')
        conditions = {}
        for condition in indicator['conditions']:
            suffix = condition['id'].rsplit('.', 1)[1]
            spec = entry['conditions'].get(suffix)
            if spec is None:
                problems.append(f'{condition["id"]}: no depth entry')
                continue
            forms, wanted = spec
            unknown = [d for d in wanted if d not in known]
            if unknown:
                problems.append(f'{condition["id"]}: dimensions {unknown} are not listed for {code}')
            conditions[condition['id']] = {'assertion': condition['text'], 'evidence_forms': list(forms),
                                           'dimensions': list(wanted)}
        substantiated, strong = entry['levels']
        indicators[code] = {'name': indicator['name'], 'openness': entry['openness'], 'where': entry['where'],
                            'dimensions': dims,
                            'levels': {'evidenced': 'The part judge credited the condition from the submitted documents.',
                                       'substantiated': substantiated, 'strong': strong},
                            'conditions': conditions}
    if problems:
        raise ValueError('depth spec does not match the rubric:\n' + '\n'.join(problems))
    return {'version': VERSION, 'rubric_version': RUBRIC, 'status': STATUS,
            'questions_per_condition': QUESTIONS_PER_CONDITION, 'indicators': indicators}


if __name__ == '__main__':
    out = Path(__file__).parent / 'depth_spec_v0.json'
    out.write_text(json.dumps(build(), indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f'wrote {out}')
