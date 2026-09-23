// ===================================================================
// Benchmark scoring, gap generation, critic and simulator.
//
// PORTED from the InGage "AI Future Ready" prototype
// (`src/services/benchmarkServices.ts`). The rules are the manager's; two
// defects in the original are fixed here and noted inline rather than
// reproduced.
//
// ⚠ This is a SECOND scoring model. The platform's own CRI engine
// (`apps/scoring/services/cri_engine.py`) scores 8 pillars from confirmed
// facts; this scores 8 domains from benchmark maturity levels. They will not
// agree. Which one is authoritative is an open decision — nothing here feeds
// the real engine, and nothing here is persisted.
// ===================================================================

import { seedCRIRuleVersion } from './seed';
import type {
  Benchmark, BenchmarkAssessment, BenchmarkCandidate, BenchmarkVersion,
  CRIRuleVersion, CriticFinding, DomainScore, GapResult, ImpactSimulation,
  MaturityLevel,
} from './types';

/** Reading order, lowest capability first. Note that L1 is the TOP. */
export const MATURITY_ORDER: MaturityLevel[] = ['L3_FOUNDATIONAL', 'L2_GOOD', 'L1_ADVANCED'];

export const MATURITY_LABELS: Record<MaturityLevel, string> = {
  L3_FOUNDATIONAL: 'L3 · Foundational',
  L2_GOOD: 'L2 · Good',
  L1_ADVANCED: 'L1 · Advanced',
};

/** The level → score mapping the whole model rests on. */
const LEVEL_SCORES: Record<MaturityLevel, number> = {
  L3_FOUNDATIONAL: 33.3,
  L2_GOOD: 66.7,
  L1_ADVANCED: 100,
};

const DOMAIN_LABELS: Record<string, string> = {
  GOV: 'Governance & Strategy',
  CUR: 'Curriculum & Academic Readiness',
  FAC: 'Faculty AI Capability',
  STU: 'Student AI Enablement',
  INF: 'Infrastructure & Data',
  RES: 'Research & Innovation',
  IND: 'Industry & Placement',
  EVQ: 'Evidence Quality & Confidence',
};

export function domainLabel(code: string): string {
  return DOMAIN_LABELS[code] || code;
}

export interface CRIResult {
  overallCRI: number;
  domainScores: DomainScore[];
  totalPenalties: number;
  /** Score before gate penalties, so a report can show the deduction rather
   * than only the final number. The original returned no such value, which is
   * why its UI displayed hardcoded penalty figures. */
  baseCRI: number;
}

/**
 * The deterministic CRI calculation, per the prototype's stated rules:
 *
 * 1. A benchmark's maturity level becomes a score (L3 = 33.3, L2 = 66.7,
 *    L1 = 100, unassessed = 0).
 * 2. Non-applicable benchmarks are excluded entirely — not scored zero.
 * 3. Domain scores are averaged, then weighted by the rule version.
 * 4. Hard and soft gates deduct a percentage penalty from the total.
 * 5. Same input, same output, every time — no model judgement anywhere.
 */
