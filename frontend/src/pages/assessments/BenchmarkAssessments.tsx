import React, { useEffect, useState } from 'react';
import { CheckCircle2, ClipboardList, Lock, Play, Plus, Send, Undo2 } from 'lucide-react';

import { PageHeader } from '../../components/PageHeader';
import { ErrorState, InlineError, LoadingState } from '../../components/ApiStates';
import { useApiResource } from '../../hooks/useApiResource';
import { getErrorMessage } from '../../utils/errors';
import {
  createCycle, cycleAction, getAssessmentReference, getCollegeProfile, getCycle, getScorecard, listColleges, listCycles,
  saveCollegeProfile,
} from '../../api/assessments';
import type {
  AssessmentReference, CollegeProfile, CollegeRow, Cycle, CycleDetail, CycleStatus, ProgrammeRow, Scorecard,
} from '../../api/assessments';
import { CycleBenchmarkPanel } from './CycleBenchmarkPanel';
import { PlanPanel } from './PlanPanel';

/**
 * Stage 5: assess a college against the current published benchmark release.
 * InGage staff set the college profile, start an assessment and review evidence;
 * college members upload evidence; the scorecard is shared once finalized.
 */

export const STATUS_BADGE: Record<CycleStatus, string> = {
  not_started: 'badge-neutral', in_progress: 'badge-brand', submitted: 'badge-warning', reviewed: 'badge-brand',
  finalized: 'badge-success',
};
const STEPS: CycleStatus[] = ['not_started', 'in_progress', 'submitted', 'reviewed', 'finalized'];
const STEP_LABEL: Record<CycleStatus, string> = {
  not_started: 'Choose benchmarks', in_progress: 'College uploads evidence', submitted: 'InGage reviews',
  reviewed: 'Scored', finalized: 'Finalized',
};
export const fmt = (v: string | null | undefined) => (v === null || v === undefined ? '—' : String(Math.round(Number(v) * 10) / 10));

export const BenchmarkAssessments: React.FC = () => {
  const ref = useApiResource<AssessmentReference>(() => getAssessmentReference(), []);
  const colleges = useApiResource<CollegeRow[]>(() => listColleges(), []);
  const [college, setCollege] = useState('');

  useEffect(() => {
    if (!college && colleges.data && colleges.data.length > 0) setCollege(colleges.data[0].id);
  }, [colleges.data, college]);

  if (ref.loading || colleges.loading) return <LoadingState message="Loading assessments…" />;
  if (ref.error || !ref.data) return <ErrorState message={ref.error || 'Could not load'} onRetry={ref.refetch} />;
  const r = ref.data;

  return (
    <div className="space-y-5">
      <PageHeader icon={ClipboardList} title="Benchmark Assessment"
        description="A college's evidence, checked against the published benchmark release, with four separate scores." />
      <div className="glass-card p-3 text-xs text-ink-600 space-y-1">
        <p>
          Current release: <strong>{r.current_release || 'none published yet'}</strong>
          {r.scoring_model ? <> · scoring model <strong>{r.scoring_model.code}</strong></> : null}
        </p>
        {!r.current_release && r.is_staff && (
          <p className="text-warning">A release must be published in Benchmark Studio before any college can be assessed.</p>
        )}
      </div>
      {colleges.error && <ErrorState message={colleges.error} onRetry={colleges.refetch} />}
      {colleges.data && colleges.data.length === 0 && <p className="text-sm text-ink-500">No college is linked to your account.</p>}
      {colleges.data && colleges.data.length > 1 && (
        <select className="input text-sm w-full md:w-96" value={college} onChange={(e) => setCollege(e.target.value)}>
          {colleges.data.map((c) => <option key={c.id} value={c.id}>{c.name}{c.city ? ` (${c.city})` : ''}{c.has_profile ? '' : ' — no profile yet'}</option>)}
        </select>
      )}
      {college && <CollegeWorkspace key={college} collegeId={college} reference={r} onProfileSaved={colleges.refetch} />}
    </div>
  );
};

