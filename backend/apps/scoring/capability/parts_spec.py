"""Source for rubric_parts_v1.json: each rubric condition split into the parts its assertion requires.

Each part is "full evidence || related evidence". Full evidence demonstrates the part as the assertion
states it. Related evidence is a real, exactly quotable passage that supports a weaker or adjacent
version of the part (digital rather than AI, planned rather than delivered, a stated recurring practice
without an identified instance, unclear scope). `not` lists near-misses that earn nothing for the
condition. Run `python -m apps.scoring.capability.parts_spec` to regenerate the JSON after editing.

The condition texts and their meaning are unchanged from AIQIF-CAP-0.3; this file only makes explicit
what each assertion already requires.
"""
import json
from pathlib import Path

VERSION = 'AIQIF-PARTS-1'
RUBRIC = 'AIQIF-CAP-0.3'

# Shared phrases.
AI = 'artificial intelligence or machine learning'
DIGITAL_FOR_AI = 'the same kind of record for a digital, IT or data service that is not AI'
PLANNED = 'the activity is planned, approved or announced but no delivery record is quoted'
RECURRING = 'a stated recurring practice (e.g. "every semester") without an identified, dated instance'

SPEC = {
    # ---- C1.1 Digital and AI Strategy Readiness
    'AIQIF-C1.1.F1': {
        'parts': [
            'An institutional plan that the institution has adopted exists: a named strategic, perspective, development, digital or AI plan that is approved, adopted, or stated to be deployed or implemented by the institution || a draft, proposal, vision or mission statement',
            'The plan names a digital, IT, e-governance, data or AI priority, goal or initiative || the plan names a general modernisation or infrastructure goal that includes technology only implicitly',
        ],
        'not': ['A mission statement alone', 'A list of completed ICT facilities that is not part of a plan'],
    },
    'AIQIF-C1.1.F2': {
        'parts': [
            'A digital, IT, e-governance, data or AI priority is identified (the priority from F1 or another stated one) || a general plan priority that includes technology only implicitly',
            'A named role, office, committee or person is assigned responsibility for that priority || a body is said to implement or monitor the plan in general, without linking it to the digital priority',
        ],
        'not': ['An organisation chart or list of committees with no stated responsibility for the priority'],
    },
    'AIQIF-C1.1.A1': {
        'parts': [
            f'An {AI} initiative is named or described || {DIGITAL_FOR_AI}',
            'A delivery record shows it operating (in use, deployed, running, delivered), not only planned || ' + PLANNED,
            'It operates in an identified institutional function or department || the function is implied but not named',
        ],
        'not': ['An AI course or student project (that is teaching, not an institutional initiative)',
                'Funding or incubation of an external startup'],
    },
    'AIQIF-C1.1.A2': {
        'parts': [
            f'A review covers a set (portfolio) of the institution\'s initiatives that includes an {AI} initiative || a review of digital or IT initiatives with no AI initiative',
            'The review records a decision (continue, expand, change, stop, fund) about that AI initiative || the review records findings or discussion without a decision',
        ],
        'not': ['A plan table of generic targets', 'A startup funding decision'],
    },
    'AIQIF-C1.1.O1': {
        'parts': [
            f'A completed portfolio review concerns an {AI} initiative || a completed review of a digital initiative that is not AI',
            'The review reports a measured result of the initiative || the review reports activity counts or qualitative impressions only',
            'The measured result is compared with the initiative\'s stated objective or target || an objective is stated elsewhere but not compared',
        ],
        'not': ['ICT or institutional KPIs that are not about an AI initiative'],
    },
    'AIQIF-C1.1.O2': {
        'parts': [
            f'A portfolio decision about an {AI} initiative is recorded || a decision about a digital initiative that is not AI',
            'A later record evaluates the effect of that decision with a stated result || a later record mentions the decision\'s implementation without evaluating its effect',
        ],
        'not': [],
    },
    # ---- C1.2 AI Governance & Accountability
    'AIQIF-C1.2.F1': {
        'parts': [
            'A named institutional body exists (council, board, committee, cell, IQAC) || a role or office rather than a body',
            'The passage states the body decides, approves or oversees a matter it identifies as digital, IT, data, e-governance or AI || the body has a general administrative or academic remit that could include digital matters',
        ],
        'not': ['A list of bodies or a reporting hierarchy without a digital matter'],
    },
    'AIQIF-C1.2.F2': {
        'parts': [
            'Digital, IT, data or AI decisions are identified as the subject || general decisions or grievances that are not about digital matters',
            'An escalation or referral route (who refers to whom, and to which higher body) is defined for those decisions || a general grievance or reporting route not specific to digital decisions',
        ],
        'not': ['An organogram alone'],
    },
    'AIQIF-C1.2.A1': {
        'parts': [
            'A governance body made a decision (resolution, approval, minute) || a body discussed or reviewed a matter without a recorded decision',
            'The decision is dated || the decision is undated or only the report date is available',
            f'The decision concerns an actual {AI} use || the decision concerns a digital or IT system that is not AI',
        ],
        'not': [],
    },
    'AIQIF-C1.2.A2': {
        'parts': [
            'A governance action is assigned to a named owner || an action is listed without an owner',
            'A follow-up record reports on that action (status, completion, outcome) || ' + RECURRING,
        ],
        'not': ['Corrective actions passed on to departments without a named owner and a follow-up record'],
    },
    'AIQIF-C1.2.O1': {
        'parts': [
            'A review evaluates how governance performed || a review of institutional performance in general',
            'The review uses an identified incident or delivery result as its basis || the review cites general outcomes without an identified incident or result',
        ],
        'not': [],
    },
    'AIQIF-C1.2.O2': {
        'parts': [
            'A governance rule was revised || a rule exists without a recorded revision',
            'A follow-up checks whether the revised rule was implemented || ' + RECURRING,
        ],
        'not': [],
    },
    # ---- C1.3 AI Investment & Resource Planning
    'AIQIF-C1.3.F1': {
        'parts': [
            'A resource commitment exists: allocated funds, budget, grant, expenditure or dedicated resources || a statement of support with no resource named',
            'The commitment supports computing, teaching or innovation capacity relevant to digital or AI work || the commitment supports facilities in general',
        ],
        'not': [],
    },
    'AIQIF-C1.3.F2': {
        'parts': [
            'An allocation decision is recorded (funds or resources allocated, earmarked, sanctioned or spent) || resources are mentioned without an allocation',
            'The allocation identifies its intended beneficiary group or function (e.g. students, faculty, a lab, an innovation centre) || the beneficiary is implied but not stated',
        ],
        'not': [],
    },
    'AIQIF-C1.3.A1': {
        'parts': [
            'A review examines committed resources || a budget or expenditure table without review',
            'The review compares them with an identified delivery need or demand || the need is stated separately but not compared',
        ],
        'not': [],
    },
    'AIQIF-C1.3.A2': {
        'parts': [
            'A capacity shortfall is documented (insufficient computers, lab space, bandwidth, staff, funding) || a general statement that facilities are being improved',
            'A resource decision responds to that shortfall || resources were added without stating they respond to the shortfall',
        ],
        'not': [],
    },
    'AIQIF-C1.3.O1': {
        'parts': [
            'A completed review states a resource cost || costs appear only in an expenditure table without a review',
            'The review reports a measured benefit or capacity result || benefits are described qualitatively',
            'Cost and result are compared || both appear but are not compared',
        ],
        'not': [],
    },
    'AIQIF-C1.3.O2': {
        'parts': [
            'A change in resource allocation is recorded || allocations differ across years without a recorded change decision',
            'A follow-up evaluates the effect of that change || the change is described without evaluation',
        ],
        'not': [],
    },
    # ---- C1.4 AI Adoption, Change & Institutional Alignment
    'AIQIF-C1.4.F1': {
        'parts': [
            'A process exists for introducing something: defined steps, a periodic assessment that decides additions, an approval route, or a role charged with introducing it || a single past introduction without a stated process',
            'What it introduces is a digital service or teaching tool (ERP module, LMS, e-content, ICT tool, online system) || the process concerns teaching or administrative changes in general',
        ],
        'not': ['A list of tools already in use'],
    },
    'AIQIF-C1.4.F2': {
        'parts': [
            'A digital service or teaching tool is identified || digital services in general',
            'Users are told whom to contact for help with it (helpdesk, named office, coordinator, support email) || a team maintains or repairs it, but the passage does not say users contact it',
        ],
        'not': ['A maintenance team or lab staff that the passage does not present as a user contact'],
    },
    'AIQIF-C1.4.A1': {
        'parts': [
            'Usage records (counts, logs, statistics, frequency) are quoted || use is asserted without records',
            'The use is repeated (several sessions, users or periods) || a single use',
            'The deployment scope is identified (programme, department, user group) || scope unclear',
        ],
        'not': [],
    },
    'AIQIF-C1.4.A2': {
        'parts': [
            'An adoption barrier is documented (users not using, lacking skills, access problems) || a general training need',
            'A support action responds to it (training, guide, help) || support is provided without linking to a barrier',
        ],
        'not': [],
    },
    'AIQIF-C1.4.O1': {
        'parts': [
            'A completed review measures adoption || adoption is asserted',
            'Adoption is compared with an explicit target || a target exists but is not compared',
        ],
        'not': ['Generic institutional KPIs not about adoption of the service or tool'],
    },
    'AIQIF-C1.4.O2': {
        'parts': [
            'An adoption or user-experience change is recorded || ' + PLANNED,
            'A follow-up evaluates its effect || the change is described without evaluation',
        ],
        'not': [],
    },
    # ---- C2.1 Responsible AI Policy & Principles
    'AIQIF-C2.1.F1': {
        'parts': [
            'Institutional guidance or policy is in effect (adopted, published, effective) || draft or proposed guidance',
            f'The guidance explicitly addresses {AI} use || guidance on IT use, academic integrity or ethics that does not mention AI',
        ],
        'not': ['A general code of conduct that does not mention AI'],
    },
    'AIQIF-C2.1.F2': {
        'parts': [
            f'Guidance concerning {AI} use exists || IT or academic integrity guidance that does not mention AI',
            'It defines a restriction on unsafe or inappropriate AI use (prohibited uses, limits, conditions) || it states principles without a restriction',
        ],
        'not': [],
    },
    'AIQIF-C2.1.A1': {
        'parts': [
            f'A deployment or onboarding check for an {AI} use is recorded || a check for a digital system that is not AI',
            'The check applies a requirement from the AI policy || the check applies general IT requirements',
        ],
        'not': [],
    },
    'AIQIF-C2.1.A2': {
        'parts': [
            'A review samples actual AI use || a review of policy compliance in general',
            'It records how a policy exception was handled || exceptions are mentioned without disposition',
        ],
        'not': [],
    },
    'AIQIF-C2.1.O1': {
        'parts': [
            'A policy review is completed || the policy is described',
            'It evaluates an identified AI incident or assurance finding || a general review without an incident or finding',
        ],
        'not': [],
    },
    'AIQIF-C2.1.O2': {
        'parts': [
            'A responsible-use control was revised || a control exists without revision',
            'A follow-up tests the effect of the revision || the revision is described without a test',
        ],
        'not': [],
    },
    # ---- C2.2 AI Risk, Privacy & Security Governance
    'AIQIF-C2.2.F1': {
        'parts': [
            'Personal or sensitive institutional data is identified (student records, personnel data, exam data) || data in general',
            'Responsibility for it is assigned to a named role, office or body || data is said to be handled securely without a responsible party',
        ],
        'not': [],
    },
    'AIQIF-C2.2.F2': {
        'parts': [
            'An information system is identified (ERP, exam system, LMS, network) || IT systems in general',
            'An access-control procedure covers it (role-based access, user accounts and permissions, authorisation steps) || security products or measures without an access procedure',
        ],
        'not': ['Firewalls, antivirus, CCTV, biometric attendance or general monitoring'],
    },
    'AIQIF-C2.2.A1': {
        'parts': [
            'A risk assessment is recorded || risks are mentioned in general',
            f'It covers an identified deployed {AI} use || it covers a digital system that is not AI',
        ],
        'not': [],
    },
    'AIQIF-C2.2.A2': {
        'parts': [
            'An access or supplier change is identified || changes in general',
            'A recorded risk decision responds to it || the change is described without a risk decision',
        ],
        'not': [],
    },
    'AIQIF-C2.2.O1': {
        'parts': [
            'A completed risk review reports exposure || risks are listed without measurement',
            'Exposure is compared with a stated risk criterion || a criterion exists but is not compared',
        ],
        'not': [],
    },
    'AIQIF-C2.2.O2': {
        'parts': [
            'A remediation was implemented || a remediation is planned',
            'A follow-up tests its effectiveness || the remediation is described without a test',
        ],
        'not': [],
    },
    # ---- C2.3 AI Model, Data & Lifecycle Governance
    'AIQIF-C2.3.F1': {
        'parts': [
            'An inventory, register or list of services in use is quoted || services are mentioned individually',
            f'The inventory identifies {AI} services || the inventory lists digital services that are not AI',
        ],
        'not': [],
    },
    'AIQIF-C2.3.F2': {
        'parts': [
            f'An inventory of {AI} services exists || an inventory of digital services',
            'Each inventoried service has a named owner || some services have owners or a general IT owner is named',
        ],
        'not': [],
    },
    'AIQIF-C2.3.A1': {
        'parts': [
            f'An actual {AI} service release or change is identified || a digital service change that is not AI',
            'An evaluation record concerns it (test results, acceptance, validation) || the release is described without evaluation',
        ],
        'not': [],
    },
    'AIQIF-C2.3.A2': {
        'parts': [
            f'A change record for an {AI} service exists || a change record for a digital service',
            'It identifies the data provenance (source of training or input data) || data is mentioned without its source',
        ],
        'not': [],
    },
    'AIQIF-C2.3.O1': {
        'parts': [
            f'An {AI} release is monitored in operation || monitoring of digital systems in general',
            'Operational behaviour is compared with a stated evaluation criterion || behaviour is described without a criterion',
        ],
        'not': [],
    },
    'AIQIF-C2.3.O2': {
        'parts': [
            f'A rollback or retirement exercise for an {AI} service took place || one for a digital service',
            'The observed result is recorded || the exercise is described without its result',
        ],
        'not': [],
    },
    # ---- C2.4 Human Oversight, Ethics & AI Assurance
    'AIQIF-C2.4.F1': {
        'parts': [
            f'A consequential {AI} use is identified (one that affects people\'s grades, admission, employment, health or rights) || an AI use without stated consequence',
            'A human intervention route (review, override, approval by a person) is defined for it || human review exists for decisions in general',
        ],
        'not': [],
    },
    'AIQIF-C2.4.F2': {
        'parts': [
            f'A consequential {AI} use is identified || an AI use without stated consequence',
            'Affected users have a route to report errors or appeal that use || a general grievance or appeal mechanism not linked to the AI use',
        ],
        'not': ['A general examination revaluation or grievance mechanism without an AI use'],
    },
    'AIQIF-C2.4.A1': {
        'parts': [
            f'An actual consequential {AI} use is identified || an AI use without stated consequence',
            'A record shows a person overseeing it (reviews, approvals, overrides) || oversight is stated as policy without a record',
        ],
        'not': [],
    },
    'AIQIF-C2.4.A2': {
        'parts': [
            f'An assurance test of a consequential {AI} use is recorded || testing of a digital system',
            'The test examines a specified failure or fairness risk || a general test',
        ],
        'not': [],
    },
    'AIQIF-C2.4.O1': {
        'parts': [
            'A reviewer separate from the delivery decision evaluates the AI use || a review by those who delivered it',
            'The evaluation concerns an identified harm or oversight result || a general evaluation',
        ],
        'not': [],
    },
    'AIQIF-C2.4.O2': {
        'parts': [
            'An oversight change was made || ' + PLANNED,
            'A follow-up tests its effect || the change is described without a test',
        ],
        'not': [],
    },
    # ---- C3.1 AI Curriculum Integration & Programme Design
    'AIQIF-C3.1.F1': {
        'parts': [
            'A governing body (Board of Studies, Academic Council) records approval of a syllabus or curriculum, naming the applicable edition or programme || the syllabus is presented as the institution\'s current syllabus without an approval record',
            f'That syllabus includes substantive {AI} content (course or units with AI/ML topics) || AI appears only in a course title or a single listed topic',
        ],
        'not': ['A committee roster or a procedure for future revisions'],
    },
    'AIQIF-C3.1.F2': {
        'parts': [
            f'A syllabus or course with {AI} content is identified || a course title alone',
            'An explicit learning objective or course outcome addresses that AI/ML content || outcomes are stated for the course but do not mention the AI content',
        ],
        'not': [],
    },
    'AIQIF-C3.1.A1': {
        'parts': [
            'Teaching records (timetables, attendance, delivery reports, course completion) are quoted || the course is listed as offered',
            f'The delivered content is substantive {AI} content || the delivered course is digital or computing without AI',
            'The programme group taught is identified || the group is implied',
        ],
        'not': [],
    },
    'AIQIF-C3.1.A2': {
        'parts': [
            'Assessed student work is recorded (marks, graded projects, exam results) || assessment is described in general',
            f'It is assessed against an explicit {AI} learning criterion || work in an AI course without a stated criterion',
        ],
        'not': [],
    },
    'AIQIF-C3.1.O1': {
        'parts': [
            f'A completed course review concerns {AI} learning || a general course or programme review',
            'Attainment is compared with a stated objective (outcome attainment against target) || attainment is reported without comparison',
        ],
        'not': ['Programme-wide pass percentages'],
    },
    'AIQIF-C3.1.O2': {
        'parts': [
            'A curriculum revision is recorded for AI content || a general syllabus revision',
            'A subsequent assessment evaluates its effect || the revision is described without evaluation',
        ],
        'not': [],
    },
    # ---- C3.2 AI Literacy Across Disciplines
    'AIQIF-C3.2.F1': {
        'parts': [
            f'A learning offer (course, module, value-added course, workshop series) is defined with its content || an offer is named without content',
            f'Its content is AI literacy (what {AI} is, how to use it, its limits) || digital or computer literacy without AI',
        ],
        'not': [],
    },
    'AIQIF-C3.2.F2': {
        'parts': [
            'An AI literacy offer is identified || a digital literacy offer',
            'A delivery route (elective, compulsory course, online platform, schedule) makes it available to an identified learner group || availability is implied',
        ],
        'not': [],
    },
    'AIQIF-C3.2.A1': {
        'parts': [
            'Delivery records (sessions held, participants, dates) are quoted || ' + PLANNED,
            'The activity is AI literacy || digital literacy without AI',
            'The discipline served is identified || discipline unclear',
        ],
        'not': [],
    },
    'AIQIF-C3.2.A2': {
        'parts': [
            'A discipline-specific access or learning gap is documented || a general need',
            'A support response addresses it || support is provided without linking it to the gap',
        ],
        'not': [],
    },
    'AIQIF-C3.2.O1': {
        'parts': [
            'An assessment reports AI literacy attainment || participation counts only',
            'It is for an identified discipline || discipline unclear',
        ],
        'not': [],
    },
    'AIQIF-C3.2.O2': {
        'parts': [
            'Targeted literacy support was provided || general support',
            'A follow-up assessment evaluates its effect || the support is described without evaluation',
        ],
        'not': [],
    },
    # ---- C3.3 AI-Enabled Pedagogy & Assessment
    'AIQIF-C3.3.F1': {
        'parts': [
            'A course design or teaching plan is identified || teaching practice in general',
            f'It specifies a learning or feedback activity supported by {AI} (AI tutor, AI feedback, AI tool in class) || an ICT-enabled activity without AI',
        ],
        'not': ['LMS, smart classrooms, online quizzes or videos without AI'],
    },
    'AIQIF-C3.3.F2': {
        'parts': [
            'An AI-supported learning activity is identified || an ICT activity',
            'Learner instructions define acceptable AI use for it || general academic integrity rules',
        ],
        'not': [],
    },
    'AIQIF-C3.3.A1': {
        'parts': [
            'Course records show the activity being used || the activity is described as available',
            'The use is repeated || a single use',
            'The activity is AI-supported || ICT-supported without AI',
        ],
        'not': [],
    },
    'AIQIF-C3.3.A2': {
        'parts': [
            'An assessment check is recorded || assessment in general',
            'It evaluates inappropriate dependence on AI in the activity || a general plagiarism check',
        ],
        'not': ['A plagiarism-detection tool used on theses'],
    },
    'AIQIF-C3.3.O1': {
        'parts': [
            'A completed evaluation reports learning or feedback results for the AI-supported activity || results for ICT-enabled teaching in general',
            'The results are compared with a stated baseline || no baseline',
        ],
        'not': [],
    },
    'AIQIF-C3.3.O2': {
        'parts': [
            'The AI-supported learning design was changed || ' + PLANNED,
            'A follow-up evaluates the effect of the change || described without evaluation',
        ],
        'not': [],
    },
    # ---- C3.4 Experiential, Project & Applied AI Learning
    'AIQIF-C3.4.F1': {
        'parts': [
            'A student project or laboratory route exists (project course, lab, capstone, internship project) || projects in general',
            f'It includes substantive {AI} work || computing work without AI',
        ],
        'not': [],
    },
    'AIQIF-C3.4.F2': {
        'parts': [
            'Student AI project or lab work is identified || student projects in general',
            'A mentoring route (assigned mentor, guide, supervisor) is provided for it || mentoring for students in general',
        ],
        'not': [],
    },
    'AIQIF-C3.4.A1': {
        'parts': [
            'Assessed project work is recorded || projects listed without assessment',
            f'The work implements an {AI} application || a non-AI application',
            'The student group is identified || group unclear',
        ],
        'not': [],
    },
    'AIQIF-C3.4.A2': {
        'parts': [
            'A moderation record exists for the AI project work || project assessment in general',
            'It checks each student\'s individual contribution || group grading only',
        ],
        'not': [],
    },
    'AIQIF-C3.4.O1': {
        'parts': [
            'A completed review of AI project work exists || project outcomes are listed',
            'Work is evaluated against an explicit capability criterion || evaluation without a criterion',
        ],
        'not': [],
    },
    'AIQIF-C3.4.O2': {
        'parts': [
            'A mentoring or design change is recorded || ' + PLANNED,
            'Later work is evaluated against a comparable criterion || later work is described without evaluation',
        ],
        'not': [],
    },
    # ---- C4.1 Faculty AI Literacy & Awareness
    'AIQIF-C4.1.F1': {
        'parts': [
            'A faculty learning activity (FDP, workshop, training, course) is identified || faculty training in general',
            f'It is focused on {AI} || ICT, e-content or pedagogy without AI',
            'Its content is defined (topics, modules, agenda) || only the title is given',
        ],
        'not': [],
    },
    'AIQIF-C4.1.F2': {
        'parts': [
            'An AI-focused learning activity is identified || ICT or pedagogy training',
            'Participation is documented (names, counts, certificates) for an identified faculty group || participation is asserted',
        ],
        'not': [],
    },
    'AIQIF-C4.1.A1': {
        'parts': [
            'An assessment of faculty is recorded (test, evaluation, certification) || attendance only',
            'It demonstrates AI literacy || ICT skills',
            'The faculty group is identified || unclear',
        ],
        'not': [],
    },
    'AIQIF-C4.1.A2': {
        'parts': [
            'A faculty AI literacy gap is documented || a general training need',
            'A support response addresses it || training without linking to the gap',
        ],
        'not': [],
    },
    'AIQIF-C4.1.O1': {
        'parts': [
            'A completed assessment measures faculty AI literacy || participation counts',
            'It is compared with a stated competency criterion || no criterion',
        ],
        'not': [],
    },
    'AIQIF-C4.1.O2': {
        'parts': [
            'A faculty AI learning activity was revised || ' + PLANNED,
            'A follow-up assessment evaluates the effect || described without evaluation',
        ],
        'not': [],
    },
    # ---- C4.2 Role-Based Faculty AI Capability
    'AIQIF-C4.2.F1': {
        'parts': [
            'A faculty AI learning offer exists || faculty ICT training',
            'It targets an identified academic role (e.g. examiners, researchers, course designers) || all faculty in general',
        ],
        'not': [],
    },
    'AIQIF-C4.2.F2': {
        'parts': [
            'A practice task is part of the offer (hands-on exercise, assignment) || lectures only',
            'The task develops a specific AI-related academic skill for the role || a general ICT skill',
        ],
        'not': [],
    },
    'AIQIF-C4.2.A1': {
        'parts': [
            'An assessed role-relevant task is recorded || a task without assessment',
            'It demonstrates a faculty AI skill || a general ICT skill',
        ],
        'not': [],
    },
    'AIQIF-C4.2.A2': {
        'parts': [
            'A role-specific faculty AI skill gap is documented || a general need',
            'A support action addresses it || support without linking to the gap',
        ],
        'not': [],
    },
    'AIQIF-C4.2.O1': {
        'parts': [
            'An academic work sample (paper, course material, assessment) is identified || work in general',
            'It demonstrates application of the assessed AI skill || AI is mentioned without showing application',
        ],
        'not': [],
    },
    'AIQIF-C4.2.O2': {
        'parts': [
            'A role pathway was revised || ' + PLANNED,
            'A subsequent task evaluation tests the effect || described without evaluation',
        ],
        'not': [],
    },
    # ---- C4.3 AI-Enabled Teaching, Research & Academic Practice
    'AIQIF-C4.3.F1': {
        'parts': [
            'A faculty work record (research output, teaching material, project report) is quoted || faculty activity in general',
            f'It shows {AI} used in an academic task || AI as a research topic without its use as a tool, or digital tools without AI',
        ],
        'not': [],
    },
    'AIQIF-C4.3.F2': {
        'parts': [
            'An AI-supported faculty task is identified || an ICT-supported task',
            'A human review step is defined for it || review of academic work in general',
        ],
        'not': [],
    },
    'AIQIF-C4.3.A1': {
        'parts': [
            'Work samples show AI use || a single mention',
            'The use is repeated in an identified faculty practice || repetition or practice unclear',
        ],
        'not': [],
    },
    'AIQIF-C4.3.A2': {
        'parts': [
            'A quality check is recorded || quality assurance in general',
            'It evaluates AI-supported academic work || it evaluates work in general',
        ],
        'not': [],
    },
    'AIQIF-C4.3.O1': {
        'parts': [
            'A completed evaluation reports an academic quality, time or research result of AI use || results in general',
            'It is compared with a stated baseline || no baseline',
        ],
        'not': [],
    },
    'AIQIF-C4.3.O2': {
        'parts': [
            'An identified failure in AI-supported practice is recorded || problems in general',
            'A practice change responding to it is evaluated || the change is described without evaluation',
        ],
        'not': [],
    },
    # ---- C4.4 Staff AI Capability, FDP & Change Enablement
    'AIQIF-C4.4.F1': {
        'parts': [
            'A digital, workflow or AI learning offer exists (training, workshop) || training in general',
            'It targets an identified non-teaching staff role (administrative, technical, library, office staff) || staff in general including faculty',
        ],
        'not': [],
    },
    'AIQIF-C4.4.F2': {
        'parts': [
            'Staff digital or AI learning is identified || general training',
            'A support route is available to staff applying it (helpdesk, mentor, coordinator) || general staff welfare',
        ],
        'not': [],
    },
    'AIQIF-C4.4.A1': {
        'parts': [
            'An assessed task for an identified staff role is recorded || training attendance',
            'It demonstrates a relevant digital or AI skill || a general skill',
        ],
        'not': [],
    },
    'AIQIF-C4.4.A2': {
        'parts': [
            'A staff workflow error is documented || problems in general',
            'A support action addresses it || support without linking to the error',
        ],
        'not': [],
    },
    'AIQIF-C4.4.O1': {
        'parts': [
            'A completed evaluation measures staff task performance || attendance or satisfaction',
            'It is compared with a stated role criterion || no criterion',
        ],
        'not': [],
    },
    'AIQIF-C4.4.O2': {
        'parts': [
            'A staff training or support change is recorded || ' + PLANNED,
            'A follow-up evaluates its effect || described without evaluation',
        ],
        'not': [],
    },
    # ---- C5.1 Student AI Literacy Provision and Attainment
    'AIQIF-C5.1.F1': {
        'parts': [
            f'An {AI} literacy offer exists (course, module, value-added course, workshop) || a digital or computer literacy offer',
            'It is accessible to an identified student group || availability unclear',
        ],
        'not': [],
    },
    'AIQIF-C5.1.F2': {
        'parts': [
            'A student AI literacy offer is identified || a digital literacy offer',
            'A learning objective defines what it intends students to learn || content is listed without an objective',
        ],
        'not': [],
    },
    'AIQIF-C5.1.A1': {
        'parts': [
            'Delivery records for an AI literacy offer are quoted || ' + PLANNED,
            'The student cohort is identified || cohort unclear',
        ],
        'not': [],
    },
    'AIQIF-C5.1.A2': {
        'parts': [
            'A participation or attainment gap is documented || a general need',
            'A support response addresses it || support without linking to the gap',
        ],
        'not': [],
    },
    'AIQIF-C5.1.O1': {
        'parts': [
            'An assessment reports student AI literacy attainment || participation counts',
            'It is measured against an explicit criterion || no criterion',
        ],
        'not': [],
    },
    'AIQIF-C5.1.O2': {
        'parts': [
            'A change addressing an access or learning gap is recorded || ' + PLANNED,
            'A follow-up evaluates its effect || described without evaluation',
        ],
        'not': [],
    },
    # ---- C5.2 Advanced & Role-Specific AI Skills
    'AIQIF-C5.2.F1': {
        'parts': [
            f'An advanced {AI} skills pathway is defined (specialisation, programme, minor, track, sequence of courses) || a single AI course',
            'It is for an identified student group || unclear',
        ],
        'not': [],
    },
    'AIQIF-C5.2.F2': {
        'parts': [
            'An advanced AI/ML pathway is identified || a single course',
            'It includes a practical assessment task (lab exam, project, practical) || theory assessment only',
        ],
        'not': [],
    },
    'AIQIF-C5.2.A1': {
        'parts': [
            'Student work shows an advanced or role-specific AI skill || work in an AI course without described skill',
            'It is judged against an explicit criterion || no criterion',
        ],
        'not': [],
    },
    'AIQIF-C5.2.A2': {
        'parts': [
            'Employer or disciplinary feedback about the pathway is identified || general feedback',
            'A delivery change responds to it || a change without linking to the feedback',
        ],
        'not': [],
    },
    'AIQIF-C5.2.O1': {
        'parts': [
            'A completed review of the AI pathway exists || pathway results are listed',
            'It evaluates a relevant skill or progression result || general outcomes',
        ],
        'not': [],
    },
    'AIQIF-C5.2.O2': {
        'parts': [
            'The pathway was revised || ' + PLANNED,
            'A subsequent task evaluation tests the effect || described without evaluation',
        ],
        'not': [],
    },
    # ---- C5.3 Student AI Projects, Portfolio & Practice
    'AIQIF-C5.3.F1': {
        'parts': [
            f'An {AI} project or portfolio opportunity exists for students || a project opportunity without AI',
            'It is available to an identified student group || unclear',
        ],
        'not': [],
    },
    'AIQIF-C5.3.F2': {
        'parts': [
            'A student AI project or portfolio is identified || student projects in general',
            'An evaluation criterion addresses individual contribution || group evaluation only',
        ],
        'not': [],
    },
    'AIQIF-C5.3.A1': {
        'parts': [
            'A reviewed student portfolio or project record is quoted || projects listed',
            'It identifies the student\'s substantive AI contribution || AI project without the student\'s role',
        ],
        'not': [],
    },
    'AIQIF-C5.3.A2': {
        'parts': [
            'A moderation record exists || assessment in general',
            'It evaluates a participating student\'s AI project or portfolio || a non-AI project',
        ],
        'not': [],
    },
    'AIQIF-C5.3.O1': {
        'parts': [
            'A completed evaluation of AI work quality or real-user value exists || project outcomes listed',
            'It uses an explicit criterion || no criterion',
        ],
        'not': [],
    },
    'AIQIF-C5.3.O2': {
        'parts': [
            'A project or mentoring change is recorded || ' + PLANNED,
            'A follow-up evaluates its effect || described without evaluation',
        ],
        'not': [],
    },
    # ---- C5.4 AI Employability, Internships & Career Outcomes
    'AIQIF-C5.4.F1': {
        'parts': [
            'An internship or career opportunity is documented || career services in general',
            f'It is AI-relevant ({AI} role, project or employer activity) || an IT or computing opportunity without AI',
        ],
        'not': [],
    },
    'AIQIF-C5.4.F2': {
        'parts': [
            'An AI-relevant opportunity is identified || an IT opportunity',
            'An eligibility rule says who can access it || availability in general',
        ],
        'not': [],
    },
    'AIQIF-C5.4.A1': {
        'parts': [
            'A verified record of participation (named students, offer letters, certificates) || counts without verification',
            'The internship or opportunity is AI-relevant || IT without AI',
        ],
        'not': [],
    },
    'AIQIF-C5.4.A2': {
        'parts': [
            'A cohort register gives the denominator (total eligible or enrolled students) || a total without the cohort',
            'It is used to interpret AI-related participation or progression || used for general placement statistics',
        ],
        'not': [],
    },
    'AIQIF-C5.4.O1': {
        'parts': [
            'A completed review reports a verified AI-related career result || general placement results',
            'It is compared with a stated target || no target',
        ],
        'not': [],
    },
    'AIQIF-C5.4.O2': {
        'parts': [
            'A career-pathway change is recorded || ' + PLANNED,
            'A follow-up evaluates its effect || described without evaluation',
        ],
        'not': [],
    },
    # ---- C6.1 Computing Provision and AI Workload Suitability
    'AIQIF-C6.1.F1': {
        'parts': [
            'Computing resources are described (computers, labs, servers, cloud, software, internet) || facilities in general',
            'Learners or researchers are stated to have access to them || resources are listed without stating who uses them',
        ],
        'not': [],
    },
    'AIQIF-C6.1.F2': {
        'parts': [
            'Resource specifications are quoted (processors, memory, GPUs, bandwidth, software) || resources described without specifications',
            f'An introductory {AI} workload is explicitly stated (e.g. training small ML models in a named course) || AI courses exist without a stated workload',
            'The passages link the specifications to that workload || both appear but are not linked',
        ],
        'not': ['An inventory and a syllabus excerpt that are not linked'],
    },
    'AIQIF-C6.1.A1': {
        'parts': [
            'Usage records of computing capacity are quoted (hours, users, logs) || availability statements',
            'The user group served is identified and relevant to digital or AI work || users in general',
        ],
        'not': [],
    },
    'AIQIF-C6.1.A2': {
        'parts': [
            'A capacity or access failure is documented || general improvement',
            'A support response addresses it || an upgrade without linking to the failure',
        ],
        'not': [],
    },
    'AIQIF-C6.1.O1': {
        'parts': [
            'A completed review reports service performance (uptime, availability, utilisation) || descriptions without measures',
            'It is compared with a stated capacity or availability target || no target',
        ],
        'not': [],
    },
    'AIQIF-C6.1.O2': {
        'parts': [
            'A continuity or recovery exercise for the computing environment took place || backup is described',
            'Recovery performance is recorded || the exercise is described without results',
        ],
        'not': [],
    },
    # ---- C6.2 Institutional Data Readiness
    'AIQIF-C6.2.F1': {
        'parts': [
            'A register, catalogue or list identifies institutional datasets or information systems || systems mentioned individually',
            'The identified assets are relevant (student, academic, administrative, research data or systems) || unclear relevance',
        ],
        'not': [],
    },
    'AIQIF-C6.2.F2': {
        'parts': [
            'Institutional datasets or systems are identified || data in general',
            'A responsible custodian is assigned to them || systems are said to be managed without a responsible party',
        ],
        'not': [],
    },
    'AIQIF-C6.2.A1': {
        'parts': [
            'A data-quality check operates || data is said to be accurate',
            'It is for an identified AI use or AI preparation activity || for a digital system without AI',
        ],
        'not': [],
    },
    'AIQIF-C6.2.A2': {
        'parts': [
            'A data-quality issue is tracked || errors in general',
            'Its disposition is recorded || the issue is described without disposition',
        ],
        'not': [],
    },
    'AIQIF-C6.2.O1': {
        'parts': [
            'A completed review measures data quality || descriptions',
            'It is compared with a stated fitness criterion || no criterion',
        ],
        'not': [],
    },
    'AIQIF-C6.2.O2': {
        'parts': [
            'A data-quality change is recorded || ' + PLANNED,
            'A follow-up measures its effect on downstream work || described without measurement',
        ],
        'not': [],
    },
    # ---- C6.3 AI Cybersecurity & Resilience
    'AIQIF-C6.3.F1': {
        'parts': [
            'The computing environment is identified (network, servers, labs, systems) || IT in general',
            'Responsibility for its security is assigned to a named role, office or body || security measures without a responsible party',
        ],
        'not': ['Security products or firewall upgrades alone'],
    },
    'AIQIF-C6.3.F2': {
        'parts': [
            'The computing environment is identified || IT in general',
            'A recovery procedure covers it (backup and restore, disaster recovery steps) || backups are mentioned without a procedure',
        ],
        'not': [],
    },
    'AIQIF-C6.3.A1': {
        'parts': [
            'A security test was carried out in the assessed environment || security tools in use',
            'It examines an identified AI-related threat || a general threat',
        ],
        'not': [],
    },
    'AIQIF-C6.3.A2': {
        'parts': [
            'An incident or exercise is recorded || security in general',
            'A response action is recorded || the incident without a response',
        ],
        'not': [],
    },
    'AIQIF-C6.3.O1': {
        'parts': [
            'A completed security review reports remediation or recovery performance || descriptions',
            'It is compared with a stated criterion || no criterion',
        ],
        'not': [],
    },
    'AIQIF-C6.3.O2': {
        'parts': [
            'A control change responds to a documented threat || a control change without a threat',
            'A follow-up test evaluates it || described without a test',
        ],
        'not': [],
    },
    # ---- C6.4 AI Labs, Digital Learning Environment & Accessibility
    'AIQIF-C6.4.F1': {
        'parts': [
            'A learning environment is identified (lab, platform, software environment) || facilities in general',
            f'It supports a specified introductory {AI} learning activity || it supports computing or ICT learning without AI',
        ],
        'not': [],
    },
    'AIQIF-C6.4.F2': {
        'parts': [
            'An AI learning environment is identified || a general computing environment',
            'Learners have a defined access route (lab hours, login, booking, remote access) || access implied',
        ],
        'not': [],
    },
    'AIQIF-C6.4.A1': {
        'parts': [
            'Usage records show learner access || availability statements',
            'The environment is an AI learning environment || a general computing lab',
        ],
        'not': [],
    },
    'AIQIF-C6.4.A2': {
        'parts': [
            'An accessibility or capacity issue is documented || general improvements',
            'A support response addresses it || support without linking to the issue',
        ],
        'not': [],
    },
    'AIQIF-C6.4.O1': {
        'parts': [
            'A completed review reports learner access || descriptions',
            'It is compared with a stated service or equity criterion || no criterion',
        ],
        'not': [],
    },
    'AIQIF-C6.4.O2': {
        'parts': [
            'An environment improvement is recorded || ' + PLANNED,
            'A follow-up evaluates its effect || described without evaluation',
        ],
        'not': [],
    },
    # ---- C7.1 AI Research Capability & Agenda
    'AIQIF-C7.1.F1': {
        'parts': [
            f'An {AI} research or applied-inquiry project is named || research in a field without AI',
            'It has a defined objective (its title or description can state what it develops and for what purpose) || the topic is named without purpose',
        ],
        'not': [],
    },
    'AIQIF-C7.1.F2': {
        'parts': [
            'An AI research project is identified || research in general',
            'A responsible lead (principal investigator, named faculty or student lead) is assigned || the department is named',
        ],
        'not': [],
    },
    'AIQIF-C7.1.A1': {
        'parts': [
            'An AI research project is active in the period || project completed long before or only proposed',
            'A reviewed work output exists (publication, patent, prototype, report reviewed by others) || an output without review',
        ],
        'not': [],
    },
    'AIQIF-C7.1.A2': {
        'parts': [
            'A progress review of the AI project is recorded || progress is described',
            'It records a decision about the project || review without decision',
        ],
        'not': [],
    },
    'AIQIF-C7.1.O1': {
        'parts': [
            'A completed review evaluates output quality or application || outputs listed',
            'It is evaluated against the stated objective || no objective comparison',
        ],
        'not': [],
    },
    'AIQIF-C7.1.O2': {
        'parts': [
            'An agenda or resource change is recorded || ' + PLANNED,
            'A follow-up evaluates its effect || described without evaluation',
        ],
        'not': [],
    },
    # ---- C7.2 AI Innovation and Mentoring Support
    'AIQIF-C7.2.F1': {
        'parts': [
            'An innovation function exists (centre, cell, incubator, distributed function) || innovation activities in general',
            'Its remit is defined (focus areas, purpose) and includes AI or digital innovation || the remit is stated without AI or digital areas',
        ],
        'not': [],
    },
    'AIQIF-C7.2.F2': {
        'parts': [
            'An innovation function is identified || innovation in general',
            'A project or mentoring service is available through it || the function exists without a stated service',
        ],
        'not': [],
    },
    'AIQIF-C7.2.A1': {
        'parts': [
            'A service record shows a project or mentoring engagement through the function (named project, mentor assignment) || services described as available',
            f'The engagement concerns {AI} || a non-AI project',
        ],
        'not': [],
    },
    'AIQIF-C7.2.A2': {
        'parts': [
            'A service review is recorded || service described',
            'It records a decision responding to use or delivery evidence || review without decision',
        ],
        'not': [],
    },
    'AIQIF-C7.2.O1': {
        'parts': [
            'A completed review evaluates an output or institutional benefit of the function || outputs listed',
            'It is evaluated against the function\'s objective || no comparison',
        ],
        'not': [],
    },
    'AIQIF-C7.2.O2': {
        'parts': [
            'A service change is recorded || ' + PLANNED,
            'A follow-up evaluates its effect || described without evaluation',
        ],
        'not': [],
    },
    # ---- C7.3 AI Funding, IP & Entrepreneurship
    'AIQIF-C7.3.F1': {
        'parts': [
            'A funding, IP or incubation support route exists (seed fund, grant scheme, IPR cell, incubator) || support described in general',
            'It is available to eligible projects (eligibility or who can apply is stated or evident) || availability implied',
        ],
        'not': [],
    },
    'AIQIF-C7.3.F2': {
        'parts': [
            'A funding, IP or incubation support route is identified || support in general',
            'A contact or application route enables access (apply to, pitch event, submission process, named contact) || availability without a route',
        ],
        'not': [],
    },
    'AIQIF-C7.3.A1': {
        'parts': [
            'A named project is recorded || projects in general',
            'The project used a funding, IP or incubation support route || support available without a project using it',
            'The project concerns AI || a non-AI project',
        ],
        'not': [],
    },
    'AIQIF-C7.3.A2': {
        'parts': [
            'A review records a funding or translation decision (selected, funded, patent filed) || a review without decision',
            'The decision concerns an identified AI project || a non-AI project',
        ],
        'not': [],
    },
    'AIQIF-C7.3.O1': {
        'parts': [
            'A completed review evaluates verified project progression || progress described',
            'It is against a stated milestone || no milestone',
        ],
        'not': [],
    },
    'AIQIF-C7.3.O2': {
        'parts': [
            'A project-support change is recorded || ' + PLANNED,
            'A follow-up evaluates its effect || described without evaluation',
        ],
        'not': [],
    },
    # ---- C7.4 AI Collaboration, Knowledge Transfer & Societal Impact
    'AIQIF-C7.4.F1': {
        'parts': [
            'A collaboration work plan exists (MoU activities, joint project plan) || an agreement without planned work',
            f'It specifies substantive {AI} research or application || collaboration in a non-AI area',
        ],
        'not': ['An MoU listing alone'],
    },
    'AIQIF-C7.4.F2': {
        'parts': [
            'Planned AI collaboration work is identified || collaboration in general',
            'A partner responsibility is assigned for it || partner named without responsibility',
        ],
        'not': [],
    },
    'AIQIF-C7.4.A1': {
        'parts': [
            'A delivery record shows collaboration work carried out || an agreement only',
            'The work is substantive AI work || non-AI work',
        ],
        'not': [],
    },
    'AIQIF-C7.4.A2': {
        'parts': [
            'Partner or beneficiary feedback is recorded || feedback in general',
            'It evaluates an identified delivered AI contribution || a general contribution',
        ],
        'not': [],
    },
    'AIQIF-C7.4.O1': {
        'parts': [
            'A completed review evaluates knowledge transfer or a beneficiary result || results listed',
            'It is against a stated objective || no comparison',
        ],
        'not': [],
    },
    'AIQIF-C7.4.O2': {
        'parts': [
            'A collaboration change is recorded || ' + PLANNED,
            'A follow-up evaluates its effect || described without evaluation',
        ],
        'not': [],
    },
    # ---- C8.1 Digital Services and AI-Enabled Operations
    'AIQIF-C8.1.F1': {
        'parts': [
            'An institutional digital service is identified (ERP, e-governance module, online admission, exam system, grievance portal) || digital tools in general',
            'Its purpose is defined (what it does or which operation it serves) || named without purpose',
        ],
        'not': [],
    },
    'AIQIF-C8.1.F2': {
        'parts': [
            'An institutional digital service is identified || digital tools in general',
            'A responsible owner (office, role, body) is assigned to it || the service is said to be maintained without a responsible party',
        ],
        'not': [],
    },
    'AIQIF-C8.1.A1': {
        'parts': [
            'Operational records of an institutional service are quoted || the service is described',
            f'They show {AI} used in that service || digital automation without AI',
            'The use is repeated || a single use',
        ],
        'not': [],
    },
    'AIQIF-C8.1.A2': {
        'parts': [
            'A monitoring record exists for the service || monitoring in general',
            'It evaluates an AI-related exception || a general exception',
        ],
        'not': [],
    },
    'AIQIF-C8.1.O1': {
        'parts': [
            'A completed evaluation reports service benefit || benefits described',
            'It is compared with a stated baseline || no baseline',
            'It discloses quality limitations || no limitations stated',
        ],
        'not': [],
    },
    'AIQIF-C8.1.O2': {
        'parts': [
            'A workflow or control change is recorded || ' + PLANNED,
            'A follow-up tests its effect || described without a test',
        ],
        'not': [],
    },
    # ---- C8.2 Industry Integration & AI Partnerships
    'AIQIF-C8.2.F1': {
        'parts': [
            'An industry work plan exists (planned activities with an industry partner) || an MoU listing without planned activities',
            'It specifies an AI-related activity || a non-AI activity',
        ],
        'not': [],
    },
    'AIQIF-C8.2.F2': {
        'parts': [
            'An AI-related industry activity is identified || industry activity in general',
            'It defines a contribution to skills, curriculum or projects || purpose unstated',
        ],
        'not': [],
    },
    'AIQIF-C8.2.A1': {
        'parts': [
            'A delivery record shows the activity carried out with an industry partner || agreement only',
            'The activity is AI-related || non-AI',
        ],
        'not': [],
    },
    'AIQIF-C8.2.A2': {
        'parts': [
            'A review of the partner\'s delivered contribution is recorded || contribution listed',
            'The contribution concerns AI skills, projects or opportunities || non-AI',
        ],
        'not': [],
    },
    'AIQIF-C8.2.O1': {
        'parts': [
            'A completed partnership review evaluates an output or outcome || results listed',
            'It is against a stated objective || no comparison',
        ],
        'not': [],
    },
    'AIQIF-C8.2.O2': {
        'parts': [
            'A jointly agreed delivery change is recorded || ' + PLANNED,
            'A follow-up evaluates its effect || described without evaluation',
        ],
        'not': [],
    },
    # ---- C8.3 AI Entrepreneurship, Placement & Workforce Outcomes
    'AIQIF-C8.3.F1': {
        'parts': [
            'An employment, enterprise or workforce pathway exists (placement programme, incubation, training-to-employment route) || career support in general',
            'It explicitly addresses AI skills || general employability skills',
        ],
        'not': [],
    },
    'AIQIF-C8.3.F2': {
        'parts': [
            'An AI-skills pathway is identified || a general pathway',
            'An opportunity or referral route connects eligible participants to it || availability in general',
        ],
        'not': [],
    },
    'AIQIF-C8.3.A1': {
        'parts': [
            'A verified record names a participant or venture || counts only',
            'It links them to an opportunity or venture through an AI pathway (e.g. an AI venture supported, an AI placement) || a non-AI venture or placement',
        ],
        'not': [],
    },
    'AIQIF-C8.3.A2': {
        'parts': [
            'A review examines pathway participation || participation counts',
            'It relates participation to an observed result || results reported separately',
        ],
        'not': [],
    },
    'AIQIF-C8.3.O1': {
        'parts': [
            'A completed review evaluates a verified progression or enterprise result || results listed',
            'It is against a stated objective || no comparison',
        ],
        'not': [],
    },
    'AIQIF-C8.3.O2': {
        'parts': [
            'A pathway portfolio change is recorded || ' + PLANNED,
            'A follow-up evaluates its effect || described without evaluation',
        ],
        'not': [],
    },
    # ---- C8.4 Measured AI Business/Educational Outcomes
    'AIQIF-C8.4.F1': {
        'parts': [
            f'An identified {AI} intervention is named || a digital intervention without AI',
            'It has an explicit intended outcome || purpose implied',
        ],
        'not': [],
    },
    'AIQIF-C8.4.F2': {
        'parts': [
            'An AI intervention outcome is identified || outcomes in general',
            'A prospective measurement method is defined for it || measured after the fact without a defined method',
        ],
        'not': [],
    },
    'AIQIF-C8.4.A1': {
        'parts': [
            'Recorded results of an AI intervention are quoted || results of a non-AI intervention',
            'They are compared with a stated baseline || no baseline',
            'The method is disclosed || method unstated',
        ],
        'not': [],
    },
    'AIQIF-C8.4.A2': {
        'parts': [
            'A review of an AI intervention\'s results is recorded || results only',
            'It examines an alternative explanation or potential harm || no such examination',
        ],
        'not': [],
    },
    'AIQIF-C8.4.O1': {
        'parts': [
            'A completed measurement review evaluates benefit of an AI intervention || benefits described',
            'It states its limitations explicitly || no limitations',
        ],
        'not': [],
    },
    'AIQIF-C8.4.O2': {
        'parts': [
            'An intervention change is recorded || ' + PLANNED,
            'A subsequent measurement evaluates its effect || described without measurement',
        ],
        'not': [],
    },
    # ---- C9.1 Institutional Measurement and Readiness Review
    'AIQIF-C9.1.F1': {
        'parts': [
            'An institutional review process exists (academic audit, IQAC review, quality audit) || reviews mentioned in general',
            'It uses defined indicators (criteria, questionnaire items, metrics) || indicators implied',
        ],
        'not': [],
    },
    'AIQIF-C9.1.F2': {
        'parts': [
            'An indicator-based institutional review is identified || reviews in general',
            'Responsibility for producing it is assigned (IQAC, named office or committee) || a body participates without stated responsibility',
        ],
        'not': [],
    },
    'AIQIF-C9.1.A1': {
        'parts': [
            'An institutional assessment is repeated (more than one cycle) || a single assessment',
            'It uses traceable evidence with reproducible calculations || evidence without traceability',
        ],
        'not': ['This assessment software itself'],
    },
    'AIQIF-C9.1.A2': {
        'parts': [
            'A change record for the assessment exists || changes in general',
            'It distinguishes evidence changes from methodology changes || no distinction',
        ],
        'not': [],
    },
    'AIQIF-C9.1.O1': {
        'parts': [
            'A completed review uses the assessment\'s results || results reported',
            'It evaluates an improvement priority || no priority',
        ],
        'not': [],
    },
    'AIQIF-C9.1.O2': {
        'parts': [
            'A measurement-method revision is recorded || ' + PLANNED,
            'A follow-up evaluates its effect || described without evaluation',
        ],
        'not': [],
    },
    # ---- C9.2 Evidence, Traceability & Auditability
    'AIQIF-C9.2.F1': {
        'parts': [
            'An evidence index identifies source records used for assessment (document list, evidence register) || documents uploaded without an index',
            'It is used for an assessment || an index for other purposes',
        ],
        'not': ['"View Document" links alone'],
    },
    'AIQIF-C9.2.F2': {
        'parts': [
            'Assessment source records are identified || records in general',
            'A custodian is assigned to preserve them || records are said to be maintained without a custodian',
        ],
        'not': [],
    },
    'AIQIF-C9.2.A1': {
        'parts': [
            'A sampled assessment finding is identified || findings in general',
            'It is traced to its requirement and source passage || traceability claimed without a trace',
        ],
        'not': [],
    },
    'AIQIF-C9.2.A2': {
        'parts': [
            'A record shows an evidence value before and after a correction || a corrected value only',
            'It states a remark or reason for the change || the change without reason',
        ],
        'not': [],
    },
    'AIQIF-C9.2.O1': {
        'parts': [
            'A completed audit evaluates traceability || audits in general',
            'It follows an explicit checking procedure || procedure unstated',
        ],
        'not': [],
    },
    'AIQIF-C9.2.O2': {
        'parts': [
            'An evidence-process improvement is recorded || ' + PLANNED,
            'A follow-up measures its effect || described without measurement',
        ],
        'not': [],
    },
    # ---- C9.3 Benchmark Evolution & AI Readiness Drift
    'AIQIF-C9.3.F1': {
        'parts': [
            'A process exists that monitors changes (stakeholder feedback, regulatory updates, industry or technology trends) || changes happen without a monitoring process',
            'The monitored changes are relevant accreditation, curriculum or technology changes || general monitoring',
        ],
        'not': [],
    },
    'AIQIF-C9.3.F2': {
        'parts': [
            'A body or process that considers such changes is identified || changes in general',
            'A review schedule defines when changes are considered (meeting frequency, review cycle) || "as needed" without a schedule',
        ],
        'not': [],
    },
    'AIQIF-C9.3.A1': {
        'parts': [
            'A change review is recorded || changes made',
            'It identifies a requirement affected by an external change || general revision',
        ],
        'not': [],
    },
    'AIQIF-C9.3.A2': {
        'parts': [
            'A versioned reassessment is recorded || a single assessment',
            'It preserves the prior result with an explanation of the change || only the new result',
        ],
        'not': [],
    },
    'AIQIF-C9.3.O1': {
        'parts': [
            'A completed review of a detected relevant change exists || changes listed',
            'It evaluates the timeliness of detection or response || no timeliness evaluation',
        ],
        'not': [],
    },
    'AIQIF-C9.3.O2': {
        'parts': [
            'A monitoring-process revision is recorded || ' + PLANNED,
            'A follow-up evaluates its effect || described without evaluation',
        ],
        'not': [],
    },
    # ---- C9.4 Outcome Learning, UAT & Continuous Improvement
    'AIQIF-C9.4.F1': {
        'parts': [
            'A feedback process exists (survey, poll, structured feedback) || feedback mentioned in general',
            'It covers an institutional digital or learning initiative (e.g. teaching-learning, an online service) || feedback on facilities or events in general',
        ],
        'not': [],
    },
    'AIQIF-C9.4.F2': {
        'parts': [
            'Actions resulting from feedback are recorded (a follow-up register or action-taken report) || actions mentioned in general',
            'Ownership of each action is assigned || actions without owners',
        ],
        'not': ['Corrective actions passed on to departments without named owners'],
    },
    'AIQIF-C9.4.A1': {
        'parts': [
            'A user acceptance or outcome review is recorded (survey results, evaluation) || a review planned',
            'It evaluates an identified deployed initiative || initiatives in general',
        ],
        'not': [],
    },
    'AIQIF-C9.4.A2': {
        'parts': [
            'A corrective action is recorded || actions in general',
            'A completion check of that action is recorded || the action without a check',
        ],
        'not': [],
    },
    'AIQIF-C9.4.O1': {
        'parts': [
            'A feedback-driven change is recorded || changes in general',
            'A completed review evaluates its subsequent result || described without evaluation',
        ],
        'not': [],
    },
    'AIQIF-C9.4.O2': {
        'parts': [
            'A review identified a lesson || reviews in general',
            'A later initiative demonstrably applies that lesson || later initiatives without the link',
        ],
        'not': [],
    },
}


