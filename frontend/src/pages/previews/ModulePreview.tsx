import React from 'react';
import { Navigate, useParams } from 'react-router-dom';
import { AlertTriangle, ArrowDown, FileInput, HelpCircle, Layers, Puzzle, Recycle } from 'lucide-react';

import { getModuleFlow } from './moduleFlows';
import type { WireBlock } from './moduleFlows';

/**
 * Renders one unbuilt module's proposed flow, for review.
 *
 * The single most important job of this screen is that **nobody mistakes it
 * for working software**. That is why the warning banner is the first thing
 * rendered, why every screen sketch is grey wireframe rather than styled UI,
 * and why no wireframe carries a value that could be read as data. A
 * screenshot of this page must be obviously a proposal.
 */

/** One wireframe block. Grey and deliberately unfinished-looking — the
 * reviewer should read the label and picture the screen, not evaluate the
 * visual design of something that does not exist. */
const Block: React.FC<{ block: WireBlock }> = ({ block }) => {
  const { type, label } = block;

  if (type === 'title') {
    return (
      <div className="h-7 rounded bg-ink-500/25 flex items-center px-2.5">
        <span className="text-[11px] font-bold text-ink-700 truncate">{label}</span>
      </div>
    );
  }

  if (type === 'button') {
    return (
      <div className="inline-flex h-7 rounded-md bg-brand-500/25 border border-brand-500/40 items-center px-3">
        <span className="text-[11px] font-semibold text-ink-700 truncate">{label}</span>
      </div>
    );
  }

  if (type === 'input') {
    return (
      <div className="h-8 rounded border-2 border-dashed border-line-300 flex items-center px-2.5">
        <span className="text-[11px] text-ink-500 italic truncate">{label}</span>
      </div>
    );
  }

  if (type === 'split') {
    return (
      <div className="grid grid-cols-2 gap-1.5">
        {label.split('|').map((part, i) => (
          <div key={i} className="h-7 rounded bg-line-100 border border-line-200 flex items-center px-2">
            <span className="text-[10px] text-ink-600 truncate">{part.trim()}</span>
          </div>
        ))}
      </div>
    );
  }

  if (type === 'table') {
    const columns = label.split('|').map((c) => c.trim());
    return (
      <div className="rounded border border-line-200 overflow-hidden">
        <div className="flex bg-line-100 border-b border-line-200">
          {columns.map((col, i) => (
            <div key={i} className="flex-1 px-2 py-1.5 min-w-0">
              <span className="text-[10px] font-bold text-ink-600 uppercase tracking-wide truncate block">
                {col}
              </span>
            </div>
          ))}
        </div>
        {/* Empty rows on purpose: this is a layout, not a dataset. */}
        {[0, 1, 2].map((row) => (
          <div key={row} className="flex border-b border-line-100 last:border-b-0">
            {columns.map((_, i) => (
              <div key={i} className="flex-1 px-2 py-2 min-w-0">
                <div className="h-2 rounded bg-line-200" style={{ width: `${55 + ((row + i) % 4) * 10}%` }} />
              </div>
            ))}
          </div>
        ))}
      </div>
    );
  }

  if (type === 'chart') {
    return (
      <div className="rounded border border-line-200 p-2.5 space-y-2">
        <span className="text-[10px] font-bold text-ink-600 uppercase tracking-wide">{label}</span>
        <div className="flex items-end gap-1.5 h-16">
          {[45, 70, 30, 85, 55, 65, 40, 75].map((h, i) => (
            <div key={i} className="flex-1 rounded-t bg-brand-500/25" style={{ height: `${h}%` }} />
          ))}
        </div>
      </div>
    );
  }

  if (type === 'list') {
    return (
      <div className="space-y-1.5">
        {[0, 1, 2].map((row) => (
          <div key={row} className="flex items-start gap-2 rounded border border-line-200 px-2.5 py-2">
            <div className="w-1.5 h-1.5 rounded-full bg-ink-500/40 mt-1.5 shrink-0" />
            <div className="min-w-0 flex-1 space-y-1">
              <span className="text-[11px] text-ink-600 truncate block">{row === 0 ? label : ''}</span>
              {row > 0 && <div className="h-2 rounded bg-line-200" style={{ width: `${80 - row * 15}%` }} />}
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (type === 'card') {
    return (
      <div className="rounded border border-line-300 bg-line-100/60 px-3 py-2.5">
        <span className="text-[11px] text-ink-700 font-medium">{label}</span>
      </div>
    );
  }

  // 'text'
  return <span className="text-[11px] text-ink-500 block">{label}</span>;
};

const SectionCard: React.FC<{
  icon: React.ElementType;
  title: string;
  children: React.ReactNode;
}> = ({ icon: Icon, title, children }) => (
  <div className="glass-card p-5 space-y-3">
    <h2 className="eyebrow flex items-center gap-2">
      <Icon className="w-4 h-4 text-ink-500 shrink-0" />
      {title}
    </h2>
    {children}
  </div>
);

export const ModulePreview: React.FC = () => {
  const { moduleKey } = useParams<{ moduleKey: string }>();
  const flow = getModuleFlow(moduleKey);

  // An unknown key is a bad link, not an error state worth a screen.
  if (!flow) return <Navigate to="/status-dashboard" replace />;

  const Icon = flow.icon;

  return (
    <div className="space-y-6">
      {/* The warning comes FIRST — before the module name — so it cannot be
          cropped out of a screenshot of the top of this page. */}
      <div className="rounded-lg border-2 border-warning-line bg-warning-bg p-4">
        <div className="flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-warning shrink-0 mt-0.5" />
          <div className="space-y-1 min-w-0">
            <p className="text-sm font-bold text-warning">
              Design preview — this module is NOT built. Nothing on this page works.
            </p>
            <p className="text-sm text-ink-600">
              The layouts below are grey sketches of a <strong>proposed</strong> flow, not agreed
              scope and not screenshots. They exist to be corrected: please tell us what is wrong,
              missing, or out of order before we write any code for this module.
            </p>
          </div>
        </div>
      </div>

      <div className="flex items-start gap-3">
        <div className="p-2.5 rounded-lg bg-brand-500/10 border border-brand-500/30 text-brand-800 shrink-0">
          <Icon className="w-6 h-6" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <h1 className="text-xl sm:text-2xl font-bold text-ink-900">{flow.label}</h1>
            <span className={flow.status === 'next' ? 'badge badge-accent' : 'badge badge-neutral'}>
              {flow.status === 'next' ? 'Next to build' : 'Not started'}
            </span>
          </div>
          <p className="text-sm text-ink-500 mt-1">{flow.purpose}</p>
        </div>
      </div>

      {flow.basedOn && (
        <div className="rounded-lg border border-info-line bg-info-bg p-4 flex items-start gap-3">
          <FileInput className="w-4 h-4 text-info shrink-0 mt-0.5" />
          <p className="text-sm text-ink-600 min-w-0">
            <strong className="text-info">Source of this flow. </strong>
            {flow.basedOn}
          </p>
        </div>
      )}

      <SectionCard icon={Puzzle} title="Why this module exists">
        <p className="text-sm text-ink-600">{flow.problem}</p>
      </SectionCard>

      <div>
        <h2 className="eyebrow flex items-center gap-2 mb-3">
          <Layers className="w-4 h-4 text-ink-500 shrink-0" />
          Proposed flow — {flow.steps.length} steps
        </h2>

        <div className="space-y-3">
          {flow.steps.map((step, index) => (
            <React.Fragment key={step.title}>
              <div className="glass-card p-5">
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                  <div className="space-y-2 min-w-0">
                    <div className="flex items-center gap-2.5">
                      <span className="w-6 h-6 rounded-full bg-brand-500 text-on-brand text-xs font-bold flex items-center justify-center shrink-0">
                        {index + 1}
                      </span>
                      <h3 className="text-sm font-bold text-ink-900">{step.title}</h3>
                    </div>
                    <p className="text-xs font-semibold text-brand-800 uppercase tracking-wide">
                      {step.actor}
                    </p>
                    <p className="text-sm text-ink-600">{step.detail}</p>
                  </div>

                  <div className="min-w-0">
                    <p className="text-[10px] font-bold text-ink-500 uppercase tracking-wide mb-2">
                      Rough screen layout
                    </p>
                    <div className="rounded-lg border border-line-200 bg-surface p-3 space-y-2">
                      {step.screen.map((block, i) => (
                        <Block key={i} block={block} />
                      ))}
                    </div>
                  </div>
                </div>
              </div>

              {index < flow.steps.length - 1 && (
                <div className="flex justify-center" aria-hidden="true">
                  <ArrowDown className="w-4 h-4 text-ink-500/50" />
                </div>
              )}
            </React.Fragment>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <SectionCard icon={Recycle} title="What it reuses (already built)">
          <ul className="space-y-2">
            {flow.reuses.map((item) => (
              <li key={item} className="text-sm text-ink-600 flex items-start gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-success mt-1.5 shrink-0" />
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </SectionCard>

        <SectionCard icon={Puzzle} title="What must exist first">
          {flow.dependsOn.length === 0 ? (
            <p className="text-sm text-ink-500">
              Nothing — this module could be built independently, whenever it is prioritised.
            </p>
          ) : (
            <ul className="space-y-2">
              {flow.dependsOn.map((item) => (
                <li key={item} className="text-sm text-ink-600 flex items-start gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-warning mt-1.5 shrink-0" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          )}
        </SectionCard>
      </div>

      <div className="glass-card p-5 space-y-3 border-brand-500/30">
        <h2 className="eyebrow flex items-center gap-2">
          <HelpCircle className="w-4 h-4 text-brand-800 shrink-0" />
          Decisions we need before building this
        </h2>
        <p className="text-sm text-ink-500">
          These are the questions the proposal above could not answer on its own. Each one changes
          what gets built, so an answer here saves rework later.
        </p>
        <ol className="space-y-2.5">
          {flow.questions.map((question, i) => (
            <li key={question} className="text-sm text-ink-700 flex items-start gap-2.5">
              <span className="w-5 h-5 rounded bg-brand-500/15 text-brand-800 text-[11px] font-bold flex items-center justify-center shrink-0 mt-0.5">
                {i + 1}
              </span>
              <span>{question}</span>
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
};