const CollegeWorkspace: React.FC<{ collegeId: string; reference: AssessmentReference; onProfileSaved: () => void }> = (
  { collegeId, reference, onProfileSaved },
) => {
  const profile = useApiResource<CollegeProfile>(() => getCollegeProfile(collegeId), [collegeId]);
  const cycles = useApiResource<Cycle[]>(() => listCycles(collegeId), [collegeId]);
  const [open, setOpen] = useState<string | null>(null);
  const [name, setName] = useState('');
  const [opensOn, setOpensOn] = useState(new Date().toISOString().slice(0, 10));
  const [err, setErr] = useState('');

  useEffect(() => {
    if (!open && cycles.data && cycles.data.length > 0) setOpen(cycles.data[0].id);
  }, [cycles.data, open]);

  const start = async () => {
    setErr('');
    try {
      const c = (await createCycle({ institution: collegeId, name, opens_on: opensOn })).data;
      setName(''); cycles.refetch(); setOpen(c.id);
    } catch (e) { setErr(getErrorMessage(e)); }
  };

  return (
    <div className="space-y-4">
      {profile.loading && <LoadingState message="Loading profile…" />}
      {profile.error && <ErrorState message={profile.error} onRetry={profile.refetch} />}
      {profile.data && (
        <ProfileCard data={profile.data} reference={reference}
          onSaved={() => { profile.refetch(); onProfileSaved(); }} />
      )}

      <div className="space-y-2">
        <p className="text-sm font-bold text-ink-900">Assessments</p>
        {(cycles.data || []).map((c) => (
          <button key={c.id} onClick={() => setOpen(c.id)}
            className={`glass-card w-full p-3 text-left text-xs flex items-center gap-2 flex-wrap ${open === c.id ? 'ring-2 ring-brand-500' : ''}`}>
            <span className="text-sm font-bold text-ink-900">{c.name}</span>
            <span className={`badge ${STATUS_BADGE[c.status]}`}>{c.status_label}</span>
            <span className="text-ink-500">{c.release_label} · from {c.opens_on}</span>
          </button>
        ))}
        {cycles.data && cycles.data.length === 0 && <p className="text-sm text-ink-500">No assessments yet.</p>}
      </div>

      {reference.is_staff && reference.current_release && profile.data?.profile && (
        <div className="glass-card p-4 space-y-2 text-xs">
          <p className="text-sm font-bold text-ink-900">Start a new assessment</p>
          <div className="grid md:grid-cols-[2fr_1fr_auto] gap-2">
            <input className="input text-xs" placeholder="Name, e.g. AI readiness 2026-27" value={name} onChange={(e) => setName(e.target.value)} />
            <input className="input text-xs" type="date" value={opensOn} onChange={(e) => setOpensOn(e.target.value)} title="Opens on (evidence age is checked against this date)" />
            <button className="btn-primary btn-sm" disabled={!name.trim()} onClick={start}><Plus className="w-3.5 h-3.5" /> Start</button>
          </div>
          <p className="text-ink-500">Uses {reference.current_release}. The college's profile decides which benchmarks apply; every decision shows its reason.</p>
        </div>
      )}
      {err && <InlineError message={err} onDismiss={() => setErr('')} />}
      {open && <CyclePanel key={open} cycleId={open} reference={reference} onChanged={cycles.refetch} />}
    </div>
  );
};

