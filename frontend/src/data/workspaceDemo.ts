// ===================================================================
// Demo content for the workspace modules — Evidence Intelligence,
// Transformation Plan, Goals & Tasks, Reminders, Compliance Mapping,
// UAT Readiness, and the AI Chatbot's canned replies.
//
// PORTED from the InGage "AI Future Ready" prototype, where each of these
// lived as a local array inside `src/App.tsx`. Content preserved; gathered
// here so the pages render data rather than hold it.
//
// ⚠ ILLUSTRATIVE DATA. No institution's real record. Nothing is persisted,
// nothing is fetched, and every screen rendering it carries a banner saying
// so — see components/DemoDataNotice.
// ===================================================================

// ===== EVIDENCE INTELLIGENCE =====
export type EvidenceStatus = 'verified' | 'uploaded' | 'under_review' | 'incomplete' | 'missing';

export interface EvidenceDoc {
  id: string;
  title: string;
  dept: string;
  type: string;
  status: EvidenceStatus;
  /** Completeness of the document itself, 0 when it does not exist yet. */
  score: number;
  issues?: string[];
}

export const EVIDENCE_DOCS: EvidenceDoc[] = [
  { id: 'ev1', title: 'Board Resolution — Digital Transformation', dept: 'Administration', type: 'Governance Document', status: 'verified', score: 95 },
  { id: 'ev2', title: 'IT Infrastructure Audit Report 2026', dept: 'IT', type: 'Technical Report', status: 'verified', score: 88 },
  { id: 'ev3', title: 'Faculty Development Program Records', dept: 'HR', type: 'Training Records', status: 'under_review', score: 72, issues: ['AI-specific training not separated'] },
  { id: 'ev4', title: 'Student AI Workshop Certificates', dept: 'Computer Science', type: 'Student Records', status: 'uploaded', score: 65, issues: ['Only CS department covered'] },
  { id: 'ev5', title: 'OBE Implementation Status Report', dept: 'Academics', type: 'Academic Report', status: 'incomplete', score: 55, issues: ['3 departments not covered'] },
  { id: 'ev6', title: 'NAAC SSR Draft — Criterion 1', dept: 'IQAC', type: 'Accreditation', status: 'under_review', score: 78, issues: ['Criterion 1.4 incomplete'] },
  { id: 'ev7', title: 'NIRF Data Submission 2026', dept: 'IQAC', type: 'Ranking Data', status: 'verified', score: 90 },
  { id: 'ev8', title: 'Innovation Cell Annual Report', dept: 'Innovation Cell', type: 'Report', status: 'uploaded', score: 70 },
  { id: 'ev9', title: 'AI Policy Document', dept: 'Administration', type: 'Policy', status: 'missing', score: 0 },
  { id: 'ev10', title: 'Data Governance Framework', dept: 'IT', type: 'Policy', status: 'missing', score: 0 },
  { id: 'ev11', title: 'Faculty AI Training Plan', dept: 'HR', type: 'Training Plan', status: 'missing', score: 0 },
  { id: 'ev12', title: 'AI Infrastructure Roadmap', dept: 'IT', type: 'Strategic Plan', status: 'missing', score: 0 },
];

// ===== TRANSFORMATION PLAN =====
export interface PlanInitiative {
  title: string;
  priority: 'critical' | 'high' | 'medium';
  owner: string;
  metric: string;
  status: 'in_progress' | 'not_started' | 'completed';
}

export interface PlanPhase {
  name: string;
  period: string;
  status: 'in_progress' | 'not_started' | 'completed';
  initiatives: PlanInitiative[];
}

