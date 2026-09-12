import React, { useEffect, useMemo, useRef, useState } from 'react';
import ReactECharts from 'echarts-for-react';
import { Bookmark, BookmarkCheck, Download, Sparkles, Send, Trash2, ExternalLink, Building2, Package, FileText, Lightbulb } from 'lucide-react';
import { StatusPill, cx } from '../../../../components/ui/primitives';
import { useChartTheme } from '../../../../lib/chartTheme';
import { formatProjectName } from '../../../../lib/projectName';
import { Drawer, Btn, Stat, Section, NotAvailable, Skeleton, ErrorBox } from '../Drawer';
import { MoreFilters } from '../SAPFilters';
import { useInsights, useMaterial, useOverview, usePO, useVendor, useVendors, useMaterials } from '../../hooks';
import { useSAPStore } from '../../store';
import { sapApi } from '../../api';
import { fmtCr, fmtDate, fmtNum, fmtPct, STATUS_LABEL, STATUS_TONE, SEVERITY_TONE } from '../../format';
import { exportCSV, exportName } from '../../export';
import type { DrawerState, Insight, KpiId, TrendBucket, WatchKind } from '../../types';

/* ── Watch button, shared ── */
const WatchBtn = ({ kind, id, label }: { kind: WatchKind; id: string; label: string }) => {
  const watched = useSAPStore(s => s.watchlist.some(w => w.kind === kind && w.id === id));
  const toggle = useSAPStore(s => s.toggleWatch);
  return <Btn variant={watched ? 'primary' : 'secondary'} onClick={() => toggle(kind, id, label)} aria-pressed={watched}>{watched ? <BookmarkCheck className="h-3.5 w-3.5" /> : <Bookmark className="h-3.5 w-3.5" />}{watched ? 'Tracking' : 'Track'}</Btn>;
};

const MiniBars = ({ series, k, label }: { series: TrendBucket[]; k: keyof TrendBucket; label: string }) => {
  const { themeName, chrome, categorical } = useChartTheme();
  const option = useMemo(() => ({
    grid: { left: 4, right: 4, top: 6, bottom: 18, containLabel: true },
    tooltip: { trigger: 'axis', backgroundColor: chrome.surface2, borderColor: chrome.borderSubtle, textStyle: { color: chrome.fgPrimary, fontSize: 12 }, valueFormatter: (v: number) => fmtCr(v) },
    xAxis: { type: 'category', data: series.map(s => s.bucket), axisTick: { show: false }, axisLine: { lineStyle: { color: chrome.axisLine } }, axisLabel: { color: chrome.fgTertiary, fontSize: 10, hideOverlap: true } },
    yAxis: { type: 'value', axisLine: { show: false }, axisTick: { show: false }, splitLine: { lineStyle: { color: chrome.gridLine } }, axisLabel: { color: chrome.fgTertiary, fontSize: 10, formatter: (v: number) => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : String(v) } },
    series: [{ name: label, type: 'bar', data: series.map(s => s[k]), barMaxWidth: 18, itemStyle: { color: categorical[0] } }],
  }), [series, k, label, chrome, categorical]);
  return <div className="h-[140px]" role="img" aria-label={`${label} by period`}><ReactECharts theme={themeName} option={option} notMerge style={{ height: '100%', width: '100%' }} /></div>;
};

const RowList = ({ rows, onOpen, icon: Icon }: { rows: { key: string; label: React.ReactNode; value: React.ReactNode; sub?: React.ReactNode }[]; onOpen?: (key: string) => void; icon?: React.ComponentType<{ className?: string }> }) => (
  <ul className="divide-y divide-border-subtle rounded-md border border-border-subtle">
    {rows.map(r => {
      const inner = <><div className="min-w-0 flex-1"><div className="truncate text-[13px] text-fg-primary">{r.label}</div>{r.sub && <div className="text-[11px] text-fg-tertiary">{r.sub}</div>}</div><div className="shrink-0 text-[13px] font-medium tabular-nums text-fg-primary">{r.value}</div></>;
      return <li key={r.key}>{onOpen ? <button type="button" onClick={() => onOpen(r.key)} className="flex w-full items-center gap-3 px-3 py-2 text-left hover:bg-surface-sunken focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">{Icon && <Icon className="h-3.5 w-3.5 shrink-0 text-fg-tertiary" />}{inner}</button> : <div className="flex items-center gap-3 px-3 py-2">{inner}</div>}</li>;
    })}
  </ul>
);

