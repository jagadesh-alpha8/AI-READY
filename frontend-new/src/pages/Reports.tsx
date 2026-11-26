import { useState } from 'react';
import { RequireSprint } from '../components/RequireSprint';
import { Dummy, Empty, ErrorState, Loading, Notice, PageHeading, Pill, Table } from '../components/ui';
import { useAccess } from '../hooks/useAccess';
import { useCapability } from '../hooks/useCapability';
import { usePolling, useResource } from '../hooks/useResource';
import { downloadCapabilityReport, getReportReadiness, openCapabilityReport } from '../services/capability';
import { Icon } from '../workspace/Icon';
import { http, saveBlob } from '../services/http';
import { downloadReport, generateReport, listReports } from '../services/reports';
import { listSprintFactsPage } from '../services/facts';
import { listSprintGapsPage } from '../services/gaps';
import type { Fact, Gap, Report, Sprint } from '../types/api';
import type { ReportReadiness } from '../types/capability';
import { DEMO_MODE } from '../config/env';
import { STAGE_ONE } from '../utils/capability';
import { toCsv } from '../utils/csv';
import { errorMessage } from '../utils/errors';
import { dateTime, num, pct, tidyText, valueText } from '../utils/format';

/** The two reports for the institution (23 Nov): a short leadership report and the full detail. */
const REPORTS = [
  { audience: 'summary' as const, icon: 'file', title: 'Leadership report',
    text: 'Your level and stars, the nine areas at a glance, where you are strong, where to focus and what to do next.', meta: 'Six pages · for leadership and the board' },
  { audience: 'detailed' as const, icon: 'assessment', title: 'Detailed report',
    text: 'Every practice in all nine areas: what your documents show, the document and page it was found on, and the next step.', meta: 'Every practice · for the teams doing the work' },
];

/** Handoff outputs (6.17) and which ones the backend produces today. */
const OUTPUTS = [
  { title: 'Executive readiness report', text: 'Leadership view of standing, gaps and the action plan.', meta: 'PDF · DOCX', live: true },
  { title: 'Detailed audit report', text: 'Pillar scorecards, missing data appendix, recommendations, 90-day plan and 12-month roadmap.', meta: 'Same generated report', live: true },
  { title: 'Machine-readable export', text: 'The full report data, CRI source and evidence metrics as JSON.', meta: 'JSON', live: true },
  { title: 'Evidence register', text: 'Traceable catalogue of submitted, extracted, verified and missing evidence.', meta: 'CSV · from facts and gaps', live: true },
  { title: 'Transformation roadmap', text: 'Selected pace, stage goals, tasks, owners and timelines.', meta: 'Not yet a backend export', live: false },
  { title: 'Board presentation', text: 'Decision-ready story for governing council meetings.', meta: 'Not yet a backend export', live: false },
];

export function Reports() {
  return <RequireSprint>{(sprint) => <ReportsBody sprint={sprint} />}</RequireSprint>;
}

