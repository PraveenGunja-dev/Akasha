import React, { useState, useEffect, useMemo, useRef } from 'react';
import { MapContainer, TileLayer, Marker, Polyline, Popup, Tooltip, CircleMarker, useMap } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import L from 'leaflet';
import { motion, AnimatePresence } from 'framer-motion';
import {
  RefreshCw, Search, X, ChevronDown, ChevronRight, Zap, MapPin, Layers,
  AlertTriangle, CheckCircle2, Clock, Loader2, Database, Calendar, Package,
} from 'lucide-react';
import {
  type TcEdge, statusMeta, voltageWeight, parseStageProgress, edgeCompletionPct, parseLengthKm,
} from './transmission/gridHelpers';
import { findSubstationCoord, SOURCE_LABEL, type SubstationCoord } from './transmission/gridCoords';

interface NetworkPayload {
  nodes: any[];
  edges: TcEdge[];
}

const EMPTY_NETWORK: NetworkPayload = { nodes: [], edges: [] };

// Carto retired the /rastertiles/positron path (404s), which left the map as a blank
// grey panel. These are the current styles, all verified reachable without a key.
// `dark` marks a surface the routes must glow against rather than be outlined on.
const BASE_LAYERS = {
  light: {
    label: 'Light',
    url: 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
    subdomains: 'abcd', dark: false,
  },
  streets: {
    label: 'Streets',
    url: 'https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png',
    subdomains: 'abcd', dark: false,
  },
  satellite: {
    label: 'Satellite',
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    subdomains: '', dark: true,
  },
  dark: {
    label: 'Dark',
    url: 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
    subdomains: 'abcd', dark: true,
  },
} as const;

type BaseLayerKey = keyof typeof BASE_LAYERS;

// Marker size tracks voltage class so the 765 kV pooling stations read as hubs.
function markerRadius(kv?: number): number {
  if (!kv) return 11;
  if (kv >= 765) return 20;
  if (kv >= 400) return 16;
  if (kv >= 220) return 13;
  return 11;
}

function substationIcon(sub: SubstationCoord, highlighted: boolean, colocatedLinks: number) {
  const size = markerRadius(sub.kv);
  const c = size / 2;
  const fill = highlighted ? '#f59e0b' : '#6366f1';
  // A dashed ring flags a coordinate we could not confidently place.
  const dash = sub.source === 'approx' ? 'stroke-dasharray="2 2"' : '';
  // An outer ring marks a campus carrying links that begin and end on the same site.
  const campusRing = colocatedLinks > 0
    ? `<circle cx="${c}" cy="${c}" r="${c * 0.86}" fill="none" stroke="${fill}" stroke-width="1.25" stroke-opacity="0.85" />`
    : '';
  return new L.DivIcon({
    // A tight core with a faint halo. The earlier halo was wide and opaque enough that
    // clustered stations merged into one blob at national zoom.
    html: `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" style="overflow:visible">
      <circle cx="${c}" cy="${c}" r="${c * 0.9}" fill="${fill}" fill-opacity="0.10" />
      ${campusRing}
      <circle cx="${c}" cy="${c}" r="${c * 0.42}" fill="${fill}" stroke="#fff" stroke-width="1.5" ${dash}
        style="filter:drop-shadow(0 1px 1.5px rgba(0,0,0,0.3))" />
    </svg>`,
    className: 'tc-substation-dot',
    iconSize: [size, size],
    iconAnchor: [c, c],
  });
}

/** Reports zoom and viewport so styling can add detail as the reader moves in. */
function MapWatcher({ onChange }: { onChange: (view: { zoom: number; bounds: L.LatLngBounds }) => void }) {
  const map = useMap();
  useEffect(() => {
    const report = () => onChange({ zoom: map.getZoom(), bounds: map.getBounds() });
    report();
    map.on('zoomend moveend', report);
    return () => { map.off('zoomend moveend', report); };
  }, [map, onChange]);
  return null;
}

/** Tower positions along traced routes, drawn only when zoomed in far enough to read them.
 *  Vertices are clipped to the viewport and thinned to a fixed budget - a traced corridor
 *  can carry 1,500 points, and drawing every one of them costs far more than it shows. */
function TowerVertices({
  edges, bounds, isDark,
}: {
  edges: { edge: TcEdge }[];
  bounds: L.LatLngBounds;
  isDark: boolean;
}) {
  const points = useMemo(() => {
    const visible: [number, number][] = [];
    for (const { edge } of edges) {
      if (!edge.path) continue;
      for (const point of edge.path) {
        if (bounds.contains(point as [number, number])) visible.push(point);
      }
    }
    const BUDGET = 900;
    const stride = Math.ceil(visible.length / BUDGET) || 1;
    return visible.filter((_, i) => i % stride === 0);
  }, [edges, bounds]);

  return (
    <>
      {points.map((point, i) => (
        <CircleMarker
          key={i}
          center={point}
          radius={1.6}
          interactive={false}
          pathOptions={{
            color: isDark ? '#ffffff' : '#334155',
            weight: 0,
            fillOpacity: isDark ? 0.55 : 0.4,
            fillColor: isDark ? '#ffffff' : '#334155',
          }}
        />
      ))}
    </>
  );
}

