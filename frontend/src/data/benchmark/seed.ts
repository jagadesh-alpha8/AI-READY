// ===================================================================
// Benchmark demo data — PORTED from the InGage "AI Future Ready" prototype
// (`src/data/benchmarkData.ts`), content preserved.
//
// ⚠ THIS IS ILLUSTRATIVE DATA, NOT AN INSTITUTION'S REAL RECORD. It lives in
// the browser, resets on reload, and is backed by no database. Every screen
// that renders it carries a banner saying so — see components/DemoDataNotice.
// ===================================================================

import type {
  ApprovalRequest, Benchmark, BenchmarkAuditEvent, BenchmarkCandidate,
  BenchmarkEvidenceRequirement, BenchmarkLevel, BenchmarkSource, BenchmarkVersion,
  CRIRuleVersion, EvidenceType, GapResult, ImpactSimulation,
  InstitutionAssessmentSnapshot, MaturityLevel, OntologyNode, SourceClaim,
  TransformationMapping,
} from './types';

// ===== ONTOLOGY =====
export const ontologyNodes: OntologyNode[] = [
  { id: 'dom-gov', code: 'GOV', label: 'Governance & Strategy', level: 'DOMAIN', parentId: null, description: 'AI governance, strategy, and leadership', sortOrder: 1, status: 'ACTIVE' },
  { id: 'dom-cur', code: 'CUR', label: 'Curriculum & Academic Readiness', level: 'DOMAIN', parentId: null, description: 'Curriculum integration, pedagogy, and academic AI adoption', sortOrder: 2, status: 'ACTIVE' },
  { id: 'dom-fac', code: 'FAC', label: 'Faculty AI Capability', level: 'DOMAIN', parentId: null, description: 'Faculty training, adoption, and applied AI in teaching', sortOrder: 3, status: 'ACTIVE' },
  { id: 'dom-stu', code: 'STU', label: 'Student AI Enablement', level: 'DOMAIN', parentId: null, description: 'Student skills, labs, and experiential AI learning', sortOrder: 4, status: 'ACTIVE' },
  { id: 'dom-inf', code: 'INF', label: 'Infrastructure & Data', level: 'DOMAIN', parentId: null, description: 'IT infrastructure, data readiness, and digital systems', sortOrder: 5, status: 'ACTIVE' },
  { id: 'dom-res', code: 'RES', label: 'Research & Innovation', level: 'DOMAIN', parentId: null, description: 'AI research output, innovation pipeline, and ecosystem', sortOrder: 6, status: 'ACTIVE' },
  { id: 'dom-ind', code: 'IND', label: 'Industry & Placement', level: 'DOMAIN', parentId: null, description: 'Industry engagement, internships, and placement outcomes', sortOrder: 7, status: 'ACTIVE' },
  { id: 'dom-evq', code: 'EVQ', label: 'Evidence Quality', level: 'DOMAIN', parentId: null, description: 'Data completeness, evidence confidence, and conflict health', sortOrder: 8, status: 'ACTIVE' },
  { id: 'cat-gov-str', code: 'GOV.STR', label: 'AI Strategy', level: 'CATEGORY', parentId: 'dom-gov', description: 'Approved AI strategy and planning', sortOrder: 1, status: 'ACTIVE' },
  { id: 'cat-gov-pol', code: 'GOV.POL', label: 'Responsible AI Policy', level: 'CATEGORY', parentId: 'dom-gov', description: 'Ethics, privacy, and responsible AI governance', sortOrder: 2, status: 'ACTIVE' },
  { id: 'cat-gov-exe', code: 'GOV.EXE', label: 'Governance Execution', level: 'CATEGORY', parentId: 'dom-gov', description: 'Steering committees, action tracking, reviews', sortOrder: 3, status: 'ACTIVE' },
  { id: 'cat-cur-int', code: 'CUR.INT', label: 'AI Course Integration', level: 'CATEGORY', parentId: 'dom-cur', description: 'AI courses and modules across programs', sortOrder: 1, status: 'ACTIVE' },
  { id: 'cat-cur-pbl', code: 'CUR.PBL', label: 'Project-Based Learning', level: 'CATEGORY', parentId: 'dom-cur', description: 'AI capstones and project work', sortOrder: 2, status: 'ACTIVE' },
  { id: 'cat-fac-lit', code: 'FAC.LIT', label: 'AI Literacy', level: 'CATEGORY', parentId: 'dom-fac', description: 'Faculty AI foundation training', sortOrder: 1, status: 'ACTIVE' },
  { id: 'cat-fac-app', code: 'FAC.APP', label: 'Applied AI Teaching', level: 'CATEGORY', parentId: 'dom-fac', description: 'AI tools in teaching practice', sortOrder: 2, status: 'ACTIVE' },
  { id: 'cat-inf-lab', code: 'INF.LAB', label: 'AI Lab Infrastructure', level: 'CATEGORY', parentId: 'dom-inf', description: 'Dedicated AI computing labs', sortOrder: 1, status: 'ACTIVE' },
  { id: 'cat-inf-sys', code: 'INF.SYS', label: 'Digital Systems', level: 'CATEGORY', parentId: 'dom-inf', description: 'LMS, ERP, and data systems', sortOrder: 2, status: 'ACTIVE' },
];