/* ── PO ── */
const PODrawer = ({ id, onClose, depth, canGoBack }: { id: string; onClose: () => void; depth: number; canGoBack: boolean }) => {
  const { data, loading, error, refetch } = usePO(id);
  const openVendor = useSAPStore(s => s.openVendor); const openMaterial = useSAPStore(s => s.openMaterial); const setFilters = useSAPStore(s => s.setFilters);
  const cols = useSAPStore(s => s.ledger.columns);
  return (
    <Drawer open onClose={onClose} depth={depth} canGoBack={canGoBack} eyebrow="Purchase order" title={<span className="font-mono">{id}</span>} width="xl"
      actions={data && <>
        <WatchBtn kind="po" id={id} label={`PO ${id} · ${data.vendor ?? 'no vendor'}`} />
        {data.vendor && <Btn onClick={() => openVendor(data.vendor!)}><Building2 className="h-3.5 w-3.5" />Vendor</Btn>}
        <Btn onClick={() => { setFilters({ search: id }); onClose(); }}><FileText className="h-3.5 w-3.5" />Show in ledger</Btn>
        <Btn onClick={() => exportCSV(data.lines, cols, exportName(`PO_${id}`, 'csv'))}><Download className="h-3.5 w-3.5" />Export</Btn>
      </>}>
      {error ? <ErrorBox message={error} onRetry={refetch} /> : loading || !data ? <div className="space-y-3"><Skeleton className="h-16" /><Skeleton className="h-40" /></div> : <>
        <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
          <Stat label="PO value" value={fmtCr(data.ordered_cr, { decimals: 2 })} />
          <Stat label="Delivered" value={fmtCr(data.delivered_cr, { decimals: 2 })} sub={`${fmtPct(data.delivered_pct)} of value`} />
          <Stat label="Still to deliver" value={fmtCr(data.outstanding_cr, { decimals: 2 })} />
          <Stat label="Consumed on site" value={fmtCr(data.consumed_cr, { decimals: 2 })} sub="MB51, this PO" />
        </div>
        <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 text-[13px] md:grid-cols-3">
          <div><dt className="text-fg-tertiary">Status</dt><dd><StatusPill tone={STATUS_TONE[data.status]}>{STATUS_LABEL[data.status]}</StatusPill></dd></div>
          <div><dt className="text-fg-tertiary">PO date</dt><dd className="text-fg-primary">{fmtDate(data.date)}</dd></div>
          <div><dt className="text-fg-tertiary">Buyer</dt><dd className="text-fg-primary">{data.buyer ?? '—'}</dd></div>
          <div className="col-span-2"><dt className="text-fg-tertiary">Vendor</dt><dd>{data.vendor ? <button type="button" onClick={() => openVendor(data.vendor!)} className="text-primary-700 hover:underline">{data.vendor}</button> : <span className="text-fg-tertiary">(no vendor recorded)</span>}</dd></div>
          <div><dt className="text-fg-tertiary">Projects</dt><dd className="text-fg-primary">{data.projects.length ? data.projects.map(formatProjectName).join(', ') : '—'}</dd></div>
        </dl>
        <div className="mt-3"><NotAvailable what="Expected delivery" why="ZSPS carries no delivery date on any line, so timeline and lateness cannot be shown." /></div>
        <Section title={`Lines (${data.lines.length})`}>
          <div className="overflow-x-auto rounded-md border border-border-subtle">
            <table className="w-full text-[12.5px]">
              <thead><tr className="bg-surface-sunken text-left text-[11px] text-fg-tertiary"><th className="px-2 py-1.5">Material</th><th className="px-2 py-1.5">Status</th><th className="px-2 py-1.5 text-right">Qty</th><th className="px-2 py-1.5 text-right">Value</th><th className="px-2 py-1.5 text-right">Delivered</th></tr></thead>
              <tbody className="divide-y divide-border-subtle">
                {data.lines.map(l => (<tr key={l.id}>
                  <td className="max-w-[260px] px-2 py-1.5"><div className="truncate text-fg-primary" title={l.material ?? ''}>{l.material ?? l.short_text ?? '—'}</div>{l.material_code && <button type="button" onClick={() => openMaterial(l.material_code!)} className="font-mono text-[11px] text-primary-700 hover:underline">{l.material_code}</button>}</td>
                  <td className="px-2 py-1.5"><StatusPill tone={STATUS_TONE[l.status]}>{STATUS_LABEL[l.status]}</StatusPill></td>
                  <td className="px-2 py-1.5 text-right tabular-nums text-fg-secondary">{l.qty == null ? '—' : fmtNum(Math.round(l.qty))}{l.delivered_qty ? <span className="text-fg-tertiary"> / {fmtNum(Math.round(l.delivered_qty))}</span> : null}</td>
                  <td className="px-2 py-1.5 text-right tabular-nums">{fmtCr(l.ordered_cr, { decimals: 2 })}</td>
                  <td className="px-2 py-1.5 text-right tabular-nums text-fg-secondary">{fmtCr(l.delivered_cr, { decimals: 2 })}</td>
                </tr>))}
              </tbody>
            </table>
          </div>
        </Section>
      </>}
    </Drawer>
  );
};

