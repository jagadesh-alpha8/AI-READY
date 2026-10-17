import React, { useState } from 'react';
import { Download, Link as LinkIcon, Upload } from 'lucide-react';

import { ErrorState, InlineError, LoadingState } from '../../components/ApiStates';
import { useApiResource } from '../../hooks/useApiResource';
import { getErrorMessage } from '../../utils/errors';
import {
  decideCycleBenchmark, downloadEvidence, getCycleBenchmark, listScoreRules, reviewEvidence, saveAssessorInput,
  saveScoreRule, uploadEvidence, listSprintDocuments, listTemplates, createTemplate, updateTemplate,
} from '../../api/assessments';
import type {
  AssessmentReference, CycleBenchmarkDetail, EvidenceItemInfo, EvidenceRequest, Level, ReviewDecision, ScoreDetail,
  SprintDocumentOption, TransformationTemplateInfo,
} from '../../api/assessments';
import { fmt } from './BenchmarkAssessments';

const EV_BADGE: Record<string, string> = {
  submitted: 'badge-warning', accepted: 'badge-success', rejected: 'badge-danger', needs_information: 'badge-warning',
};
const LEVELS: Level[] = ['L3', 'L2', 'L1'];
const LEVEL_NAME: Record<string, string> = { L3: 'L3 Foundational', L2: 'L2 Good / Recommended', L1: 'L1 Advanced / Aspirational', '': 'Any level' };

export const CycleBenchmarkPanel: React.FC<{ cycleId: string; code: string; reference: AssessmentReference; onChanged: () => void }> = (
  { cycleId, code, reference, onChanged },
) => {
  const d = useApiResource<CycleBenchmarkDetail>(() => getCycleBenchmark(cycleId, code), [cycleId, code]);
  const refresh = () => { d.refetch(); onChanged(); };
  const [err, setErr] = useState('');

  if (d.loading) return <LoadingState message="Loading benchmark…" />;
  if (d.error || !d.data) return <ErrorState message={d.error || 'Not found'} onRetry={d.refetch} />;
  const b = d.data;
  const staff = reference.is_staff;
  const canUpload = reference.can_upload && b.cycle_status === 'in_progress' && !!b.included;
  const canReview = staff && ['in_progress', 'submitted', 'reviewed'].includes(b.cycle_status);

  const decide = async (body: { included?: boolean; target_level?: Level }) => {
    setErr('');
    const goesAgainst = body.included !== undefined && b.applicability_result !== 'requires_review'
      && body.included !== (b.applicability_result === 'applies');
    const note = goesAgainst ? window.prompt('This goes against the applicability rules. Why?', '') : '';
    if (goesAgainst && !note) return;
    try { await decideCycleBenchmark(cycleId, code, { ...body, note: note || '' }); refresh(); } catch (e) { setErr(getErrorMessage(e)); }
  };

  return (
    <div className="rounded-lg border border-brand-500/40 bg-surface p-3 space-y-3">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="font-mono text-ink-500">{b.benchmark_code}</span>
        <span className="text-sm font-bold text-ink-900 flex-1">{b.title}</span>
        <span className="badge badge-neutral" title={`Frozen snapshot #${b.snapshot_hash}`}>{b.release_label}</span>
      </div>
      <p className="text-ink-600"><strong>Applies?</strong> {b.applicability_result.replace(/_/g, ' ')} — {b.applicability_reason}
        {b.selected_by !== 'rules_engine' ? ` · decided by a reviewer${b.decision_note ? `: "${b.decision_note}"` : ''}` : ''}</p>

      {staff && ['not_started', 'in_progress'].includes(b.cycle_status) && (
        <div className="flex flex-wrap gap-2 items-center">
          {b.included !== true && <button className="btn-secondary btn-sm" onClick={() => decide({ included: true })}>Include</button>}
          {b.included !== false && <button className="btn-secondary btn-sm" onClick={() => decide({ included: false })}>Leave out</button>}
          <span className="text-ink-500">Target level</span>
          <select className="input text-xs w-auto" value={b.target_level} onChange={(e) => decide({ target_level: e.target.value as Level })}>
            {LEVELS.map((l) => <option key={l} value={l}>{LEVEL_NAME[l]}</option>)}
          </select>
        </div>
      )}
      {err && <InlineError message={err} onDismiss={() => setErr('')} />}

      <details>
        <summary className="cursor-pointer font-bold text-ink-900">What each level means</summary>
        <div className="space-y-2 pt-2">
          {LEVELS.map((l) => b.levels[l] && (
            <div key={l}>
              <p className="font-bold">{LEVEL_NAME[l]}{l === b.target_level ? ' — target' : ''}</p>
              <p className="text-ink-700 whitespace-pre-line">{b.levels[l]!.definition}</p>
            </div>
          ))}
          {b.requirements.length > 0 && (
            <p className="text-ink-500">Based on: {b.requirements.map((r) => `${r.code} (${r.source_code}${r.page ? ` p.${r.page}` : ''})`).join(', ')}</p>
          )}
        </div>
      </details>

      {b.included && (
        <div className="space-y-2">
          <p className="font-bold text-ink-900">Evidence requested</p>
          {b.requests.map((r) => (
            <RequestCard key={r.key} r={r} cycleId={cycleId} code={code} canUpload={canUpload} canReview={canReview} onChanged={refresh} />
          ))}
          {b.requests.length === 0 && <p className="text-ink-500">This release has no evidence rules for this benchmark.</p>}
        </div>
      )}

      {staff && b.preview && <ScoreBox title="Scores if calculated now (not saved)" scores={b.preview.scores} level={b.preview.current_level} composite={b.preview.composite} detail={b.preview.detail} />}
      {b.assessment && (
        <ScoreBox title="Saved scores" level={b.assessment.current_level} composite={b.assessment.composite_score} detail={b.assessment.detail}
          scores={{ compliance: b.assessment.compliance_score, maturity: b.assessment.maturity_score,
                    evidence_confidence: b.assessment.evidence_confidence_score, outcome: b.assessment.outcome_score }} />
      )}
      {staff && b.included && ['submitted', 'reviewed'].includes(b.cycle_status) && (
        <AssessorForm cycleId={cycleId} code={code} detail={b} onSaved={refresh} />
      )}
      {staff && b.included && <WeightsForm code={code} />}
      {staff && b.included && <TemplatesForm code={code} />}
    </div>
  );
};