// ===== SOURCE REGISTRY =====
export const benchmarkSources: BenchmarkSource[] = [
  { id: 'src-1', title: 'AICTE AI Integration Guidelines 2025', sourceType: 'REGULATORY', authorityLevel: 'REGULATORY', url: 'https://aicte-india.org/ai-guidelines', publishedDate: '2025-03-15', retrievedDate: '2026-06-01', contentHash: 'abc123', status: 'ACTIVE', lastReviewedAt: '2026-06-01', reviewedBy: 'u5' },
  { id: 'src-2', title: 'NAAC Revised Assessment Framework 2024', sourceType: 'REGULATORY', authorityLevel: 'ACCREDITATION', url: 'https://naac.gov.in/framework-2024', publishedDate: '2024-08-01', retrievedDate: '2026-05-15', contentHash: 'def456', status: 'ACTIVE', lastReviewedAt: '2026-05-15', reviewedBy: 'u5' },
  { id: 'src-3', title: 'UNESCO AI in Education Competency Framework', sourceType: 'FRAMEWORK', authorityLevel: 'INDUSTRY_STANDARD', url: 'https://unesco.org/ai-edu', publishedDate: '2024-11-01', retrievedDate: '2026-04-20', contentHash: 'ghi789', status: 'ACTIVE', lastReviewedAt: '2026-04-20', reviewedBy: 'u5' },
  { id: 'src-4', title: 'InGage AI Readiness Methodology v2.0', sourceType: 'INGAGE_INTERNAL', authorityLevel: 'INGAGE_METHODOLOGY', url: null, publishedDate: '2026-01-15', retrievedDate: '2026-01-15', contentHash: 'jkl012', status: 'ACTIVE', lastReviewedAt: '2026-07-01', reviewedBy: 'u5' },
  { id: 'src-5', title: 'MIT AI in Higher Education Report 2025', sourceType: 'ACADEMIC', authorityLevel: 'RESEARCH_BASED', url: 'https://mit.edu/ai-he-2025', publishedDate: '2025-09-01', retrievedDate: '2026-03-10', contentHash: 'mno345', status: 'ACTIVE', lastReviewedAt: '2026-03-10', reviewedBy: null },
  { id: 'src-6', title: 'NEP 2020 — AI & Technology Integration', sourceType: 'REGULATORY', authorityLevel: 'REGULATORY', url: 'https://education.gov.in/nep', publishedDate: '2020-07-29', retrievedDate: '2026-01-05', contentHash: 'pqr678', status: 'ACTIVE', lastReviewedAt: '2026-01-05', reviewedBy: 'u5' },
  { id: 'src-7', title: 'World Economic Forum — Future of Jobs AI Skills', sourceType: 'INDUSTRY', authorityLevel: 'LEADING_PRACTICE', url: 'https://weforum.org/foj-2025', publishedDate: '2025-01-10', retrievedDate: '2026-02-15', contentHash: 'stu901', status: 'ACTIVE', lastReviewedAt: '2026-02-15', reviewedBy: null },
];

export const sourceClaims: SourceClaim[] = [
  { id: 'sc-1', sourceId: 'src-1', claimText: 'All AICTE-approved institutions must have an approved AI integration strategy by 2026', claimCategory: 'Governance', extractionMethod: 'MANUAL', confidence: 0.95, pageReference: 'Section 3.1', status: 'HUMAN_VALIDATED' },
  { id: 'sc-2', sourceId: 'src-2', claimText: 'Institutions must demonstrate AI literacy programs for at least 60% of faculty', claimCategory: 'Faculty', extractionMethod: 'MANUAL', confidence: 0.90, pageReference: 'Criterion 2.4', status: 'HUMAN_VALIDATED' },
  { id: 'sc-3', sourceId: 'src-3', claimText: 'Faculty AI competency framework requires foundation, intermediate, and advanced tiers', claimCategory: 'Faculty', extractionMethod: 'AI_EXTRACTED', confidence: 0.85, pageReference: 'Chapter 4', status: 'HUMAN_VALIDATED' },
  { id: 'sc-4', sourceId: 'src-4', claimText: 'CRI scoring follows weighted pillar model with deterministic calculation', claimCategory: 'Methodology', extractionMethod: 'MANUAL', confidence: 1.0, pageReference: 'Section 5.2', status: 'HUMAN_VALIDATED' },
  { id: 'sc-5', sourceId: 'src-6', claimText: 'NEP 2020 mandates AI/computational thinking across all undergraduate programs', claimCategory: 'Curriculum', extractionMethod: 'MANUAL', confidence: 0.92, pageReference: 'Para 11.8', status: 'HUMAN_VALIDATED' },
  { id: 'sc-6', sourceId: 'src-5', claimText: 'Institutions with dedicated AI labs show 3x higher research output', claimCategory: 'Infrastructure', extractionMethod: 'AI_EXTRACTED', confidence: 0.78, pageReference: 'p.47', status: 'AI_EXTRACTED' },
  { id: 'sc-7', sourceId: 'src-7', claimText: 'AI skills gap in graduates costs industry $2.5T annually', claimCategory: 'Industry', extractionMethod: 'AI_EXTRACTED', confidence: 0.80, pageReference: 'Executive Summary', status: 'AI_EXTRACTED' },
];

