import React, { useState } from 'react';
import { 
  AlertTriangle, CheckCircle, Clock, ShieldAlert, 
  FileText, ArrowRight, User, DollarSign, Building2, 
  Calendar, Layers, HelpCircle, ExternalLink, Activity,
  Search, ShieldCheck, ChevronRight, Filter, AlertCircle,
  TrendingDown, TrendingUp, Info, Zap, Download, Loader2
} from 'lucide-react';
import ActivityInvestigationModal from './ActivityInvestigationModal';

interface ProjectStoryViewProps {
  storyData: any;
  projectId: string;
}

export default function ProjectStoryView({ storyData, projectId }: ProjectStoryViewProps) {
  const [selectedActivity, setSelectedActivity] = useState<any>(null);
  const [activeQuestionFilter, setActiveQuestionFilter] = useState<string>('all');
  const [timelineFilter, setTimelineFilter] = useState<string>('ALL');
  const [downloadingFormat, setDownloadingFormat] = useState<'pdf' | 'docx' | null>(null);

  if (!storyData || !storyData.has_data) {
    return (
      <div className="p-8 border border-border rounded-2xl bg-card text-center text-muted-foreground">
        <Layers className="w-10 h-10 mx-auto mb-3 opacity-30" />
        <h4 className="font-semibold text-foreground mb-1">No Connected Story Data</h4>
        <p className="text-xs">Schedule and quality integrations must be synced to generate cross-system intelligence.</p>
      </div>
    );
  }

  const {
    overall_status,
    executive_summary = {},
    top_delays = [],
    all_delays = [],
    top_root_causes = [],
    contractor_impact_ranking = [],
    gaps = [],
    timeline = [],
    core_questions = {}
  } = storyData;

  // Real operational values
  const maxDelay = Math.max(...top_delays.map((d: any) => d.delay_days || 0), 0);
  const critDelaysCount = executive_summary.critical_activities_delayed || top_delays.length;
  const commExposure = executive_summary.commercial_exposure_cr || 0;
  const critNcCount = executive_summary.critical_issues_count || 0;
  const openRfiCount = executive_summary.open_rfis_count || 0;
  const topBottleneck = top_root_causes[0]?.category || 'Civil / Handover';
  const contractorCount = contractor_impact_ranking.length || 0;

  const handleDownloadReport = async (format: 'pdf' | 'docx') => {
    setDownloadingFormat(format);
    try {
      const res = await fetch(`/akasha/api/intelligence/${projectId}/report`);
      if (res.ok) {
        const data = await res.json();
        const url = format === 'pdf' ? (data.pdf_url || data.docx_url) : data.docx_url;
        const filename = format === 'pdf' ? (data.pdf_filename || `${projectId}_Report.pdf`) : (data.docx_filename || `${projectId}_Report.docx`);
        const link = document.createElement('a');
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
      }
    } catch (err) {
      console.error('Failed to download executive report:', err);
    } finally {
      setDownloadingFormat(null);
    }
  };

  // Status colors
  let statusBadgeColor = "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/30";
  if (overall_status === "AT_RISK") {
    statusBadgeColor = "bg-yellow-500/10 text-yellow-600 dark:text-yellow-400 border-yellow-500/30";
  } else if (overall_status === "CRITICAL") {
    statusBadgeColor = "bg-orange-500/10 text-orange-600 dark:text-orange-400 border-orange-500/30";
  } else if (overall_status === "SEVERE") {
    statusBadgeColor = "bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/30";
  }

  // Filter activities based on the 9 Core Questions
  const getFilteredActivities = () => {
    if (activeQuestionFilter === 'issues_causing_delays') {
      return core_questions?.issues_causing_delays || [];
    }
    if (activeQuestionFilter === 'delayed_without_issues') {
      return core_questions?.delayed_activities_without_issues || [];
    }
    if (activeQuestionFilter === 'commercial_delays') {
      return core_questions?.delays_with_commercial || [];
    }
    if (activeQuestionFilter === 'milestones_at_risk') {
      return core_questions?.milestones_at_risk || [];
    }
    return top_delays;
  };

  const filteredActivities = getFilteredActivities();

  // Filter timeline events
  const filteredTimeline = timeline.filter((e: any) => {
    if (timelineFilter === 'ALL') return true;
    if (timelineFilter === 'P6' && e.source?.includes('P6')) return true;
    if (timelineFilter === 'NC' && e.source?.includes('NC')) return true;
    if (timelineFilter === 'RFI' && e.source?.includes('RFI')) return true;
    if (timelineFilter === 'INVOICE' && e.source?.includes('Invoice')) return true;
    return false;
  });

  return (
    <div className="space-y-6">
      
      {/* 1. EXECUTIVE SUMMARY & HEADLINE BANNER */}
      <div className="bg-card border border-border/80 rounded-2xl p-6 shadow-sm relative overflow-hidden">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 pb-6 border-b border-border/60">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-[11px] font-bold uppercase tracking-widest text-primary">
                Executive Variance Intelligence
              </span>
              <span className="text-xs text-muted-foreground">• Project: <strong>{projectId}</strong></span>
            </div>
            <h2 className="text-2xl font-black tracking-tight text-foreground flex items-center gap-3">
              Schedule Delay & Loss Attribution
              <span className={`text-xs px-3 py-1 rounded-full font-bold uppercase tracking-wider border ${statusBadgeColor}`}>
                Variance: +{maxDelay} Days
              </span>
            </h2>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={() => handleDownloadReport('pdf')}
              disabled={downloadingFormat !== null}
              className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-gradient-to-r from-blue-600 to-sky-600 hover:from-blue-500 hover:to-sky-500 text-white text-xs font-bold transition-all shadow-sm border border-blue-400/40 hover:scale-[1.02] active:scale-[0.98] disabled:opacity-50"
            >
              {downloadingFormat === 'pdf' ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Download className="w-4 h-4" />
              )}
              <span>Download PDF Report</span>
            </button>
            <button
              onClick={() => handleDownloadReport('docx')}
              disabled={downloadingFormat !== null}
              className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-muted/80 hover:bg-muted text-foreground text-xs font-semibold transition-all border border-border hover:scale-[1.02] active:scale-[0.98] disabled:opacity-50"
            >
              {downloadingFormat === 'docx' ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <FileText className="w-4 h-4 text-primary" />
              )}
              <span>Word (.docx)</span>
            </button>
          </div>
        </div>

        {/* Critical Insights Alert Bar */}
        {executive_summary.critical_insights && executive_summary.critical_insights.length > 0 && (
          <div className="mt-4 p-4 rounded-xl bg-primary/5 border border-primary/20 flex flex-col md:flex-row items-start md:items-center justify-between gap-3">
            <div className="flex items-center gap-2.5">
              <Zap className="w-4 h-4 text-primary shrink-0" />
              <div className="text-xs font-semibold text-foreground">
                <span className="font-bold text-primary mr-1.5">Executive Key Findings:</span>
                {executive_summary.critical_insights.join(' • ')}
              </div>
            </div>
          </div>
        )}

        {/* 2. ESSENTIAL OPERATIONAL METRICS GRID (Clear & Required Facts, No Synthetic Radar) */}
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-3 mt-6">
          {[
            { label: 'Critical Delay', value: `+${maxDelay}d`, sub: 'Max Path Variance', icon: Clock, color: maxDelay > 60 ? 'text-destructive' : 'text-amber-500', bg: maxDelay > 60 ? 'bg-destructive/10' : 'bg-amber-500/10' },
            { label: 'Delayed Tasks', value: `${critDelaysCount}`, sub: 'Critical Activities', icon: ShieldAlert, color: 'text-orange-500', bg: 'bg-orange-500/10' },
            { label: 'Value at Risk', value: `₹${commExposure} Cr`, sub: 'Pending SLR Exposure', icon: DollarSign, color: commExposure > 0 ? 'text-amber-500' : 'text-emerald-500', bg: commExposure > 0 ? 'bg-amber-500/10' : 'bg-emerald-500/10' },
            { label: 'Quality Holds', value: `${critNcCount} NCs`, sub: 'Pulse Open Defects', icon: AlertTriangle, color: critNcCount > 0 ? 'text-destructive' : 'text-emerald-500', bg: critNcCount > 0 ? 'bg-destructive/10' : 'bg-emerald-500/10' },
            { label: 'Site Hold Pts', value: `${openRfiCount} RFIs`, sub: 'Pending Inspections', icon: CheckCircle, color: 'text-sky-500', bg: 'bg-sky-500/10' },
            { label: 'Top Root Cause', value: `${topBottleneck.slice(0, 14)}`, sub: 'Primary Driver', icon: Filter, color: 'text-purple-500', bg: 'bg-purple-500/10' },
            { label: 'EPC Vendors', value: `${contractorCount}`, sub: 'Impacted Partners', icon: User, color: 'text-indigo-500', bg: 'bg-indigo-500/10' },
            { label: 'Discrepancies', value: `${gaps.length} Cases`, sub: 'Cross-System Gaps', icon: Layers, color: gaps.length > 0 ? 'text-amber-500' : 'text-emerald-500', bg: gaps.length > 0 ? 'bg-amber-500/10' : 'bg-emerald-500/10' },
          ].map(({ label, value, sub, icon: Icon, color, bg }) => {
            return (
              <div key={label} className={`rounded-xl p-3 border border-border/80 ${bg} flex flex-col items-center text-center gap-1 transition-transform hover:scale-[1.02]`}>
                <Icon className={`w-4 h-4 ${color}`} />
                <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">{label}</span>
                <span className={`text-base font-black ${color} truncate max-w-full`}>{value}</span>
                <span className="text-[9px] text-muted-foreground/80 truncate max-w-full">{sub}</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* 3. THE 9 CORE QUESTIONS FILTER BAR */}
      <div className="bg-card border border-border/80 rounded-2xl p-4 shadow-sm space-y-2">
        <div className="flex items-center justify-between text-xs font-bold text-muted-foreground uppercase tracking-wider px-1">
          <span className="flex items-center gap-1.5">
            <Filter className="w-3.5 h-3.5 text-primary" /> Key Project Questions & Filters
          </span>
          <span className="text-[11px] font-normal text-muted-foreground lowercase">click to isolate evidence</span>
        </div>
        <div className="flex flex-wrap gap-2 pt-1">
          <button
            onClick={() => setActiveQuestionFilter('all')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all border ${
              activeQuestionFilter === 'all'
                ? 'bg-primary text-primary-foreground border-primary shadow-sm'
                : 'bg-muted/50 hover:bg-muted text-muted-foreground hover:text-foreground border-border'
            }`}
          >
            All Active Delays ({top_delays.length})
          </button>
          <button
            onClick={() => setActiveQuestionFilter('issues_causing_delays')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all border ${
              activeQuestionFilter === 'issues_causing_delays'
                ? 'bg-primary text-primary-foreground border-primary shadow-sm'
                : 'bg-muted/50 hover:bg-muted text-muted-foreground hover:text-foreground border-border'
            }`}
          >
            What issues cause delays? ({core_questions?.issues_causing_delays?.length || 0})
          </button>
          <button
            onClick={() => setActiveQuestionFilter('delayed_without_issues')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all border ${
              activeQuestionFilter === 'delayed_without_issues'
                ? 'bg-primary text-primary-foreground border-primary shadow-sm'
                : 'bg-muted/50 hover:bg-muted text-muted-foreground hover:text-foreground border-border'
            }`}
          >
            Unexplained Delays (Case A) ({executive_summary.activities_without_issues || 0})
          </button>
          <button
            onClick={() => setActiveQuestionFilter('commercial_delays')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all border ${
              activeQuestionFilter === 'commercial_delays'
                ? 'bg-primary text-primary-foreground border-primary shadow-sm'
                : 'bg-muted/50 hover:bg-muted text-muted-foreground hover:text-foreground border-border'
            }`}
          >
            Delays with Commercial Exposure ({core_questions?.delays_with_commercial?.length || 0})
          </button>
          <button
            onClick={() => setActiveQuestionFilter('milestones_at_risk')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all border ${
              activeQuestionFilter === 'milestones_at_risk'
                ? 'bg-primary text-primary-foreground border-primary shadow-sm'
                : 'bg-muted/50 hover:bg-muted text-muted-foreground hover:text-foreground border-border'
            }`}
          >
            Milestones at Risk ({executive_summary.milestones_at_risk || 0})
          </button>
        </div>
      </div>

      {/* 4. ACTIVE DELAYS TABLE & 'WHY IS THIS DELAYED?' CARDS */}
      <div className="bg-card border border-border/80 rounded-2xl p-6 shadow-sm space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-lg font-bold text-foreground">
              Investigate Delayed Activities
            </h3>
            <p className="text-xs text-muted-foreground">
              Click "Investigate" on any activity to unpack the connected RFI, NC, contractor, root cause, and invoice evidence chain.
            </p>
          </div>
          <span className="text-xs font-semibold text-muted-foreground">
            Showing {filteredActivities.length} activities
          </span>
        </div>

        <div className="overflow-x-auto rounded-xl border border-border/80 shadow-2xs bg-card">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="border-b border-border text-[11px] font-bold text-muted-foreground uppercase tracking-wider bg-muted/40">
                <th className="px-4 py-3 w-[27%] min-w-[220px]">Activity & WBS</th>
                <th className="px-3 py-3 w-[12%] min-w-[110px]">Package</th>
                <th className="px-4 py-3 w-[20%] min-w-[180px]">Delay & Validation</th>
                <th className="px-3 py-3 w-[14%] min-w-[130px]">Root Cause</th>
                <th className="px-3 py-3 w-[16%] min-w-[150px]">Connected Evidence</th>
                <th className="px-3 py-3 w-[6%] min-w-[70px]">Commercial</th>
                <th className="px-4 py-3 w-[5%] min-w-[95px] text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/60">
              {filteredActivities.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-12 text-center text-muted-foreground text-sm">
                    No delayed activities matching the selected filter criteria.
                  </td>
                </tr>
              ) : (
                filteredActivities.map((act: any, idx: number) => {
                  const conf = act.root_cause?.confidence || 'NO EVIDENCE FOUND';
                  let confBadge = "bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/30";
                  if (conf === "CONFIRMED") confBadge = "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/30";
                  else if (conf === "HIGH CONFIDENCE") confBadge = "bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/30";
                  else if (conf === "LIKELY") confBadge = "bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 border-indigo-500/30";
                  else if (conf === "POSSIBLE") confBadge = "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/30";

                  return (
                    <tr 
                      key={idx}
                      onClick={() => setSelectedActivity(act)}
                      className="hover:bg-muted/30 transition-colors cursor-pointer group align-top"
                    >
                      {/* 1. Activity & WBS */}
                      <td className="px-4 py-3.5 max-w-[280px]">
                        <div className="font-bold text-foreground text-[13px] group-hover:text-primary transition-colors leading-snug">
                          {act.name}
                        </div>
                        <div className="text-[11px] font-mono text-muted-foreground flex items-center gap-1.5 mt-1">
                          <span className="px-1.5 py-0.2 rounded bg-muted border border-border/80 font-medium">
                            {act.activity_id}
                          </span>
                          {act.is_critical && (
                            <span className="text-[9px] px-1.5 py-0.2 rounded bg-destructive/10 text-destructive font-bold border border-destructive/20">
                              CRITICAL
                            </span>
                          )}
                          {act.is_milestone && (
                            <span className="text-[9px] px-1.5 py-0.2 rounded bg-purple-500/10 text-purple-600 font-bold border border-purple-500/20">
                              MILESTONE
                            </span>
                          )}
                        </div>
                      </td>

                      {/* 2. Package */}
                      <td className="px-3 py-3.5">
                        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-muted/70 border border-border/80 font-medium text-foreground text-[11px] shadow-2xs">
                          <Layers className="w-3 h-3 text-primary shrink-0" />
                          <span className="truncate">{act.package || 'General'}</span>
                        </span>
                      </td>

                      {/* 3. Delay & Validation */}
                      <td className="px-4 py-3.5">
                        <div className="space-y-1.5">
                          <div className="flex items-center gap-1.5 flex-wrap">
                            {act.delay_days > 0 ? (
                              <span className={`inline-flex items-center gap-1 font-black text-xs px-2.5 py-0.5 rounded-full border shadow-2xs ${
                                act.delay_days > 90 
                                  ? 'bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/25' 
                                  : act.delay_days > 30 
                                  ? 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/25' 
                                  : 'bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/25'
                              }`}>
                                <Clock className="w-3 h-3 shrink-0" />
                                +{act.delay_days}d
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-1 font-bold text-xs px-2.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/25">
                                <CheckCircle className="w-3 h-3" /> On Track
                              </span>
                            )}

                            {act.validation?.anomaly_detected ? (
                              <span 
                                title={act.validation?.anomaly_notes?.join('; ') || 'P6 calendar year normalized'}
                                className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-purple-500/10 text-purple-600 dark:text-purple-400 border border-purple-500/25 cursor-help inline-flex items-center gap-0.5"
                              >
                                ⚠️ Corrected
                              </span>
                            ) : (
                              <span 
                                title={`Verified calculation basis: ${act.validation?.basis || 'P6 Baseline comparison'}`}
                                className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/25 cursor-help inline-flex items-center gap-0.5"
                              >
                                <ShieldCheck className="w-2.5 h-2.5" /> Validated
                              </span>
                            )}
                          </div>

                          <div className="text-[11px] text-muted-foreground space-y-0.5 pt-0.5">
                            <div className="flex items-center gap-1.5 font-mono">
                              <span className="font-sans text-[10px] font-medium text-muted-foreground/80 w-8 shrink-0">Fin:</span>
                              <span className="font-semibold text-foreground">
                                {act.forecast_finish || '—'}
                              </span>
                              <span className="font-sans text-[9px] px-1 py-0.2 rounded bg-muted/80 text-muted-foreground capitalize font-medium">
                                {act.status?.toLowerCase() === 'completed' ? 'Done' : 'Prog'}
                              </span>
                            </div>
                            <div className="flex items-center gap-1.5 font-mono">
                              <span className="font-sans text-[10px] font-medium text-muted-foreground/80 w-8 shrink-0">Base:</span>
                              <span className="text-muted-foreground">
                                {act.baseline_finish || '—'}
                              </span>
                            </div>
                          </div>
                        </div>
                      </td>

                      {/* 4. Root Cause */}
                      <td className="px-3 py-3.5">
                        <div className="font-bold text-foreground text-[12.5px] leading-snug">
                          {act.root_cause?.category || 'Unknown'}
                        </div>
                        <span className={`text-[10px] font-bold px-2 py-0.5 rounded-md border mt-1 inline-block ${confBadge}`}>
                          {conf}
                        </span>
                      </td>

                      {/* 5. Connected Evidence */}
                      <td className="px-3 py-3.5">
                        <div className="space-y-1">
                          {act.matched_ncs?.length > 0 && (
                            <div className="inline-flex items-center gap-1 text-[10.5px] px-2 py-0.5 rounded-md bg-orange-500/10 text-orange-600 dark:text-orange-400 border border-orange-500/20 font-medium max-w-full truncate">
                              <ShieldAlert className="w-3 h-3 shrink-0" />
                              <span className="truncate">{act.matched_ncs.length} NC ({act.matched_ncs[0].nc_label})</span>
                            </div>
                          )}
                          {act.matched_rfis?.length > 0 && (
                            <div className="inline-flex items-center gap-1 text-[10.5px] px-2 py-0.5 rounded-md bg-primary/10 text-primary border border-primary/20 font-medium max-w-full truncate">
                              <FileText className="w-3 h-3 shrink-0" />
                              <span className="truncate">{act.matched_rfis.length} RFI ({act.matched_rfis[0].rfi_label})</span>
                            </div>
                          )}
                          {!act.has_linked_issue && (
                            <span className="text-[11px] text-muted-foreground italic flex items-center gap-1 py-0.5">
                              <Info className="w-3 h-3 text-muted-foreground/60 shrink-0" />
                              <span>No issue (Case A)</span>
                            </span>
                          )}
                        </div>
                      </td>

                      {/* 6. Commercial */}
                      <td className="px-3 py-3.5">
                        {act.commercial_exposure_inr > 0 ? (
                          <span className="text-xs font-bold text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 rounded-md inline-block font-mono">
                            ₹{((act.commercial_exposure_inr || 0)/10000000).toFixed(2)} Cr
                          </span>
                        ) : (
                          <span className="text-muted-foreground/50 font-mono text-xs pl-1">—</span>
                        )}
                      </td>

                      {/* 7. Action */}
                      <td className="px-4 py-3.5 text-right">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setSelectedActivity(act);
                          }}
                          className="px-3 py-1.5 rounded-lg text-xs font-bold bg-primary/10 hover:bg-primary text-primary hover:text-primary-foreground transition-all flex items-center gap-1 ml-auto shadow-2xs hover:shadow-xs shrink-0"
                        >
                          Investigate <ChevronRight className="w-3.5 h-3.5" />
                        </button>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* 5. ROOT CAUSES & CONTRACTOR DELAY IMPACT */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        
        {/* Top 5 Root Causes */}
        <div className="bg-card border border-border/80 rounded-2xl p-6 shadow-sm space-y-4">
          <h3 className="text-sm font-bold text-foreground flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-orange-500" /> Top Root Causes Across Project
          </h3>
          <div className="space-y-3">
            {top_root_causes.map((rc: any, idx: number) => (
              <div key={idx} className="p-3 rounded-xl border border-border/80 bg-muted/20 space-y-1.5">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-bold text-foreground text-sm">{rc.category}</span>
                  <span className="font-semibold text-destructive">
                    {rc.total_delay_days.toLocaleString()} days impact
                  </span>
                </div>
                <div className="flex items-center justify-between text-xs text-muted-foreground">
                  <span>{rc.delayed_activities_count} activities impacted</span>
                  <span className="font-mono text-[11px]">
                    e.g. {rc.sample_activity_ids?.slice(0, 2).join(', ')}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Contractor Impact Ranking */}
        <div className="bg-card border border-border/80 rounded-2xl p-6 shadow-sm space-y-4">
          <h3 className="text-sm font-bold text-foreground flex items-center gap-2">
            <Building2 className="w-4 h-4 text-primary" /> Contractor Delay Impact Ranking
          </h3>
          <div className="space-y-3">
            {contractor_impact_ranking.length === 0 ? (
              <div className="p-6 text-center text-xs text-muted-foreground">
                No contractor delay attribution available.
              </div>
            ) : (
              contractor_impact_ranking.map((c: any, idx: number) => (
                <div key={idx} className="p-3 rounded-xl border border-border/80 bg-muted/20 space-y-1">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-bold text-foreground">{c.contractor_name}</span>
                    <span className="font-bold text-destructive">
                      +{c.total_delay_impact_days}d delay
                    </span>
                  </div>
                  <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
                    <span>Activities: <strong>{c.activities_affected}</strong></span>
                    <span>•</span>
                    <span>NCs: <strong>{c.nc_count}</strong></span>
                    <span>•</span>
                    <span>RFIs: <strong>{c.rfi_count}</strong></span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

      </div>

      {/* 6. GAP DETECTION & MISSING INTERACTIONS (CASES A-E) */}
      <div className="bg-card border border-border/80 rounded-2xl p-6 shadow-sm space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-bold text-foreground flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-primary" /> Missing Interactions & System Gaps (Cases A–E)
          </h3>
          <span className="text-xs text-muted-foreground font-semibold">
            {gaps.length} discrepancy patterns flagged
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {gaps.map((gap: any, idx: number) => (
            <div key={idx} className="p-4 rounded-xl border border-border bg-muted/20 space-y-2 text-xs">
              <div className="flex items-center justify-between">
                <span className="font-bold px-2 py-0.5 rounded bg-primary/10 text-primary text-[10px]">
                  {gap.case}
                </span>
                <span className={`font-semibold capitalize ${gap.severity === 'high' ? 'text-destructive' : 'text-amber-500'}`}>
                  {gap.severity} priority
                </span>
              </div>
              <h4 className="font-bold text-foreground text-sm leading-snug">{gap.title}</h4>
              <p className="text-muted-foreground leading-relaxed">{gap.description}</p>
              <div className="p-2.5 rounded-lg bg-background border border-border/60 text-foreground font-medium flex items-start gap-1.5">
                <ArrowRight className="w-3.5 h-3.5 text-primary shrink-0 mt-0.5" />
                <span><strong>Recommendation:</strong> {gap.recommended_action}</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* 7. UNIFIED CHRONOLOGICAL PROJECT TIMELINE */}
      <div className="bg-card border border-border/80 rounded-2xl p-6 shadow-sm space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-border/60">
          <div>
            <h3 className="text-sm font-bold text-foreground flex items-center gap-2">
              <Calendar className="w-4 h-4 text-primary" /> Unified Chronological Project Timeline
            </h3>
            <p className="text-xs text-muted-foreground">
              Sequential flow of schedule shifts, RFI inspections, NC non-conformances, and invoice milestones.
            </p>
          </div>

          <div className="flex items-center gap-1.5">
            {['ALL', 'P6', 'NC', 'RFI', 'INVOICE'].map((f) => (
              <button
                key={f}
                onClick={() => setTimelineFilter(f)}
                className={`px-2.5 py-1 rounded-md text-[11px] font-bold transition-colors ${
                  timelineFilter === f
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-muted hover:bg-muted/80 text-muted-foreground'
                }`}
              >
                {f}
              </button>
            ))}
          </div>
        </div>

        <div className="relative pl-6 space-y-4 before:absolute before:left-2 before:top-2 before:bottom-2 before:w-0.5 before:bg-border max-h-[500px] overflow-y-auto pr-2">
          {filteredTimeline.length === 0 ? (
            <div className="p-6 text-center text-xs text-muted-foreground">
              No timeline events recorded for the selected filter.
            </div>
          ) : (
            filteredTimeline.map((item: any, idx: number) => {
              let dotColor = "bg-primary";
              if (item.source?.includes('NC')) dotColor = "bg-orange-500";
              else if (item.source?.includes('P6')) dotColor = "bg-destructive";
              else if (item.source?.includes('Invoice')) dotColor = "bg-emerald-500";

              return (
                <div key={idx} className="relative pl-4 text-xs space-y-1 group">
                  <div className={`absolute -left-[21px] top-1.5 w-2.5 h-2.5 rounded-full ${dotColor} ring-4 ring-card`} />
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-muted-foreground font-semibold">{item.date}</span>
                    <span className="px-1.5 py-0.2 rounded text-[10px] font-bold bg-muted border border-border text-foreground">
                      {item.source}
                    </span>
                    <span className="text-foreground font-bold">{item.title}</span>
                  </div>
                  <p className="text-muted-foreground leading-normal">{item.description}</p>
                  {item.responsible && (
                    <div className="text-[10px] text-muted-foreground">
                      Responsible: <strong className="text-foreground">{item.responsible}</strong>
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* Single Activity Investigation Modal */}
      {selectedActivity && (
        <ActivityInvestigationModal
          activity={selectedActivity}
          onClose={() => setSelectedActivity(null)}
        />
      )}

    </div>
  );
}

function FlagIcon(props: any) {
  return (
    <svg 
      {...props} 
      xmlns="http://www.w3.org/2000/svg" 
      viewBox="0 0 24 24" 
      fill="none" 
      stroke="currentColor" 
      strokeWidth="2" 
      strokeLinecap="round" 
      strokeLinejoin="round"
    >
      <path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z" />
      <line x1="4" x2="4" y1="22" y2="15" />
    </svg>
  );
}
