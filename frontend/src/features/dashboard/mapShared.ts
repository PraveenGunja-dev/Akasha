import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

/* ═══════════════════════════════════════════════════════════════════════════
   MAP CHROME — shared by the Network Overview and the SAP location map.

   One basemap, one set of bounds, one control cluster, one fit-to-data
   behaviour. Two maps that look the same because they are built from the
   same parts, not because someone matched the CSS by hand.
   ═══════════════════════════════════════════════════════════════════════════ */

/* Two free, key-free Esri canvases. Grey rather than imagery: the data is
   the subject and the basemap is context. */
export const BASEMAP = {
  light: 'https://services.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}',
  dark: 'https://services.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}',
};

/* Everything we draw sits in western India, so the map is fenced to the
   subcontinent: no panning to the Atlantic, no zooming out to the globe. */
export const INDIA_BOUNDS = L.latLngBounds(L.latLng(6.5, 67.5), L.latLng(37.5, 97.5));

/** Quadratic bezier between two points, bowed perpendicular to the chord —
    how transmission schematics draw a corridor whose exact route is not the
    point. */
export function arc(a: [number, number], b: [number, number], bow = 0.16, steps = 32): [number, number][] {
  const [ay, ax] = a; const [by, bx] = b;
  const my = (ay + by) / 2; const mx = (ax + bx) / 2;
  const cy = my + (bx - ax) * bow; const cx = mx - (by - ay) * bow;
  const pts: [number, number][] = [];
  for (let i = 0; i <= steps; i++) {
    const t = i / steps; const k = 1 - t;
    pts.push([k * k * ay + 2 * k * t * cy + t * t * by, k * k * ax + 2 * k * t * cx + t * t * bx]);
  }
  return pts;
}

/** Catmull-Rom spline through surveyed points. A traced route is accurate
    but at 500px wide its vertices read as a scribble; passing a spline
    through them keeps every surveyed point on the line and rounds the
    turns between them. Nothing is moved — only interpolated. */
export function smooth(path: [number, number][], perSegment = 8): [number, number][] {
  if (path.length < 3) return path;
  const out: [number, number][] = [path[0]];
  for (let i = 0; i < path.length - 1; i++) {
    const p0 = path[Math.max(i - 1, 0)], p1 = path[i], p2 = path[i + 1], p3 = path[Math.min(i + 2, path.length - 1)];
    for (let s = 1; s <= perSegment; s++) {
      const t = s / perSegment, t2 = t * t, t3 = t2 * t;
      out.push([
        0.5 * (2 * p1[0] + (-p0[0] + p2[0]) * t + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2 + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3),
        0.5 * (2 * p1[1] + (-p0[1] + p2[1]) * t + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3),
      ]);
    }
  }
  return out;
}

/** Leaflet's default tooltip is a white speech bubble; this is the flat
    card the rest of the app uses. Injected once. */
export const MAP_TOOLTIP_CLASS = 'akasha-map-tip';
let styled = false;
export function ensureMapStyles() {
  if (styled || typeof document === 'undefined') return;
  styled = true;
  const el = document.createElement('style');
  el.textContent = `
    .${MAP_TOOLTIP_CLASS} { background: var(--surface-2); color: var(--fg-primary); border: 1px solid var(--border-subtle);
      border-radius: 6px; box-shadow: var(--elev-overlay); padding: 8px 10px; font: 12px/1.4 ui-sans-serif, system-ui; white-space: nowrap; }
    .${MAP_TOOLTIP_CLASS}::before { display: none; }
    .${MAP_TOOLTIP_CLASS} .k { color: var(--fg-secondary); margin-right: 14px; }
    .${MAP_TOOLTIP_CLASS} .v { font-variant-numeric: tabular-nums; float: right; }
    .${MAP_TOOLTIP_CLASS} .t { font-weight: 600; margin-bottom: 4px; }
    .leaflet-interactive:focus { outline: none; }
  `;
  document.head.appendChild(el);
}

