import {
  Layers, Target, ListChecks, Bot, Bell, Network, ClipboardCheck, Settings,
  Award, BookOpen,
} from 'lucide-react';

/**
 * Design previews for the modules that are in the product plan but NOT built.
 *
 * These are **proposals**, not specifications. The plan gave module names; the
 * flows below are this team's suggested interpretation of each one, written so
 * they can be reviewed and corrected before any code is committed to them.
 * Every preview screen says so, loudly — nothing here is working software and
 * nothing here should be read as an agreed scope.
 *
 * Deliberately contains **no numbers that could pass for data**. Wireframe
 * labels describe what a field is ("Overall CRI score"), never what it says —
 * the same "never fabricate a value" stance the extraction and scoring layers
 * take. A screenshot of this page must not be mistakable for a screenshot of
 * the product.
 */

type LucideIcon = typeof Layers;

/** Wireframe primitives. Enough shapes to make a screen recognisable at a
 * glance, few enough that a reviewer reads the labels rather than the art. */
export type BlockType =
  | 'title' | 'text' | 'card' | 'table' | 'chart' | 'button' | 'input' | 'list' | 'split';

export interface WireBlock {
  type: BlockType;
  label: string;
}

export interface FlowStep {
  title: string;
  /** Who is acting — a role from the platform's existing 11, or "System". */
  actor: string;
  detail: string;
  screen: WireBlock[];
}

export interface ModuleFlow {
  key: string;
  label: string;
  icon: LucideIcon;
  status: 'next' | 'planned';
  /** One line: what this module is for. */
  purpose: string;
  /** The problem it solves — the reason to build it at all. */
  problem: string;
  /** Where the flow came from, when it is NOT this team's own proposal —
   * e.g. a prototype handed over for reference. Rendered prominently, because
   * "we read this off your prototype" and "we made this up" deserve very
   * different weight in a review. */
  basedOn?: string;
  steps: FlowStep[];
  /** What must exist first. Honest about ordering. */
  dependsOn: string[];
  /** What is already built that this module would reuse rather than rebuild. */
  reuses: string[];
  /** The decisions we need from the reviewer before building. */
  questions: string[];
}