def build(rubric):
    expected = {c['id']: c['text'] for i in rubric['indicators'] for c in i['conditions']}
    if set(SPEC) != set(expected):
        raise ValueError(f'Spec covers {len(SPEC)} conditions; rubric has {len(expected)}: '
                         f'missing {sorted(set(expected) - set(SPEC))}, extra {sorted(set(SPEC) - set(expected))}')
    conditions = {}
    for cid, text in expected.items():
        parts = []
        for n, line in enumerate(SPEC[cid]['parts']):
            full, _, related = (piece.strip() for piece in line.partition('||'))
            if not full or not related:
                raise ValueError(f'{cid} part {n + 1} needs full and related evidence.')
            parts.append({'id': f'p{n + 1}', 'full': full, 'related': related})
        if not 2 <= len(parts) <= 4:
            raise ValueError(f'{cid} needs 2 to 4 parts.')
        conditions[cid] = {'assertion': text, 'parts': parts, 'not_enough': SPEC[cid].get('not', [])}
    return {'version': VERSION, 'rubric_version': rubric['version'], 'conditions': conditions}


if __name__ == '__main__':
    import os
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    import django
    django.setup()
    from apps.scoring.capability.engine import release
    pack = build(release())
    target = Path(__file__).with_name('rubric_parts_v1.json')
    target.write_text(json.dumps(pack, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(f'Wrote {len(pack["conditions"])} conditions, '
          f'{sum(len(c["parts"]) for c in pack["conditions"].values())} parts to {target.name}')
