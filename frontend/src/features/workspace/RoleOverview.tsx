import { useEffect, useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import { useSearchParams } from 'react-router-dom';
import {
  AlertTriangle, Boxes, CheckCircle2, ClipboardCheck, Factory, Gauge, IndianRupee,
  PackageCheck, Search, ShieldAlert, Truck, Zap, ArrowRight,
} from 'lucide-react';
import { KPITile, SourceTag, StatusPill, containerVariants, itemVariants } from '../../components/ui/primitives';
import HeroBanner from '../../components/layout/HeroBanner';
import type { Tone } from '../../components/ui/primitives';
import { formatProjectName } from '../../lib/projectName';
import type { DashboardConfig, KpiStatus, SectionId } from './dashboards';

/* A dashboard's first screen: its own KPIs (not the Executive overview, which
   is built for the whole portfolio and reads empty for a handful of projects),
   then the projects in the user's portfolio as cards that work for 3 or 50,
   then how much of the client's KPI list is live. Every figure comes from a
   portfolio-aware endpoint; the server narrows it to the user's portfolios. */

interface Props {
  config: DashboardConfig;
  dash: any;                 // /api/dashboard/summary
  loading: boolean;
  scopeLabel: string;
  onOpenProject: (projectId: string) => void;
  onNavigate: (section: SectionId) => void;
}

const nf = (n: number, d = 0) => n.toLocaleString('en-IN', { maximumFractionDigits: d, minimumFractionDigits: d });
const cr = (inr: number) => nf(inr / 1e7, inr >= 1e10 ? 0 : 1);

function useJson<T>(url: string | null): { data: T | null; error: string; loading: boolean } {
  const [state, setState] = useState<{ data: T | null; error: string; loading: boolean }>({ data: null, error: '', loading: !!url });
  useEffect(() => {
    if (!url) return;
    let live = true;
    setState(s => ({ ...s, loading: true, error: '' }));
    fetch(url)
      .then(r => (r.ok ? r.json() : Promise.reject(new Error(`${r.status}`))))
      .then(d => { if (live) setState({ data: d, error: '', loading: false }); })
      .catch(() => { if (live) setState({ data: null, error: 'Could not load', loading: false }); });
    return () => { live = false; };
  }, [url]);
  return state;
}

export default function RoleOverview({ config, dash, loading, scopeLabel, onOpenProject, onNavigate }: Props) {
  const [params] = useSearchParams();
  const qs = useMemo(() => {
    const q = new URLSearchParams();
    const p = params.get('portfolio');
    const ph = params.get('phase') || 'Ongoing';
    if (p) q.set('portfolio', p);
    if (ph && ph !== 'ALL') q.set('phase', ph);
    return q.toString() ? `?${q}` : '';
  }, [params]);
  const portfolioOnly = params.get('portfolio') ? `?portfolio=${encodeURIComponent(params.get('portfolio')!)}` : '';

  const k = config.key;
  const wantQuality = k === 'pmag' || k === 'projects';
  const wantStatutory = k === 'pmag';
  const wantModules = k === 'projects' || k === 'tc_ordering' || k === 'tc_stores';
  const quality = useJson<any>(wantQuality ? `/akasha/api/quality/overview${qs}` : null);
  const statutory = useJson<any>(wantStatutory ? `/akasha/api/statutory/dashboard-summary${qs}` : null);
  const modules = useJson<any>(wantModules ? `/akasha/api/module-deliveries/summary${portfolioOnly}` : null);

  const s = dash?.summary ?? {};
  const projects: any[] = dash?.projects ?? [];
  const mt = modules.data?.totals;
  const awaitingGrn = (modules.data?.projects ?? []).reduce((a: number, p: any) => a + (p.procurement?.awaiting_grn_mwp ?? 0), 0);
  const aribaGrn = (modules.data?.projects ?? []).reduce((a: number, p: any) => a + (p.procurement?.received_mwp ?? 0), 0);

  const tiles = (() => {
    const busy = loading;
    const total = s.total_projects ?? projects.length;
    const delayed = s.delayed_projects ?? 0;
    const q = quality.data;
    const aged30 = q?.aging?.['30+'] ?? 0;
    switch (k) {
      case 'projects': return [
        <KPITile key="cap" icon={Zap} label="Capacity" value={nf(s.total_mw ?? 0)} unit="MWac" loading={busy}
          proportion={s.total_mw ? { pct: ((s.achieved_mw ?? 0) / s.total_mw) * 100, nowLabel: `${nf(s.achieved_mw ?? 0)} MW at COD` } : undefined}
          source="P6" />,
        <KPITile key="del" icon={AlertTriangle} label="Projects delayed" value={nf(delayed)} denominator={nf(total)} loading={busy}
          tone={delayed > 0 ? 'risk' : 'healthy'} subtext="P6 finish later than baseline" source="P6" onClick={() => onNavigate('project360')} />,
        <KPITile key="mod" icon={PackageCheck} label="Modules received" value={mt ? nf(mt.received_mwp) : '—'} unit="MWp" loading={modules.loading}
          error={modules.error || undefined}
          proportion={mt?.ordered_mwp ? { pct: (mt.received_mwp / mt.ordered_mwp) * 100, nowLabel: `of ${nf(mt.ordered_mwp)} MWp ordered` } : undefined}
          source="SAP" onClick={() => onNavigate('ordering')} />,
        <KPITile key="nc" icon={ShieldAlert} label="Open NCs" value={q ? nf(q.open_ncs) : '—'} loading={quality.loading} error={quality.error || undefined}
          tone={q && q.critical_open > 0 ? 'risk' : 'neutral'}
          stats={q ? [{ label: 'Critical', value: nf(q.critical_open) }, { label: '30+ days', value: nf(aged30) }] : undefined}
          source="Pulse" onClick={() => onNavigate('quality')} />,
      ];
      case 'pmag': return [
        <KPITile key="del" icon={AlertTriangle} label="Projects delayed" value={nf(delayed)} denominator={nf(total)} loading={busy}
          tone={delayed > 0 ? 'risk' : 'healthy'} subtext="P6 finish later than baseline" source="P6" onClick={() => onNavigate('project360')} />,
        <KPITile key="nc" icon={ShieldAlert} label="Open NCs" value={q ? nf(q.open_ncs) : '—'} loading={quality.loading} error={quality.error || undefined}
          tone={aged30 > 0 ? 'risk' : 'neutral'}
          stats={q ? [{ label: 'Critical', value: nf(q.critical_open) }, { label: '30+ days', value: nf(aged30) }] : undefined}
          source="Pulse" onClick={() => onNavigate('quality')} />,
        <KPITile key="rfi" icon={ClipboardCheck} label="RFI pass rate" value={q ? nf(q.rfi_pass_rate ?? 0, 1) : '—'} unit="%" loading={quality.loading}
          stats={q ? [{ label: 'RFIs', value: nf(q.total_rfis) }, { label: 'In flight', value: nf(q.rfis_in_flight ?? 0) }] : undefined}
          source="Pulse" onClick={() => onNavigate('quality')} />,
        statutory.data && statutory.data.total_projects_tracked === 0
          ? <KPITile key="stat" icon={CheckCircle2} label="Statutory approvals" value="No projects tracked" isText loading={statutory.loading}
              subtext="None of these projects is in the statutory tracker" onClick={() => onNavigate('approvals')} />
          : <KPITile key="stat" icon={CheckCircle2} label="Statutory approvals" value={statutory.data ? nf(statutory.data.overall_compliance_percent ?? 0) : '—'} unit="%"
              loading={statutory.loading} error={statutory.error || undefined}
              subtext={statutory.data ? `${nf(statutory.data.total_projects_tracked)} projects tracked` : undefined}
              tone={(statutory.data?.overall_compliance_percent ?? 100) < 80 ? 'watch' : 'neutral'} onClick={() => onNavigate('approvals')} />,
      ];
      case 'tc_ordering': return [
        <KPITile key="po" icon={IndianRupee} label="PO value" value={cr(s.total_po_value ?? 0)} unit="₹ Cr" loading={busy}
          proportion={s.total_po_value ? { pct: (((s.total_po_delivered_cr ?? 0) * 1e7) / s.total_po_value) * 100, nowLabel: `₹${nf(s.total_po_delivered_cr ?? 0)} Cr delivered` } : undefined}
          source="SAP" />,
        <KPITile key="ord" icon={Factory} label="Modules ordered" value={mt ? nf(mt.ordered_mwp) : '—'} unit="MWp" loading={modules.loading}
          stats={mt ? [{ label: 'Balance to order', value: nf(mt.balance_ordering_mwp), unit: 'MWp' }] : undefined}
          source="SAP" onClick={() => onNavigate('ordering')} />,
        <KPITile key="grn" icon={Truck} label="Awaiting GRN" value={modules.data ? nf(awaitingGrn, 1) : '—'} unit="MWp" loading={modules.loading}
          subtext="Dispatched in Ariba, no GR posting yet" tone={awaitingGrn > 0 ? 'watch' : 'neutral'} onClick={() => onNavigate('ordering')} />,
        <KPITile key="cov" icon={ClipboardCheck} label="Receipts proven in Ariba" value={mt?.received_mwp ? nf((aribaGrn / mt.received_mwp) * 100) : '—'} unit="%"
          loading={modules.loading} subtext={mt ? `${nf(aribaGrn)} of ${nf(mt.received_mwp)} MWp received` : undefined} onClick={() => onNavigate('ordering')} />,
      ];
      default: return [   // tc_stores
        <KPITile key="inv" icon={Boxes} label="Module inventory" value={mt ? nf(mt.inventory_mwp) : '—'} unit="MWp" loading={modules.loading}
          subtext="Received less erected (SAP − P6)" source={['SAP', 'P6']} onClick={() => onNavigate('ordering')} />,
        <KPITile key="rcv" icon={PackageCheck} label="Modules received" value={mt ? nf(mt.received_mwp) : '—'} unit="MWp" loading={modules.loading}
          proportion={mt?.ordered_mwp ? { pct: (mt.received_mwp / mt.ordered_mwp) * 100, nowLabel: `of ${nf(mt.ordered_mwp)} MWp ordered` } : undefined}
          source="SAP" />,
        <KPITile key="grn" icon={Truck} label="Awaiting GRN" value={modules.data ? nf(awaitingGrn, 1) : '—'} unit="MWp" loading={modules.loading}
          subtext="Dispatched, not yet booked at site" tone={awaitingGrn > 0 ? 'watch' : 'neutral'} />,
        <KPITile key="all" icon={Gauge} label="All-material stock" value="Being built" isText
          subtext="Plant-wise MB52 stock, ageing and ABC are next" onClick={() => onNavigate('kpis')} />,
      ];
    }
  })();

  const counts = config.kpis.reduce((acc, r) => ({ ...acc, [r.status]: (acc[r.status] ?? 0) + 1 }), {} as Record<KpiStatus, number>);

  return (
    <motion.div variants={containerVariants} initial="hidden" animate="show" className="space-y-5">
      <motion.div variants={itemVariants}>
        <HeroBanner compact part1={config.title} part2="Overview" sub={config.purpose}>
          <div className="flex flex-wrap items-center gap-2 text-[12px]">
            <span className="rounded-full border border-border bg-card/80 px-2.5 py-1 font-semibold text-foreground backdrop-blur">{scopeLabel}</span>
            <SourceTag system="P6" /><SourceTag system="SAP" /><SourceTag system="Pulse" />
          </div>
        </HeroBanner>
      </motion.div>

      <motion.div variants={itemVariants} className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">{tiles}</motion.div>

      {config.key !== 'tc_stores' && (
        <motion.div variants={itemVariants}>
          <ProjectCards projects={projects} loading={loading} onOpen={onOpenProject} onAll={() => onNavigate('project360')} />
        </motion.div>
      )}

      <motion.button variants={itemVariants} type="button" onClick={() => onNavigate('kpis')}
        className="bento-card group flex w-full flex-wrap items-center gap-x-5 gap-y-2 px-4 py-3 text-left transition-colors hover:border-primary/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary">
        <span className="text-[12px] font-semibold text-foreground">KPI coverage</span>
        <span className="text-[12px] text-muted-foreground"><b className="text-[var(--status-healthy-fg)]">{counts.live ?? 0}</b> live</span>
        <span className="text-[12px] text-muted-foreground"><b className="text-foreground">{counts.partial ?? 0}</b> partial</span>
        <span className="text-[12px] text-muted-foreground"><b className="text-foreground">{counts.planned ?? 0}</b> being built</span>
        <span className="text-[12px] text-muted-foreground"><b className="text-foreground">{counts['no-data'] ?? 0}</b> need a data source</span>
        <span className="ml-auto inline-flex items-center gap-1 text-[12px] font-medium text-primary">See all {config.kpis.length} <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" /></span>
      </motion.button>
    </motion.div>
  );
}

/* ── Projects as cards ─────────────────────────────────────────────────── */

// Status is the server's own verdict (p6.health, the rule that counts
// "Projects delayed"), so a card never disagrees with the tile above it.
// Days late are calendar days, current finish minus baseline finish. P6's
// finish_date_variance is in working hours, so it is not read as days.
function projectState(p: any): { tone: Tone; label: string; days: number | null } {
  const fin = p?.p6?.finish_date ? new Date(p.p6.finish_date) : null;
  const base = p?.p6?.baseline_finish_date ? new Date(p.p6.baseline_finish_date) : null;
  const late = fin && base ? Math.round((fin.getTime() - base.getTime()) / 86_400_000) : null;
  if (p?.is_commissioned) return { tone: 'done', label: 'Commissioned', days: 0 };
  const health = String(p?.p6?.health ?? '').toLowerCase();
  if (health === 'delayed') return { tone: 'risk', label: late && late > 0 ? `${late}d late` : 'Delayed', days: -(late && late > 0 ? late : 0.1) };
  if (health === 'on track') return { tone: 'healthy', label: 'On plan', days: 0 };
  return { tone: 'neutral', label: 'No P6 data', days: 1 };
}

function ProjectCards({ projects, loading, onOpen, onAll }: {
  projects: any[]; loading: boolean; onOpen: (id: string) => void; onAll: () => void;
}) {
  const [q, setQ] = useState('');
  const sorted = useMemo(() => [...projects]
    .filter(p => !q || `${p.project_name} ${p.p6_project_name}`.toLowerCase().includes(q.toLowerCase()))
    .sort((a, b) => (projectState(a).days ?? 0) - (projectState(b).days ?? 0)), [projects, q]);
  const shown = sorted.slice(0, 12);

  return (
    <section className="bento-card p-0">
      <div className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-3">
        <h2 className="text-[13px] font-semibold text-foreground">Projects <span className="font-normal text-muted-foreground">· {projects.length}, most delayed first</span></h2>
        {projects.length > 6 && (
          <div className="relative ml-auto w-full sm:w-56">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden />
            <input aria-label="Find a project" value={q} onChange={e => setQ(e.target.value)} placeholder="Find a project"
              className="w-full rounded-lg border border-border bg-background py-1.5 pl-8 pr-3 text-[12px] text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/30" />
          </div>
        )}
      </div>
      {loading && projects.length === 0 ? (
        <div className="grid gap-3 p-4 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => <div key={i} className="h-[92px] animate-pulse rounded-lg bg-muted/60" />)}
        </div>
      ) : projects.length === 0 ? (
        <p className="px-4 py-6 text-sm text-muted-foreground">No projects match this portfolio and phase.</p>
      ) : (
        <ul className="grid gap-3 p-4 sm:grid-cols-2 xl:grid-cols-3">
          {shown.map(p => {
            const st = projectState(p);
            const pct = Math.max(0, Math.min(100, Number(p?.p6?.progress ?? 0)));
            const id = p?.p6?.id;
            return (
              <li key={p.mapping_id ?? p.project_name}>
                <button type="button" disabled={!id} onClick={() => id && onOpen(id)}
                  className="group flex h-full w-full flex-col gap-2 rounded-lg border border-border bg-card p-3 text-left transition-[border-color,transform] hover:-translate-y-0.5 hover:border-primary/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:cursor-default disabled:hover:translate-y-0">
                  <span className="flex items-start justify-between gap-2">
                    <span className="min-w-0">
                      <span className="block truncate text-[13px] font-semibold text-foreground" title={p.project_name}>{p.project_name}</span>
                      <span className="block truncate text-[11px] text-muted-foreground" title={p.p6_project_name}>{formatProjectName(p.p6_project_name) || '—'}</span>
                    </span>
                    <StatusPill tone={st.tone}>{st.label}</StatusPill>
                  </span>
                  <span className="flex items-center gap-2">
                    <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted" aria-hidden>
                      <span className="block h-full rounded-full bg-primary transition-[width] duration-700" style={{ width: `${pct}%` }} />
                    </span>
                    <span className="w-10 text-right text-[11px] tabular-nums text-muted-foreground">{nf(pct)}%</span>
                  </span>
                  <span className="flex justify-between text-[11px] tabular-nums text-muted-foreground">
                    <span>{nf(p.capacity_mwac ?? 0)} MWac</span>
                    <span>P6 progress</span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
      {sorted.length > shown.length && (
        <button type="button" onClick={onAll} className="flex w-full items-center justify-center gap-1 border-t border-border py-2.5 text-[12px] font-medium text-primary hover:bg-muted/50">
          All {sorted.length} projects in Project 360 <ArrowRight className="h-3.5 w-3.5" />
        </button>
      )}
    </section>
  );
}
