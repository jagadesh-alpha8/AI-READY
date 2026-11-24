import { useMemo } from 'react';
import { areaTitle } from '../utils/areaTitles';
import { useCapability } from '../hooks/useCapability';
import type { ChecklistItem, ConditionRecord, FoundationPlan, NextStepAction, PriorityPlan, Result, Run } from '../types/capability';
import { cleanText, displayQuote, docLabel, quoteQuality } from './plain';
import { countedShare, headlineScore, pillarName } from '../utils/capability';
import { levelFor, type Level } from '../utils/levels';

/** One readiness area as the screens and the report show it. */
export interface AreaView {
  code: string;
  name: string;
  /** The area's score as it counts now. */
  score: number;
  /** What the documents show before any credit is held for the follow-up answers (>= score). */
  shown: number;
  level: ReturnType<typeof levelFor>;
  requirements: number;
  inPlace: number;
  partly: number;
  /** One line from the college's own documents that earned credit here, with where it came from. */
  quote: { text: string; source: string } | null;
  /** Requirements not yet done, foundations first: the server's label and plain "done when" line for each. */
  missing: ChecklistItem[];
  explanation: string | null;
  /** Points the priority plan's actions in this area would add. */
  pointsAvailable: number;
  /** Overall points this area could still add if all of it were shown (its key indicators' weights). */
  room: number;
}

export interface ResultView {
  run: Run;
  result: Result;
  final: boolean;
  score: number;
  shownScore: number;
  heldPoints: number;
  level: ReturnType<typeof levelFor>;
  areas: AreaView[];
  strengths: AreaView[];
  focus: AreaView[];
  /** The plan's actions, largest first, that together reach the next level (at most three). */
  toNextLevel: { name: string; area: string; points: number }[];
  /** The three areas with the most overall points still to gain. */
  wherePoints: AreaView[];
  /** The first steps (4 to 6): the leadership report's "What to do next", finished on the server. */
  actions: NextStepAction[];
  /** True when the steps' text was written for this college (else the plain checklist wording). */
  stepsWritten: boolean;
  plan: PriorityPlan | null;
  summary: string;
}

const LEVEL_ORDER: Record<string, number> = { F: 0, A: 1, O: 2 };
const levelOf = (conditionId: string) => LEVEL_ORDER[conditionId.split('.').pop()?.[0] || 'F'] ?? 3;