export const MODULE_FLOWS: ModuleFlow[] = [
  {
    key: 'evidence-intelligence',
    label: 'Evidence Intelligence',
    icon: Layers,
    status: 'next',
    purpose:
      'Ask a question in plain English and get back the exact passages from the college’s own uploaded documents that answer it — each one citable to a file and page.',
    problem:
      'Today a consultant who wants to check "what AI training has the faculty actually had?" must open every uploaded PDF and read. The facts the audit extracted are structured but narrow; the documents hold far more than the extractor was asked to pull out.',
    steps: [
      {
        title: 'Index the sprint’s documents',
        actor: 'System (automatic)',
        detail:
          'When a document finishes AI processing, its text is split into page-bounded chunks and indexed for meaning-based search. Nothing is asked of the user. This half is already built and tested.',
        screen: [
          { type: 'title', label: 'Document indexing status' },
          { type: 'table', label: 'Document name | Pages | Chunks indexed | Status' },
          { type: 'text', label: 'Re-index this sprint (only re-processes changed documents)' },
          { type: 'button', label: 'Re-index' },
        ],
      },
      {
        title: 'Ask a question',
        actor: 'Consultant / Institution Admin',
        detail:
          'A free-text question, optionally narrowed to one document type or to this sprint only. Results come back ranked by relevance.',
        screen: [
          { type: 'title', label: 'Evidence search' },
          { type: 'input', label: 'e.g. "faculty AI certification and training programmes"' },
          { type: 'split', label: 'Filter: document type | Scope: this sprint / all sprints' },
          { type: 'button', label: 'Search' },
        ],
      },
      {
        title: 'Read the evidence, with its source',
        actor: 'Consultant',
        detail:
          'Each result shows the passage, the document it came from, and the page number — so a claim in the final report can always be traced back to a page a reviewer can open.',
        screen: [
          { type: 'list', label: 'Result: passage text' },
          { type: 'text', label: 'Source: document name · page number · relevance' },
          { type: 'button', label: 'Open source document at that page' },
          { type: 'button', label: 'Attach as evidence to a fact or gap' },
        ],
      },
      {
        title: 'Attach evidence where it counts',
        actor: 'Consultant',
        detail:
          'A found passage can be pinned to an unconfirmed fact or an open gap, which is what turns search into audit progress rather than a side tool.',
        screen: [
          { type: 'card', label: 'Gap: "No evidence of faculty AI training"' },
          { type: 'list', label: 'Attached evidence — passage + source citation' },
          { type: 'button', label: 'Resolve gap using this evidence' },
        ],
      },
    ],
    dependsOn: ['AI Readiness Audit (documents must be uploaded and processed first)'],
    reuses: [
      'The document indexing and semantic search layer — already built, tested and committed',
      'The existing gap and fact review screens — evidence attaches to them rather than a new record type',
    ],
    questions: [
      'Should search cover all of an institution’s past sprints by default, or only the current one?',
      'Who should be allowed to search — every institution member, or consultants only?',
      'Should attaching evidence auto-resolve the gap, or only mark it ready for review?',
    ],
  },

  {
    key: 'cri-benchmark-intelligence',
    label: 'CRI & Benchmark Intelligence',
    icon: Award,
    status: 'planned',
    basedOn:
      'The InGage “AI Future Ready” prototype (CriBenchmarkIntelligence page). The flow, the eight domains and the scoring rules below are read off that prototype, not proposed by this team.',
    purpose:
      'Score an institution against the published benchmark library and show the result: an overall Campus Readiness Index, a domain breakdown, the gaps behind it, and the roadmap that closes them.',
    problem:
      'The audit today scores an institution against its own confirmed facts. It cannot answer "compared to what?" — there is no external standard in the system. This module supplies one.',
    steps: [
      {
        title: 'CRI score card',
        actor: 'Institution Admin / Leadership',
        detail:
          'One headline index out of 100, broken down across eight weighted domains — Governance, Curriculum, Faculty, Student, Infrastructure, Research, Industry, Evidence Quality — each showing its weight and how many benchmarks were actually evaluated.',
        screen: [
          { type: 'title', label: 'Overall Campus Readiness Index — score out of 100' },
          { type: 'card', label: 'Gate failures and the penalty each one applied' },
          { type: 'chart', label: 'Domain readiness breakdown — eight weighted domains' },
          { type: 'button', label: 'Recalculate CRI' },
        ],
      },
      {
        title: 'Where the score came from',
        actor: 'System (deterministic)',
        detail:
          'Each applicable benchmark is placed at a maturity level, which becomes a score; domain scores are weighted; then hard and soft gates deduct a penalty. Non-applicable benchmarks are excluded rather than scored zero. Every step is replayable — no model judgement anywhere.',
        screen: [
          { type: 'table', label: 'Benchmark | Current level | Target level | Gate status | Weighted score' },
          { type: 'text', label: 'Each row states in plain words why it scored what it scored' },
        ],
      },
      {
        title: 'Gap analysis',
        actor: 'Consultant / Institution Admin',
        detail:
          'Every benchmark below its target becomes a gap, carrying its severity, what evidence is missing, what capability is absent, what it depends on, the effort band, and how many CRI points it is costing.',
        screen: [
          { type: 'list', label: 'Gap: benchmark, severity, current level vs target level' },
          { type: 'card', label: 'Evidence gaps · capability gaps · dependencies · CRI points at stake' },
        ],
      },
      {
        title: 'Transformation roadmap',
        actor: 'Consultant',
        detail:
          'Each gap maps to a named initiative with an owner, a timeline and an estimated CRI lift — which is the handover point into the Transformation Plan module.',
        screen: [
          { type: 'table', label: 'Initiative | Priority | Owner | Timeline | Estimated CRI lift' },
        ],
      },
    ],
    dependsOn: [
      'Benchmark Studio — there is nothing to score against until a benchmark library is published',
      'AI Readiness Audit — the evidence that places a benchmark at a level comes from uploaded documents',
    ],
    reuses: [
      'The audit’s confirmed facts and documents, as the evidence behind each benchmark level',
      'The existing deterministic-scoring discipline: replayable, explainable, no AI in the score itself',
    ],
    questions: [
      'This is a SECOND scoring model. The platform already computes a CRI from 8 pillars and their criteria; this computes one from benchmarks and maturity levels. Does the new model replace the existing engine, or run beside it? The two will not agree, and a client seeing two different CRI numbers is a serious problem.',
      'The prototype numbers maturity levels L3 → L2 → L1 with **L1 as the highest**. That is the reverse of how most people read "level 1". Confirm before it reaches a client report.',
      'Who sets an institution’s target level per benchmark — the consultant, or a rule?',
      'Gate penalties are deducted from the overall score. Should a client-facing report show the penalty explicitly, or only the final number?',
    ],
  },

  {
    key: 'benchmark-studio',
    label: 'Benchmark Studio',
    icon: BookOpen,
    status: 'planned',
    basedOn:
      'The InGage “AI Future Ready” prototype (BenchmarkStudio page, 7 tabs). The lifecycle, governance roles and source model below are read off that prototype, not proposed by this team.',
    purpose:
      'The internal tool where InGage authors, sources, versions, approves and publishes the benchmark library that every client institution is then scored against.',
    problem:
      'A benchmark library is the company’s core IP. It cannot live in a spreadsheet: it needs traceable sources, reviewed wording, version history, and an approval trail — because a published benchmark changes every client’s score.',
    steps: [
      {
        title: 'Browse and filter the library',
        actor: 'Benchmark Editor',
        detail:
          'Every benchmark, filterable by lifecycle state, domain, criticality, authority and confidence. Each carries a code such as GOV.STR.001, placing it in the ontology.',
        screen: [
          { type: 'input', label: 'Search benchmarks' },
          { type: 'split', label: 'Status | Domain · Criticality · Authority' },
          { type: 'table', label: 'Code | Title | Domain | Criticality | Lifecycle state' },
        ],
      },
      {
        title: 'Define the benchmark and its three levels',
        actor: 'Benchmark Editor',
        detail:
          'A definition and rationale, then three maturity levels — Foundational, Good, Advanced — each with observable requirements, minimum evidence, expected outcomes, and explicit non-examples of what does NOT count.',
        screen: [
          { type: 'input', label: 'Title · code · definition · rationale' },
          { type: 'card', label: 'Level: title, definition, observable requirements' },
          { type: 'list', label: 'Minimum evidence required at this level' },
          { type: 'text', label: 'Non-examples — what does not count as meeting this level' },
        ],
      },
      {
        title: 'Cite the authority behind it',
        actor: 'Source Reviewer',
        detail:
          'Each benchmark links to registered sources — regulatory, accreditation, research, or InGage methodology — down to the individual claim and page. A source can support or contradict a benchmark, and sources go stale and need re-review.',
        screen: [
          { type: 'table', label: 'Source | Type | Authority | Published | Status' },
          { type: 'card', label: 'Claim text · page reference · confidence · validated by' },
          { type: 'split', label: 'Relationship: supports / contradicts | Review status' },
        ],
      },
      {
        title: 'Review, approve, publish — then it is frozen',
        actor: 'Methodology Reviewer → Approver → Publisher',
        detail:
          'A benchmark moves through an explicit lifecycle from draft to published. **A published benchmark is immutable** — changing it means creating a new version, so no client’s past score can be quietly rewritten.',
        screen: [
          { type: 'list', label: 'Pending approval requests, with requester and comments' },
          { type: 'split', label: 'Approve | Reject · Request changes' },
          { type: 'table', label: 'Version | Change note | Published at | Immutable' },
        ],
      },
      {
        title: 'AI-proposed candidates, with a critic and a simulator',
        actor: 'AI agent, reviewed by a human',
        detail:
          'An agent proposes new benchmarks from the source registry. An adversarial critic flags weak ones — levels that are not distinguishable, overlap with an existing benchmark — and an impact simulator estimates what adding it would do to every client’s score before anyone commits.',
        screen: [
          { type: 'card', label: 'Candidate: suggested title, code, three draft levels' },
          { type: 'list', label: 'Critic findings — severity, the problem, the suggested fix' },
          { type: 'card', label: 'Impact simulation: institutions affected, expected CRI movement, risk' },
          { type: 'button', label: 'Convert to draft benchmark' },
        ],
      },
    ],
    dependsOn: [
      'An agreed ontology — the domain/category tree every benchmark code hangs off',
      'The nine governance roles in the prototype, which do not exist in this platform’s current role model',
    ],
    reuses: [
      'The immutability and append-only audit pattern already used for baseline approval',
      'The document search layer — already built — for pulling claims out of source documents',
    ],
    questions: [
      'The prototype defines **nine** governance roles (editor, source reviewer, methodology reviewer, approver, publisher, auditor, and more). This platform has eleven roles, none of which are these. Do we add them, or map the new duties onto existing roles?',
      'When a published benchmark is revised, what happens to institutions already scored against the old version — re-score, or leave the old assessment standing?',
      'Who owns the library day to day, and how many benchmarks should v1 ship with? The prototype seeds twelve.',
      'Is this screen InGage-internal only, forever? If so it should sit behind a separate entry point, not in a client’s menu.',
    ],
  },

  {
    key: 'transformation-plan',
    label: 'Transformation Plan',
    icon: Target,
    status: 'planned',
    purpose:
      'Turn the audit’s recommendations into a phased, dated roadmap the institution actually commits to.',
    problem:
      'The audit currently ends with a list of recommendations and a report. Nothing sequences them, assigns them a phase, or tracks whether the institution ever acted — so the engagement stops at the diagnosis.',
    steps: [
      {
        title: 'Pull in the approved recommendations',
        actor: 'System',
        detail:
          'Every recommendation generated at the end of the audit appears as a candidate item. Nothing is invented here — the plan is built from what the audit already produced.',
        screen: [
          { type: 'title', label: 'Build transformation plan' },
          { type: 'table', label: 'Recommendation | Pillar | Priority | Include?' },
        ],
      },
      {
        title: 'Sequence into phases',
        actor: 'Consultant',
        detail:
          'Each item is dragged into a phase — for example Quick Wins (0–3 months), Foundation (3–9), Scale (9–18). Phase names and durations to be confirmed.',
        screen: [
          { type: 'split', label: 'Phase 1 | Phase 2 | Phase 3 — drag items between columns' },
          { type: 'card', label: 'Item card: title, pillar, owner role, effort estimate' },
        ],
      },
      {
        title: 'Assign owners and target dates',
        actor: 'Consultant + Institution Admin',
        detail:
          'Each item gets an accountable role and a target date. Owner roles already exist in the platform — the same ones the audit assigns to gaps.',
        screen: [
          { type: 'table', label: 'Item | Owner role | Target date | Dependency' },
          { type: 'button', label: 'Publish plan to the institution' },
        ],
      },
      {
        title: 'Track progress against the baseline',
        actor: 'Institution Admin',
        detail:
          'The plan shows what has moved. The intent is to re-run the CRI score at the end of a phase and show the delta against the approved baseline.',
        screen: [
          { type: 'chart', label: 'CRI score at baseline vs. current — by pillar' },
          { type: 'text', label: 'Items completed / in progress / not started, per phase' },
        ],
      },
    ],
    dependsOn: [
      'AI Readiness Audit — needs approved recommendations and a locked baseline',
      'Goals & Tasks — if plan items are to break down into assignable work',
    ],
    reuses: [
      'The recommendation generator and its consultant-editing screen',
      'The approved baseline, which is already immutable and version-fingerprinted — the correct thing to measure progress against',
    ],
    questions: [
      'What are the agreed phase names and durations?',
      'Should a plan item be assignable to a named person, or stay at role level as the audit does?',
      'Does re-scoring at the end of a phase create a new sprint, or a new scoring run inside the same one?',
    ],
  },

  {
    key: 'goals-tasks',
    label: 'Goals & Tasks',
    icon: ListChecks,
    status: 'planned',
    purpose:
      'The working layer beneath the plan — individual tasks with a named owner, a due date, and a state.',
    problem:
      'A transformation plan item like "establish an AI governance committee" is months of work by several people. Without a task layer the plan is a wish list nobody can act on day to day.',
    steps: [
      {
        title: 'Break a plan item into tasks',
        actor: 'Consultant / Institution Admin',
        detail:
          'A plan item opens into a task list. Tasks can also be created standalone, for work the audit never surfaced.',
        screen: [
          { type: 'card', label: 'Plan item: title, phase, owner role' },
          { type: 'list', label: 'Task rows — title, assignee, due date, status' },
          { type: 'button', label: 'Add task' },
        ],
      },
      {
        title: 'Assign and schedule',
        actor: 'Institution Admin',
        detail:
          'Each task goes to a named user with a due date. This is the first place the platform would assign work to a *person* rather than a role — a decision worth confirming.',
        screen: [
          { type: 'input', label: 'Task title' },
          { type: 'split', label: 'Assignee (user) | Due date | Priority' },
          { type: 'button', label: 'Save task' },
        ],
      },
      {
        title: 'Work the board',
        actor: 'Any assigned user',
        detail:
          'A personal view of "what is assigned to me", plus an institution-wide board grouped by status or by phase.',
        screen: [
          { type: 'split', label: 'To do | In progress | Blocked | Done' },
          { type: 'card', label: 'Task card: title, assignee avatar, due date' },
        ],
      },
      {
        title: 'Roll progress back up',
        actor: 'System',
        detail:
          'Completing tasks advances the parent plan item, which advances the phase — so the plan reflects reality without anyone updating it twice.',
        screen: [
          { type: 'text', label: 'Plan item progress, derived from its task states' },
          { type: 'chart', label: 'Phase completion over time' },
        ],
      },
    ],
    dependsOn: ['Transformation Plan — tasks hang off plan items'],
    reuses: [
      'The user and role model — all 11 roles and institution scoping already exist',
      'The append-only history pattern used by fact review, for a task audit trail',
    ],
    questions: [
      'Are tasks assigned to named users, or kept at role level like the rest of the platform?',
      'Do we need file attachments and comments on a task, or is a title and a status enough for v1?',
      'Should a task be able to exist without a parent plan item?',
    ],
  },

  {
    key: 'ai-chatbot',
    label: 'AI Chatbot',
    icon: Bot,
    status: 'planned',
    purpose:
      'A conversational way to ask about an institution’s readiness — answered only from that institution’s own audited data, with sources shown.',
    problem:
      'A principal will not read a 40-page report to ask one question. They want to type "where are we weakest?" and get a straight answer they can trust.',
    steps: [
      {
        title: 'Ask a question',
        actor: 'Any institution member',
        detail:
          'A chat panel, scoped to one institution. The user does not choose a data source — the assistant decides what to look at.',
        screen: [
          { type: 'title', label: 'Ask about this institution' },
          { type: 'input', label: 'e.g. "Which pillar is our weakest and why?"' },
        ],
      },
      {
        title: 'Answer from audited data only',
        actor: 'System',
        detail:
          'The assistant reads the confirmed facts, the CRI pillar scores, the open gaps, and the indexed document passages — never the open internet, and never another institution’s data.',
        screen: [
          { type: 'text', label: 'Answer paragraph' },
          { type: 'list', label: 'Sources: pillar score / confirmed fact / document + page' },
        ],
      },
      {
        title: 'Say when it does not know',
        actor: 'System',
        detail:
          'If the data does not support an answer, it says so and points at the gap that would need closing — rather than guessing. This matches the anti-fabrication rule the extraction and scoring layers already enforce.',
        screen: [
          { type: 'card', label: '"I cannot answer that yet — 3 facts are unconfirmed."' },
          { type: 'button', label: 'Open the related gap' },
        ],
      },
    ],
    dependsOn: [
      'Evidence Intelligence — the document retrieval layer it would read from',
      'AI Readiness Audit — a completed sprint, or there is nothing to answer from',
    ],
    reuses: [
      'The document search layer — already built, including the guarantee that one college can never read another’s documents',
      'The existing multi-provider AI setup (OpenAI / Anthropic), so no new vendor decision is needed',
    ],
    questions: [
      'Should it answer only from audited data, or also explain general AI-readiness concepts?',
      'Is chat history saved per user, or cleared each session?',
      'Which roles get access — everyone, or leadership and consultants only?',
    ],
  },

  {
    key: 'reminders',
    label: 'Reminders',
    icon: Bell,
    status: 'planned',
    purpose:
      'Nudge the right person when something is waiting on them, so a sprint does not stall silently.',
    problem:
      'A sprint currently stalls without anyone noticing — unconfirmed facts and unresolved gaps sit until a consultant chases by phone. There is no notification of any kind in the platform today.',
    steps: [
      {
        title: 'Detect what is waiting',
        actor: 'System (scheduled)',
        detail:
          'A recurring job finds items that are overdue or idle: gaps unresolved past a threshold, facts unconfirmed, a baseline awaiting approval, a plan task past its due date.',
        screen: [
          { type: 'table', label: 'Trigger | Condition | Who it notifies' },
        ],
      },
      {
        title: 'Notify the owner',
        actor: 'System',
        detail:
          'The owner role already recorded on each gap and fact decides who is told. Channel to be confirmed — in-app only, or email as well.',
        screen: [
          { type: 'card', label: 'In-app: bell icon with unread count' },
          { type: 'list', label: '"5 facts await your confirmation — Sprint SPR-XXXX"' },
        ],
      },
      {
        title: 'Act from the notification',
        actor: 'Assigned user',
        detail:
          'Each notification links directly to the screen where the item can be actioned, rather than dropping the user on a dashboard to hunt for it.',
        screen: [
          { type: 'button', label: 'Go to Owner Workspace' },
          { type: 'text', label: 'Mark read · Snooze · Reassign' },
        ],
      },
    ],
    dependsOn: [
      'A scheduled-job runner — not configured today, and a deliberate omission so far',
      'An email provider, if reminders are to leave the app — none is configured',
    ],
    reuses: [
      'Owner roles already recorded on every gap and fact — the routing question is already answered',
      'The existing background-job infrastructure, which would host the scheduled check',
    ],
    questions: [
      'In-app only, or email too? Email needs a provider decision and a sending domain.',
      'What are the thresholds — how many days idle before a gap is chased?',
      'Daily digest, or one notification per event?',
    ],
  },

  {
    key: 'compliance-mapping',
    label: 'Compliance Mapping',
    icon: Network,
    status: 'planned',
    purpose:
      'Show how the institution’s AI-readiness evidence maps onto the accreditation frameworks it is already assessed against.',
    problem:
      'Colleges care about NAAC, NBA and NIRF. If the same uploaded evidence can be shown against those criteria, the audit stops being an extra exercise and starts saving them work they already had to do.',
    steps: [
      {
        title: 'Choose a framework',
        actor: 'Consultant',
        detail:
          'The institution selects which framework and cycle applies. The criteria set for each framework would need to be loaded as configuration — it is not in the platform today.',
        screen: [
          { type: 'title', label: 'Compliance mapping' },
          { type: 'split', label: 'Framework: NAAC / NBA / NIRF | Cycle / version' },
        ],
      },
      {
        title: 'Map criteria to evidence',
        actor: 'System, reviewed by a consultant',
        detail:
          'Each framework criterion is matched to the confirmed facts and document passages that support it. The consultant confirms or corrects every match — the same review discipline the audit already uses for extracted facts.',
        screen: [
          { type: 'table', label: 'Criterion | Matched evidence | Confidence | Confirm?' },
          { type: 'card', label: 'Evidence preview: passage + document + page' },
        ],
      },
      {
        title: 'See coverage and holes',
        actor: 'Institution Admin',
        detail:
          'A coverage view showing which criteria are evidenced, which are thin, and which have nothing — the compliance equivalent of the gap dashboard.',
        screen: [
          { type: 'chart', label: 'Coverage by criterion group' },
          { type: 'list', label: 'Criteria with no supporting evidence' },
        ],
      },
      {
        title: 'Export the mapping',
        actor: 'Consultant',
        detail:
          'A document the institution can hand to an assessor, with every claim carrying its source citation.',
        screen: [
          { type: 'button', label: 'Export mapping (PDF / DOCX)' },
        ],
      },
    ],
    dependsOn: [
      'Evidence Intelligence — the matching depends on document retrieval',
      'A loaded criteria set per framework — needs to be sourced and agreed',
    ],
    reuses: [
      'The report generator, which already produces versioned PDF and DOCX with cited data',
      'The confirm / correct / reject review pattern from fact review',
    ],
    questions: [
      'Which framework do we build first — NAAC?',
      'Who supplies the official criteria list, and in what format?',
      'Is this per sprint, or a standing institution-level view that spans sprints?',
    ],
  },

  {
    key: 'uat-readiness',
    label: 'UAT Readiness',
    icon: ClipboardCheck,
    status: 'planned',
    purpose:
      'A structured checklist the client signs off before an engagement is declared complete.',
    problem:
      'There is no formal hand-over step. "Done" is currently a judgement call, which is exactly the kind of ambiguity that causes disputes at the end of an engagement.',
    steps: [
      {
        title: 'Generate the checklist',
        actor: 'System',
        detail:
          'A checklist derived from what the engagement actually contains — required documents received, facts confirmed, gaps closed, baseline approved, report delivered.',
        screen: [
          { type: 'title', label: 'UAT readiness — Sprint SPR-XXXX' },
          { type: 'list', label: 'Checklist item | Auto-checked | Manual sign-off' },
        ],
      },
      {
        title: 'Client walkthrough and sign-off',
        actor: 'Institution Admin / Leadership',
        detail:
          'Each item is accepted or rejected with a comment. Rejections are what block completion — mirroring how blocking gaps already prevent baseline approval.',
        screen: [
          { type: 'table', label: 'Item | Status | Reviewer | Comment' },
          { type: 'button', label: 'Accept · Reject with reason' },
        ],
      },
      {
        title: 'Record the sign-off',
        actor: 'System',
        detail:
          'A permanent, non-editable record of who signed off, when, and on what — following the append-only audit trail the platform already uses for baseline decisions.',
        screen: [
          { type: 'card', label: 'Signed off by · role · timestamp' },
          { type: 'button', label: 'Download sign-off certificate' },
        ],
      },
    ],
    dependsOn: ['AI Readiness Audit — there must be a completed sprint to sign off'],
    reuses: [
      'The baseline approval workflow, which already models "approve / approve provisionally / return for correction"',
      'The immutable decision-history pattern already used for baseline sign-off',
    ],
    questions: [
      'What exactly constitutes "delivered" — which items must be green before sign-off is allowed?',
      'Can a client sign off with items outstanding, the way a baseline can be approved provisionally?',
      'Is a downloadable signed certificate required, or is an in-app record enough?',
    ],
  },

  {
    key: 'admin-settings',
    label: 'Admin / Settings',
    icon: Settings,
    status: 'planned',
    purpose:
      'The screens that let an administrator run the platform without a developer — users, roles, scoring configuration and integrations.',
    problem:
      'Today, adding a user or retuning a pillar weight requires the Django admin or a developer. That is fine for a pilot and unacceptable once the platform is handed to a client.',
    steps: [
      {
        title: 'Manage users and roles',
        actor: 'Super Admin / Institution Admin',
        detail:
          'Invite a user, set their role and institution, deactivate a leaver. All 11 roles and the permission rules behind them already exist — this is the missing interface for them.',
        screen: [
          { type: 'title', label: 'Users' },
          { type: 'table', label: 'Name | Email | Role | Institution | Status' },
          { type: 'button', label: 'Invite user' },
        ],
      },
      {
        title: 'Tune the scoring rubric',
        actor: 'Super Admin',
        detail:
          'Adjust pillar weights and criteria. The scoring engine already reads these from the database and re-fingerprints itself when they change — so this screen is safe to add without touching the engine.',
        screen: [
          { type: 'table', label: 'Pillar | Weight | Criteria count | Active' },
          { type: 'text', label: 'Weights must total 100%' },
        ],
      },
      {
        title: 'Configure integrations',
        actor: 'Super Admin',
        detail:
          'Where keys and connections are managed — the AI provider, Google Drive, the document index. Values would be write-only: settable, never displayed back.',
        screen: [
          { type: 'list', label: 'AI provider · Google Drive · Document index — connected / not configured' },
          { type: 'button', label: 'Test connection' },
        ],
      },
    ],
    dependsOn: [],
    reuses: [
      'The complete role and permission model — already built and enforced on every endpoint',
      'The configurable pillar and criterion tables the scoring engine already reads at run time',
    ],
    questions: [
      'Should an Institution Admin be able to invite users, or only a Super Admin?',
      'Do invited users get an email invitation? There is no email provider configured yet.',
      'Should changing a pillar weight require re-scoring existing sprints, or only apply to new ones?',
    ],
  },
];

export function getModuleFlow(key: string | undefined): ModuleFlow | undefined {
  return MODULE_FLOWS.find((m) => m.key === key);
}
