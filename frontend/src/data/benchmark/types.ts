// ===================================================================
// Benchmark Intelligence & Governance — type definitions
//
// PORTED, essentially unchanged, from the InGage "AI Future Ready"
// prototype (`src/types/benchmarkTypes.ts`). The shape of this model is the
// manager's design, not this team's: it is reproduced faithfully so that a
// review compares like with like, and so that a future backend can be built
// against the same contract.
//
// Nothing here is persisted yet. These types describe DEMO data held in the
// browser (see ./seed.ts) — no Django model, migration or endpoint backs any
// of it. Every screen that renders it says so.
// ===================================================================

// ===== GOVERNANCE ROLES =====
// Note: these nine are the prototype's own role set. They do NOT correspond
// to the eleven roles this platform actually enforces server-side; mapping
// the two is an open decision.
export type BenchmarkRole =
  | 'INGAGE_ADMIN' | 'BENCHMARK_EDITOR' | 'SOURCE_REVIEWER'
  | 'METHODOLOGY_REVIEWER' | 'APPROVER' | 'PUBLISHER'
  | 'AUDITOR' | 'CLIENT_ADMIN' | 'CLIENT_MEMBER';

// ===== ONTOLOGY =====
export interface OntologyNode {
  id: string;
  code: string;
  label: string;
  level: 'DOMAIN' | 'SECTION' | 'CATEGORY' | 'CAPABILITY';
  parentId: string | null;
  description: string;
  sortOrder: number;
  status: 'ACTIVE' | 'DEPRECATED';
}

export type AuthorityCategory =
  | 'REGULATORY' | 'ACCREDITATION' | 'INDUSTRY_STANDARD'
  | 'LEADING_PRACTICE' | 'INGAGE_METHODOLOGY' | 'RESEARCH_BASED' | 'EXPERT_CONSENSUS';

export type BenchmarkLifecycleState =
  | 'DRAFT' | 'RESEARCH' | 'VALIDATION' | 'INTERNAL_REVIEW' | 'INGAGE_APPROVAL'
  | 'PUBLISHED' | 'UNDER_REVIEW' | 'REVISED' | 'SUPERSEDED' | 'RETIRED' | 'REJECTED';

/** The only legal moves. A benchmark cannot skip review on its way to
 * publication, and a published one cannot be edited back into a draft. */
export const LIFECYCLE_TRANSITIONS: Record<BenchmarkLifecycleState, BenchmarkLifecycleState[]> = {
  DRAFT: ['RESEARCH'],
  RESEARCH: ['VALIDATION'],
  VALIDATION: ['INTERNAL_REVIEW'],
  INTERNAL_REVIEW: ['INGAGE_APPROVAL'],
  INGAGE_APPROVAL: ['PUBLISHED', 'REJECTED'],
  PUBLISHED: ['UNDER_REVIEW', 'SUPERSEDED'],
  UNDER_REVIEW: ['REVISED'],
  REVISED: ['INGAGE_APPROVAL'],
  SUPERSEDED: ['RETIRED'],
  RETIRED: [],
  REJECTED: [],
};

export type BenchmarkConfidence = 'LOW' | 'MEDIUM' | 'HIGH' | 'APPROVED_METHOD';
export type EvidenceConfidenceLevel = 'UNVERIFIED' | 'LOW' | 'MEDIUM' | 'HIGH' | 'VALIDATED';

/** ⚠ Read the numbering carefully: **L1 is the HIGHEST** level, L3 the lowest.
 * That is the prototype's convention and it is preserved here rather than
 * silently corrected — but it reverses what most readers expect from
 * "level 1", and it is flagged as an open question before this reaches any
 * client-facing report. */
export type MaturityLevel = 'L3_FOUNDATIONAL' | 'L2_GOOD' | 'L1_ADVANCED';

// ===== BENCHMARK ENTITY =====
export interface Benchmark {
  id: string;
  code: string;
  title: string;
  ontologyNodeId: string;
  ontologyPath: string;
  definition: string;
  rationale: string;
  authorityCategory: AuthorityCategory;
  criticality: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
  benchmarkConfidence: BenchmarkConfidence;
  scoringConfigStatus: 'CONFIG_REQUIRED' | 'METHODOLOGY_REVIEW' | 'APPROVED';
  status: BenchmarkLifecycleState;
  currentVersionId: string;
  createdBy: string;
  createdAt: string;
  updatedBy: string;
  updatedAt: string;
}

