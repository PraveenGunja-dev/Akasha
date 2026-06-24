import React from 'react';
import {
  Zap, Sun, Wind, Activity, MapPin, AlertTriangle, Info, RefreshCw, Thermometer
} from 'lucide-react';

export default function SiteMonitoring({ data, theme }: any) {
  const isDark = theme === 'dark';
  const { telemetry, equipment_health, alerts } = data || {
    telemetry: { total_output_mw: 0, avg_irradiance_wm2: 0, wind_speed_ms: 0, grid_sync_pct: 0 },
    equipment_health: [],
    alerts: []
  };

  return (
    <div className="space-y-4">
      {/* ─── Page Header & Filters ─── */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-2">
        <div>
          <h2 className="text-[20px] font-heading font-bold text-foreground">Site Monitoring Overview</h2>
          <p className="text-[13px] text-muted-foreground mt-1">Live telemetry and health status across all active assets.</p>
        </div>
        <div className="flex items-center gap-3">
          <select className="bg-card border border-border rounded px-3 py-1.5 text-[12px] text-foreground focus:ring-2 focus:ring-primary focus:border-primary outline-none">
            <option>All Regions</option>
            <option>Northern Grid</option>
            <option>Southern Valley</option>
          </select>
          <select className="bg-card border border-border rounded px-3 py-1.5 text-[12px] text-foreground focus:ring-2 focus:ring-primary focus:border-primary outline-none">
            <option>All Projects Types</option>
            <option>Solar PV</option>
            <option>Wind Offshore</option>
            <option>Hydroelectric</option>
          </select>
          <button className="p-1.5 border border-border rounded hover:bg-slate-50 dark:hover:bg-slate-800 text-muted-foreground transition-colors shadow-sm">
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* ─── Main Grid ─── */}
      <div className="grid grid-cols-1 md:grid-cols-12 gap-4">
        
        {/* Map View Widget (Col 8) */}
        <div className="md:col-span-8 bento-card flex flex-col overflow-hidden h-[400px]">
          <div className="px-5 py-3.5 border-b border-border bg-card flex justify-between items-center shrink-0">
            <h3 className="section-label !text-[12px] !text-foreground flex items-center gap-2">
              <MapPin className="w-4 h-4 text-primary" /> Asset Geography
            </h3>
            <div className="flex gap-3">
              <span className="inline-flex items-center gap-1.5 text-[11px] text-muted-foreground font-medium">
                <span className="w-2 h-2 rounded-full bg-primary"></span> Optimal
              </span>
              <span className="inline-flex items-center gap-1.5 text-[11px] text-muted-foreground font-medium">
                <span className="w-2 h-2 rounded-full bg-red-500"></span> Alert
              </span>
            </div>
          </div>
          <div className="flex-1 relative bg-slate-100 dark:bg-slate-800/30 overflow-hidden group/map">
            {/* Map Placeholder Image or Vector */}
            <div className="absolute inset-0 opacity-[0.15] dark:opacity-10 pointer-events-none" style={{ backgroundImage: 'radial-gradient(circle at 10px 10px, rgba(0,0,0,0.4) 1px, transparent 0)', backgroundSize: '40px 40px' }}></div>
            
            {/* Simulated Map Pins */}
            <div className="absolute top-[30%] left-[40%] flex flex-col items-center group cursor-pointer z-10">
              <div className="w-4 h-4 rounded-full bg-primary border-2 border-card shadow-sm z-10 transition-transform group-hover:scale-125"></div>
              <div className="bg-foreground text-background px-2 py-1 rounded text-[10px] font-bold mt-1 absolute top-full hidden group-hover:block whitespace-nowrap z-20 shadow-lg">
                Solar Farm Alpha
              </div>
            </div>
            
            <div className="absolute top-[60%] left-[70%] flex flex-col items-center group cursor-pointer z-10">
              <div className="w-4 h-4 rounded-full bg-red-500 border-2 border-card shadow-sm z-10 animate-pulse transition-transform group-hover:scale-125"></div>
              <div className="bg-foreground text-background px-2 py-1 rounded text-[10px] font-bold mt-1 absolute top-full hidden group-hover:block whitespace-nowrap z-20 shadow-lg">
                Wind Park Beta (Turbine Fault)
              </div>
            </div>

            <div className="absolute bottom-4 right-4 bg-card/80 backdrop-blur border border-border px-3 py-1.5 rounded shadow-sm text-[10px] font-bold text-muted-foreground">
              Northern Grid Region
            </div>
          </div>
        </div>

        {/* Telemetry Feeds Widget (Col 4) */}
        <div className="md:col-span-4 grid grid-cols-2 gap-4">
          {/* KPI 1 */}
          <div className="bento-card p-4 flex flex-col justify-between hover:border-primary/30 transition-colors">
            <div className="flex justify-between items-start mb-2">
              <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Total Output</span>
              <Zap className="w-4 h-4 text-primary" />
            </div>
            <div>
              <div className="text-[22px] font-black text-foreground leading-none">{telemetry.total_output_mw} <span className="text-[11px] font-medium text-muted-foreground">MW</span></div>
              <div className="text-[10px] font-bold text-primary mt-1 flex items-center">
                <Activity className="w-3 h-3 mr-1" /> +2.4% vs prev hr
              </div>
            </div>
          </div>
          {/* KPI 2 */}
          <div className="bento-card p-4 flex flex-col justify-between hover:border-amber-500/30 transition-colors">
            <div className="flex justify-between items-start mb-2">
              <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Avg Irradiance</span>
              <Sun className="w-4 h-4 text-amber-500" />
            </div>
            <div>
              <div className="text-[22px] font-black text-foreground leading-none">{telemetry.avg_irradiance_wm2} <span className="text-[11px] font-medium text-muted-foreground">W/m²</span></div>
              <div className="text-[10px] font-medium text-muted-foreground mt-1">Optimal range</div>
            </div>
          </div>
          {/* KPI 3 */}
          <div className="bento-card p-4 flex flex-col justify-between hover:border-blue-500/30 transition-colors">
            <div className="flex justify-between items-start mb-2">
              <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Wind Speed</span>
              <Wind className="w-4 h-4 text-blue-500" />
            </div>
            <div>
              <div className="text-[22px] font-black text-foreground leading-none">{telemetry.wind_speed_ms} <span className="text-[11px] font-medium text-muted-foreground">m/s</span></div>
              <div className="text-[10px] font-bold text-red-500 mt-1 flex items-center">
                <Activity className="w-3 h-3 mr-1" /> -1.2% dropping
              </div>
            </div>
          </div>
          {/* KPI 4 */}
          <div className="bento-card p-4 flex flex-col justify-between hover:border-emerald-500/30 transition-colors">
            <div className="flex justify-between items-start mb-2">
              <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Grid Sync</span>
              <Activity className="w-4 h-4 text-emerald-500" />
            </div>
            <div>
              <div className="text-[22px] font-black text-foreground leading-none">{telemetry.grid_sync_pct} <span className="text-[11px] font-medium text-muted-foreground">%</span></div>
              <div className="text-[10px] font-medium text-muted-foreground mt-1">Stable connection</div>
            </div>
          </div>
        </div>

        {/* Equipment Health Widget (Col 7) */}
        <div className="md:col-span-7 bento-card flex flex-col overflow-hidden">
          <div className="px-5 py-3.5 border-b border-border bg-card flex justify-between items-center shrink-0">
            <h3 className="section-label !text-[12px] !text-foreground flex items-center gap-2">
              <Activity className="w-4 h-4 text-emerald-500" /> Equipment Health Status
            </h3>
            <button className="text-[11px] text-primary font-bold hover:underline">View All Assets</button>
          </div>
          <div className="flex-1 overflow-x-auto overflow-y-auto custom-scrollbar">
            <table className="intel-table">
              <thead className="sticky top-0 z-10 bg-card">
                <tr>
                  <th>Site ID</th>
                  <th>Type</th>
                  <th>Equipment Focus</th>
                  <th>Efficiency</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {equipment_health.map((eq: any, i: number) => (
                  <tr key={i} className="hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors">
                    <td className="font-bold text-foreground whitespace-nowrap">{eq.id}</td>
                    <td>
                      <span className="flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground">
                        {eq.type === 'Solar' ? <Sun className="w-3 h-3 text-amber-500" /> : eq.type === 'Wind' ? <Wind className="w-3 h-3 text-blue-500" /> : <Zap className="w-3 h-3 text-cyan-500" />}
                        {eq.type}
                      </span>
                    </td>
                    <td className="text-[11px] font-medium text-muted-foreground">{eq.focus}</td>
                    <td className="font-bold text-foreground">{eq.efficiency}%</td>
                    <td>
                      <span className={
                        eq.status === 'OPERATIONAL' ? 'risk-badge-low' : 
                        eq.status === 'MAINTENANCE REQ' ? 'risk-badge-high' : 
                        eq.status === 'DEGRADED' ? 'text-[10px] px-2 py-0.5 rounded bg-amber-50 text-amber-600 dark:bg-amber-500/10 dark:text-amber-500 font-bold border border-amber-200 dark:border-amber-500/30' : 
                        'text-[10px] px-2 py-0.5 rounded bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400 font-bold border border-slate-200 dark:border-slate-700'
                      }>
                        {eq.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Site-Specific Alert Log (Col 5) */}
        <div className="md:col-span-5 bento-card flex flex-col overflow-hidden">
          <div className="px-5 py-3.5 border-b border-border bg-card flex justify-between items-center shrink-0">
            <h3 className="section-label !text-[12px] !text-foreground flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-red-500" /> Recent Alerts
            </h3>
            <span className="bg-red-500 text-white text-[10px] font-bold px-2 py-0.5 rounded-full">{alerts.length} Active</span>
          </div>
          <div className="flex-1 overflow-y-auto p-3 space-y-3 custom-scrollbar bg-slate-50 dark:bg-slate-900/20">
            {alerts.map((a: any, i: number) => (
              <div key={i} className={`p-3 rounded-lg flex gap-3 items-start border shadow-sm ${
                a.level === 'critical' ? 'bg-red-50 dark:bg-red-950/20 border-red-200 dark:border-red-900/50' : 
                a.level === 'warning' ? 'bg-amber-50 dark:bg-amber-950/20 border-amber-200 dark:border-amber-900/50' : 
                'bg-card border-border'
              }`}>
                <div className="shrink-0 mt-0.5">
                  {a.level === 'critical' ? <AlertTriangle className="w-4 h-4 text-red-500" /> : 
                   a.level === 'warning' ? <Thermometer className="w-4 h-4 text-amber-500" /> : 
                   <Info className="w-4 h-4 text-slate-500" />}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex justify-between items-center mb-1">
                    <h4 className="font-bold text-[12px] text-foreground truncate">{a.title}</h4>
                    <span className="text-[10px] text-muted-foreground shrink-0">{a.time}</span>
                  </div>
                  <p className="text-[11px] text-muted-foreground leading-relaxed">{a.desc}</p>
                  
                  {a.level === 'critical' && (
                    <div className="mt-2.5 flex gap-3">
                      <button className="text-[10px] font-bold text-red-600 dark:text-red-400 hover:underline uppercase tracking-wider">Acknowledge</button>
                      <button className="text-[10px] font-bold text-primary hover:underline uppercase tracking-wider">Create Ticket</button>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>

      </div>
    </div>
  );
}