export function calculateCRI(
  assessments: BenchmarkAssessment[],
  ruleVersion: CRIRuleVersion = seedCRIRuleVersion,
): CRIResult {
  type Bucket = { totalRaw: number; count: number; gatesPassed: number; gatesFailed: number };
  const domains: Record<string, Bucket> = {};

  Object.keys(ruleVersion.dimensionWeights).forEach((code) => {
    domains[code] = { totalRaw: 0, count: 0, gatesPassed: 0, gatesFailed: 0 };
  });

  assessments.forEach((ba) => {
    if (ba.applicabilityResult === 'DOES_NOT_APPLY') return;

    const code = ba.benchmarkCode.split('.')[0];
    if (!domains[code]) domains[code] = { totalRaw: 0, count: 0, gatesPassed: 0, gatesFailed: 0 };

    domains[code].totalRaw += ba.currentLevel ? LEVEL_SCORES[ba.currentLevel] : 0;
    domains[code].count += 1;

    if (ba.gateStatus === 'PASSED') domains[code].gatesPassed += 1;
    else if (ba.gateStatus === 'HARD_FAIL' || ba.gateStatus === 'SOFT_FAIL') domains[code].gatesFailed += 1;
  });

  let weightedSum = 0;

  const domainScores: DomainScore[] = Object.entries(ruleVersion.dimensionWeights).map(
    ([code, weight]) => {
      const bucket = domains[code] || { totalRaw: 0, count: 0, gatesPassed: 0, gatesFailed: 0 };
      const rawAvg = bucket.count > 0 ? Number((bucket.totalRaw / bucket.count).toFixed(1)) : 0;
      const weighted = Number((rawAvg * weight).toFixed(2));
      if (bucket.count > 0) weightedSum += weighted;

      return {
        domainCode: code,
        domainLabel: domainLabel(code),
        rawScore: rawAvg,
        normalizedScore: rawAvg,
        weight,
        weightedScore: weighted,
        benchmarkCount: bucket.count,
        applicableBenchmarkCount: bucket.count,
        gatesPassed: bucket.gatesPassed,
        gatesFailed: bucket.gatesFailed,
        confidence: bucket.count === 0 ? 'UNVERIFIED' : bucket.gatesFailed === 0 ? 'HIGH' : 'MEDIUM',
      };
    },
  );

  // The original computed this twice and discarded the first result. Only the
  // weighted sum is kept, which is correct while the weights total 1.0.
  const baseCRI = Number(weightedSum.toFixed(1));

  let totalPenalties = 0;
  ruleVersion.gateRules.forEach((gate) => {
    const match = assessments.find((a) => a.benchmarkCode === gate.benchmarkCode);
    if (!match) return;
    if (gate.gateType === 'HARD' && !match.currentLevel) {
      totalPenalties += gate.penaltyPercentage;
    } else if (gate.gateType === 'SOFT' && match.currentLevel === 'L3_FOUNDATIONAL') {
      totalPenalties += gate.penaltyPercentage / 2;
    }
  });

  const overallCRI = Math.max(0, Math.min(100, Number((baseCRI - totalPenalties).toFixed(1))));
  return { overallCRI, domainScores, totalPenalties, baseCRI };
}

/** Every applicable benchmark sitting below its target becomes a gap. */
export function generateGaps(assessments: BenchmarkAssessment[]): GapResult[] {
  const gaps: GapResult[] = [];

  assessments.forEach((ba) => {
    if (ba.applicabilityResult === 'DOES_NOT_APPLY') return;
    if (ba.currentLevel === ba.targetLevel) return;

    const isAbsent = !ba.currentLevel;
    const isCriticalGate = ba.gateStatus === 'HARD_FAIL';

    gaps.push({
      id: `gap-gen-${ba.benchmarkId}`,
      assessmentSnapshotId: ba.snapshotId,
      benchmarkId: ba.benchmarkId,
      benchmarkCode: ba.benchmarkCode,
      benchmarkTitle: ba.benchmarkCode,
      gapType: isAbsent ? 'CAPABILITY_ABSENT' : 'CAPABILITY_BELOW_TARGET',
      severity: isCriticalGate ? 'CRITICAL' : isAbsent ? 'HIGH' : 'MEDIUM',
      currentLevel: ba.currentLevel,
      targetLevel: ba.targetLevel,
      evidenceGaps: ba.evidenceConfidence === 'UNVERIFIED' ? ['Evidence missing'] : [],
      capabilityGaps: [
        `Current level (${ba.currentLevel ? MATURITY_LABELS[ba.currentLevel] : 'none'}) is below target (${MATURITY_LABELS[ba.targetLevel]})`,
      ],
      dependencyGaps: [],
      recommendedActions: [`Build the capability needed to reach ${MATURITY_LABELS[ba.targetLevel]}`],
      estimatedEffort: isAbsent ? '30_90_DAYS' : '0_30_DAYS',
      criImpact: isCriticalGate ? 15.0 : isAbsent ? 10.0 : 5.0,
      domainCode: ba.benchmarkCode.split('.')[0],
    });
  });

  return gaps;
}

export interface ValidationResult {
  isValid: boolean;
  errors: string[];
  warnings: string[];
}