export const PLAN_PHASES: PlanPhase[] = [
  {
    name: 'Foundation (Months 1–2)', period: 'Sep–Oct 2026', status: 'in_progress',
    initiatives: [
      { title: 'Establish AI Governance Framework', priority: 'critical', owner: 'Director', metric: 'AI Policy approved', status: 'in_progress' },
      { title: 'Faculty AI Capacity Building', priority: 'critical', owner: 'Dean Academics', metric: '80% faculty trained', status: 'not_started' },
      { title: 'Data Governance & Infrastructure', priority: 'high', owner: 'IT Head', metric: 'Data governance approved', status: 'not_started' },
    ],
  },
  {
    name: 'Build (Months 3–4)', period: 'Nov–Dec 2026', status: 'not_started',
    initiatives: [
      { title: 'AI-Integrated Curriculum Development', priority: 'high', owner: 'Department Heads', metric: 'AI modules in 50% of programs', status: 'not_started' },
      { title: 'Student AI Enablement Program', priority: 'high', owner: 'Department Heads', metric: 'AI lab operational', status: 'not_started' },
      { title: 'Administrative Process Digitization', priority: 'medium', owner: 'Registrar', metric: '5 processes digitized', status: 'not_started' },
    ],
  },
  {
    name: 'Scale (Months 5–6)', period: 'Jan–Feb 2027', status: 'not_started',
    initiatives: [
      { title: 'NAAC Evidence Completion Drive', priority: 'critical', owner: 'IQAC Coordinator', metric: '100% evidence collected', status: 'not_started' },
      { title: 'AI Innovation Ecosystem', priority: 'medium', owner: 'Director', metric: '3 AI partnerships', status: 'not_started' },
    ],
  },
];

export const PLAN_TARGET = {
  headline: 'AI Transformation Roadmap',
  target: 'Target: CRI 75+ (Established band) by December 2026',
  derivedFrom: 'Generated from CRI 43.5 · 58% evidence complete · 14 documents missing',
};

// ===== GOALS & TASKS =====
export type TaskStatus = 'not_started' | 'in_progress' | 'completed';

export interface WorkTask {
  id: string;
  title: string;
  owner: string;
  dept: string;
  due: string;
  status: TaskStatus;
  priority: 'critical' | 'high' | 'medium';
}

export const TASKS: WorkTask[] = [
  { id: 't1', title: 'Form AI Steering Committee', owner: 'Dr. Rajesh Kumar', dept: 'Administration', due: 'Sep 10', status: 'in_progress', priority: 'critical' },
  { id: 't2', title: 'Draft AI Ethics Guidelines', owner: 'Dr. Priya Sharma', dept: 'Academics', due: 'Sep 20', status: 'not_started', priority: 'critical' },
  { id: 't3', title: 'Design AI Training Curriculum', owner: 'Dr. Sunita Patel', dept: 'HR', due: 'Sep 25', status: 'not_started', priority: 'critical' },
  { id: 't4', title: 'Conduct Batch 1 Faculty Training', owner: 'Dr. Sunita Patel', dept: 'HR', due: 'Oct 31', status: 'not_started', priority: 'high' },
  { id: 't5', title: 'Draft Data Governance Policy', owner: 'Prof. Anil Mehta', dept: 'IT', due: 'Sep 30', status: 'not_started', priority: 'high' },
  { id: 't6', title: 'Evaluate Cloud ERP Options', owner: 'Prof. Anil Mehta', dept: 'IT', due: 'Oct 15', status: 'not_started', priority: 'high' },
  { id: 't10', title: 'Collect Missing NAAC Evidence', owner: 'Dr. Rajesh Kumar', dept: 'IQAC', due: 'Oct 31', status: 'in_progress', priority: 'critical' },
  { id: 't12', title: 'Upload Board Resolution', owner: 'Dr. Rajesh Kumar', dept: 'Administration', due: 'Sep 5', status: 'completed', priority: 'high' },
];

export interface WorkGoal {
  id: string;
  title: string;
  owner: string;
  due: string;
  progress: number;
  status: TaskStatus;
  priority: 'critical' | 'high';
}

export const GOALS: WorkGoal[] = [
  { id: 'g1', title: 'Draft and Approve AI Policy', owner: 'Dr. Rajesh Kumar', due: 'Sep 30', progress: 25, status: 'in_progress', priority: 'critical' },
  { id: 'g2', title: 'Infrastructure Modernization Plan', owner: 'Prof. Anil Mehta', due: 'Oct 31', progress: 10, status: 'in_progress', priority: 'high' },
  { id: 'g3', title: 'Launch Faculty AI Training', owner: 'Dr. Priya Sharma', due: 'Dec 31', progress: 5, status: 'not_started', priority: 'critical' },
  { id: 'g5', title: 'Complete OBE Implementation', owner: 'Dr. Priya Sharma', due: 'Nov 30', progress: 40, status: 'in_progress', priority: 'high' },
  { id: 'g6', title: 'NAAC SSR Preparation', owner: 'Dr. Rajesh Kumar', due: 'Jan 31', progress: 35, status: 'in_progress', priority: 'critical' },
];