// ===== BENCHMARKS =====
export const seedBenchmarks: Benchmark[] = [
  { id: 'bm-1', code: 'GOV.STR.001', title: 'Approved AI Strategy', ontologyNodeId: 'cat-gov-str', ontologyPath: 'Governance & Strategy > AI Strategy', definition: 'The institution has a formally approved AI integration strategy with clear objectives, timelines, resource allocation, and governance structure.', rationale: 'An approved strategy is the foundation for systematic AI adoption.', authorityCategory: 'REGULATORY', criticality: 'CRITICAL', benchmarkConfidence: 'HIGH', scoringConfigStatus: 'APPROVED', status: 'PUBLISHED', currentVersionId: 'bm-1-v1', createdBy: 'u5', createdAt: '2026-01-15', updatedBy: 'u5', updatedAt: '2026-06-01' },
  { id: 'bm-2', code: 'GOV.POL.001', title: 'Responsible AI Policy', ontologyNodeId: 'cat-gov-pol', ontologyPath: 'Governance & Strategy > Responsible AI Policy', definition: 'The institution has an approved policy covering AI ethics, data privacy, academic integrity, and responsible use guidelines.', rationale: 'Responsible AI policy ensures ethical deployment and reduces risk.', authorityCategory: 'REGULATORY', criticality: 'CRITICAL', benchmarkConfidence: 'HIGH', scoringConfigStatus: 'APPROVED', status: 'PUBLISHED', currentVersionId: 'bm-2-v1', createdBy: 'u5', createdAt: '2026-01-20', updatedBy: 'u5', updatedAt: '2026-06-01' },
  { id: 'bm-3', code: 'GOV.EXE.001', title: 'AI Steering Committee', ontologyNodeId: 'cat-gov-exe', ontologyPath: 'Governance & Strategy > Governance Execution', definition: 'An active AI steering committee exists with defined membership, mandate, meeting cadence, and documented decisions.', rationale: 'Governance execution requires an accountable body.', authorityCategory: 'LEADING_PRACTICE', criticality: 'HIGH', benchmarkConfidence: 'HIGH', scoringConfigStatus: 'APPROVED', status: 'PUBLISHED', currentVersionId: 'bm-3-v1', createdBy: 'u5', createdAt: '2026-02-01', updatedBy: 'u5', updatedAt: '2026-06-01' },
  { id: 'bm-4', code: 'CUR.INT.001', title: 'AI Course Integration', ontologyNodeId: 'cat-cur-int', ontologyPath: 'Curriculum & Academic Readiness > AI Course Integration', definition: 'AI/ML courses or modules are integrated into programs across departments, not limited to CS.', rationale: 'NEP 2020 mandates computational thinking across disciplines.', authorityCategory: 'REGULATORY', criticality: 'HIGH', benchmarkConfidence: 'HIGH', scoringConfigStatus: 'APPROVED', status: 'PUBLISHED', currentVersionId: 'bm-4-v1', createdBy: 'u5', createdAt: '2026-02-10', updatedBy: 'u5', updatedAt: '2026-06-01' },
  { id: 'bm-5', code: 'FAC.LIT.001', title: 'Faculty AI Foundation Certification', ontologyNodeId: 'cat-fac-lit', ontologyPath: 'Faculty AI Capability > AI Literacy', definition: 'Faculty have completed foundation-level AI literacy certification with documented completion evidence.', rationale: 'Faculty readiness is a prerequisite for effective AI curriculum delivery.', authorityCategory: 'ACCREDITATION', criticality: 'CRITICAL', benchmarkConfidence: 'APPROVED_METHOD', scoringConfigStatus: 'APPROVED', status: 'PUBLISHED', currentVersionId: 'bm-5-v1', createdBy: 'u5', createdAt: '2026-02-15', updatedBy: 'u5', updatedAt: '2026-06-01' },
  { id: 'bm-6', code: 'INF.LAB.001', title: 'Dedicated AI Lab Infrastructure', ontologyNodeId: 'cat-inf-lab', ontologyPath: 'Infrastructure & Data > AI Lab Infrastructure', definition: 'The institution has a dedicated AI/ML computing lab with GPU resources, software tools, and adequate student access.', rationale: 'Hands-on AI learning requires appropriate infrastructure.', authorityCategory: 'LEADING_PRACTICE', criticality: 'HIGH', benchmarkConfidence: 'HIGH', scoringConfigStatus: 'APPROVED', status: 'PUBLISHED', currentVersionId: 'bm-6-v1', createdBy: 'u5', createdAt: '2026-03-01', updatedBy: 'u5', updatedAt: '2026-06-01' },
  { id: 'bm-7', code: 'FAC.APP.001', title: 'AI-Augmented Teaching Practice', ontologyNodeId: 'cat-fac-app', ontologyPath: 'Faculty AI Capability > Applied AI Teaching', definition: 'Faculty actively use AI tools in teaching methodology, assessment, and content delivery.', rationale: 'Applied AI teaching transforms learning outcomes.', authorityCategory: 'INGAGE_METHODOLOGY', criticality: 'MEDIUM', benchmarkConfidence: 'MEDIUM', scoringConfigStatus: 'APPROVED', status: 'PUBLISHED', currentVersionId: 'bm-7-v1', createdBy: 'u5', createdAt: '2026-03-10', updatedBy: 'u5', updatedAt: '2026-06-01' },
  { id: 'bm-8', code: 'CUR.PBL.001', title: 'AI Capstone Projects', ontologyNodeId: 'cat-cur-pbl', ontologyPath: 'Curriculum & Academic Readiness > Project-Based Learning', definition: 'Students complete AI/ML capstone projects with industry relevance and measurable outcomes.', rationale: 'Project-based learning bridges theory and practice.', authorityCategory: 'LEADING_PRACTICE', criticality: 'MEDIUM', benchmarkConfidence: 'HIGH', scoringConfigStatus: 'APPROVED', status: 'PUBLISHED', currentVersionId: 'bm-8-v1', createdBy: 'u5', createdAt: '2026-03-15', updatedBy: 'u5', updatedAt: '2026-06-01' },
  { id: 'bm-9', code: 'INF.SYS.001', title: 'Digital Systems & Data Readiness', ontologyNodeId: 'cat-inf-sys', ontologyPath: 'Infrastructure & Data > Digital Systems', definition: 'LMS/ERP systems are operational with data export capability and integration readiness for AI workloads.', rationale: 'Data-ready systems are prerequisite for AI analytics.', authorityCategory: 'INGAGE_METHODOLOGY', criticality: 'HIGH', benchmarkConfidence: 'MEDIUM', scoringConfigStatus: 'APPROVED', status: 'PUBLISHED', currentVersionId: 'bm-9-v1', createdBy: 'u5', createdAt: '2026-03-20', updatedBy: 'u5', updatedAt: '2026-06-01' },
  { id: 'bm-10', code: 'GOV.STR.002', title: 'AI Budget Allocation', ontologyNodeId: 'cat-gov-str', ontologyPath: 'Governance & Strategy > AI Strategy', definition: 'Dedicated budget allocated for AI initiatives with transparent tracking.', rationale: 'Without dedicated budget, AI initiatives remain aspirational.', authorityCategory: 'LEADING_PRACTICE', criticality: 'HIGH', benchmarkConfidence: 'MEDIUM', scoringConfigStatus: 'METHODOLOGY_REVIEW', status: 'INTERNAL_REVIEW', currentVersionId: 'bm-10-v1', createdBy: 'u5', createdAt: '2026-04-01', updatedBy: 'u5', updatedAt: '2026-07-01' },
  { id: 'bm-11', code: 'STU.SKL.001', title: 'Student AI Skills Program', ontologyNodeId: 'dom-stu', ontologyPath: 'Student AI Enablement', definition: 'Structured AI skills development program available to students across all departments.', rationale: 'Students need systematic AI skill building beyond coursework.', authorityCategory: 'INGAGE_METHODOLOGY', criticality: 'MEDIUM', benchmarkConfidence: 'MEDIUM', scoringConfigStatus: 'APPROVED', status: 'DRAFT', currentVersionId: 'bm-11-v1', createdBy: 'u5', createdAt: '2026-05-01', updatedBy: 'u5', updatedAt: '2026-07-15' },
  { id: 'bm-12', code: 'RES.OUT.001', title: 'AI Research Output', ontologyNodeId: 'dom-res', ontologyPath: 'Research & Innovation', definition: 'Faculty publish AI/ML research in indexed journals and conferences.', rationale: 'Research output demonstrates institutional AI maturity.', authorityCategory: 'ACCREDITATION', criticality: 'MEDIUM', benchmarkConfidence: 'HIGH', scoringConfigStatus: 'APPROVED', status: 'PUBLISHED', currentVersionId: 'bm-12-v1', createdBy: 'u5', createdAt: '2026-03-25', updatedBy: 'u5', updatedAt: '2026-06-01' },
];