/* ── Vendor ── */
const VendorDrawer = ({ id, onClose, depth, canGoBack }: { id: string; onClose: () => void; depth: number; canGoBack: boolean }) => {
  const { data, loading, error, refetch } = useVendor(id);
  const openPO = useSAPStore(s => s.openPO); const openMaterial = useSAPStore(s => s.openMaterial); const setFilters = useSAPStore(s => s.setFilters);
  return (
    <Drawer open onClose={onClose} depth={depth} canGoBack={canGoBack} eyebrow="Vendor" title={id} width="xl"
      actions={data && <>
        <WatchBtn kind="vendor" id={id} label={id} />
        <Btn onClick={() => { setFilters({ vendor: id }); onClose(); }}><FileText className="h-3.5 w-3.5" />All POs in ledger</Btn>
        <Btn onClick={() => { setFilters({ vendor: id }); onClose(); }}><Package className="h-3.5 w-3.5" />Materials</Btn>
      </>}>
      {error ? <ErrorBox message={error} onRetry={refetch} /> : loading || !data ? <div className="space-y-3"><Skeleton className="h-16" /><Skeleton className="h-36" /><Skeleton className="h-36" /></div> : <>
        <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
          <Stat label="Total PO value" value={fmtCr(data.ordered_cr)} sub={`${fmtNum(data.pos)} POs · ${fmtNum(data.materials)} materials`} />
          <Stat label="Delivered" value={fmtCr(data.delivered_cr)} sub={`${fmtPct(data.delivered_pct)} of value`} />
          <Stat label="Still to deliver" value={fmtCr(data.outstanding_cr)} sub={`${fmtPct(100 - data.delivered_pct)} outstanding`} />
          <Stat label="Exposure" value={fmtPct(data.ordered_cr ? (data.outstanding_cr / data.ordered_cr) * 100 : 0, 0)} sub="outstanding ÷ ordered" />
        </div>
        <div className="mt-3 grid gap-2 md:grid-cols-2">
          <NotAvailable what="Average delivery time · delayed POs · risk score" why="delivery_date is null on every ZSPS row; no timing exists to score against." />
          <div className="rounded-md border border-border-subtle bg-surface-0 px-3 py-2 text-[12px] text-fg-secondary">Delivery %, exposure and PO count are measured from ZSPS. Nothing here is estimated.</div>
        </div>
        <Section title="PO value by quarter"><MiniBars series={data.trend} k="ordered_cr" label="PO value ordered" /></Section>
        <Section title="Top materials"><RowList icon={Package} onOpen={openMaterial} rows={data.top_materials.map(m => ({ key: m.code, label: m.name || m.code, sub: <span className="font-mono">{m.code}</span>, value: <>{fmtCr(m.ordered_cr)} <span className="text-fg-tertiary">· {fmtPct(m.ordered_cr ? (m.delivered_cr / m.ordered_cr) * 100 : 0, 0)} deliv.</span></> }))} /></Section>
        <Section title="Projects"><RowList rows={data.projects.slice(0, 8).map(p => ({ key: p.project, label: formatProjectName(p.project), value: fmtCr(p.ordered_cr) }))} /></Section>
        <Section title="Recent purchase orders"><RowList icon={FileText} onOpen={openPO} rows={data.recent_pos.map(p => ({ key: p.po, label: <span className="font-mono">{p.po}</span>, sub: `${fmtDate(p.date)} · ${p.lines} lines`, value: <>{fmtCr(p.ordered_cr, { decimals: 2 })} <span className="text-fg-tertiary">· {fmtPct(p.ordered_cr ? (p.delivered_cr / p.ordered_cr) * 100 : 0, 0)}</span></> }))} /></Section>
      </>}
    </Drawer>
  );
};