export interface BenchmarkVersion {
  id: string;
  benchmarkId: string;
  versionNumber: number;
  effectiveFrom: string | null;
  effectiveTo: string | null;
  changeNote: string;
  status: BenchmarkLifecycleState;
  publishedAt: string | null;
  publishedBy: string | null;
  /** Set on publication and never unset — this is what stops a past client
   * score from being quietly rewritten. */
  isImmutable: boolean;
  levels: BenchmarkLevel[];
  evidenceRequirements: BenchmarkEvidenceRequirement[];
  sourceLinks: BenchmarkSourceLink[];
  applicabilityRules: ApplicabilityRule[];
  criMapping: CRIMapping | null;
}

export interface BenchmarkLevel {
  id: string;
  benchmarkVersionId: string;
  level: MaturityLevel;
  levelTitle: string;
  definition: string;
  observableRequirements: string[];
  minimumEvidenceRequirements: string[];
  outcomeExpectations: string[];
  /** What explicitly does NOT count as meeting this level. */
  nonExamples: string[];
  reviewNotes: string;
  requiresManualReview: boolean;
}

export type EvidenceType =
  | 'DOCUMENT' | 'DATA_EXPORT' | 'SCREENSHOT' | 'PHOTO' | 'URL' | 'POLICY'
  | 'MINUTES' | 'REPORT' | 'CERTIFICATE' | 'ASSET_REGISTER' | 'USAGE_LOG'
  | 'INTEGRATION_RECORD' | 'SURVEY' | 'INTERVIEW' | 'SYSTEM_RECORD' | 'OTHER';

export type ValidationMethod =
  | 'AUTO_EXTRACT' | 'MANUAL_REVIEW' | 'SYSTEM_INTEGRATION' | 'AI_ASSISTED_REVIEW';

export interface BenchmarkEvidenceRequirement {
  id: string;
  benchmarkVersionId: string;
  level: MaturityLevel;
  evidenceType: EvidenceType;
  title: string;
  description: string;
  required: boolean;
  minimumCount: number;
  freshnessDays: number;
  validationMethod: ValidationMethod;
  privacyClassification: 'PUBLIC' | 'INTERNAL' | 'CONFIDENTIAL' | 'RESTRICTED';
}

// ===== SOURCE REGISTRY =====
export type SourceType =
  | 'REGULATORY' | 'ACADEMIC' | 'INDUSTRY' | 'FRAMEWORK' | 'WHITEPAPER' | 'INGAGE_INTERNAL';

export interface BenchmarkSource {
  id: string;
  title: string;
  sourceType: SourceType;
  authorityLevel: AuthorityCategory;
  url: string | null;
  publishedDate: string | null;
  retrievedDate: string;
  contentHash: string | null;
  status: 'ACTIVE' | 'STALE' | 'SUPERSEDED' | 'INVALID';
  lastReviewedAt: string;
  reviewedBy: string | null;
}

export interface SourceClaim {
  id: string;
  sourceId: string;
  claimText: string;
  claimCategory: string;
  extractionMethod: 'MANUAL' | 'AI_EXTRACTED' | 'RAG';
  confidence: number;
  pageReference: string | null;
  status: 'AI_EXTRACTED' | 'HUMAN_VALIDATED' | 'REJECTED';
}

export type SourceRelationship = 'SUPPORTS' | 'CONTRADICTS' | 'CONTEXT' | 'SUPERSEDES' | 'INSPIRES';

export interface BenchmarkSourceLink {
  id: string;
  benchmarkVersionId: string;
  sourceId: string;
  sourceClaimId: string | null;
  relationship: SourceRelationship;
  authorityCategory: AuthorityCategory;
  citationNote: string;
  reviewStatus: 'AI_EXTRACTED' | 'HUMAN_VALIDATED' | 'REJECTED';
}

// ===== APPLICABILITY =====
export type ApplicabilityResult = 'APPLIES' | 'DOES_NOT_APPLY' | 'OPTIONAL' | 'REQUIRES_REVIEW';

export interface ApplicabilityRule {
  id: string;
  benchmarkVersionId: string;
  ruleCode: string;
  description: string;
  conditionJson: Record<string, unknown>;
  result: ApplicabilityResult;
  reasonTemplate: string;
  priority: number;
  effectiveFrom: string;
  effectiveTo: string | null;
  version: number;
  status: 'DRAFT' | 'APPROVED';
}

