import type { MenuTourConfig, MenuTourStep } from '../../types/guide';
import type { UserRole } from '../../types/auth';

export type MenuKey =
  | 'dashboard'
  | 'institution-dna'
  | 'sprint-setup'
  | 'sprint-upload'
  | 'sprint-monitor'
  | 'evidence-intelligence'
  | 'sprint-facts'
  | 'sprint-aiqif-review'
  | 'evidence-requests'
  | 'sprint-gaps'
  | 'sprint-confirmation'
  | 'sprint-score'
  | 'sprint-approval'
  | 'sprint-recommendations'
  | 'sprint-report'
  | 'cri-benchmark-intelligence'
  | 'benchmark-studio'
  | 'benchmark-assessment'
  | 'transformation-plan'
  | 'goals-tasks'
  | 'ai-copilot'
  | 'reminders'
  | 'compliance-mapping'
  | 'uat-readiness'
  | 'admin-settings';

const ALL_ROLES: readonly UserRole[] = ['super_admin', 'consultant', 'iqac_coordinator'];
const STAFF_ROLES: readonly UserRole[] = ['super_admin', 'consultant'];
const SUPER_ADMIN_ONLY: readonly UserRole[] = ['super_admin'];
const CONFIRMATION_ROLES: readonly UserRole[] = ['consultant', 'iqac_coordinator'];

/**
 * Curated, role-checked interactive product tours for every accessible menu
 * in the AI Readiness Platform.
 *
 * Each tour provides concise, instructional steps highlighting the menu's purpose
 * and key controls using stable `data-tour` target attributes.
 */
