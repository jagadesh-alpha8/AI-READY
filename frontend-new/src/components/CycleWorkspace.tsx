import { useEffect, useRef, useState } from 'react';
import { useAccess } from '../hooks/useAccess';
import { useResource } from '../hooks/useResource';
import {
  cycleAction, downloadCycleEvidence, getAssessmentReference, getCycleBenchmark, getScorecard, listCycleSprintDocuments, reviewCycleEvidence,
  saveAssessorInput, uploadCycleEvidence, decideCycleBenchmark,
} from '../services/assessments';
import type { CycleDetail } from '../types/api';
import type { AssessmentReference, CycleBenchmarkDetail, CycleEvidenceItem, CycleScorecard, SprintDocumentOption } from '../types/workflow';
import { errorMessage } from '../utils/errors';
import { dateTime, humanize } from '../utils/format';
import { ActionDialog, ErrorState, Loading, Notice, Panel, Pill, Table, type DialogField } from './ui';

/** Lifecycle moves the server allows from each status (apps/assessments CycleActionView). */
const NEXT_ACTIONS: Record<string, ('open' | 'submit' | 'return' | 'score' | 'finalize')[]> = {
  not_started: ['open'],
  in_progress: ['submit'],
  submitted: ['return', 'score'],
  reviewed: ['return', 'score', 'finalize'],
  finalized: [],
};

/** Move the cycle along its lifecycle (staff; coordinators may submit). */
export function CycleActions({ cycle, onChanged }: { cycle: CycleDetail; onChanged: (text: string) => void }) {
  const { can } = useAccess();
  const staff = can('assessments.manage');
  const [moving, setMoving] = useState<'open' | 'submit' | 'return' | 'score' | 'finalize' | null>(null);
  const allowed = (NEXT_ACTIONS[cycle.status] || []).filter((a) => staff || (a === 'submit' && can('documents.contribute')));
  if (!allowed.length) return null;
  return (
    <>
      {allowed.map((a) => (
        <button key={a} className={a === 'finalize' || a === 'open' ? 'primary-action' : 'secondary-button'} onClick={() => setMoving(a)}>{humanize(a)} cycle</button>
      ))}
      {moving && (
        <ActionDialog title={`${humanize(moving)} the cycle?`} confirmLabel={humanize(moving)}
          description={moving === 'finalize' ? 'A finalized cycle is frozen; the improvement plan can then be generated.' : undefined}
          fields={[{ name: 'note', label: 'Note', type: 'textarea', required: moving === 'return' }]}
          onSubmit={async (v) => { await cycleAction(cycle.id, moving, v.note); onChanged(`Cycle: ${humanize(moving)} done.`); }}
          onClose={() => setMoving(null)} />
      )}
    </>
  );
}

/** The cycle's scorecard (visible once InGage has reviewed it). */
export function CycleScorecardPanel({ cycleId }: { cycleId: string }) {
  const scorecard = useResource<CycleScorecard>(() => getScorecard(cycleId), `sc:${cycleId}`);
  return (
    <Panel title="Scorecard" sub={scorecard.data?.scoring_model ? `${scorecard.data.scoring_model.name} · ${scorecard.data.scoring_model.formula_version}` : undefined}>
      {scorecard.loading ? <Loading /> : scorecard.error ? <ErrorState error={scorecard.error} /> : scorecard.data && (
        <>
          {scorecard.data.scoring_model?.description && <p className="muted">{scorecard.data.scoring_model.description}</p>}
          <Table columns={['Benchmark', 'Target', 'Current level', 'Composite']}>
            {scorecard.data.benchmarks.map((b) => (
              <tr key={b.benchmark_code}><td>{b.benchmark_code} · {b.title}</td><td>{b.target_level}</td><td>{b.assessment?.current_level || '—'}</td><td>{b.assessment?.composite_score ?? '—'}</td></tr>
            ))}
          </Table>
        </>
      )}
    </Panel>
  );
}

type Form = { kind: 'scope' | 'assessor' } | { kind: 'evidence'; ruleKey: string; title: string } | { kind: 'review'; item: CycleEvidenceItem };