// ===== CRI MAPPING & RULES =====
export interface CRIMapping {
  id: string;
  benchmarkVersionId: string;
  domainCode: string;
  sectionCode: string | null;
  categoryCode: string | null;
  capabilityCode: string | null;
  weight: number;
  normalizedWeight: number | null;
  gateType: 'NONE' | 'SOFT' | 'HARD';
  gateThreshold: number | null;
  status: 'CONFIG_REQUIRED' | 'METHODOLOGY_REVIEW' | 'APPROVED';
}

export interface CRIRuleVersion {
  id: string;
  versionNumber: number;
  effectiveFrom: string;
  effectiveTo: string | null;
  dimensionWeights: Record<string, number>;
  gateRules: CRIGateRule[];
  normalizationMethod: 'WEIGHT_BASED' | 'RANK_BASED' | 'PERCENTILE';
  /** `REQUIRES_INGAGE_APPROVAL` is spec §2.4: methodology numbers that have
   * not been signed off are held in that state rather than presented as
   * settled. The weights and thresholds shipped with the prototype are
   * exactly that — plausible placeholders nobody has approved. */
  status: 'DRAFT' | 'REQUIRES_INGAGE_APPROVAL' | 'METHODOLOGY_REVIEW' | 'APPROVED' | 'SUPERSEDED';
  approvedBy: string | null;
  approvedAt: string | null;
}

/** A criticality gate — spec §13.6.
 *
 * ⚠ A gate **caps** a score; it does not deduct from it. The prototype
 * implemented gates as subtracted percentage penalties, which is a different
 * mechanism and produces very different numbers (it is why its own sample
 * data computed 0.0 — 20 points subtracted from a base of 7.7). The spec's
 * intent is a ceiling: "an institution cannot receive a high responsible-AI
 * governance rating if no AI policy or accountability structure exists."
 */
export interface CRIGateRule {
  id: string;
  ruleVersionId: string;
  gateCode: string;
  gateDescription: string;
  /** The benchmark whose level decides whether this gate fires. */
  benchmarkCode: string;
  /** Human-readable statement of when the gate applies. */
  triggerCondition: string;
  /** The gate fires when the benchmark sits below this level, or is unassessed. */
  minimumLevel: MaturityLevel;
  capScoreEffect: 'CAP_OVERALL' | 'CAP_DOMAIN' | 'CAP_CATEGORY' | 'FLAG_ONLY' | 'REVIEW_REQUIRED';
  /** The ceiling applied when the gate fires. Null for FLAG_ONLY and
   * REVIEW_REQUIRED, which change no number. */
  maxAllowedScore: number | null;
  reviewOverrideAllowed: boolean;
  overrideRequiresApproval: boolean;
}

/** What one gate did to one assessment — the trace §13.7 requires. */
export interface GateOutcome {
  gateCode: string;
  gateDescription: string;
  benchmarkCode: string;
  fired: boolean;
  capScoreEffect: CRIGateRule['capScoreEffect'];
  /** Plain words: why it fired or why it did not. */
  reason: string;
  /** What it actually changed, if anything. */
  effect: string;
}

// ===== GAP ENGINE =====
export type GapType =
  | 'CAPABILITY_ABSENT' | 'CAPABILITY_BELOW_TARGET' | 'EVIDENCE_MISSING'
  | 'EVIDENCE_STALE' | 'EVIDENCE_INSUFFICIENT' | 'DEPENDENCY_UNMET';

export type GapSeverity = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'INFORMATIONAL';

export interface GapResult {
  id: string;
  assessmentSnapshotId: string;
  benchmarkId: string;
  benchmarkCode: string;
  benchmarkTitle: string;
  gapType: GapType;
  severity: GapSeverity;
  currentLevel: MaturityLevel | null;
  targetLevel: MaturityLevel;
  evidenceGaps: string[];
  capabilityGaps: string[];
  dependencyGaps: string[];
  recommendedActions: string[];
  estimatedEffort: '0_30_DAYS' | '30_90_DAYS' | '90_180_DAYS' | '180_PLUS_DAYS';
  criImpact: number;
  domainCode: string;
}

// ===== TRANSFORMATION =====
export interface TransformationMapping {
  id: string;
  gapId: string;
  interventionTemplateId: string;
  goalTemplateId: string | null;
  initiativeCode: string;
  title: string;
  description: string;
  priority: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
  estimatedCriLift: number;
  timeline: string;
  owner: string;
  status: 'PROPOSED' | 'APPROVED' | 'IN_PROGRESS' | 'COMPLETED';
  linkedBenchmarkIds: string[];
}