export const MENU_TOURS: Record<MenuKey, MenuTourConfig> = {
  dashboard: {
    menuKey: 'dashboard',
    menuTitle: 'Dashboard',
    menuPurpose: 'Discovery Sprints overview, institutional metrics, and sprint lifecycle management.',
    roles: 'all',
    steps: [
      {
        id: 'dashboard-sprint-context',
        number: 1,
        title: 'Selected Sprint Context Bar',
        purpose: 'Displays the currently active discovery sprint scoping all audit data. Use the selector to switch sprints anytime.',
        tour_target: 'sprint-context-bar',
        tour_location: 'Dashboard > Header Context Bar',
      },
      {
        id: 'dashboard-banner',
        number: 2,
        title: 'Discovery Sprints Overview',
        purpose: 'Execute fast-track AI readiness audits across governance, curriculum, faculty capability, student readiness, labs, research, and placements.',
        tour_target: 'dashboard-banner',
        tour_location: 'Dashboard > Top Banner',
      },
      {
        id: 'dashboard-metrics',
        number: 3,
        title: 'Institutional Metrics Overview',
        purpose: 'Track active sprints, total institutions onboarded, average CRI score, and average evidence confidence at a glance.',
        tour_target: 'dashboard-metrics',
        tour_location: 'Dashboard > Metrics Row',
      },
      {
        id: 'dashboard-create',
        number: 4,
        title: 'Create New Discovery Sprint',
        purpose: 'Initialize a new discovery engagement for an institution to begin document collection and scoring.',
        tour_target: 'dashboard-create-btn',
        tour_location: 'Dashboard > Banner Actions',
      },
      {
        id: 'dashboard-sprints-table',
        number: 5,
        title: 'Sprint Directory & Actions',
        purpose: 'Review sprint progress. Click "Open" to jump into the audit workflow or archive finished engagements.',
        tour_target: 'dashboard-sprints-table',
        tour_location: 'Dashboard > Sprints Table',
      },
    ],
  },

  'institution-dna': {
    menuKey: 'institution-dna',
    menuTitle: 'Institution DNA',
    menuPurpose: 'Establish and maintain baseline institutional profiles, departments, leadership, and digital maturity.',
    roles: 'all',
    steps: [
      {
        id: 'dna-header',
        number: 1,
        title: 'Institution DNA Directory',
        purpose: 'Maintain institutional master records. Each institution holds its profile, departments, leadership, and IT infrastructure.',
        tour_target: 'institution-dna-header',
        tour_location: 'Platform Modules > Institution DNA',
      },
      {
        id: 'dna-search',
        number: 2,
        title: 'Filter & Search Institutions',
        purpose: 'Quickly find an institution by typing its name, affiliation, city, state, or accreditation status.',
        tour_target: 'institution-dna-search',
        tour_location: 'Institution DNA > Search Controls',
      },
      {
        id: 'dna-add-btn',
        number: 3,
        title: 'Register New College',
        purpose: 'Add a new institution to begin profiling its organizational structure and readiness parameters.',
        tour_target: 'institution-add-btn',
        tour_location: 'Institution DNA > Header Actions',
      },
      {
        id: 'dna-table',
        number: 4,
        title: 'Institutions Table & Detail Workspace',
        purpose: 'Click any institution to open its full profile, leadership directory, department roster, and digital maturity rating.',
        tour_target: 'institution-dna-table',
        tour_location: 'Institution DNA > Directory Table',
      },
    ],
  },

  'sprint-setup': {
    menuKey: 'sprint-setup',
    menuTitle: 'Sprint Setup',
    menuPurpose: 'Initialize or configure an audit sprint with institutional baseline parameters and academic year.',
    roles: ALL_ROLES,
    steps: [
      {
        id: 'sprint-setup-header',
        number: 1,
        title: 'Sprint Configuration',
        purpose: 'Configure the parameters of a new AI readiness discovery engagement for an institution.',
        tour_target: 'sprint-setup-form',
        tour_location: 'AI Readiness Audit > Sprint Setup',
      },
      {
        id: 'sprint-setup-inst',
        number: 2,
        title: 'Institution Selection',
        purpose: 'Select the institution being audited. Master profile data is populated directly from Institution DNA.',
        tour_target: 'sprint-setup-institution',
        tour_location: 'Sprint Setup > Form Fields',
      },
      {
        id: 'sprint-setup-details',
        number: 3,
        title: 'Sprint Name & Academic Year',
        purpose: 'Specify the audit name and target academic year. This scopes document uploads and CRI evaluations.',
        tour_target: 'sprint-setup-name',
        tour_location: 'Sprint Setup > Form Fields',
      },
      {
        id: 'sprint-setup-submit',
        number: 4,
        title: 'Initialize Sprint',
        purpose: 'Confirm setup to create the sprint and advance directly to Upload Data Pack.',
        tour_target: 'sprint-setup-submit',
        tour_location: 'Sprint Setup > Action Buttons',
      },
    ],
  },

  'sprint-upload': {
    menuKey: 'sprint-upload',
    menuTitle: 'Upload Data Pack',
    menuPurpose: 'Upload institutional documents, reports, and policies, or import them directly from Google Drive.',
    roles: ALL_ROLES,
    steps: [
      {
        id: 'upload-source-toggle',
        number: 1,
        title: 'Choose Data Source',
        purpose: 'Switch between uploading local files directly or importing an entire evidence folder from Google Drive.',
        tour_target: 'upload-source-toggle',
        tour_location: 'AI Readiness Audit > Upload Data Pack',
      },
      {
        id: 'upload-dropzone',
        number: 2,
        title: 'Document Ingestion Zone',
        purpose: 'Drag and drop PDF/Word documents or provide a shared Google Drive folder URL to ingest evidence.',
        tour_target: 'upload-dropzone',
        tour_location: 'Upload Data Pack > Ingestion Card',
      },
      {
        id: 'upload-checklist',
        number: 3,
        title: 'Required Document Checklist',
        purpose: 'Review expected compliance files: NAAC SSR, AQAR, Syllabi, Lab Inventories, and Research Publications.',
        tour_target: 'upload-checklist',
        tour_location: 'Upload Data Pack > Audit Checklist',
      },
      {
        id: 'upload-table',
        number: 4,
        title: 'Uploaded Documents Registry',
        purpose: 'Verify file types, review automated category classifications, and remove invalid uploads.',
        tour_target: 'upload-documents-table',
        tour_location: 'Upload Data Pack > Documents Table',
      },
      {
        id: 'upload-extract-btn',
        number: 5,
        title: 'Start AI Extraction',
        purpose: 'Initiate OCR reading and automated AI fact extraction across all confirmed sprint documents.',
        tour_target: 'upload-start-extraction',
        tour_location: 'Upload Data Pack > Pipeline Action',
      },
    ],
  },

  'sprint-monitor': {
    menuKey: 'sprint-monitor',
    menuTitle: 'AI Processing Monitor',
    menuPurpose: 'Track real-time OCR, page reading, classification, and AI fact extraction jobs.',
    roles: ALL_ROLES,
    steps: [
      {
        id: 'monitor-summary',
        number: 1,
        title: 'Processing Summary Tiles',
        purpose: 'Monitor document completeness: total documents, complete, in-progress, partial, and unreadable pages.',
        tour_target: 'monitor-summary-tiles',
        tour_location: 'AI Readiness Audit > AI Processing Monitor',
      },
      {
        id: 'monitor-actions',
        number: 2,
        title: 'Extraction Pipeline Controls',
        purpose: 'Trigger fresh extraction runs, re-process partial documents, or cancel active extraction tasks.',
        tour_target: 'monitor-actions',
        tour_location: 'AI Processing Monitor > Control Bar',
      },
      {
        id: 'monitor-table',
        number: 3,
        title: 'Document Pipeline Status',
        purpose: 'Inspect page reading progress, OCR warning counts, and extracted facts yielded per document.',
        tour_target: 'monitor-pipeline-table',
        tour_location: 'AI Processing Monitor > Pipeline Table',
      },
      {
        id: 'monitor-proceed',
        number: 4,
        title: 'Proceed to Facts Review',
        purpose: 'Advance to review and validate extracted institutional claims once processing completes.',
        tour_target: 'monitor-proceed-btn',
        tour_location: 'AI Processing Monitor > Header Navigation',
      },
    ],
  },

  'evidence-intelligence': {
    menuKey: 'evidence-intelligence',
    menuTitle: 'Evidence Intelligence',
    menuPurpose: 'Analyze the institution’s evidence position, document processing quality, and missing requirements.',
    roles: ALL_ROLES,
    steps: [
      {
        id: 'evidence-header',
        number: 1,
        title: 'Evidence Intelligence Position',
        purpose: 'High-level synthesis of all evidence gathered for the selected sprint, highlighting documentation gaps.',
        tour_target: 'evidence-header',
        tour_location: 'Platform Modules > Evidence Intelligence',
      },
      {
        id: 'evidence-metrics',
        number: 2,
        title: 'Key Evidence Metrics',
        purpose: 'Track processed documents, total verified facts, OCR warnings, and open missing-document gaps.',
        tour_target: 'evidence-metrics',
        tour_location: 'Evidence Intelligence > Metrics Row',
      },
      {
        id: 'evidence-filters',
        number: 3,
        title: 'Document Status Filters',
        purpose: 'Filter evidence by processing status or isolate documents flagged as needing attention.',
        tour_target: 'evidence-filters',
        tour_location: 'Evidence Intelligence > Filters',
      },
      {
        id: 'evidence-table',
        number: 4,
        title: 'Document Inventory & Yield',
        purpose: 'Inspect each document’s page count, OCR quality, and the number of facts it contributed to the audit.',
        tour_target: 'evidence-table',
        tour_location: 'Evidence Intelligence > Inventory Table',
      },
    ],
  },

  'sprint-facts': {
    menuKey: 'sprint-facts',
    menuTitle: 'Extracted Facts Review',
    menuPurpose: 'Validate AI-extracted metrics, institutional claims, and citations; confirm, correct, or reject values.',
    roles: ALL_ROLES,
    steps: [
      {
        id: 'facts-confidence',
        number: 1,
        title: 'CRI Evidence Confidence',
        purpose: 'Evaluates empirical confidence based on confirmed facts, source citations, and verified metrics.',
        tour_target: 'facts-summary-tile',
        tour_location: 'AI Readiness Audit > Extracted Facts Review',
      },
      {
        id: 'facts-filters',
        number: 2,
        title: 'Facet & Attribute Filters',
        purpose: 'Filter facts by review status (confirmed, pending, rejected), owner role, source document, or pillar.',
        tour_target: 'facts-filters',
        tour_location: 'Facts Review > Table Filters',
      },
      {
        id: 'facts-bulk',
        number: 3,
        title: 'Bulk Confirmation',
        purpose: 'Review and confirm high-confidence facts in batches to speed up audit progression.',
        tour_target: 'facts-bulk-confirm',
        tour_location: 'Facts Review > Action Bar',
      },
      {
        id: 'facts-table',
        number: 4,
        title: 'Fact Verification & Citations',
        purpose: 'Verify citations in the original document. Confirm accurate values, enter corrections, or request evidence.',
        tour_target: 'facts-table',
        tour_location: 'Facts Review > Facts Table',
      },
      {
        id: 'facts-expert-link',
        number: 5,
        title: 'AI-QIF Expert Queue Access',
        purpose: 'Super Admins can access the dedicated queue to settle ambiguous indicator mappings and evidence tags.',
        tour_target: 'facts-expert-link',
        tour_location: 'Facts Review > Expert Link',
      },
    ],
  },

  'sprint-aiqif-review': {
    menuKey: 'sprint-aiqif-review',
    menuTitle: 'AI-QIF Expert Queue',
    menuPurpose: 'Resolve indicator mappings, validate AI evidence classifications, and establish tagging precedents.',
    roles: SUPER_ADMIN_ONLY,
    steps: [
      {
        id: 'aiqif-header',
        number: 1,
        title: 'Expert Tagging Queue',
        purpose: 'Dedicated queue for Super Admins to resolve facts where automatic indicator assignment requires human expertise.',
        tour_target: 'aiqif-header',
        tour_location: 'Extracted Facts > AI-QIF Expert Queue',
      },
      {
        id: 'aiqif-auto',
        number: 2,
        title: 'Precedent-Based Decisions',
        purpose: 'Run automated decision engine to apply precedents from earlier expert determinations to pending items.',
        tour_target: 'aiqif-auto-decide',
        tour_location: 'Expert Queue > Controls',
      },
      {
        id: 'aiqif-tabs',
        number: 3,
        title: 'Pending Queue vs Reviewed History',
        purpose: 'Switch between items awaiting review and decided items to edit or reopen previous determinations.',
        tour_target: 'aiqif-tabs',
        tour_location: 'Expert Queue > Tab Navigation',
      },
      {
        id: 'aiqif-cards',
        number: 4,
        title: 'Indicator Tagging & Relationships',
        purpose: 'Confirm AI evidence classification, map facts to indicators, and specify direct, supporting, or contextual relationships.',
        tour_target: 'aiqif-cards',
        tour_location: 'Expert Queue > Decision Cards',
      },
    ],
  },

  'evidence-requests': {
    menuKey: 'evidence-requests',
    menuTitle: 'Evidence Requests',
    menuPurpose: 'Coordinate missing evidence workflows, assign collection tasks, and review uploaded proofs.',
    roles: ALL_ROLES,
    steps: [
      {
        id: 'evidence-requests-header',
        number: 1,
        title: 'Evidence Requests Center',
        purpose: 'Coordinate requests for additional institutional proof raised during facts review.',
        tour_target: 'evidence-requests-header',
        tour_location: 'Platform Modules > Evidence Requests',
      },
      {
        id: 'evidence-requests-views',
        number: 2,
        title: 'Workflow Views',
        purpose: 'Quickly filter requests: "Assigned to me", "Awaiting review", "Open / returned", or "Overdue".',
        tour_target: 'evidence-requests-views',
        tour_location: 'Evidence Requests > View Tabs',
      },
      {
        id: 'evidence-requests-table',
        number: 3,
        title: 'Request Tracking & Deadlines',
        purpose: 'Track assigned owner role, required evidence types, due dates, and submission history.',
        tour_target: 'evidence-requests-table',
        tour_location: 'Evidence Requests > Requests List',
      },
      {
        id: 'evidence-requests-actions',
        number: 4,
        title: 'Evidence Review & Decision',
        purpose: 'Review submitted evidence files, approve verified proofs, or return requests with feedback.',
        tour_target: 'evidence-requests-actions',
        tour_location: 'Evidence Requests > Action Controls',
      },
    ],
  },

  'sprint-gaps': {
    menuKey: 'sprint-gaps',
    menuTitle: 'Gap Dashboard',
    menuPurpose: 'Review missing documentation, resolve conflicting metrics, and track gap remediation.',
    roles: ALL_ROLES,
    steps: [
      {
        id: 'gaps-summary',
        number: 1,
        title: 'Gap Analysis Overview',
        purpose: 'Displays open gaps, blocking items that prevent baseline approval, and conflict items across the sprint.',
        tour_target: 'gaps-summary-bar',
        tour_location: 'AI Readiness Audit > Gap Dashboard',
      },
      {
        id: 'gaps-filters',
        number: 2,
        title: 'Gap Priority & Type Filters',
        purpose: 'Filter by priority (blocking, high, medium), gap type (missing document, low confidence, conflict), or owner role.',
        tour_target: 'gaps-filters',
        tour_location: 'Gap Dashboard > Filters',
      },
      {
        id: 'gaps-table',
        number: 3,
        title: 'Gap Settlement Actions',
        purpose: 'Resolve gaps with explanation notes, mark items as institutionally unavailable, or skip optional gaps.',
        tour_target: 'gaps-table',
        tour_location: 'Gap Dashboard > Gaps Table',
      },
      {
        id: 'gaps-evidence-btn',
        number: 4,
        title: 'Upload Evidence & Conflict Comparison',
        purpose: 'Upload supporting proof to satisfy missing items or open the side-by-side comparison to resolve discrepancies.',
        tour_target: 'gaps-evidence-btn',
        tour_location: 'Gap Dashboard > Row Actions',
      },
      {
        id: 'gaps-proceed-btn',
        number: 5,
        title: 'Proceed to CRI Scoring',
        purpose: 'Navigate to Live CRI Preview to calculate readiness scores once critical gaps are addressed.',
        tour_target: 'gaps-proceed-btn',
        tour_location: 'Gap Dashboard > Header Navigation',
      },
    ],
  },

  'sprint-confirmation': {
    menuKey: 'sprint-confirmation',
    menuTitle: 'Owner Confirmation Workspace',
    menuPurpose: 'Role-specific task workspace for college staff and consultants to verify facts and resolve assigned gaps.',
    roles: CONFIRMATION_ROLES,
    steps: [
      {
        id: 'owner-header',
        number: 1,
        title: 'Owner Confirmation Workspace',
        purpose: 'Personalized task center showing review items and gap remediation assigned to your institutional role.',
        tour_target: 'owner-workspace-header',
        tour_location: 'AI Readiness Audit > Owner Workspace',
      },
      {
        id: 'owner-readiness',
        number: 2,
        title: 'Sprint Readiness for Baseline Review',
        purpose: 'Real-time indicator showing if all required facts and blocking gaps are settled for baseline formalization.',
        tour_target: 'owner-readiness-card',
        tour_location: 'Owner Workspace > Readiness Card',
      },
      {
        id: 'owner-filters',
        number: 3,
        title: 'Task Scope Filters',
        purpose: 'Switch between "My tasks" and "All sprint tasks", and filter by owner role or overdue status.',
        tour_target: 'owner-task-filters',
        tour_location: 'Owner Workspace > Controls',
      },
      {
        id: 'owner-list',
        number: 4,
        title: 'Assigned Action Items',
        purpose: 'Confirm extracted facts, resolve open gaps, or assign evidence collection tasks to team members.',
        tour_target: 'owner-task-list',
        tour_location: 'Owner Workspace > Task Cards',
      },
      {
        id: 'owner-proceed',
        number: 5,
        title: 'Proceed to Live CRI',
        purpose: 'Advance to Live CRI Preview once assigned confirmation tasks are completed.',
        tour_target: 'owner-proceed-btn',
        tour_location: 'Owner Workspace > Header Navigation',
      },
    ],
  },

  'sprint-score': {
    menuKey: 'sprint-score',
    menuTitle: 'Live CRI Preview',
    menuPurpose: 'Real-time evaluation of the College Readiness Index across all nine AI-QIF criteria.',
    roles: 'all',
    steps: [
      {
        id: 'cri-header',
        number: 1,
        title: 'Campus Readiness Index Preview',
        purpose: 'Live readiness evaluation dynamically computed from verified facts, open gaps, and evidence coverage.',
        tour_target: 'cri-preview-header',
        tour_location: 'AI Readiness Audit > Live CRI Preview',
      },
      {
        id: 'cri-recalc',
        number: 2,
        title: 'Recalculate CRI Score',
        purpose: 'Trigger a deterministic score recomputation following fact confirmations or gap resolutions.',
        tour_target: 'cri-recalculate-btn',
        tour_location: 'Live CRI Preview > Controls',
      },
      {
        id: 'cri-tiles',
        number: 3,
        title: 'CRI Scorecard Tiles',
        purpose: 'Review Coverage-Adjusted CRI, Raw CRI, and total Evidence Coverage across required criteria.',
        tour_target: 'cri-score-tiles',
        tour_location: 'Live CRI Preview > Metric Tiles',
      },
      {
        id: 'cri-breakdown',
        number: 4,
        title: '9 AI-QIF Criteria Breakdown',
        purpose: 'Explore detailed scores, weightings, and confidence indicators across each of the nine dimensions.',
        tour_target: 'cri-criteria-breakdown',
        tour_location: 'Live CRI Preview > Criteria Table',
      },
      {
        id: 'cri-proceed',
        number: 5,
        title: 'Proceed to Baseline Approval',
        purpose: 'Lock and formalize the baseline score to unlock recommendations and report generation.',
        tour_target: 'cri-proceed-btn',
        tour_location: 'Live CRI Preview > Header Navigation',
      },
    ],
  },

  'sprint-approval': {
    menuKey: 'sprint-approval',
    menuTitle: 'Baseline Approval',
    menuPurpose: 'Formalize and lock the baseline CRI score with rationale to unlock recommendations and report export.',
    roles: ALL_ROLES,
    steps: [
      {
        id: 'approval-header',
        number: 1,
        title: 'Baseline Status & Governance',
        purpose: 'Review whether the baseline is provisional, approved & locked, or returned for revision.',
        tour_target: 'approval-header',
        tour_location: 'AI Readiness Audit > Baseline Approval',
      },
      {
        id: 'approval-metrics',
        number: 2,
        title: 'Candidate Baseline Metrics',
        purpose: 'Inspect the formal candidate score, confidence level, and criterion deltas under review.',
        tour_target: 'approval-metrics-card',
        tour_location: 'Baseline Approval > Metrics Card',
      },
      {
        id: 'approval-actions',
        number: 3,
        title: 'Formal Approval Actions',
        purpose: 'Approve and lock the baseline, grant provisional approval, or return the audit with feedback.',
        tour_target: 'approval-actions',
        tour_location: 'Baseline Approval > Governance Actions',
      },
      {
        id: 'approval-history',
        number: 4,
        title: 'Audit Trail & Cycles',
        purpose: 'Inspect the immutable history of previous approval cycles, timestamps, and reviewer notes.',
        tour_target: 'approval-history',
        tour_location: 'Baseline Approval > Audit Trail',
      },
    ],
  },

  'sprint-recommendations': {
    menuKey: 'sprint-recommendations',
    menuTitle: 'Recommendations',
    menuPurpose: 'Prioritized recommendations generated by the engine with expected CRI lift and horizon timelines.',
    roles: 'all',
    steps: [
      {
        id: 'recs-header',
        number: 1,
        title: 'Strategic Recommendations',
        purpose: 'Actionable institutional initiatives generated by the engine based on audit gaps and maturity goals.',
        tour_target: 'recommendations-header',
        tour_location: 'AI Readiness Audit > Recommendations',
      },
      {
        id: 'recs-generate',
        number: 2,
        title: 'Generate Recommendations',
        purpose: 'Run recommendation generation across the approved baseline to generate tailored transformation initiatives.',
        tour_target: 'recommendations-generate-btn',
        tour_location: 'Recommendations > Generation Bar',
      },
      {
        id: 'recs-cards',
        number: 3,
        title: 'Initiative Details & CRI Lift',
        purpose: 'Inspect each initiative’s projected CRI score lift, priority level, implementation timeline, and rationale.',
        tour_target: 'recommendations-cards',
        tour_location: 'Recommendations > Initiative Cards',
      },
      {
        id: 'recs-actions',
        number: 4,
        title: 'Accept, Edit, or Hide',
        purpose: 'Accept initiatives into the formal report, edit wording for institutional context, or hide optional suggestions.',
        tour_target: 'recommendations-actions',
        tour_location: 'Recommendations > Card Actions',
      },
      {
        id: 'recs-proceed',
        number: 5,
        title: 'Proceed to Report & Export',
        purpose: 'Advance to compile and generate the final AI Readiness Audit Discovery Report.',
        tour_target: 'recommendations-proceed-btn',
        tour_location: 'Recommendations > Header Navigation',
      },
    ],
  },

  'sprint-report': {
    menuKey: 'sprint-report',
    menuTitle: 'Report & Export',
    menuPurpose: 'Export and review the formal AI Readiness Audit Discovery Report in PDF and Word formats.',
    roles: 'all',
    steps: [
      {
        id: 'report-header',
        number: 1,
        title: 'Audit Discovery Report',
        purpose: 'The formal deliverable presenting institutional readiness scores, criterion findings, and transformation plan.',
        tour_target: 'report-header',
        tour_location: 'AI Readiness Audit > Report & Export',
      },
      {
        id: 'report-generate',
        number: 2,
        title: 'Generate Formal Report',
        purpose: 'Compile all verified facts, approved baselines, and accepted recommendations into the report document.',
        tour_target: 'report-generate-btn',
        tour_location: 'Report & Export > Header Actions',
      },
      {
        id: 'report-export',
        number: 3,
        title: 'Export Formats',
        purpose: 'Download publication-ready PDF, editable Word (.docx) document, or print the report directly.',
        tour_target: 'report-export-actions',
        tour_location: 'Report & Export > Download Options',
      },
      {
        id: 'report-preview',
        number: 4,
        title: 'Executive Preview Tabs',
        purpose: 'Review executive summary, institutional profile, AI-QIF findings, and strategic recommendations in-app.',
        tour_target: 'report-preview-tabs',
        tour_location: 'Report & Export > Report Preview',
      },
    ],
  },

  'cri-benchmark-intelligence': {
    menuKey: 'cri-benchmark-intelligence',
    menuTitle: 'CRI & Benchmark Intelligence',
    menuPurpose: 'Pillar-based readiness score, critical gaps, and strategic improvement roadmap.',
    roles: 'all',
    steps: [
      {
        id: 'benchmark-intel-header',
        number: 1,
        title: 'Readiness Intelligence Overview',
        purpose: 'Macro-level evaluation of institution readiness across eight core institutional pillars.',
        tour_target: 'benchmark-intel-header',
        tour_location: 'Platform Modules > CRI & Benchmark Intelligence',
      },
      {
        id: 'benchmark-intel-tabs',
        number: 2,
        title: 'Readiness Perspectives',
        purpose: 'Switch between Readiness Score breakdown, Critical Gaps, and the strategic Improvement Roadmap.',
        tour_target: 'benchmark-intel-tabs',
        tour_location: 'Benchmark Intelligence > Tab Strip',
      },
      {
        id: 'benchmark-intel-meter',
        number: 3,
        title: 'Overall Readiness Meter',
        purpose: 'Visual indicator of current maturity rating compared against target college benchmarks.',
        tour_target: 'benchmark-intel-meter',
        tour_location: 'Benchmark Intelligence > Score Panel',
      },
      {
        id: 'benchmark-intel-pillars',
        number: 4,
        title: 'Pillar Performance Cards',
        purpose: 'Detailed assessment cards for Governance, Curriculum, Faculty, Students, Labs, Research, and Placement.',
        tour_target: 'benchmark-intel-pillars',
        tour_location: 'Benchmark Intelligence > Pillar Grid',
      },
    ],
  },

  'benchmark-studio': {
    menuKey: 'benchmark-studio',
    menuTitle: 'Benchmark Studio',
    menuPurpose: 'Standard benchmark catalog, indicators, origin sources, and applicability rules.',
    roles: STAFF_ROLES,
    steps: [
      {
        id: 'studio-header',
        number: 1,
        title: 'Benchmark Studio Catalogue',
        purpose: 'InGage standard benchmark catalogue every college is assessed against: manager-provided sources and indicators.',
        tour_target: 'studio-header',
        tour_location: 'Platform Modules > Benchmark Studio',
      },
      {
        id: 'studio-tabs',
        number: 2,
        title: 'Studio Sections',
        purpose: 'Navigate between Source Library, Benchmark Library, and Applicability Preview.',
        tour_target: 'studio-tabs',
        tour_location: 'Benchmark Studio > Section Tabs',
      },
      {
        id: 'studio-search',
        number: 3,
        title: 'Benchmark Explorer Search',
        purpose: 'Search standard indicators by code, indicator title, or source accreditation authority.',
        tour_target: 'studio-search',
        tour_location: 'Benchmark Studio > Search Bar',
      },
      {
        id: 'studio-table',
        number: 4,
        title: 'Indicators & Level Descriptors',
        purpose: 'Examine detailed criteria, L1-L3 maturity progression levels, and evidentiary documentation requirements.',
        tour_target: 'studio-table',
        tour_location: 'Benchmark Studio > Indicator Table',
      },
    ],
  },

  'benchmark-assessment': {
    menuKey: 'benchmark-assessment',
    menuTitle: 'Benchmark Assessment',
    menuPurpose: 'Assess a college against a published benchmark release across four separate assessment scores.',
    roles: 'all',
    steps: [
      {
        id: 'assessment-header',
        number: 1,
        title: 'Benchmark Assessment Engine',
        purpose: 'Evaluate a college’s evidence against a published benchmark release with four independent scores.',
        tour_target: 'assessment-header',
        tour_location: 'Platform Modules > Benchmark Assessment',
      },
      {
        id: 'assessment-college',
        number: 2,
        title: 'Institution & Assessment Cycle',
        purpose: 'Select the institution and assessment cycle under evaluation.',
        tour_target: 'assessment-college-select',
        tour_location: 'Benchmark Assessment > Selection Header',
      },
      {
        id: 'assessment-stages',
        number: 3,
        title: '5-Stage Assessment Workflow',
        purpose: 'Track cycle progress through Choose benchmarks, Upload evidence, InGage review, Scored, and Finalized.',
        tour_target: 'assessment-stages',
        tour_location: 'Benchmark Assessment > Lifecycle Bar',
      },
      {
        id: 'assessment-scorecard',
        number: 4,
        title: 'Scoring & Assessment Panels',
        purpose: 'Inspect domain scores, comparative benchmark performance, and evidence fulfillment.',
        tour_target: 'assessment-scorecard',
        tour_location: 'Benchmark Assessment > Scorecards',
      },
    ],
  },

  'transformation-plan': {
    menuKey: 'transformation-plan',
    menuTitle: 'Sprint Transformation Plan',
    menuPurpose: 'Sequenced initiatives across dated horizons (0-30, 30-60, 60-90, 90+ days) and score movement.',
    roles: 'all',
    steps: [
      {
        id: 'trans-header',
        number: 1,
        title: 'Transformation Plan Horizons',
        purpose: 'Audit recommendations sequenced into dated implementation horizons with projected score lifts.',
        tour_target: 'transformation-header',
        tour_location: 'Platform Modules > Sprint Transformation Plan',
      },
      {
        id: 'trans-generate',
        number: 2,
        title: 'Recalculate Horizons',
        purpose: 'Regenerate horizons and initiative sequencing whenever recommendations change.',
        tour_target: 'transformation-generate-btn',
        tour_location: 'Transformation Plan > Header Actions',
      },
      {
        id: 'trans-horizons',
        number: 3,
        title: 'Horizon Milestones',
        purpose: 'Expand Immediate (0-30 days), Near term (30-60 days), Consolidate (60-90 days), and Longer term (90+ days) initiatives.',
        tour_target: 'transformation-horizons',
        tour_location: 'Transformation Plan > Horizons List',
      },
      {
        id: 'trans-initiatives',
        number: 4,
        title: 'Initiative Ownership & Details',
        purpose: 'Review action steps, responsible owner roles, and targeted readiness impact for each initiative.',
        tour_target: 'transformation-initiatives',
        tour_location: 'Transformation Plan > Initiative Cards',
      },
    ],
  },

  'goals-tasks': {
    menuKey: 'goals-tasks',
    menuTitle: 'Goals & Tasks',
    menuPurpose: 'Track open gaps, extracted facts awaiting confirmation, and strategic audit goals.',
    roles: ALL_ROLES,
    steps: [
      {
        id: 'gt-header',
        number: 1,
        title: 'Goals & Tasks Tracking',
        purpose: 'Outstanding work items derived directly from active sprint facts, open gaps, and recommendations.',
        tour_target: 'goals-tasks-header',
        tour_location: 'Platform Modules > Goals & Tasks',
      },
      {
        id: 'gt-tabs',
        number: 2,
        title: 'Tasks vs Goals',
        purpose: 'Toggle between tactical tasks (unconfirmed facts, open gaps) and strategic goals (recommendations).',
        tour_target: 'goals-tasks-tabs',
        tour_location: 'Goals & Tasks > Tab Navigation',
      },
      {
        id: 'gt-filters',
        number: 3,
        title: 'Priority Filtering',
        purpose: 'Filter tasks by urgency: blocking items, high priority, medium, or optional tasks.',
        tour_target: 'goals-tasks-filters',
        tour_location: 'Goals & Tasks > Priority Pills',
      },
      {
        id: 'gt-list',
        number: 4,
        title: 'Actionable Tasks List',
        purpose: 'Review assignees, due dates, and click deep links directly into the workspace to resolve each item.',
        tour_target: 'goals-tasks-list',
        tour_location: 'Goals & Tasks > Work Items List',
      },
    ],
  },

  'ai-copilot': {
    menuKey: 'ai-copilot',
    menuTitle: 'AI Copilot',
    menuPurpose: 'Deterministic answers about institutional readiness and vector semantic search across uploaded evidence.',
    roles: 'all',
    steps: [
      {
        id: 'copilot-header',
        number: 1,
        title: 'AI Copilot Advisory Assistant',
        purpose: 'Answers readiness questions using verified figures from the live API and semantic search across institutional documents.',
        tour_target: 'copilot-header',
        tour_location: 'Platform Modules > AI Copilot',
      },
      {
        id: 'copilot-suggestions',
        number: 2,
        title: 'One-Tap Starter Queries',
        purpose: 'Click starter suggestions to immediately query current CRI scores, top gaps, missing documents, or next steps.',
        tour_target: 'copilot-suggestions',
        tour_location: 'AI Copilot > Starter Prompts',
      },
      {
        id: 'copilot-chat',
        number: 3,
        title: 'Evidence-Grounded Responses',
        purpose: 'Read verified answers with precise citations to source documents and page numbers.',
        tour_target: 'copilot-chat-area',
        tour_location: 'AI Copilot > Chat History',
      },
      {
        id: 'copilot-input',
        number: 4,
        title: 'Ask a Question',
        purpose: 'Type natural language inquiries about your institution’s readiness metrics, evidence, or gaps.',
        tour_target: 'copilot-input',
        tour_location: 'AI Copilot > Input Box',
      },
    ],
  },

  reminders: {
    menuKey: 'reminders',
    menuTitle: 'Reminders',
    menuPurpose: 'Standing alerts and overdue items derived from real sprint state and deadlines.',
    roles: ALL_ROLES,
    steps: [
      {
        id: 'reminders-header',
        number: 1,
        title: 'Reminders & Alerts',
        purpose: 'Standing alert overview identifying overdue evidence requests, unconfirmed facts, and blocking gaps.',
        tour_target: 'reminders-header',
        tour_location: 'Platform Modules > Reminders',
      },
      {
        id: 'reminders-filters',
        number: 2,
        title: 'Severity Filtering',
        purpose: 'Filter reminders by urgency: Critical (blocking items), High (impending due dates), or Medium.',
        tour_target: 'reminders-filters',
        tour_location: 'Reminders > Severity Pills',
      },
      {
        id: 'reminders-list',
        number: 3,
        title: 'Actionable Alert Cards',
        purpose: 'Click directly on any alert card to navigate to the specific screen that resolves the item.',
        tour_target: 'reminders-list',
        tour_location: 'Reminders > Alerts List',
      },
    ],
  },

  'compliance-mapping': {
    menuKey: 'compliance-mapping',
    menuTitle: 'Compliance Mapping',
    menuPurpose: 'Accreditation evidence mapping across NAAC, AICTE, NIRF, and institutional frameworks.',
    roles: 'all',
    steps: [
      {
        id: 'compliance-header',
        number: 1,
        title: 'Compliance & Accreditation Mapping',
        purpose: 'Map audited institutional documents and findings against regulatory accreditation frameworks.',
        tour_target: 'compliance-header',
        tour_location: 'Platform Modules > Compliance Mapping',
      },
      {
        id: 'compliance-frameworks',
        number: 2,
        title: 'Accreditation Frameworks',
        purpose: 'Track evidence coverage for NAAC, AICTE, and NIRF criteria based on ingested documents.',
        tour_target: 'compliance-frameworks',
        tour_location: 'Compliance Mapping > Framework Cards',
      },
      {
        id: 'compliance-status',
        number: 3,
        title: 'Document Coverage & Missing Evidence',
        purpose: 'Review covered required documents alongside flagged accreditation gaps to ensure compliance readiness.',
        tour_target: 'compliance-status',
        tour_location: 'Compliance Mapping > Evidence Breakdown',
      },
    ],
  },

  'uat-readiness': {
    menuKey: 'uat-readiness',
    menuTitle: 'UAT Readiness',
    menuPurpose: 'Engagement verification checklist to confirm whether an institution’s audit is ready for sign-off.',
    roles: ALL_ROLES,
    steps: [
      {
        id: 'uat-header',
        number: 1,
        title: 'Engagement Handover Readiness',
        purpose: 'Automated verification dashboard assessing whether the sprint meets all requirements for client handover.',
        tour_target: 'uat-header',
        tour_location: 'Platform Modules > UAT Readiness',
      },
      {
        id: 'uat-meter',
        number: 2,
        title: 'Readiness Meter & Metrics',
        purpose: 'Track overall readiness percentage and count of passing versus blocking audit requirements.',
        tour_target: 'uat-meter',
        tour_location: 'UAT Readiness > Readiness Meter',
      },
      {
        id: 'uat-checklist',
        number: 3,
        title: 'Automated Verification Checks',
        purpose: 'Review status of documents uploaded, facts reviewed, gaps resolved, baseline approved, and report generated.',
        tour_target: 'uat-checklist',
        tour_location: 'UAT Readiness > Verification Checklist',
      },
    ],
  },

  'admin-settings': {
    menuKey: 'admin-settings',
    menuTitle: 'Settings',
    menuPurpose: 'Account settings, role access matrix, scoring rubric configuration, user management, and AI usage.',
    roles: 'all',
    steps: [
      {
        id: 'settings-header',
        number: 1,
        title: 'Administration & Settings',
        purpose: 'Manage your account, view permissions, configure scoring rubrics, and administer platform users.',
        tour_target: 'settings-header',
        tour_location: 'Platform Modules > Settings',
      },
      {
        id: 'settings-tabs',
        number: 2,
        title: 'Authorized Settings Tabs',
        purpose: 'Switch between Account, Role & Access Matrix, Rubric weights, User Administration, and AI Usage (based on permissions).',
        tour_target: 'settings-tabs',
        tour_location: 'Settings > Tab Strip',
      },
      {
        id: 'settings-content',
        number: 3,
        title: 'Configuration Workspace',
        purpose: 'Update password, review role privileges, manage college accounts, or inspect AI token usage metrics.',
        tour_target: 'settings-content',
        tour_location: 'Settings > Active Tab Panel',
      },
    ],
  },
};