// Detail thresholds. At national zoom the map is a portfolio overview and anything
// more than the routes themselves is noise; moving in earns labels, then towers.
const ZOOM_LABELS = 7;   // station names become permanent
const ZOOM_VERTICES = 9; // tower positions along traced routes appear

/** Line weight grows with zoom so routes stay hairline-fine when zoomed out.
 *  Weights are deliberately thin - a luminous 1.5px trace reads as infrastructure,
 *  a 5px one reads as a diagram. */
function zoomWeight(base: number, zoom: number) {
  const thin = base * 0.55;
  if (zoom <= 5) return Math.max(1, thin - 0.5);
  if (zoom <= 7) return Math.max(1.2, thin);
  if (zoom >= 11) return thin + 1.4;
  if (zoom >= 9) return thin + 0.7;
  return thin + 0.3;
}

// The portfolio reaches from Kutch to Varanasi to north Karnataka, but the working
// area is Gujarat and Rajasthan. Panning is fenced to the subcontinent so the map can
// never drift out over Arabia or China, which is what made it read as mostly empty.
const INDIA_BOUNDS: [[number, number], [number, number]] = [[6.0, 66.0], [36.5, 90.0]];
const DEFAULT_CENTER: [number, number] = [23.2, 73.0];

/** Frames the visible network, and re-frames it whenever the filters change.
 *  Keyed on the filter rather than on `points` so panning is never yanked back, but
 *  tracked with a ref so the first fit still happens once the network finishes loading. */
function FitToPoints({ points, fitKey }: { points: [number, number][]; fitKey: string }) {
  const map = useMap();
  const fittedKeyRef = useRef<string | null>(null);
  useEffect(() => {
    if (points.length === 0 || fittedKeyRef.current === fitKey) return;
    fittedKeyRef.current = fitKey;
    map.fitBounds(points, { padding: [50, 50], maxZoom: 8 });
  }, [fitKey, points, map]);
  return null;
}

// How firmly the ingest tied an OSM alignment to the edge - see ingest_line_geometry.py.
const ROUTE_CONFIDENCE: Record<string, string> = {
  high: 'Traced route',
  medium: 'Traced route (multi-segment)',
  low: 'Likely route, unverified',
};

const REGION_FILTERS = ['all', 'Rajasthan', 'Khavda'] as const;
const STATUS_FILTERS = ['all', 'charged', 'in_progress', 'under_bidding'] as const;

