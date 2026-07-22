import React, { useState, useEffect, useMemo } from 'react';
import {
  Shield, AlertTriangle, CheckCircle2, Clock, Users, XCircle,
  Package, MapPin, Search, Filter, ChevronDown
} from 'lucide-react';

const STATUS_CONFIG: Record<string, { label: string; color: string; bg: string; border: string }> = {
  raised: { label: 'Raised', color: 'text-destructive', bg: 'bg-destructive/10', border: 'border-destructive/20' },
  submitted: { label: 'In Review (EE)', color: 'text-amber-500', bg: 'bg-amber-500/10', border: 'border-amber-500/20' },
  approved: { label: 'In Review (QI)', color: 'text-blue-500', bg: 'bg-blue-500/10', border: 'border-blue-500/20' },
  completed: { label: 'Approved', color: 'text-success', bg: 'bg-success/10', border: 'border-success/20' },
  rejected: { label: 'Rejected', color: 'text-orange-500', bg: 'bg-orange-500/10', border: 'border-orange-500/20' },
};

const HANDLER_LABELS: Record<string, { label: string; color: string; bg: string }> = {
  contractor: { label: 'Contractor Pending', color: 'text-destructive', bg: 'bg-destructive/5' },
  execution_engineer: { label: 'EE Review Pending', color: 'text-amber-500', bg: 'bg-amber-500/5' },
  quality_inspector: { label: 'QI Review Pending', color: 'text-blue-500', bg: 'bg-blue-500/5' },
};

interface QualityProjectTabProps {
  projectName: string;
}