// Capability routes replace the historical CRI/approval sequence for the administrator experience.
for (const key of ['sprint-score', 'sprint-recommendations', 'sprint-report', 'cri-benchmark-intelligence', 'transformation-plan', 'goals-tasks'] as MenuKey[]) {
  MENU_TOURS[key] = {
    menuKey: key, menuTitle: key === 'sprint-report' ? 'Capability Report & Export' : 'Institutional AI Capability',
    menuPurpose: 'Frozen evidence, capability bounds and grounded conditional pathways without a baseline approval gate.',
    roles: 'all', steps: [
      { id: `${key}-history`, number: 1, title: 'Select an assessment', purpose: 'Select a frozen assessment and reference period. Failed or cancelled runs do not publish scores.', tour_target: 'capability-history', tour_location: 'Capability > History' },
      { id: `${key}-start`, number: 2, title: 'Explicit assessment start', purpose: 'Confirm scope and period before starting. Model calls use configured credits; reading and refreshing do not.', tour_target: 'capability-start', tour_location: 'Capability > Start assessment' },
      { id: `${key}-standing`, number: 3, title: 'Evidence and capability are separate', purpose: 'Capability bounds preserve unresolved evidence. Experimental tiers are not accreditation standards.', tour_target: 'capability-header', tour_location: 'Capability > Standing' },
    ],
  };
}
MENU_TOURS.dashboard.steps = MENU_TOURS.dashboard.steps.map(step => step.id === 'dashboard-metrics' ? { ...step, purpose: 'Platform counts and the selected institution’s frozen capability assessment; no averaged legacy CRI headline.' } : step);
MENU_TOURS['sprint-approval'].menuTitle = 'Legacy Baseline Approval';