/* ── Material ── */
const MaterialDrawer = ({ id, onClose, depth, canGoBack }: { id: string; onClose: () => void; depth: number; canGoBack: boolean }) => {
  const { data, loading, error, refetch } = useMaterial(id);
  const openVendor = useSAPStore(s => s.openVendor); const setFilters = useSAPStore(s => s.setFilters);
  const { themeName, chrome, categorical } = useChartTheme();
  const cons = useMemo(() => data?.consumption ?? [], [data]);
  const consOpt = useMemo(() => ({
    grid: { left: 4, right: 4, top: 6, bottom: 18, containLabel: true },
    tooltip: { trigger: 'axis', backgroundColor: chrome.surface2, borderColor: chrome.borderSubtle, textStyle: { color: chrome.fgPrimary, fontSize: 12 }, valueFormatter: (v: number) => fmtCr(v, { decimals: 2 }) },
    xAxis: { type: 'category', data: cons.map(c => c.month), axisTick: { show: false }, axisLine: { lineStyle: { color: chrome.axisLine } }, axisLabel: { color: chrome.fgTertiary, fontSize: 10, hideOverlap: true } },
    yAxis: { type: 'value', axisLine: { show: false }, axisTick: { show: false }, splitLine: { lineStyle: { color: chrome.gridLine } }, axisLabel: { color: chrome.fgTertiary, fontSize: 10 } },
    series: [{ name: 'Consumed value', type: 'bar', data: cons.map(c => c.value_cr), barMaxWidth: 18, itemStyle: { color: categorical[0] } }],
  }), [cons, chrome, categorical]);
  const prices = useMemo(() => data?.unit_prices ?? [], [data]);
  const priceStats = useMemo(() => { if (prices.length < 2) return null; const v = prices.map(p => p.unit_price).sort((a, b) => a - b); const med = v[Math.floor(v.length / 2)]; return { min: v[0], max: v[v.length - 1], med, spread: med ? ((v[v.length - 1] - v[0]) / med) * 100 : 0 }; }, [prices]);
  return (
    <Drawer open onClose={onClose} depth={depth} canGoBack={canGoBack} eyebrow={<span className="font-mono">{id}</span>} title={data?.name ?? id} width="xl"
      actions={data && <>
        <WatchBtn kind="material" id={id} label={`${data.name} (${id})`} />
        <Btn onClick={() => { setFilters({ material: id }); onClose(); }}><FileText className="h-3.5 w-3.5" />POs in ledger</Btn>
      </>}>
      {error ? <ErrorBox message={error} onRetry={refetch} /> : loading || !data ? <div className="space-y-3"><Skeleton className="h-16" /><Skeleton className="h-36" /></div> : <>
        <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
          <Stat label="PO value" value={fmtCr(data.ordered_cr)} sub={`${fmtNum(data.pos)} POs · ${fmtNum(data.vendors)} suppliers`} />
          <Stat label="Delivered" value={fmtCr(data.delivered_cr)} sub={`${fmtPct(data.delivered_pct)}`} />
          <Stat label="Still to deliver" value={fmtCr(data.outstanding_cr)} />
          <Stat label="Inventory on hand" value={fmtNum(Math.round(data.inventory.qty))} sub={`${data.inventory.unit ?? 'units'} · ${fmtCr(data.inventory.value_cr)} · MB52`} />
        </div>
        <Section title="Consumption by month (MB51)">{cons.length ? <div className="h-[140px]" role="img" aria-label="Consumed value by month"><ReactECharts theme={themeName} option={consOpt} notMerge style={{ height: '100%', width: '100%' }} /></div> : <NotAvailable what="Consumption" why="No MB51 goods issues recorded for this material." />}</Section>
        <Section title="Unit price on PO lines" right={priceStats && <span className="text-[12px] text-fg-tertiary">{prices.length} lines</span>}>
          {priceStats ? <div className="grid grid-cols-3 gap-2"><Stat label="Lowest" value={`₹${fmtNum(Math.round(priceStats.min))}`} /><Stat label="Median" value={`₹${fmtNum(Math.round(priceStats.med))}`} /><Stat label="Spread" value={fmtPct(priceStats.spread, 0)} sub="(max − min) ÷ median" /></div> : <NotAvailable what="Price variance" why="Fewer than two priced lines." />}
          <p className="mt-1.5 text-[11px] text-fg-tertiary">Value ÷ ordered quantity per line. 42% of lines carry no date, so this is a spread, not a trend.</p>
        </Section>
        <Section title="Suppliers"><RowList icon={Building2} onOpen={openVendor} rows={data.suppliers.map(s => ({ key: s.name, label: s.name, sub: `${fmtNum(s.pos)} POs`, value: <>{fmtCr(s.ordered_cr)} <span className="text-fg-tertiary">· {fmtPct(s.ordered_cr ? (s.delivered_cr / s.ordered_cr) * 100 : 0, 0)}</span></> }))} /></Section>
        <Section title="Projects"><RowList rows={data.projects.slice(0, 8).map(p => ({ key: p.project, label: formatProjectName(p.project), value: fmtCr(p.ordered_cr) }))} /></Section>
      </>}
    </Drawer>
  );
};

