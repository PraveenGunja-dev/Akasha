import React, { useState } from 'react';
import { Sparkles, Calculator, ListChecks, UserPlus, XCircle, Check } from 'lucide-react';
import Drawer from './Drawer';
import type { CapacityInsight, ActionPriority } from './types';
import { useCapacityActions, defaultDueDate } from './useCapacityActions';
import { cx } from '../../components/ui/primitives/cx';
import { SEVERITY_META } from './severity';
import { useProjectLink } from './useProjectLink';

/* ═══════════════════════════════════════════════════════════════════════════
   INSIGHT DRAWER

   Every action here does something: Create action writes to the action store,
   View projects hands the affected names back to the page so the drill-down
   opens filtered to them, Dismiss records a dismissal rather than hiding the
   row locally.

   The source badge is load-bearing. A calculated figure is labelled
   "Calculated", never "AI" — the two are visually distinct so the reader can
   tell arithmetic from a model.
   ═══════════════════════════════════════════════════════════════════════════ */


const Row = ({ label, children }: { label: string; children: React.ReactNode }) => (
  <div className="border-t border-border-subtle py-2.5 first:border-t-0">
    <dt className="section-label mb-1">{label}</dt>
    <dd className="text-[12px] leading-relaxed text-fg-secondary">{children}</dd>
  </div>
);