function ReportsBody({ sprint }: { sprint: Sprint }) {
  const { can, staff } = useAccess();
  const reports = useResource<Report[]>(() => listReports(sprint.id), sprint.id);
  const cap = useCapability(sprint.id);
  const capRunId = cap.run.data?.assessment ? cap.run.data.id : '';
  // The stage comes from the run list (a final run names its Stage 1 run), not from the JSON report, which carries
  // every model packet (73 MB for test 13) and was downloaded just to read two fields.
  const final = cap.stage === 'final';
  const [busy, setBusy] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [msg, setMsg] = useState<{ tone: 'success' | 'error' | 'info'; text: string } | null>(null);
  const generating = (reports.data || []).some((r) => r.status === 'draft' || r.status === 'generating');
  usePolling(() => void reports.refetch(), generating, 4000);

  const generate = async () => {
    setBusy(true);
    setMsg(null);
    try {
      await generateReport(sprint.id);
      setMsg({ tone: 'info', text: 'Report generation started. A fresh CRI is calculated first; this list updates when it is ready.' });
      await reports.refetch();
    } catch (e) { setMsg({ tone: 'error', text: errorMessage(e) }); } finally { setBusy(false); }
  };

  const download = async (fn: () => Promise<void>) => {
    try { await fn(); } catch (e) { setMsg({ tone: 'error', text: errorMessage(e) }); }
  };

  /**
   * Evidence register: every extracted, verified and requested fact of the sprint (GET /sprints/{id}/facts, all
   * pages) plus each missing document (GET /sprints/{id}/gaps?gap_type=missing_document), as one CSV.
   */
  const exportRegister = () => download(async () => {
    setExporting(true);
    try {
      const facts: Fact[] = [];
      for (let page = 1; ; page += 1) {
        const res = await listSprintFactsPage(sprint.id, { page, page_size: 100, ordering: 'field_key' });
        facts.push(...res.data.results);
        if (!res.data.next || res.data.results.length === 0) break;
      }
      const missing: Gap[] = [];
      for (let page = 1; ; page += 1) {
        const res = await listSprintGapsPage(sprint.id, { page, page_size: 100, gap_type: 'missing_document' });
        missing.push(...res.data.results);
        if (!res.data.next || res.data.results.length === 0) break;
      }
      const csv = toCsv(
        ['Evidence item', 'Value', 'Status', 'Verification', 'Pillar', 'AI-QIF indicators', 'Source document', 'Page', 'Source quote', 'Confidence', 'Reviewed at'],
        [
          ...facts.map((f) => [f.field_name, valueText(f.value), f.status, f.verification?.status_label || '', f.pillar_label,
            f.aiqif_mappings.map((m) => m.indicator_code).join(' '), f.source_document_filename || '', f.source_page, tidyText(f.source_snippet),
            pct(f.confidence_score), f.reviewed_at || '']),
          ...missing.map((g) => [g.title, '', g.status === 'open' ? 'missing' : `missing (${g.status})`, '', g.pillar_label, '', '', '', tidyText(g.description), '', '']),
        ],
      );
      saveBlob(new Blob([csv], { type: 'text/csv;charset=utf-8' }), `${sprint.sprint_code}-evidence-register.csv`);
      setMsg({ tone: 'success', text: `Evidence register downloaded: ${facts.length} evidence items and ${missing.length} missing documents.` });
    } finally {
      setExporting(false);
    }
  });

  const exportJson = (r: Report) => download(async () => {
    const res = await http.get(`/reports/${r.id}`);
    saveBlob(new Blob([JSON.stringify(res.data, null, 2)], { type: 'application/json' }), `${sprint.sprint_code}-report-v${r.version}.json`);
  });

  return (
    <>
      <PageHeading page="reports" actions={!DEMO_MODE && can('sprint.manage') && <button className="primary-action" disabled={busy || generating} onClick={() => void generate()}>{generating ? 'Generating…' : 'Generate report'}</button>} />
      {msg && <Notice tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Notice>}
      {!DEMO_MODE && <div className="feature-grid">
        {OUTPUTS.map((o, i) => (
          <article key={o.title} className={`feature-card ${o.live ? '' : 'muted-card'}`}>
            <div className="feature-icon">{String(i + 1).padStart(2, '0')}</div>
            <h3>{o.title}</h3>
            <p>{o.text}</p>
            <div className="feature-meta"><span>{o.meta}</span><b>{o.live ? 'Available' : 'Sample only'}</b></div>
          </article>
        ))}
      </div>}
      {capRunId && !final && (
        <Notice tone="info">These reports show your Stage 1 result, from your documents alone. Once the follow-up questions are answered and the result is published, the final reports appear here.</Notice>
      )}
      {!cap.run.data?.assessment ? (cap.run.loading ? <Loading /> : <Empty title="No reports yet">The reports are ready once the assessment of your documents completes.</Empty>) : (() => {
        const rows = [{ runId: cap.run.data!.id, final, when: dateTime(cap.run.data!.created_at), advice: cap.advice?.id },
          ...(final && cap.provisionalId
            ? [{ runId: cap.provisionalId, final: false, when: '', advice: undefined }] : [])];
        return (
          <>
            {rows.map((row) => (
              <section key={row.runId} className="ws-report-group">
                <h2 className="ws-report-group-title">{row.final ? 'Final result' : STAGE_ONE}{row.when && <small>{row.when}</small>}</h2>
                <ReportCards sprintId={sprint.id} runId={row.runId} staff={staff} download={download} />
                {staff && <details className="ws-technical">
                  <summary>Technical appendix (for InGage)</summary>
                  <p className="muted">Every requirement, model decision and source page, for review and audit.</p>
                  <div className="ws-row">
                    {(['leadership', 'evidence'] as const).flatMap((audience) => (['pdf', 'html', 'json'] as const).map((format) => (
                      <button key={`${audience}-${format}`} className="secondary-button" onClick={() => void download(() => downloadCapabilityReport(sprint.id, row.runId, format, audience, row.advice))}>
                        {audience === 'leadership' ? 'Basic' : 'Evidence'} · {format.toUpperCase()}
                      </button>
                    )))}
                  </div>
                </details>}
              </section>
            ))}
          </>
        );
      })()}
      {!DEMO_MODE && <>
      <h2 className="section-title">Audit report versions</h2>
      {reports.loading && !reports.data ? <Loading /> : reports.error ? <ErrorState error={reports.error} onRetry={() => void reports.refetch()} /> :
        !reports.data?.length ? <Empty title="No reports yet">Generate the first report once the assessment has run.</Empty> : (
          <Table columns={['Version', 'Status', 'CRI', 'Confidence', 'Generated', 'Download']}>
            {reports.data.map((r) => (
              <tr key={r.id}>
                <td>v{r.version}</td>
                <td><Pill status={r.status} /></td>
                <td>{r.status === 'ready' ? num(r.overall_cri, 1) : '—'}</td>
                <td>{r.status === 'ready' ? `${num(r.confidence_score)}%` : '—'}</td>
                <td>{dateTime(r.generated_at)}</td>
                <td>
                  {r.status === 'ready' ? (
                    <div className="row-actions">
                      {r.pdf_available && <button className="secondary-button" onClick={() => void download(() => downloadReport(r.id, 'pdf', `${sprint.sprint_code}-v${r.version}.pdf`))}>PDF</button>}
                      {r.docx_available && <button className="secondary-button" onClick={() => void download(() => downloadReport(r.id, 'docx', `${sprint.sprint_code}-v${r.version}.docx`))}>DOCX</button>}
                      <button className="secondary-button" onClick={() => void exportJson(r)}>JSON</button>
                    </div>
                  ) : r.status === 'failed' ? <span className="muted">Generation failed</span> : <span className="muted">Working…</span>}
                </td>
              </tr>
            ))}
          </Table>
        )}
      <div className="button-row spaced">
        <button className="secondary-button" disabled={exporting} onClick={() => void exportRegister()}>
          {exporting ? 'Preparing evidence register…' : 'Evidence register · CSV'}
        </button>
      </div>
      <Dummy code="R-07" title="Roadmap and board presentation exports" note="These outputs need export endpoints the backend does not have yet; the downloads are disabled.">
        <div className="button-row">
          <button className="secondary-button" disabled>Transformation roadmap · PDF</button>
          <button className="secondary-button" disabled>Board presentation · PPTX</button>
        </div>
      </Dummy>
      </>}
    </>
  );
}

