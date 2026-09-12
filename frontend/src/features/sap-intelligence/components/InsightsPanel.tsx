import React, { useState } from 'react';
import { Lightbulb, Sparkles, ChevronRight, AlertTriangle, AlertOctagon, Info, CheckCircle2 } from 'lucide-react';
import { Card, CardHeader, StatusPill, cx } from '../../../components/ui/primitives';
import { useInsights } from '../hooks';
import { useSAPStore } from '../store';
import { SEVERITY_TONE } from '../format';
import { Btn, Skeleton, ErrorBox, Empty } from './Drawer';
import type { Insight, Severity } from '../types';

/* The "what needs attention" column. Every item is computed from the same
   filtered data as the rest of the page and labelled by how it was made:
   "Computed" for the rule engine, and an "AI" note only where the model
   actually added one. The panel never calls arithmetic "AI". */

const SEV_ICON: Record<Severity, React.ComponentType<{ className?: string }>> = { critical: AlertOctagon, warning: AlertTriangle, info: Info, success: CheckCircle2 };
const CAT_LABEL: Record<string, string> = { procurement: 'Procurement', inventory: 'Inventory', vendor: 'Vendor', material: 'Material', financial: 'Financial', risk: 'Risk', 'data-quality': 'Data quality' };

export const InsightRow = ({ i, onOpen, compact }: { i: Insight; onOpen: () => void; compact?: boolean }) => {
  const Icon = SEV_ICON[i.severity];
  const tone = SEVERITY_TONE[i.severity];
  return (
    <button type="button" onClick={onOpen}
      className={cx('group flex w-full items-start gap-3 rounded-md border border-l-[3px] border-border-subtle bg-surface-1 text-left transition-colors hover:border-border-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        tone === 'critical' && 'border-l-status-critical-solid', tone === 'risk' && 'border-l-status-risk-solid', tone === 'healthy' && 'border-l-status-healthy-solid', tone === 'neutral' && 'border-l-border-strong',
        compact ? 'px-3 py-2' : 'px-3.5 py-3')}>
      <Icon className={cx('mt-0.5 h-4 w-4 shrink-0', tone === 'critical' ? 'text-status-critical-fg' : tone === 'risk' ? 'text-status-risk-fg' : tone === 'healthy' ? 'text-status-healthy-fg' : 'text-fg-tertiary')} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate text-[13px] font-semibold text-fg-primary">{i.title}</span>
        </div>
        {!compact && <p className="mt-0.5 line-clamp-2 text-[12.5px] leading-snug text-fg-secondary">{i.aiNote ?? i.summary}</p>}
        <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-[11px] text-fg-tertiary">
          <span className="rounded bg-surface-sunken px-1.5 py-px">{CAT_LABEL[i.category] ?? i.category}</span>
          <span className="rounded bg-surface-sunken px-1.5 py-px">Computed</span>
          {i.aiNote && <StatusPill tone="ai" className="!py-px !text-[11px]"><Sparkles className="mr-1 inline h-3 w-3" />AI note</StatusPill>}
        </div>
      </div>
      <ChevronRight className="mt-1 h-4 w-4 shrink-0 text-fg-tertiary opacity-0 transition-opacity group-hover:opacity-100" />
    </button>
  );
};

export const InsightsPanel = () => {
  const { insights, loading, error, refetch, data } = useInsights();
  const openInsight = useSAPStore(s => s.openInsight);
  const openDrawer = useSAPStore(s => s.openDrawer);
  const [showAll, setShowAll] = useState(false);
  const shown = showAll ? insights : insights.slice(0, 4);

  return (
    <Card pad="md" className="flex h-full flex-col">
      <CardHeader icon={Lightbulb} eyebrow="Needs attention" title="Insights"
        right={<>
          {insights.length > 4 && <Btn variant="ghost" onClick={() => setShowAll(v => !v)}>{showAll ? 'Show top 4' : `View all ${insights.length}`}</Btn>}
        </>} />
      <div className="custom-scrollbar min-h-0 flex-1 space-y-2 overflow-y-auto">
        {error ? <ErrorBox message={error} onRetry={refetch} />
          : loading && !data ? <>{[0, 1, 2, 3].map(i => <Skeleton key={i} className="h-[76px]" />)}</>
            : shown.length === 0 ? <Empty message="Nothing needs attention for the selected filters." />
              : shown.map(i => <InsightRow key={i.id} i={i} onOpen={() => openInsight(i.id)} />)}
      </div>
      <button type="button" onClick={() => openDrawer({ kind: 'ask' })}
        className="mt-3 flex h-9 w-full shrink-0 items-center gap-2 rounded-md border border-border-default bg-surface-0 px-3 text-left text-[13px] text-fg-tertiary hover:border-border-strong hover:text-fg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
        <Sparkles className="h-3.5 w-3.5 text-secondary-600" /> Ask Akasha about your SAP data…
      </button>
    </Card>
  );
};
