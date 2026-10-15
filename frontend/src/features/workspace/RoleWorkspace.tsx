import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { useSearchParams } from 'react-router-dom';
import {
  Home, Command, Calendar, BarChart2, HardHat, ShieldCheck, CheckCircle, Network,
  Database, FileText, ListChecks, ChevronDown,
} from 'lucide-react';
import { AppFrame, AppHeader, AppRail } from '../../components/layout/AppRail';
import { Loader as AkLoader } from '../../components/ui/primitives';
import { useAuth } from '../../context/AuthContext';
import { DASHBOARDS } from './dashboards';
import type { SectionId } from './dashboards';
import RoleOverview from './RoleOverview';
import KpiCoverage from './KpiCoverage';
import Project360 from '../projects/Project360';
import ProjectWorkspace from '../projects/ProjectWorkspace';
import P6View from '../../components/dashboards/P6View';
import CapacityOverviewPage from '../capacity/CapacityOverviewPage';
import ModuleDeliveriesPage from '../modules/ModuleDeliveriesPage';
import QualityCommandCenter from '../quality/QualityCommandCenter';
import ComplianceDashboard from '../compliance/ComplianceDashboard';
import TransmissionDataViewer from '../analytics/TransmissionDataViewer';
import SAPIntelligencePage from '../sap-intelligence/SAPIntelligencePage';
import EInvoiceIntelligence from '../analytics/EInvoiceIntelligence';
import ReportsInsights from '../analytics/ReportsInsights';

/* One shell for the PMAG, Projects, TC Ordering and TC Stores dashboards.
   The sections are the Executive dashboard's own components, so a figure reads
   the same wherever it is shown; each dashboard picks the ones its KPI list
   needs (./dashboards.ts).

   Portfolio scope: a user with portfolios assigned sees only those - the
   server narrows every call - and the sections that cannot yet filter by
   portfolio (`allPortfolioOnly`) are not offered to them at all. */

interface SectionDef {
  label: string;
  icon: React.JSX.Element;
  /** Reads across every portfolio; hidden from portfolio-scoped users until its API filters by portfolio. */
  allPortfolioOnly?: boolean;
  needs?: 'dash' | 'p6';
}

const SECTIONS: Record<SectionId, SectionDef> = {
  overview: { label: 'Overview', icon: <Home />, needs: 'dash' },
  project360: { label: 'Project 360', icon: <Command /> },
  schedule: { label: 'P6 & DPR', icon: <Calendar />, needs: 'p6' },
  capacity: { label: 'Capacity Overview', icon: <BarChart2 /> },
  ordering: { label: 'Ordering Schedule', icon: <HardHat /> },
  quality: { label: 'Quality', icon: <ShieldCheck /> },
  approvals: { label: 'Approvals', icon: <CheckCircle /> },
  transmission: { label: 'Transmission', icon: <Network />, allPortfolioOnly: true, needs: 'dash' },
  sap: { label: 'SAP Intelligence', icon: <Database />, allPortfolioOnly: true },
  einvoice: { label: 'E-Invoice', icon: <FileText />, allPortfolioOnly: true },
  reports: { label: 'CPAG Report', icon: <FileText /> },
  kpis: { label: 'KPI Coverage', icon: <ListChecks /> },
};