// ===== VERSIONS, WITH THEIR THREE LEVELS =====
const mkLevel = (
  vid: string, lvl: MaturityLevel, title: string, def: string,
  obs: string[], evd: string[], outcomes: string[],
): BenchmarkLevel => ({
  id: `${vid}-${lvl}`, benchmarkVersionId: vid, level: lvl, levelTitle: title, definition: def,
  observableRequirements: obs, minimumEvidenceRequirements: evd, outcomeExpectations: outcomes,
  nonExamples: [], reviewNotes: '', requiresManualReview: false,
});

const mkEvReq = (
  vid: string, lvl: MaturityLevel, title: string, evType: EvidenceType = 'DOCUMENT',
): BenchmarkEvidenceRequirement => ({
  id: `${vid}-ev-${lvl}`, benchmarkVersionId: vid, level: lvl, evidenceType: evType,
  title, description: `Evidence: ${title}`, required: true, minimumCount: 1,
  freshnessDays: 365, validationMethod: 'MANUAL_REVIEW', privacyClassification: 'INTERNAL',
});

export const seedBenchmarkVersions: BenchmarkVersion[] = seedBenchmarks.map((bm) => ({
  id: `${bm.id}-v1`,
  benchmarkId: bm.id,
  versionNumber: 1,
  effectiveFrom: bm.status === 'PUBLISHED' ? '2026-06-01' : null,
  effectiveTo: null,
  changeNote: 'Initial version',
  status: bm.status,
  publishedAt: bm.status === 'PUBLISHED' ? '2026-06-01' : null,
  publishedBy: bm.status === 'PUBLISHED' ? 'u5' : null,
  isImmutable: bm.status === 'PUBLISHED',
  levels: [
    mkLevel(`${bm.id}-v1`, 'L3_FOUNDATIONAL', 'Foundational',
      `Basic awareness and initial steps toward ${bm.title.toLowerCase()}`,
      ['Awareness exists', 'Initial documentation started', 'Basic compliance attempted'],
      ['Draft document or informal record'],
      ['Minimal awareness level established']),
    mkLevel(`${bm.id}-v1`, 'L2_GOOD', 'Good / Recommended',
      `Systematic implementation of ${bm.title.toLowerCase()} with evidence`,
      ['Formal documentation exists', 'Systematic process in place', 'Regular reviews conducted'],
      ['Approved policy/document', 'Meeting minutes or review records'],
      ['Consistent practice demonstrated']),
    mkLevel(`${bm.id}-v1`, 'L1_ADVANCED', 'Advanced / Aspirational',
      `Institution-wide excellence in ${bm.title.toLowerCase()} with measurable outcomes`,
      ['Institution-wide adoption', 'Outcome-linked metrics', 'Continuous improvement cycle'],
      ['Outcome reports', 'External validation evidence', 'Impact assessment'],
      ['Measurable improvement demonstrated', 'External recognition achieved']),
  ],
  evidenceRequirements: [
    mkEvReq(`${bm.id}-v1`, 'L3_FOUNDATIONAL', `${bm.title} — draft / initial document`),
    mkEvReq(`${bm.id}-v1`, 'L2_GOOD', `${bm.title} — approved document`, 'POLICY'),
    mkEvReq(`${bm.id}-v1`, 'L1_ADVANCED', `${bm.title} — outcome report`, 'REPORT'),
  ],
  sourceLinks: [{
    id: `sl-${bm.id}`, benchmarkVersionId: `${bm.id}-v1`, sourceId: 'src-4', sourceClaimId: 'sc-4',
    relationship: 'SUPPORTS', authorityCategory: 'INGAGE_METHODOLOGY',
    citationNote: 'InGage methodology reference', reviewStatus: 'HUMAN_VALIDATED',
  }],
  applicabilityRules: [{
    id: `ar-${bm.id}`, benchmarkVersionId: `${bm.id}-v1`, ruleCode: `${bm.code}-APPLY-ALL`,
    description: 'Applies to all engineering institutions',
    conditionJson: { institution_type: { contains: 'Engineering' } },
    result: 'APPLIES', reasonTemplate: 'Engineering institution — benchmark applies',
    priority: 1, effectiveFrom: '2026-06-01', effectiveTo: null, version: 1, status: 'APPROVED',
  }],
  criMapping: {
    id: `cri-${bm.id}`, benchmarkVersionId: `${bm.id}-v1`,
    domainCode: bm.code.split('.')[0], sectionCode: null,
    categoryCode: bm.code.split('.').slice(0, 2).join('.'), capabilityCode: bm.code,
    weight: bm.criticality === 'CRITICAL' ? 0.15 : bm.criticality === 'HIGH' ? 0.12 : 0.08,
    normalizedWeight: null,
    gateType: bm.criticality === 'CRITICAL' ? 'HARD' : 'NONE',
    gateThreshold: bm.criticality === 'CRITICAL' ? 33 : null,
    status: 'APPROVED',
  },
}));