export const ALL_MENU_TOURS: MenuTourConfig[] = Object.values(MENU_TOURS);

function canRoleAccess(roles?: readonly UserRole[] | readonly string[] | 'all', role?: UserRole): boolean {
  if (!roles || !role || roles === 'all') return true;
  return (roles as readonly string[]).includes(role);
}

/**
 * Generates a role-aware tour of the platform's main navigation menus.
 * Highlights one accessible navbar/sidebar menu item at a time without navigating away.
 */
export function getNavigationTour(role?: UserRole): MenuTourConfig {
  const steps: MenuTourStep[] = [];
  let num = 1;

  // 1. Dashboard
  if (canRoleAccess(MENU_TOURS.dashboard.roles, role)) {
    steps.push({
      id: 'nav-tour-dashboard',
      number: num++,
      title: 'Dashboard',
      purpose: 'Selected institution capability, evidence resolution and sprint metrics.',
      tour_target: 'nav-dashboard',
      tour_location: 'Main Navigation > Cockpit',
    });
  }

  // 2. Institution DNA
  if (canRoleAccess(MENU_TOURS['institution-dna'].roles, role)) {
    steps.push({
      id: 'nav-tour-institution-dna',
      number: num++,
      title: 'Institution DNA',
      purpose: 'Profile your institution profile, campus departments, leadership, student intake, and digital baseline.',
      tour_target: 'nav-institution-dna',
      tour_location: 'Main Navigation > Platform Modules',
    });
  }

  // 3. AI Readiness Audit Header
  steps.push({
    id: 'nav-tour-audit-module',
    number: num++,
    title: 'AI Readiness Audit',
    purpose: 'The central discovery audit workspace containing the sequence of steps from data upload to report export.',
    tour_target: 'module-ai-readiness-audit',
    tour_location: 'Main Navigation > Core Audit',
  });

  // Sprint Steps
  const SPRINT_STEPS: { key: MenuKey; title: string; purpose: string }[] = [
    {
      key: 'sprint-setup',
      title: '1. Sprint Setup',
      purpose: 'Configure a new discovery sprint, select evaluation academic years, and define audit scope.',
    },
    {
      key: 'sprint-upload',
      title: '2. Upload Data Pack',
      purpose: 'Upload institutional PDFs (NAAC SSR, AQAR, syllabi) or sync directly with Google Drive.',
    },
    {
      key: 'sprint-monitor',
      title: '3. AI Processing Monitor',
      purpose: 'Monitor real-time document OCR extraction, vision fallback, text chunking, and fact extraction jobs.',
    },
    {
      key: 'evidence-intelligence',
      title: '4. Evidence Intelligence',
      purpose: 'Interactive evidence graph linking uploaded institutional documents directly to AI-QIF readiness criteria.',
    },
    {
      key: 'sprint-facts',
      title: '5. Extracted Facts Review',
      purpose: 'Review and verify facts extracted by AI from uploaded files with source page citations.',
    },
    {
      key: 'evidence-requests',
      title: '6. Evidence Requests',
      purpose: 'Track and assign requests for missing institutional evidence or clarifications directly to department owners.',
    },
    {
      key: 'sprint-gaps',
      title: '7. Gap Dashboard',
      purpose: 'Inspect legacy fact-review gaps. Capability evidence distinguishes missing evidence from documented shortfalls.',
    },
    {
      key: 'sprint-confirmation',
      title: '8. Owner Workspace',
      purpose: 'Dedicated confirmation queue for department owners to sign off on extracted facts and evidence.',
    },
    {
      key: 'sprint-score',
      title: '9. Capability & Evidence',
      purpose: 'Frozen capability bounds and evidence decisions for all 36 indicators. New evidence needs a new explicit assessment.',
    },
    {
      key: 'sprint-approval',
      title: '10. Legacy Baseline Approval',
      purpose: 'Historical CRI approval only. Capability recommendations and report export do not require this step.',
    },
    {
      key: 'sprint-recommendations',
      title: '11. Recommendations',
      purpose: 'Explore AI-recommended transformation initiatives and interventions customized for your institution.',
    },
    {
      key: 'sprint-report',
      title: '12. Report & Export',
      purpose: 'Generate, preview, and download formal executive presentations and comprehensive audit PDF packs.',
    },
  ];

  for (const item of SPRINT_STEPS) {
    const config = MENU_TOURS[item.key];
    if (config && canRoleAccess(config.roles, role)) {
      steps.push({
        id: `nav-tour-${item.key}`,
        number: num++,
        title: item.title,
        purpose: item.purpose,
        tour_target: `nav-${item.key}`,
        tour_location: 'AI Readiness Audit > Sprint Steps',
      });
    }
  }

  // Other Platform Modules
  const MODULES: { key: MenuKey; title: string; purpose: string; location: string }[] = [
    {
      key: 'cri-benchmark-intelligence',
      title: 'CRI & Benchmark Intelligence',
      purpose: 'Compare institutional readiness metrics against peer group percentiles and national averages.',
      location: 'Main Navigation > Intelligence',
    },
    {
      key: 'benchmark-studio',
      title: 'Benchmark Studio',
      purpose: 'InGage administration workspace to configure indicator criteria, evaluation rubrics, and weightings.',
      location: 'Main Navigation > Administration',
    },
    {
      key: 'benchmark-assessment',
      title: 'Benchmark Assessment',
      purpose: 'Conduct structured readiness evaluations and view multi-dimensional gap assessments.',
      location: 'Main Navigation > Assessments',
    },
    {
      key: 'transformation-plan',
      title: 'Sprint Transformation Plan',
      purpose: 'Translate audit recommendations into concrete institutional roadmaps with milestones and target dates.',
      location: 'Main Navigation > Strategy',
    },
    {
      key: 'goals-tasks',
      title: 'Goals & Tasks',
      purpose: 'Operational workboard to assign and track audit tasks, evidence uploads, and verification duties.',
      location: 'Main Navigation > Workspace',
    },
    {
      key: 'ai-copilot',
      title: 'AI Copilot',
      purpose: 'Chat directly with the AI Copilot to ask questions about your documents, CRI scores, or audit guidelines.',
      location: 'Main Navigation > Workspace',
    },
    {
      key: 'reminders',
      title: 'Reminders',
      purpose: 'Keep track of upcoming deadlines, pending review queues, and sprint milestone dates.',
      location: 'Main Navigation > Workspace',
    },
    {
      key: 'compliance-mapping',
      title: 'Compliance Mapping',
      purpose: 'Cross-reference institutional readiness data against NAAC, NBA, and NIRF accreditation criteria.',
      location: 'Main Navigation > Compliance',
    },
    {
      key: 'uat-readiness',
      title: 'UAT Readiness',
      purpose: 'Verify system readiness checklist and track sign-offs before formal audits.',
      location: 'Main Navigation > Verification',
    },
    {
      key: 'admin-settings',
      title: 'Settings',
      purpose: 'Manage your user profile, view role access permissions, and configure organization settings.',
      location: 'Main Navigation > Administration',
    },
  ];

  for (const mod of MODULES) {
    const config = MENU_TOURS[mod.key];
    if (config && canRoleAccess(config.roles, role)) {
      steps.push({
        id: `nav-tour-${mod.key}`,
        number: num++,
        title: mod.title,
        purpose: mod.purpose,
        tour_target: `nav-${mod.key}`,
        tour_location: mod.location,
      });
    }
  }

  // Top Bar controls
  steps.push({
    id: 'nav-tour-persistent-tour-btn',
    number: num++,
    title: 'Product Tour (Top Bar)',
    purpose: 'Replay this platform navigation tour anytime by clicking this button in the top bar.',
    tour_target: 'persistent-tour-btn',
    tour_location: 'Top Navigation Bar',
  });

  steps.push({
    id: 'nav-tour-workflow-guide-btn',
    number: num++,
    title: 'Workflow Guide (Top Bar)',
    purpose: 'Open the 11-step audit workflow guide drawer anytime to check real platform progress and next actionable steps.',
    tour_target: 'workflow-guide-btn',
    tour_location: 'Top Navigation Bar',
  });

  return {
    menuKey: 'navigation-tour' as any,
    menuTitle: 'Platform Navigation Tour',
    menuPurpose: 'Guided walkthrough of the platform sidebar menus, modules, and top controls.',
    roles: 'all',
    steps,
  };
}

/**
 * Retrieve the curated tour configuration for a given menu, checking that the user's role
 * is authorized to view that menu.
 */
export function getMenuTour(menuKey: string | null | undefined, role?: UserRole): MenuTourConfig | null {
  if (!menuKey) return null;
  if (menuKey === 'navigation-tour') return getNavigationTour(role);
  const config = MENU_TOURS[menuKey as MenuKey];
  if (!config) return null;
  if (!role) return config;
  if (config.roles === 'all') return config;
  if (Array.isArray(config.roles) && !config.roles.includes(role)) return null;
  return config;
}
