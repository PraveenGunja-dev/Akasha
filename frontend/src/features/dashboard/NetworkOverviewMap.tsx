import React, { useEffect, useMemo, useRef, useState } from 'react';
import ReactECharts from 'echarts-for-react';
import { Zap, Maximize2 } from 'lucide-react';
import { ChartFrame, SourceTag, cx } from '../../components/ui/primitives';
import { useChartTheme } from '../../lib/chartTheme';
import { statusMeta, STATUS_META } from '../analytics/transmission/gridHelpers';
import { findSubstationCoord } from '../analytics/transmission/gridCoords';
import type { TcEdge } from '../analytics/transmission/gridHelpers';
import { ensureIndiaMap, smoothPath } from './indiaMap';

/* ═══════════════════════════════════════════════════════════════════════════
   NETWORK OVERVIEW — the transmission grid on the same India outline the
   SAP location map uses.

   Two encodings, two questions: COLOUR is status (charged / in progress /
   under bidding), WIDTH is voltage class, and pending corridors are dashed.
   Surveyed routes (17 of 565 edges) pass through a spline so every surveyed
   point stays on the line and the turns are rounded; the rest are drawn as
   schematic arcs between their substations. One line per corridor, not per
   circuit — parallel circuits stacked identical lines on top of each other.

   Hover a corridor: it thickens and the rest fade. Click anything: open
   the full transmission map.
   ═══════════════════════════════════════════════════════════════════════════ */

const PENDING_DASH = [6, 6];
const BIDDING_DASH = [2, 5];

interface Corridor { id: string; from: string; to: string; voltage: string; kv: number; status: string; statusKey: string; color: string; width: number; traced: boolean; coords: [number, number][]; a: [number, number]; b: [number, number] }
interface Node { key: string; label: string; lng: number; lat: number; color: string; degree: number }