// ===== CRI RULE VERSION =====
export const seedCRIRuleVersion: CRIRuleVersion = {
  id: 'cri-rule-v1', versionNumber: 1, effectiveFrom: '2026-06-01', effectiveTo: null,
  dimensionWeights: { GOV: 0.10, CUR: 0.15, FAC: 0.18, STU: 0.15, INF: 0.17, RES: 0.10, IND: 0.10, EVQ: 0.05 },
  gateRules: [
    { id: 'gate-1', ruleVersionId: 'cri-rule-v1', benchmarkCode: 'GOV.STR.001', gateType: 'HARD', minimumLevel: 'L3_FOUNDATIONAL', penaltyPercentage: 20, description: 'Approved AI strategy is required for CRI > 50' },
    { id: 'gate-2', ruleVersionId: 'cri-rule-v1', benchmarkCode: 'GOV.POL.001', gateType: 'HARD', minimumLevel: 'L3_FOUNDATIONAL', penaltyPercentage: 15, description: 'Responsible AI policy is required for CRI > 60' },
    { id: 'gate-3', ruleVersionId: 'cri-rule-v1', benchmarkCode: 'FAC.LIT.001', gateType: 'SOFT', minimumLevel: 'L3_FOUNDATIONAL', penaltyPercentage: 10, description: 'Faculty AI literacy below foundational triggers a 10% penalty' },
  ],
  normalizationMethod: 'WEIGHT_BASED', status: 'APPROVED', approvedBy: 'u5', approvedAt: '2026-06-01',
};