/* ── Insight ── */
const InsightDrawer = ({ id, onClose, depth, canGoBack }: { id: string; onClose: () => void; depth: number; canGoBack: boolean }) => {
  const { insights } = useInsights();
  const i = insights.find(x => x.id === id) as Insight | undefined;
  const openVendor = useSAPStore(s => s.openVendor); const openMaterial = useSAPStore(s => s.openMaterial); const setFilters = useSAPStore(s => s.setFilters); const dismiss = useSAPStore(s => s.dismissInsight);
  const tone = i ? SEVERITY_TONE[i.severity] : 'neutral';
  return (
    <Drawer open onClose={onClose} depth={depth} canGoBack={canGoBack} eyebrow="Insight" title={i?.title ?? 'Insight'}
      actions={i && <>
        <WatchBtn kind="insight" id={i.id} label={i.title} />
        {i.affectedVendors[0] && <Btn onClick={() => openVendor(i.affectedVendors[0])}><Building2 className="h-3.5 w-3.5" />View vendor</Btn>}
        {i.affectedMaterials[0] && <Btn onClick={() => openMaterial(i.affectedMaterials[0])}><Package className="h-3.5 w-3.5" />View materials</Btn>}
        <Btn onClick={() => { setFilters({ vendor: i.affectedVendors[0] ?? null, material: i.affectedMaterials[0] ?? null }); onClose(); }}><FileText className="h-3.5 w-3.5" />View POs</Btn>
        <Btn variant="ghost" onClick={() => dismiss(i.id)} className="ml-auto"><Trash2 className="h-3.5 w-3.5" />Dismiss</Btn>
      </>}>
      {!i ? <div className="text-[13px] text-fg-tertiary">This insight no longer applies to the current filters, or was dismissed.</div> : <>
        <div className="flex flex-wrap items-center gap-2"><StatusPill tone={tone}>{i.severity}</StatusPill><span className="rounded bg-surface-sunken px-1.5 py-px text-[11px] text-fg-tertiary">{i.category}</span><span className="rounded bg-surface-sunken px-1.5 py-px text-[11px] text-fg-tertiary">Computed from SAP data</span></div>
        <Section title="What happened"><p className="text-[13px] leading-relaxed text-fg-primary">{i.summary}</p></Section>
        {i.aiNote && <Section title={<span className="inline-flex items-center gap-1.5"><Sparkles className="h-3.5 w-3.5 text-secondary-600" />Why it matters <span className="font-normal text-fg-tertiary">· AI note ({i.aiSource})</span></span>}><p className="rounded-md border border-status-ai-border bg-status-ai-bg px-3 py-2 text-[13px] leading-relaxed text-fg-primary">{i.aiNote}</p></Section>}
        {(i.currentValue != null || i.previousValue != null) && <Section title="Figures"><div className="grid grid-cols-2 gap-2"><Stat label={i.metric ?? 'Current'} value={typeof i.currentValue === 'number' ? fmtNum(Math.round(i.currentValue * 10) / 10) : '—'} />{i.previousValue != null && <Stat label="Previous" value={fmtNum(Math.round(i.previousValue * 10) / 10)} />}</div></Section>}
        {i.recommendation && <Section title="Recommended action"><p className="text-[13px] leading-relaxed text-fg-primary">{i.recommendation}</p></Section>}
        {i.affectedVendors.length > 0 && <Section title="Affected vendors"><RowList icon={Building2} onOpen={openVendor} rows={i.affectedVendors.map(v => ({ key: v, label: v, value: '' }))} /></Section>}
        {i.affectedMaterials.length > 0 && <Section title="Affected materials"><RowList icon={Package} onOpen={openMaterial} rows={i.affectedMaterials.map(m => ({ key: m, label: <span className="font-mono">{m}</span>, value: '' }))} /></Section>}
        <Section title="Evidence"><pre className="custom-scrollbar max-h-64 overflow-auto rounded-md border border-border-subtle bg-surface-0 p-3 text-[11px] leading-snug text-fg-secondary">{JSON.stringify(i.evidence, null, 2)}</pre></Section>
        <p className="mt-3 text-[11px] text-fg-tertiary">Source: {i.source === 'rules' ? 'rule engine over ZSPS / MB51 / MB52' : i.source} · generated {fmtDate(i.createdAt)}</p>
      </>}
    </Drawer>
  );
};

/* ── KPI drill-down ── */
const KPI_META: Record<KpiId, { title: string; what: string }> = {
  pos: { title: 'Purchase orders', what: 'Distinct PO numbers in scope, and how they split by line status.' },
  vendors: { title: 'Vendor exposure', what: 'Vendors ranked by PO value with delivered and outstanding shares.' },
  materials: { title: 'Material exposure', what: 'Coded materials ranked by PO value.' },
  inventory: { title: 'Inventory on hand', what: 'MB52 snapshot value by material.' },
  ordered: { title: 'PO amount', what: 'Ordered value, where it sits, and how it compares to the previous period.' },
  delivered: { title: 'Delivered value', what: 'ZSPS delivered value by vendor.' },
  outstanding: { title: 'Outstanding PO exposure', what: 'Still-to-deliver value by vendor — where the money is stuck.' },
  pct: { title: 'Delivery and consumption', what: 'Delivered ÷ ordered, with MB51 consumption alongside.' },
};