const RequestCard: React.FC<{ r: EvidenceRequest; cycleId: string; code: string; canUpload: boolean; canReview: boolean; onChanged: () => void }> = (
  { r, cycleId, code, canUpload, canReview, onChanged },
) => {
  const [adding, setAdding] = useState(false);
  const [title, setTitle] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [url, setUrl] = useState('');
  const [issued, setIssued] = useState('');
  const [valid, setValid] = useState('');
  const [desc, setDesc] = useState('');
  const [auditDoc, setAuditDoc] = useState('');
  const [auditDocs, setAuditDocs] = useState<SprintDocumentOption[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const accepted = r.items.filter((i) => i.status === 'accepted').length;

  const send = async () => {
    setBusy(true); setErr('');
    try {
      await uploadEvidence(cycleId, code, { rule_key: r.key, title, description: desc, source_url: url, issued_on: issued, valid_until: valid, file, sprint_document: auditDoc || undefined });
      setAdding(false); setTitle(''); setFile(null); setUrl(''); setIssued(''); setValid(''); setDesc(''); setAuditDoc(''); onChanged();
    } catch (e) { setErr(getErrorMessage(e)); } finally { setBusy(false); }
  };

  return (
    <div className="rounded-lg border border-line-200 p-2 space-y-1">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="badge badge-neutral">{LEVEL_NAME[r.level || '']}</span>
        <span className="font-bold text-ink-900 flex-1">{r.title}</span>
        {r.mandatory ? <span className="badge badge-warning">required</span> : <span className="badge badge-neutral">optional</span>}
        <span className={accepted >= r.minimum_count ? 'text-success' : 'text-ink-500'}>{accepted}/{r.minimum_count} accepted</span>
      </div>
      <p className="text-ink-500">
        {r.evidence_type_name}{r.minimum_currency_months ? ` · issued within the last ${r.minimum_currency_months} months` : ''}
        {r.scope_rule ? ` · must cover: ${r.scope_rule}` : ''}
      </p>
      {r.items.map((i) => <EvidenceRow key={i.id} item={i} canReview={canReview} onChanged={onChanged} />)}
      {canUpload && !adding && <button className="btn-secondary btn-sm" onClick={() => {
        setAdding(true);
        if (auditDocs === null) listSprintDocuments(cycleId).then((x) => setAuditDocs(x.data)).catch(() => setAuditDocs([]));
      }}><Upload className="w-3.5 h-3.5" /> Add evidence</button>}
      {adding && (
        <div className="space-y-2 pt-1">
          <input className="input text-xs" placeholder="Title, e.g. Academic integrity policy (approved by Academic Council)" value={title} onChange={(e) => setTitle(e.target.value)} />
          <div className="grid md:grid-cols-2 gap-2">
            <input className="input text-xs" type="file" onChange={(e) => setFile(e.target.files?.[0] || null)} />
            <input className="input text-xs" placeholder="…or a link (https://)" value={url} onChange={(e) => setUrl(e.target.value)} />
            <select className="input text-xs md:col-span-2" value={auditDoc} onChange={(e) => setAuditDoc(e.target.value)}>
              <option value="">…or reuse a document already uploaded in an AI Readiness Audit sprint{auditDocs ? ` (${auditDocs.length})` : ''}</option>
              {(auditDocs || []).map((d) => <option key={d.id} value={d.id}>{d.title} — {d.sprint}</option>)}
            </select>
            <label className="text-ink-500">Issued on <input className="input text-xs" type="date" value={issued} onChange={(e) => setIssued(e.target.value)} /></label>
            <label className="text-ink-500">Valid until (if any) <input className="input text-xs" type="date" value={valid} onChange={(e) => setValid(e.target.value)} /></label>
          </div>
          <input className="input text-xs" placeholder="Short note (optional)" value={desc} onChange={(e) => setDesc(e.target.value)} />
          <div className="flex gap-2">
            <button className="btn-primary btn-sm" disabled={busy || !title.trim() || (!file && !url.trim() && !auditDoc)} onClick={send}>Upload</button>
            <button className="btn-secondary btn-sm" onClick={() => setAdding(false)}>Cancel</button>
          </div>
          <p className="text-ink-400">PDF, Word, Excel, PowerPoint, CSV, text or images, up to 25 MB. Don't upload personal data of students or staff unless the request asks for it.</p>
        </div>
      )}
      {err && <InlineError message={err} onDismiss={() => setErr('')} />}
    </div>
  );
};

const EvidenceRow: React.FC<{ item: EvidenceItemInfo; canReview: boolean; onChanged: () => void }> = ({ item, canReview, onChanged }) => {
  const [reviewing, setReviewing] = useState(false);
  const [scores, setScores] = useState({ relevance_score: 80, completeness_score: 80, currency_score: 80, authenticity_score: 80, scope_score: 80 });
  const [notes, setNotes] = useState('');
  const [err, setErr] = useState('');
  const last = item.reviews[0];

  const download = async () => {
    try {
      const blob = (await downloadEvidence(item.id)).data;
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = item.original_filename || 'evidence';
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e) { setErr(getErrorMessage(e)); }
  };
  const decide = async (decision: ReviewDecision) => {
    setErr('');
    try { await reviewEvidence(item.id, { decision, notes, ...scores }); setReviewing(false); onChanged(); }
    catch (e) { setErr(getErrorMessage(e)); }
  };

  return (
    <div className="rounded border border-line-200 bg-surface p-2 space-y-1">
      <div className="flex items-center gap-2 flex-wrap">
        <span className={`badge ${EV_BADGE[item.status]}`}>{item.status_label}</span>
        <span className="text-ink-900 flex-1 min-w-0">{item.title}</span>
        {item.from_audit && <span className="badge badge-neutral">from audit</span>}
        {item.has_file && <button className="btn-secondary btn-sm" onClick={download} title={`SHA-256 ${item.file_sha256}`}><Download className="w-3.5 h-3.5" /> {item.original_filename}</button>}
        {item.source_url && <a className="text-brand-600 underline flex items-center gap-1" href={item.source_url} target="_blank" rel="noreferrer"><LinkIcon className="w-3 h-3" /> link</a>}
      </div>
      <p className="text-ink-500">by {item.submitted_by}{item.issued_on ? ` · issued ${item.issued_on}` : ' · no issue date'}{item.valid_until ? ` · valid until ${item.valid_until}` : ''}{item.description ? ` · ${item.description}` : ''}</p>
      {last && (
        <p className="text-ink-600">
          {last.decision_label} by {last.reviewer}{last.notes ? ` — "${last.notes}"` : ''} · quality {fmt(String(
            (Number(last.relevance_score) + Number(last.completeness_score) + Number(last.currency_score) + Number(last.authenticity_score) + Number(last.scope_score)) / 5))}
        </p>
      )}
      {canReview && !reviewing && <button className="btn-secondary btn-sm" onClick={() => setReviewing(true)}>{last ? 'Review again' : 'Review'}</button>}
      {reviewing && (
        <div className="space-y-2">
          <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
            {(Object.keys(scores) as (keyof typeof scores)[]).map((k) => (
              <label key={k} className="text-ink-500">{k.replace('_score', '')}
                <input className="input text-xs" type="number" min={0} max={100} value={scores[k]}
                  onChange={(e) => setScores({ ...scores, [k]: Number(e.target.value) })} />
              </label>
            ))}
          </div>
          <input className="input text-xs" placeholder="Note to the college (needed to reject or ask for more)" value={notes} onChange={(e) => setNotes(e.target.value)} />
          <div className="flex flex-wrap gap-2">
            <button className="btn-primary btn-sm" onClick={() => decide('accepted')}>Accept</button>
            <button className="btn-secondary btn-sm" onClick={() => decide('needs_information')}>Ask for more</button>
            <button className="btn-secondary btn-sm" onClick={() => decide('rejected')}>Reject</button>
            <button className="btn-secondary btn-sm" onClick={() => setReviewing(false)}>Cancel</button>
          </div>
          <p className="text-ink-400">Scores 0-100: is it about this request (relevance), is it complete, is it recent (currency), is it genuine (authenticity), does it cover the whole institution or programme (scope).</p>
        </div>
      )}
      {err && <InlineError message={err} onDismiss={() => setErr('')} />}
    </div>
  );
};

const ScoreBox: React.FC<{ title: string; scores: Record<string, string | null>; level: string; composite: string | null; detail: ScoreDetail }> = (
  { title, scores, level, composite, detail },
) => (
  <div className="rounded-lg border border-line-200 p-2 space-y-1">
    <p className="font-bold text-ink-900">{title}</p>
    <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
      {[['Compliance', 'compliance'], ['Maturity', 'maturity'], ['Evidence confidence', 'evidence_confidence'], ['Outcome', 'outcome']].map(([label, k]) => (
        <div key={k} title={(detail as Record<string, unknown>)[k] as string}>
          <p className="text-ink-500">{label}</p>
          <p className="text-sm font-bold text-ink-900">{fmt(scores[k])}</p>
          <p className="text-ink-400">{(detail as Record<string, unknown>)[k] as string}</p>
        </div>
      ))}
      <div>
        <p className="text-ink-500">Composite</p>
        <p className="text-sm font-bold text-ink-900">{fmt(composite)}</p>
        <p className="text-ink-400">{detail.composite}</p>
      </div>
    </div>
    <p className="text-ink-600">Level reached: <strong>{level || 'none'}</strong>{detail.needs_assessor_confirmation ? ' — the assessor must confirm this level' : ''}</p>
    {(detail.level_notes || []).map((n) => <p key={n} className="text-ink-500">{n}</p>)}
  </div>
);

const AssessorForm: React.FC<{ cycleId: string; code: string; detail: CycleBenchmarkDetail; onSaved: () => void }> = ({ cycleId, code, detail, onSaved }) => {
  const a = detail.assessment;
  const [outcome, setOutcome] = useState(a?.outcome_score ?? '');
  const [outcomeNote, setOutcomeNote] = useState(a?.outcome_note || '');
  const [override, setOverride] = useState(a?.level_override || '');
  const [overrideNote, setOverrideNote] = useState(a?.override_note || '');
  const [err, setErr] = useState('');
  const [ok, setOk] = useState('');
  const save = async () => {
    setErr(''); setOk('');
    try {
      await saveAssessorInput(cycleId, code, { outcome_score: outcome === '' ? null : Number(outcome), outcome_note: outcomeNote,
        level_override: override, override_note: overrideNote });
      setOk('Saved.'); onSaved();
    } catch (e) { setErr(getErrorMessage(e)); }
  };
  return (
    <div className="rounded-lg border border-line-200 p-2 space-y-2">
      <p className="font-bold text-ink-900">Assessor</p>
      <div className="grid md:grid-cols-[8rem_1fr] gap-2">
        <input className="input text-xs" type="number" min={0} max={100} placeholder="Outcome 0-100" value={outcome} onChange={(e) => setOutcome(e.target.value)} />
        <input className="input text-xs" placeholder="Which measured result is this based on?" value={outcomeNote} onChange={(e) => setOutcomeNote(e.target.value)} />
        <select className="input text-xs" value={override} onChange={(e) => setOverride(e.target.value)}>
          <option value="">Level from evidence</option>
          {LEVELS.map((l) => <option key={l} value={l}>Set {l}</option>)}
        </select>
        <input className="input text-xs" placeholder="Why the level differs from the evidence (needed if set)" value={overrideNote} onChange={(e) => setOverrideNote(e.target.value)} />
      </div>
      <button className="btn-primary btn-sm" onClick={save}>Save</button>
      {ok && <span className="text-success ml-2">{ok}</span>}
      {err && <InlineError message={err} onDismiss={() => setErr('')} />}
    </div>
  );
};

/** Composite weights for one benchmark (approved by an InGage person; also used in Studio > Levels). */
export const WeightsForm: React.FC<{ code: string; onSaved?: () => void }> = ({ code, onSaved }) => {
  const rules = useApiResource(() => listScoreRules(), []);
  const row = rules.data?.rules.find((r) => r.benchmark_code === code);
  const [w, setW] = useState<{ compliance: string; maturity: string; evidence: string; outcome: string } | null>(null);
  const [note, setNote] = useState('');
  const [err, setErr] = useState('');
  if (!rules.data) return null;
  const current = w || {
    compliance: row?.weights?.compliance || '0.25', maturity: row?.weights?.maturity || '0.25',
    evidence: row?.weights?.evidence_confidence || '0.25', outcome: row?.weights?.outcome || '0.25',
  };
  const save = async () => {
    setErr('');
    try {
      await saveScoreRule(code, { compliance_weight: current.compliance, maturity_weight: current.maturity,
        evidence_weight: current.evidence, outcome_weight: current.outcome, note });
      setW(null); setNote(''); rules.refetch(); onSaved?.();
    } catch (e) { setErr(getErrorMessage(e)); }
  };
  return (
    <details className="rounded-lg border border-line-200 p-2">
      <summary className="cursor-pointer font-bold text-ink-900">
        Composite weights ({rules.data.scoring_model}) — {row?.weights ? `approved by ${row.approved_by}` : 'not approved yet, so no composite'}
      </summary>
      <div className="space-y-2 pt-2">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          {(['compliance', 'maturity', 'evidence', 'outcome'] as const).map((k) => (
            <label key={k} className="text-ink-500">{k}
              <input className="input text-xs" value={current[k]} onChange={(e) => setW({ ...current, [k]: e.target.value })} />
            </label>
          ))}
        </div>
        <input className="input text-xs" placeholder='Who approved and why, e.g. "Approved by Dr. X, benchmark owner, 13 Oct"' value={note} onChange={(e) => setNote(e.target.value)} />
        <button className="btn-primary btn-sm" onClick={save}>Save weights</button>
        <p className="text-ink-400">The four must add up to 1. They apply the next time scores are calculated; finalized assessments keep the weights they used.</p>
        {err && <InlineError message={err} onDismiss={() => setErr('')} />}
      </div>
    </details>
  );
};

const GAP_TYPES: [string, string][] = [
  ['capability', 'Capability (level below target)'], ['compliance', 'Compliance'], ['evidence', 'Evidence quality'],
  ['outcome', 'Outcome'], ['dependency', 'Dependency'],
];

/** The expert's playbook for closing each kind of gap on this benchmark; used
 * when an improvement plan is generated (otherwise the plan lists the unmet
 * evidence requests as tasks). */
const TemplatesForm: React.FC<{ code: string }> = ({ code }) => {
  const list = useApiResource<TransformationTemplateInfo[]>(() => listTemplates(code), [code]);
  const [gapType, setGapType] = useState('capability');
  const existing = (list.data || []).find((t) => t.gap_type === gapType);
  const [form, setForm] = useState<Record<string, string>>({});
  const [err, setErr] = useState('');
  const [ok, setOk] = useState('');
  const value = (k: keyof TransformationTemplateInfo) =>
    form[k] ?? (k === 'tasks' ? (existing?.tasks || []).join('\n') : String(existing?.[k] ?? ''));
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setForm({ ...form, [k]: e.target.value });
  const save = async () => {
    setErr(''); setOk('');
    const body = {
      benchmark_code: code, gap_type: gapType, title: value('title'), intervention: value('intervention'),
      expected_evidence: value('expected_evidence'), expected_outcome: value('expected_outcome'),
      tasks: value('tasks').split('\n').map((x) => x.trim()).filter(Boolean),
    };
    try {
      if (existing) await updateTemplate(existing.id, body); else await createTemplate(body);
      setForm({}); setOk('Saved — used for plans generated from now on.'); list.refetch();
    } catch (e) { setErr(getErrorMessage(e)); }
  };
  return (
    <details className="rounded-lg border border-line-200 p-2">
      <summary className="cursor-pointer font-bold text-ink-900">
        Improvement templates — {(list.data || []).length ? (list.data || []).map((t) => t.gap_type).join(', ') : 'none yet'}
      </summary>
      <div className="space-y-2 pt-2">
        <select className="input text-xs w-auto" value={gapType} onChange={(e) => { setGapType(e.target.value); setForm({}); }}>
          {GAP_TYPES.map(([k, l]) => <option key={k} value={k}>{l}{(list.data || []).some((t) => t.gap_type === k) ? ' ✓' : ''}</option>)}
        </select>
        <input className="input text-xs" placeholder="Initiative title" value={value('title')} onChange={set('title')} />
        <textarea className="input text-xs" rows={2} placeholder="What the college should do" value={value('intervention')} onChange={set('intervention')} />
        <input className="input text-xs" placeholder="Evidence that proves it was done" value={value('expected_evidence')} onChange={set('expected_evidence')} />
        <input className="input text-xs" placeholder="Measurable outcome expected" value={value('expected_outcome')} onChange={set('expected_outcome')} />
        <textarea className="input text-xs" rows={3} placeholder="Tasks, one per line (optional)" value={value('tasks')} onChange={set('tasks')} />
        <button className="btn-primary btn-sm" onClick={save}>{existing ? 'Update template' : 'Save template'}</button>
        {ok && <span className="text-success ml-2">{ok}</span>}
        {err && <InlineError message={err} onDismiss={() => setErr('')} />}
      </div>
    </details>
  );
};