// ===== REMINDERS =====
export type ReminderType = 'deadline' | 'overdue' | 'document' | 'progress' | 'review';

export interface ReminderItem {
  id: string;
  title: string;
  message: string;
  due: string;
  priority: 'critical' | 'high' | 'medium';
  type: ReminderType;
}

export const REMINDERS: ReminderItem[] = [
  { id: 'r1', title: 'AI Steering Committee formation deadline', message: '3 members confirmed, 4 remaining', due: 'Sep 10', priority: 'critical', type: 'deadline' },
  { id: 'r5', title: 'NAAC evidence collection overdue', message: '14 documents missing, 3 past deadline', due: 'Aug 25', priority: 'critical', type: 'overdue' },
  { id: 'r2', title: 'AI Ethics Guidelines draft due', message: 'Work has not started yet', due: 'Sep 20', priority: 'critical', type: 'deadline' },
  { id: 'r7', title: 'OBE report incomplete', message: '3 departments not covered', due: 'Sep 15', priority: 'high', type: 'document' },
  { id: 'r3', title: 'Faculty training curriculum design', message: 'AI training curriculum needed by Sep 25', due: 'Sep 25', priority: 'high', type: 'deadline' },
  { id: 'r4', title: 'Data Governance Policy draft', message: 'Critical for CRI improvement', due: 'Sep 30', priority: 'high', type: 'deadline' },
  { id: 'r6', title: 'Weekly CRI progress update', message: 'CRI: 43.5, target: 75', due: 'Sep 6', priority: 'medium', type: 'progress' },
  { id: 'r8', title: 'Faculty training records review', message: 'AI-specific training not separated', due: 'Sep 12', priority: 'medium', type: 'review' },
];

// ===== COMPLIANCE MAPPING =====
export type MappingStatus = 'not_started' | 'evidence_missing' | 'partially_mapped' | 'mapped' | 'verified';

export interface ComplianceRow {
  id: string;
  framework: string;
  criterion: string;
  status: MappingStatus;
  confidence: number;
  gaps: number;
}

export const COMPLIANCE_FRAMEWORKS = ['NAAC', 'NBA', 'NIRF', 'NEP', 'AI_FUTURE_READY'] as const;

export const COMPLIANCE_ROWS: ComplianceRow[] = [
  { id: 'cm1', framework: 'NAAC', criterion: 'Criterion 6.5 — Quality Assurance', status: 'partially_mapped', confidence: 55, gaps: 2 },
  { id: 'cm2', framework: 'NAAC', criterion: 'Criterion 6.3 — Faculty Empowerment', status: 'evidence_missing', confidence: 30, gaps: 2 },
  { id: 'cm5', framework: 'NAAC', criterion: 'Criterion 4.3 — IT Infrastructure', status: 'partially_mapped', confidence: 50, gaps: 2 },
  { id: 'cm6', framework: 'NAAC', criterion: 'Criterion 1.1–1.4 — Curriculum Design', status: 'partially_mapped', confidence: 60, gaps: 1 },
  { id: 'cm3', framework: 'NIRF', criterion: 'Teaching, Learning & Resources', status: 'partially_mapped', confidence: 45, gaps: 2 },
  { id: 'cm4', framework: 'NEP', criterion: 'NEP 2020 — Multidisciplinary Education', status: 'evidence_missing', confidence: 35, gaps: 2 },
  { id: 'cm7', framework: 'NBA', criterion: 'Program Outcomes & Assessment', status: 'evidence_missing', confidence: 40, gaps: 2 },
  { id: 'cm8', framework: 'AI_FUTURE_READY', criterion: 'AI Governance & Strategy', status: 'not_started', confidence: 15, gaps: 3 },
  { id: 'cm9', framework: 'AI_FUTURE_READY', criterion: 'Faculty AI Competence', status: 'not_started', confidence: 10, gaps: 2 },
  { id: 'cm10', framework: 'AI_FUTURE_READY', criterion: 'Data & Infrastructure Readiness', status: 'not_started', confidence: 20, gaps: 3 },
];

