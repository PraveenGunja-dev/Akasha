import React, { useState } from 'react';
import { 
  X, AlertTriangle, CheckCircle, Clock, ShieldAlert, 
  FileText, ArrowRight, User, DollarSign, Building2, 
  Calendar, Layers, HelpCircle, ExternalLink, Activity as ActivityIcon,
  Search, ShieldCheck, CornerDownRight, Copy, Check, Sparkles,
  ChevronRight, ArrowUpRight, IndianRupee, Shield, AlertCircle
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface ActivityInvestigationModalProps {
  activity: any;
  onClose: () => void;
  onOpenAnotherActivity?: (activityId: string) => void;
}

export default function ActivityInvestigationModal({
  activity,
  onClose,
  onOpenAnotherActivity
}: ActivityInvestigationModalProps) {
  const [copied, setCopied] = useState(false);

  if (!activity) return null;

  const {
    activity_id,
    name,
    wbs_name,
    package: pkg,
    status,
    delay_days = 0,
    variance_days,
    validation,
    is_critical,
    is_milestone,
    total_float,
    percent_complete = 0,
    planned_start,
    planned_finish,
    forecast_finish,
    baseline_finish,
    root_cause = {},
    matched_ncs = [],
    matched_rfis = [],
    related_invoices = [],
    commercial_exposure_inr = 0,
    narrative_story = ''
  } = activity;

  const rcCategory = root_cause?.category || 'Unknown';
  const confidence = root_cause?.confidence || 'NO EVIDENCE FOUND';
  const hasIssue = (matched_ncs?.length > 0) || (matched_rfis?.length > 0);

  // Confidence styling & score
  let confColor = "bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/30";
  let confProgress = 10;
  let confBarColor = "bg-rose-500";
  if (confidence === "CONFIRMED") {
    confColor = "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/30";
    confProgress = 100;
    confBarColor = "bg-emerald-500";
  } else if (confidence === "HIGH CONFIDENCE") {
    confColor = "bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/30";
    confProgress = 85;
    confBarColor = "bg-blue-500";
  } else if (confidence === "LIKELY") {
    confColor = "bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 border-indigo-500/30";
    confProgress = 65;
    confBarColor = "bg-indigo-500";
  } else if (confidence === "POSSIBLE") {
    confColor = "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/30";
    confProgress = 45;
    confBarColor = "bg-amber-500";
  }

  const commExposureCr = (commercial_exposure_inr / 10000000).toFixed(2);

  const handleCopyId = () => {
    if (activity_id) {
      navigator.clipboard.writeText(activity_id);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div 
      className="fixed inset-0 z-[120] flex items-center justify-center p-3 sm:p-6 bg-black/75 backdrop-blur-md animate-in fade-in duration-200"
      onClick={onClose}
    >
      <div 
        className="bg-card border border-border/80 rounded-2xl shadow-[0_25px_60px_-15px_rgba(0,0,0,0.5)] w-full max-w-5xl max-h-[92vh] flex flex-col overflow-hidden ring-1 ring-white/10 animate-in zoom-in-95 duration-200 relative"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Ambient Top Glow */}
        <div className="absolute top-0 left-1/4 right-1/4 h-1 bg-gradient-to-r from-transparent via-primary/50 to-transparent pointer-events-none" />

        {/* Modal Header */}
        <div className="p-6 border-b border-border/70 bg-gradient-to-b from-muted/50 to-transparent flex items-start justify-between">
          <div className="space-y-2 pr-4">
            <div className="flex flex-wrap items-center gap-2">
              <button
                onClick={handleCopyId}
                title="Click to copy Activity ID"
                className="group flex items-center gap-1.5 text-xs font-mono font-bold px-2.5 py-1 rounded-lg bg-muted border border-border/80 text-foreground hover:border-primary/50 transition-colors shadow-xs"
              >
                <span>{activity_id}</span>
                {copied ? <Check className="w-3 h-3 text-emerald-500" /> : <Copy className="w-3 h-3 text-muted-foreground group-hover:text-foreground transition-colors" />}
              </button>

              <span className="text-xs font-semibold px-2.5 py-1 rounded-lg bg-primary/10 text-primary border border-primary/20 flex items-center gap-1">
                <Layers className="w-3 h-3" /> {pkg || 'General'}
              </span>

              {is_critical && (
                <span className="text-xs font-bold px-2.5 py-1 rounded-lg bg-destructive/10 text-destructive border border-destructive/20 flex items-center gap-1">
                  <ShieldAlert className="w-3 h-3" /> Critical Path
                </span>
              )}

              {is_milestone && (
                <span className="text-xs font-bold px-2.5 py-1 rounded-lg bg-purple-500/10 text-purple-600 dark:text-purple-400 border border-purple-500/20 flex items-center gap-1">
                  <Shield className="w-3 h-3" /> Milestone
                </span>
              )}

              <span className={`text-xs font-bold px-3 py-1 rounded-full border shadow-xs ${confColor}`}>
                {confidence}
              </span>

              {validation?.anomaly_detected && (
                <span className="text-xs font-bold px-2.5 py-1 rounded-full bg-purple-500/10 text-purple-600 dark:text-purple-400 border border-purple-500/30 flex items-center gap-1">
                  <AlertCircle className="w-3 h-3" /> P6 Typo Corrected
                </span>
              )}
            </div>

            <h2 className="text-2xl font-black text-foreground tracking-tight leading-snug">
              {name}
            </h2>

            <div className="text-xs text-muted-foreground flex flex-wrap items-center gap-3">
              <span>WBS: <strong className="text-foreground font-semibold">{wbs_name || 'N/A'}</strong></span>
              <span className="opacity-40">•</span>
              <span>Status: <strong className="text-foreground font-semibold capitalize">{status}</strong></span>
              <span className="opacity-40">•</span>
              <span>Physical Progress: <strong className="text-foreground font-semibold">{Math.round(percent_complete)}%</strong></span>
              {total_float !== null && total_float !== undefined && (
                <>
                  <span className="opacity-40">•</span>
                  <span>Float: <strong className={total_float <= 0 ? 'text-destructive font-bold' : 'text-foreground'}>{total_float}d</strong></span>
                </>
              )}
            </div>
          </div>

          <button 
            onClick={onClose}
            className="p-2.5 rounded-xl text-muted-foreground hover:text-foreground hover:bg-muted transition-colors shrink-0 border border-transparent hover:border-border"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Scrollable Body */}
        <div className="p-6 space-y-6 overflow-y-auto">

          {/* 1. INTERACTIVE CAUSAL CHAIN PIPELINE */}
          <div className="bg-gradient-to-br from-muted/60 via-card to-muted/40 border border-border/80 rounded-2xl p-5 shadow-xs">
            <div className="flex items-center justify-between mb-3.5">
              <div className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                <Search className="w-3.5 h-3.5 text-primary" /> Intelligence Causal Pipeline
              </div>
              <span className="text-[11px] text-muted-foreground font-medium">
                End-to-End Multi-System Causality
              </span>
            </div>

            {/* Stepper Pipeline */}
            <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2">
              
              {/* Step 1: Delay */}
              <div className={`p-3 rounded-xl border flex flex-col justify-between ${
                delay_days > 0 ? 'bg-destructive/10 border-destructive/25' : 'bg-emerald-500/10 border-emerald-500/25'
              }`}>
                <span className={`text-[9px] font-black uppercase tracking-wider flex items-center gap-1 ${
                  delay_days > 0 ? 'text-destructive/80' : 'text-emerald-600 dark:text-emerald-400'
                }`}>
                  <Clock className="w-3 h-3" /> 1. DELAY
                </span>
                <span className={`text-base font-black mt-1 ${
                  delay_days > 0 ? 'text-destructive' : 'text-emerald-600 dark:text-emerald-400'
                }`}>
                  {delay_days > 0 ? `+${delay_days}d` : 'On Track'}
                </span>
                <span className="text-[10px] text-muted-foreground truncate">
                  {validation?.anomaly_detected ? 'Sanitized P6 Date' : (delay_days > 0 ? 'Schedule Slip' : 'Within Baseline')}
                </span>
              </div>

              {/* Step 2: Activity */}
              <div className="p-3 rounded-xl bg-card border border-border flex flex-col justify-between">
                <span className="text-[9px] font-black uppercase tracking-wider text-muted-foreground flex items-center gap-1">
                  <Layers className="w-3 h-3 text-primary" /> 2. ACTIVITY
                </span>
                <span className="text-xs font-bold text-foreground mt-1 truncate" title={name}>{activity_id}</span>
                <span className="text-[10px] text-muted-foreground truncate">{pkg}</span>
              </div>

              {/* Step 3: Package */}
              <div className="p-3 rounded-xl bg-card border border-border flex flex-col justify-between">
                <span className="text-[9px] font-black uppercase tracking-wider text-muted-foreground flex items-center gap-1">
                  <Building2 className="w-3 h-3 text-primary" /> 3. PACKAGE
                </span>
                <span className="text-xs font-bold text-foreground mt-1 truncate">{pkg || 'General'}</span>
                <span className="text-[10px] text-muted-foreground truncate">{wbs_name || 'Civil/Elec'}</span>
              </div>

              {/* Step 4: Issue / RFI */}
              <div className={`p-3 rounded-xl border flex flex-col justify-between ${
                hasIssue ? 'bg-orange-500/10 border-orange-500/30' : 'bg-muted/40 border-border'
              }`}>
                <span className={`text-[9px] font-black uppercase tracking-wider flex items-center gap-1 ${
                  hasIssue ? 'text-orange-600 dark:text-orange-400' : 'text-muted-foreground'
                }`}>
                  <ShieldAlert className="w-3 h-3" /> 4. ISSUE / RFI
                </span>
                <span className="text-xs font-bold text-foreground mt-1">
                  {matched_ncs.length > 0 ? `${matched_ncs.length} NCs Logged` : matched_rfis.length > 0 ? `${matched_rfis.length} RFIs` : 'No Issue (Case A)'}
                </span>
                <span className="text-[10px] text-muted-foreground truncate">
                  {matched_ncs[0]?.nc_label || matched_rfis[0]?.rfi_label || 'Unlogged'}
                </span>
              </div>

              {/* Step 5: Root Cause */}
              <div className="p-3 rounded-xl bg-primary/10 border border-primary/25 flex flex-col justify-between">
                <span className="text-[9px] font-black uppercase tracking-wider text-primary flex items-center gap-1">
                  <AlertTriangle className="w-3 h-3" /> 5. ROOT CAUSE
                </span>
                <span className="text-xs font-black text-primary mt-1 truncate">{rcCategory}</span>
                <span className="text-[10px] text-muted-foreground truncate">{confidence}</span>
              </div>

              {/* Step 6: Responsible */}
              <div className="p-3 rounded-xl bg-card border border-border flex flex-col justify-between">
                <span className="text-[9px] font-black uppercase tracking-wider text-muted-foreground flex items-center gap-1">
                  <User className="w-3 h-3 text-primary" /> 6. RESPONSIBLE
                </span>
                <span className="text-xs font-bold text-foreground mt-1 truncate" title={root_cause?.responsible_party}>
                  {root_cause?.responsible_party || 'Unassigned'}
                </span>
                <span className="text-[10px] text-muted-foreground capitalize">{root_cause?.resolution_status || 'Open'}</span>
              </div>

              {/* Step 7: Commercial */}
              <div className="p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/25 flex flex-col justify-between">
                <span className="text-[9px] font-black uppercase tracking-wider text-emerald-600 dark:text-emerald-400 flex items-center gap-1">
                  <IndianRupee className="w-3 h-3" /> 7. COMMERCIAL
                </span>
                <span className="text-xs font-black text-foreground mt-1">₹{commExposureCr} Cr</span>
                <span className="text-[10px] text-muted-foreground truncate">{related_invoices.length} Invoices</span>
              </div>

            </div>
          </div>

          {/* 2. PROJECT STORY NARRATIVE (RICH MARKDOWN) */}
          <div className="bg-card border border-primary/20 rounded-2xl p-6 shadow-sm relative overflow-hidden bg-gradient-to-br from-primary/5 via-transparent to-primary/5">
            <div className="flex items-center justify-between mb-3 pb-3 border-b border-border/50">
              <div className="flex items-center gap-2">
                <div className="w-7 h-7 rounded-lg bg-primary/10 flex items-center justify-center text-primary">
                  <Sparkles className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-foreground">Multi-System Project Story</h3>
                  <p className="text-[10px] uppercase font-semibold tracking-wider text-muted-foreground">Connected Narrative Synthesis</p>
                </div>
              </div>
              <div className="flex items-center gap-2 text-xs">
                <span className={`px-2.5 py-0.5 rounded-full font-bold border text-[11px] ${confColor}`}>
                  {confidence}
                </span>
              </div>
            </div>

            {/* Validation Notice Banner if Anomaly Detected */}
            {validation?.anomaly_detected && (
              <div className="mb-4 p-3.5 rounded-xl bg-purple-500/10 border border-purple-500/25 text-xs flex items-start gap-2.5">
                <AlertCircle className="w-4 h-4 text-purple-600 dark:text-purple-400 shrink-0 mt-0.5" />
                <div className="space-y-0.5">
                  <div className="font-bold text-foreground flex items-center gap-2">
                    <span>Schedule Data Validation Applied</span>
                    <span className="text-[9px] font-bold px-1.5 py-0.2 rounded bg-purple-500/20 text-purple-600 dark:text-purple-300">
                      P6 Calendar Anomaly Corrected
                    </span>
                  </div>
                  <p className="text-muted-foreground text-[11px] leading-relaxed">
                    {validation?.anomaly_notes?.join('. ') || 'P6 calendar year was verified and normalized to project schedule window.'}
                  </p>
                </div>
              </div>
            )}

            {/* Render with ReactMarkdown and Custom Executive Styles */}
            <div className="prose prose-sm dark:prose-invert max-w-none text-foreground leading-relaxed font-normal">
              <ReactMarkdown 
                remarkPlugins={[remarkGfm]}
                components={{
                  h1: ({node, ...props}) => (
                    <h1 className="text-base font-black text-foreground mt-2 mb-1 tracking-tight" {...props} />
                  ),
                  h2: ({node, ...props}) => (
                    <h2 className="text-sm font-extrabold text-foreground mt-2 mb-1 tracking-tight" {...props} />
                  ),
                  h3: ({node, ...props}) => (
                    <h3 className="text-xs font-bold text-primary mt-1 mb-1 uppercase tracking-wider" {...props} />
                  ),
                  h4: ({node, ...props}) => (
                    <h4 className="text-xs font-bold text-foreground mt-3 mb-1 uppercase tracking-wider flex items-center gap-1" {...props} />
                  ),
                  strong: ({node, ...props}) => (
                    <strong className="font-bold text-foreground bg-primary/10 text-primary px-1.5 py-0.2 rounded mx-0.5 border border-primary/20" {...props} />
                  ),
                  em: ({node, ...props}) => (
                    <em className="font-medium text-foreground not-italic px-1 py-0.2 rounded bg-muted text-[12px]" {...props} />
                  ),
                  blockquote: ({node, ...props}) => (
                    <blockquote className="my-2.5 p-3 rounded-xl bg-muted/40 border-l-3 border-primary text-foreground text-xs leading-relaxed space-y-1 shadow-2xs not-italic" {...props} />
                  ),
                  ul: ({node, ...props}) => (
                    <ul className="my-2 space-y-1 pl-1 list-none" {...props} />
                  ),
                  li: ({node, ...props}) => (
                    <li className="text-[13px] text-foreground/90 leading-relaxed flex items-start gap-2" {...props}>
                      <span className="w-1.5 h-1.5 rounded-full bg-primary shrink-0 mt-2" />
                      <span className="flex-1">{props.children}</span>
                    </li>
                  ),
                  p: ({node, ...props}) => (
                    <p className="my-1.5 leading-relaxed text-[13.5px] text-foreground/90" {...props} />
                  ),
                  code: ({node, ...props}) => (
                    <code className="font-mono text-xs px-1.5 py-0.5 rounded bg-muted border border-border text-foreground font-semibold" {...props} />
                  )
                }}
              >
                {narrative_story || "No multi-system narrative generated."}
              </ReactMarkdown>
            </div>

            {/* Quick Entity Tags */}
            <div className="flex flex-wrap gap-2 mt-4 pt-3 border-t border-border/40 text-xs">
              <div className="px-2.5 py-1 rounded-lg bg-muted/80 border border-border text-muted-foreground flex items-center gap-1.5">
                <span className="font-semibold text-foreground">Root Cause:</span>
                <span className="font-bold text-primary">{rcCategory}</span>
              </div>
              <div className="px-2.5 py-1 rounded-lg bg-muted/80 border border-border text-muted-foreground flex items-center gap-1.5">
                <span className="font-semibold text-foreground">Responsible:</span>
                <span className="font-bold text-foreground">{root_cause?.responsible_party || 'Unassigned'}</span>
              </div>
              <div className="px-2.5 py-1 rounded-lg bg-muted/80 border border-border text-muted-foreground flex items-center gap-1.5">
                <span className="font-semibold text-foreground">Resolution Status:</span>
                <span className="capitalize font-bold text-foreground">{root_cause?.resolution_status || 'Open'}</span>
              </div>
              {commercial_exposure_inr > 0 && (
                <div className="px-2.5 py-1 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-600 dark:text-emerald-400 flex items-center gap-1.5 font-bold">
                  <span>Exposure:</span>
                  <span>₹{commExposureCr} Cr</span>
                </div>
              )}
            </div>
          </div>

          {/* 3. CORE METRICS TILES */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="kpi-card bg-card border border-border rounded-xl p-4 shadow-xs">
              <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground block mb-1">Schedule Delay</span>
              <div className="flex items-baseline gap-1.5">
                <span className={`text-2xl font-black ${delay_days > 0 ? 'text-destructive' : 'text-emerald-600 dark:text-emerald-400'}`}>
                  {delay_days > 0 ? `+${delay_days}` : '0'}
                </span>
                <span className="text-xs font-normal text-muted-foreground">
                  {delay_days > 0 ? 'days' : 'days (On Track)'}
                </span>
              </div>
              <span className="text-[10px] font-semibold text-muted-foreground flex items-center gap-1 mt-1">
                <ShieldCheck className="w-3 h-3 text-primary" />
                {validation?.status === 'CORRECTED_ANOMALY' ? 'Sanitized P6 Date' : (validation?.status || 'P6 Validated')}
              </span>
            </div>
            <div className="kpi-card bg-card border border-border rounded-xl p-4 shadow-xs">
              <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground block mb-1">Baseline Finish</span>
              <span className="text-sm font-bold text-foreground block font-mono">{baseline_finish || '—'}</span>
              <span className="text-[10px] text-muted-foreground">Approved Baseline</span>
            </div>
            <div className="kpi-card bg-card border border-border rounded-xl p-4 shadow-xs">
              <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground block mb-1">Forecast / Actual Finish</span>
              <span className="text-sm font-bold text-foreground block font-mono">{forecast_finish || '—'}</span>
              <span className="text-[10px] text-muted-foreground capitalize">{status || 'In Progress'}</span>
            </div>
            <div className="kpi-card bg-card border border-border rounded-xl p-4 shadow-xs">
              <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground block mb-1">Commercial Exposure</span>
              <span className="text-2xl font-black text-foreground">₹{commExposureCr} <span className="text-xs font-normal text-muted-foreground">Cr</span></span>
              <span className="text-[10px] text-muted-foreground">{related_invoices.length} Invoices Linked</span>
            </div>
          </div>

          {/* 4. ROOT CAUSE & VERIFIED EVIDENCE */}
          <div className="bg-card border border-border rounded-2xl p-6 shadow-sm space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-3 border-b border-border/60">
              <div className="flex items-center gap-2">
                <AlertTriangle className="w-5 h-5 text-orange-500" />
                <h3 className="text-base font-bold text-foreground">Root Cause Intelligence</h3>
              </div>
              <div className="flex items-center gap-3">
                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground font-medium">Confidence:</span>
                  <div className="w-24 h-2 bg-muted rounded-full overflow-hidden border border-border">
                    <div className={`h-full ${confBarColor}`} style={{ width: `${confProgress}%` }} />
                  </div>
                </div>
                <span className={`text-xs font-bold px-2.5 py-0.5 rounded border ${confColor}`}>
                  {confidence}
                </span>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 text-xs">
              <div className="space-y-3">
                <div className="p-3 rounded-xl bg-muted/40 border border-border/80">
                  <span className="text-[10px] uppercase font-bold text-muted-foreground block mb-1">Identified Category</span>
                  <span className="text-base font-black text-primary">{rcCategory}</span>
                </div>

                <div className="p-4 rounded-xl bg-muted/30 border border-border/80 space-y-1.5">
                  <span className="text-[10px] uppercase font-bold text-muted-foreground block">Verified System Evidence</span>
                  <div className="text-sm font-medium text-foreground leading-relaxed italic border-l-2 border-primary/60 pl-3">
                    "{root_cause?.evidence || 'No direct issue or PO constraint logged in connected systems.'}"
                  </div>
                </div>
              </div>

              <div className="space-y-3">
                <div className="p-3 rounded-xl bg-muted/40 border border-border/80 flex items-center justify-between">
                  <span className="text-muted-foreground font-medium">Source System:</span>
                  <span className="font-bold text-foreground px-2 py-0.5 rounded bg-muted border border-border">
                    {root_cause?.source_system || 'Primavera P6'}
                  </span>
                </div>

                <div className="p-3 rounded-xl bg-muted/40 border border-border/80 flex items-center justify-between">
                  <span className="text-muted-foreground font-medium">Responsible Party:</span>
                  <span className="font-bold text-foreground flex items-center gap-1.5">
                    <User className="w-3.5 h-3.5 text-primary" /> {root_cause?.responsible_party || 'Unassigned'}
                  </span>
                </div>

                <div className="p-3 rounded-xl bg-muted/40 border border-border/80 flex items-center justify-between">
                  <span className="text-muted-foreground font-medium">Resolution Status:</span>
                  <span className="font-bold text-foreground capitalize">{root_cause?.resolution_status || 'Open'}</span>
                </div>

                <div className="p-3 rounded-xl bg-muted/40 border border-border/80 flex items-center justify-between">
                  <span className="text-muted-foreground font-medium">Resolution Duration:</span>
                  <span className="font-bold text-foreground">{root_cause?.duration_days ? `${root_cause.duration_days} days` : 'N/A'}</span>
                </div>
              </div>
            </div>
          </div>

          {/* 5. CONNECTED QUALITY NON-CONFORMANCES (PULSE NC) */}
          <div className="bg-card border border-border rounded-2xl p-6 shadow-sm space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-border/60">
              <div className="flex items-center gap-2">
                <ShieldAlert className="w-5 h-5 text-destructive" />
                <h3 className="text-base font-bold text-foreground">Connected Non-Conformances (Pulse NC)</h3>
              </div>
              <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-muted border border-border text-muted-foreground">
                {matched_ncs.length} matched
              </span>
            </div>

            {matched_ncs.length === 0 ? (
              <div className="p-6 rounded-xl bg-muted/20 border border-border/60 text-xs text-muted-foreground text-center">
                No quality non-conformances directly associated with this activity or location.
              </div>
            ) : (
              <div className="space-y-3">
                {matched_ncs.map((nc: any, idx: number) => (
                  <div key={idx} className="p-4 rounded-xl border border-border bg-gradient-to-br from-muted/30 to-muted/10 space-y-2 text-xs hover:border-primary/40 transition-colors">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-foreground text-sm">{nc.nc_label}</span>
                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                          nc.category === 'Critical' ? 'bg-destructive/10 text-destructive border border-destructive/20' : 'bg-muted text-muted-foreground'
                        }`}>
                          {nc.category || 'NC'}
                        </span>
                        <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-primary/10 text-primary border border-primary/20">
                          {nc.confidence}
                        </span>
                      </div>
                      <span className="text-muted-foreground font-mono">{nc.created_at || '—'}</span>
                    </div>

                    <p className="text-foreground font-semibold text-[13px] leading-relaxed">
                      {nc.defect_type || nc.description}
                    </p>

                    <div className="flex flex-wrap items-center gap-4 text-muted-foreground pt-1 border-t border-border/40">
                      <span>Contractor: <strong className="text-foreground font-bold">{nc.contractor_name || 'N/A'}</strong></span>
                      {nc.debit && (
                        <span className="text-destructive font-bold">Debit Penalty: ₹{nc.debit}</span>
                      )}
                      <span>Status: <strong className="text-foreground capitalize">{nc.status}</strong></span>
                      {nc.duration_days > 0 && (
                        <span>Open Duration: <strong className="text-foreground">{nc.duration_days} days</strong></span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* 6. CONNECTED INSPECTIONS (PULSE RFI) */}
          <div className="bg-card border border-border rounded-2xl p-6 shadow-sm space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-border/60">
              <div className="flex items-center gap-2">
                <CheckCircle className="w-5 h-5 text-primary" />
                <h3 className="text-base font-bold text-foreground">Connected Inspections (Pulse RFI)</h3>
              </div>
              <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-muted border border-border text-muted-foreground">
                {matched_rfis.length} matched
              </span>
            </div>

            {matched_rfis.length === 0 ? (
              <div className="p-6 rounded-xl bg-muted/20 border border-border/60 text-xs text-muted-foreground text-center">
                No inspection requests logged for this activity workarea.
              </div>
            ) : (
              <div className="space-y-3">
                {matched_rfis.map((rfi: any, idx: number) => (
                  <div key={idx} className="p-4 rounded-xl border border-border bg-gradient-to-br from-muted/30 to-muted/10 space-y-1.5 text-xs hover:border-primary/40 transition-colors">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-foreground text-sm">{rfi.rfi_label}</span>
                        <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-primary/10 text-primary border border-primary/20">
                          {rfi.confidence}
                        </span>
                      </div>
                      <span className="text-muted-foreground font-mono">{rfi.created_at || '—'}</span>
                    </div>

                    <p className="text-foreground font-medium">
                      Checkpoint: <strong className="text-foreground font-bold">{rfi.inspection_point_name || 'General Inspection'}</strong>
                    </p>

                    <div className="flex flex-wrap items-center gap-4 text-muted-foreground pt-1 border-t border-border/40">
                      <span>Contractor: <strong className="text-foreground">{rfi.contractor_name || 'N/A'}</strong></span>
                      <span>Status: <strong className="text-foreground capitalize">{rfi.status}</strong></span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* 7. COMMERCIAL TRANSACTIONS (SAP / E-INVOICE) */}
          <div className="bg-card border border-border rounded-2xl p-6 shadow-sm space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-border/60">
              <div className="flex items-center gap-2">
                <DollarSign className="w-5 h-5 text-emerald-500" />
                <h3 className="text-base font-bold text-foreground">Commercial Transactions (SAP & E-Invoice)</h3>
              </div>
              <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-muted border border-border text-muted-foreground">
                {related_invoices.length} invoices
              </span>
            </div>

            {related_invoices.length === 0 ? (
              <div className="p-6 rounded-xl bg-muted/20 border border-border/60 text-xs text-muted-foreground text-center">
                No direct invoices mapped to this package.
              </div>
            ) : (
              <div className="space-y-3">
                {related_invoices.map((inv: any, idx: number) => (
                  <div key={idx} className="p-4 rounded-xl border border-border bg-gradient-to-br from-muted/30 to-muted/10 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs hover:border-emerald-500/40 transition-colors">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-foreground text-sm">{inv.invoice_no}</span>
                        <span className="text-[11px] font-mono px-2 py-0.2 rounded bg-muted border border-border text-muted-foreground">
                          PO: {inv.work_order_no || 'N/A'}
                        </span>
                      </div>
                      <div className="text-muted-foreground">
                        Vendor: <strong className="text-foreground font-semibold">{inv.vendor_name}</strong>
                      </div>
                      {inv.invoice_date && (
                        <div className="text-[11px] text-muted-foreground font-mono">
                          Date: {inv.invoice_date}
                        </div>
                      )}
                    </div>

                    <div className="text-left sm:text-right">
                      <div className="text-base font-black text-foreground">
                        ₹{((inv.amount_inr || 0)/10000000).toFixed(2)} Cr
                      </div>
                      <span className="inline-block mt-0.5 text-[10px] font-bold px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
                        {inv.status || 'Processed'}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

        </div>

        {/* Modal Footer */}
        <div className="p-4 border-t border-border/70 bg-muted/30 flex items-center justify-between">
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <ShieldCheck className="w-4 h-4 text-primary" />
            <span>Akasha Project-Level Intelligence System • Multi-System Evidence Verified</span>
          </div>
          <button
            onClick={onClose}
            className="px-5 py-2 rounded-xl text-xs font-bold bg-primary text-primary-foreground hover:bg-primary/90 transition-colors shadow-sm"
          >
            Done
          </button>
        </div>

      </div>
    </div>
  );
}
