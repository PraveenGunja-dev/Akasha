import React, { useState, useRef, useMemo, useEffect } from 'react';
import { MapContainer, TileLayer, Marker, Popup, Polyline, Tooltip, useMapEvents } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import L from 'leaflet';
import { MapPin, Layers, ChevronDown, Zap, Search, Thermometer, Wind, Loader2, CloudLightning, CloudRain, X, Activity, Sun, Maximize2, Minimize2, Cloud, Globe, Factory, Target } from 'lucide-react';

// ─── OIM-style voltage color scale ───
const getVoltageColor = (voltageTag?: string): string => {
  if (!voltageTag) return '#888888';
  const match = voltageTag.match(/\d+/);
  if (!match) return '#888888';
  let v = parseInt(match[0], 10);
  if (v < 1000) v *= 1000; // normalize kV → V
  if (v >= 550000) return '#00bcd4'; // cyan  ≥550 kV
  if (v >= 310000) return '#9c27b0'; // purple ≥310 kV
  if (v >= 220000) return '#e53935'; // red    ≥220 kV
  if (v >= 132000) return '#ff9800'; // orange ≥132 kV
  if (v >= 52000) return '#fdd835'; // yellow ≥52 kV
  if (v >= 25000) return '#4caf50'; // green  ≥25 kV
  if (v >= 10000) return '#2196f3'; // blue   ≥10 kV
  return '#555555'; // dark  <10 kV
};

const getVoltageWeight = (voltageTag?: string): number => {
  if (!voltageTag) return 2;
  const match = voltageTag.match(/\d+/);
  if (!match) return 2;
  let v = parseInt(match[0], 10);
  if (v < 1000) v *= 1000;
  if (v >= 550000) return 5;
  if (v >= 310000) return 4.5;
  if (v >= 220000) return 4;
  if (v >= 132000) return 3.5;
  return 3;
};

const formatVoltageLabel = (voltageTag?: string): string => {
  if (!voltageTag) return '';
  // Handle multi-voltage like "400000;220000"
  return voltageTag.split(';').map(v => {
    const num = parseInt(v.trim(), 10);
    if (isNaN(num)) return v;
    if (num >= 1000) return `${Math.round(num / 1000)} kV`;
    return `${num} kV`;
  }).join(' / ');
};

// Create DivIcon for substations with name labels
const createSubstationLabelIcon = (name: string, voltage?: string) => new L.DivIcon({
  html: `<div style="
    display:flex; flex-direction:column; align-items:center; gap:2px; pointer-events:auto;
  ">
    <div style="
      width:12px; height:12px; border-radius:2px; border:2px solid #fff;
      background:${voltage ? getVoltageColor(voltage) : '#8b5cf6'};
      box-shadow:0 1px 4px rgba(0,0,0,0.4);
    "></div>
    <div style="
      background:rgba(255,255,255,0.92); border:1px solid #cbd5e1; border-radius:3px;
      padding:1px 4px; font-size:10px; font-weight:700; color:#1e293b;
      white-space:nowrap; line-height:1.3; text-align:center;
      box-shadow:0 1px 3px rgba(0,0,0,0.15); max-width:140px; overflow:hidden; text-overflow:ellipsis;
    ">${name}${voltage ? `<br/><span style="font-weight:500;color:#64748b;font-size:9px">${formatVoltageLabel(voltage)}</span>` : ''}</div>
  </div>`,
  className: 'substation-label-icon',
  iconSize: [0, 0],
  iconAnchor: [0, 8],
  popupAnchor: [0, -12],
});

// Create DivIcon for generators (solar/wind plants)
const createGeneratorIcon = (type: string) => {
  const color = type === 'solar' ? '#f59e0b' : type === 'wind' ? '#0ea5e9' : '#8b5cf6';
  return new L.DivIcon({
    html: `<div style="
      width:14px; height:14px; border-radius:50%; background:${color};
      border:2px solid white; box-shadow:0 2px 4px rgba(0,0,0,0.3);
      display:flex; align-items:center; justify-content:center;
    "></div>`,
    className: 'generator-dot-icon',
    iconSize: [14, 14],
    iconAnchor: [7, 7],
    popupAnchor: [0, -7],
  });
};
import ReactECharts from 'echarts-for-react';

// Factory to create standard tear-drop markers
const createMarkerIcon = (color: string) => new L.DivIcon({
  html: `<div style="display: flex; align-items: center; justify-content: center;">
    <svg viewBox="0 0 24 24" width="32" height="32" stroke="white" stroke-width="2" fill="${color}" stroke-linecap="round" stroke-linejoin="round" style="filter: drop-shadow(0px 3px 3px rgba(0,0,0,0.3));">
      <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"></path>
      <circle cx="12" cy="10" r="3" fill="white"></circle>
    </svg>
  </div>`,
  className: 'custom-color-marker',
  iconSize: [32, 32],
  iconAnchor: [16, 32],
  popupAnchor: [0, -32],
});