/** The readiness picture of the latest completed assessment, shaped for people rather than auditors. */
export function buildResultView(run: Run, plan: PriorityPlan | null, foundation: FoundationPlan | null = null): ResultView | null {
  const assessment = run.assessment;
  if (!assessment) return null;
  const result = assessment.result;
  const final = run.stage === 'final';
  const score = headlineScore(result) ?? 0;
  const reserve = result.depth_reserve;
  const records = new Map<string, ConditionRecord>(assessment.records.map((r) => [r.condition_id, r]));
  const pages = new Map<string, string>();
  for (const doc of run.source_manifest || []) {
    doc.pages.forEach((p, i) => pages.set(p.page_id, `${docLabel(doc.filename)}, page ${i + 1}`));
  }
  const names = Array.from(new Set((run.source_manifest || []).map((d) => docLabel(d.filename)).filter((n) => n.length >= 8)))
    .sort((a, b) => b.length - a.length);
  void foundation;   // the foundation plan's roles are no longer used for the first steps (next_steps.py)
  const checklist = run.next_steps?.checklist || {};
  const usedQuotes = new Set<string>();
  const gains = new Map<string, number>();
  for (const a of plan?.actions || []) {
    const area = a.pillar || a.indicator.split('.')[0];
    gains.set(area, (gains.get(area) || 0) + (a.score_gain || 0));
  }

  const totalWeight = result.indicators.reduce((n, i) => n + (i.weight_units || 0), 0);
  const indicatorScore = new Map((result.documented?.indicators || []).map((i) => [i.code, i.score]));
  const areas: AreaView[] = (result.documented?.pillars || []).map((p) => {
    const indicators = result.indicators.filter((i) => i.pillar === p.code || i.code.startsWith(`${p.code}.`));
    const room = totalWeight ? indicators.reduce((n, i) => n + ((i.weight_units || 0) / totalWeight) * (100 - (indicatorScore.get(i.code) ?? 0)), 0) : 0;
    const conditions = indicators.flatMap((i) => i.conditions);
    let credit = 0;
    let counted = 0;
    let inPlace = 0;
    let partly = 0;
    const candidates: { q: number; stage: number; text: string; source: string }[] = [];
    for (const c of conditions) {
      const r = records.get(c.id);
      const cr = r?.credit ?? (r?.state === 'met' ? 1 : 0);
      credit += cr;
      counted += r ? cr * countedShare(r) : cr;
      if (cr >= 1) inPlace += 1;
      else if (cr > 0) partly += 1;
      if (cr >= 0.5) {
        const cites = r?.citations?.length ? r.citations : (r?.parts || []).flatMap((x) => x.citations || []);
        for (const cite of cites) {
          const q = cite.quote ? quoteQuality(cite.quote, cr) : 0;
          if (q > 0) candidates.push({ q, stage: levelOf(c.id), text: cite.quote, source: pages.get(cite.source_id) || 'your documents' });
        }
      }
    }
    // The held part, area by area: requirements count equally within an area, so the ratio of credit shown to
    // credit counted scales the area's own score.
    const best = candidates.sort((x, y) => y.q - x.q || x.stage - y.stage).find((x) => !usedQuotes.has(x.text));
    if (best) usedQuotes.add(best.text);
    const quote: AreaView['quote'] = best ? { text: displayQuote(best.text), source: best.source } : null;
    const ratio = counted > 0 ? credit / counted : 1;
    const shown = Math.min(100, p.score * ratio);
    const exp = p.explanation;
    return {
      code: p.code, name: pillarName(p.code), score: p.score, shown, level: levelFor(p.score),
      requirements: conditions.length, inPlace, partly, quote,
      missing: checklist[p.code] || [],
      explanation: exp ? cleanText([exp.found, exp.text].filter(Boolean).join(' '), names) || null : null,
      pointsAvailable: gains.get(p.code) || 0, room,
    };
  });

  const byScore = [...areas].sort((a, b) => b.score - a.score);
  const strengths = byScore.filter((a) => a.score > 0).slice(0, 3);
  const focus = [...areas].sort((a, b) => a.score - b.score || b.pointsAvailable - a.pointsAvailable)
    .filter((a) => !strengths.includes(a)).slice(0, 3);
  const level = levelFor(score);
  const toNextLevel: ResultView['toNextLevel'] = [];
  let gathered = 0;
  for (const a of [...(plan?.actions || [])].sort((x, y) => y.score_gain - x.score_gain)) {
    if (toNextLevel.length >= 5 || (level.next && gathered >= level.pointsToNext)) break;
    toNextLevel.push({ name: areaTitle(a.indicator, a.name), area: pillarName(a.pillar || a.indicator.split('.')[0]), points: a.score_gain });
    gathered += a.score_gain;
  }
  const wherePoints = [...areas].sort((a, b) => b.room - a.room).slice(0, 3);
  const actions = run.next_steps?.actions || [];
  const heldPoints = reserve?.still_held_points ?? 0;
  const summary = strengths.length
    ? `Your documents show the most in ${strengths[0].name}${strengths[1] ? `, followed by ${strengths[1].name}` : ''}.${focus.length ? ` Focus next on ${focus[0].name}${focus[1] ? `, then ${focus[1].name}` : ''}.` : ''}`
    : 'Your documents show little AI-specific practice so far. The areas below show where to start.';
  return {
    run, result, final, score, shownScore: Math.min(100, score + heldPoints), heldPoints, level, areas, strengths, focus,
    toNextLevel, wherePoints, actions, stepsWritten: !!run.next_steps?.written, plan, summary,
  };
}

/** The capability hook plus the shaped result. */
export function useResultView(sprintId: string) {
  const cap = useCapability(sprintId);
  const plan = cap.plan?.priority_plan || null;
  const foundation = cap.foundation;
  const view = useMemo(() => (cap.run.data ? buildResultView(cap.run.data, plan, foundation) : null), [cap.run.data, plan, foundation]);
  return { cap, view };
}

export type { Level };
