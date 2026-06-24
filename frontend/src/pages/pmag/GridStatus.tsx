import React from 'react';
import {
  Network, CheckCircle2, AlertTriangle, Clock, MapPin, Zap, ArrowRight, Shield, Layers
} from 'lucide-react';

export default function GridStatus({ connectivity, critical_path, theme }: any) {
  const isDark = theme === 'dark';

  return (
    <div className="space-y-4">
      {/* ─── Page Header ─── */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-2">
        <div>
          <h2 className="text-[20px] font-heading font-bold text-foreground">Grid Status & Connectivity</h2>
          <p className="text-[13px] text-muted-foreground mt-1">Real-time status of transmission line routing, substation readiness, and ECOD.</p>
        </div>
        <div className="flex items-center gap-3">
          <select className="bg-card border border-border rounded px-3 py-1.5 text-[12px] text-foreground focus:ring-2 focus:ring-primary focus:border-primary outline-none">
            <option>All Regions</option>
            <option>Northern Grid</option>
            <option>Southern Valley</option>
          </select>
          <button className="bg-primary text-white text-[12px] font-bold px-4 py-1.5 rounded flex items-center gap-2 hover:bg-primary/90 transition-colors">
            Generate Report
          </button>
        </div>
      </div>

      {/* ─── KPI Row ─── */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* KPI 1 */}
        <div className="bento-card p-4 flex flex-col gap-2">
          <div className="flex justify-between items-center text-muted-foreground">
            <span className="text-[10px] font-bold uppercase tracking-wider">Target ECOD</span>
            <Clock className="w-4 h-4" />
          </div>
          <div className="flex items-end gap-2">
            <span className="text-[24px] font-black text-foreground leading-none">Nov 15</span>
            <span className="text-[12px] text-emerald-600 font-bold mb-0.5">On Schedule</span>
          </div>
        </div>
        {/* KPI 2 */}
        <div className="bento-card p-4 flex flex-col gap-2">
          <div className="flex justify-between items-center text-muted-foreground">
            <span className="text-[10px] font-bold uppercase tracking-wider">Substation Readiness</span>
            <Shield className="w-4 h-4" />
          </div>
          <div className="flex items-end gap-2">
            <span className="text-[24px] font-black text-foreground leading-none">82%</span>
            <span className="text-[12px] text-amber-600 font-bold mb-0.5">2 Pending</span>
          </div>
        </div>
        {/* KPI 3 */}
        <div className="bento-card p-4 flex flex-col gap-2">
          <div className="flex justify-between items-center text-muted-foreground">
            <span className="text-[10px] font-bold uppercase tracking-wider">Total Grid Capacity</span>
            <Zap className="w-4 h-4" />
          </div>
          <div className="flex items-end gap-2">
            <span className="text-[24px] font-black text-foreground leading-none">1.2 GW</span>
            <span className="text-[12px] text-muted-foreground font-medium mb-0.5">Synchronized</span>
          </div>
        </div>
      </div>

      {/* ─── Main Content Grid ─── */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        
        {/* Substation Nodes Map Placeholder (Spans 8 cols) */}
        <div className="lg:col-span-8 bento-card flex flex-col h-[450px]">
          <div className="px-5 py-3.5 border-b border-border bg-card flex justify-between items-center shrink-0">
            <h3 className="section-label !text-[12px] !text-foreground flex items-center gap-2">
              <MapPin className="w-4 h-4 text-primary" /> Substation Nodes
            </h3>
            <div className="flex gap-3">
              <span className="inline-flex items-center gap-1.5 text-[11px] text-muted-foreground font-medium">
                <span className="w-2 h-2 rounded-full bg-emerald-500"></span> Active
              </span>
              <span className="inline-flex items-center gap-1.5 text-[11px] text-muted-foreground font-medium">
                <span className="w-2 h-2 rounded-full bg-amber-500"></span> In Progress
              </span>
            </div>
          </div>
          <div className="flex-1 relative bg-slate-100 dark:bg-slate-800/50 overflow-hidden flex items-center justify-center">
            {/* Map Simulation */}
            <div className="absolute inset-0 opacity-20 pointer-events-none" style={{ backgroundImage: 'radial-gradient(circle at 2px 2px, rgba(0,0,0,0.15) 1px, transparent 0)', backgroundSize: '24px 24px' }}></div>
            
            <div className="relative w-full h-full p-8 flex items-center justify-between">
               {/* Node 1 */}
               <div className="flex flex-col items-center group relative">
                 <div className="w-8 h-8 rounded-full bg-emerald-500 border-4 border-card shadow-lg z-10 flex items-center justify-center">
                    <CheckCircle2 className="w-4 h-4 text-white" />
                 </div>
                 <div className="mt-2 text-center">
                   <div className="text-[11px] font-bold text-foreground">Node Alpha</div>
                   <div className="text-[10px] text-emerald-600">Energized</div>
                 </div>
                 <div className="absolute top-4 left-8 w-[150px] h-[3px] bg-emerald-500 z-0"></div>
               </div>

               {/* Node 2 */}
               <div className="flex flex-col items-center group relative">
                 <div className="w-8 h-8 rounded-full bg-amber-500 border-4 border-card shadow-lg z-10 animate-pulse"></div>
                 <div className="mt-2 text-center">
                   <div className="text-[11px] font-bold text-foreground">Substation Beta</div>
                   <div className="text-[10px] text-amber-600">Testing Phase</div>
                 </div>
                 <div className="absolute top-4 left-8 w-[150px] h-[3px] bg-slate-300 dark:bg-slate-700 border-t-2 border-dashed border-amber-500 z-0"></div>
               </div>

               {/* Node 3 */}
               <div className="flex flex-col items-center group relative">
                 <div className="w-8 h-8 rounded-full bg-slate-300 dark:bg-slate-700 border-4 border-card shadow-lg z-10"></div>
                 <div className="mt-2 text-center">
                   <div className="text-[11px] font-bold text-foreground">Gamma Point</div>
                   <div className="text-[10px] text-muted-foreground">Planning</div>
                 </div>
               </div>
            </div>
          </div>
        </div>

        {/* Critical Path Interdependency (Spans 4 cols) */}
        <div className="lg:col-span-4 bento-card flex flex-col h-[450px]">
          <div className="px-4 py-3.5 border-b border-border bg-card flex justify-between items-center shrink-0">
            <h3 className="section-label !text-[12px] !text-foreground flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-amber-500" /> Critical Path
            </h3>
          </div>
          <div className="flex-1 overflow-y-auto p-4 custom-scrollbar">
            <div className="space-y-4 relative before:absolute before:inset-0 before:ml-5 before:-translate-x-px md:before:mx-auto md:before:translate-x-0 before:h-full before:w-0.5 before:bg-gradient-to-b before:from-transparent before:via-slate-200 dark:before:via-slate-700 before:to-transparent">
              
              {/* Item 1 */}
              <div className="relative flex items-center justify-between md:justify-normal md:odd:flex-row-reverse group is-active">
                <div className="flex items-center justify-center w-10 h-10 rounded-full border-4 border-card bg-emerald-500 text-white shrink-0 md:order-1 md:group-odd:-translate-x-1/2 md:group-even:translate-x-1/2 shadow-sm z-10">
                  <CheckCircle2 className="w-4 h-4" />
                </div>
                <div className="w-[calc(100%-4rem)] md:w-[calc(50%-2.5rem)] p-3 rounded-lg border border-border bg-card shadow-sm">
                  <div className="flex items-center justify-between mb-1">
                    <h4 className="font-bold text-[12px] text-foreground">Tower Foundation</h4>
                    <span className="text-[10px] text-emerald-600 font-medium">Done</span>
                  </div>
                  <p className="text-[11px] text-muted-foreground">Sector 4 completely laid out.</p>
                </div>
              </div>

              {/* Item 2 */}
              <div className="relative flex items-center justify-between md:justify-normal md:odd:flex-row-reverse group is-active">
                <div className="flex items-center justify-center w-10 h-10 rounded-full border-4 border-card bg-amber-500 text-white shrink-0 md:order-1 md:group-odd:-translate-x-1/2 md:group-even:translate-x-1/2 shadow-sm z-10">
                  <Clock className="w-4 h-4" />
                </div>
                <div className="w-[calc(100%-4rem)] md:w-[calc(50%-2.5rem)] p-3 rounded-lg border border-amber-200 dark:border-amber-900/50 bg-amber-50 dark:bg-amber-900/10 shadow-sm">
                  <div className="flex items-center justify-between mb-1">
                    <h4 className="font-bold text-[12px] text-foreground">Line Stringing</h4>
                    <span className="text-[10px] text-amber-600 font-bold">In Progress</span>
                  </div>
                  <p className="text-[11px] text-muted-foreground">Delayed due to clearance permit. Blocks downstream.</p>
                </div>
              </div>

              {/* Item 3 */}
              <div className="relative flex items-center justify-between md:justify-normal md:odd:flex-row-reverse group">
                <div className="flex items-center justify-center w-10 h-10 rounded-full border-4 border-card bg-slate-200 dark:bg-slate-700 text-slate-500 shrink-0 md:order-1 md:group-odd:-translate-x-1/2 md:group-even:translate-x-1/2 shadow-sm z-10">
                  <Layers className="w-4 h-4" />
                </div>
                <div className="w-[calc(100%-4rem)] md:w-[calc(50%-2.5rem)] p-3 rounded-lg border border-border bg-card/50 shadow-sm opacity-60">
                  <div className="flex items-center justify-between mb-1">
                    <h4 className="font-bold text-[12px] text-foreground">Testing & Commissioning</h4>
                    <span className="text-[10px] text-muted-foreground">Pending</span>
                  </div>
                  <p className="text-[11px] text-muted-foreground">Waiting on line stringing.</p>
                </div>
              </div>

            </div>
          </div>
        </div>
      </div>

      {/* ─── Site to Transmission Readiness Log ─── */}
      <div className="bento-card overflow-hidden">
        <div className="px-5 py-3.5 border-b border-border bg-card flex justify-between items-center">
          <h3 className="section-label !text-[12px] !text-foreground flex items-center gap-2">
            <Network className="w-4 h-4 text-[#0b74b1]" /> Site to Transmission Readiness Log
          </h3>
          <div className="relative">
            <input 
              type="text" 
              placeholder="Filter by Site ID..." 
              className="pl-8 pr-3 py-1 bg-background border border-border rounded text-[11px] focus:ring-1 focus:ring-primary outline-none"
            />
          </div>
        </div>
        <div className="overflow-x-auto max-h-[400px] overflow-y-auto custom-scrollbar">
          <table className="intel-table">
            <thead className="sticky top-0 z-10">
              <tr>
                <th>Site Name</th>
                <th>Required Substation</th>
                <th>Line Route (%)</th>
                <th>Tower Found. (%)</th>
                <th>Stringing (%)</th>
                <th>Status</th>
                <th>Target ECOD</th>
              </tr>
            </thead>
            <tbody>
              {connectivity.map((c: any, i: number) => (
                <tr key={i}>
                  <td className="font-bold text-foreground">{c.project}</td>
                  <td className="text-muted-foreground">SS-{c.project.substring(0,3).toUpperCase()}-01</td>
                  
                  <td>
                    <div className="flex items-center gap-2">
                      <div className="w-12 h-1.5 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden">
                        <div className="h-full bg-[#0b74b1] rounded-full" style={{ width: '100%' }}></div>
                      </div>
                      <span className="text-[10px] font-bold">100%</span>
                    </div>
                  </td>
                  
                  <td>
                    <div className="flex items-center gap-2">
                      <div className="w-12 h-1.5 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden">
                        <div className="h-full bg-emerald-500 rounded-full" style={{ width: i % 2 === 0 ? '100%' : '60%' }}></div>
                      </div>
                      <span className="text-[10px] font-bold">{i % 2 === 0 ? '100%' : '60%'}</span>
                    </div>
                  </td>

                  <td>
                    <div className="flex items-center gap-2">
                      <div className="w-12 h-1.5 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden">
                        <div className={`h-full rounded-full ${i === 0 ? 'bg-amber-500' : 'bg-[#0b74b1]'}`} style={{ width: i === 0 ? '30%' : '90%' }}></div>
                      </div>
                      <span className="text-[10px] font-bold text-amber-600">{i === 0 ? '30%' : '90%'}</span>
                    </div>
                  </td>

                  <td>
                    <span className={c.scd_status?.toLowerCase().includes('completed') ? 'risk-badge-low' : 'risk-badge-medium'}>
                      {c.scd_status}
                    </span>
                  </td>
                  
                  <td className="font-medium text-foreground">{c.ecod_projection}</td>
                </tr>
              ))}
              {connectivity.length === 0 && (
                <tr>
                  <td colSpan={7} className="text-center py-6 text-muted-foreground text-[12px]">No connectivity data available.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

    </div>
  );
}
