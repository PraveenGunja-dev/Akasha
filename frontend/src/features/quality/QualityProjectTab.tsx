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
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      list = list.filter((nc: any) =>
        (nc.nc_label || '').toLowerCase().includes(q) ||
        (nc.defect_type || '').toLowerCase().includes(q)
      );
    }
    return list;
  }, [data?.ncs, statusFilter, blockFilter, searchQuery]);

  const blocks = useMemo(() => data?.blocks || [], [data?.blocks]);
  const allBlocks = useMemo(() => (data?.ncs || []).map((nc: any) => nc.workarea_name).filter(Boolean), [data?.ncs]);
  const uniqueBlocks = useMemo(() => [...new Set(allBlocks)].sort(), [allBlocks]);

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

      {/* ── Who Needs to Act? ── */}
      {handlerTotal > 0 && (
        <div className="bg-card border border-border rounded-xl p-5">
          <h3 className="text-[11px] font-bold uppercase tracking-widest text-muted-foreground mb-3 flex items-center gap-2">
            <Users className="w-3.5 h-3.5 text-primary" /> Who Needs to Act? <span className="text-foreground ml-1">{handlerTotal} open</span>
          </h3>
          <div className="space-y-2">
            {Object.entries(HANDLER_LABELS).map(([key, cfg]) => {
              const count = byHandler[key] || 0;
              if (count === 0) return null;
              const pct = handlerTotal > 0 ? (count / handlerTotal) * 100 : 0;
              return (
                <div key={key} className={`flex items-center gap-3 p-2.5 rounded-lg ${cfg.bg}`}>
                  <span className={`text-xs font-bold ${cfg.color} w-40`}>{cfg.label}</span>
                  <div className="flex-1 h-2.5 bg-muted rounded-full overflow-hidden">
                    <div className="h-full rounded-full transition-all duration-500"
                      style={{
                        width: `${pct}%`,
                        backgroundColor: key === 'contractor' ? '#ef4444' : key === 'execution_engineer' ? '#f59e0b' : '#3b82f6'
                      }} />
                  </div>
                  <span className={`text-sm font-bold ${cfg.color} w-8 text-right`}>{count}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

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
              <input value={searchQuery} onChange={e => setSearchQuery(e.target.value)} placeholder="Search..."
                className="pl-7 pr-2 py-1 bg-muted border border-border rounded-lg text-[11px] w-[150px] focus:outline-none focus:ring-1 focus:ring-primary" />
            </div>
            <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
              className="bg-muted border border-border rounded-lg text-[11px] px-2 py-1 focus:outline-none focus:ring-1 focus:ring-primary appearance-none cursor-pointer">
              <option value="all">All Status</option>
              {Object.entries(STATUS_CONFIG).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
            </select>
          </div>
        </div>

        <div className="space-y-1.5 max-h-[400px] overflow-y-auto custom-scrollbar">
          {filteredNCs.length === 0 ? (
            <div className="text-center py-8 text-sm text-muted-foreground">No NCs match the current filters.</div>
          ) : filteredNCs.map((nc: any, i: number) => {
            const sCfg = STATUS_CONFIG[nc.status] || { label: nc.status, color: 'text-muted-foreground', bg: 'bg-muted', border: 'border-border' };
            return (
              <div key={nc.id || i} className="border border-border/50 rounded-lg p-3 hover:border-primary/20 transition-colors">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span className="font-mono font-bold text-xs">{nc.nc_label}</span>
                      <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold ${nc.category === 'Critical' ? 'bg-destructive/10 text-destructive' : 'bg-blue-500/10 text-blue-500'}`}>{nc.category}</span>
                      <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold ${sCfg.bg} ${sCfg.color}`}>{sCfg.label}</span>
                    </div>
                    <p className="text-[11px] text-muted-foreground mt-0.5 truncate">{nc.defect_type}</p>
                    <div className="flex items-center gap-2 mt-1 text-[9px] text-muted-foreground/60 flex-wrap">
                      <span>{nc.workarea_name || '—'}</span>
                      <span>•</span>
                      <span>{nc.package_name || '—'}</span>
                      <span>•</span>
                      <span>{nc.vendor_name || nc.contractor_name || '—'}</span>
                      {nc.debit && nc.debit > 0 && <span className="text-pink-500 font-bold">₹{nc.debit.toLocaleString()}</span>}
                    </div>
                  </div>
                  <div className={`text-sm font-bold shrink-0 ${nc.age_days > 30 ? 'text-destructive' : nc.age_days > 14 ? 'text-warning' : 'text-muted-foreground'}`}>
                    {nc.age_days}d
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