export default function InsightDrawer({
  insight, open, onClose, onViewProjects, projectIdByName,
}: {
  insight: CapacityInsight | null;
  open: boolean;
  onClose: () => void;
  onViewProjects: (projectNames: string[], title: string) => void;
  /** Insights carry project NAMES; the route needs the mapping id. */
  projectIdByName?: Record<string, string>;
}) {
  const { open: openProject } = useProjectLink();
  const { actions, createAction, setStatus } = useCapacityActions();
  const [owner, setOwner] = useState('');
  const [priority, setPriority] = useState<ActionPriority>('High');
  const [saved, setSaved] = useState<string | null>(null);

  if (!insight) return null;
  const meta = SEVERITY_META[insight.severity];
  const Icon = meta.icon;
  const existing = actions.find((a) => a.sourceInsightId === insight.id && a.status !== 'Dismissed');

  const handleCreate = async () => {
    const created = await createAction({
      title: insight.title,
      description: insight.recommendation,
      priority,
      owner: owner.trim() || 'Unassigned',
      dueDate: defaultDueDate(),
      affectedProjects: insight.affectedProjects,
      affectedMW: insight.affectedMW,
      sourceInsightId: insight.id,
    });
    setSaved(created.id);
    setTimeout(() => setSaved(null), 2600);
  };

  const handleDismiss = async () => {
    if (existing) { await setStatus(existing.id, 'Dismissed'); }
    onClose();
  };

  return (
    <Drawer
      open={open}
      onClose={onClose}
      width="max-w-2xl"
      title={insight.title}
      subtitle={
        <span className="flex flex-wrap items-center gap-2">
          <span className={cx('inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-bold', meta.chip)}>
            <Icon className="h-3 w-3" /> {meta.label}
          </span>
          <span className="rounded-full border border-border px-2 py-0.5 text-[10px] font-semibold text-fg-secondary">
            {insight.category}
          </span>
          <span className={cx(
            'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold',
            insight.source === 'ai'
              ? 'border-brand-purple/30 bg-brand-purple/10 text-brand-purple'
              : 'border-border bg-muted text-fg-secondary',
          )}>
            {insight.source === 'ai' ? <Sparkles className="h-3 w-3" /> : <Calculator className="h-3 w-3" />}
            {insight.source === 'ai' ? 'AI generated' : 'Calculated'}
          </span>
        </span>
      }
      footer={
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={handleCreate}
            disabled={!!saved}
            className="inline-flex items-center gap-1.5 rounded-lg bg-gradient-to-r from-brand-blue to-brand-purple px-3 py-1.5 text-[12px] font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          >
            {saved ? <><Check className="h-3.5 w-3.5" /> Action created</> : <><ListChecks className="h-3.5 w-3.5" /> Create action</>}
          </button>
          <button
            onClick={() => onViewProjects(insight.affectedProjects, insight.title)}
            disabled={!insight.affectedProjects.length}
            className="rounded-lg border border-border px-3 py-1.5 text-[12px] font-semibold text-fg-secondary transition-colors hover:bg-muted disabled:opacity-40 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
            title={insight.affectedProjects.length ? undefined : 'This insight is portfolio-level and names no individual projects'}
          >
            View projects ({insight.affectedProjects.length})
          </button>
          <button
            onClick={handleDismiss}
            className="ml-auto inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[12px] font-semibold text-fg-tertiary transition-colors hover:bg-muted hover:text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          >
            <XCircle className="h-3.5 w-3.5" /> Dismiss
          </button>
        </div>
      }
    >
      <div className="mb-4 rounded-xl border border-border bg-muted/40 p-3">
        <div className="section-label mb-1">{insight.metric.label}</div>
        <div className="flex flex-wrap items-baseline gap-2">
          <span className="metric-lg leading-none">{insight.metric.value}</span>
          {insight.metric.comparison && (
            <span className="text-[11px] font-medium text-fg-tertiary">{insight.metric.comparison}</span>
          )}
        </div>
      </div>

      <dl>
        <Row label="Why this matters">{insight.summary}</Row>
        <Row label="How this is derived">{insight.detail}</Row>
        <Row label="Recommended action">{insight.recommendation}</Row>
        <Row label="Affected capacity">
          {insight.affectedMW.toLocaleString('en-IN', { maximumFractionDigits: 1 })} MW
          {insight.affectedProjects.length > 0 && ` across ${insight.affectedProjects.length} project${insight.affectedProjects.length === 1 ? '' : 's'}`}
        </Row>
        {insight.affectedProjects.length > 0 && (
          <Row label="Projects">
            <ul className="flex flex-wrap gap-1.5">
              {insight.affectedProjects.map((p) => {
                const id = projectIdByName?.[p];
                return (
                  <li key={p}>
                    <button
                      onClick={() => id && openProject(id)}
                      disabled={!id}
                      title={id ? `Open ${p}` : 'No project id mapped for this name'}
                      className="rounded-md border border-border bg-card px-1.5 py-0.5 text-[10.5px] font-medium text-fg-secondary transition-colors enabled:hover:border-primary/40 enabled:hover:text-primary disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                    >
                      {p}
                    </button>
                  </li>
                );
              })}
            </ul>
          </Row>
        )}
        <Row label="Evidence">
          <code className="rounded bg-muted px-1.5 py-0.5 text-[11px]">{insight.evidence}</code>
        </Row>
        <Row label="Generated">
          {new Date(insight.generatedAt).toLocaleString()} — recomputed whenever the filters change.
        </Row>
      </dl>

      {/* Assign owner — part of creating the action, not a separate dead button */}
      <div className="mt-4 rounded-xl border border-border p-3">
        <div className="section-label mb-2 flex items-center gap-1.5">
          <UserPlus className="h-3 w-3" /> Assign an owner
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <input
            value={owner}
            onChange={(e) => setOwner(e.target.value)}
            placeholder="Owner name"
            aria-label="Action owner"
            className="min-w-0 flex-1 rounded-lg border border-border bg-card px-2.5 py-1.5 text-[12px] text-foreground placeholder:text-fg-tertiary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          />
          <select
            value={priority}
            onChange={(e) => setPriority(e.target.value as ActionPriority)}
            aria-label="Action priority"
            className="rounded-lg border border-border bg-card px-2.5 py-1.5 text-[12px] font-semibold text-fg-secondary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          >
            <option>High</option><option>Medium</option><option>Low</option>
          </select>
        </div>
        {existing && (
          <p className="mt-2 text-[11px] text-status-healthy-fg">
            Tracked already — owner {existing.owner}, due {existing.dueDate}, status {existing.status}.
          </p>
        )}
      </div>
    </Drawer>
  );
}
