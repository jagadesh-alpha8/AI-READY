import React, { useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { listReports, generateReport, getReport, downloadReport } from '../../api/reports';
import { getSprint } from '../../api/sprints';
import { useApiResource } from '../../hooks/useApiResource';
import { getErrorMessage } from '../../utils/errors';
import { ErrorState, InlineError, LoadingState } from '../../components/ApiStates';
import type { Report } from '../../types';
import { FileText, Download, Sparkles, Printer, Globe } from 'lucide-react';

const POLL_INTERVAL_MS = 3000;

async function fetchLatestReport(sprintId: string): Promise<{ data: Report | null }> {
  const list = await listReports(sprintId);
  const latest = list.data[0];
  if (!latest) return { data: null };
  if (latest.status !== 'ready') return { data: latest };
  const detail = await getReport(latest.id);
  return { data: detail.data };
}

export const ReportPreviewExport: React.FC = () => {
  const { sprintId } = useParams<{ sprintId: string }>();
  const isRealSprint = !!sprintId && sprintId !== 'demo-sprint-id';

  const {
    data: report,
    setData: setReport,
    loading,
    error,
    refetch,
  } = useApiResource<Report | null>(() => fetchLatestReport(sprintId!), [sprintId], isRealSprint);
  const { data: sprint } = useApiResource(() => getSprint(sprintId!), [sprintId], isRealSprint);

  const [generating, setGenerating] = useState(false);
  const [actionError, setActionError] = useState('');
  const [downloading, setDownloading] = useState<'pdf' | 'docx' | null>(null);

  // Report generation runs on Celery, same as extraction -- the row
  // generateReport() returns is fresh (status 'draft'/'generating') and
  // won't include report_data yet. Rather than guessing how long the real
  // job takes with a fixed delay, poll the real status every few seconds
  // (mirroring AIProcessingMonitor.tsx's pattern) until it's no longer
  // in flight.
  const isGeneratingOnServer = report?.status === 'draft' || report?.status === 'generating';
  const refetchRef = useRef(refetch);
  refetchRef.current = refetch;

  useEffect(() => {
    if (!isGeneratingOnServer) return;
    const timer = setInterval(() => refetchRef.current(), POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [isGeneratingOnServer]);

  const handleGenerate = async () => {
    if (!isRealSprint) {
      setActionError('No active sprint is selected. Set up a sprint first.');
      return;
    }
    setGenerating(true);
    setActionError('');
    try {
      const res = await generateReport(sprintId!);
      setReport(res.data);
    } catch (err) {
      setActionError(getErrorMessage(err, 'Failed to generate the report.'));
    } finally {
      setGenerating(false);
    }
  };

  const handleDownload = async (fileFormat: 'pdf' | 'docx') => {
    if (!report) return;
    setDownloading(fileFormat);
    setActionError('');
    try {
      await downloadReport(report.id, fileFormat, `${sprint?.sprint_code || 'report'}_v${report.version}.${fileFormat}`);
    } catch (err) {
      setActionError(getErrorMessage(err, `Failed to download the ${fileFormat.toUpperCase()}.`));
    } finally {
      setDownloading(null);
    }
  };

  const data = report?.report_data;

  return (
    <div className="space-y-6">
      {/* Top Banner */}
      <div className="glass-card p-5 sm:p-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h1 className="text-xl sm:text-2xl font-bold text-ink-900 flex items-center gap-2">
              <FileText className="w-5 h-5 text-brand-800" /> Screen 10: Executive AI Readiness Discovery Report
            </h1>
            <p className="text-sm text-ink-500 mt-1">
              Final executive report preview with PDF/DOCX export and publication control.
            </p>
          </div>
          <div className="flex items-center gap-3 flex-wrap">
            <button onClick={() => window.print()} className="btn-secondary">
              <Printer className="w-3.5 h-3.5" />
              <span>Print / Save PDF</span>
            </button>
            <button onClick={handleGenerate} disabled={generating} className="btn-primary shrink-0">
              <Globe className="w-4 h-4" />
              <span>{generating ? 'Generating...' : 'Publish Final Report'}</span>
            </button>
          </div>
        </div>
      </div>

      {actionError && <InlineError message={actionError} onDismiss={() => setActionError('')} />}

      {loading ? (
        <LoadingState message="Loading report..." />
      ) : error ? (
        <ErrorState message={error} onRetry={refetch} />
      ) : !report ? (
        <div className="glass-card p-8 text-center space-y-3 max-w-4xl mx-auto">
          <p className="text-sm text-ink-500">No report generated yet for this sprint.</p>
          <button onClick={handleGenerate} disabled={generating} className="btn-primary btn-sm">
            {generating ? 'Generating...' : 'Generate Report Now'}
          </button>
        </div>
      ) : report.status !== 'ready' || !data ? (
        <LoadingState
          message={
            report.status === 'failed'
              ? 'Report generation failed. Try publishing again.'
              : 'Report is generating -- this page will update automatically.'
          }
        />
      ) : (
        <>
          {/* Executive Report Document Container */}
          <div className="bg-card border border-line-200 rounded-xl p-6 sm:p-8 space-y-8 shadow-popover text-ink-700 max-w-4xl mx-auto">
            {/* Report Header */}
            <div className="border-b border-line-200 pb-6 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div>
                <span className="text-xs font-bold text-brand-800 uppercase tracking-widest">INGAGE TECHNOLOGIES • AIOS DISCOVERY SPRINT</span>
                <h2 className="text-xl sm:text-2xl font-bold text-ink-900 mt-1">Executive AI Readiness Baseline Report</h2>
                <p className="text-xs text-ink-500 mt-0.5">
                  Institution: {data.institution.name}
                  {sprint?.academic_year ? ` | Academic Year: ${sprint.academic_year}` : ''}
                </p>
              </div>
              <div className="sm:text-right shrink-0">
                <span className={report.status === 'ready' ? 'badge-success' : 'badge-warning'}>
                  Status: {report.status.toUpperCase()}
                </span>
                <p className="text-xs text-ink-400 mt-1">Version: {report.version}.0</p>
              </div>
            </div>

            {/* Section 1: Executive Summary */}
            <div className="space-y-3">
              <h3 className="text-sm font-bold text-brand-800 uppercase tracking-wide">1. Executive Summary &amp; CRI Score</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="p-4 bg-surface rounded-xl border border-line-200 text-center">
                  <span className="text-xs text-ink-500">Campus Readiness Index (CRI)</span>
                  <div className="text-3xl sm:text-4xl font-bold text-ink-900 my-1 tabular-nums">{data.overall_cri.toFixed(1)} <span className="text-sm text-ink-500 font-normal">/ 100</span></div>
                  <span className="text-xs text-brand-800 font-semibold">Confidence-Weighted Baseline</span>
                </div>
                <div className="p-4 bg-surface rounded-xl border border-line-200 text-center">
                  <span className="text-xs text-ink-500">CRI Evidence Confidence</span>
                  <div className="text-3xl sm:text-4xl font-bold text-accent my-1 tabular-nums">{(data.confidence_score * 100).toFixed(0)}%</div>
                  <span className="text-xs text-accent font-semibold">
                    {data.confidence_score >= 0.8 ? 'High Confidence Baseline' : 'Building Confidence'}
                  </span>
                </div>
              </div>
              <p className="text-sm leading-relaxed text-ink-700 bg-surface p-4 rounded-lg border border-line-200">
                {data.executive_summary}
              </p>
            </div>

            {/* Section 2: Pillar Evaluation */}
            <div className="space-y-3">
              <h3 className="text-sm font-bold text-brand-800 uppercase tracking-wide">2. Pillar Scorecard Overview</h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
                {data.pillar_scorecards.map((p) => (
                  <div key={p.pillar} className="p-3 bg-surface rounded-lg border border-line-200 flex justify-between gap-2">
                    <span className="text-ink-700">{p.label}</span>
                    <span className={`font-bold tabular-nums ${
                      p.status === 'strong' ? 'text-success' : p.status === 'at_risk' ? 'text-danger' : 'text-brand-800'
                    }`}>
                      {p.raw_score.toFixed(1)} / 100
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {/* Section 3: 90-Day Priority Action Plan */}
            <div className="space-y-3">
              <h3 className="text-sm font-bold text-brand-800 uppercase tracking-wide">3. 90-Day Transformation Roadmap</h3>
              <div className="space-y-2 text-sm">
                {data.ninety_day_action_plan.length === 0 ? (
                  <p className="text-ink-400">No near-term actions identified yet.</p>
                ) : (
                  data.ninety_day_action_plan.flatMap((bucket) =>
                    bucket.items.map((item: any, idx: number) => (
                      <div key={`${bucket.timeline}-${idx}`} className="p-3 bg-surface rounded-lg border border-line-200">
                        <span className="font-bold text-ink-900">{item.title}</span>
                        <p className="text-ink-500 text-xs mt-0.5">
                          {item.description} (+{item.expected_cri_lift?.toFixed?.(1) ?? item.expected_cri_lift} CRI Lift)
                        </p>
                      </div>
                    )),
                  )
                )}
              </div>
            </div>

            {/* Download actions */}
            <div className="flex items-center gap-3 pt-2 flex-wrap">
              <button
                onClick={() => handleDownload('pdf')}
                disabled={!report.pdf_available || downloading !== null}
                className="btn-primary btn-sm"
              >
                <Download className="w-3.5 h-3.5" /> {downloading === 'pdf' ? 'Downloading...' : 'Download PDF'}
              </button>
              <button
                onClick={() => handleDownload('docx')}
                disabled={!report.docx_available || downloading !== null}
                className="btn-secondary btn-sm"
              >
                <Download className="w-3.5 h-3.5" /> {downloading === 'docx' ? 'Downloading...' : 'Download DOCX'}
              </button>
              <button onClick={handleGenerate} disabled={generating} className="btn-secondary btn-sm">
                <Sparkles className="w-3.5 h-3.5" /> {generating ? 'Regenerating...' : 'Regenerate Report'}
              </button>
            </div>

            {/* Footer */}
            <div className="pt-6 border-t border-line-200 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-1 text-xs text-ink-400">
              <span>InGage AIOS Platform • Confidential Executive Baseline</span>
              <span>Sprint ID: {sprintId}</span>
            </div>
          </div>
        </>
      )}
    </div>
  );
};