const ProfileCard: React.FC<{ data: CollegeProfile; reference: AssessmentReference; onSaved: () => void }> = ({ data, reference, onSaved }) => {
  const p = data.profile;
  const [editing, setEditing] = useState(false);
  const [itype, setItype] = useState(p?.institution_type || '');
  const [status, setStatus] = useState(p?.autonomous_status || '');
  const [bodies, setBodies] = useState<string[]>(p?.approval_bodies || []);
  const [progs, setProgs] = useState<ProgrammeRow[]>(data.programmes.map((x) => ({ name: x.name, programme_type: x.programme_type, approval_body: x.approval_body })));
  const [err, setErr] = useState('');
  const typeName = (code: string) => reference.programme_types.find((t) => t.code === code)?.name || code;

  const save = async () => {
    setErr('');
    try {
      await saveCollegeProfile(data.institution, { institution_type: itype, autonomous_status: status, approval_bodies: bodies, programmes: progs });
      setEditing(false); onSaved();
    } catch (e) { setErr(getErrorMessage(e)); }
  };

  if (!editing) {
    return (
      <div className="glass-card p-4 text-xs space-y-1">
        <div className="flex items-center gap-2">
          <p className="text-sm font-bold text-ink-900 flex-1">{data.institution_name} — profile</p>
          {reference.is_staff && <button className="btn-secondary btn-sm" onClick={() => setEditing(true)}>{p ? 'Edit' : 'Set up profile'}</button>}
        </div>
        {p ? (
          <>
            <p>{p.institution_type_name}{p.autonomous_status ? ` · ${reference.autonomous_statuses.find((s) => s.code === p.autonomous_status)?.name || p.autonomous_status}` : ''}
              {p.approval_bodies.length ? ` · approvals: ${p.approval_bodies.join(', ')}` : ''}</p>
            <p className="text-ink-500">Programmes: {data.programmes.length ? data.programmes.map((x) => `${x.name} (${x.programme_type_name}${x.approval_body ? `, ${x.approval_body}` : ''})`).join('; ') : 'none'}</p>
          </>
        ) : <p className="text-ink-500">Not set up yet. The profile decides which benchmarks apply to this college.</p>}
      </div>
    );
  }
  return (
    <div className="glass-card p-4 text-xs space-y-2">
      <p className="text-sm font-bold text-ink-900">{data.institution_name} — profile</p>
      <div className="grid md:grid-cols-2 gap-2">
        <select className="input text-xs" value={itype} onChange={(e) => setItype(e.target.value)}>
          <option value="">Institution type…</option>
          {reference.institution_types.map((t) => <option key={t.code} value={t.code}>{t.name}</option>)}
        </select>
        <select className="input text-xs" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">Status (optional)…</option>
          {reference.autonomous_statuses.map((t) => <option key={t.code} value={t.code}>{t.name}</option>)}
        </select>
      </div>
      <div className="flex flex-wrap gap-2">
        {reference.approval_bodies.map((b) => (
          <label key={b} className="flex items-center gap-1">
            <input type="checkbox" checked={bodies.includes(b)} onChange={(e) => setBodies(e.target.checked ? [...bodies, b] : bodies.filter((x) => x !== b))} /> {b}
          </label>
        ))}
      </div>
      <p className="font-bold text-ink-900">Programmes</p>
      {progs.map((x, i) => (
        <div key={i} className="grid md:grid-cols-[2fr_2fr_1fr_auto] gap-2">
          <input className="input text-xs" value={x.name} placeholder="Name, e.g. B.E. CSE" onChange={(e) => setProgs(progs.map((y, j) => j === i ? { ...y, name: e.target.value } : y))} />
          <select className="input text-xs" value={x.programme_type} onChange={(e) => setProgs(progs.map((y, j) => j === i ? { ...y, programme_type: e.target.value } : y))}>
            <option value="">Programme type…</option>
            {reference.programme_types.map((t) => <option key={t.code} value={t.code}>{typeName(t.code)}</option>)}
          </select>
          <select className="input text-xs" value={x.approval_body} onChange={(e) => setProgs(progs.map((y, j) => j === i ? { ...y, approval_body: e.target.value } : y))}>
            <option value="">Approval…</option>
            {reference.approval_bodies.map((b) => <option key={b} value={b}>{b}</option>)}
          </select>
          <button className="btn-secondary btn-sm" onClick={() => setProgs(progs.filter((_, j) => j !== i))}>Remove</button>
        </div>
      ))}
      <button className="btn-secondary btn-sm" onClick={() => setProgs([...progs, { name: '', programme_type: '', approval_body: '' }])}><Plus className="w-3.5 h-3.5" /> Add programme</button>
      <div className="flex gap-2">
        <button className="btn-primary btn-sm" disabled={!itype} onClick={save}>Save profile</button>
        <button className="btn-secondary btn-sm" onClick={() => setEditing(false)}>Cancel</button>
      </div>
      <p className="text-ink-500">Changing the profile does not change assessments already started; each keeps the profile it was started with.</p>
      {err && <InlineError message={err} onDismiss={() => setErr('')} />}
    </div>
  );
};