export default function TransmissionDataViewer({ dashboardData }: { dashboardData?: any }) {
  const [rajasthanNetwork, setRajasthanNetwork] = useState<NetworkPayload>(EMPTY_NETWORK);
  const [khavdaNetwork, setKhavdaNetwork] = useState<NetworkPayload>(EMPTY_NETWORK);
  const [khavdaProjectsRaw, setKhavdaProjectsRaw] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [regionFilter, setRegionFilter] = useState<typeof REGION_FILTERS[number]>('all');
  const [statusFilter, setStatusFilter] = useState<typeof STATUS_FILTERS[number]>('all');
  const [mapSearch, setMapSearch] = useState('');

  const [tableSearch, setTableSearch] = useState('');
  const [selectedProject, setSelectedProject] = useState<any | null>(null);
  const [debugOpen, setDebugOpen] = useState(false);
  const [hoveredEdgeId, setHoveredEdgeId] = useState<string | null>(null);
  const [legendOpen, setLegendOpen] = useState(false);
  const [view, setView] = useState<{ zoom: number; bounds: L.LatLngBounds | null }>({ zoom: 5, bounds: null });
  const zoom = view.zoom;

  const [baseLayer, setBaseLayer] = useState<BaseLayerKey>('light');
  const [layersOpen, setLayersOpen] = useState(false);
  const [overlays, setOverlays] = useState({
    substations: true,
    labels: true,
    towers: true,
    straight: true,
  });
  const base = BASE_LAYERS[baseLayer];
  const isDark = base.dark;

  const fetchTransmissionData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [rajRes, khnRes, khpRes] = await Promise.all([
        fetch('/akasha/api/tc/rajasthan/network').then(r => r.json()).catch(e => ({ error: e.message })),
        fetch('/akasha/api/tc/khavda/network').then(r => r.json()).catch(e => ({ error: e.message })),
        fetch('/akasha/api/tc/khavda/projects').then(r => r.json()).catch(e => ({ error: e.message })),
      ]);
      setRajasthanNetwork(rajRes?.edges ? rajRes : EMPTY_NETWORK);
      setKhavdaNetwork(khnRes?.edges ? khnRes : EMPTY_NETWORK);
      setKhavdaProjectsRaw(khpRes);
    } catch (err: any) {
      setError(err.message || 'Error fetching transmission data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchTransmissionData(); }, []);

  const allEdges = useMemo(
    () => [...rajasthanNetwork.edges, ...khavdaNetwork.edges],
    [rajasthanNetwork, khavdaNetwork]
  );

  const stats = useMemo(() => {
    const total = allEdges.length;
    const charged = allEdges.filter(e => e.normalized_status === 'charged').length;
    const inProgress = allEdges.filter(e => e.normalized_status === 'in_progress').length;
    const underBidding = allEdges.filter(e => e.normalized_status === 'under_bidding').length;
    const totalLengthKm = allEdges.reduce((sum, e) => sum + parseLengthKm(e.length), 0);
    const avgCompletion = total > 0
      ? Math.round(allEdges.reduce((sum, e) => sum + edgeCompletionPct(e), 0) / total)
      : 0;
    return { total, charged, inProgress, underBidding, totalLengthKm, avgCompletion };
  }, [allEdges]);

  const filteredEdges = useMemo(() => {
    return allEdges.filter(e => {
      if (regionFilter !== 'all' && e.region !== regionFilter) return false;
      if (statusFilter !== 'all' && e.normalized_status !== statusFilter) return false;
      return true;
    });
  }, [allEdges, regionFilter, statusFilter]);

  type LocatedEdge = { edge: TcEdge; from: SubstationCoord; to: SubstationCoord };

  // Edges whose endpoints share a campus (HVDC terminal at a pooling station, a LILO tap,
  // a GIS bay) have zero length on the map. Drawing them would render nothing at all, so
  // they are pulled out and reported on the substation marker instead.
  const { geoEdges, colocatedEdges, unmappedCount } = useMemo(() => {
    const located = filteredEdges
      .map(e => ({ edge: e, from: findSubstationCoord(e.from_label), to: findSubstationCoord(e.to_label) }))
      .filter(x => x.from && x.to) as LocatedEdge[];
    const drawable: LocatedEdge[] = [];
    const sameSite: LocatedEdge[] = [];
    for (const item of located) {
      (item.from.lat === item.to.lat && item.from.lng === item.to.lng ? sameSite : drawable).push(item);
    }
    return {
      geoEdges: drawable,
      colocatedEdges: sameSite,
      unmappedCount: filteredEdges.length - located.length,
    };
  }, [filteredEdges]);

  const tracedCount = useMemo(
    () => geoEdges.filter(({ edge }) => (edge.path?.length ?? 0) >= 2).length,
    [geoEdges]
  );

  // substation name -> the co-located links terminating there
  const colocatedBySite = useMemo(() => {
    const map = new Map<string, TcEdge[]>();
    colocatedEdges.forEach(({ edge, from }) => {
      const list = map.get(from.name) ?? [];
      list.push(edge);
      map.set(from.name, list);
    });
    return map;
  }, [colocatedEdges]);

  const substationMarkers = useMemo(() => {
    const map = new Map<string, SubstationCoord>();
    [...geoEdges, ...colocatedEdges].forEach(({ from, to }) => {
      map.set(from.name, from);
      map.set(to.name, to);
    });
    return Array.from(map.values());
  }, [geoEdges, colocatedEdges]);

  const fitPoints = useMemo<[number, number][]>(
    () => substationMarkers.map(s => [s.lat, s.lng]),
    [substationMarkers]
  );

  const searchMatch = useMemo(() => {
    if (!mapSearch.trim()) return null;
    const q = mapSearch.toLowerCase();
    return substationMarkers.find(s => s.name.toLowerCase().includes(q)) || null;
  }, [mapSearch, substationMarkers]);

  const projects: any[] = dashboardData?.projects || [];
  const filteredProjects = useMemo(() => {
    if (!tableSearch.trim()) return projects;
    const q = tableSearch.toLowerCase();
    return projects.filter(p =>
      (p.project_name || '').toLowerCase().includes(q) ||
      (p.p6_project_name || '').toLowerCase().includes(q)
    );
  }, [projects, tableSearch]);

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-700">
      {/* Header */}
      <div className="flex justify-between items-center bg-card/60 border border-border p-6 rounded-2xl backdrop-blur-xl">
        <div>
          <h2 className="text-2xl font-light tracking-wide text-foreground">Transmission Grid</h2>
          <p className="text-sm text-muted-foreground mt-1">
            Live substation network &amp; line status across Rajasthan and Khavda corridors
          </p>
        </div>
        <button
          onClick={fetchTransmissionData}
          className="flex items-center gap-2 px-4 py-2 bg-primary/10 text-primary border border-primary/30 rounded-full hover:bg-primary/20 transition-colors disabled:opacity-60"
          disabled={loading}
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          {loading ? 'Refreshing...' : 'Refresh Data'}
        </button>
      </div>

      {error && (
        <div className="p-4 bg-destructive/10 text-destructive border border-destructive/20 rounded-xl">
          {error}
        </div>
      )}

      {/* Stat Cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-4">
        <StatTile label="Total Lines" value={stats.total} icon={<Zap className="w-4 h-4" />} tone="primary" />
        <StatTile label="Charged" value={stats.charged} icon={<CheckCircle2 className="w-4 h-4" />} tone="success" />
        <StatTile label="In Progress" value={stats.inProgress} icon={<Clock className="w-4 h-4" />} tone="warning" />
        <StatTile label="Under Bidding" value={stats.underBidding} icon={<AlertTriangle className="w-4 h-4" />} tone="destructive" />
        <StatTile label="Route Length" value={`${Math.round(stats.totalLengthKm).toLocaleString()} km`} icon={<MapPin className="w-4 h-4" />} tone="muted" />
        <StatTile label="Avg. Completion" value={`${stats.avgCompletion}%`} icon={<Database className="w-4 h-4" />} tone="muted" />
      </div>

      {/* Map */}
      <div className="glass-panel rounded-2xl overflow-hidden shadow-lg border border-border relative">
        <div className="absolute top-4 left-4 z-[1000] flex flex-wrap gap-2">
          {REGION_FILTERS.map(r => (
            <FilterChip key={r} active={regionFilter === r} onClick={() => setRegionFilter(r)}>
              {r === 'all' ? 'All Regions' : r}
            </FilterChip>
          ))}
          <div className="w-px bg-border mx-1" />
          {STATUS_FILTERS.map(s => (
            <FilterChip key={s} active={statusFilter === s} onClick={() => setStatusFilter(s)} dotColor={s !== 'all' ? statusMeta(s).color : undefined}>
              {s === 'all' ? 'All Statuses' : statusMeta(s).label}
            </FilterChip>
          ))}
        </div>

        <div className="absolute top-4 right-4 z-[1000] w-64 space-y-2">
          <div className="flex items-center gap-1.5">
            <div className="flex items-center flex-1 bg-card border border-border shadow-lg rounded-lg overflow-hidden">
              <div className="pl-3 py-2 text-muted-foreground"><Search className="w-4 h-4" /></div>
              <input
                type="text"
                placeholder="Find substation..."
                className="w-full bg-transparent border-none px-2 py-2 text-sm text-foreground focus:outline-none placeholder:text-muted-foreground"
                value={mapSearch}
                onChange={(e) => setMapSearch(e.target.value)}
              />
            </div>
            <button
              onClick={() => setLayersOpen(o => !o)}
              title="Layers"
              className={`shrink-0 p-2 rounded-lg border shadow-lg transition-colors ${
                layersOpen ? 'bg-primary text-primary-foreground border-primary' : 'bg-card text-muted-foreground border-border hover:bg-muted'
              }`}
            >
              <Layers className="w-4 h-4" />
            </button>
          </div>

          {layersOpen && (
            <div className="bg-card/95 backdrop-blur-sm border border-border rounded-xl shadow-lg overflow-hidden">
              <div className="px-3 pt-2.5 pb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                Base map
              </div>
              <div className="grid grid-cols-2 gap-1.5 px-3 pb-2.5">
                {(Object.keys(BASE_LAYERS) as BaseLayerKey[]).map(key => (
                  <button
                    key={key}
                    onClick={() => setBaseLayer(key)}
                    className={`px-2 py-1.5 rounded-lg text-[11px] font-medium border transition-colors ${
                      baseLayer === key
                        ? 'bg-primary text-primary-foreground border-primary'
                        : 'bg-background text-foreground border-border hover:bg-muted'
                    }`}
                  >
                    {BASE_LAYERS[key].label}
                  </button>
                ))}
              </div>

              <div className="px-3 pt-2 pb-1 border-t border-border/50 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                Overlays
              </div>
              <div className="px-3 pb-2.5 space-y-0.5">
                {([
                  ['substations', 'Substations'],
                  ['labels', `Station labels (zoom ${ZOOM_LABELS}+)`],
                  ['towers', `Tower points (zoom ${ZOOM_VERTICES}+)`],
                  ['straight', 'Untraced straight lines'],
                ] as const).map(([key, label]) => (
                  <label key={key} className="flex items-center gap-2 py-0.5 cursor-pointer text-[11px] text-muted-foreground hover:text-foreground transition-colors">
                    <input
                      type="checkbox"
                      checked={overlays[key]}
                      onChange={() => setOverlays(o => ({ ...o, [key]: !o[key] }))}
                      className="accent-primary w-3.5 h-3.5"
                    />
                    {label}
                  </label>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Legend. Status is always visible; the full key stays folded away so the map
            is not competing with a wall of text at a glance. */}
        <div className="absolute bottom-4 left-4 z-[1000] bg-card/95 backdrop-blur-sm border border-border rounded-xl shadow-lg text-[11px] w-[188px] overflow-hidden">
          <div className="px-3 pt-2.5 pb-2 flex items-center gap-x-3 gap-y-1 flex-wrap">
            {(['charged', 'in_progress', 'under_bidding'] as const).map(s => {
              const meta = statusMeta(s);
              return (
                <div key={s} className="flex items-center gap-1.5">
                  <span style={{ width: 14, height: 3, background: meta.color, borderRadius: 2 }} />
                  <span className="text-muted-foreground">{meta.label}</span>
                </div>
              );
            })}
          </div>

          {geoEdges.length > 0 && (
            <div className="px-3 pb-2 text-[10px] text-muted-foreground">
              {tracedCount} of {geoEdges.length} routes traced
            </div>
          )}

          <button
            onClick={() => setLegendOpen(o => !o)}
            className="w-full flex items-center justify-between px-3 py-1.5 border-t border-border/50 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground hover:bg-muted transition-colors"
          >
            Full key
            <ChevronDown className={`w-3 h-3 transition-transform ${legendOpen ? 'rotate-180' : ''}`} />
          </button>

          {legendOpen && (
            <div className="px-3 pb-2.5 pt-1.5 border-t border-border/50 space-y-2">
              <div>
                <div className="font-semibold text-foreground uppercase tracking-wider mb-1 text-[10px]">Substation</div>
                {([[765, '765 kV'], [400, '400 kV'], [220, '≤ 220 kV']] as const).map(([kv, label]) => (
                  <div key={kv} className="flex items-center gap-2 py-0.5">
                    <span className="inline-flex w-[18px] justify-center">
                      <span className="rounded-full bg-[#6366f1] border border-white"
                        style={{ width: markerRadius(kv) * 0.45, height: markerRadius(kv) * 0.45 }} />
                    </span>
                    <span className="text-muted-foreground">{label}</span>
                  </div>
                ))}
                <div className="flex items-center gap-2 py-0.5">
                  <span className="inline-flex w-[18px] justify-center">
                    <span className="w-2 h-2 rounded-full border-[1.5px] border-dashed border-[#6366f1]" />
                  </span>
                  <span className="text-muted-foreground">Approximate area</span>
                </div>
                <div className="flex items-center gap-2 py-0.5">
                  <span className="inline-flex w-[18px] justify-center">
                    <span className="w-3 h-3 rounded-full border border-[#6366f1] flex items-center justify-center">
                      <span className="w-1 h-1 rounded-full bg-[#6366f1]" />
                    </span>
                  </span>
                  <span className="text-muted-foreground">In-campus links</span>
                </div>
              </div>

              <div>
                <div className="font-semibold text-foreground uppercase tracking-wider mb-1 text-[10px]">Route</div>
                <div className="flex items-center gap-2 py-0.5">
                  <span style={{ width: 18, height: 3, background: 'hsl(var(--muted-foreground))', borderRadius: 2 }} />
                  <span className="text-muted-foreground">Traced alignment</span>
                </div>
                <div className="flex items-center gap-2 py-0.5">
                  <span style={{ width: 18, height: 2, background: 'hsl(var(--muted-foreground))', borderRadius: 2, opacity: 0.45 }} />
                  <span className="text-muted-foreground">Straight-line only</span>
                </div>
              </div>

              {(unmappedCount > 0 || colocatedEdges.length > 0) && (
                <div className="pt-1.5 border-t border-border/50 text-[10px] text-muted-foreground space-y-0.5">
                  {colocatedEdges.length > 0 && <div>{colocatedEdges.length} in-campus link{colocatedEdges.length === 1 ? '' : 's'} shown on the substation</div>}
                  {unmappedCount > 0 && <div>{unmappedCount} line{unmappedCount === 1 ? '' : 's'} without coordinates</div>}
                </div>
              )}
            </div>
          )}
        </div>

        <div className="h-[560px] w-full [&_.leaflet-container]:!font-sans">
          <MapContainer
            center={DEFAULT_CENTER}
            zoom={6}
            minZoom={5}
            maxBounds={INDIA_BOUNDS}
            maxBoundsViscosity={1}
            scrollWheelZoom={true}
            style={{ height: '100%', width: '100%' }}
            attributionControl={false}
          >
            <TileLayer key={baseLayer} url={base.url} subdomains={base.subdomains || undefined} />
            <FitToPoints points={fitPoints} fitKey={`${regionFilter}|${statusFilter}`} />
            <MapWatcher onChange={setView} />
            {overlays.towers && view.bounds && zoom >= ZOOM_VERTICES && (
              <TowerVertices edges={geoEdges} bounds={view.bounds} isDark={isDark} />
            )}

            {geoEdges
              .filter(({ edge }) => overlays.straight || (edge.path?.length ?? 0) >= 2)
              .map(({ edge, from, to }) => {
              const meta = statusMeta(edge.normalized_status);
              const pct = edgeCompletionPct(edge);
              const weight = zoomWeight(voltageWeight(edge.voltage), zoom);
              const hovered = hoveredEdgeId === edge.id;
              // A traced route follows the real alignment; without one we can only draw the
              // straight chord, so it is rendered fainter to read as an approximation.
              const traced = (edge.path?.length ?? 0) >= 2;
              const positions: [number, number][] = traced
                ? edge.path!
                : [[from.lat, from.lng], [to.lat, to.lng]];
              const dashArray = traced ? meta.dash : '3, 7';
              // A low-confidence trace is a plausible alignment rather than a verified one,
              // so it sits visually between a confirmed route and a bare straight line.
              const routeOpacity = !traced ? 0.45 : edge.path_confidence === 'low' ? 0.7 : 0.9;
              return (
                <React.Fragment key={edge.id}>
                  {/* A wide, faint stroke in the line's own colour. On the dark surface this
                      reads as the route glowing rather than as an outline drawn around it. */}
                  <Polyline
                    positions={positions}
                    interactive={false}
                    pathOptions={{
                      color: isDark ? meta.color : '#ffffff',
                      weight: weight + (isDark ? 6 : 3.5),
                      opacity: isDark ? (hovered ? 0.3 : 0.16) : hovered ? 0.9 : 0.55,
                      lineCap: 'round',
                      lineJoin: 'round',
                    }}
                  />
                <Polyline
                  positions={positions}
                  eventHandlers={{
                    mouseover: () => setHoveredEdgeId(edge.id),
                    mouseout: () => setHoveredEdgeId(null),
                  }}
                  pathOptions={{
                    color: meta.color,
                    weight: hovered ? weight + 1.5 : traced ? weight : weight - 0.5,
                    opacity: hovered ? 1 : routeOpacity,
                    dashArray,
                    lineCap: 'round',
                    lineJoin: 'round',
                    className: dashArray ? 'tc-line-flow' : undefined,
                  }}
                >
                  <Popup>
                    <div className="min-w-[220px]">
                      <h3 className="font-bold text-sm text-foreground border-b pb-1 mb-2">
                        {edge.from_label} &harr; {edge.to_label}
                      </h3>
                      <div className="text-xs text-foreground grid grid-cols-2 gap-y-1 gap-x-3 mb-2">
                        <div><span className="text-muted-foreground">Region</span><br /><span className="font-semibold">{edge.region}</span></div>
                        <div><span className="text-muted-foreground">Voltage</span><br /><span className="font-semibold">{edge.voltage || '—'}</span></div>
                        <div><span className="text-muted-foreground">Length</span><br /><span className="font-semibold">{edge.length || '—'} km</span></div>
                        <div><span className="text-muted-foreground">Expected</span><br /><span className="font-semibold">{edge.expected_date || '—'}</span></div>
                        {edge.contractor && <div className="col-span-2"><span className="text-muted-foreground">Contractor</span><br /><span className="font-semibold">{edge.contractor}</span></div>}
                        <div className="col-span-2">
                          <span className="text-muted-foreground">Route</span><br />
                          <span className="font-semibold">
                            {traced
                              ? `${ROUTE_CONFIDENCE[edge.path_confidence ?? 'high']} · ${edge.path!.length} pts${edge.path_length_km ? ` · ${Math.round(edge.path_length_km)} km` : ''}`
                              : 'Straight-line approximation'}
                          </span>
                        </div>
                      </div>
                      <div className="flex items-center justify-between text-[10px] font-bold uppercase tracking-wider mb-1" style={{ color: meta.color }}>
                        <span>{meta.label}</span><span>{pct}%</span>
                      </div>
                      <div className="w-full h-1.5 bg-muted rounded-full overflow-hidden">
                        <div className="h-full rounded-full" style={{ width: `${pct}%`, background: meta.color }} />
                      </div>
                      {edge.projects?.length > 0 && (
                        <div className="mt-2 pt-2 border-t flex flex-wrap gap-1">
                          {edge.projects.map((p, i) => (
                            <span key={i} className="text-[10px] px-1.5 py-0.5 bg-primary/10 text-primary rounded font-medium">{p}</span>
                          ))}
                        </div>
                      )}
                    </div>
                  </Popup>
                </Polyline>
                </React.Fragment>
              );
            })}

            {(overlays.substations ? substationMarkers : []).map(sub => {
              const sameSite = colocatedBySite.get(sub.name) ?? [];
              return (
                <Marker
                  key={sub.name}
                  position={[sub.lat, sub.lng]}
                  icon={substationIcon(sub, sub.name === searchMatch?.name, sameSite.length)}
                  zIndexOffset={sub.kv && sub.kv >= 765 ? 100 : 0}
                >
                  <Tooltip
                    direction="top"
                    offset={[0, -8]}
                    opacity={1}
                    className="tc-substation-label"
                    permanent={overlays.labels && zoom >= ZOOM_LABELS}
                  >
                    {sub.name}{sub.kv ? ` · ${sub.kv} kV` : ''}
                  </Tooltip>
                  <Popup>
                    <div className="text-xs min-w-[200px]">
                      <div className="font-bold text-sm text-foreground mb-1">{sub.name}</div>
                      <div className="grid grid-cols-2 gap-x-3 gap-y-1 mb-2">
                        <div><span className="text-muted-foreground">Voltage</span><br /><span className="font-semibold">{sub.kv ? `${sub.kv} kV` : '—'}</span></div>
                        <div><span className="text-muted-foreground">Position</span><br /><span className="font-semibold font-mono">{sub.lat.toFixed(4)}, {sub.lng.toFixed(4)}</span></div>
                      </div>
                      <div className={`text-[10px] font-semibold uppercase tracking-wider ${sub.source === 'approx' ? 'text-warning' : 'text-muted-foreground'}`}>
                        {SOURCE_LABEL[sub.source]}
                      </div>
                      {sameSite.length > 0 && (
                        <div className="mt-2 pt-2 border-t">
                          <div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground mb-1">
                            {sameSite.length} link{sameSite.length === 1 ? '' : 's'} within this campus
                          </div>
                          <div className="space-y-0.5 max-h-28 overflow-y-auto">
                            {sameSite.map(link => {
                              const meta = statusMeta(link.normalized_status);
                              return (
                                <div key={link.id} className="flex items-center justify-between gap-2">
                                  <span className="text-[10px] text-foreground truncate">{link.from_label} &harr; {link.to_label}</span>
                                  <span className="text-[9px] font-bold uppercase shrink-0" style={{ color: meta.color }}>{link.voltage || meta.label}</span>
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      )}
                    </div>
                  </Popup>
                </Marker>
              );
            })}
          </MapContainer>
        </div>
      </div>

      {/* Project Mapping Table */}
      <div>
        <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-primary to-secondary flex items-center justify-center shadow-sm">
              <h3 className="text-white font-bold text-lg">M</h3>
            </div>
            <h2 className="text-xl font-medium text-foreground tracking-wide">Project &harr; Transmission Mapping</h2>
          </div>
          <div className="flex items-center bg-card border border-border rounded-lg overflow-hidden w-64">
            <div className="pl-3 py-1.5 text-muted-foreground"><Search className="w-4 h-4" /></div>
            <input
              type="text"
              placeholder="Search project..."
              className="w-full bg-transparent border-none px-2 py-1.5 text-sm text-foreground focus:outline-none placeholder:text-muted-foreground"
              value={tableSearch}
              onChange={(e) => setTableSearch(e.target.value)}
            />
          </div>
        </div>

        <div className="bg-card rounded-2xl overflow-hidden shadow-lg border border-border">
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="bg-muted text-muted-foreground uppercase tracking-widest text-[10px] font-bold border-b border-border">
                <tr>
                  <th className="px-6 py-4">Project Name</th>
                  <th className="px-6 py-4">Capacity</th>
                  <th className="px-6 py-4">P6 Schedule</th>
                  <th className="px-6 py-4">SAP Inventory</th>
                  <th className="px-6 py-4">Transmission Lines</th>
                  <th className="px-6 py-4" />
                </tr>
              </thead>
              <tbody className="divide-y divide-border/30">
                {filteredProjects.length === 0 && (
                  <tr><td colSpan={6} className="px-6 py-10 text-center text-muted-foreground italic">
                    {projects.length === 0 ? 'No project mapping data available.' : 'No projects match your search.'}
                  </td></tr>
                )}
                {filteredProjects.map((proj: any, idx: number) => (
                  <tr
                    key={proj.mapping_id ?? idx}
                    className="hover:bg-muted transition-colors cursor-pointer"
                    onClick={() => setSelectedProject(proj)}
                  >
                    <td className="px-6 py-4 font-medium text-foreground">{proj.project_name || proj.p6_project_name || 'Unknown'}</td>
                    <td className="px-6 py-4 text-muted-foreground">{proj.capacity_mwac ? `${proj.capacity_mwac} MW` : '—'}</td>
                    <td className="px-6 py-4">
                      <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold ${
                        proj.p6?.health === 'On Track' ? 'bg-success/10 text-success' :
                        proj.p6?.health === 'Delayed' ? 'bg-destructive/10 text-destructive' : 'bg-muted text-muted-foreground'
                      }`}>
                        {proj.p6?.health || 'N/A'}
                      </span>
                    </td>
                    <td className="px-6 py-4 font-mono">{proj.sap?.inv_qty ?? 0}</td>
                    <td className="px-6 py-4">
                      <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium border ${
                        proj.tc?.has_data ? 'border-purple-500/30 text-purple-600 bg-purple-500/5' : 'border-border text-muted-foreground'
                      }`}>
                        {proj.tc?.status || '0 Edges'}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-right">
                      <ChevronRight className="w-4 h-4 text-muted-foreground" />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Detail Drawer */}
      <AnimatePresence>
        {selectedProject && (
          <>
            <motion.div
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              className="fixed inset-0 bg-black/40 backdrop-blur-sm z-[2000]"
              onClick={() => setSelectedProject(null)}
            />
            <motion.div
              initial={{ x: 420, opacity: 0 }} animate={{ x: 0, opacity: 1 }} exit={{ x: 420, opacity: 0 }}
              transition={{ type: 'spring', bounce: 0.1, duration: 0.4 }}
              className="fixed right-4 top-4 bottom-4 w-[26rem] max-w-[90vw] bg-background border border-border rounded-2xl shadow-2xl flex flex-col z-[2001] overflow-hidden"
            >
              <div className="p-5 border-b border-border bg-muted flex items-start justify-between">
                <div>
                  <h3 className="text-base font-bold text-foreground leading-tight">
                    {selectedProject.project_name || selectedProject.p6_project_name}
                  </h3>
                  <p className="text-xs text-muted-foreground mt-1">{selectedProject.capacity_mwac ? `${selectedProject.capacity_mwac} MW` : ''}</p>
                </div>
                <button onClick={() => setSelectedProject(null)} className="p-1.5 rounded-md hover:bg-muted text-muted-foreground transition-colors">
                  <X className="w-4 h-4" />
                </button>
              </div>

              <div className="flex-1 overflow-y-auto custom-scrollbar">
                {selectedProject.p6 && (
                  <DetailSection icon={<Calendar className="w-4 h-4" />} title="P6 Schedule" color="#3B82F6">
                    <DetailRow label="Health" value={selectedProject.p6.health || 'N/A'} />
                    <DetailRow label="Progress" value={`${selectedProject.p6.progress ?? 0}%`} />
                    <DetailRow label="Start Date" value={selectedProject.p6.start_date || '—'} />
                    <DetailRow label="Finish Date" value={selectedProject.p6.finish_date || '—'} />
                  </DetailSection>
                )}

                {selectedProject.sap && (
                  <DetailSection icon={<Package className="w-4 h-4" />} title="SAP Material" color="#F59E0B">
                    <div className="grid grid-cols-2 gap-2">
                      <MiniStat label="Required" value={selectedProject.sap.req_qty ?? 0} />
                      <MiniStat label="Inventory" value={selectedProject.sap.inv_qty ?? 0} />
                      <MiniStat label="In Transit" value={selectedProject.sap.it_qty ?? 0} />
                      <MiniStat label="PO Qty" value={selectedProject.sap.po_qty ?? 0} />
                    </div>
                  </DetailSection>
                )}

                <DetailSection icon={<Zap className="w-4 h-4" />} title="Transmission Linkage" color="#8B5CF6">
                  {!selectedProject.tc?.has_data ? (
                    <p className="text-xs text-muted-foreground italic">No transmission lines linked to this project yet.</p>
                  ) : (
                    <div className="space-y-3">
                      {['khavda', 'rajasthan'].map(region => {
                        const lines = selectedProject.tc.data?.[region] || [];
                        if (lines.length === 0) return null;
                        return (
                          <div key={region}>
                            <div className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-1.5">
                              {region} ({lines.length})
                            </div>
                            <div className="space-y-1.5">
                              {lines.map((line: any, i: number) => {
                                const meta = statusMeta((line.status || '').toLowerCase().includes('charg') ? 'charged' : undefined);
                                return (
                                  <div key={i} className="flex items-center justify-between px-2.5 py-1.5 bg-muted rounded-lg border border-border text-xs">
                                    <span className="text-foreground truncate pr-2">{line.voltage || 'Line'}</span>
                                    <span className="text-[10px] font-bold uppercase" style={{ color: meta.color }}>{line.status}</span>
                                  </div>
                                );
                              })}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </DetailSection>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>

      {/* Debug / Raw API Payloads */}
      <div className="border border-border rounded-2xl overflow-hidden">
        <button
          onClick={() => setDebugOpen(!debugOpen)}
          className="w-full flex items-center justify-between px-5 py-3 bg-muted hover:bg-muted/70 transition-colors"
        >
          <span className="text-xs font-bold uppercase tracking-widest text-muted-foreground flex items-center gap-2">
            <Database className="w-3.5 h-3.5" /> Raw API Debug Data
          </span>
          <ChevronDown className={`w-4 h-4 text-muted-foreground transition-transform ${debugOpen ? 'rotate-180' : ''}`} />
        </button>
        {debugOpen && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 p-4 bg-background">
            <DataCard title={`Rajasthan Network (${rajasthanNetwork.edges.length} lines)`} data={rajasthanNetwork} />
            <DataCard title={`Khavda Network (${khavdaNetwork.edges.length} lines)`} data={khavdaNetwork} />
            <DataCard title="Khavda Block Hierarchy (raw)" data={khavdaProjectsRaw} />
          </div>
        )}
      </div>
    </div>
  );
}

function StatTile({ label, value, icon, tone }: { label: string; value: string | number; icon: React.ReactNode; tone: 'primary' | 'success' | 'warning' | 'destructive' | 'muted' }) {
  const toneClasses: Record<string, string> = {
    primary: 'text-primary bg-primary/10',
    success: 'text-success bg-success/10',
    warning: 'text-warning bg-warning/10',
    destructive: 'text-destructive bg-destructive/10',
    muted: 'text-muted-foreground bg-muted',
  };
  return (
    <div className="bg-card border border-border rounded-xl p-4 flex flex-col gap-2">
      <div className={`w-7 h-7 rounded-lg flex items-center justify-center ${toneClasses[tone]}`}>{icon}</div>
      <div className="text-xl font-bold text-foreground">{value}</div>
      <div className="text-[10px] uppercase tracking-widest text-muted-foreground font-semibold">{label}</div>
    </div>
  );
}

function FilterChip({ active, onClick, children, dotColor }: { active: boolean; onClick: () => void; children: React.ReactNode; dotColor?: string }) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold border shadow-sm transition-colors ${
        active ? 'bg-primary text-primary-foreground border-primary' : 'bg-card text-foreground border-border hover:bg-muted'
      }`}
    >
      {dotColor && <span className="w-2 h-2 rounded-full" style={{ background: active ? '#fff' : dotColor }} />}
      {children}
    </button>
  );
}

function DetailSection({ icon, title, color, children }: { icon: React.ReactNode; title: string; color: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(true);
  return (
    <div className="border-b border-border">
      <button onClick={() => setOpen(!open)} className="w-full flex items-center gap-2 px-5 py-3 hover:bg-muted transition-colors">
        <div className="w-5 h-5 rounded flex items-center justify-center" style={{ backgroundColor: `${color}15`, color }}>{icon}</div>
        <span className="text-[11px] font-bold text-foreground flex-1 text-left uppercase tracking-wider">{title}</span>
        <ChevronDown className={`w-3.5 h-3.5 text-muted-foreground transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && <div className="px-5 pb-4 space-y-1.5">{children}</div>}
    </div>
  );
}

function DetailRow({ label, value }: { label: string; value: any }) {
  return (
    <div className="flex justify-between items-center py-0.5">
      <span className="text-[11px] text-muted-foreground">{label}</span>
      <span className="text-[11px] font-semibold font-mono text-foreground">{value}</span>
    </div>
  );
}

function MiniStat({ label, value }: { label: string; value: any }) {
  return (
    <div className="bg-muted rounded-lg p-2.5 text-center border border-border">
      <div className="text-sm font-bold text-foreground">{value}</div>
      <div className="text-[9px] text-muted-foreground uppercase font-bold tracking-wider">{label}</div>
    </div>
  );
}

function DataCard({ title, data }: { title: string; data: any }) {
  return (
    <div className="bg-muted/50 border border-border/40 rounded-xl p-4 flex flex-col max-h-[400px]">
      <h3 className="text-xs font-bold text-foreground mb-2 uppercase tracking-wider">{title}</h3>
      <div className="flex-1 overflow-auto bg-black/90 rounded-lg p-3 custom-scrollbar">
        {data ? (
          <pre className="text-[10px] text-green-400/90 whitespace-pre-wrap font-mono">
            {JSON.stringify(data, null, 2)}
          </pre>
        ) : (
          <p className="text-xs text-muted-foreground italic">No data available...</p>
        )}
      </div>
    </div>
  );
}
