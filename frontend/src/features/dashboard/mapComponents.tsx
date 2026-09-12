import React, { useEffect, useRef } from 'react';
import { useMap } from 'react-leaflet';
import L from 'leaflet';
import { Plus, Minus, Crosshair } from 'lucide-react';

/* Map components shared by the Network Overview and the SAP location map.
   Non-component helpers (basemap, bounds, curves, tooltip styles) live in
   mapShared.ts so this file exports only components (fast refresh). */

/** Frames the map on the geometry, once it exists. */
export function FitToData({ points, padding = 28 }: { points: [number, number][]; padding?: number }) {
  const map = useMap();
  useEffect(() => {
    if (points.length < 1) return;
    if (points.length === 1) { map.setView(points[0], 7, { animate: false }); return; }
    const b = L.latLngBounds(points.map((p) => L.latLng(p[0], p[1])));
    map.fitBounds(b, { padding: [padding, padding], animate: false });
  }, [points, map, padding]);
  return null;
}

/** Zoom in / out / reset. Lives inside the map because it needs the instance. */
export function MapControls() {
  const map = useMap();
  const home = useRef<L.LatLngBounds | null>(null);
  useEffect(() => { home.current = map.getBounds(); }, [map]);
  const btn = 'w-8 h-8 flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted rounded-md transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring';
  return (
    <div className="absolute right-3 top-3 z-[400] flex flex-col gap-1 rounded-lg border border-border bg-white p-1 shadow-sm dark:bg-card">
      <button type="button" className={btn} onClick={() => map.zoomIn()} title="Zoom in" aria-label="Zoom in"><Plus className="h-4 w-4" /></button>
      <div className="h-px w-full bg-border" />
      <button type="button" className={btn} onClick={() => map.zoomOut()} title="Zoom out" aria-label="Zoom out"><Minus className="h-4 w-4" /></button>
      <div className="h-px w-full bg-border" />
      <button type="button" className={btn} onClick={() => home.current && map.fitBounds(home.current, { padding: [28, 28] })} title="Reset view" aria-label="Reset view"><Crosshair className="h-4 w-4" /></button>
    </div>
  );
}

/** Card shell: header with icon, legend row, then the map. */
export const MapCard = ({ icon: Icon, title, subtitle, legend, children, right }: {
  icon: React.ComponentType<{ className?: string }>; title: React.ReactNode; subtitle?: React.ReactNode; legend?: React.ReactNode; right?: React.ReactNode; children: React.ReactNode;
}) => (
  <div className="flex h-full w-full flex-col overflow-hidden rounded-xl border border-border bg-card shadow-sm">
    <div className="flex shrink-0 items-start gap-3 bg-card p-4 pb-2">
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-blue-100 bg-blue-50 dark:border-blue-800/30 dark:bg-blue-900/20">
        <Icon className="h-5 w-5 text-blue-600 dark:text-blue-400" />
      </div>
      <div className="min-w-0 flex-1">
        <h3 className="text-base font-bold text-foreground">{title}</h3>
        {subtitle && <p className="text-xs text-muted-foreground">{subtitle}</p>}
      </div>
      {right && <div className="flex shrink-0 items-center gap-2">{right}</div>}
    </div>
    {legend && <div className="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 pb-2 text-[10px] font-medium text-fg-secondary">{legend}</div>}
    <div className="relative m-4 mt-0 flex-1 overflow-hidden rounded-xl border border-border/50 bg-[#f8f9fa] dark:bg-[#1a1b1e]">
      {children}
    </div>
  </div>
);