const CyclePanel: React.FC<{ cycleId: string; reference: AssessmentReference; onChanged: () => void }> = ({ cycleId, reference, onChanged }) => {
  const cycle = useApiResource<CycleDetail>(() => getCycle(cycleId), [cycleId]);
  const [bench, setBench] = useState<string | null>(null);
  const [showCard, setShowCard] = useState(false);
  const [busy, setBusy] = useState('');
  const [err, setErr] = useState('');
  const [problems, setProblems] = useState<string[]>([]);

  const act = async (action: 'open' | 'submit' | 'return' | 'score' | 'finalize', note = '') => {
    setBusy(action); setErr(''); setProblems([]);
    try { await cycleAction(cycleId, action, note); cycle.refetch(); onChanged(); }
    catch (e: any) { setErr(getErrorMessage(e)); setProblems(e?.response?.data?.problems || []); }
    finally { setBusy(''); }
  };

  if (cycle.loading) return <LoadingState message="Loading assessment…" />;
  if (cycle.error || !cycle.data) return <ErrorState message={cycle.error || 'Not found'} onRetry={cycle.refetch} />;
  const c = cycle.data;
  const staff = reference.is_staff;
  const included = c.benchmarks.filter((b) => b.included);
  const others = c.benchmarks.filter((b) => !b.included);
  const stepIndex = STEPS.indexOf(c.status);

  return (
    <div className="glass-card p-4 space-y-3 text-xs">
      <div className="flex items-center gap-2 flex-wrap">
        <p className="text-sm font-bold text-ink-900">{c.name}</p>
        <span className={`badge ${STATUS_BADGE[c.status]}`}>{c.status_label}</span>
        <span className="text-ink-500" title={c.release_hash}>{c.release_label} · started by {c.created_by}</span>
      </div>
      <div className="flex flex-wrap gap-1">
        {STEPS.map((s, i) => (
          <span key={s} className={`px-2 py-0.5 rounded-full border ${i <= stepIndex ? 'border-brand-500 text-brand-700 bg-brand-500/10' : 'border-line-200 text-ink-400'}`}>
            {i + 1}. {STEP_LABEL[s]}
          </span>
        ))}
      </div>

      <div className="flex flex-wrap gap-2">
        {staff && c.status === 'not_started' && (
          <button className="btn-primary btn-sm" disabled={!!busy} onClick={() => act('open')}><Play className="w-3.5 h-3.5" /> Ask the college for evidence</button>
        )}
        {reference.can_upload && c.status === 'in_progress' && (
          <button className="btn-primary btn-sm" disabled={!!busy} onClick={() => {
            if (window.confirm('Submit the evidence to InGage for review? You can no longer upload unless InGage sends it back.')) act('submit');
          }}><Send className="w-3.5 h-3.5" /> Submit evidence for review</button>
        )}
        {staff && (c.status === 'submitted' || c.status === 'reviewed') && (
          <>
            <button className="btn-primary btn-sm" disabled={!!busy} onClick={() => act('score')}><CheckCircle2 className="w-3.5 h-3.5" /> Calculate scores</button>
            <button className="btn-secondary btn-sm" disabled={!!busy} onClick={() => {
              const note = window.prompt('What should the college add or fix?', '');
              if (note) act('return', note);
            }}><Undo2 className="w-3.5 h-3.5" /> Send back to college</button>
          </>
        )}
        {staff && c.status === 'reviewed' && (
          <button className="btn-primary btn-sm" disabled={!!busy} onClick={() => {
            if (window.confirm('Finalize? Scores, weights and evidence decisions are frozen and the college can see the scorecard.')) act('finalize');
          }}><Lock className="w-3.5 h-3.5" /> Finalize</button>
        )}
        {c.scores_visible && (c.status === 'reviewed' || c.status === 'finalized') && (
          <button className="btn-secondary btn-sm" onClick={() => setShowCard(!showCard)}>{showCard ? 'Hide scorecard' : 'Show scorecard'}</button>
        )}
      </div>
      {!staff && c.status !== 'finalized' && <p className="text-ink-500">The scorecard is shared with the college once InGage finalizes the assessment.</p>}
      {err && <InlineError message={err} onDismiss={() => setErr('')} />}
      {problems.length > 0 && <div>{problems.map((p) => <p key={p} className="text-danger">• {p}</p>)}</div>}
      {showCard && <ScorecardView cycleId={cycleId} />}
      {c.status === 'finalized' && <PlanPanel cycleId={cycleId} staff={staff} canEdit={reference.can_upload} />}

      <p className="font-bold text-ink-900 pt-1">Benchmarks in this assessment ({included.length})</p>
      <BenchTable rows={included} active={bench} onPick={setBench} showScores={c.scores_visible} />
      {others.length > 0 && (
        <details className="text-ink-600">
          <summary className="cursor-pointer">Not included ({others.length}) — with the reason</summary>
          <div className="pt-2"><BenchTable rows={others} active={bench} onPick={setBench} showScores={false} /></div>
        </details>
      )}
      {bench && (
        <CycleBenchmarkPanel key={`${cycleId}-${bench}`} cycleId={cycleId} code={bench} reference={reference}
          onChanged={() => { cycle.refetch(); onChanged(); }} />
      )}
    </div>
  );
};

