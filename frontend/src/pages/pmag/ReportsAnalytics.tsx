import React, { useState } from 'react';
import {
  FileText, Download, Filter, Search, Calendar, HardDrive, 
  Settings, Clock, FileDown, Plus, Play, Pause, ChevronRight
} from 'lucide-react';

export default function ReportsAnalytics({ data, theme }: any) {
  const isDark = theme === 'dark';
  const { kpis, reports, schedules } = data || {
    kpis: { generated_this_month: 0, scheduled_tasks: 0, storage_used_gb: 0 },
    reports: [],
    schedules: []
  };

  const [activeCategory, setActiveCategory] = useState('All');

  return (
    <div className="space-y-4">
      {/* ─── Page Header ─── */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-2">
        <div>
          <h2 className="text-[20px] font-heading font-bold text-foreground">Governance Reports</h2>
          <p className="text-[13px] text-muted-foreground mt-1">Access, generate, and schedule automated reporting for all project nodes.</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="relative hidden md:block">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <input 
              type="text" 
              placeholder="Search reports..." 
              className="pl-9 pr-4 py-1.5 bg-card border border-border rounded text-[12px] text-foreground focus:ring-2 focus:ring-primary focus:border-primary outline-none w-64"
            />
          </div>
          <button className="p-1.5 border border-border rounded bg-card hover:bg-muted dark:hover:bg-card text-muted-foreground transition-colors">
            <Filter className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* ─── KPI Row ─── */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* KPI 1 */}
        <div className="bento-card p-4 flex items-center justify-between">
          <div>
            <p className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider mb-1">Generated This Month</p>
            <div className="flex items-end gap-2">
              <span className="text-[28px] font-black text-foreground leading-none">{kpis.generated_this_month}</span>
              <span className="text-[12px] text-success font-bold mb-1 flex items-center">+12%</span>
            </div>
          </div>
          <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center">
            <FileText className="w-5 h-5 text-primary" />
          </div>
        </div>
        {/* KPI 2 */}
        <div className="bento-card p-4 flex items-center justify-between">
          <div>
            <p className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider mb-1">Scheduled Tasks</p>
            <div className="flex items-end gap-2">
              <span className="text-[28px] font-black text-foreground leading-none">{kpis.scheduled_tasks}</span>
              <span className="text-[12px] text-muted-foreground font-medium mb-1">Active</span>
            </div>
          </div>
          <div className="w-10 h-10 rounded-full bg-warning/100/10 flex items-center justify-center">
            <Calendar className="w-5 h-5 text-warning" />
          </div>
        </div>
        {/* KPI 3 */}
        <div className="bento-card p-4 flex items-center justify-between">
          <div>
            <p className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider mb-1">Storage Used</p>
            <div className="flex items-end gap-2">
              <span className="text-[28px] font-black text-foreground leading-none">{kpis.storage_used_gb}</span>
              <span className="text-[12px] text-muted-foreground font-medium mb-1">GB</span>
            </div>
          </div>
          <div className="w-10 h-10 rounded-full bg-slate-200 dark:bg-card flex items-center justify-center">
            <HardDrive className="w-5 h-5 text-muted-foreground dark:text-muted-foreground" />
          </div>
        </div>
      </div>

      {/* ─── Main Content Grid ─── */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        
        {/* Report Repository (Spans 8 cols) */}
        <div className="lg:col-span-8 bento-card flex flex-col h-[500px]">
          <div className="px-5 py-3.5 border-b border-border bg-card flex flex-col gap-3">
            <div className="flex justify-between items-center">
              <h3 className="section-label !text-[12px] !text-foreground flex items-center gap-2">
                <FileText className="w-4 h-4 text-primary" /> Report Repository
              </h3>
            </div>
            {/* Tabs */}
            <div className="flex gap-4 border-b border-border text-[12px] font-bold">
              {['All', 'Governance', 'Progress', 'Financial'].map(tab => (
                <button
                  key={tab}
                  className={`pb-2 px-1 transition-colors ${activeCategory === tab ? 'text-primary border-b-2 border-primary' : 'text-muted-foreground hover:text-foreground'}`}
                  onClick={() => setActiveCategory(tab)}
                >
                  {tab}
                </button>
              ))}
            </div>
          </div>
          <div className="flex-1 overflow-x-auto overflow-y-auto custom-scrollbar">
            <table className="intel-table">
              <thead className="sticky top-0 z-10 bg-card">
                <tr>
                  <th>Report Name</th>
                  <th>Date</th>
                  <th>Category</th>
                  <th>Format</th>
                  <th>Status</th>
                  <th className="text-right">Action</th>
                </tr>
              </thead>
              <tbody>
                {reports
                  .filter((r: any) => activeCategory === 'All' || r.category === activeCategory)
                  .map((r: any, i: number) => (
                  <tr key={i} className="hover:bg-muted dark:hover:bg-white/50 transition-colors">
                    <td className="font-bold text-foreground flex items-center gap-2">
                      <FileDown className="w-4 h-4 text-muted-foreground" />
                      {r.name}
                    </td>
                    <td className="text-muted-foreground">{r.date}</td>
                    <td>
                      <span className="text-[10px] px-2 py-0.5 rounded bg-muted dark:bg-card text-foreground dark:text-muted-foreground font-bold border border-border">
                        {r.category}
                      </span>
                    </td>
                    <td className="text-[11px] font-bold text-muted-foreground">{r.format}</td>
                    <td>
                      {r.status === 'Ready' ? (
                        <span className="risk-badge-low">Ready</span>
                      ) : (
                        <span className="text-[10px] px-2 py-0.5 rounded bg-warning/10 text-warning dark:bg-warning/100/10 dark:text-warning font-bold border border-warning/20 dark:border-warning/20 flex items-center gap-1 w-fit">
                          <Clock className="w-3 h-3" /> Processing
                        </span>
                      )}
                    </td>
                    <td className="text-right">
                      <button className="p-1 text-primary hover:bg-primary/10 rounded transition-colors" disabled={r.status !== 'Ready'}>
                        <Download className="w-4 h-4" />
                      </button>
                    </td>
                  </tr>
                ))}
                {reports.length === 0 && (
                  <tr>
                    <td colSpan={6} className="text-center py-8 text-muted-foreground text-[12px]">No reports found for this category.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Side Widgets (Spans 4 cols) */}
        <div className="lg:col-span-4 flex flex-col gap-4 h-full">
          
          {/* Custom Builder Form */}
          <div className="bento-card p-4 flex-1 flex flex-col">
            <h3 className="section-label !text-[12px] !text-foreground flex items-center gap-2 mb-4">
              <Settings className="w-4 h-4 text-primary" /> Custom Builder
            </h3>
            <div className="space-y-3 flex-1">
              <div>
                <label className="block text-[11px] font-bold text-muted-foreground mb-1">Report Type</label>
                <select className="w-full bg-background border border-border rounded px-3 py-1.5 text-[12px] text-foreground outline-none focus:border-primary">
                  <option>Detailed Site Overview</option>
                  <option>Financial Summary</option>
                  <option>Risk & Compliance</option>
                </select>
              </div>
              <div>
                <label className="block text-[11px] font-bold text-muted-foreground mb-1">Date Range</label>
                <select className="w-full bg-background border border-border rounded px-3 py-1.5 text-[12px] text-foreground outline-none focus:border-primary">
                  <option>Last 30 Days</option>
                  <option>This Quarter</option>
                  <option>Year to Date</option>
                  <option>Custom Range...</option>
                </select>
              </div>
              <div>
                <label className="block text-[11px] font-bold text-muted-foreground mb-1">Include Modules</label>
                <div className="grid grid-cols-2 gap-2 text-[11px] text-foreground">
                  <label className="flex items-center gap-1.5"><input type="checkbox" defaultChecked className="rounded border-border text-primary focus:ring-primary" /> Financials</label>
                  <label className="flex items-center gap-1.5"><input type="checkbox" defaultChecked className="rounded border-border text-primary focus:ring-primary" /> Schedules</label>
                  <label className="flex items-center gap-1.5"><input type="checkbox" className="rounded border-border text-primary focus:ring-primary" /> Resources</label>
                  <label className="flex items-center gap-1.5"><input type="checkbox" className="rounded border-border text-primary focus:ring-primary" /> Risks</label>
                </div>
              </div>
            </div>
            <button className="w-full bg-primary text-white text-[12px] font-bold py-2 rounded mt-4 hover:bg-primary/90 transition-colors flex justify-center items-center gap-2">
              <Plus className="w-4 h-4" /> Generate Report
            </button>
          </div>

          {/* Automation Schedules */}
          <div className="bento-card p-4 flex-1 flex flex-col">
            <div className="flex justify-between items-center mb-4">
              <h3 className="section-label !text-[12px] !text-foreground flex items-center gap-2">
                <Clock className="w-4 h-4 text-accent" /> Automation Schedules
              </h3>
              <button className="text-[11px] text-primary font-bold hover:underline">Manage</button>
            </div>
            <div className="space-y-3 flex-1 overflow-y-auto custom-scrollbar pr-1">
              {schedules.map((s: any, i: number) => (
                <div key={i} className="flex items-center justify-between p-3 border border-border rounded-lg bg-card hover:bg-muted dark:hover:bg-card transition-colors">
                  <div>
                    <h4 className="text-[12px] font-bold text-foreground mb-0.5">{s.name}</h4>
                    <p className="text-[10px] text-muted-foreground">{s.schedule}</p>
                  </div>
                  {/* Toggle Switch */}
                  <div className="relative inline-block w-8 h-4 align-middle select-none transition duration-200 ease-in">
                    <input type="checkbox" name={`toggle-${i}`} id={`toggle-${i}`} defaultChecked={s.active} className="toggle-checkbox absolute block w-4 h-4 rounded-full bg-white border-2 border-border dark:border-slate-600 appearance-none cursor-pointer z-10 transition-transform duration-200 ease-in-out" />
                    <label htmlFor={`toggle-${i}`} className="toggle-label block overflow-hidden h-4 rounded-full bg-slate-300 dark:bg-slate-700 cursor-pointer transition-colors duration-200 ease-in"></label>
                  </div>
                </div>
              ))}
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}
