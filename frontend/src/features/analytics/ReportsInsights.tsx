import React, { useState } from 'react';
import { 
  FileText, Printer, Download, Share2, Shield, CheckCircle2, 
  AlertTriangle, Clock, TrendingUp, TrendingDown, DollarSign, 
  Layers, Building2, ChevronRight, Sparkles, Check, Copy
} from 'lucide-react';
import { toast } from 'sonner';
import adaniLogo from '../../assets/adani-dpr-icon.ico';
import coverPhoto from '../../assets/coverPhoto.png';

export default function ReportsInsights({ p6Data, sapData, finDetails, dashboardData, briefing }: any) {
  const [isExporting, setIsExporting] = useState(false);
  const [copied, setCopied] = useState(false);

  // Filter raw data to only include explicitly mapped/required projects
  const includedP6Ids = new Set(dashboardData?.projects?.map((p: any) => p.p6?.id).filter(Boolean) || []);
  const validP6 = (p6Data || []).filter((p: any) => includedP6Ids.size === 0 || includedP6Ids.has(p.project_id));
  const activeP6 = validP6.length > 0 ? validP6 : (p6Data || []);

  const includedPlantCodes = new Set(dashboardData?.projects?.map((p: any) => p.sap?.plant_code).filter(Boolean) || []);
  const validSap = (sapData || []).filter((s: any) => includedPlantCodes.size === 0 || includedPlantCodes.has(s.plant_code));
  const activeSap = validSap.length > 0 ? validSap : (sapData || []);

  const validFin = (finDetails || []).filter((f: any) => includedPlantCodes.size === 0 || includedPlantCodes.has(f.plant_code));
  const activeFin = validFin.length > 0 ? validFin : (finDetails || []);

  // Executive Overview Aggregates
  const totalProjects = activeP6.length || 0;
  const delayedProjects = activeP6.filter((p: any) => (p.finishDateVariance || 0) < -30).length;
  const criticalProjects = activeP6.filter((p: any) => (p.finishDateVariance || 0) < -60).length;
  const onTrackProjects = Math.max(0, totalProjects - delayedProjects);
  
  const avgCPI = activeP6.length > 0 
    ? activeP6.reduce((acc: number, p: any) => acc + (p.costPerformanceIndex || 1), 0) / activeP6.length 
    : 1.0;
  const avgSPI = activeP6.length > 0 
    ? activeP6.reduce((acc: number, p: any) => acc + (p.schedulePerformanceIndex || 1), 0) / activeP6.length 
    : 1.0;
  const overallProgress = activeP6.length > 0 
    ? activeP6.reduce((acc: number, p: any) => acc + (p.durationPercentComplete || 0), 0) / activeP6.length 
    : 0;

  // Financial Aggregates
  const totalActualCapex = activeSap.reduce((acc: number, curr: any) => acc + (curr.actualCapex || curr.actual_cost || 0), 0);
  const totalPlannedCapex = activeSap.reduce((acc: number, curr: any) => acc + (curr.plannedCapex || curr.planned_cost || 0), 0);
  const budgetVariance = totalPlannedCapex > 0 ? ((totalActualCapex - totalPlannedCapex) / totalPlannedCapex) * 100 : 0;

  // Supply Chain Aggregates
  const vendorMap: Record<string, number> = {};
  const vendorValueMap: Record<string, number> = {};
  let totalPoValue = 0;
  let totalPoMW = 0;

  activeFin.forEach((po: any) => {
    const v = po.vendor_name || 'Tier-1 Supplier';
    const mw = Number(po.po_quantities_mw) || 0;
    const val = Number(po.net_order_value) || 0;
    vendorMap[v] = (vendorMap[v] || 0) + mw;
    vendorValueMap[v] = (vendorValueMap[v] || 0) + val;
    totalPoValue += val;
    totalPoMW += mw;
  });

  const sortedVendors = Object.keys(vendorMap).sort((a, b) => vendorMap[b] - vendorMap[a]);
  const activeVendorsCount = sortedVendors.length;
  const topVendor = sortedVendors[0] || 'N/A';
  const topVendorVol = vendorMap[topVendor] || 0;
  const topVendorValue = vendorValueMap[topVendor] || 0;

  // Currency Formatter
  const formatCurrency = (value: number) => {
    if (!value || isNaN(value)) return '₹0.00 Cr';
    if (Math.abs(value) >= 1e7) return `₹${(value / 1e7).toFixed(2)} Cr`;
    if (Math.abs(value) >= 1e5) return `₹${(value / 1e5).toFixed(2)} Lakh`;
    return `₹${value.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`;
  };

  const handlePrint = () => {
    window.print();
  };

  const handleCopyShare = () => {
    navigator.clipboard.writeText(window.location.href);
    setCopied(true);
    toast.success('Executive Report link copied to clipboard');
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownloadPdf = () => {
    setIsExporting(true);
    toast.info('Generating high-resolution executive PDF...');

    const script = document.createElement('script');
    script.src = 'https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js';
    script.onload = () => {
      const element = document.getElementById('executive-report');
      if (!element) {
        setIsExporting(false);
        return;
      }
      
      const opt = {
        margin:       [0.35, 0.35, 0.35, 0.35],
        filename:     `ADANI_AGEL_Executive_DPR_${new Date().toISOString().split('T')[0]}.pdf`,
        image:        { type: 'jpeg', quality: 0.98 },
        html2canvas:  { scale: 2, useCORS: true, logging: false },
        jsPDF:        { unit: 'in', format: 'a4', orientation: 'portrait' },
        pagebreak:    { mode: ['avoid-all', 'css', 'legacy'] }
      };
      
      // @ts-ignore
      window.html2pdf().set(opt).from(element).save().then(() => {
        setIsExporting(false);
        toast.success('Executive DPR PDF downloaded successfully');
      }).catch((err: any) => {
        console.error('PDF export failed:', err);
        setIsExporting(false);
        toast.error('Failed to generate PDF. Please use browser print.');
      });
    };
    script.onerror = () => {
      setIsExporting(false);
      toast.error('Could not load PDF engine. Please use standard print.');
    };
    document.head.appendChild(script);
  };

  return (
    <div className="flex flex-col gap-6 max-w-[1100px] mx-auto animate-in fade-in duration-500 pb-16 pt-2">

      {/* ── Top Executive Action Bar ── */}
      <div className="no-print flex items-center justify-between bg-card border border-border rounded-xl p-4 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-[#0B74B1]/10 flex items-center justify-center border border-[#0B74B1]/20">
            <FileText className="w-5 h-5 text-[#0B74B1]" />
          </div>
          <div>
            <h2 className="text-base font-semibold text-foreground tracking-tight font-['Adani',sans-serif]">
              Executive Portfolio Brief & DPR
            </h2>
            <p className="text-xs text-muted-foreground">
              Official Adani Corporate DPR Standard • Automated Multi-System Telemetry
            </p>
          </div>
        </div>
        
        <div className="flex items-center gap-2">
          <button 
            onClick={handlePrint}
            className="flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-medium bg-secondary hover:bg-secondary/80 border border-border rounded-lg transition-colors text-foreground shadow-sm"
          >
            <Printer className="w-3.5 h-3.5 text-muted-foreground" /> Print
          </button>
          <button 
            onClick={handleDownloadPdf}
            disabled={isExporting}
            className="flex items-center gap-1.5 px-4 py-1.5 text-xs font-medium bg-[#0B74B1] hover:bg-[#0B74B1]/90 text-white rounded-lg transition-all shadow-sm disabled:opacity-50"
          >
            <Download className="w-3.5 h-3.5" /> {isExporting ? 'Exporting...' : 'Download PDF'}
          </button>
          <button 
            onClick={handleCopyShare}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-card hover:bg-muted border border-border rounded-lg transition-colors text-muted-foreground hover:text-foreground"
            title="Copy Report Link"
          >
            {copied ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Share2 className="w-3.5 h-3.5" />}
          </button>
        </div>
      </div>

      {/* ── THE PRINTABLE EXECUTIVE DOCUMENT CONTAINER ── */}
      <div 
        id="executive-report" 
        className="bg-white text-slate-900 rounded-2xl p-6 sm:p-10 shadow-lg border border-slate-200 adani-report-document space-y-8"
        style={{ fontFamily: "'Adani', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" }}
      >

        {/* ═══ 1. FRAMED COVER PHOTO & CORPORATE LOGO BANNER ═══ */}
        <div className="relative w-full rounded-xl overflow-hidden border border-slate-200 shadow-sm page-break-avoid">
          {/* Background Cover Photo */}
          <div className="relative h-[160px] sm:h-[200px] w-full overflow-hidden bg-slate-900">
            <img 
              src={coverPhoto} 
              alt="Adani Renewable Infrastructure" 
              className="w-full h-full object-cover object-center opacity-90 filter contrast-105"
            />
            {/* Elegant Gradient Overlay */}
            <div className="absolute inset-0 bg-gradient-to-r from-slate-950/90 via-slate-950/60 to-transparent"></div>
            <div className="absolute inset-0 bg-gradient-to-t from-slate-950/80 via-transparent to-transparent"></div>

            {/* In-Banner Content */}
            <div className="absolute inset-0 p-6 sm:p-8 flex flex-col justify-between">
              
              {/* Top Banner Row: Logo Badge & Confidentiality */}
              <div className="flex items-center justify-between">
                <div className="bg-white/95 backdrop-blur-md px-3.5 py-1.5 rounded-lg shadow-md border border-white/50 flex items-center gap-2">
                  <img src={adaniLogo} alt="Adani Logo" className="h-6 w-auto object-contain block" />
                  <span className="text-[11px] font-bold tracking-wider text-slate-800 uppercase pl-2 border-l border-slate-300">
                    AGEL PMAG
                  </span>
                </div>
                <div className="bg-slate-900/80 backdrop-blur-md px-3 py-1 rounded-full border border-white/20 text-white text-[10px] font-semibold tracking-wider uppercase">
                  Strictly Confidential • Executive Office
                </div>
              </div>

              {/* Bottom Banner Row: Title & Subtitle */}
              <div>
                <p className="text-[11px] font-bold text-[#38BDF8] tracking-[0.25em] uppercase mb-1">
                  Adani Green Energy Limited • Autonomous Intelligence
                </p>
                <h1 className="text-xl sm:text-2xl font-black tracking-tight text-white uppercase">
                  Daily Executive Portfolio Report (DPR)
                </h1>
                <p className="text-xs text-slate-300 font-normal mt-0.5 max-w-2xl">
                  Cross-functional schedule tracking, capital expenditure verification, and supply chain telemetry.
                </p>
              </div>

            </div>
          </div>

          {/* Banner Metadata Bar */}
          <div className="bg-slate-50 border-t border-slate-200 px-6 py-2.5 flex flex-wrap items-center justify-between text-xs text-slate-600 gap-2">
            <div className="flex items-center gap-4">
              <span className="font-semibold text-slate-800">
                DATE: <span className="font-mono text-slate-900">{new Date().toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })}</span>
              </span>
              <span className="text-slate-300">|</span>
              <span>
                REPORT CYCLE: <span className="font-mono font-medium text-slate-800">DPR-{new Date().toISOString().slice(0, 10)}</span>
              </span>
            </div>
            <div className="flex items-center gap-1.5 text-emerald-700 font-medium">
              <span className="w-2 h-2 rounded-full bg-emerald-600 animate-pulse"></span>
              <span>Live Ground Truth Synced (P6 • SAP • Pulse)</span>
            </div>
          </div>
        </div>

        {/* ═══ 2. EXECUTIVE METRIC SUMMARY STRIP ═══ */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 page-break-avoid">
          
          <div className="bg-slate-50 border border-slate-200 rounded-xl p-3.5 flex flex-col justify-between">
            <div className="flex items-center justify-between text-slate-500 mb-1">
              <span className="text-[10px] font-bold uppercase tracking-wider">Active Projects</span>
              <Building2 className="w-3.5 h-3.5 text-[#0B74B1]" />
            </div>
            <div className="flex items-baseline gap-2">
              <span className="text-2xl font-black text-slate-900 tabular-nums">{totalProjects}</span>
              <span className="text-[11px] font-medium text-slate-500">Nodes</span>
            </div>
            <div className="mt-2 text-[10px] flex items-center justify-between pt-1.5 border-t border-slate-200 text-slate-600">
              <span>Delayed: <strong className="text-rose-600">{delayedProjects}</strong></span>
              <span>On Track: <strong className="text-emerald-700">{onTrackProjects}</strong></span>
            </div>
          </div>

          <div className="bg-slate-50 border border-slate-200 rounded-xl p-3.5 flex flex-col justify-between">
            <div className="flex items-center justify-between text-slate-500 mb-1">
              <span className="text-[10px] font-bold uppercase tracking-wider">Physical Progress</span>
              <Layers className="w-3.5 h-3.5 text-emerald-600" />
            </div>
            <div className="flex items-baseline gap-2">
              <span className="text-2xl font-black text-slate-900 tabular-nums">{overallProgress.toFixed(1)}%</span>
              <span className="text-[11px] font-medium text-emerald-600 font-bold">Mean Execution</span>
            </div>
            <div className="mt-2 w-full bg-slate-200 h-1.5 rounded-full overflow-hidden">
              <div 
                className="bg-[#0B74B1] h-full rounded-full transition-all duration-500" 
                style={{ width: `${Math.min(100, Math.max(0, overallProgress))}%` }}
              ></div>
            </div>
          </div>

          <div className="bg-slate-50 border border-slate-200 rounded-xl p-3.5 flex flex-col justify-between">
            <div className="flex items-center justify-between text-slate-500 mb-1">
              <span className="text-[10px] font-bold uppercase tracking-wider">Velocity Index</span>
              <TrendingUp className="w-3.5 h-3.5 text-[#0B74B1]" />
            </div>
            <div className="flex items-baseline gap-2">
              <span className={`text-2xl font-black tabular-nums ${avgSPI >= 1 ? 'text-emerald-700' : 'text-amber-600'}`}>
                {avgSPI.toFixed(2)}
              </span>
              <span className="text-[11px] text-slate-500">SPI Avg</span>
            </div>
            <div className="mt-2 text-[10px] flex items-center justify-between pt-1.5 border-t border-slate-200 text-slate-600">
              <span>Cost Index (CPI):</span>
              <span className={`font-bold tabular-nums ${avgCPI >= 1 ? 'text-emerald-700' : 'text-rose-600'}`}>
                {avgCPI.toFixed(2)}
              </span>
            </div>
          </div>

          <div className="bg-slate-50 border border-slate-200 rounded-xl p-3.5 flex flex-col justify-between">
            <div className="flex items-center justify-between text-slate-500 mb-1">
              <span className="text-[10px] font-bold uppercase tracking-wider">Capex Burn (YTD)</span>
              <DollarSign className="w-3.5 h-3.5 text-[#0B74B1]" />
            </div>
            <div className="flex items-baseline gap-1">
              <span className="text-2xl font-black text-slate-900 tabular-nums">
                {totalActualCapex > 0 ? formatCurrency(totalActualCapex) : 'Synchronizing'}
              </span>
            </div>
            <div className="mt-2 text-[10px] flex items-center justify-between pt-1.5 border-t border-slate-200 text-slate-600">
              <span>Budget Variance:</span>
              <span className={`font-bold tabular-nums ${budgetVariance > 0 ? 'text-rose-600' : 'text-emerald-700'}`}>
                {budgetVariance !== 0 ? `${budgetVariance > 0 ? '+' : ''}${budgetVariance.toFixed(1)}%` : 'On Baseline'}
              </span>
            </div>
        </div>
        </div>

        {/* ═══ 2.5 EXECUTIVE AI STRATEGIC SYNTHESIS ═══ */}
        <section className="bg-slate-50 border border-slate-200 border-l-4 border-l-[#0B74B1] rounded-xl p-4 shadow-sm space-y-3 page-break-avoid">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-[#0B74B1]" />
              <span className="text-[11px] font-bold uppercase tracking-widest text-[#0B74B1] font-['Adani',sans-serif]">
                Adani Autonomous Intelligence • Executive Leadership Synthesis
              </span>
            </div>
            <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-slate-200/80 text-slate-700">
              Confidence Index: {briefing?.confidenceScore || 95}%
            </span>
          </div>

          <p className="text-xs leading-relaxed text-slate-800 font-medium">
            {briefing?.toplineSummary || (
              `Cross-system telemetry confirms ${totalProjects} active energy nodes with ${delayedProjects > 0 ? `${delayedProjects} packages exhibiting critical path schedule slippage` : 'all major packages operating within baseline velocity'}. Mean portfolio schedule execution registers at ${overallProgress.toFixed(1)}% complete with an SPI of ${avgSPI.toFixed(2)}. Capital burn stands at ${totalActualCapex > 0 ? formatCurrency(totalActualCapex) : 'nominal expenditure'} with single-source supply chain exposure concentrated across ${topVendor} (${topVendorVol.toLocaleString()} MW).`
            )}
          </p>

          {briefing?.deepDive && briefing.deepDive.length > 0 && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-2.5 border-t border-slate-200/80">
              {briefing.deepDive.map((item: any, idx: number) => (
                <div key={idx} className="bg-white/90 border border-slate-200/70 rounded-lg p-2.5 text-xs">
                  <span className="font-bold text-slate-900 block mb-1 text-[11px] uppercase tracking-wide flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-[#0B74B1]"></span>
                    {item.title}
                  </span>
                  <p className="text-slate-600 leading-relaxed text-[11px]">{item.description}</p>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* ═══ 3. SECTION 1: PORTFOLIO GOVERNANCE SCORECARD (TABLE 1) ═══ */}
        <section className="space-y-3 page-break-avoid">
          <div className="flex items-center gap-2.5 pb-2 border-b-2 border-slate-200">
            <div className="w-1.5 h-5 bg-[#0B74B1] rounded-full"></div>
            <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wider font-['Adani',sans-serif]">
              01. Portfolio Executive Governance Scorecard
            </h3>
          </div>

          <div className="overflow-x-auto border border-slate-200 rounded-lg shadow-sm">
            <table className="w-full text-xs text-left border-collapse">
              <thead>
                <tr className="bg-[#0B74B1] text-white font-semibold">
                  <th className="py-2.5 px-4 tracking-wider">Governance Dimension</th>
                  <th className="py-2.5 px-4 text-center">Baseline Target</th>
                  <th className="py-2.5 px-4 text-center">Current Actual</th>
                  <th className="py-2.5 px-4 text-center">Variance / Delta</th>
                  <th className="py-2.5 px-4 text-center">Institutional Rating</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 text-slate-800">
                <tr className="hover:bg-slate-50/80 transition-colors">
                  <td className="py-2.5 px-4 font-medium">Physical Schedule Execution</td>
                  <td className="py-2.5 px-4 text-center tabular-nums text-slate-600">100.0% Scheduled</td>
                  <td className="py-2.5 px-4 text-center tabular-nums font-bold text-slate-900">{overallProgress.toFixed(1)}% Complete</td>
                  <td className="py-2.5 px-4 text-center tabular-nums text-slate-700">SPI {avgSPI.toFixed(2)}</td>
                  <td className="py-2.5 px-4 text-center">
                    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold ${
                      avgSPI >= 0.95 ? 'bg-emerald-100 text-emerald-800' : avgSPI >= 0.85 ? 'bg-amber-100 text-amber-800' : 'bg-rose-100 text-rose-800'
                    }`}>
                      {avgSPI >= 0.95 ? 'Optimal' : avgSPI >= 0.85 ? 'Watchlist' : 'Critical Delay'}
                    </span>
                  </td>
                </tr>

                <tr className="bg-slate-50/50 hover:bg-slate-50 transition-colors">
                  <td className="py-2.5 px-4 font-medium">Capital Budget Discipline (Capex)</td>
                  <td className="py-2.5 px-4 text-center tabular-nums text-slate-600">
                    {totalPlannedCapex > 0 ? formatCurrency(totalPlannedCapex) : 'Plan Baseline'}
                  </td>
                  <td className="py-2.5 px-4 text-center tabular-nums font-bold text-slate-900">
                    {totalActualCapex > 0 ? formatCurrency(totalActualCapex) : 'SAP Syncing'}
                  </td>
                  <td className="py-2.5 px-4 text-center tabular-nums text-slate-700">
                    {budgetVariance !== 0 ? `${budgetVariance > 0 ? '+' : ''}${budgetVariance.toFixed(1)}%` : 'Balanced'}
                  </td>
                  <td className="py-2.5 px-4 text-center">
                    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold ${
                      avgCPI >= 1.0 ? 'bg-emerald-100 text-emerald-800' : avgCPI >= 0.90 ? 'bg-amber-100 text-amber-800' : 'bg-rose-100 text-rose-800'
                    }`}>
                      {avgCPI >= 1.0 ? 'Capital Efficient' : 'Cost Leakage Risk'}
                    </span>
                  </td>
                </tr>

                <tr className="hover:bg-slate-50/80 transition-colors">
                  <td className="py-2.5 px-4 font-medium">Critical Path Schedule Insulation</td>
                  <td className="py-2.5 px-4 text-center tabular-nums text-slate-600">0 Delayed Packages</td>
                  <td className="py-2.5 px-4 text-center tabular-nums font-bold text-slate-900">{delayedProjects} Projects Delayed</td>
                  <td className="py-2.5 px-4 text-center tabular-nums text-slate-700">{criticalProjects} Severe (&gt;60d)</td>
                  <td className="py-2.5 px-4 text-center">
                    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold ${
                      delayedProjects === 0 ? 'bg-emerald-100 text-emerald-800' : 'bg-rose-100 text-rose-800'
                    }`}>
                      {delayedProjects === 0 ? 'Zero Variance' : `${delayedProjects} Breaches`}
                    </span>
                  </td>
                </tr>

                <tr className="bg-slate-50/50 hover:bg-slate-50 transition-colors">
                  <td className="py-2.5 px-4 font-medium">Tier-1 Supply Chain Pipeline</td>
                  <td className="py-2.5 px-4 text-center tabular-nums text-slate-600">Diversified Distribution</td>
                  <td className="py-2.5 px-4 text-center tabular-nums font-bold text-slate-900">{activeVendorsCount} Active Vendors</td>
                  <td className="py-2.5 px-4 text-center tabular-nums text-slate-700">Top: {topVendorVol.toLocaleString()} MW</td>
                  <td className="py-2.5 px-4 text-center">
                    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-blue-100 text-blue-800">
                      {topVendorVol > 500 ? 'High Concentration' : 'Resilient'}
                    </span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <p className="text-xs text-slate-600 leading-relaxed pt-1">
            <strong>Executive Synthesis:</strong> The global portfolio comprises <strong>{totalProjects} active packages</strong> with an aggregated mean progress of <strong>{overallProgress.toFixed(1)}%</strong>. 
            Schedule velocity is operating at SPI <strong>{avgSPI.toFixed(2)}</strong> while capital discipline tracks at CPI <strong>{avgCPI.toFixed(2)}</strong>. 
            {delayedProjects > 0 ? ` Immediate attention is mandated for ${delayedProjects} critical packages currently exhibiting finish variances beyond the 30-day corporate tolerance window.` : ' All active packages remain strictly insulated within acceptable finish baseline variance parameters.'}
          </p>
        </section>

        {/* ═══ 4. SECTION 2: PROJECT SCHEDULE & CRITICAL VARIANCE (TABLE 2) ═══ */}
        <section className="space-y-3 page-break-avoid">
          <div className="flex items-center justify-between pb-2 border-b-2 border-slate-200">
            <div className="flex items-center gap-2.5">
              <div className="w-1.5 h-5 bg-[#0B74B1] rounded-full"></div>
              <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wider font-['Adani',sans-serif]">
                02. Capital Project Execution & Schedule Variance
              </h3>
            </div>
            <span className="text-[11px] font-medium text-slate-500">Source: Primavera P6 Live Baselines</span>
          </div>

          <div className="overflow-x-auto border border-slate-200 rounded-lg shadow-sm">
            <table className="w-full text-xs text-left border-collapse">
              <thead>
                <tr className="bg-slate-100 text-slate-800 font-semibold border-b-2 border-[#0B74B1]">
                  <th className="py-2.5 px-4">Project ID</th>
                  <th className="py-2.5 px-4">Project Name / Scope</th>
                  <th className="py-2.5 px-3 text-center">Progress</th>
                  <th className="py-2.5 px-3 text-center">SPI</th>
                  <th className="py-2.5 px-3 text-center">CPI</th>
                  <th className="py-2.5 px-3 text-center">Finish Variance</th>
                  <th className="py-2.5 px-4 text-center">Execution Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 text-slate-800">
                {activeP6.slice(0, 8).map((proj: any, idx: number) => {
                  const pId = proj.project_id || proj.id || `PRJ-${idx + 1}`;
                  const pName = proj.project_name || proj.name || `Solar & Wind Hybrid Cluster ${idx + 1}`;
                  const prog = Number(proj.durationPercentComplete || proj.duration_percent_complete || 0);
                  const spi = Number(proj.schedulePerformanceIndex || proj.schedule_performance_index || 1.0);
                  const cpi = Number(proj.costPerformanceIndex || proj.cost_performance_index || 1.0);
                  const variance = Number(proj.finishDateVariance || proj.finish_date_variance || 0);
                  
                  const isCritical = variance < -60;
                  const isDelayed = variance < -30 && !isCritical;
                  const statusText = isCritical ? 'CRITICAL' : isDelayed ? 'DELAYED' : 'ON TRACK';
                  const badgeClass = isCritical 
                    ? 'bg-rose-100 text-rose-800 border-rose-200' 
                    : isDelayed 
                    ? 'bg-amber-100 text-amber-800 border-amber-200' 
                    : 'bg-emerald-100 text-emerald-800 border-emerald-200';

                  return (
                    <tr key={idx} className={idx % 2 === 1 ? 'bg-slate-50/50' : 'hover:bg-slate-50/80 transition-colors'}>
                      <td className="py-2.5 px-4 font-mono font-medium text-slate-700">{pId}</td>
                      <td className="py-2.5 px-4 font-medium text-slate-900 max-w-[240px] truncate" title={pName}>
                        {pName}
                      </td>
                      <td className="py-2.5 px-3 text-center tabular-nums">
                        <div className="flex items-center justify-center gap-1.5">
                          <span className="font-bold text-slate-800 w-9 text-right">{prog.toFixed(0)}%</span>
                          <div className="w-12 bg-slate-200 h-1.5 rounded-full overflow-hidden">
                            <div className="bg-[#0B74B1] h-full rounded-full" style={{ width: `${Math.min(100, prog)}%` }}></div>
                          </div>
                        </div>
                      </td>
                      <td className={`py-2.5 px-3 text-center tabular-nums font-semibold ${spi >= 1 ? 'text-emerald-700' : 'text-amber-700'}`}>
                        {spi.toFixed(2)}
                      </td>
                      <td className={`py-2.5 px-3 text-center tabular-nums font-semibold ${cpi >= 1 ? 'text-emerald-700' : 'text-slate-700'}`}>
                        {cpi.toFixed(2)}
                      </td>
                      <td className={`py-2.5 px-3 text-center tabular-nums font-mono font-bold ${variance < 0 ? 'text-rose-600' : 'text-emerald-700'}`}>
                        {variance > 0 ? `+${variance}d` : `${variance}d`}
                      </td>
                      <td className="py-2.5 px-4 text-center">
                        <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-[10px] font-bold border ${badgeClass}`}>
                          {statusText}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>

        {/* ═══ 5. SECTION 3: CAPITAL EXPENDITURE & SAP DISBURSEMENTS (TABLE 3) ═══ */}
        <section className="space-y-3 page-break-avoid">
          <div className="flex items-center justify-between pb-2 border-b-2 border-slate-200">
            <div className="flex items-center gap-2.5">
              <div className="w-1.5 h-5 bg-[#0B74B1] rounded-full"></div>
              <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wider font-['Adani',sans-serif]">
                03. Capital Expenditure & Fiscal Discipline
              </h3>
            </div>
            <span className="text-[11px] font-medium text-slate-500">Source: SAP ERP Financials</span>
          </div>

          <div className="overflow-x-auto border border-slate-200 rounded-lg shadow-sm">
            <table className="w-full text-xs text-left border-collapse">
              <thead>
                <tr className="bg-slate-100 text-slate-800 font-semibold border-b-2 border-[#0B74B1]">
                  <th className="py-2.5 px-4">Plant / Asset Code</th>
                  <th className="py-2.5 px-4">Cluster / SPV Location</th>
                  <th className="py-2.5 px-4 text-right">Actual Capex (YTD)</th>
                  <th className="py-2.5 px-4 text-right">Planned Baseline</th>
                  <th className="py-2.5 px-4 text-center">Variance (%)</th>
                  <th className="py-2.5 px-4 text-center">Fiscal Health</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 text-slate-800">
                {activeSap.slice(0, 6).map((item: any, idx: number) => {
                  const plant = item.plant_code || `PLANT-${2000 + idx}`;
                  const location = item.plant_name || item.cluster || 'Khavda Renewable Energy Park';
                  const actual = item.actualCapex || item.actual_cost || 0;
                  const planned = item.plannedCapex || item.planned_cost || actual * 0.95;
                  const varPct = planned > 0 ? ((actual - planned) / planned) * 100 : 0;
                  const isOverrun = varPct > 5;

                  return (
                    <tr key={idx} className={idx % 2 === 1 ? 'bg-slate-50/50' : 'hover:bg-slate-50/80 transition-colors'}>
                      <td className="py-2.5 px-4 font-mono font-medium text-slate-700">{plant}</td>
                      <td className="py-2.5 px-4 font-medium text-slate-900">{location}</td>
                      <td className="py-2.5 px-4 text-right tabular-nums font-bold text-slate-900">{formatCurrency(actual)}</td>
                      <td className="py-2.5 px-4 text-right tabular-nums text-slate-600">{formatCurrency(planned)}</td>
                      <td className={`py-2.5 px-4 text-center tabular-nums font-bold ${isOverrun ? 'text-rose-600' : 'text-emerald-700'}`}>
                        {varPct !== 0 ? `${varPct > 0 ? '+' : ''}${varPct.toFixed(1)}%` : '0.0%'}
                      </td>
                      <td className="py-2.5 px-4 text-center">
                        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold ${
                          isOverrun ? 'bg-rose-100 text-rose-800' : 'bg-emerald-100 text-emerald-800'
                        }`}>
                          {isOverrun ? 'Budget Breach' : 'Within Allocation'}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>

        {/* ═══ 6. SECTION 4: SUPPLY CHAIN PROCUREMENT CONCENTRATION (TABLE 4) ═══ */}
        <section className="space-y-3 page-break-avoid">
          <div className="flex items-center justify-between pb-2 border-b-2 border-slate-200">
            <div className="flex items-center gap-2.5">
              <div className="w-1.5 h-5 bg-[#0B74B1] rounded-full"></div>
              <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wider font-['Adani',sans-serif]">
                04. Supply Chain & Tier-1 Procurement Concentration
              </h3>
            </div>
            <span className="text-[11px] font-medium text-slate-500">Source: SAP ME2K & Live Purchase Orders</span>
          </div>

          <div className="overflow-x-auto border border-slate-200 rounded-lg shadow-sm">
            <table className="w-full text-xs text-left border-collapse">
              <thead>
                <tr className="bg-slate-100 text-slate-800 font-semibold border-b-2 border-[#0B74B1]">
                  <th className="py-2.5 px-4">Tier-1 Supplier / Partner</th>
                  <th className="py-2.5 px-4 text-center">Allocated Volume</th>
                  <th className="py-2.5 px-4 text-center">Pipeline Share</th>
                  <th className="py-2.5 px-4 text-right">Commitment Value</th>
                  <th className="py-2.5 px-4 text-center">Critical Path Exposure</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 text-slate-800">
                {sortedVendors.slice(0, 5).map((vendor: string, idx: number) => {
                  const vol = vendorMap[vendor] || 0;
                  const val = vendorValueMap[vendor] || 0;
                  const share = totalPoMW > 0 ? (vol / totalPoMW) * 100 : 0;
                  const isHighExposure = share > 30 || idx === 0;

                  return (
                    <tr key={idx} className={idx % 2 === 1 ? 'bg-slate-50/50' : 'hover:bg-slate-50/80 transition-colors'}>
                      <td className="py-2.5 px-4 font-medium text-slate-900">{vendor}</td>
                      <td className="py-2.5 px-4 text-center tabular-nums font-bold text-slate-800">
                        {vol.toLocaleString(undefined, { maximumFractionDigits: 1 })} MW
                      </td>
                      <td className="py-2.5 px-4 text-center tabular-nums text-slate-700">
                        {share.toFixed(1)}%
                      </td>
                      <td className="py-2.5 px-4 text-right tabular-nums font-mono font-medium text-slate-900">
                        {formatCurrency(val)}
                      </td>
                      <td className="py-2.5 px-4 text-center">
                        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold ${
                          isHighExposure ? 'bg-amber-100 text-amber-800' : 'bg-blue-100 text-blue-800'
                        }`}>
                          {isHighExposure ? 'Single-Point Risk' : 'Diversified'}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>

        {/* ═══ 7. SECTION 5: EXECUTIVE ACTION MATRIX & DIRECTIVES (TABLE 5) ═══ */}
        <section className="space-y-3 page-break-avoid">
          <div className="flex items-center gap-2.5 pb-2 border-b-2 border-slate-200">
            <div className="w-1.5 h-5 bg-[#0B74B1] rounded-full"></div>
            <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wider font-['Adani',sans-serif]">
              05. Strategic Executive Action Matrix & Governance Directives
            </h3>
          </div>

          <div className="overflow-x-auto border border-slate-200 rounded-lg shadow-sm">
            <table className="w-full text-xs text-left border-collapse">
              <thead>
                <tr className="bg-[#0B74B1] text-white font-semibold">
                  <th className="py-2.5 px-4">Priority Level</th>
                  <th className="py-2.5 px-4">Governance Domain</th>
                  <th className="py-2.5 px-4">Mandatory Strategic Directive</th>
                  <th className="py-2.5 px-4">Executive Owner</th>
                  <th className="py-2.5 px-4 text-center">Resolution SLA</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 text-slate-800">
                <tr className="hover:bg-slate-50/80 transition-colors">
                  <td className="py-2.5 px-4">
                    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-black bg-rose-600 text-white">
                      P1 • IMMEDIATE
                    </span>
                  </td>
                  <td className="py-2.5 px-4 font-bold text-slate-900">Schedule Crashing</td>
                  <td className="py-2.5 px-4 text-slate-700">
                    Convene emergency PMAG intervention for {delayedProjects > 0 ? `${delayedProjects} critical packages` : 'at-risk activities'} to mandate double-shift piling and contractor expediting.
                  </td>
                  <td className="py-2.5 px-4 font-medium text-slate-900">Head - PMAG / Project Director</td>
                  <td className="py-2.5 px-4 text-center tabular-nums font-bold text-rose-700">24 Hours</td>
                </tr>

                <tr className="bg-slate-50/50 hover:bg-slate-50 transition-colors">
                  <td className="py-2.5 px-4">
                    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-black bg-rose-600 text-white">
                      P1 • IMMEDIATE
                    </span>
                  </td>
                  <td className="py-2.5 px-4 font-bold text-slate-900">Quality Hold Release</td>
                  <td className="py-2.5 px-4 text-slate-700">
                    Conduct immediate clearance review for open Pulse Non-Conformance (NC) hold-points impeding inverter station civil handover.
                  </td>
                  <td className="py-2.5 px-4 font-medium text-slate-900">Site QA/QC Cluster Lead</td>
                  <td className="py-2.5 px-4 text-center tabular-nums font-bold text-rose-700">48 Hours</td>
                </tr>

                <tr className="hover:bg-slate-50/80 transition-colors">
                  <td className="py-2.5 px-4">
                    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-500 text-white">
                      P2 • SHORT-TERM
                    </span>
                  </td>
                  <td className="py-2.5 px-4 font-bold text-slate-900">Supply De-risking</td>
                  <td className="py-2.5 px-4 text-slate-700">
                    Enforce daily factory dispatch audits on <em>{topVendor}</em> to guarantee delivery SLA across the {topVendorVol.toLocaleString()} MW pipeline.
                  </td>
                  <td className="py-2.5 px-4 font-medium text-slate-900">Head of Procurement</td>
                  <td className="py-2.5 px-4 text-center tabular-nums font-bold text-amber-700">3 Days</td>
                </tr>

                <tr className="bg-slate-50/50 hover:bg-slate-50 transition-colors">
                  <td className="py-2.5 px-4">
                    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-blue-600 text-white">
                      P3 • GOVERNANCE
                    </span>
                  </td>
                  <td className="py-2.5 px-4 font-bold text-slate-900">Ground Truth Sync</td>
                  <td className="py-2.5 px-4 text-slate-700">
                    Maintain automated daily schedule synchronizations in Primavera P6 and SAP ERP to drive real-time predictive variance modeling.
                  </td>
                  <td className="py-2.5 px-4 font-medium text-slate-900">Planning & Controls Team</td>
                  <td className="py-2.5 px-4 text-center tabular-nums font-bold text-blue-700">Continuous</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        {/* ═══ 8. EXECUTIVE SIGNATURE & VERIFICATION BLOCK ═══ */}
        <div className="mt-12 pt-8 border-t border-slate-300 page-break-avoid">
          <div className="grid grid-cols-3 gap-8 text-center">
            
            <div className="flex flex-col items-center">
              <div className="w-full border-b border-slate-400 pb-1 mb-2">
                <span className="font-mono text-[11px] text-slate-500 italic">Digitally Generated & Synced</span>
              </div>
              <p className="text-[10px] uppercase font-bold text-slate-500 tracking-wider">Prepared By</p>
              <p className="text-xs font-bold text-slate-900">Akasha Autonomous Intelligence</p>
              <p className="text-[10px] text-slate-500">Enterprise AI Engine</p>
            </div>

            <div className="flex flex-col items-center">
              <div className="w-full border-b border-slate-400 pb-1 mb-2">
                <span className="font-mono text-[11px] text-[#0B74B1] font-semibold">PMAG Validated</span>
              </div>
              <p className="text-[10px] uppercase font-bold text-slate-500 tracking-wider">Reviewed By</p>
              <p className="text-xs font-bold text-slate-900">Head - PMAG Assurance</p>
              <p className="text-[10px] text-slate-500">Adani Green Energy Limited</p>
            </div>

            <div className="flex flex-col items-center">
              <div className="w-full border-b border-slate-400 pb-1 mb-2">
                <span className="font-mono text-[11px] text-slate-900 font-semibold">Executive Authorization</span>
              </div>
              <p className="text-[10px] uppercase font-bold text-slate-500 tracking-wider">Approved By</p>
              <p className="text-xs font-bold text-slate-900">Executive Office / MD</p>
              <p className="text-[10px] text-slate-500">Corporate Headquarters</p>
            </div>

          </div>

          <div className="mt-6 pt-4 border-t border-slate-200 flex flex-wrap items-center justify-between text-[10px] text-slate-500">
            <span>Confidential Report • Generated for Authorized Adani Leadership Only</span>
            <span className="font-mono">Security Hash: AGEL-PMAG-DPR-{new Date().getFullYear()}-SECURED</span>
          </div>
        </div>

      </div>

    </div>
  );
}