// ===== ASSESSMENT SNAPSHOT =====
export const seedAssessmentSnapshot: InstitutionAssessmentSnapshot = {
  id: 'snap-inst1-v1', institutionId: 'inst1', assessmentDate: '2026-08-30',
  benchmarkVersionIds: seedBenchmarkVersions.map((v) => v.id),
  criRuleVersionId: 'cri-rule-v1', normalizationRuleVersionId: 'norm-v1',
  applicabilityRuleVersionIds: ['app-v1'], targetRuleVersionId: 'target-v1',
  overallCRI: 43.5,
  domainScores: [
    { domainCode: 'GOV', domainLabel: 'Governance & Strategy', rawScore: 40, normalizedScore: 40, weight: 0.10, weightedScore: 4.0, benchmarkCount: 3, applicableBenchmarkCount: 3, gatesPassed: 2, gatesFailed: 1, confidence: 'MEDIUM' },
    { domainCode: 'CUR', domainLabel: 'Curriculum & Academic Readiness', rawScore: 50, normalizedScore: 50, weight: 0.15, weightedScore: 7.5, benchmarkCount: 2, applicableBenchmarkCount: 2, gatesPassed: 2, gatesFailed: 0, confidence: 'HIGH' },
    { domainCode: 'FAC', domainLabel: 'Faculty AI Capability', rawScore: 35, normalizedScore: 35, weight: 0.18, weightedScore: 6.3, benchmarkCount: 2, applicableBenchmarkCount: 2, gatesPassed: 1, gatesFailed: 1, confidence: 'LOW' },
    { domainCode: 'STU', domainLabel: 'Student AI Enablement', rawScore: 45, normalizedScore: 45, weight: 0.15, weightedScore: 6.75, benchmarkCount: 1, applicableBenchmarkCount: 1, gatesPassed: 1, gatesFailed: 0, confidence: 'MEDIUM' },
    { domainCode: 'INF', domainLabel: 'Infrastructure & Data', rawScore: 55, normalizedScore: 55, weight: 0.17, weightedScore: 9.35, benchmarkCount: 2, applicableBenchmarkCount: 2, gatesPassed: 2, gatesFailed: 0, confidence: 'HIGH' },
    { domainCode: 'RES', domainLabel: 'Research & Innovation', rawScore: 30, normalizedScore: 30, weight: 0.10, weightedScore: 3.0, benchmarkCount: 1, applicableBenchmarkCount: 1, gatesPassed: 1, gatesFailed: 0, confidence: 'LOW' },
    { domainCode: 'IND', domainLabel: 'Industry & Placement', rawScore: 40, normalizedScore: 40, weight: 0.10, weightedScore: 4.0, benchmarkCount: 0, applicableBenchmarkCount: 0, gatesPassed: 0, gatesFailed: 0, confidence: 'MEDIUM' },
    { domainCode: 'EVQ', domainLabel: 'Evidence Quality', rawScore: 52, normalizedScore: 52, weight: 0.05, weightedScore: 2.6, benchmarkCount: 0, applicableBenchmarkCount: 0, gatesPassed: 0, gatesFailed: 0, confidence: 'MEDIUM' },
  ],
  benchmarkAssessments: [
    { id: 'ba-1', snapshotId: 'snap-inst1-v1', benchmarkId: 'bm-1', benchmarkCode: 'GOV.STR.001', benchmarkVersionId: 'bm-1-v1', applicabilityResult: 'APPLIES', currentLevel: 'L3_FOUNDATIONAL', targetLevel: 'L2_GOOD', aspirationalLevel: 'L1_ADVANCED', rawScore: 33.3, weightedScore: 5.0, evidenceConfidence: 'HIGH', evidenceItems: ['ev1'], gateStatus: 'PASSED', explanation: 'Foundational draft strategy present.' },
    { id: 'ba-2', snapshotId: 'snap-inst1-v1', benchmarkId: 'bm-2', benchmarkCode: 'GOV.POL.001', benchmarkVersionId: 'bm-2-v1', applicabilityResult: 'APPLIES', currentLevel: null, targetLevel: 'L2_GOOD', aspirationalLevel: 'L1_ADVANCED', rawScore: 0, weightedScore: 0, evidenceConfidence: 'UNVERIFIED', evidenceItems: [], gateStatus: 'HARD_FAIL', explanation: 'No AI ethics policy uploaded. Critical gate fail.' },
    { id: 'ba-5', snapshotId: 'snap-inst1-v1', benchmarkId: 'bm-5', benchmarkCode: 'FAC.LIT.001', benchmarkVersionId: 'bm-5-v1', applicabilityResult: 'APPLIES', currentLevel: 'L3_FOUNDATIONAL', targetLevel: 'L2_GOOD', aspirationalLevel: 'L1_ADVANCED', rawScore: 33.3, weightedScore: 5.0, evidenceConfidence: 'LOW', evidenceItems: ['ev6'], gateStatus: 'SOFT_FAIL', explanation: 'Only 35% of faculty completed foundation training.' },
  ],
  status: 'OFFICIAL', calculatedAt: '2026-08-30T10:00:00Z', calculatedBy: 'u5',
};