/**
 * The leadership and detailed reports of one result. Their text must be written and checked before a college can
 * download them (the draft gate, capability/publication.py): until then the college is told they are being written,
 * and InGage staff can open them marked Draft, with the reasons.
 */
function ReportCards({ sprintId, runId, staff, download }: {
  sprintId: string; runId: string; staff: boolean; download: (fn: () => Promise<void>) => Promise<void>;
}) {
  const readiness = useResource<ReportReadiness>(() => getReportReadiness(sprintId, runId), `ws-ready:${runId}`);
  const ready = !!readiness.data?.ready;
  const draft = !!readiness.data && !ready;
  const open = staff || ready;
  return (
    <>
      {draft && (staff
        ? <Notice tone="warn"><strong>Draft.</strong> {readiness.data!.reasons.join(' ')} The college can't download these reports yet; yours are marked Draft.</Notice>
        : <Notice tone="info">Your reports are being written. They can be downloaded here as soon as they are ready.</Notice>)}
      <div className="ws-cards ws-cards-2">
        {REPORTS.map((r) => (
          <article className="ws-card ws-report-card" key={r.audience}>
            <div className="ws-report-icon"><Icon name={r.icon} /></div>
            <h3>{r.title}{draft && staff && <span className="tag amber" style={{ marginLeft: 8 }}>Draft</span>}</h3>
            <p>{r.text}</p>
            <small className="ws-source">{r.meta}</small>
            <div className="ws-row">
              <button className="primary-action" disabled={!open || (readiness.loading && !readiness.data)} onClick={() => void download(() => openCapabilityReport(sprintId, runId, r.audience))}>Open</button>
              <button className="secondary-button" disabled={!open || (readiness.loading && !readiness.data)} onClick={() => void download(() => downloadCapabilityReport(sprintId, runId, 'pdf', r.audience))}>Download PDF</button>
            </div>
          </article>
        ))}
      </div>
    </>
  );
}
