import React from 'react';
import { X } from 'lucide-react';

import { getFactVerification } from '../../api/facts';
import { ErrorState, LoadingState } from '../../components/ApiStates';
import { useApiResource } from '../../hooks/useApiResource';
import type { Fact, FactVerificationRun, VerificationCheck } from '../../types';

/**
 * Fact verification (backend apps/facts/verification/), shown as four separate results -- never blended:
 * extraction confidence (the model's own estimate), source grounding, validation (both deterministic) and
 * cross-source agreement. Deterministic results say Pass / Fail with the rule; nothing here is a probability
 * except the labelled extraction confidence.
 */

export const VERIFICATION_LABEL: Record<string, string> = {
  verified: 'Verified', needs_review: 'Needs review', invalid: 'Invalid', conflicting: 'Conflicting',
};
export const verificationBadgeClass = (status?: string) => ({
  verified: 'badge-success', needs_review: 'badge-warning', invalid: 'badge-danger', conflicting: 'badge-danger',
}[status || ''] || 'badge-neutral');

const GROUNDING_LABEL: Record<string, string> = {
  exact: 'Quote found on the page', ocr_variant: 'Quote found (OCR differences; numbers exact)',
  not_found: 'Quote not on the cited page', unavailable: 'Page text not stored', no_quote: 'No quote',
  no_page: 'No page cited', page_missing: 'Page outside the document', document_missing: 'No document cited',
  wrong_sprint: 'Document of another sprint', value_conflicts_quote: 'Value contradicts its own quote',
  value_not_in_quote: 'Quote does not state the value',
};
const CROSS_LABEL: Record<string, string> = {
  agrees: 'Other sources agree', disagrees: 'Another source disagrees', in_open_conflict: 'In an open conflict',
  not_comparable: 'Other sources measure something else', no_other_source: 'No other source',
};
export const AUTOMATION_LABEL: Record<string, string> = {
  auto_verified: 'Confirmed by the rules', precedent: 'Confirmed: matches an earlier reviewer decision',
  would_auto_verify: 'Would be confirmed by the rules (shadow mode)',
  would_precedent: 'Would be confirmed by precedent (shadow mode)', review: 'Needs a person',
  not_applicable: 'Already reviewed',
};

/** The compact cell in the facts table; opens the full breakdown. */
export const VerificationCell: React.FC<{ fact: Fact; onOpen: () => void }> = ({ fact, onOpen }) => {
  const v = fact.verification;
  if (!v) return <span className="text-xs text-ink-400">Not verified yet</span>;
  return (
    <button type="button" onClick={onOpen} className="text-left" title={v.automation_reason || 'Why?'}>
      <span className={verificationBadgeClass(v.status)}>{v.status_label}</span>
      <span className="block text-[11px] text-ink-500 mt-0.5 whitespace-normal max-w-[13rem]">
        {GROUNDING_LABEL[v.grounding] || v.grounding} · checks {v.validation}
        {v.cross_source && v.cross_source !== 'no_other_source' ? ` · ${CROSS_LABEL[v.cross_source] || v.cross_source}` : ''}
      </span>
      <span className="block text-[11px] font-semibold text-accent mt-0.5">Why?</span>
    </button>
  );
};

const statusClass = (s: string) => (s === 'pass' ? 'text-success' : s === 'warn' ? 'text-warning' : 'text-danger');

const Section: React.FC<{ title: string; kind: string; children: React.ReactNode }> = ({ title, kind, children }) => (
  <section className="space-y-1.5">
    <div className="flex items-baseline justify-between gap-2">
      <h3 className="text-sm font-bold text-ink-900">{title}</h3>
      <span className="text-[10px] uppercase tracking-wide text-ink-400">{kind}</span>
    </div>
    {children}
  </section>
);

