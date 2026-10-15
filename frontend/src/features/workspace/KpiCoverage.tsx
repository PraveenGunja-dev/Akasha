import { motion } from 'framer-motion';
import { ArrowRight } from 'lucide-react';
import { PageHeader, StatusPill, containerVariants, itemVariants } from '../../components/ui/primitives';
import type { Tone } from '../../components/ui/primitives';
import type { DashboardConfig, KpiStatus, SectionId } from './dashboards';

/* The client's KPI list for this dashboard, each with where it is shown or
   why it is not yet. Kept on screen so a missing KPI reads as a known data
   gap with a named source, not as something overlooked. */

const STATUS: Record<KpiStatus, { label: string; tone: Tone }> = {
  live: { label: 'Live', tone: 'healthy' },
  partial: { label: 'Partial', tone: 'watch' },
  planned: { label: 'Being built', tone: 'done' },
  'no-data': { label: 'Needs data', tone: 'neutral' },
};
const ORDER: KpiStatus[] = ['live', 'partial', 'planned', 'no-data'];

export default function KpiCoverage({ config, sectionLabel, onNavigate, visible }: {
  config: DashboardConfig; sectionLabel: (id: SectionId) => string; onNavigate: (id: SectionId) => void;
  /** Sections this user has; a KPI shown elsewhere says so instead of linking. */
  visible: SectionId[];
}) {
  const rows = [...config.kpis].sort((a, b) => ORDER.indexOf(a.status) - ORDER.indexOf(b.status));
  return (
    <motion.div variants={containerVariants} initial="hidden" animate="show" className="space-y-4">
      <motion.div variants={itemVariants}>
        <PageHeader title="KPI coverage"
          subtitle={`The ${config.kpis.length} KPIs agreed for the ${config.title} dashboard, and where each stands. A KPI marked "Needs data" has no source in Akasha yet; nothing is estimated in its place.`} />
      </motion.div>
      <motion.div variants={itemVariants} className="bento-card overflow-x-auto p-0">
        <table className="w-full min-w-[720px] text-[12px]">
          <thead className="border-b border-border bg-[var(--neutral-100)] text-left text-[10px] uppercase tracking-wider text-muted-foreground">
            <tr className="[&>th]:px-4 [&>th]:py-2 [&>th]:font-semibold">
              <th>KPI</th><th>Source</th><th>Status</th><th>Where / what is needed</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(r => (
              <tr key={r.kpi} className="border-b border-[var(--border-subtle)] align-top last:border-0">
                <td className="px-4 py-2.5 font-medium text-foreground">{r.kpi}</td>
                <td className="px-4 py-2.5 text-muted-foreground">{r.source}</td>
                <td className="whitespace-nowrap px-4 py-2.5"><StatusPill tone={STATUS[r.status].tone}>{STATUS[r.status].label}</StatusPill></td>
                <td className="px-4 py-2.5 text-muted-foreground">
                  {r.section && !visible.includes(r.section) && (
                    <span className="mr-2 text-foreground">{sectionLabel(r.section)} (all-portfolio access only, for now) ·</span>
                  )}
                  {r.section && visible.includes(r.section) && (
                    <button type="button" onClick={() => onNavigate(r.section!)}
                      className="mr-2 inline-flex items-center gap-1 font-medium text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary">
                      {sectionLabel(r.section)} <ArrowRight className="h-3 w-3" />
                    </button>
                  )}
                  {r.note}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </motion.div>
    </motion.div>
  );
}