export const MAPPING_STATUS_LABELS: Record<MappingStatus, string> = {
  not_started: 'Not started',
  evidence_missing: 'Evidence missing',
  partially_mapped: 'Partial',
  mapped: 'Mapped',
  verified: 'Verified',
};

// ===== UAT READINESS =====
export interface UatItem {
  module: string;
  item: string;
  status: 'ready' | 'in_progress';
  risk: 'low' | 'medium' | 'high';
}

export const UAT_ITEMS: UatItem[] = [
  { module: 'AI Readiness Audit', item: 'CRI score calculation and display', status: 'ready', risk: 'low' },
  { module: 'AI Readiness Audit', item: 'Category gap analysis and recommendations', status: 'ready', risk: 'low' },
  { module: 'Institution DNA', item: 'Institution profile display and edit', status: 'ready', risk: 'low' },
  { module: 'Evidence Intelligence', item: 'Document upload and status tracking', status: 'in_progress', risk: 'medium' },
  { module: 'Transformation Plan', item: 'Plan generation from CRI and evidence', status: 'ready', risk: 'low' },
  { module: 'Goals & Tasks', item: 'Task board and status updates', status: 'in_progress', risk: 'medium' },
  { module: 'AI Chatbot', item: 'Context-aware responses', status: 'in_progress', risk: 'medium' },
  { module: 'Reminders', item: 'Reminder display and actions', status: 'ready', risk: 'low' },
  { module: 'Compliance Mapping', item: 'NAAC / NBA / NIRF / NEP mapping', status: 'in_progress', risk: 'medium' },
  { module: 'Role-Based Views', item: 'Role switcher and contextual views', status: 'ready', risk: 'low' },
  { module: 'Responsive Design', item: 'Mobile and tablet compatibility', status: 'in_progress', risk: 'medium' },
  { module: 'Backend Contracts', item: 'API contracts documented and typed', status: 'in_progress', risk: 'high' },
];

// ===== AI CHATBOT =====
/** Canned replies, keyed by a word in the question. This is a scripted demo,
 * NOT a model call — the page says so plainly, because a chat box that looks
 * intelligent is the easiest thing in this whole port to mistake for real. */
export const CHAT_REPLIES: { keyword: string; reply: string }[] = [
  { keyword: 'gap', reply: 'Your top gaps are AI Policy & Ethics (20/100), Data Readiness (35/100), and Faculty AI Adoption (38/100). These three have the highest potential for CRI improvement.' },
  { keyword: 'document', reply: 'You have 14 missing documents. The critical ones: AI Policy Document, Data Governance Framework, Faculty AI Training Plan. Uploading these would move evidence completeness from 58% to over 80%.' },
  { keyword: 'task', reply: 'You have 3 critical tasks this week: Form AI Steering Committee (Sep 10), Draft AI Ethics Guidelines (Sep 20), Design AI Training Curriculum (Sep 25).' },
  { keyword: 'score', reply: 'Your CRI is 43.5/100 (Developing). To reach Established (60+), focus on AI Policy & Ethics (+15 pts), Faculty Training (+12 pts) and Data Readiness (+10 pts).' },
  { keyword: 'naac', reply: 'NAAC evidence is 60% complete with 14 missing documents. The SSR Criterion 1 draft is at 78% and under review. Priority: complete evidence collection by Oct 31.' },
];

export const CHAT_FALLBACK =
  'I can help with gap analysis, missing documents, task tracking, CRI scores and compliance mapping. Try asking about any of those.';

export const CHAT_SUGGESTIONS = [
  'What are our top gaps?',
  'Missing documents?',
  'CRI score details?',
];

export const CHAT_OPENING =
  'Hello. I am the AI Readiness Chatbot. I can help you understand your CRI score, identify gaps, track tasks, and navigate your transformation journey. What would you like to know?';
