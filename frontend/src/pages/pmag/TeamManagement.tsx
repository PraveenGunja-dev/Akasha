import React from 'react';
import {
  Users, Network, PieChart, CheckSquare, Search, MoreVertical, Filter, TrendingUp,
  ShieldAlert, UserPlus, Settings2
} from 'lucide-react';

export default function TeamManagement({ data, theme }: any) {
  const isDark = theme === 'dark';
  const { kpis, members, activity_log } = data || {
    kpis: { total_personnel: 0, active_projects: 0, avg_allocation_pct: 0, dpr_submission_rate_pct: 0 },
    members: [],
    activity_log: []
  };

  return (
    <div className="space-y-4">
      {/* ─── Page Header ─── */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-2">
        <div>
          <h2 className="text-[20px] font-heading font-bold text-foreground">Team & Stakeholders</h2>
          <p className="text-[13px] text-muted-foreground mt-1">Manage PMO staff, project assignments, and governance permissions.</p>
        </div>
        <div className="flex gap-3">
          <button className="flex items-center gap-2 bg-card border border-border text-foreground text-[12px] px-4 py-1.5 rounded hover:bg-muted dark:hover:bg-card transition-colors shadow-sm">
            <Settings2 className="w-4 h-4" /> Permissions
          </button>
          <button className="flex items-center gap-2 bg-primary text-white text-[12px] font-bold px-4 py-1.5 rounded hover:bg-primary/90 transition-colors shadow-sm">
            <UserPlus className="w-4 h-4" /> Add Member
          </button>
        </div>
      </div>

      {/* ─── KPI Row ─── */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bento-card p-4 flex flex-col gap-2">
          <div className="flex justify-between items-center text-muted-foreground">
            <span className="text-[10px] font-bold uppercase tracking-wider">Total Personnel</span>
            <Users className="w-4 h-4" />
          </div>
          <div className="flex items-end gap-2">
            <span className="text-[24px] font-black text-foreground leading-none">{kpis.total_personnel}</span>
            <span className="text-[12px] text-primary font-bold mb-0.5 flex items-center">
              <TrendingUp className="w-3 h-3 mr-1" /> 4
            </span>
          </div>
        </div>
        <div className="bento-card p-4 flex flex-col gap-2">
          <div className="flex justify-between items-center text-muted-foreground">
            <span className="text-[10px] font-bold uppercase tracking-wider">Active Projects</span>
            <Network className="w-4 h-4" />
          </div>
          <div className="flex items-end gap-2">
            <span className="text-[24px] font-black text-foreground leading-none">{kpis.active_projects}</span>
          </div>
        </div>
        <div className="bento-card p-4 flex flex-col gap-2">
          <div className="flex justify-between items-center text-muted-foreground">
            <span className="text-[10px] font-bold uppercase tracking-wider">Avg Allocation</span>
            <PieChart className="w-4 h-4" />
          </div>
          <div className="flex items-end gap-2">
            <span className="text-[24px] font-black text-foreground leading-none">{kpis.avg_allocation_pct}%</span>
            <span className="text-[12px] text-muted-foreground font-medium mb-0.5">Capacity</span>
          </div>
        </div>
        <div className="bento-card p-4 flex flex-col gap-2">
          <div className="flex justify-between items-center text-muted-foreground">
            <span className="text-[10px] font-bold uppercase tracking-wider">DPR Submission</span>
            <CheckSquare className="w-4 h-4" />
          </div>
          <div className="flex items-end gap-2">
            <span className="text-[24px] font-black text-foreground leading-none">{kpis.dpr_submission_rate_pct}%</span>
            <span className="text-[12px] text-destructive font-bold mb-0.5 flex items-center">
              - 2%
            </span>
          </div>
        </div>
      </div>

      {/* ─── Main Content Grid ─── */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 h-[600px]">
        
        {/* Member Directory Table (Spans 8 cols) */}
        <div className="lg:col-span-8 bento-card flex flex-col overflow-hidden">
          <div className="px-5 py-3.5 border-b border-border bg-card flex justify-between items-center shrink-0">
            <h3 className="section-label !text-[12px] !text-foreground flex items-center gap-2">
              <Users className="w-4 h-4 text-primary" /> Member Directory
            </h3>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <input 
                type="text" 
                placeholder="Search by name, role..." 
                className="pl-9 pr-4 py-1.5 bg-background border border-border rounded text-[12px] text-foreground focus:ring-1 focus:ring-primary outline-none w-64"
              />
            </div>
          </div>
          <div className="flex-1 overflow-x-auto overflow-y-auto custom-scrollbar">
            <table className="intel-table">
              <thead className="sticky top-0 z-10 bg-card">
                <tr>
                  <th>Personnel</th>
                  <th>Role & Level</th>
                  <th>Primary Assignment</th>
                  <th className="text-center">Alloc.</th>
                  <th>Status</th>
                  <th className="text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {members.map((m: any, i: number) => (
                  <tr key={i} className="hover:bg-muted dark:hover:bg-white/50 transition-colors">
                    <td>
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center text-primary font-bold text-[12px]">
                          {m.name.split(' ').map((n: string) => n[0]).join('')}
                        </div>
                        <div>
                          <p className="font-bold text-[12px] text-foreground">{m.name}</p>
                          <p className="text-[10px] text-muted-foreground">{m.email}</p>
                        </div>
                      </div>
                    </td>
                    <td>
                      <p className="font-medium text-[11px] text-foreground">{m.role}</p>
                      <p className="text-[10px] text-muted-foreground">{m.level}</p>
                    </td>
                    <td className="text-[11px] text-muted-foreground font-medium">{m.assignment}</td>
                    <td className="text-center">
                      <div className="w-full bg-muted dark:bg-card rounded-full h-1.5 mt-1">
                        <div className={`h-1.5 rounded-full ${m.allocation > 100 ? 'bg-destructive/100' : 'bg-primary'}`} style={{ width: `${Math.min(m.allocation, 100)}%` }}></div>
                      </div>
                      <span className={`text-[10px] ${m.allocation > 100 ? 'text-destructive font-bold' : 'text-muted-foreground'}`}>{m.allocation}%</span>
                    </td>
                    <td>
                      <span className={m.allocation > 100 ? 'risk-badge-high' : m.status === 'Active' ? 'risk-badge-low' : 'risk-badge-medium'}>
                        {m.status}
                      </span>
                    </td>
                    <td className="text-right">
                      <button className="p-1 text-muted-foreground hover:text-primary transition-colors">
                        <MoreVertical className="w-4 h-4" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Side Widgets (Spans 4 cols) */}
        <div className="lg:col-span-4 flex flex-col gap-4 h-full">
          
          {/* Capacity Heatmap */}
          <div className="bento-card p-4 flex-1 flex flex-col">
            <div className="flex justify-between items-center mb-4 shrink-0">
              <h3 className="section-label !text-[12px] !text-foreground flex items-center gap-2">
                <PieChart className="w-4 h-4 text-primary" /> Capacity Heatmap
              </h3>
              <button className="text-muted-foreground hover:text-primary"><Filter className="w-4 h-4" /></button>
            </div>
            <div className="flex-1 overflow-y-auto custom-scrollbar pr-1">
              {/* Heatmap Grid Simulation */}
              <div className="grid grid-cols-[1fr_repeat(4,_minmax(0,_1fr))] gap-1 text-[10px] font-bold text-muted-foreground mb-2 px-1">
                <div>Role/Dept</div>
                <div className="text-center">W1</div>
                <div className="text-center">W2</div>
                <div className="text-center">W3</div>
                <div className="text-center">W4</div>
              </div>
              <div className="flex flex-col gap-2">
                {/* Dept 1 */}
                <div className="grid grid-cols-[1fr_repeat(4,_minmax(0,_1fr))] gap-1 items-center px-1">
                  <div className="truncate text-[11px] font-bold text-foreground">Engineering</div>
                  <div className="h-6 bg-success/100/20 text-success dark:text-success rounded-sm flex items-center justify-center text-[10px] font-medium border border-success/20">85%</div>
                  <div className="h-6 bg-destructive/100/20 text-destructive dark:text-destructive rounded-sm flex items-center justify-center text-[10px] font-bold border border-destructive/20">105%</div>
                  <div className="h-6 bg-warning/100/20 text-warning dark:text-warning rounded-sm flex items-center justify-center text-[10px] font-medium border border-warning/20">95%</div>
                  <div className="h-6 bg-success/100/20 text-success dark:text-success rounded-sm flex items-center justify-center text-[10px] font-medium border border-success/20">80%</div>
                </div>
                {/* Dept 2 */}
                <div className="grid grid-cols-[1fr_repeat(4,_minmax(0,_1fr))] gap-1 items-center px-1">
                  <div className="truncate text-[11px] font-bold text-foreground">Project Mgmt</div>
                  <div className="h-6 bg-success/100/20 text-success dark:text-success rounded-sm flex items-center justify-center text-[10px] font-medium border border-success/20">70%</div>
                  <div className="h-6 bg-success/100/20 text-success dark:text-success rounded-sm flex items-center justify-center text-[10px] font-medium border border-success/20">75%</div>
                  <div className="h-6 bg-success/100/20 text-success dark:text-success rounded-sm flex items-center justify-center text-[10px] font-medium border border-success/20">80%</div>
                  <div className="h-6 bg-success/100/20 text-success dark:text-success rounded-sm flex items-center justify-center text-[10px] font-medium border border-success/20">85%</div>
                </div>
                {/* Dept 3 */}
                <div className="grid grid-cols-[1fr_repeat(4,_minmax(0,_1fr))] gap-1 items-center px-1">
                  <div className="truncate text-[11px] font-bold text-foreground">Field Ops</div>
                  <div className="h-6 bg-destructive/100/20 text-destructive dark:text-destructive rounded-sm flex items-center justify-center text-[10px] font-bold border border-destructive/20">110%</div>
                  <div className="h-6 bg-destructive/100/20 text-destructive dark:text-destructive rounded-sm flex items-center justify-center text-[10px] font-bold border border-destructive/20">110%</div>
                  <div className="h-6 bg-warning/100/20 text-warning dark:text-warning rounded-sm flex items-center justify-center text-[10px] font-medium border border-warning/20">98%</div>
                  <div className="h-6 bg-success/100/20 text-success dark:text-success rounded-sm flex items-center justify-center text-[10px] font-medium border border-success/20">90%</div>
                </div>
                {/* Dept 4 */}
                <div className="grid grid-cols-[1fr_repeat(4,_minmax(0,_1fr))] gap-1 items-center px-1">
                  <div className="truncate text-[11px] font-bold text-foreground">Risk & Comp</div>
                  <div className="h-6 bg-slate-200 dark:bg-card text-foreground dark:text-muted-foreground rounded-sm flex items-center justify-center text-[10px] font-medium border border-border dark:border-slate-700">40%</div>
                  <div className="h-6 bg-slate-200 dark:bg-card text-foreground dark:text-muted-foreground rounded-sm flex items-center justify-center text-[10px] font-medium border border-border dark:border-slate-700">40%</div>
                  <div className="h-6 bg-success/100/20 text-success dark:text-success rounded-sm flex items-center justify-center text-[10px] font-medium border border-success/20">50%</div>
                  <div className="h-6 bg-success/100/20 text-success dark:text-success rounded-sm flex items-center justify-center text-[10px] font-medium border border-success/20">60%</div>
                </div>
              </div>
            </div>
            <div className="mt-4 pt-3 border-t border-border flex justify-between text-[10px] font-bold text-muted-foreground shrink-0">
              <div className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-sm bg-success/100/50 border border-emerald-500/50"></span> Optimal</div>
              <div className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-sm bg-warning/100/50 border border-amber-500/50"></span> High</div>
              <div className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-sm bg-destructive/100/50 border border-red-500/50"></span> Over (100%+)</div>
            </div>
          </div>

          {/* DPR Performance Tracker */}
          <div className="bento-card p-4 h-48 flex flex-col shrink-0">
            <div className="flex justify-between items-center mb-1">
              <h3 className="section-label !text-[12px] !text-foreground">DPR Submission Perf.</h3>
              <TrendingUp className="w-4 h-4 text-primary" />
            </div>
            <p className="text-[10px] text-muted-foreground mb-3">Daily compliance across all active projects.</p>
            <div className="flex-1 flex items-end gap-2 px-1">
              {/* Bar Chart Simulation */}
              <div className="flex-1 bg-primary/20 rounded-t h-[60%] relative group">
                <div className="absolute -top-6 left-1/2 -translate-x-1/2 bg-foreground text-background text-[10px] font-bold px-1.5 py-0.5 rounded opacity-0 group-hover:opacity-100 transition-opacity">92%</div>
              </div>
              <div className="flex-1 bg-primary/20 rounded-t h-[75%] relative group">
                <div className="absolute -top-6 left-1/2 -translate-x-1/2 bg-foreground text-background text-[10px] font-bold px-1.5 py-0.5 rounded opacity-0 group-hover:opacity-100 transition-opacity">95%</div>
              </div>
              <div className="flex-1 bg-primary/20 rounded-t h-[40%] relative group">
                <div className="absolute -top-6 left-1/2 -translate-x-1/2 bg-foreground text-background text-[10px] font-bold px-1.5 py-0.5 rounded opacity-0 group-hover:opacity-100 transition-opacity">80%</div>
              </div>
              <div className="flex-1 bg-primary rounded-t h-[85%] relative group shadow-sm shadow-primary/20">
                <div className="absolute -top-6 left-1/2 -translate-x-1/2 bg-foreground text-background text-[10px] font-bold px-1.5 py-0.5 rounded opacity-0 group-hover:opacity-100 transition-opacity">98%</div>
              </div>
              <div className="flex-1 bg-primary/20 rounded-t h-[70%] relative group">
                <div className="absolute -top-6 left-1/2 -translate-x-1/2 bg-foreground text-background text-[10px] font-bold px-1.5 py-0.5 rounded opacity-0 group-hover:opacity-100 transition-opacity">94%</div>
              </div>
            </div>
            <div className="flex justify-between text-[10px] font-bold text-muted-foreground mt-1 border-t border-border pt-1">
              <span>Wk 1</span>
              <span>Wk 2</span>
              <span>Wk 3</span>
              <span>Wk 4</span>
              <span>Current</span>
            </div>
          </div>
        </div>
      </div>

      {/* ─── Bottom Section: Governance Activity Log ─── */}
      <div className="bento-card p-5">
        <div className="flex justify-between items-center mb-4 border-b border-border pb-3">
          <h3 className="section-label !text-[12px] !text-foreground flex items-center gap-2">
            <ShieldAlert className="w-4 h-4 text-accent" /> Governance & Activity Log
          </h3>
          <button className="text-[11px] text-primary font-bold hover:underline">View All Logs</button>
        </div>
        <div className="flex flex-col">
          {activity_log.map((log: any, i: number) => (
            <div key={i} className="flex gap-4 py-3 border-b border-border/50 last:border-0 hover:bg-muted dark:hover:bg-white/50 transition-colors px-2 rounded">
              <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${
                log.type === 'admin' ? 'bg-primary/10 text-primary' : 
                log.type === 'alert' ? 'bg-destructive/100/10 text-destructive' : 'bg-slate-200 dark:bg-card text-muted-foreground dark:text-muted-foreground'
              }`}>
                {log.type === 'admin' ? <Settings2 className="w-4 h-4" /> : log.type === 'alert' ? <ShieldAlert className="w-4 h-4" /> : <Users className="w-4 h-4" />}
              </div>
              <div className="flex-1">
                <p className="text-[12px] text-foreground">
                  <strong>{log.user}</strong> {log.action} <span className="font-bold text-primary">{log.target}</span>.
                </p>
                <p className="text-[11px] text-muted-foreground">{log.details}</p>
              </div>
              <div className="text-[10px] font-medium text-muted-foreground whitespace-nowrap">
                {log.time}
              </div>
            </div>
          ))}
        </div>
      </div>

    </div>
  );
}