// Weather Simulation Side Panel
function WeatherSimulationPanel({ location, onClose }: { location: { lat: number, lng: number, name: string }, onClose: () => void }) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [isExpanded, setIsExpanded] = useState(false);

  useEffect(() => {
    setLoading(true);
    fetch(`https://api.open-meteo.com/v1/forecast?latitude=${location.lat}&longitude=${location.lng}&hourly=wind_speed_10m,temperature_2m,precipitation_probability,cloud_cover,wind_direction_10m&forecast_days=7&wind_speed_unit=ms&timezone=auto`)
      .then(res => res.json())
      .then(resData => {
        setData(resData);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [location.lat, location.lng]);

  const getChartOptions = (expanded: boolean) => {
    if (!data || !data.hourly) return {};

    return {
      tooltip: {
        trigger: 'axis',
        appendToBody: true, // Fixes clipping & overlap issues by floating over the DOM
        backgroundColor: 'rgba(255, 255, 255, 0.95)',
        borderColor: '#e2e8f0',
        padding: expanded ? [12, 16] : [6, 10], // smaller padding for mini view
        textStyle: { color: '#1e293b', fontSize: expanded ? 12 : 10 },
        formatter: function (params: any) {
          let html = `<div style="font-weight:bold;margin-bottom:${expanded ? '5px' : '2px'};font-size:${expanded ? '12px' : '10px'}">${params[0].name}</div>`;
          params.forEach((p: any) => {
            let unit = p.seriesName === 'Temperature' ? '°C' : p.seriesName === 'Wind Speed' ? 'm/s' : '%';
            if (expanded) {
              html += `<div style="display:flex;justify-content:space-between;gap:15px;margin-bottom:2px">
                <span>${p.marker} ${p.seriesName}</span>
                <span style="font-weight:bold">${p.value} ${unit}</span>
              </div>`;
            } else {
              // Ultra-compact tooltip for minimized view
              html += `<div style="font-size:10px;margin-bottom:2px;display:flex;justify-content:space-between;gap:12px;align-items:center">
                <span style="display:flex;align-items:center;gap:4px">${p.marker} <span style="color:#64748b">${p.seriesName}</span></span>
                <b style="color:#0f172a">${p.value} ${unit}</b>
              </div>`;
            }
          });
          return html;
        }
      },
      legend: {
        show: expanded, // Hide legend in minimized view to save space
        data: ['Temperature', 'Wind Speed', 'Precip. Prob.', 'Cloud Cover'],
        bottom: 0,
        textStyle: { fontSize: 10 }
      },
      grid: expanded 
        ? { top: 40, right: 30, bottom: 40, left: 40 }
        : { top: 15, right: 10, bottom: 20, left: 25 },
      xAxis: {
        type: 'category',
        boundaryGap: false,
        data: data.hourly.time.map((t: string) => {
          const d = new Date(t);
          return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:00`;
        }),
        axisLine: { lineStyle: { color: '#cbd5e1' } },
        axisLabel: { fontSize: expanded ? 10 : 8, color: '#64748b', formatter: (val: string) => val.split(' ')[0] },
      },
      yAxis: [
        { 
          type: 'value', 
          name: expanded ? '°C / m/s' : '', 
          position: 'left', 
          nameTextStyle: { fontSize: 10, color: '#64748b' }, 
          axisLabel: { fontSize: expanded ? 10 : 8, color: '#64748b' },
          splitLine: { show: expanded, lineStyle: { type: 'dashed', color: '#e2e8f0', opacity: 0.5 } }
        },
        { 
          type: 'value', 
          name: expanded ? '%' : '', 
          position: 'right', 
          nameTextStyle: { fontSize: 10, color: '#64748b' }, 
          axisLabel: { fontSize: expanded ? 10 : 8, color: '#64748b' }, 
          splitLine: { show: false }, 
          min: 0, 
          max: 100 
        }
      ],
      series: [
        {
          name: 'Temperature',
          type: 'line',
          smooth: 0.4,
          showSymbol: false,
          yAxisIndex: 0,
          lineStyle: { 
            width: 3, 
            color: { type: 'linear', x: 0, y: 0, x2: 1, y2: 0, colorStops: [{offset: 0, color: '#f43f5e'}, {offset: 1, color: '#fb923c'}] },
            shadowColor: 'rgba(244, 63, 94, 0.4)', shadowBlur: 10, shadowOffsetY: 5
          },
          data: data.hourly.temperature_2m,
        },
        {
          name: 'Wind Speed',
          type: 'line',
          smooth: 0.4,
          showSymbol: false,
          yAxisIndex: 0,
          lineStyle: { 
            width: 3, 
            color: { type: 'linear', x: 0, y: 0, x2: 1, y2: 0, colorStops: [{offset: 0, color: '#0ea5e9'}, {offset: 1, color: '#38bdf8'}] },
            shadowColor: 'rgba(14, 165, 233, 0.4)', shadowBlur: 10, shadowOffsetY: 5
          },
          data: data.hourly.wind_speed_10m
        },
        {
          name: 'Precip. Prob.',
          type: 'bar',
          barWidth: '60%',
          itemStyle: { 
            borderRadius: [4, 4, 0, 0],
            color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{offset: 0, color: '#3b82f6'}, {offset: 1, color: 'rgba(59, 130, 246, 0.1)'}] }
          },
          yAxisIndex: 1,
          data: data.hourly.precipitation_probability
        },
        {
          name: 'Cloud Cover',
          type: 'line',
          smooth: true,
          showSymbol: false,
          yAxisIndex: 1,
          lineStyle: { width: 0 },
          itemStyle: { color: '#94a3b8' },
          areaStyle: { 
            color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{offset: 0, color: 'rgba(148, 163, 184, 0.4)'}, {offset: 1, color: 'rgba(148, 163, 184, 0.05)'}] }
          },
          data: data.hourly.cloud_cover
        }
      ]
    };
  };

  if (isExpanded) {
    return (
      <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-slate-900/40 backdrop-blur-md p-4 sm:p-8 animate-fade-in" onWheel={(e) => e.stopPropagation()}>
        <div className="w-full max-w-7xl bg-white/90 dark:bg-slate-900/90 backdrop-blur-xl shadow-2xl rounded-3xl flex flex-col overflow-hidden max-h-[95vh] border border-white/20 dark:border-slate-800/50">
          <div className="p-6 border-b border-slate-200/50 dark:border-slate-700/50 flex justify-between items-center bg-gradient-to-r from-slate-50 to-white dark:from-slate-900 dark:to-slate-800">
            <div>
              <h3 className="font-extrabold text-2xl text-slate-900 dark:text-white flex items-center gap-3">
                <div className="p-2 bg-blue-100 dark:bg-blue-900/40 rounded-xl">
                  <Activity className="w-6 h-6 text-blue-600 dark:text-blue-400" />
                </div>
                Weather Simulation Engine
              </h3>
              <p className="text-sm font-medium text-slate-500 dark:text-slate-400 mt-1 ml-12">{location.name} ({location.lat.toFixed(2)}, {location.lng.toFixed(2)})</p>
            </div>
            <div className="flex items-center gap-2">
              <button onClick={() => setIsExpanded(false)} className="p-2 hover:bg-slate-200 dark:hover:bg-slate-700 rounded-full transition-colors text-muted-foreground" title="Minimize">
                <Minimize2 className="w-5 h-5" />
              </button>
              <button onClick={onClose} className="p-2 hover:bg-slate-200 dark:hover:bg-slate-700 rounded-full transition-colors text-muted-foreground" title="Close">
                <X className="w-6 h-6" />
              </button>
            </div>
          </div>

          <div className="flex-1 p-8 overflow-y-auto bg-slate-50/50 dark:bg-slate-900/50">
            <div className="mb-8 text-slate-600 dark:text-slate-400 text-lg leading-relaxed max-w-3xl">
              Analyze 7-day high-precision forecasting data for optimal generation dispatching and site safety.
            </div>

            {loading ? (
              <div className="h-[400px] flex flex-col items-center justify-center gap-4 bg-white/50 dark:bg-slate-800/50 rounded-2xl border border-slate-200/50 dark:border-slate-700/50 shadow-sm backdrop-blur-sm">
                <Loader2 className="w-12 h-12 animate-spin text-blue-500" />
                <span className="text-lg font-semibold text-slate-600 dark:text-slate-300">Running Environmental Simulation...</span>
              </div>
            ) : data ? (
              <div className="grid grid-cols-1 lg:grid-cols-5 gap-8">
                
                {/* Chart Section - Takes 3 columns (60%) */}
                <div className="lg:col-span-3 h-[450px] w-full bg-white dark:bg-slate-800/90 rounded-3xl border border-slate-200/60 dark:border-slate-700/60 shadow-xl shadow-slate-200/40 dark:shadow-none p-6 hover:shadow-2xl transition-shadow duration-300 backdrop-blur-xl flex flex-col">
                  <ReactECharts option={getChartOptions(true)} style={{ flex: 1, width: '100%' }} />
                </div>

                {/* Metrics Section - Takes 2 columns (40%), stacked 2x2 */}
                <div className="lg:col-span-2 grid grid-cols-2 gap-6 h-[450px]">
                  
                  <div className="bg-gradient-to-br from-amber-50 to-orange-100 dark:from-amber-900/40 dark:to-orange-900/20 p-6 rounded-3xl border border-amber-200/60 dark:border-amber-800/60 shadow-lg shadow-amber-100/50 dark:shadow-none hover:-translate-y-1 transition-all duration-300 flex flex-col justify-between">
                    <div>
                      <div className="flex items-center gap-2 text-amber-700 dark:text-amber-500 mb-3">
                        <Cloud className="w-6 h-6" />
                        <span className="text-xs font-bold uppercase tracking-widest opacity-80">Precip Prob</span>
                      </div>
                      <div className="text-5xl font-black text-amber-900 dark:text-amber-50 tracking-tighter">
                        {Math.max(...(data?.hourly?.precipitation_probability || [0]))} <span className="text-xl font-semibold text-amber-700/60">%</span>
                      </div>
                    </div>
                    <div className="text-xs font-medium text-amber-900/70 dark:text-amber-200/70 leading-relaxed border-t border-amber-300/30 dark:border-amber-700/50 pt-4">
                      High probability indicates rainfall; may interrupt civil works.
                    </div>
                  </div>

                  <div className="bg-gradient-to-br from-cyan-50 to-blue-100 dark:from-cyan-900/40 dark:to-blue-900/20 p-6 rounded-3xl border border-cyan-200/60 dark:border-cyan-800/60 shadow-lg shadow-cyan-100/50 dark:shadow-none hover:-translate-y-1 transition-all duration-300 flex flex-col justify-between">
                    <div>
                      <div className="flex items-center gap-2 text-cyan-700 dark:text-cyan-500 mb-3">
                        <Wind className="w-6 h-6" />
                        <span className="text-xs font-bold uppercase tracking-widest opacity-80">Max Wind</span>
                      </div>
                      <div className="text-5xl font-black text-cyan-900 dark:text-cyan-50 tracking-tighter">
                        {Math.max(...(data?.hourly?.wind_speed_10m || [0])).toFixed(0)} <span className="text-xl font-semibold text-cyan-700/60">m/s</span>
                      </div>
                    </div>
                    <div className="text-xs font-medium text-cyan-900/70 dark:text-cyan-200/70 leading-relaxed border-t border-cyan-300/30 dark:border-cyan-700/50 pt-4">
                      Speeds above 20m/s risk automatic turbine shutdown.
                    </div>
                  </div>

                  <div className="bg-gradient-to-br from-slate-100 to-slate-200 dark:from-slate-800 dark:to-slate-700/50 p-6 rounded-3xl border border-slate-300/60 dark:border-slate-600/60 shadow-lg shadow-slate-200/50 dark:shadow-none hover:-translate-y-1 transition-all duration-300 flex flex-col justify-between">
                    <div>
                      <div className="flex items-center gap-2 text-slate-700 dark:text-slate-400 mb-3">
                        <Cloud className="w-6 h-6" />
                        <span className="text-xs font-bold uppercase tracking-widest opacity-80">Cloud Cover</span>
                      </div>
                      <div className="text-5xl font-black text-slate-900 dark:text-white tracking-tighter">
                        {data?.hourly?.cloud_cover ? (data.hourly.cloud_cover.reduce((a: number, b: number) => a + b, 0) / data.hourly.cloud_cover.length).toFixed(0) : 0} <span className="text-xl font-semibold text-slate-500">%</span>
                      </div>
                    </div>
                    <div className="text-xs font-medium text-slate-600 dark:text-slate-400 leading-relaxed border-t border-slate-300/50 dark:border-slate-600/50 pt-4">
                      Dense cover diminishes solar yield. Dispatch grid reserves.
                    </div>
                  </div>

                  <div className="bg-gradient-to-br from-rose-50 to-red-100 dark:from-rose-900/40 dark:to-red-900/20 p-6 rounded-3xl border border-rose-200/60 dark:border-rose-800/60 shadow-lg shadow-rose-100/50 dark:shadow-none hover:-translate-y-1 transition-all duration-300 flex flex-col justify-between">
                    <div>
                      <div className="flex items-center gap-2 text-rose-700 dark:text-rose-500 mb-3">
                        <Thermometer className="w-6 h-6" />
                        <span className="text-xs font-bold uppercase tracking-widest opacity-80">Peak Temp</span>
                      </div>
                      <div className="text-5xl font-black text-rose-900 dark:text-rose-50 tracking-tighter">
                        {Math.max(...(data?.hourly?.temperature_2m || [0])).toFixed(0)} <span className="text-xl font-semibold text-rose-700/60">°C</span>
                      </div>
                    </div>
                    <div className="text-xs font-medium text-rose-900/70 dark:text-rose-200/60 leading-relaxed border-t border-rose-300/30 dark:border-rose-700/50 pt-4">
                      Panels lose efficiency for every degree above 25°C.
                    </div>
                  </div>

                </div>
              </div>
            ) : null}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="absolute top-20 left-4 w-96 bg-white/90 dark:bg-slate-900/90 backdrop-blur-xl shadow-2xl rounded-2xl flex flex-col border border-white/20 dark:border-slate-800/50 z-[2000] overflow-hidden transform transition-all duration-300">
      <div className="px-4 py-3 border-b border-slate-200/50 dark:border-slate-700/50 flex justify-between items-center bg-gradient-to-r from-slate-50 to-white dark:from-slate-900 dark:to-slate-800">
        <div>
          <h3 className="font-extrabold text-[15px] text-slate-900 dark:text-white flex items-center gap-2">
            <div className="p-1.5 bg-blue-100 dark:bg-blue-900/40 rounded-lg">
              <Activity className="w-4 h-4 text-blue-600 dark:text-blue-400" />
            </div>
            Weather Sim
          </h3>
          <p className="text-[10px] font-medium text-slate-500 dark:text-slate-400 mt-0.5 ml-8">{location.name} ({location.lat.toFixed(2)}, {location.lng.toFixed(2)})</p>
        </div>
        <div className="flex items-center gap-1">
          <button onClick={() => setIsExpanded(true)} className="p-1.5 hover:bg-slate-200 dark:hover:bg-slate-700 rounded-md transition-colors text-slate-500" title="Expand">
            <Maximize2 className="w-4 h-4" />
          </button>
          <button onClick={onClose} className="p-1.5 hover:bg-slate-200 dark:hover:bg-slate-700 rounded-md transition-colors text-slate-500" title="Close">
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      <div className="p-3 bg-slate-50/50 dark:bg-slate-900/50 flex-1 overflow-hidden">
        {loading ? (
          <div className="h-44 flex flex-col items-center justify-center gap-3">
            <Loader2 className="w-6 h-6 animate-spin text-blue-500" />
            <span className="text-xs font-semibold text-slate-600 dark:text-slate-400">Running Simulation...</span>
          </div>
        ) : (
          <div className="h-48 w-full bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 pt-2 px-1 shadow-sm hover:shadow-md transition-shadow">
            <ReactECharts option={getChartOptions(false)} style={{ height: '100%', width: '100%' }} />
          </div>
        )}

        {!loading && data && (
          <div className="mt-3 grid grid-cols-2 gap-2">
            <div className="bg-gradient-to-br from-amber-50 to-orange-50 dark:from-amber-900/30 dark:to-orange-900/20 p-2.5 rounded-xl border border-amber-200/50 dark:border-amber-800/50 shadow-sm transition-transform hover:scale-[1.02]">
              <div className="flex items-center gap-1.5 text-amber-600 dark:text-amber-500 mb-1">
                <Thermometer className="w-3.5 h-3.5" />
                <span className="text-[10px] font-bold uppercase tracking-wider">7-Day Peak Temp</span>
              </div>
              <div className="text-lg font-extrabold text-amber-900 dark:text-amber-100">
                {Math.max(...(data?.hourly?.temperature_2m || [0])).toFixed(0)} <span className="text-xs font-semibold text-amber-600/70">°C</span>
              </div>
            </div>
            <div className="bg-gradient-to-br from-cyan-50 to-blue-50 dark:from-cyan-900/30 dark:to-blue-900/20 p-2.5 rounded-xl border border-cyan-200/50 dark:border-cyan-800/50 shadow-sm transition-transform hover:scale-[1.02]">
              <div className="flex items-center gap-1.5 text-cyan-600 dark:text-cyan-500 mb-1">
                <Wind className="w-3.5 h-3.5" />
                <span className="text-[10px] font-bold uppercase tracking-wider">7-Day Max Wind</span>
              </div>
              <div className="text-lg font-extrabold text-cyan-900 dark:text-cyan-100">
                {Math.max(...(data?.hourly?.wind_speed_10m || [0])).toFixed(0)} <span className="text-xs font-semibold text-cyan-600/70">m/s</span>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// Factory to create small dot markers for zoomed-out view
const createDotIcon = (color: string) => new L.DivIcon({
  html: `<div style="background-color: ${color}; width: 14px; height: 14px; border-radius: 50%; border: 2px solid white; box-shadow: 0 2px 4px rgba(0,0,0,0.3); display: flex; align-items: center; justify-content: center;"></div>`,
  className: 'custom-dot-marker',
  iconSize: [14, 14],
  iconAnchor: [7, 7],
  popupAnchor: [0, -7],
});

// Define distinct colors
const substationMarkerIcon = createMarkerIcon('#8b5cf6');
const projectMarkerIcon = createMarkerIcon('#0ea5e9');

const substationDotIcon = createDotIcon('#8b5cf6');
const projectDotIcon = createDotIcon('#0ea5e9');

interface ProjectMapProps {
  projects?: any[];
  onOpenProject?: (projectId: string) => void;
  theme?: 'light' | 'dark';
}

const MAP_STYLES = [
  { id: 'google-standard', name: 'Google Maps Standard', url: 'https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}' },
  { id: 'google-hybrid', name: 'Google Satellite Hybrid', url: 'https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}' },
  { id: 'google-terrain', name: 'Google Terrain', url: 'https://mt1.google.com/vt/lyrs=p&x={x}&y={y}&z={z}' },
  { id: 'esri-street', name: 'ESRI Street Map', url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}' },
  { id: 'esri-natgeo', name: 'ESRI National Geographic', url: 'https://server.arcgisonline.com/ArcGIS/rest/services/NatGeo_World_Map/MapServer/tile/{z}/{y}/{x}' },
  { id: 'esri-light-gray', name: 'ESRI Minimalist Light', url: 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}' },
  { id: 'carto-voyager', name: 'Carto Voyager (Standard)', url: 'https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png' },
  { id: 'carto-positron', name: 'Carto Enterprise Light', url: 'https://{s}.basemaps.cartocdn.com/rastertiles/positron/{z}/{x}/{y}{r}.png' },
  { id: 'carto-dark', name: 'Carto Minimalist Dark', url: 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png' },
  { id: 'osm-standard', name: 'OSM Detailed View', url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png' },
  { id: 'osm-hot', name: 'OSM Infrastructure (HOT)', url: 'https://{s}.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png' },
  { id: 'open-topo', name: 'OpenTopo Contours', url: 'https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png' },
];

// Curated Substation Coordinates provided by the user
const SUBSTATION_COORDS = [
  { name: "Padghe", lat: 19.353, lng: 73.212 },         // 0
  { name: "Pirana", lat: 22.872, lng: 72.557 },         // 1
  { name: "South Olpad", lat: 21.890, lng: 73.086 },    // 2
  { name: "Lakadia", lat: 23.394, lng: 70.598 },        // 3
  { name: "Halvad", lat: 22.911, lng: 71.231 },         // 4
  { name: "Boisar", lat: 19.742, lng: 72.785 },         // 5
  { name: "Khavda", lat: 24.024, lng: 69.337 },         // 6
  { name: "Bhuj", lat: 23.379, lng: 69.592 },           // 7
  { name: "Pune", lat: 18.734, lng: 73.699 },           // 8
  { name: "Banaskantha", lat: 24.090, lng: 72.000 },    // 9
  { name: "Ramgarh", lat: 27.471, lng: 70.494 },        // 10
  { name: "Bhadla", lat: 27.618, lng: 72.206 },         // 11
  { name: "Fatehgarh", lat: 26.285, lng: 71.100 },      // 12
  { name: "Sikar", lat: 27.612, lng: 75.088 },          // 13
  { name: "Khetri", lat: 27.951, lng: 75.709 },         // 14
  { name: "Narela", lat: 28.753, lng: 76.984 },         // 15
  { name: "Jhatikara", lat: 28.462, lng: 76.937 },      // 16
  { name: "Bikaner", lat: 28.373, lng: 73.171 },        // 17
  { name: "Mandsaur", lat: 24.207, lng: 75.171 },       // 18
  { name: "Indore", lat: 22.909, lng: 75.900 },         // 19
  { name: "Mandvi", lat: 22.833, lng: 69.355 },         // 20
];

// Edge data provided by the user
const ALL_EDGES = [
  { source: "Bikaner", target: "Sikar", type: "765kV", status: "charged" },
  { source: "Sikar", target: "Khetri", type: "765kV", status: "charged" },
  { source: "Khetri", target: "Narela", type: "765kV", status: "in_progress" },
  { source: "Narela", target: "Jhatikara", type: "400kV", status: "under_bidding" },
  { source: "Bhadla", target: "Fatehgarh", type: "765kV", status: "charged" },
  { source: "Bhadla", target: "Bikaner", type: "765kV", status: "charged" },
  { source: "Banaskantha", target: "Pirana", type: "765kV", status: "in_progress" },
  { source: "Pirana", target: "South Olpad", type: "400kV", status: "charged" },
  { source: "South Olpad", target: "Boisar", type: "400kV", status: "in_progress" },
  { source: "Boisar", target: "Padghe", type: "400kV", status: "charged" },
  { source: "Padghe", target: "Pune", type: "400kV", status: "under_bidding" },
  { source: "Khavda", target: "Bhuj", type: "765kV", status: "charged" },
  { source: "Bhuj", target: "Lakadia", type: "765kV", status: "charged" },
  { source: "Lakadia", target: "Halvad", type: "765kV", status: "in_progress" },
  { source: "Halvad", target: "Pirana", type: "765kV", status: "charged" }
];

// Helper to get color based on status
const getEdgeColor = (status: string) => {
  switch (status) {
    case 'charged': return '#10b981'; // Green
    case 'in_progress': return '#f59e0b'; // Amber
    case 'under_bidding': return '#ef4444'; // Red
    default: return '#8b5cf6'; // Default purple
  }
};

// Helper to get dash pattern based on status
const getEdgeDash = (status: string) => {
  return status === 'charged' ? undefined : '5, 10';
};

// Helper to determine coordinates based on project name
const getProjectCoordinates = (project: any, index: number) => {
  if (project.latitude && project.longitude) {
    return [project.latitude, project.longitude];
  }

  const name = (project.name || project.projectId || "").toLowerCase();
  const locName = (project.locationName || "").toLowerCase();

  // Search the curated list for a match
  for (const sub of SUBSTATION_COORDS) {
    if (name.includes(sub.name.toLowerCase()) || locName.includes(sub.name.toLowerCase())) {
      // Add a tiny deterministic jitter so multiple projects at the same site don't completely overlap
      const jitterLat = (Math.sin(index * 123.45) * 0.05);
      const jitterLng = (Math.cos(index * 678.90) * 0.05);
      return [sub.lat + jitterLat, sub.lng + jitterLng];
    }
  }

  // Return null if absolutely no match found to avoid hallucinating locations
  return null;
};

export default function ProjectMap({ projects = [], onOpenProject, theme }: ProjectMapProps) {
  const [activeStyle, setActiveStyle] = useState(MAP_STYLES[0]);
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const [showTransmission, setShowTransmission] = useState(false); // Hidden by default to reduce clutter
  const [showProjects, setShowProjects] = useState(false);
  const [currentZoom, setCurrentZoom] = useState(6);
  const [searchQuery, setSearchQuery] = useState('');
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [showWeatherSim, setShowWeatherSim] = useState(false);
  const [simLocation, setSimLocation] = useState<{ lat: number, lng: number, name: string }>({ lat: 24.0, lng: 74.0, name: 'Western Grid Average' });

  // Overpass API State
  const [showOIM, setShowOIM] = useState(false);
  const [viewportGrid, setViewportGrid] = useState<any[]>([]);
  const [isExtractingGrid, setIsExtractingGrid] = useState(false);
  const [clickedLocation, setClickedLocation] = useState<L.LatLng | null>(null);
  const [overpassLoading, setOverpassLoading] = useState(false);
  const [overpassData, setOverpassData] = useState<any>(null);

  // New State for P6 Project ID Filtering
  const [p6ProjectIdFilter, setP6ProjectIdFilter] = useState('');
  const [mappedTcEdges, setMappedTcEdges] = useState<any[]>([]);
  const [isLoadingEdges, setIsLoadingEdges] = useState(false);

  useEffect(() => {
    if (!p6ProjectIdFilter.trim()) {
      setMappedTcEdges([]);
      return;
    }

    const timer = setTimeout(async () => {
      setIsLoadingEdges(true);
      try {
        const res = await fetch(`/akasha/api/tc-network/project/${p6ProjectIdFilter.trim()}`);
        if (res.ok) {
          const data = await res.json();
          setMappedTcEdges(data.edges || []);

          // Optionally, fly to the first edge's substation if coordinates exist
          if (data.edges && data.edges.length > 0) {
            const firstEdge = data.edges[0];
            const startNode = SUBSTATION_COORDS.find(s => (firstEdge.from_label || '').toLowerCase().includes(s.name.toLowerCase()));
            if (startNode && mapRef.current) {
              mapRef.current.flyTo([startNode.lat, startNode.lng], 8, { duration: 1.5 });
            }
          }
        } else {
          setMappedTcEdges([]);
        }
      } catch (err) {
        console.error("Failed to fetch TC mapped edges", err);
        setMappedTcEdges([]);
      } finally {
        setIsLoadingEdges(false);
      }
    }, 500); // debounce

    return () => clearTimeout(timer);
  }, [p6ProjectIdFilter]);

  const mapRef = useRef<L.Map>(null);

  const extractGridInViewport = async () => {
    if (!mapRef.current) return;
    const zoom = mapRef.current.getZoom();
    if (zoom < 8) {
      console.warn("Please zoom in closer (zoom level 8 or higher) before extracting the grid to prevent overloading the browser.");
      return;
    }

    setIsExtractingGrid(true);
    const bounds = mapRef.current.getBounds();
    // Overpass bbox format: south,west,north,east
    const bbox = `${bounds.getSouth()},${bounds.getWest()},${bounds.getNorth()},${bounds.getEast()}`;

    // out geom includes the latitude and longitude for every point in the line!
    const query = `
      [out:json][timeout:30];
      (
        way["power"="line"](${bbox});
        node["power"="substation"](${bbox});
        way["power"="substation"](${bbox});
        node["power"="plant"](${bbox});
        way["power"="plant"](${bbox});
        node["power"="generator"](${bbox});
      );
      out geom tags;
    `;

    try {
      const response = await fetch('https://overpass-api.de/api/interpreter', {
        method: 'POST',
        body: query
      });
      const data = await response.json();
      setViewportGrid(data.elements || []);
    } catch (err) {
      console.error("Vector Extraction Error:", err);
      console.warn("Failed to extract grid vectors from OpenStreetMap.");
    } finally {
      setIsExtractingGrid(false);
    }
  };

  const handleMapRightClick = async (e: L.LeafletMouseEvent) => {
    setClickedLocation(e.latlng);
    setOverpassLoading(true);
    setOverpassData(null);

    // Construct Overpass QL query (2000 meter radius)
    const query = `
      [out:json];
      (
        node["power"](around:2000, ${e.latlng.lat}, ${e.latlng.lng});
        way["power"](around:2000, ${e.latlng.lat}, ${e.latlng.lng});
      );
      out tags;
    `;

    try {
      const response = await fetch('https://overpass-api.de/api/interpreter', {
        method: 'POST',
        body: query
      });
      const data = await response.json();

      // Filter out elements without interesting tags
      const filtered = data.elements.filter((el: any) => {
        if (!el.tags) return false;

        // Filter out low voltage "village" lines (11kV, 33kV)
        if (el.tags.power === 'line') {
          if (el.tags.voltage) {
            // Extract the first sequence of numbers (e.g., "400000;220000" -> 400000)
            const match = el.tags.voltage.match(/\d+/);
            if (match) {
              let volts = parseInt(match[0], 10);
              // Some mappers write "400" instead of "400000". If it's less than 1000, assume it's in kV.
              if (volts < 1000) volts *= 1000;

              // Only keep High Voltage transmission lines (66kV and above)
              if (volts < 66000) return false;
            }
          }
          return true; // Keep lines that are either high voltage or have no voltage tag specified
        }

        return el.tags.power === 'substation' || el.tags.power === 'plant';
      });

      // Deduplicate by name/voltage to avoid rendering 50 segments of the same line
      const uniqueData = [];
      const seen = new Set();
      for (const item of filtered) {
        const key = `${item.tags.power}-${item.tags.name || ''}-${item.tags.voltage || ''}`;
        if (!seen.has(key)) {
          seen.add(key);
          uniqueData.push(item);
        }
      }

      setOverpassData(uniqueData);
    } catch (err) {
      console.error("Overpass API Error:", err);
      setOverpassData([]);
    } finally {
      setOverpassLoading(false);
    }
  };

  // Create a sub-component for map events
  function MapEventsHandler() {
    useMapEvents({
      contextmenu: handleMapRightClick
    });
    return null;
  }

  // Combine and filter searchable locations
  const searchSuggestions = useMemo(() => {
    if (!searchQuery.trim()) return [];

    const query = searchQuery.toLowerCase();
    const suggestions: { name: string; type: string; lat: number; lng: number }[] = [];

    // Search static substations
    SUBSTATION_COORDS.forEach(sub => {
      if (sub.name.toLowerCase().includes(query)) {
        suggestions.push({ name: sub.name, type: 'Substation', lat: sub.lat, lng: sub.lng });
      }
    });

    // Search dynamic projects
    projects.forEach((proj, idx) => {
      const name = proj.name || proj.projectId || '';
      if (name.toLowerCase().includes(query)) {
        const coords = getProjectCoordinates(proj, idx);
        suggestions.push({ name: name, type: proj.category || 'Project', lat: coords[0], lng: coords[1] });
      }
    });

    return suggestions.slice(0, 8); // limit to top 8
  }, [searchQuery, projects]);

  const handleSearchSelect = (lat: number, lng: number) => {
    if (mapRef.current) {
      mapRef.current.flyTo([lat, lng], 10, { duration: 1.5 });
    }
    setSearchQuery('');
    setShowSuggestions(false);
  };

  // Component to track zoom level
  function ZoomTracker() {
    useMapEvents({
      zoomend: (e) => {
        setCurrentZoom(e.target.getZoom());
      }
    });
    return null;
  }

  // Center on MP / Gujarat / Rajasthan area (Western/Central India) where most projects are
  const center: [number, number] = [24.0, 74.0];
  const zoom = 6;

  // Bounding box for India to restrict panning
  const indiaBounds: L.LatLngBoundsExpression = [
    [7.0, 68.0], // Southwest coordinates (tighter)
    [36.0, 97.0] // Northeast coordinates (tighter)
  ];

  return (
    <div className="w-full h-full min-h-[calc(100vh-120px)] overflow-hidden relative">

      {/* Floating Overlay Controls */}
      <div className="absolute top-4 right-4 z-[1000] flex gap-4 items-start">

        {/* Search Bar */}
        <div className="w-72 relative">
          <div className="flex items-center bg-card border border-border dark:border-slate-700 shadow-lg rounded-lg overflow-hidden focus-within:ring-2 focus-within:ring-indigo-500 transition-all">
            <div className="pl-3 py-2 text-muted-foreground">
              <Search className="w-5 h-5" />
            </div>
            <input
              type="text"
              placeholder="Search projects..."
              className="w-full bg-transparent border-none px-3 py-2 text-sm text-foreground dark:text-muted-foreground focus:outline-none placeholder:text-muted-foreground"
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value);
                setShowSuggestions(true);
              }}
              onFocus={() => setShowSuggestions(true)}
            />
          </div>

          {/* Autocomplete Suggestions */}
          {showSuggestions && searchSuggestions.length > 0 && (
            <div className="absolute top-full left-0 right-0 mt-2 bg-card border border-border dark:border-slate-700 rounded-lg shadow-xl overflow-hidden py-1 max-h-64 overflow-y-auto">
              {searchSuggestions.map((item, idx) => (
                <button
                  key={`${item.name}-${idx}`}
                  onClick={() => handleSearchSelect(item.lat, item.lng)}
                  className="w-full text-left px-4 py-2 text-sm hover:bg-muted dark:hover:bg-slate-700/50 transition-colors flex flex-col"
                >
                  <span className="font-semibold text-foreground dark:text-muted-foreground">{item.name}</span>
                  <span className="text-xs text-muted-foreground dark:text-muted-foreground">{item.type}</span>
                </button>
              ))}
            </div>
          )}

          {/* New P6 Project ID Filter */}
          <div className="mt-2 relative">
            <div className="flex items-center bg-card border border-border dark:border-slate-700 shadow-lg rounded-lg overflow-hidden focus-within:ring-2 focus-within:ring-indigo-500 transition-all">
              <div className="pl-3 py-2 text-primary">
                {isLoadingEdges ? <Loader2 className="w-5 h-5 animate-spin" /> : <Layers className="w-5 h-5" />}
              </div>
              <input
                type="text"
                placeholder="Filter by P6 Project ID..."
                className="w-full bg-transparent border-none px-3 py-2 text-sm text-foreground dark:text-muted-foreground focus:outline-none placeholder:text-muted-foreground"
                value={p6ProjectIdFilter}
                onChange={(e) => setP6ProjectIdFilter(e.target.value)}
                title="Enter P6 Project ID to see its mapped transmission lines"
              />
            </div>

            {/* P6 Project ID Autocomplete Suggestions */}
            {p6ProjectIdFilter.trim() && !isLoadingEdges && mappedTcEdges.length === 0 && (
              <div className="absolute top-full left-0 right-0 mt-2 bg-card border border-border dark:border-slate-700 rounded-lg shadow-xl overflow-hidden py-1 max-h-48 overflow-y-auto">
                {projects
                  .filter(p => {
                    const id = p.projectId || p.project_id;
                    return id && id.toLowerCase().includes(p6ProjectIdFilter.toLowerCase());
                  })
                  .slice(0, 8)
                  .map((proj, idx) => {
                    const id = proj.projectId || proj.project_id;
                    return (
                      <button
                        key={`p6-sug-${idx}`}
                        onClick={() => setP6ProjectIdFilter(id)}
                        className="w-full text-left px-4 py-2 text-sm hover:bg-muted dark:hover:bg-slate-700/50 transition-colors font-semibold text-foreground dark:text-muted-foreground"
                      >
                        {id}
                      </button>
                    );
                  })}
                {projects.filter(p => {
                  const id = p.projectId || p.project_id;
                  return id && id.toLowerCase().includes(p6ProjectIdFilter.toLowerCase());
                }).length === 0 && (
                    <div className="px-4 py-2 text-sm text-muted-foreground italic">No matching Project IDs found in summary data</div>
                  )}
              </div>
            )}
          </div>
        </div>

        {/* Map Buttons (Grid, Radar, Layers) */}
        <div className="flex flex-col gap-2 items-end">

          {/* Weather Simulation Panel Toggle */}
          <button
            onClick={() => setShowWeatherSim(!showWeatherSim)}
            className={`flex items-center gap-2 border shadow-lg rounded-lg px-3 py-2 transition-colors ${showWeatherSim
              ? 'bg-primary/10 dark:bg-primary/100/20 border-indigo-300 dark:border-indigo-500/50 text-indigo-700 dark:text-primary'
              : 'bg-card border-border dark:border-slate-700 hover:bg-muted dark:hover:bg-slate-700 text-foreground dark:text-muted-foreground'
              }`}
          >
            <CloudLightning className={`w-4 h-4`} />
            <span className="text-sm font-semibold">
              Simulation Panel
            </span>
          </button>

          {/* Global Infra (OIM) Toggle */}
          <button
            onClick={() => {
              setShowOIM(!showOIM);
              if (showOIM) setViewportGrid([]); // clear on turn off
            }}
            className={`flex items-center gap-2 border shadow-lg rounded-lg px-3 py-2 transition-colors ${showOIM
              ? 'bg-success/10 dark:bg-success/100/20 border-emerald-300 dark:border-emerald-500/50 text-success dark:text-success'
              : 'bg-card border-border dark:border-slate-700 hover:bg-muted dark:hover:bg-slate-700 text-foreground dark:text-muted-foreground'
              }`}
          >
            <Globe className={`w-4 h-4`} />
            <span className="text-sm font-semibold">
              Real Grid Vectors
            </span>
          </button>

          {/* Fetch Vectors Button (Only shows if OIM is enabled) */}
          {showOIM && (
            <button
              onClick={extractGridInViewport}
              disabled={isExtractingGrid}
              className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white border-transparent shadow-lg rounded-lg px-3 py-2 transition-colors disabled:opacity-50"
            >
              {isExtractingGrid ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
              <span className="text-sm font-semibold">
                {isExtractingGrid ? "Extracting..." : "Load in Viewport"}
              </span>
            </button>
          )}

          {/* Transmission Lines Toggle */}
          <button
            onClick={() => setShowTransmission(!showTransmission)}
            className={`flex items-center gap-2 border shadow-lg rounded-lg px-3 py-2 transition-colors ${showTransmission
              ? 'bg-warning/10 dark:bg-warning/100/20 border-amber-300 dark:border-amber-500/50 text-warning dark:text-warning'
              : 'bg-card border-border dark:border-slate-700 hover:bg-muted dark:hover:bg-slate-700 text-foreground dark:text-muted-foreground'
              }`}
          >
            <Zap className={`w-4 h-4 ${showTransmission ? 'fill-current' : ''}`} />
            <span className="text-sm font-semibold">
              Power Grid
            </span>
          </button>

          {/* Projects Toggle */}
          <button
            onClick={() => setShowProjects(!showProjects)}
            className={`flex items-center gap-2 border shadow-lg rounded-lg px-3 py-2 transition-colors ${showProjects
              ? 'bg-primary/10 dark:bg-primary/100/20 border-blue-300 dark:border-blue-500/50 text-blue-700 dark:text-primary'
              : 'bg-card border-border dark:border-slate-700 hover:bg-muted dark:hover:bg-slate-700 text-foreground dark:text-muted-foreground'
              }`}
          >
            <Target className={`w-4 h-4 ${showProjects ? 'fill-current' : ''}`} />
            <span className="text-sm font-semibold">
              Projects
            </span>
          </button>

          {/* Base Map Dropdown */}
          <div className="relative">
            <button
              onClick={() => setIsDropdownOpen(!isDropdownOpen)}
              className="flex items-center gap-2 bg-card border border-border dark:border-slate-700 shadow-lg rounded-lg px-3 py-2 hover:bg-muted dark:hover:bg-slate-700 transition-colors"
            >
              <Layers className="w-4 h-4 text-primary dark:text-primary" />
              <span className="text-sm font-semibold text-foreground dark:text-muted-foreground">
                {activeStyle.name}
              </span>
              <ChevronDown className={`w-4 h-4 text-muted-foreground transition-transform ${isDropdownOpen ? 'rotate-180' : ''}`} />
            </button>

            {isDropdownOpen && (
              <div className="absolute right-0 top-full mt-2 w-56 bg-card border border-border dark:border-slate-700 rounded-lg shadow-xl overflow-hidden py-1">
                <div className="px-3 py-2 text-xs font-bold text-muted-foreground uppercase tracking-wider border-b border-muted dark:border-slate-700/50 mb-1">
                  Map Layers
                </div>
                {MAP_STYLES.map((style) => (
                  <button
                    key={style.id}
                    onClick={() => {
                      setActiveStyle(style);
                      setIsDropdownOpen(false);
                    }}
                    className={`w-full text-left px-3 py-2 text-sm transition-colors flex items-center justify-between
                    ${activeStyle.id === style.id
                        ? 'bg-primary/10 dark:bg-primary/100/10 text-indigo-700 dark:text-primary font-semibold'
                        : 'text-foreground dark:text-muted-foreground hover:bg-muted dark:hover:bg-slate-700/50'
                      }
                  `}
                  >
                    {style.name}
                    {activeStyle.id === style.id && (
                      <div className="w-2 h-2 rounded-full bg-primary/100" />
                    )}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {showWeatherSim && (
          <WeatherSimulationPanel
            location={simLocation}
            onClose={() => setShowWeatherSim(false)}
          />
        )}
      </div>

      <div className="absolute inset-0 z-0 [&_.leaflet-container]:!font-sans">
        <MapContainer
          ref={mapRef}
          center={center}
          zoom={zoom}
          minZoom={4}
          maxBounds={indiaBounds}
          maxBoundsViscosity={1.0}
          scrollWheelZoom={true}
          style={{ height: '100%', width: '100%', fontFamily: 'inherit' }}
          attributionControl={false}
        >
          <TileLayer
            key={activeStyle.id} // Re-render when changing styles
            url={activeStyle.url}
          />
          <ZoomTracker />
          <MapEventsHandler />

          {/* ─── OIM-Style Vector Grid ─── */}
          {showOIM && viewportGrid.map((element, idx) => {
            const tags = element.tags || {};

            // ── Transmission Lines (ways with power=line) ──
            if (element.type === 'way' && tags.power === 'line' && element.geometry) {
              const positions = element.geometry.map((g: any) => [g.lat, g.lon] as [number, number]);
              const color = getVoltageColor(tags.voltage);
              const weight = getVoltageWeight(tags.voltage);
              const vLabel = formatVoltageLabel(tags.voltage);
              return (
                <Polyline
                  key={`osm-line-${element.id}-${idx}`}
                  positions={positions}
                  pathOptions={{ color, weight, opacity: 0.85, lineCap: 'round' }}
                >
                  {vLabel && (
                    <Tooltip permanent direction="center" className="voltage-label-tooltip">
                      {vLabel}
                    </Tooltip>
                  )}
                  <Popup>
                    <div className="min-w-[220px] p-1">
                      <h3 className="font-bold text-sm border-b pb-1 mb-2" style={{ color }}>
                        ⚡ {tags.name || 'Transmission Line'}
                      </h3>
                      <div className="text-xs text-foreground grid grid-cols-2 gap-y-1.5 gap-x-3">
                        {tags.voltage && <div><span className="font-semibold text-muted-foreground">Voltage</span><br /><span className="font-bold">{vLabel}</span></div>}
                        {tags.cables && <div><span className="font-semibold text-muted-foreground">Cables</span><br /><span className="font-bold">{tags.cables}</span></div>}
                        {tags.circuits && <div><span className="font-semibold text-muted-foreground">Circuits</span><br /><span className="font-bold">{tags.circuits}</span></div>}
                        {tags.wires && <div><span className="font-semibold text-muted-foreground">Wires</span><br /><span className="font-bold">{tags.wires}</span></div>}
                        {tags.operator && <div className="col-span-2"><span className="font-semibold text-muted-foreground">Operator</span><br /><span className="font-bold">{tags.operator}</span></div>}
                        {tags.ref && <div className="col-span-2"><span className="font-semibold text-muted-foreground">Ref</span><br /><span className="font-bold">{tags.ref}</span></div>}
                      </div>
                    </div>
                  </Popup>
                </Polyline>
              );
            }

            // ── Substations (nodes) ──
            if (element.type === 'node' && tags.power === 'substation') {
              return (
                <Marker
                  key={`osm-sub-node-${element.id}-${idx}`}
                  position={[element.lat, element.lon]}
                  icon={createSubstationLabelIcon(tags.name || 'Substation', tags.voltage)}
                >
                  <Popup>
                    <div className="min-w-[220px] p-1">
                      <h3 className="font-bold text-sm text-indigo-700 border-b pb-1 mb-2">
                        🏗️ {tags.name || 'Substation'}
                      </h3>
                      <div className="text-xs text-foreground grid grid-cols-2 gap-y-1.5 gap-x-3">
                        {tags.voltage && <div><span className="font-semibold text-muted-foreground">Voltage</span><br /><span className="font-bold">{formatVoltageLabel(tags.voltage)}</span></div>}
                        {tags.operator && <div><span className="font-semibold text-muted-foreground">Operator</span><br /><span className="font-bold">{tags.operator}</span></div>}
                        {tags.substation && <div><span className="font-semibold text-muted-foreground">Type</span><br /><span className="font-bold">{tags.substation}</span></div>}
                        {tags.ref && <div><span className="font-semibold text-muted-foreground">Ref</span><br /><span className="font-bold">{tags.ref}</span></div>}
                      </div>
                    </div>
                  </Popup>
                </Marker>
              );
            }

            // ── Substations (ways — use centroid) ──
            if (element.type === 'way' && tags.power === 'substation' && element.geometry) {
              const lats = element.geometry.map((g: any) => g.lat);
              const lons = element.geometry.map((g: any) => g.lon);
              const centLat = lats.reduce((a: number, b: number) => a + b, 0) / lats.length;
              const centLon = lons.reduce((a: number, b: number) => a + b, 0) / lons.length;
              return (
                <Marker
                  key={`osm-sub-way-${element.id}-${idx}`}
                  position={[centLat, centLon]}
                  icon={createSubstationLabelIcon(tags.name || 'Substation', tags.voltage)}
                >
                  <Popup>
                    <div className="min-w-[220px] p-1">
                      <h3 className="font-bold text-sm text-indigo-700 border-b pb-1 mb-2">
                        🏗️ {tags.name || 'Substation'}
                      </h3>
                      <div className="text-xs text-foreground grid grid-cols-2 gap-y-1.5 gap-x-3">
                        {tags.voltage && <div><span className="font-semibold text-muted-foreground">Voltage</span><br /><span className="font-bold">{formatVoltageLabel(tags.voltage)}</span></div>}
                        {tags.operator && <div><span className="font-semibold text-muted-foreground">Operator</span><br /><span className="font-bold">{tags.operator}</span></div>}
                        {tags.substation && <div><span className="font-semibold text-muted-foreground">Type</span><br /><span className="font-bold">{tags.substation}</span></div>}
                      </div>
                    </div>
                  </Popup>
                </Marker>
              );
            }

            // ── Power Plants / Generators ──
            if (element.type === 'node' && (tags.power === 'plant' || tags.power === 'generator')) {
              const src = (tags['generator:source'] || tags.source || tags['plant:source'] || '').toLowerCase();
              const genType = src.includes('solar') ? 'solar' : src.includes('wind') ? 'wind' : 'other';
              return (
                <Marker
                  key={`osm-gen-${element.id}-${idx}`}
                  position={[element.lat, element.lon]}
                  icon={createGeneratorIcon(genType)}
                >
                  <Popup>
                    <div className="min-w-[200px] p-1">
                      <h3 className="font-bold text-sm border-b pb-1 mb-2" style={{ color: genType === 'solar' ? '#f59e0b' : genType === 'wind' ? '#0ea5e9' : '#8b5cf6' }}>
                        {genType === 'solar' ? '☀️' : genType === 'wind' ? '🌀' : '⚡'} {tags.name || `${genType.charAt(0).toUpperCase() + genType.slice(1)} Generator`}
                      </h3>
                      <div className="text-xs text-foreground grid grid-cols-2 gap-y-1.5 gap-x-3">
                        {tags['generator:output:electricity'] && <div><span className="font-semibold text-muted-foreground">Output</span><br /><span className="font-bold">{tags['generator:output:electricity']}</span></div>}
                        {tags['plant:output:electricity'] && <div><span className="font-semibold text-muted-foreground">Capacity</span><br /><span className="font-bold">{tags['plant:output:electricity']}</span></div>}
                        {tags.operator && <div className="col-span-2"><span className="font-semibold text-muted-foreground">Operator</span><br /><span className="font-bold">{tags.operator}</span></div>}
                      </div>
                    </div>
                  </Popup>
                </Marker>
              );
            }

            return null;
          })}

          {/* ─── OIM Legend Panel ─── */}
          {showOIM && viewportGrid.length > 0 && (
            <div className="leaflet-bottom leaflet-left" style={{ pointerEvents: 'auto' }}>
              <div className="leaflet-control" style={{
                background: 'rgba(255,255,255,0.95)', borderRadius: 8, padding: '10px 12px',
                fontSize: 10, lineHeight: '18px', boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
                border: '1px solid #e2e8f0', minWidth: 130, marginBottom: 20, marginLeft: 10,
              }}>
                <div style={{ fontWeight: 800, fontSize: 11, marginBottom: 6, color: '#1e293b' }}>Power Lines</div>
                {[
                  { label: '≥ 550 kV', color: '#00bcd4' },
                  { label: '≥ 310 kV', color: '#9c27b0' },
                  { label: '≥ 220 kV', color: '#e53935' },
                  { label: '≥ 132 kV', color: '#ff9800' },
                  { label: '≥ 52 kV', color: '#fdd835' },
                ].map(item => (
                  <div key={item.label} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <div style={{ width: 22, height: 4, borderRadius: 2, background: item.color }} />
                    <span style={{ color: '#475569' }}>{item.label}</span>
                  </div>
                ))}
                <div style={{ fontWeight: 800, fontSize: 11, margin: '8px 0 4px', color: '#1e293b' }}>Infrastructure</div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}><span>🏗️</span><span style={{ color: '#475569' }}>Substation</span></div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}><span>☀️</span><span style={{ color: '#475569' }}>Solar Plant</span></div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}><span>🌀</span><span style={{ color: '#475569' }}>Wind Turbine</span></div>
              </div>
            </div>
          )}

          {/* Overpass Extraction Popup */}
          {clickedLocation && (
            <Popup position={clickedLocation} eventHandlers={{ remove: () => setClickedLocation(null) }}>
              <div className="min-w-[250px] max-w-[350px] max-h-[300px] overflow-y-auto custom-scrollbar">
                <h3 className="font-bold text-sm text-foreground mb-2 border-b pb-1">Real-World Infrastructure</h3>

                {overpassLoading ? (
                  <div className="flex flex-col items-center justify-center p-4 gap-2 text-muted-foreground">
                    <Loader2 className="w-5 h-5 animate-spin text-primary" />
                    <span className="text-xs">Extracting OSM data...</span>
                  </div>
                ) : overpassData && overpassData.length > 0 ? (
                  <div className="flex flex-col gap-3 mt-2">
                    {overpassData.map((item: any, idx: number) => (
                      <div key={idx} className="bg-muted border rounded p-2 shadow-sm">
                        <div className="font-bold text-xs text-indigo-700 uppercase tracking-wider mb-1 flex items-center gap-1.5">
                          {item.tags.power === 'line' ? <Zap className="w-3.5 h-3.5 text-warning" /> : <Layers className="w-3.5 h-3.5 text-primary" />}
                          {item.tags.power} {item.tags.name ? `- ${item.tags.name}` : ''}
                        </div>
                        <div className="text-[11px] text-foreground grid grid-cols-2 gap-x-2 gap-y-1">
                          {item.tags.voltage && <div><span className="font-medium text-muted-foreground">Voltage:</span> {item.tags.voltage}</div>}
                          {item.tags.cables && <div><span className="font-medium text-muted-foreground">Cables:</span> {item.tags.cables}</div>}
                          {item.tags.circuits && <div><span className="font-medium text-muted-foreground">Circuits:</span> {item.tags.circuits}</div>}
                          {item.tags.operator && <div><span className="font-medium text-muted-foreground">Operator:</span> {item.tags.operator}</div>}
                          {item.tags.line && <div className="col-span-2"><span className="font-medium text-muted-foreground">Line Route:</span> {item.tags.line}</div>}
                        </div>
                        <button
                          className="mt-2 w-full text-[10px] font-semibold bg-white border border-border hover:bg-primary/10 hover:border-indigo-300 hover:text-indigo-700 text-foreground py-1.5 rounded transition-colors"
                          onClick={() => alert(`Bound ${item.tags.power} to project!`)}
                        >
                          Bind to Project Data
                        </button>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-xs text-muted-foreground p-2 text-center">
                    No power infrastructure found within 2km.
                  </div>
                )}
              </div>
            </Popup>
          )}

          {/* Custom Dynamic Transmission Lines Network */}
          {(mappedTcEdges.length > 0 ? mappedTcEdges : (showTransmission ? ALL_EDGES : [])).map((edge: any, index: number) => {
            const sourceName = edge.from_label || edge.source;
            const targetName = edge.to_label || edge.target;
            const status = edge.status || edge.normalized_status || 'charged';
            const type = edge.voltage || edge.type || '400kV';

            const start = SUBSTATION_COORDS.find(s => (sourceName || '').toLowerCase().includes(s.name.toLowerCase()));
            const end = SUBSTATION_COORDS.find(s => (targetName || '').toLowerCase().includes(s.name.toLowerCase()));

            if (!start || !end) return null; // Skip if coordinates not found

            return (
              <Polyline
                key={`line-${index}`}
                positions={[[start.lat, start.lng], [end.lat, end.lng]]}
                pathOptions={{
                  color: getEdgeColor(status),
                  weight: type.includes('765') ? 4 : 2,
                  opacity: 0.9,
                  dashArray: getEdgeDash(status),
                  lineCap: 'round'
                }}
              >
                <Popup>
                  <div className="flex flex-col gap-1 min-w-[120px]">
                    <h3 className="font-bold text-sm text-indigo-700">{sourceName} ↔ {targetName}</h3>
                    <div className="text-xs text-foreground">
                      <div>Type/Voltage: {type}</div>
                      <div>Status: <span className="font-semibold" style={{ color: getEdgeColor(status) }}>{status.replace('_', ' ').toUpperCase()}</span></div>
                      {edge.length && <div>Length: {edge.length}</div>}
                    </div>
                  </div>
                </Popup>
              </Polyline>
            );
          })}

          {/* Guaranteed Permanent Markers for Curated Substations */}
          {SUBSTATION_COORDS.map((sub, index) => (
            <Marker
              key={`static-${index}`}
              position={[sub.lat, sub.lng]}
              icon={currentZoom > 6 ? substationMarkerIcon : substationDotIcon}
              eventHandlers={{
                click: () => {
                  setSimLocation({ lat: sub.lat, lng: sub.lng, name: sub.name });
                  if (!showWeatherSim) setShowWeatherSim(true);
                }
              }}
            >
              <Popup>
                <div className="flex flex-col gap-2 min-w-[150px]">
                  <h3 className="font-bold text-sm text-indigo-700">{sub.name}</h3>
                  <div className="text-xs text-foreground">
                    <div>Type: Major Substation / Project Node</div>
                    <div>Lat: {sub.lat} | Lng: {sub.lng}</div>
                  </div>
                </div>
              </Popup>
            </Marker>
          ))}

          {/* Dynamic Markers from Backend Projects */}
          {showProjects && projects.map((project, index) => {
            const coords = getProjectCoordinates(project, index);
            if (!coords) return null; // Skip rendering if no accurate location is found
            
            const projName = project.name || project.projectId;
            return (
              <Marker
                key={project.projectId || index}
                position={[coords[0], coords[1]]}
                icon={currentZoom > 6 ? projectMarkerIcon : projectDotIcon}
                eventHandlers={{
                  click: () => {
                    setSimLocation({ lat: coords[0], lng: coords[1], name: projName });
                    if (!showWeatherSim) setShowWeatherSim(true);
                  }
                }}
              >
                <Popup>
                  <div className="flex flex-col gap-2 min-w-[200px]">
                    <h3 className="font-bold text-sm">{project.name || project.projectId}</h3>
                    <div className="text-xs text-foreground">
                      <div>Status: {project.health || 'N/A'}</div>
                      <div>Progress: {project.progress || 0}%</div>
                    </div>
                    {onOpenProject && (
                      <button
                        onClick={() => onOpenProject(project.projectId)}
                        className="mt-2 text-xs bg-indigo-600 text-white px-3 py-1.5 rounded hover:bg-indigo-700 transition-colors"
                      >
                        View Details
                      </button>
                    )}
                  </div>
                </Popup>
              </Marker>
            );
          })}
        </MapContainer>
      </div>
    </div>
  );
}
