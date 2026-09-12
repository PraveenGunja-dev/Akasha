import React, { useState, useEffect, useMemo } from 'react';
import { MapContainer, TileLayer, Polyline, Marker, Tooltip } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { Loader2, Zap, Maximize2 } from 'lucide-react';
import { BASEMAP, INDIA_BOUNDS, arc, smooth, MAP_TOOLTIP_CLASS, ensureMapStyles } from './mapShared';
import { FitToData, MapControls } from './mapComponents';
import { statusMeta, STATUS_META } from '../analytics/transmission/gridHelpers';
import { findSubstationCoord } from '../analytics/transmission/gridCoords';
import type { TcEdge } from '../analytics/transmission/gridHelpers';
import { useChartTheme } from '../../lib/chartTheme';

/* ═══════════════════════════════════════════════════════════════════════════
   NETWORK OVERVIEW — transmission mini-map

   Three things make a grid map readable at this size:

   1. FIT THE DATA. A fixed centre/zoom was showing Afghanistan and Pakistan
      around a network that lives in western India. The view is computed from
      the line geometry itself, so the map is always as tight as the data.

   2. CURVE THE LINES. The traced routes are surveyed polylines — accurate,
      and at 500px wide they read as jagged scribble. Each line is redrawn as
      a smooth arc between its endpoints, which is how transmission schematics
      are normally drawn. The true route stays available on the full map.

   3. SEPARATE THE ENCODINGS. Colour carries VOLTAGE; line STYLE carries
      state — solid where the line is charged, dashed where it is still
      pending. One colour doing both jobs is what made the old version
      unreadable: a red line could mean 400kV or delayed, and you could not
      tell which. Two channels, two questions, both answerable from the line
      itself rather than from its endpoints.
   ═══════════════════════════════════════════════════════════════════════════ */

/* Voltage classes, in descending capacity. Distinct hues, none of them the
   status reds/greens, so a line colour is never mistaken for a state. */
const VOLTAGE_COLORS: { test: RegExp; label: string; color: string }[] = [
  { test: /800/, label: '800 kV', color: '#ec4899' },
  { test: /765/, label: '765 kV', color: '#a855f7' },
  { test: /500/, label: '500 kV', color: '#3b82f6' },
  { test: /400/, label: '400 kV', color: '#f59e0b' },
  { test: /220/, label: '220 kV', color: '#22c55e' },
  { test: /132/, label: '132 kV', color: '#ef4444' },
];
const OTHER_VOLTAGE = { label: 'Other', color: '#64748b' };

const voltageOf = (v?: string) => {
  const s = String(v || '');
  return VOLTAGE_COLORS.find((c) => c.test.test(s)) || OTHER_VOLTAGE;
};

const squareIcon = (color: string, onDark: boolean) =>
  L.divIcon({
    className: '',
    iconSize: [11, 11],
    iconAnchor: [5.5, 5.5],
    html: `<div style="width:11px;height:11px;border:2px solid ${onDark ? '#fff' : color};
      background:${onDark ? color : '#fff'};border-radius:2px;
      box-shadow:0 0 0 1px rgba(0,0,0,.25), 0 1px 3px rgba(0,0,0,.35)"></div>`,
  });