const KpiDrawer = ({ id, onClose, depth, canGoBack }: { id: KpiId; onClose: () => void; depth: number; canGoBack: boolean }) => {
  const ov = useOverview(); const k = ov.data?.kpis; const p = ov.data?.period;
  const vendors = useVendors(15); const mats = useMaterials(id === 'inventory' ? 'inventory' : 'value', 15);
  const openVendor = useSAPStore(s => s.openVendor); const openMaterial = useSAPStore(s => s.openMaterial); const setFilters = useSAPStore(s => s.setFilters);
  const meta = KPI_META[id];
  const showVendors = ['vendors', 'ordered', 'delivered', 'outstanding'].includes(id);
  const showMats = ['materials', 'inventory'].includes(id);
  const vRows = (vendors.data?.vendors ?? []).slice().sort((a, b) => id === 'outstanding' ? b.outstanding_cr - a.outstanding_cr : id === 'delivered' ? b.delivered_cr - a.delivered_cr : b.ordered_cr - a.ordered_cr);
  return (
    <Drawer open onClose={onClose} depth={depth} canGoBack={canGoBack} eyebrow="KPI" title={meta.title} width="xl"
      actions={<>{id === 'outstanding' && <Btn onClick={() => { setFilters({ status: 'pending' }); onClose(); }}><FileText className="h-3.5 w-3.5" />Pending lines in ledger</Btn>}{id === 'delivered' && <Btn onClick={() => { setFilters({ status: 'delivered' }); onClose(); }}><FileText className="h-3.5 w-3.5" />Delivered lines in ledger</Btn>}</>}>
      <p className="text-[13px] text-fg-secondary">{meta.what}</p>
      {k && p && (
        <div className="mt-3 grid grid-cols-2 gap-2 md:grid-cols-4">
          {id === 'pos' && <><Stat label="POs" value={fmtNum(k.pos)} sub={p.pos.pct != null ? `${p.pos.pct > 0 ? '+' : ''}${p.pos.pct}% vs prev. period` : undefined} /><Stat label="Lines" value={fmtNum(k.lines)} sub={`${fmtPct(p.dated_share, 0)} dated`} />{Object.entries(ov.data!.status_mix).map(([s, n]) => <Stat key={s} label={STATUS_LABEL[s as keyof typeof STATUS_LABEL]} value={fmtNum(n as number)} sub="lines" />)}</>}
          {id === 'ordered' && <><Stat label="Current period" value={fmtCr(p.ordered_cr.current)} sub={`${p.current[0]} → ${p.current[1]}`} /><Stat label="Previous period" value={fmtCr(p.ordered_cr.previous)} sub={`${p.previous[0]} → ${p.previous[1]}`} /><Stat label="Change" value={p.ordered_cr.pct == null ? '—' : `${p.ordered_cr.pct > 0 ? '+' : ''}${p.ordered_cr.pct}%`} sub={`on ${fmtPct(p.dated_share, 0)} dated lines`} /><Stat label="All in scope" value={fmtCr(k.ordered_cr)} /></>}
          {(id === 'delivered' || id === 'outstanding' || id === 'pct') && <><Stat label="Ordered" value={fmtCr(k.ordered_cr)} /><Stat label="Delivered" value={fmtCr(k.delivered_cr)} sub={fmtPct(k.delivered_pct)} /><Stat label="Still to deliver" value={fmtCr(k.outstanding_cr)} sub={fmtPct(100 - k.delivered_pct)} /><Stat label="Consumed on site" value={fmtCr(k.consumed_value_cr)} sub="MB51 · not subtracted" /></>}
          {id === 'inventory' && <><Stat label="Stock value" value={fmtCr(k.inventory_value_cr)} /><Stat label="Units" value={fmtNum(Math.round(k.inventory_qty))} sub="mixed units of measure" /></>}
          {id === 'vendors' && <><Stat label="Vendors" value={fmtNum(k.vendors)} sub={p.vendors.pct != null ? `${p.vendors.pct > 0 ? '+' : ''}${p.vendors.pct}% vs prev.` : undefined} /><Stat label="Top 5 share" value={fmtPct(vRows.slice(0, 5).reduce((a, v) => a + v.share_pct, 0), 0)} sub="of PO value" /></>}
          {id === 'materials' && <><Stat label="Coded materials" value={fmtNum(k.materials)} />{mats.data?.no_material_code && <Stat label="No material code" value={fmtCr(mats.data.no_material_code.ordered_cr)} sub={`${fmtNum(mats.data.no_material_code.pos)} POs`} />}</>}
        </div>)}
      {id === 'inventory' && <div className="mt-3"><NotAvailable what="Inventory trend" why="MB52 is a point-in-time snapshot with no history." /></div>}
      {showVendors && <Section title={id === 'outstanding' ? 'By vendor — outstanding' : 'By vendor'}>{vendors.loading && !vendors.data ? <Skeleton className="h-48" /> : <RowList icon={Building2} onOpen={openVendor} rows={vRows.map(v => ({ key: v.name, label: v.name, sub: `${fmtNum(v.pos)} POs · ${fmtPct(v.delivered_pct, 0)} delivered`, value: fmtCr(id === 'outstanding' ? v.outstanding_cr : id === 'delivered' ? v.delivered_cr : v.ordered_cr) }))} />}</Section>}
      {showMats && <Section title="By material">{mats.loading && !mats.data ? <Skeleton className="h-48" /> : <RowList icon={Package} onOpen={openMaterial} rows={(mats.data?.materials ?? []).map(m => ({ key: m.code, label: m.name, sub: <span className="font-mono">{m.code}</span>, value: fmtCr(id === 'inventory' ? m.inventory_value_cr : m.ordered_cr) }))} />}</Section>}
    </Drawer>
  );
};