export default function QualityProjectTab({ projectName }: QualityProjectTabProps) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [blockFilter, setBlockFilter] = useState('all');
  const [contractorFilter, setContractorFilter] = useState('all');

  useEffect(() => {
    if (!projectName) return;
    setLoading(true);
    fetch(`/akasha/api/quality/project/${encodeURIComponent(projectName)}`)
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [projectName]);

  const filteredNCs = useMemo(() => {
    if (!data?.ncs) return [];
    let list = data.ncs;
    if (statusFilter !== 'all') list = list.filter((nc: any) => nc.status === statusFilter);
    if (blockFilter !== 'all') list = list.filter((nc: any) => nc.workarea_name === blockFilter);
    if (contractorFilter !== 'all') {
      list = list.filter((nc: any) => (nc.vendor_name || nc.contractor_name || 'Unknown') === contractorFilter);
    }
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      list = list.filter((nc: any) =>
        (nc.nc_label || '').toLowerCase().includes(q) ||
        (nc.defect_type || '').toLowerCase().includes(q) ||
        (nc.description || '').toLowerCase().includes(q)
      );
    }
    return list;
  }, [data?.ncs, statusFilter, blockFilter, contractorFilter, searchQuery]);

  const blocks = useMemo(() => data?.blocks || [], [data?.blocks]);
  const allBlocks = useMemo(() => (data?.ncs || []).map((nc: any) => nc.workarea_name).filter(Boolean), [data?.ncs]);
  const uniqueBlocks = useMemo(() => [...new Set(allBlocks)].sort(), [allBlocks]);

  const allContractors = useMemo(() => (data?.ncs || []).map((nc: any) => nc.vendor_name || nc.contractor_name || 'Unknown').filter(Boolean), [data?.ncs]);
  const uniqueContractors = useMemo(() => [...new Set(allContractors)].sort(), [allContractors]);

  // Analytics for top contractors
  const topContractors = useMemo(() => {
    const counts: Record<string, number> = {};
    let totalOpen = 0;
    (data?.ncs || []).forEach((nc: any) => {
      if (nc.status === 'completed' || nc.status === 'rejected') return;
      const name = nc.vendor_name || nc.contractor_name || 'Unknown';
      counts[name] = (counts[name] || 0) + 1;
      totalOpen++;
    });
    const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 5);
    return { list: sorted, total: totalOpen };
  }, [data?.ncs]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="flex items-center gap-2 text-muted-foreground text-sm">
          <Shield className="w-5 h-5 animate-pulse text-primary" /> Loading quality data...
        </div>
      </div>
    );
  }

  if (!data || data.total_ncs === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center">
        <CheckCircle2 className="w-12 h-12 text-success/40 mb-3" />
        <h3 className="font-semibold text-lg">No Quality Issues</h3>
        <p className="text-sm text-muted-foreground mt-1">No NCs have been recorded for this project. Try syncing data.</p>
      </div>
    );
  }

  const byHandler = data.by_handler || {};
  const byStatus = data.by_status || {};
  const handlerTotal = Object.values(byHandler).reduce((a: number, b: any) => a + (Number(b) || 0), 0) as number;

  return (
    <div className="flex flex-col gap-5 animate-in fade-in duration-400">

      {/* ── KPI Row ── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="bg-card border border-border rounded-xl p-4 flex flex-col gap-1">
          <span className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground">Total NCs</span>
          <span className="text-2xl font-bold">{data.total_ncs}</span>
          <span className="text-[10px] text-muted-foreground">{data.by_status?.completed || 0} resolved</span>
        </div>
        <div className="bg-card border border-border rounded-xl p-4 flex flex-col gap-1">
          <span className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground">RFI Progress</span>
          <span className="text-2xl font-bold text-success">{data.rfis_completed}<span className="text-sm text-muted-foreground font-normal">/{data.total_rfis}</span></span>
          <span className="text-[10px] text-muted-foreground">{data.total_rfis > 0 ? Math.round(data.rfis_completed / data.total_rfis * 100) : 0}% completed</span>
        </div>
        <div className="bg-card border border-border rounded-xl p-4 flex flex-col gap-1">
          <span className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground">Closure Rate</span>
          <span className={`text-2xl font-bold ${data.closure_rate >= 70 ? 'text-success' : data.closure_rate >= 40 ? 'text-warning' : 'text-destructive'}`}>{data.closure_rate}%</span>
          <span className="text-[10px] text-muted-foreground">NC resolution rate</span>
        </div>
        <div className="bg-card border border-border rounded-xl p-4 flex flex-col gap-1">
          <span className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground">Quality Score</span>
          <span className={`text-2xl font-bold ${data.quality_score >= 70 ? 'text-success' : data.quality_score >= 40 ? 'text-warning' : 'text-destructive'}`}>{data.quality_score}<span className="text-sm text-muted-foreground font-normal">/100</span></span>
          <span className="text-[10px] text-muted-foreground">Composite quality metric</span>
        </div>
      </div>

      {/* ── Analytics Grid ── */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {handlerTotal > 0 && (
          <div className="bg-card border border-border rounded-xl p-5 shadow-sm">
            <h3 className="text-[11px] font-bold uppercase tracking-widest text-muted-foreground mb-4 flex items-center gap-2">
              <Users className="w-3.5 h-3.5 text-primary" /> Who Needs to Act? <span className="text-foreground ml-1">{handlerTotal} open</span>
            </h3>
            <div className="grid grid-cols-3 gap-3">
              {Object.entries(HANDLER_LABELS).map(([key, cfg]) => {
                const count = byHandler[key] || 0;
                return (
                  <div key={key} className={`flex flex-col items-center justify-center gap-2 p-4 rounded-xl border border-transparent transition-all hover:scale-[1.02] cursor-default ${cfg.bg}`}>
                    <span className={`text-4xl font-black ${cfg.color} drop-shadow-sm`}>{count}</span>
                    <span className={`text-[9px] font-bold ${cfg.color} uppercase tracking-widest text-center leading-tight`}>
                      {cfg.label.replace(' Pending', '')}<br />Pending
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {topContractors.total > 0 && (
          <div className="bg-card border border-border rounded-xl p-5 shadow-sm">
            <h3 className="text-[11px] font-bold uppercase tracking-widest text-muted-foreground mb-4 flex items-center gap-2">
              <AlertTriangle className="w-3.5 h-3.5 text-warning" /> Top Contractors by Open NCs
            </h3>
            <div className="space-y-4">
              {topContractors.list.map(([name, count], i) => {
                const maxCount = topContractors.list[0][1];
                const pct = (count / maxCount) * 100;
                return (
                  <div key={name} className="flex items-start gap-3 group">
                    <div className="w-6 h-6 rounded-full bg-primary/10 text-primary flex items-center justify-center text-[10px] font-bold shrink-0 mt-0.5 ring-2 ring-background">
                      {i + 1}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex justify-between items-end mb-1.5">
                        <span className="text-[10px] font-bold text-foreground/90 truncate uppercase tracking-widest pr-2" title={name}>{name}</span>
                        <span className="text-xs font-black text-foreground">{count}</span>
                      </div>
                      <div className="h-1.5 w-full bg-black/5 dark:bg-white/5 rounded-full overflow-hidden">
                        <div className="h-full bg-primary opacity-80 rounded-full transition-all duration-700 ease-out group-hover:opacity-100 shadow-sm" style={{ width: `${pct}%` }} />
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* ── Block Quality Map ── */}
      {blocks.length > 0 && (
        <div className="bg-card border border-border rounded-xl p-5">
          <h3 className="text-[11px] font-bold uppercase tracking-widest text-muted-foreground mb-3 flex items-center gap-2">
            <MapPin className="w-3.5 h-3.5 text-primary" /> Block Quality Map
          </h3>
          <div className="flex flex-wrap gap-2">
            {blocks.sort((a: any, b: any) => a.name.localeCompare(b.name)).map((block: any) => {
              const hasOpenCritical = block.critical_open > 0;
              const hasOpen = block.open > 0;
              return (
                <button key={block.name}
                  onClick={() => setBlockFilter(blockFilter === block.name ? 'all' : block.name)}
                  className={`px-3 py-2 rounded-lg border text-xs font-medium transition-all flex items-center gap-1.5 ${
                    blockFilter === block.name ? 'border-primary bg-primary/10 text-primary ring-1 ring-primary/30' :
                    hasOpenCritical ? 'border-destructive/30 bg-destructive/5 hover:border-destructive/50' :
                    hasOpen ? 'border-warning/30 bg-warning/5 hover:border-warning/50' :
                    'border-success/30 bg-success/5 hover:border-success/50'
                  }`}>
                  <span className={`w-2 h-2 rounded-full ${hasOpenCritical ? 'bg-destructive animate-pulse' : hasOpen ? 'bg-warning' : 'bg-success'}`}></span>
                  {block.name}
                  <span className="text-muted-foreground/60">({block.total})</span>
                </button>
              );
            })}
          </div>
          <div className="flex items-center gap-4 mt-3 text-[9px] text-muted-foreground/60">
            <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-destructive"></span> Open Critical NC</span>
            <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-warning"></span> Open Non-Critical</span>
            <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-success"></span> No open NCs</span>
          </div>
        </div>
      )}

      {/* ── NC List ── */}
      <div className="bg-card border border-border rounded-xl p-5">
        <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
          <h3 className="text-[11px] font-bold uppercase tracking-widest text-muted-foreground flex items-center gap-2">
            <Shield className="w-3.5 h-3.5 text-primary" /> NC Details
          </h3>
          <div className="flex items-center gap-2 flex-wrap">
            <div className="relative">
              <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3 text-muted-foreground" />
              <input value={searchQuery} onChange={e => setSearchQuery(e.target.value)} placeholder="Search defect or description..."
                className="pl-7 pr-2 py-1.5 bg-muted border border-border rounded-lg text-[11px] w-[200px] focus:outline-none focus:ring-1 focus:ring-primary" />
            </div>
            <select value={contractorFilter} onChange={e => setContractorFilter(e.target.value)}
              className="bg-muted border border-border rounded-lg text-[11px] px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-primary appearance-none cursor-pointer">
              <option value="all">All Contractors</option>
              {uniqueContractors.map((c: any) => <option key={String(c)} value={String(c)}>{String(c)}</option>)}
            </select>
            <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
              className="bg-muted border border-border rounded-lg text-[11px] px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-primary appearance-none cursor-pointer">
              <option value="all">All Status</option>
              {Object.entries(STATUS_CONFIG).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
            </select>
          </div>
        </div>

        <div className="overflow-x-auto max-h-[400px] overflow-y-auto custom-scrollbar">
          <table className="intel-table relative w-full">
            <thead className="sticky top-0 bg-slate-50/95 dark:bg-gray-900/95 backdrop-blur-sm z-10 text-[10px] uppercase tracking-wider">
              <tr>
                <th className="whitespace-nowrap">NC ID & Status</th>
                <th>Defect / Description</th>
                <th>Location</th>
                <th>Responsibility</th>
                <th>Pending With</th>
                <th className="text-right">Age</th>
              </tr>
            </thead>
            <tbody>
              {filteredNCs.length === 0 ? (
                <tr>
                  <td colSpan={6} className="text-center py-8 text-sm text-muted-foreground">No NCs match the current filters.</td>
                </tr>
              ) : filteredNCs.map((nc: any, i: number) => {
                const sCfg = STATUS_CONFIG[nc.status] || { label: nc.status, color: 'text-muted-foreground', bg: 'bg-muted', border: 'border-border' };
                return (
                  <tr key={nc.id || i} className="hover:bg-muted/50 transition-colors group">
                    <td className="align-top max-w-[200px]">
                      <div className="font-mono font-bold text-[11px] text-foreground mb-1">{nc.nc_label}</div>
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold ${nc.category === 'Critical' ? 'bg-destructive/10 text-destructive' : 'bg-blue-500/10 text-blue-500'}`}>{nc.category}</span>
                        <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold ${sCfg.bg} ${sCfg.color}`}>{sCfg.label}</span>
                      </div>
                    </td>
                    <td className="align-top max-w-[250px]">
                      <div className="text-[11px] font-semibold text-foreground/90 truncate" title={nc.defect_type}>{nc.defect_type}</div>
                      {nc.description && <div className="text-[10px] text-muted-foreground line-clamp-2 mt-0.5" title={nc.description}>{nc.description}</div>}
                    </td>
                    <td className="align-top max-w-[150px]">
                      <div className="text-[10px] flex items-center gap-1 truncate text-foreground/80"><MapPin className="w-2.5 h-2.5 text-muted-foreground/60 shrink-0"/> {nc.workarea_name || '—'}</div>
                      {nc.package_name && <div className="text-[9px] text-muted-foreground mt-0.5 truncate pl-3.5">{nc.package_name}</div>}
                    </td>
                    <td className="align-top max-w-[180px]">
                      <div className="text-[10px] font-medium text-foreground/80 truncate flex items-center gap-1" title={nc.vendor_name || nc.contractor_name}><Users className="w-2.5 h-2.5 text-muted-foreground/60 shrink-0"/> {nc.vendor_name || nc.contractor_name || '—'}</div>
                      {(nc.engineer_name || nc.quality_name) && (
                        <div className="flex flex-col gap-0.5 mt-1 pl-3.5 text-[9px] text-muted-foreground">
                          {nc.engineer_name && <div className="truncate"><span className="font-semibold">EE:</span> {nc.engineer_name}</div>}
                          {nc.quality_name && <div className="truncate"><span className="font-semibold">QI:</span> {nc.quality_name}</div>}
                        </div>
                      )}
                    </td>
                    <td className="align-top">
                      {nc.current_handler ? (
                        <div className="flex items-center gap-1 text-[10px] text-amber-500 font-medium capitalize">
                          <Clock className="w-2.5 h-2.5 shrink-0" /> {nc.current_handler.replace(/_/g, ' ')}
                        </div>
                      ) : <span className="text-muted-foreground/50 text-[10px]">—</span>}
                    </td>
                    <td className="align-top text-right">
                      <div className={`text-sm font-black ${nc.age_days > 30 ? 'text-destructive' : nc.age_days > 14 ? 'text-warning' : 'text-foreground'}`}>
                        {nc.age_days}<span className="text-[9px] font-semibold opacity-60 ml-0.5">d</span>
                      </div>
                      {nc.debit && nc.debit > 0 && <div className="text-[9px] font-bold text-pink-500 mt-1 whitespace-nowrap">₹{nc.debit.toLocaleString()}</div>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