const Check: React.FC<{ check: VerificationCheck }> = ({ check }) => (
  <li className="text-xs">
    <span className={`font-bold uppercase ${statusClass(check.status)}`}>{check.status}</span>{' '}
    <span className="font-semibold text-ink-800">{check.label}</span>
    <span className="text-ink-600"> — {check.detail}</span>
  </li>
);

const Breakdown: React.FC<{ run: FactVerificationRun; precedent: FactVerificationRun['precedent'] }> = ({ run, precedent }) => {
  const calc = run.derivation;
  const p = precedent || run.precedent;
  return (
    <div className="space-y-4">
      <div className="panel-muted">
        <span className={verificationBadgeClass(run.outcome)}>{VERIFICATION_LABEL[run.outcome]}</span>
        <p className="text-sm text-ink-800 mt-1">{run.reason}</p>
        <p className="text-xs text-ink-500 mt-1">
          {AUTOMATION_LABEL[run.automation_decision] || run.automation_decision}
          {run.automation_reason && run.automation_reason !== run.reason ? ` — ${run.automation_reason}` : ''}
          {' · '}risk {run.risk_level || '—'} · {run.mode === 'enforce' ? 'rules active' : 'shadow mode (rules record only)'}
        </p>
        {run.blockers.length > 1 && (
          <ul className="list-disc ml-4 mt-1 text-xs text-ink-600">{run.blockers.map((b) => <li key={b}>{b}</li>)}</ul>
        )}
      </div>

      <Section title="Extraction confidence" kind="model estimate">
        <p className="text-xs text-ink-600">
          {run.extraction_confidence == null ? 'Not given.' : `${Math.round(run.extraction_confidence * 100)}%`} — how sure
          the model was that it read the value correctly. It never confirms a fact on its own.
        </p>
      </Section>

      <Section title="Source grounding" kind="deterministic">
        <p className="text-xs text-ink-700">
          {run.citation.document_name || 'No document'}{run.citation.document_version ? ` v${run.citation.document_version}` : ''}
          {run.citation.source_page ? `, page ${run.citation.source_page}` : ''}:{' '}
          <span className="font-semibold">{GROUNDING_LABEL[run.grounding.status] || run.grounding.status}</span>
          {run.grounding.score != null && run.grounding.quote !== 'exact' ? ` (${Math.round(run.grounding.score * 100)}% of the text matched)` : ''}
        </p>
        {run.citation.source_snippet && <blockquote className="text-xs italic text-ink-500 border-l-2 border-line-200 pl-2">“{run.citation.source_snippet}”</blockquote>}
        {run.grounding.detail.map((d) => <p key={d} className="text-xs text-ink-600">{d}</p>)}
      </Section>

      <Section title="Validation" kind="deterministic">
        <ul className="space-y-0.5">{run.validation.checks.map((c) => <Check key={c.code + c.label} check={c} />)}</ul>
      </Section>

      {calc && calc.inputs && (
        <Section title="Calculated value" kind="deterministic">
          <p className="text-xs text-ink-700">
            <span className="font-mono">{calc.formula}</span> = <span className="font-mono">{calc.computed ?? '—'}</span>
            {' '}(fact says <span className="font-mono">{calc.stated ?? '—'}</span>):{' '}
            <span className={`font-bold ${calc.status === 'pass' ? 'text-success' : 'text-danger'}`}>{calc.status === 'pass' ? 'PASS' : 'FAIL'}</span>
          </p>
          <ul className="space-y-1">
            {calc.inputs.map((i, n) => (
              <li key={n} className="text-xs text-ink-600">
                <span className="font-semibold text-ink-800">{i.label || `Input ${n + 1}`}: {i.value}</span>
                {' '}— {i.document_name || 'document'}{i.document_version ? ` v${i.document_version}` : ''}, page {i.source_page || '?'}:{' '}
                {GROUNDING_LABEL[i.grounding.status] || i.grounding.status}
              </li>
            ))}
          </ul>
          {(calc.includes?.length || calc.excludes?.length) ? (
            <p className="text-xs text-ink-500">
              {calc.includes?.length ? `Includes: ${calc.includes.join(', ')}. ` : ''}
              {calc.excludes?.length ? `Excludes: ${calc.excludes.join(', ')}.` : ''}
            </p>
          ) : null}
          {calc.detail?.map((d) => <p key={d} className="text-xs text-danger">{d}</p>)}
        </Section>
      )}

      <Section title="Other sources" kind="deterministic">
        <p className="text-xs text-ink-700">{CROSS_LABEL[run.cross_source.status] || run.cross_source.status}
          {run.scope.period ? ` · this fact's period: ${run.scope.period}` : ''}
          {run.scope.population?.length ? ` · population: ${run.scope.population.join(', ')}` : ''}</p>
        <ul className="space-y-0.5">
          {run.cross_source.compared.map((c) => (
            <li key={c.fact_id} className={`text-xs ${c.agrees ? 'text-ink-600' : 'text-danger'}`}>
              {c.agrees ? 'Agrees' : 'Disagrees'}: {String(c.value)} — {c.document || 'document'}
              {c.document_version ? ` v${c.document_version}` : ''}{c.page ? `, page ${c.page}` : ''}{c.period ? ` (${c.period})` : ''}
            </li>
          ))}
          {run.cross_source.not_comparable.map((c) => (
            <li key={c.fact_id} className="text-xs text-ink-500">Not compared: {String(c.value)} — {c.document || 'document'} ({c.why})</li>
          ))}
        </ul>
      </Section>

      {p && (
        <Section title="Earlier reviewer decision" kind={p.match === 'exact' ? 'precedent (exact)' : 'suggestion only'}>
          <p className="text-xs text-ink-700">
            {p.decided_by_name} {p.action} {JSON.stringify(p.value)}
            {p.document_version ? ` on v${p.document_version}` : ''}{p.source_page ? `, page ${p.source_page}` : ''}.
            {p.match === 'rejected' ? ' A person rejected a matching value before: review carefully.' : ''}
          </p>
          {p.differences.length > 0 && <p className="text-xs text-ink-500">Differs: {p.differences.join('; ')}.</p>}
        </Section>
      )}

      {run.ai_assessments.length > 0 && (
        <Section title="AI-assisted notes" kind="AI judgement — not a decision">
          {run.ai_assessments.map((a, n) => <p key={n} className="text-xs text-ink-600">{a.label}: {a.detail}</p>)}
        </Section>
      )}
    </div>
  );
};