/* ── Ask Akasha ── */
const SUGGESTED = ['Which vendors have the highest outstanding value?', 'Where is inventory building up?', 'What is our remaining PO exposure?', 'Which materials carry the most outstanding value?', 'Which vendors contribute most to procurement risk?', 'How much have we ordered versus delivered?'];

const AskDrawer = ({ onClose, depth, canGoBack }: { onClose: () => void; depth: number; canGoBack: boolean }) => {
  const filters = useSAPStore(s => s.filters);
  const ov = useOverview(); const vendors = useVendors(10); const mats = useMaterials('outstanding', 10); const { insights } = useInsights();
  const [msgs, setMsgs] = useState<{ role: 'user' | 'assistant'; content: string; error?: boolean }[]>([]);
  const [q, setQ] = useState(''); const [busy, setBusy] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { end.current?.scrollIntoView({ behavior: 'smooth' }); }, [msgs]);
  const context = useMemo(() => ({ filters, kpis: ov.data?.kpis, period: ov.data?.period, top_vendors: vendors.data?.vendors, top_outstanding_materials: mats.data?.materials, insights: insights.slice(0, 6).map(i => ({ title: i.title, summary: i.summary, severity: i.severity })), synced_at: ov.data?.synced_at }), [filters, ov.data, vendors.data, mats.data, insights]);
  const send = async (text: string) => {
    const question = text.trim(); if (!question || busy) return;
    setQ(''); setBusy(true);
    const hist = msgs.filter(m => !m.error);
    setMsgs(m => [...m, { role: 'user', content: question }]);
    try { const r = await sapApi.ask(question, context, hist); setMsgs(m => [...m, { role: 'assistant', content: r.answer || 'No answer returned.' }]); }
    catch (e: unknown) { setMsgs(m => [...m, { role: 'assistant', content: `The AI service is unavailable right now (${e instanceof Error ? e.message : 'no response'}). The figures on the page are still live.`, error: true }]); }
    finally { setBusy(false); }
  };
  return (
    <Drawer open onClose={onClose} depth={depth} canGoBack={canGoBack} eyebrow={<span className="inline-flex items-center gap-1.5"><Sparkles className="h-3.5 w-3.5 text-secondary-600" />Ask Akasha</span>} title="Questions over the current view"
      actions={<form className="flex w-full items-center gap-2" onSubmit={e => { e.preventDefault(); send(q); }}>
        <input data-autofocus value={q} onChange={e => setQ(e.target.value)} placeholder="Ask about the filtered SAP data…" aria-label="Question" disabled={busy}
          className="h-9 flex-1 rounded-md border border-border-default bg-surface-1 px-3 text-[13px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" />
        <Btn variant="primary" type="submit" disabled={busy || !q.trim()} aria-label="Send"><Send className="h-3.5 w-3.5" /></Btn>
      </form>}>
      <p className="text-[12px] text-fg-tertiary">Answers are grounded in what is on screen — current filters, KPIs, top vendors and materials, and the insights list. Nothing else is sent.</p>
      {msgs.length === 0 && <div className="mt-3 flex flex-wrap gap-1.5">{SUGGESTED.map(s => <button key={s} type="button" onClick={() => send(s)} className="rounded-full border border-border-default bg-surface-0 px-3 py-1 text-left text-[12.5px] text-fg-secondary hover:border-border-strong hover:text-fg-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">{s}</button>)}</div>}
      <div className="mt-3 space-y-3" aria-live="polite">
        {msgs.map((m, i) => (<div key={i} className={cx('max-w-[92%] rounded-md px-3 py-2 text-[13px] leading-relaxed', m.role === 'user' ? 'ml-auto bg-primary-50 text-fg-primary' : m.error ? 'border border-status-risk-border bg-status-risk-bg text-status-risk-fg' : 'border border-border-subtle bg-surface-0 text-fg-primary whitespace-pre-wrap')}>{m.content}</div>))}
        {busy && <div className="flex items-center gap-2 text-[12px] text-fg-tertiary"><span className="h-2 w-2 animate-pulse rounded-full bg-secondary-500" />Thinking…</div>}
        <div ref={end} />
      </div>
    </Drawer>
  );
};