/** One benchmark inside a cycle: scope and target, evidence requests and items, review, assessor input. */
export function BenchmarkDialog({ cycleId, code, onClose, onChanged }: { cycleId: string; code: string; onClose: () => void; onChanged: () => void }) {
  const { can } = useAccess();
  const staff = can('assessments.manage');
  const detail = useResource<CycleBenchmarkDetail>(() => getCycleBenchmark(cycleId, code), `cb:${cycleId}:${code}`);
  const ref = useResource<AssessmentReference>(getAssessmentReference, 'assess-ref');
  const docs = useResource<SprintDocumentOption[]>(() => listCycleSprintDocuments(cycleId), `cyc-docs:${cycleId}`);
  const [form, setForm] = useState<Form | null>(null);
  const [msg, setMsg] = useState<{ tone: 'success' | 'error'; text: string } | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => { if (dialog.current && !dialog.current.open) dialog.current.showModal?.(); }, []);
  const d = detail.data;
  const canUpload = ref.data?.can_upload ?? true;
  const changed = async (text: string) => { setMsg({ tone: 'success', text }); await detail.refetch(); onChanged(); };

  const formFields = (f: Form): DialogField[] => {
    if (f.kind === 'scope') return [
      { name: 'included', label: 'Include in this cycle', type: 'select', required: true, initial: d?.included === false ? 'no' : 'yes', options: [{ value: 'yes', label: 'Included' }, { value: 'no', label: 'Excluded' }] },
      { name: 'target_level', label: 'Target level', type: 'select', required: true, initial: d?.target_level || 'L2', options: ['L3', 'L2', 'L1'].map((l) => ({ value: l, label: l })) },
      { name: 'note', label: 'Reason', type: 'textarea', required: true },
    ];
    if (f.kind === 'assessor') return [
      { name: 'outcome_score', label: 'Outcome score (0–100, optional)', type: 'number', initial: d?.assessment?.outcome_score || '' },
      { name: 'outcome_note', label: 'Outcome note', type: 'textarea' },
      { name: 'level_override', label: 'Level override', type: 'select', options: ['L3', 'L2', 'L1'].map((l) => ({ value: l, label: l })) },
      { name: 'override_note', label: 'Override reason (required with an override)', type: 'textarea' },
      { name: 'assessor_notes', label: 'Assessor notes', type: 'textarea', initial: d?.assessment?.assessor_notes || '' },
    ];
    if (f.kind === 'evidence') return [
      { name: 'title', label: 'Title', required: true, initial: f.title },
      { name: 'file', label: 'File', type: 'file' },
      { name: 'source_url', label: 'Or a link', type: 'text' },
      { name: 'sprint_document', label: 'Or reuse an audit document', type: 'select', options: (docs.data || []).map((x) => ({ value: x.id, label: `${x.title || x.filename} · ${humanize(x.document_type)}` })) },
      { name: 'issued_on', label: 'Issued on', type: 'date' },
      { name: 'valid_until', label: 'Valid until', type: 'date' },
      { name: 'description', label: 'Description', type: 'textarea' },
    ];
    const scores = ['relevance', 'completeness', 'currency', 'authenticity', 'scope'].map((k) => ({
      name: k, label: `${humanize(k)} (1–5)`, type: 'select' as const, required: true, initial: '3', options: ['1', '2', '3', '4', '5'].map((n) => ({ value: n, label: n })),
    }));
    return [
      { name: 'decision', label: 'Decision', type: 'select', required: true, options: [{ value: 'accepted', label: 'Accept' }, { value: 'needs_information', label: 'Needs information' }, { value: 'rejected', label: 'Reject' }] },
      ...scores,
      { name: 'notes', label: 'Notes', type: 'textarea', required: true },
    ];
  };

  const submit = async (f: Form, v: Record<string, string>, files: Record<string, File | null>) => {
    if (f.kind === 'scope') {
      await decideCycleBenchmark(cycleId, code, { included: v.included === 'yes', target_level: v.target_level, note: v.note });
      return changed('Scope saved.');
    }
    if (f.kind === 'assessor') {
      if (v.level_override && !v.override_note.trim()) throw new Error('Give a reason for the level override.');
      await saveAssessorInput(cycleId, code, {
        outcome_score: v.outcome_score === '' ? null : Number(v.outcome_score), outcome_note: v.outcome_note,
        level_override: v.level_override, override_note: v.override_note, assessor_notes: v.assessor_notes,
      });
      return changed('Assessor input saved.');
    }
    if (f.kind === 'evidence') {
      if (!files.file && !v.source_url && !v.sprint_document) throw new Error('Attach a file, give a link or choose an audit document.');
      await uploadCycleEvidence(cycleId, code, {
        rule_key: f.ruleKey, title: v.title, description: v.description, source_url: v.source_url, issued_on: v.issued_on,
        valid_until: v.valid_until, file: files.file, sprint_document: v.sprint_document,
      });
      return changed('Evidence submitted.');
    }
    if (f.kind !== 'review') return;
    await reviewCycleEvidence(f.item.id, {
      decision: v.decision as 'accepted', relevance_score: +v.relevance, completeness_score: +v.completeness, currency_score: +v.currency,
      authenticity_score: +v.authenticity, scope_score: +v.scope, notes: v.notes,
    });
    return changed('Review recorded.');
  };

  return (
    <dialog ref={dialog} className="action-dialog fact-dialog" onCancel={(e) => { e.preventDefault(); onClose(); }} aria-labelledby="cb-title">
      <div className="fact-dialog-body">
        <div className="fact-dialog-head">
          <div><span className="eyebrow">{code}</span><h2 id="cb-title">{d?.title || 'Loading…'}</h2></div>
          <button className="notice-close" aria-label="Close" onClick={onClose}>×</button>
        </div>
        {msg && <Notice tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Notice>}
        {detail.loading && !d ? <Loading /> : detail.error ? <ErrorState error={detail.error} /> : d && (
          <>
            <section className="fact-section">
              <div className="fact-meta">
                <span>{humanize(d.kind)}</span><span>Target {d.target_level}</span><span>{d.included === false ? 'Excluded' : humanize(d.applicability_result)}</span>
                {d.assessment && <span>Current {d.assessment.current_level} · {d.assessment.composite_score ?? '—'}</span>}
              </div>
              <p className="muted">{d.applicability_reason}</p>
            </section>
            <section className="fact-section">
              <h3>Source requirements</h3>
              <ul className="plain-list">{d.requirements.map((r) => <li key={r.code}><b>{r.code}</b> {r.statement} <span className="muted">({r.source_code}{r.page != null && `, p. ${r.page}`})</span></li>)}</ul>
            </section>
            <section className="fact-section">
              <h3>Evidence requests</h3>
              {d.requests.map((r) => (
                <article key={r.key} className="condition">
                  <div><b>{r.title}</b> · {r.level} · {r.evidence_type_name}{r.mandatory && ' · mandatory'} · min {r.minimum_count}</div>
                  <p className="muted">{r.validation_method}</p>
                  {r.items.map((it) => (
                    <div key={it.id} className="row-actions">
                      <Pill status={it.status} label={it.status_label} /> {it.title} <span className="muted">· {it.submitted_by} · {dateTime(it.created_at)}{it.from_audit && ' · from audit'}</span>
                      {it.has_file && <button className="link-button" onClick={() => void downloadCycleEvidence(it.id, it.original_filename).catch((e) => setMsg({ tone: 'error', text: errorMessage(e) }))}>Download</button>}
                      {it.source_url && <a className="link-button" href={it.source_url} target="_blank" rel="noreferrer">Link</a>}
                      {staff && it.status === 'submitted' && <button className="secondary-button" onClick={() => setForm({ kind: 'review', item: it })}>Review</button>}
                    </div>
                  ))}
                  {canUpload && d.cycle_status !== 'finalized' && <button className="secondary-button" onClick={() => setForm({ kind: 'evidence', ruleKey: r.key, title: r.title })}>Submit evidence</button>}
                </article>
              ))}
            </section>
          </>
        )}
      </div>
      <div className="button-row dialog-actions fact-dialog-foot">
        {d && staff && (
          <div className="row-actions">
            <button className="secondary-button" onClick={() => setForm({ kind: 'scope' })}>Scope & target</button>
            <button className="secondary-button" onClick={() => setForm({ kind: 'assessor' })}>Assessor input</button>
          </div>
        )}
        <button className="secondary-button" onClick={onClose}>Close</button>
      </div>
      {form && (
        <ActionDialog title={form.kind === 'scope' ? 'Scope and target' : form.kind === 'assessor' ? 'Assessor input' : form.kind === 'evidence' ? 'Submit evidence' : form.kind === 'review' ? `Review: ${form.item.title}` : ''}
          confirmLabel="Save" fields={formFields(form)} onSubmit={(v, files) => submit(form, v, files)} onClose={() => setForm(null)} />
      )}
    </dialog>
  );
}