// ===== ASSESSMENT =====
export interface InstitutionAssessmentSnapshot {
  id: string;
  institutionId: string;
  assessmentDate: string;
  benchmarkVersionIds: string[];
  criRuleVersionId: string;
  normalizationRuleVersionId: string;
  applicabilityRuleVersionIds: string[];
  targetRuleVersionId: string;
  benchmarkAssessments: BenchmarkAssessment[];
  overallCRI: number;
  domainScores: DomainScore[];
  status: 'DRAFT' | 'PROVISIONAL' | 'OFFICIAL' | 'SUPERSEDED';
  calculatedAt: string;
  calculatedBy: string;
}

export interface BenchmarkAssessment {
  id: string;
  snapshotId: string;
  benchmarkId: string;
  benchmarkCode: string;
  benchmarkVersionId: string;
  applicabilityResult: ApplicabilityResult;
  currentLevel: MaturityLevel | null;
  targetLevel: MaturityLevel;
  aspirationalLevel: MaturityLevel | null;
  rawScore: number;
  weightedScore: number;
  evidenceConfidence: EvidenceConfidenceLevel;
  evidenceItems: string[];
  gateStatus: 'PASSED' | 'SOFT_FAIL' | 'HARD_FAIL' | 'NOT_APPLICABLE';
  explanation: string;
}

export interface DomainScore {
  domainCode: string;
  domainLabel: string;
  rawScore: number;
  normalizedScore: number;
  weight: number;
  weightedScore: number;
  benchmarkCount: number;
  applicableBenchmarkCount: number;
  gatesPassed: number;
  gatesFailed: number;
  confidence: EvidenceConfidenceLevel;
}

// ===== APPROVAL =====
export type ApprovalAction = 'APPROVE' | 'REJECT' | 'REQUEST_CHANGES' | 'PUBLISH';

export interface ApprovalRequest {
  id: string;
  objectType: 'BENCHMARK' | 'BENCHMARK_VERSION' | 'CRI_RULE' | 'NORMALIZATION_RULE' | 'APPLICABILITY_RULE';
  objectId: string;
  requestedBy: string;
  requestedAt: string;
  status: 'PENDING' | 'APPROVED' | 'REJECTED' | 'CHANGES_REQUESTED';
  reviewerComments: string;
  reviewedBy: string | null;
  reviewedAt: string | null;
  action: ApprovalAction | null;
}

export interface BenchmarkAuditEvent {
  id: string;
  actor: string;
  action: string;
  objectType: string;
  objectId: string;
  beforeHash: string | null;
  afterHash: string | null;
  timestamp: string;
  reason: string;
  requestId: string;
}

// ===== AI BENCHMARK FACTORY =====
export type CandidateStatus =
  | 'NEW' | 'NEEDS_RESEARCH' | 'READY_FOR_REVIEW' | 'CHANGES_REQUESTED'
  | 'APPROVED_FOR_DRAFT' | 'REJECTED' | 'CONVERTED_TO_BENCHMARK';

export interface BenchmarkCandidate {
  id: string;
  suggestedTitle: string;
  suggestedCode: string;
  suggestedOntologyPath: string;
  suggestedDefinition: string;
  suggestedLevels: { L3: string; L2: string; L1: string };
  sourceClaimIds: string[];
  aiConfidence: number;
  criticFindings: CriticFinding[];
  impactSummary: string;
  status: CandidateStatus;
  createdBy: string;
  createdAt: string;
  agentRunId: string | null;
}

export interface CriticFinding {
  id: string;
  candidateId: string;
  checkType: string;
  severity: 'ERROR' | 'WARNING' | 'INFO';
  finding: string;
  suggestion: string;
  overriddenBy: string | null;
  overrideReason: string | null;
}

export interface ImpactSimulation {
  id: string;
  candidateId: string | null;
  ruleChangeId: string | null;
  simulationType: 'NEW_BENCHMARK' | 'BENCHMARK_CHANGE' | 'RULE_CHANGE' | 'WEIGHT_CHANGE';
  affectedInstitutions: number;
  expectedCriMovement: { min: number; max: number };
  newEvidenceBurden: number;
  newGatesTriggered: number;
  riskLevel: 'LOW' | 'MEDIUM' | 'HIGH';
  summary: string;
  simulatedAt: string;
}

export interface BenchmarkSearchFilters {
  query: string;
  status: BenchmarkLifecycleState | 'ALL';
  domain: string;
  criticality: string;
}