// ===== GAPS & TRANSFORMATION =====
export const seedGaps: GapResult[] = [
  { id: 'gap-1', assessmentSnapshotId: 'snap-inst1-v1', benchmarkId: 'bm-2', benchmarkCode: 'GOV.POL.001', benchmarkTitle: 'Responsible AI Policy', gapType: 'CAPABILITY_ABSENT', severity: 'CRITICAL', currentLevel: null, targetLevel: 'L2_GOOD', evidenceGaps: ['Approved AI Policy Document', 'Board Resolution'], capabilityGaps: ['Ethical AI guidelines absent', 'Data privacy clause missing'], dependencyGaps: ['Steering committee approval required'], recommendedActions: ['Draft AI Ethics Policy', 'Submit to Academic Council for approval'], estimatedEffort: '0_30_DAYS', criImpact: 15.0, domainCode: 'GOV' },
  { id: 'gap-2', assessmentSnapshotId: 'snap-inst1-v1', benchmarkId: 'bm-5', benchmarkCode: 'FAC.LIT.001', benchmarkTitle: 'Faculty AI Foundation Certification', gapType: 'CAPABILITY_BELOW_TARGET', severity: 'HIGH', currentLevel: 'L3_FOUNDATIONAL', targetLevel: 'L2_GOOD', evidenceGaps: ['Faculty completion certificates (need 85 more)'], capabilityGaps: ['Non-CS faculty coverage below target (35% vs 80% target)'], dependencyGaps: [], recommendedActions: ['Enroll 80 faculty members in AI Foundation FDP', 'Track completion per department'], estimatedEffort: '30_90_DAYS', criImpact: 12.0, domainCode: 'FAC' },
  { id: 'gap-3', assessmentSnapshotId: 'snap-inst1-v1', benchmarkId: 'bm-4', benchmarkCode: 'CUR.INT.001', benchmarkTitle: 'AI Course Integration', gapType: 'CAPABILITY_BELOW_TARGET', severity: 'MEDIUM', currentLevel: 'L3_FOUNDATIONAL', targetLevel: 'L2_GOOD', evidenceGaps: ['Non-CS department syllabus copies with AI modules'], capabilityGaps: ['AI modules absent in Mechanical, Civil, Management programs'], dependencyGaps: ['Faculty AI training required first'], recommendedActions: ['Introduce a 15-hour AI application module in 4 non-CS departments'], estimatedEffort: '30_90_DAYS', criImpact: 8.0, domainCode: 'CUR' },
  { id: 'gap-4', assessmentSnapshotId: 'snap-inst1-v1', benchmarkId: 'bm-1', benchmarkCode: 'GOV.STR.001', benchmarkTitle: 'Approved AI Strategy', gapType: 'EVIDENCE_INSUFFICIENT', severity: 'HIGH', currentLevel: 'L3_FOUNDATIONAL', targetLevel: 'L2_GOOD', evidenceGaps: ['Formal Governing Body approval minute'], capabilityGaps: ['Resource allocation schedule incomplete'], dependencyGaps: [], recommendedActions: ['Present the AI roadmap to the Governing Body for formal sign-off'], estimatedEffort: '0_30_DAYS', criImpact: 10.0, domainCode: 'GOV' },
];

export const seedTransformationMappings: TransformationMapping[] = [
  { id: 'tm-1', gapId: 'gap-1', interventionTemplateId: 'int-gov-policy', goalTemplateId: 'goal-gov-policy', initiativeCode: 'INI-GOV-01', title: 'Establish AI Governance & Ethics Policy', description: 'Draft, review, and formally approve an institution-wide Responsible AI Policy covering ethics, academic integrity, and data protection.', priority: 'CRITICAL', estimatedCriLift: 15.0, timeline: 'Months 1–2', owner: 'Director / IQAC Head', status: 'IN_PROGRESS', linkedBenchmarkIds: ['bm-2'] },
  { id: 'tm-2', gapId: 'gap-2', interventionTemplateId: 'int-fac-training', goalTemplateId: 'goal-fac-training', initiativeCode: 'INI-FAC-01', title: 'Faculty AI Capacity Building Drive', description: 'Conduct a structured 4-week Faculty Development Program in AI for 80+ faculty across all non-CS departments.', priority: 'CRITICAL', estimatedCriLift: 12.0, timeline: 'Months 1–3', owner: 'Dean Academics', status: 'PROPOSED', linkedBenchmarkIds: ['bm-5'] },
  { id: 'tm-3', gapId: 'gap-3', interventionTemplateId: 'int-cur-integration', goalTemplateId: 'goal-cur-integration', initiativeCode: 'INI-CUR-01', title: 'Cross-Disciplinary AI Curriculum Upgrade', description: 'Integrate applied AI modules into 6 non-CS degree programs with Board of Studies approval.', priority: 'HIGH', estimatedCriLift: 8.0, timeline: 'Months 3–4', owner: 'Board of Studies Chairs', status: 'PROPOSED', linkedBenchmarkIds: ['bm-4'] },
  { id: 'tm-4', gapId: 'gap-4', interventionTemplateId: 'int-gov-strategy', goalTemplateId: 'goal-gov-strategy', initiativeCode: 'INI-GOV-02', title: 'Formalize 3-Year Institutional AI Strategy', description: 'Secure Governing Body approval for a 3-year AI transformation roadmap with dedicated budget.', priority: 'HIGH', estimatedCriLift: 10.0, timeline: 'Months 1–2', owner: 'Director', status: 'APPROVED', linkedBenchmarkIds: ['bm-1'] },
];