export default function RoleWorkspace({ dashboard }: { dashboard: string }) {
  const config = DASHBOARDS[dashboard];
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const access = user?.portfolio_access;
  const scoped = !!access && !access.all;

  // Sections this user gets on this dashboard.
  const groups = useMemo(() => config.groups
    .map(g => ({ ...g, sections: g.sections.filter(id => !(scoped && SECTIONS[id].allPortfolioOnly)) }))
    .filter(g => g.sections.length > 0), [config, scoped]);
  const visible = useMemo(() => groups.flatMap(g => g.sections), [groups]);

  const requested = params.get('view') as SectionId | null;
  const section: SectionId = requested && visible.includes(requested) ? requested : 'overview';
  const [projectId, setProjectId] = useState<string | null>(null);

  const go = useCallback((id: SectionId) => {
    setProjectId(null);
    setParams(prev => { if (id === 'overview') prev.delete('view'); else prev.set('view', id); return prev; });
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, [setParams]);

  // Portfolio choice in the URL, kept within the user's own portfolios.
  const clusters = access?.clusters ?? [];
  const portfolio = params.get('portfolio') || '';
  useEffect(() => {
    const parts = portfolio.split(',').map(s => s.trim()).filter(Boolean);
    if (scoped && parts.some(p => !clusters.includes(p))) {
      setParams(prev => { prev.delete('portfolio'); return prev; }, { replace: true });
    }
  }, [scoped, portfolio, clusters, setParams]);
  const phase = params.get('phase') || 'Ongoing';
  const scopeLabel = portfolio || (scoped ? (clusters.length === 1 ? clusters[0] : `${clusters.join(', ')}`) : 'All portfolios');

  // Shared data, fetched only when the open section needs it.
  const need = SECTIONS[section].needs;
  const query = useMemo(() => {
    const q = new URLSearchParams();
    if (portfolio) q.set('portfolio', portfolio);
    if (phase !== 'ALL') q.set('phase', phase);
    return q.toString() ? `?${q}` : '';
  }, [portfolio, phase]);
  const [dash, setDash] = useState<any>(null);
  const [p6, setP6] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const seq = useRef(0);
  useEffect(() => {
    if (!need) return;
    const mine = ++seq.current;
    setLoading(true);
    const url = need === 'dash' ? `/akasha/api/dashboard/summary${query}` : `/akasha/api/summary${query}`;
    fetch(url)
      .then(r => (r.ok ? r.json() : Promise.reject(r.status)))
      .then(d => { if (mine === seq.current) { if (need === 'dash') setDash(d); else setP6(Array.isArray(d) ? d : []); } })
      .catch(() => { if (mine === seq.current) { if (need === 'dash') setDash(null); else setP6([]); } })
      .finally(() => { if (mine === seq.current) setLoading(false); });
  }, [need, query]);

  const label = (id: SectionId) => SECTIONS[id].label;

  const content = (() => {
    if (projectId) return <ProjectWorkspace projectId={projectId} onBack={() => setProjectId(null)} />;
    switch (section) {
      case 'overview': return <RoleOverview config={config} dash={dash} loading={loading} scopeLabel={scopeLabel} onOpenProject={setProjectId} onNavigate={go} />;
      case 'project360': return <Project360 onOpenProject={setProjectId} />;
      case 'schedule': return loading && p6.length === 0
        ? <AkLoader size="md" label="Loading the P6 schedule…" className="min-h-[60vh] w-full" />
        : <P6View p6Data={p6} loading={loading} />;
      case 'capacity': return <CapacityOverviewPage />;
      case 'ordering': return <ModuleDeliveriesPage />;
      case 'quality': return <QualityCommandCenter />;
      case 'approvals': return <ComplianceDashboard />;
      case 'transmission': return <TransmissionDataViewer dashboardData={dash} />;
      case 'sap': return <SAPIntelligencePage />;
      case 'einvoice': return <EInvoiceIntelligence />;
      case 'reports': return <ReportsInsights allowedScopes={access?.all ? undefined : access?.apis ?? []} />;
      case 'kpis': return <KpiCoverage config={config} sectionLabel={label} onNavigate={go} visible={visible} />;
    }
  })();

  const railGroups = groups.map(g => ({ title: g.title, items: g.sections.map(id => ({ id, label: SECTIONS[id].label, icon: SECTIONS[id].icon })) }));
  const portfolioOptions = scoped
    ? (clusters.length > 1 ? [{ v: '', l: 'All my portfolios' }] : []).concat(clusters.map(c => ({ v: c, l: c })))
    : [{ v: '', l: 'All portfolios' }, ...clusters.map(c => ({ v: c, l: c }))];
  const select = 'appearance-none rounded-lg border border-border bg-card py-1.5 pl-3 pr-8 text-[12px] font-semibold text-foreground shadow-sm transition-colors hover:bg-muted focus:outline-none focus:ring-2 focus:ring-primary/30 disabled:opacity-100';

  return (
    <AppFrame
      rail={<AppRail subtitle={`${config.title} dashboard`} groups={railGroups} active={projectId ? 'project360' : section} onSelect={id => go(id as SectionId)} />}
      header={
        <AppHeader kicker={config.title} title={projectId ? 'Project' : label(section)}>
          <label className="relative hidden sm:block">
            <span className="sr-only">Phase</span>
            <select value={phase} className={select}
              onChange={e => { const v = e.target.value; setParams(prev => { if (v === 'Ongoing') prev.delete('phase'); else prev.set('phase', v); return prev; }); }}>
              <option value="Ongoing">Ongoing</option>
              <option value="Commissioned">Commissioned</option>
              <option value="ALL">All phases</option>
            </select>
            <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden />
          </label>
          <label className="relative">
            <span className="sr-only">Portfolio</span>
            <select value={portfolio} disabled={portfolioOptions.length < 2} className={`${select} max-w-[11rem] sm:max-w-none`}
              onChange={e => { const v = e.target.value; setParams(prev => { if (v) prev.set('portfolio', v); else prev.delete('portfolio'); return prev; }); }}>
              {portfolioOptions.map(o => <option key={o.v || 'all'} value={o.v}>{o.l}</option>)}
            </select>
            {portfolioOptions.length > 1 && <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden />}
          </label>
        </AppHeader>
      }>
      <AnimatePresence mode="wait">
        <motion.div key={projectId ? `project:${projectId}` : section}
          initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }}
          transition={{ duration: 0.18, ease: [0.2, 0, 0, 1] }}>
          {content}
        </motion.div>
      </AnimatePresence>
    </AppFrame>
  );
}