/** A benchmark cannot be published without all three levels defined. */
export function validateBenchmark(benchmark: Benchmark, version: BenchmarkVersion): ValidationResult {
  const errors: string[] = [];
  const warnings: string[] = [];

  if (!benchmark.code) errors.push('A benchmark code is required.');
  if (!benchmark.title) errors.push('A title is required.');
  if (!benchmark.definition) errors.push('A definition is required.');

  const defined = new Set(version.levels.map((l) => l.level));
  MATURITY_ORDER.forEach((level) => {
    if (!defined.has(level)) errors.push(`${MATURITY_LABELS[level]} is not defined.`);
  });

  if (version.evidenceRequirements.length === 0) warnings.push('No evidence requirements are defined.');
  if (version.sourceLinks.length === 0) warnings.push('No authoritative source is cited.');

  return { isValid: errors.length === 0, errors, warnings };
}

/** Published benchmarks are frozen; revising means a new version. */
export function canEditBenchmark(benchmark: Benchmark): { canEdit: boolean; reason?: string } {
  if (benchmark.status === 'PUBLISHED') {
    return {
      canEdit: false,
      reason: 'Published benchmarks are immutable. Create a revision to make changes — editing in place would silently rewrite every score already calculated against this version.',
    };
  }
  return { canEdit: true };
}

/** The adversarial critic: cheap structural checks an AI-drafted candidate
 * must survive before a human spends time reviewing it. */
export function runAdversarialCritic(candidate: BenchmarkCandidate): CriticFinding[] {
  const findings: CriticFinding[] = [...candidate.criticFindings];

  if (candidate.suggestedTitle.trim().length < 10) {
    findings.push({
      id: `cf-${candidate.id}-title`, candidateId: candidate.id,
      checkType: 'DEFINITIONAL_CLARITY', severity: 'WARNING',
      finding: 'The title is too short to identify a specific capability.',
      suggestion: 'Expand it to name the exact capability or outcome being measured.',
      overriddenBy: null, overrideReason: null,
    });
  }

  const { L3, L2, L1 } = candidate.suggestedLevels;
  if (L3.trim().toLowerCase() === L2.trim().toLowerCase()) {
    findings.push({
      id: `cf-${candidate.id}-l3l2`, candidateId: candidate.id,
      checkType: 'LEVEL_DISTINCTNESS', severity: 'ERROR',
      finding: 'L3 and L2 are worded identically, so an assessor cannot tell them apart.',
      suggestion: 'L2 should require systematic, documented adoption rather than initial awareness.',
      overriddenBy: null, overrideReason: null,
    });
  }
  if (L2.trim().toLowerCase() === L1.trim().toLowerCase()) {
    findings.push({
      id: `cf-${candidate.id}-l2l1`, candidateId: candidate.id,
      checkType: 'LEVEL_DISTINCTNESS', severity: 'ERROR',
      finding: 'L2 and L1 are worded identically.',
      suggestion: 'L1 should require measurable outcomes, not just systematic practice.',
      overriddenBy: null, overrideReason: null,
    });
  }

  return findings;
}

/** What adding this benchmark would do to the whole client cohort — the
 * check that stops a well-meaning addition from silently moving everyone's
 * score. The cohort figures are illustrative. */
export function simulateImpact(candidate: BenchmarkCandidate): ImpactSimulation {
  return {
    id: `sim-${candidate.id}`,
    candidateId: candidate.id,
    ruleChangeId: null,
    simulationType: 'NEW_BENCHMARK',
    affectedInstitutions: 14,
    expectedCriMovement: { min: -4.5, max: 1.8 },
    newEvidenceBurden: 2,
    newGatesTriggered: candidate.suggestedCode.startsWith('INF') ? 1 : 0,
    riskLevel: candidate.aiConfidence > 0.8 ? 'LOW' : 'MEDIUM',
    summary: `Simulated adding ${candidate.suggestedCode} across a cohort of 14 institutions. Average CRI shift estimated between −4.5 and +1.8 points.`,
    simulatedAt: new Date().toISOString(),
  };
}