export default function TransmissionMiniMap({ onTabChange }: { onTabChange?: (tab: string) => void }) {
  const [edges, setEdges] = useState<TcEdge[]>([]);
  const [loading, setLoading] = useState(true);

  const { themeName } = useChartTheme();
  const isDark = themeName === 'dark';
  const [hover, setHover] = useState<string | null>(null);
  useEffect(() => { ensureMapStyles(); }, []);

  useEffect(() => {
    let mounted = true;
    Promise.all([
      fetch('/akasha/api/tc/rajasthan/network').then((r) => (r.ok ? r.json() : null)),
      fetch('/akasha/api/tc/khavda/network').then((r) => (r.ok ? r.json() : null)),
    ])
      .then(([rj, kh]) => {
        if (!mounted) return;
        const all = [...(rj?.edges || []), ...(kh?.edges || [])] as TcEdge[];
        setEdges(all);
        setLoading(false);
      })
      .catch(() => { if (mounted) setLoading(false); });
    return () => { mounted = false; };
  }, []);

  /* Arcs, substations and the framing bounds, derived once. */
  const { lines, nodes, points, statuses } = useMemo(() => {
    const lines: { id: string; pts: [number, number][]; color: string; weight: number; label: string; dash?: string; charged: boolean; traced: boolean; voltage: string; status: string; from: string; to: string }[] = [];
    const nodeMap = new Map<string, { pos: [number, number]; label: string; color: string; degree: number }>();
    const points: [number, number][] = [];
    const voltages = new Set<string>();
    const statuses = new Set<string>();

    /* One arc per CORRIDOR, not per circuit. 565 edges run between 52
       substations — many are parallel circuits on the same route, and drawing
       each one stacks identical arcs on top of each other. */
    const seen = new Set<string>();

    edges.forEach((e) => {
      /* Endpoints come from the traced route where one exists (17 edges), and
         otherwise from the substation coordinate table. Without this fallback
         the map showed 17 of 565 lines. */
      const path = (e.path && e.path.length >= 2) ? (e.path as [number, number][]) : null;
      const fromC = findSubstationCoord(e.from_label);
      const toC = findSubstationCoord(e.to_label);
      const a: [number, number] | null = path ? path[0] : (fromC ? [fromC.lat, fromC.lng] : null);
      const b: [number, number] | null = path ? path[path.length - 1] : (toC ? [toC.lat, toC.lng] : null);
      if (!a || !b) return;                       // no coordinates, nothing to draw
      if (a[0] === b[0] && a[1] === b[1]) return; // same site: a dot, not a line

      const corridor = [e.from_label, e.to_label].sort().join('|') + '|' + (e.voltage || '');
      if (seen.has(corridor)) return;
      seen.add(corridor);

      const v = voltageOf(e.voltage);
      voltages.add(v.label);
      const kv = parseInt(String(e.voltage || '').replace(/\D/g, ''), 10) || 0;
      const st = statusMeta(e.normalized_status);
      if (e.normalized_status) statuses.add(e.normalized_status);
      /* statusMeta already carries the dash pattern for each state: charged
         has none, in-progress and under-bidding each have their own. */
      const charged = e.normalized_status === 'charged';
      const statusLabel = st.label;
      lines.push({
        voltage: v.label, status: statusLabel, from: String(e.from_label || ''), to: String(e.to_label || ''),
        id: e.id, pts: path && path.length > 4 ? smooth(path) : arc(a, b),
        /* Colour = status, weight = voltage class. */
        color: st.color,
        weight: kv >= 765 ? 4.5 : kv >= 500 ? 3.5 : 2.5,
        label: `${e.from_label} → ${e.to_label}`,
        dash: st.dash, charged, traced: !!path,
      });
      points.push(a, b);
      ([[e.from, e.from_label, a], [e.to, e.to_label, b]] as const).forEach(([id, label, pos]) => {
        const key = String(id);
        const found = nodeMap.get(key);
        if (found) found.degree += 1;
        else nodeMap.set(key, { pos: pos as [number, number], label: String(label || key), color: st.color, degree: 1 });
      });
    });

    return { lines, nodes: Array.from(nodeMap.values()), points, voltages: Array.from(voltages), statuses: Array.from(statuses) };
  }, [edges]);

  /* Only hubs get a name. Labelling every substation is what turned the old
     map into overlapping text. */
  const labelled = useMemo(
    () => [...nodes].sort((a, b) => b.degree - a.degree).slice(0, 3),
    [nodes]
  );

  if (loading) {
    return (
      <div className="flex min-h-[400px] flex-1 flex-col items-center justify-center gap-2 rounded-xl border border-border bg-card text-muted-foreground shadow-sm">
        <Loader2 className="h-5 w-5 animate-spin" />
        <span className="text-sm font-medium">Loading grid network…</span>
      </div>
    );
  }

  /* Two free, key-free Esri basemaps.

     Satellite is the default because this network is sparse: 47 corridors
     over two states leaves a lot of empty canvas, and on a flat grey fill
     that emptiness is all you see. Imagery gives the gap something to be —
     Kutch salt flats, the Aravallis, the coastline — so the map reads as a
     place with a grid on it rather than as a mostly-blank panel. The lines
     are then lifted off it with a dark scrim and a glow. */
  const baseLayerUrl = isDark ? BASEMAP.dark : BASEMAP.light;

  return (
    <div className="flex h-full w-full flex-col overflow-hidden rounded-xl border border-border bg-card shadow-sm">
      {/* HEADER */}
      <div className="flex shrink-0 items-start gap-3 bg-card p-4">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-blue-100 bg-blue-50 dark:border-blue-800/30 dark:bg-blue-900/20">
          <Zap className="h-5 w-5 text-blue-600 dark:text-blue-400" />
        </div>
        <div className="min-w-0">
          <h3 className="text-base font-bold text-foreground">Network Overview</h3>
          <p className="text-xs text-muted-foreground">
            {lines.length} corridors · colour = status, weight = voltage, solid = charged · hover for detail
          </p>
        </div>
      </div>

      {/* Legend sits under the header, not over the map. */}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 pb-2 text-[10px] font-medium text-fg-secondary">
          <span className="flex items-center gap-1.5">
            <svg width="16" height="4"><line x1="0" y1="2" x2="16" y2="2" stroke="currentColor" strokeWidth="3" strokeLinecap="round" /></svg>
            Charged
          </span>
          <span className="flex items-center gap-1.5">
            <svg width="16" height="4"><line x1="0" y1="2" x2="16" y2="2" stroke="currentColor" strokeWidth="2" strokeDasharray="4 3" strokeLinecap="round" /></svg>
            Pending
          </span>
          <span className="h-3 w-px bg-border" />
          {[['765 kV+', 4.5], ['500 kV', 3.5], ['400 kV', 2.5]].map(([label, w]) => (
            <span key={String(label)} className="flex items-center gap-1.5">
              <span className="w-4 rounded-full bg-fg-tertiary" style={{ height: `${w}px` }} />
              {label}
            </span>
          ))}
          <span className="h-3 w-px bg-border" />
          {statuses.map((k) => {
            const m = STATUS_META[k] || statusMeta(k);
            return (
              <span key={k} className="flex items-center gap-1.5">
                <span className="h-2.5 w-2.5 rounded-[2px] border-2 bg-white" style={{ borderColor: m.color }} />
                {m.label}
              </span>
            );
          })}
        </div>


      {/* MAP */}
      <div className="relative m-4 mt-0 flex-1 overflow-hidden rounded-xl border border-border/50 bg-[#f8f9fa] dark:bg-[#1a1b1e]">
        <div className={`map-clean absolute inset-0 [&_.leaflet-container]:!bg-transparent [&_.leaflet-container]:!font-sans`}>
          <MapContainer
            center={[23.5, 78]}
            zoom={5}
            minZoom={4}
            maxZoom={11}
            maxBounds={INDIA_BOUNDS}
            maxBoundsViscosity={1}
            zoomControl={false}
            scrollWheelZoom={false}
            doubleClickZoom={false}
            dragging
            style={{ height: '100%', width: '100%', background: 'transparent' }}
          >
            <TileLayer key={baseLayerUrl} url={baseLayerUrl} attribution="Esri" />
            <FitToData points={points} />
            <MapControls />

            {lines.map((l) => {
              const hot = hover === l.id;
              const dim = hover !== null && !hot;
              return (
                <React.Fragment key={l.id}>
                  {/* Soft halo keeps a line legible where it crosses another;
                      on hover it becomes the line's own colour — a glow. */}
                  <Polyline
                    positions={l.pts}
                    pathOptions={{ color: hot ? l.color : '#fff', weight: l.weight + (hot ? 9 : 5), opacity: hot ? 0.28 : dim ? 0.35 : 0.85, lineCap: 'round', lineJoin: 'round' }}
                  />
                  <Polyline
                    positions={l.pts}
                    pathOptions={{ color: l.color, weight: hot ? l.weight + 1.5 : l.weight, opacity: dim ? 0.3 : 1, dashArray: l.dash, lineCap: 'round', lineJoin: 'round' }}
                    eventHandlers={{
                      mouseover: () => setHover(l.id),
                      mouseout: () => setHover((h) => (h === l.id ? null : h)),
                      click: () => onTabChange && onTabChange('transmission_data'),
                    }}
                  >
                    <Tooltip className={MAP_TOOLTIP_CLASS} sticky direction="top" offset={[0, -8]}>
                      <div className="t">{l.from} → {l.to}</div>
                      <div><span className="k">Voltage</span><span className="v">{l.voltage}</span></div>
                      <div><span className="k">Status</span><span className="v" style={{ color: l.color }}>{l.status}</span></div>
                      <div><span className="k">Route</span><span className="v">{l.traced ? 'surveyed' : 'schematic arc'}</span></div>
                      <div style={{ marginTop: 4, color: 'var(--fg-tertiary)' }}>click to open the full map</div>
                    </Tooltip>
                  </Polyline>
                </React.Fragment>
              );
            })}

            {nodes.map((n, i) => (
              <Marker key={i} position={n.pos} icon={squareIcon(n.color, false)} eventHandlers={{ click: () => onTabChange && onTabChange('transmission_data') }}>
                <Tooltip className={MAP_TOOLTIP_CLASS} direction="top" offset={[0, -8]}>
                  <div className="t">{n.label}</div>
                  <div><span className="k">Corridors</span><span className="v">{n.degree}</span></div>
                </Tooltip>
              </Marker>
            ))}

            {labelled.map((n, i) => (
              <Marker
                key={`lbl-${i}`}
                position={n.pos}
                interactive={false}
                icon={L.divIcon({
                  className: '',
                  iconSize: [0, 0],
                  iconAnchor: [-9, 6],
                  html: `<span style="white-space:nowrap;font:600 10px/1 ui-sans-serif,system-ui;
                          color:#334155;
                          background:rgba(255,255,255,.9);
                          padding:2px 5px;border-radius:4px;
                          box-shadow:0 1px 3px rgba(0,0,0,.3)">${n.label}</span>`,
                })}
              />
            ))}
          </MapContainer>
        </div>

        <button
          onClick={() => onTabChange && onTabChange('transmission_data')}
          className="pointer-events-auto absolute right-3 top-14 z-[400] flex items-center gap-2 rounded-lg border border-border bg-white/95 px-3 py-1.5 text-[11px] font-semibold text-primary shadow-sm backdrop-blur-sm transition-colors hover:bg-slate-50 dark:bg-card/95"
        >
          <Maximize2 className="h-3.5 w-3.5" />
          View Full Map
        </button>
      </div>
    </div>
  );
}
