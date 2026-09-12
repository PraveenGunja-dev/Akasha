import * as echarts from 'echarts';

/* One India outline, registered once, shared by the SAP location map and the
   Network Overview. 34 states, 128 KB, simplified to 0.02°, served from
   /public under the app base the same way adani.ttf is — no external
   network at runtime. A failed load resets so a retry can succeed. */

const GEO_URL = `${import.meta.env.BASE_URL}geo/india-states.json`;
let registered: Promise<void> | null = null;

export const ensureIndiaMap = (): Promise<void> => {
  if (!registered) {
    registered = fetch(GEO_URL)
      .then(r => { if (!r.ok) throw new Error(`${r.status} loading ${GEO_URL}`); return r.json(); })
      .then(g => { if (!g?.features?.length) throw new Error('GeoJSON has no features'); echarts.registerMap('india', g); })
      .catch(e => { registered = null; throw e; });
  }
  return registered;
};

/** Catmull-Rom spline through surveyed points: every point stays on the
    line, the turns between them are rounded. Nothing moves, only
    interpolates. Coordinates are [lng, lat] as ECharts expects. */
export function smoothPath(path: [number, number][], perSegment = 8): [number, number][] {
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