export const FactVerificationModal: React.FC<{ fact: Fact; onClose: () => void }> = ({ fact, onClose }) => {
  const { data, loading, error, refetch } = useApiResource(() => getFactVerification(fact.id), [fact.id]);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink-900/40 p-4" role="dialog" aria-modal="true">
      <div className="glass-card w-full max-w-2xl p-5 space-y-4 max-h-[90vh] overflow-y-auto">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-base font-bold text-ink-900">Why: {fact.field_name || fact.field_key}</h2>
            <p className="text-xs text-ink-500 mt-0.5">
              Value <span className="font-mono">{JSON.stringify(fact.value)}</span>
              {fact.original_value !== undefined && fact.original_value !== null
                && JSON.stringify(fact.original_value) !== JSON.stringify(fact.value)
                ? <> · first extracted as <span className="font-mono">{JSON.stringify(fact.original_value)}</span></> : null}
              {fact.value_origin === 'calculated' ? ' · calculated value' : ''}
            </p>
          </div>
          <button className="btn-icon" onClick={onClose} aria-label="Close"><X className="w-4 h-4" /></button>
        </div>
        {loading && !data ? <LoadingState message="Loading verification..." />
          : error ? <ErrorState message={error} onRetry={refetch} />
            : data?.latest ? <Breakdown run={data.latest} precedent={data.precedent} />
              : <p className="text-sm text-ink-500">This fact has not been verified yet.</p>}
      </div>
    </div>
  );
};