/* ── Watchlist ── */
const WatchlistDrawer = ({ onClose, depth, canGoBack }: { onClose: () => void; depth: number; canGoBack: boolean }) => {
  const list = useSAPStore(s => s.watchlist); const remove = useSAPStore(s => s.removeWatch); const openDrawer = useSAPStore(s => s.openDrawer);
  const ICON: Record<WatchKind, React.ComponentType<{ className?: string }>> = { po: FileText, vendor: Building2, material: Package, insight: Lightbulb };
  return (
    <Drawer open onClose={onClose} depth={depth} canGoBack={canGoBack} eyebrow="Watchlist" title={`${list.length} tracked item${list.length === 1 ? '' : 's'}`}>
      {list.length === 0 ? <p className="text-[13px] text-fg-tertiary">Nothing tracked yet. Use “Track” on a PO, vendor, material or insight.</p> : (
        <ul className="divide-y divide-border-subtle rounded-md border border-border-subtle">
          {list.map(w => { const I = ICON[w.kind]; return (
            <li key={`${w.kind}:${w.id}`} className="flex items-center gap-3 px-3 py-2">
              <I className="h-3.5 w-3.5 shrink-0 text-fg-tertiary" />
              <button type="button" onClick={() => openDrawer({ kind: w.kind, id: w.id } as DrawerState)} className="min-w-0 flex-1 text-left hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded"><div className="truncate text-[13px] text-fg-primary">{w.label}</div><div className="text-[11px] text-fg-tertiary">{w.kind} · added {fmtDate(w.addedAt)}</div></button>
              <button type="button" onClick={() => remove(w.kind, w.id)} className="rounded p-1 text-fg-tertiary hover:text-status-critical-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" aria-label={`Stop tracking ${w.label}`}><Trash2 className="h-3.5 w-3.5" /></button>
            </li>); })}
        </ul>)}
      <p className="mt-3 text-[11px] text-fg-tertiary">Stored in this browser. <ExternalLink className="inline h-3 w-3" /> Shared or server-side watchlists are not part of the platform yet.</p>
    </Drawer>
  );
};

/* ── Filters (mobile / long tail) ── */
const FiltersDrawer = ({ onClose, depth }: { onClose: () => void; depth: number }) => {
  const clear = useSAPStore(s => s.clearFilters);
  return <Drawer open onClose={onClose} depth={depth} eyebrow="Filters" title="Refine the view" width="md" actions={<><Btn variant="ghost" onClick={clear}>Clear all</Btn><Btn variant="primary" className="ml-auto" onClick={onClose}>Done</Btn></>}><MoreFilters /></Drawer>;
};

/* ── Host: renders the stack ── */
export const DrawerHost = () => {
  const drawers = useSAPStore(s => s.drawers); const close = useSAPStore(s => s.closeDrawer);
  return <>{drawers.map((d, i) => {
    const p = { key: `${d.kind}:${'id' in d ? d.id : ''}:${i}`, onClose: close, depth: i, canGoBack: i > 0 };
    switch (d.kind) {
      case 'po': return <PODrawer {...p} id={d.id} />;
      case 'vendor': return <VendorDrawer {...p} id={d.id} />;
      case 'material': return <MaterialDrawer {...p} id={d.id} />;
      case 'insight': return <InsightDrawer {...p} id={d.id} />;
      case 'kpi': return <KpiDrawer {...p} id={d.id} />;
      case 'ask': return <AskDrawer {...p} />;
      case 'watchlist': return <WatchlistDrawer {...p} />;
      case 'filters': return <FiltersDrawer {...p} />;
      default: return null;
    }
  })}</>;
};