// ===== APPROVALS, CANDIDATES, AUDIT =====
export const seedApprovalRequests: ApprovalRequest[] = [
  { id: 'appr-1', objectType: 'BENCHMARK', objectId: 'bm-10', requestedBy: 'BENCHMARK_EDITOR', requestedAt: '2026-07-01T14:00:00Z', status: 'PENDING', reviewerComments: 'Submitted for methodology review', reviewedBy: null, reviewedAt: null, action: null },
  { id: 'appr-2', objectType: 'BENCHMARK', objectId: 'bm-11', requestedBy: 'BENCHMARK_EDITOR', requestedAt: '2026-07-15T09:30:00Z', status: 'PENDING', reviewerComments: 'Draft ready for initial review', reviewedBy: null, reviewedAt: null, action: null },
  { id: 'appr-3', objectType: 'BENCHMARK_VERSION', objectId: 'bm-1-v1', requestedBy: 'BENCHMARK_EDITOR', requestedAt: '2026-05-28T11:00:00Z', status: 'APPROVED', reviewerComments: 'Approved after peer review of the L3/L2/L1 definitions.', reviewedBy: 'u5', reviewedAt: '2026-05-30T16:00:00Z', action: 'PUBLISH' },
];

export const seedCandidates: BenchmarkCandidate[] = [
  { id: 'cand-1', suggestedTitle: 'AI Cybersecurity & Model Risk Governance', suggestedCode: 'INF.SEC.001', suggestedOntologyPath: 'Infrastructure & Data > Cybersecurity', suggestedDefinition: 'Framework for assessing, monitoring, and mitigating security vulnerabilities and data-leakage risks in deployed AI tools.', suggestedLevels: { L3: 'Basic password protection and anti-virus for AI endpoints', L2: 'Documented AI model access policy and API credential security', L1: 'Continuous automated red-teaming, model vulnerability scanning, and zero-trust architecture' }, sourceClaimIds: ['sc-1', 'sc-7'], aiConfidence: 0.84, criticFindings: [{ id: 'cf-1', candidateId: 'cand-1', checkType: 'DEFINITIONAL_CLARITY', severity: 'INFO', finding: 'L3 definition needs clearer observable criteria', suggestion: 'Specify minimum technical controls', overriddenBy: null, overrideReason: null }], impactSummary: 'Affects 100% of technical institutions; estimated average CRI change of −3.2 points due to a new security gate.', status: 'READY_FOR_REVIEW', createdBy: 'AI_AGENT_RESEARCHER', createdAt: '2026-07-20T10:00:00Z', agentRunId: 'arun-101' },
  { id: 'cand-2', suggestedTitle: 'GenAI Academic Integrity Automated Verification', suggestedCode: 'CUR.INT.002', suggestedOntologyPath: 'Curriculum & Academic Readiness > Academic Integrity', suggestedDefinition: 'Institutional deployment of AI plagiarism and disclosure verification protocols across all student assessments.', suggestedLevels: { L3: 'Informal guidelines asking students to declare AI usage', L2: 'Mandatory AI usage disclosure form and detection tooling in place', L1: 'Integrated LMS submission pipeline with automated AI attribution analysis' }, sourceClaimIds: ['sc-5'], aiConfidence: 0.79, criticFindings: [{ id: 'cf-2', candidateId: 'cand-2', checkType: 'OVERLAP_CHECK', severity: 'WARNING', finding: 'Potential overlap with GOV.POL.001 (Responsible AI Policy)', suggestion: 'Cross-reference and scope strictly to assessment verification', overriddenBy: null, overrideReason: null }], impactSummary: 'Affects all institutions; provides a potential +4.5-point CRI lift.', status: 'NEW', createdBy: 'AI_AGENT_RESEARCHER', createdAt: '2026-07-21T15:30:00Z', agentRunId: 'arun-102' },
];

export const seedImpactSimulation: ImpactSimulation = {
  id: 'sim-1', candidateId: 'cand-1', ruleChangeId: null, simulationType: 'NEW_BENCHMARK',
  affectedInstitutions: 14, expectedCriMovement: { min: -5.2, max: 2.1 },
  newEvidenceBurden: 2, newGatesTriggered: 1, riskLevel: 'MEDIUM',
  summary: 'Adding INF.SEC.001 as a Critical benchmark would lower the average CRI from 48.2 to 44.5 across a test cohort of 14 institutions, because of the strict security gate. 3 institutions meet L2.',
  simulatedAt: '2026-07-20T11:00:00Z',
};

export const seedAuditEvents: BenchmarkAuditEvent[] = [
  { id: 'bae-1', actor: 'Admin User (u5)', action: 'BENCHMARK_PUBLISHED', objectType: 'BENCHMARK', objectId: 'bm-1', beforeHash: 'hash_draft_1', afterHash: 'hash_pub_1', timestamp: '2026-06-01T10:00:00Z', reason: 'Official release of Pilot Benchmark Library v1.0', requestId: 'req-001' },
  { id: 'bae-2', actor: 'Admin User (u5)', action: 'ASSESSMENT_CALCULATED', objectType: 'INSTITUTION_ASSESSMENT', objectId: 'snap-inst1-v1', beforeHash: null, afterHash: 'hash_snap_1', timestamp: '2026-08-30T10:00:00Z', reason: 'Official baseline assessment calculation', requestId: 'req-002' },
];