const BenchTable: React.FC<{ rows: CycleDetail['benchmarks']; active: string | null; onPick: (c: string) => void; showScores: boolean }> = (
  { rows, active, onPick, showScores },
) => (
  <div className="space-y-1">
    {rows.map((b) => (
      <button key={b.benchmark_code} onClick={() => onPick(b.benchmark_code)}
        className={`w-full text-left rounded-lg border bg-surface p-2 flex items-center gap-2 flex-wrap ${active === b.benchmark_code ? 'border-brand-500' : 'border-line-200'}`}>
        <span className="font-mono text-ink-500">{b.benchmark_code}</span>
        <span className="text-ink-900 flex-1 min-w-0 truncate">{b.title}</span>
        {b.included === null && <span className="badge badge-warning">decide</span>}
        {b.included === false && <span className="text-ink-500 truncate max-w-[24rem]" title={b.applicability_reason}>{b.applicability_reason}</span>}
        {b.included && <span className="text-ink-500">{b.accepted}/{b.evidence} accepted{b.waiting ? ` · ${b.waiting} waiting` : ''}</span>}
        {showScores && b.assessment && (
          <span className="badge badge-brand">{b.assessment.current_level || 'no level'}{b.assessment.composite_score ? ` · ${fmt(b.assessment.composite_score)}` : ''}</span>
        )}
      </button>
    ))}
  </div>
);

const ScorecardView: React.FC<{ cycleId: string }> = ({ cycleId }) => {
  const card = useApiResource<Scorecard>(() => getScorecard(cycleId), [cycleId]);
  if (card.loading) return <LoadingState message="Loading scorecard…" />;
  if (card.error || !card.data) return <ErrorState message={card.error || 'Not found'} onRetry={card.refetch} />;
  const s = card.data;
  return (
    <div className="rounded-lg border border-line-200 bg-surface p-3 space-y-2">
      <p className="font-bold text-ink-900">Scorecard — {s.name}</p>
      <p className="text-ink-500">
        Assessed against {s.release_label} (#{s.release_hash.slice(0, 10)}){s.scoring_model ? ` · ${s.scoring_model.code} v${s.scoring_model.formula_version}` : ''} · method {s.method}
        {s.finalized_at ? ` · finalized ${new Date(s.finalized_at).toLocaleDateString()} by ${s.finalized_by}` : ' · not final yet'}
      </p>
      {s.scoring_model && <p className="text-ink-500">{s.scoring_model.description}</p>}
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-left text-ink-500">
              <th className="py-1 pr-2">Benchmark</th><th className="pr-2">Level (target)</th><th className="pr-2">Compliance</th>
              <th className="pr-2">Maturity</th><th className="pr-2">Evidence confidence</th><th className="pr-2">Outcome</th><th>Composite</th>
            </tr>
          </thead>
          <tbody>
            {s.benchmarks.map((b) => {
              const a = b.assessment;
              return (
                <tr key={b.benchmark_code} className="border-t border-line-200 align-top">
                  <td className="py-1 pr-2"><span className="font-mono">{b.benchmark_code}</span> {b.title}</td>
                  <td className="pr-2">{a?.current_level || '—'} ({b.target_level})</td>
                  <td className="pr-2" title={a?.detail.compliance}>{fmt(a?.compliance_score)}</td>
                  <td className="pr-2" title={a?.detail.maturity}>{fmt(a?.maturity_score)}</td>
                  <td className="pr-2" title={a?.detail.evidence_confidence}>{fmt(a?.evidence_confidence_score)}</td>
                  <td className="pr-2" title={a?.detail.outcome}>{fmt(a?.outcome_score)}</td>
                  <td title={a?.detail.composite}>{fmt(a?.composite_score)}{a && !a.composite_score && <span className="block text-ink-400">{a.detail.composite}</span>}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="text-ink-400">Hover a score to see why. "—" means not calculated, never zero.</p>
    </div>
  );
};