export default function NetworkOverviewMap({ onTabChange }: { onTabChange?: (tab: string) => void }) {
  const [edges, setEdges] = useState<TcEdge[]>([]);
  const [loading, setLoading] = useState(true);
  const [mapReady, setMapReady] = useState<true | string | false>(false);
  const { themeName, chrome, sequential } = useChartTheme();
  const host = useRef<HTMLDivElement>(null); const chart = useRef<ReactECharts>(null);

  useEffect(() => {
    let on = true;
    ensureIndiaMap().then(() => on && setMapReady(true)).catch((e: unknown) => on && setMapReady(e instanceof Error ? e.message : 'map outline failed'));
    Promise.all([
      fetch('/akasha/api/tc/rajasthan/network').then(r => (r.ok ? r.json() : null)),
      fetch('/akasha/api/tc/khavda/network').then(r => (r.ok ? r.json() : null)),
    ]).then(([rj, kh]) => { if (!on) return; setEdges([...(rj?.edges || []), ...(kh?.edges || [])] as TcEdge[]); setLoading(false); })
      .catch(() => { if (on) setLoading(false); });
    return () => { on = false; };
  }, []);
  useEffect(() => { if (!host.current) return; const ro = new ResizeObserver(() => chart.current?.getEchartsInstance().resize()); ro.observe(host.current); return () => ro.disconnect(); }, []);

  const { corridors, nodes, statuses } = useMemo(() => {
    const corridors: Corridor[] = []; const nodeMap = new Map<string, Node>(); const seen = new Set<string>(); const statuses = new Set<string>();
    edges.forEach(e => {
      /* Endpoints come from the traced route where one exists, otherwise from the substation table. */
      const path = (e.path && e.path.length >= 2) ? (e.path as [number, number][]) : null; // [lat, lng]
      const fromC = findSubstationCoord(e.from_label); const toC = findSubstationCoord(e.to_label);
      const a: [number, number] | null = path ? [path[0][1], path[0][0]] : (fromC ? [fromC.lng, fromC.lat] : null);
      const b: [number, number] | null = path ? [path[path.length - 1][1], path[path.length - 1][0]] : (toC ? [toC.lng, toC.lat] : null);
      if (!a || !b || (a[0] === b[0] && a[1] === b[1])) return;
      const key = [e.from_label, e.to_label].sort().join('|') + '|' + (e.voltage || '');
      if (seen.has(key)) return; seen.add(key);
      const st = statusMeta(e.normalized_status); if (e.normalized_status) statuses.add(e.normalized_status);
      const kv = parseInt(String(e.voltage || '').replace(/\D/g, ''), 10) || 0;
      const traced = !!path && path.length > 4;
      corridors.push({ id: e.id, from: String(e.from_label || ''), to: String(e.to_label || ''), voltage: e.voltage || '—', kv, status: st.label, statusKey: e.normalized_status || '', color: st.color,
        width: kv >= 765 ? 4 : kv >= 500 ? 3 : 2.2, traced, coords: traced ? smoothPath(path!.map(p => [p[1], p[0]] as [number, number])) : [a, b], a, b });
      ([[e.from, e.from_label, a], [e.to, e.to_label, b]] as const).forEach(([id, label, pos]) => {
        const k = String(id); const f = nodeMap.get(k);
        if (f) f.degree += 1; else nodeMap.set(k, { key: k, label: String(label || k), lng: pos[0], lat: pos[1], color: st.color, degree: 1 });
      });
    });
    return { corridors, nodes: [...nodeMap.values()], statuses: [...statuses] };
  }, [edges]);

  const labelled = useMemo(() => [...nodes].sort((a, b) => b.degree - a.degree).slice(0, 3).map(n => n.key), [nodes]);

  const option = useMemo(() => {
    const lineItem = (c: Corridor) => ({ name: `${c.from} → ${c.to}`, coords: c.coords, c, lineStyle: { color: c.color, width: c.width, type: c.statusKey === 'charged' ? 'solid' : c.statusKey === 'under_bidding' ? BIDDING_DASH : PENDING_DASH, opacity: 0.95, cap: 'round', join: 'round' } });
    const lineBase = { type: 'lines', coordinateSystem: 'geo', z: 2, silent: false, emphasis: { focus: 'self', blurScope: 'coordinateSystem', lineStyle: { width: 6, opacity: 1 } }, blur: { lineStyle: { opacity: 0.18 } } };
    return {
      animationDuration: 200,
      tooltip: { trigger: 'item', backgroundColor: chrome.surface2, borderColor: chrome.borderSubtle, borderWidth: 1, padding: [10, 14], textStyle: { color: chrome.fgPrimary, fontSize: 12 },
        formatter: (p: { seriesType?: string; data?: { c?: Corridor; n?: Node } }) => {
          const row = (l: string, v: string) => `<div style="display:flex;justify-content:space-between;gap:24px"><span style="color:${chrome.fgSecondary}">${l}</span><span style="font-variant-numeric:tabular-nums">${v}</span></div>`;
          if (p.seriesType === 'lines' && p.data?.c) { const c = p.data.c;
            return `<div style="font-weight:600;margin-bottom:6px">${c.from} → ${c.to}</div>` + row('Voltage', c.voltage) + row('Status', `<span style="color:${c.color}">${c.status}</span>`) + row('Route', c.traced ? 'surveyed' : 'schematic arc') + `<div style="margin-top:6px;color:${chrome.fgTertiary}">click to open the full map</div>`; }
          if (p.data?.n) { const n = p.data.n; return `<div style="font-weight:600;margin-bottom:6px">${n.label}</div>` + row('Corridors', String(n.degree)) + `<div style="margin-top:6px;color:${chrome.fgTertiary}">click to open the full map</div>`; }
          return '';
        } },
      geo: { map: 'india', roam: false, aspectScale: 0.9, layoutCenter: ['50%', '52%'], layoutSize: '112%', silent: true,
        itemStyle: { areaColor: chrome.surface1, borderColor: chrome.axisLine, borderWidth: 0.6 },
        regions: [{ name: 'Gujarat', itemStyle: { areaColor: sequential[1] } }, { name: 'Rajasthan', itemStyle: { areaColor: sequential[1] } }] },
      series: [
        { ...lineBase, name: 'traced', polyline: true, data: corridors.filter(c => c.traced).map(lineItem) },
        { ...lineBase, name: 'schematic', polyline: false, lineStyle: { curveness: 0.22 }, data: corridors.filter(c => !c.traced).map(lineItem) },
        {
          type: 'scatter', coordinateSystem: 'geo', z: 4, symbol: 'rect', symbolSize: 10,
          itemStyle: { color: '#fff', borderWidth: 2 },
          emphasis: { scale: 1.3 },
          label: { show: false },
          data: nodes.map(n => ({ name: n.label, value: [n.lng, n.lat], n, itemStyle: { borderColor: n.color },
            label: labelled.includes(n.key) ? { show: true, position: 'right', distance: 6, color: chrome.fgPrimary, fontSize: 10, fontWeight: 600, backgroundColor: 'rgba(255,255,255,.9)', padding: [2, 5], borderRadius: 4, formatter: n.label } : undefined })),
        },
      ],
    };
  }, [corridors, nodes, labelled, chrome, sequential]);

  const onEvents = useMemo(() => ({ click: () => onTabChange && onTabChange('transmission_data') }), [onTabChange]);

  const legend = <>
    {[['Charged', 'solid'], ['Pending', 'dashed']].map(([l, k]) => (
      <span key={l} className="flex items-center gap-1.5"><svg width="16" height="4"><line x1="0" y1="2" x2="16" y2="2" stroke="currentColor" strokeWidth={k === 'solid' ? 3 : 2} strokeDasharray={k === 'solid' ? undefined : '4 3'} strokeLinecap="round" /></svg>{l}</span>))}
    <span className="h-3 w-px bg-border" />
    {([['765 kV+', 4], ['500 kV', 3], ['400 kV', 2.2]] as const).map(([l, w]) => <span key={l} className="flex items-center gap-1.5"><span className="w-4 rounded-full bg-fg-tertiary" style={{ height: `${w}px` }} />{l}</span>)}
    <span className="h-3 w-px bg-border" />
    {statuses.map(k => { const m = STATUS_META[k] || statusMeta(k); return <span key={k} className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-[2px] border-2 bg-white" style={{ borderColor: m.color }} />{m.label}</span>; })}
  </>;

  return (
    <ChartFrame icon={Zap} eyebrow="Transmission" title="Network overview" className="h-full"
      right={<>
        {corridors.length > 0 && <span className="hidden text-[12px] text-fg-tertiary lg:inline">{corridors.length} corridors · colour = status, width = voltage</span>}
        <button type="button" onClick={() => onTabChange && onTabChange('transmission_data')} className="inline-flex h-7 items-center gap-1.5 rounded-md border border-border-default bg-surface-1 px-2.5 text-[12px] font-medium text-primary hover:bg-surface-sunken focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"><Maximize2 className="h-3.5 w-3.5" />Full map</button>
        <SourceTag system="TC" />
      </>}>
      <div ref={host} className="flex h-full w-full flex-col">
        <div className="mb-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] font-medium text-fg-secondary">{legend}</div>
        {typeof mapReady === 'string' ? <div className="text-[13px] text-status-critical-fg">Map outline could not be loaded ({mapReady}).</div>
          : loading || !mapReady ? <div className={cx('min-h-0 flex-1 animate-pulse rounded-md bg-surface-sunken')} aria-busy />
            : corridors.length === 0 ? <div className="flex flex-1 items-center justify-center text-[13px] text-fg-tertiary">No transmission corridors with coordinates.</div>
              : <div className="min-h-0 flex-1" role="img" aria-label={`Transmission network: ${corridors.length} corridors across ${nodes.length} substations`}>
                <ReactECharts ref={chart} theme={themeName} option={option} notMerge onEvents={onEvents} style={{ height: '100%', width: '100%' }} />
              </div>}
      </div>
    </ChartFrame>
  );
}
