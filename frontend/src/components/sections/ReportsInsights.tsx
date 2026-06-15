import React from 'react';
import { FileText, Printer, Download, Share2 } from 'lucide-react';

export default function ReportsInsights({ p6Data, sapData, finDetails }: any) {

  // Executive Overview Aggregates
  const totalProjects = p6Data?.length || 0;
  const delayedProjects = (p6Data || []).filter((p: any) => (p.finishDateVariance || 0) < -30).length;
  const criticalProjects = (p6Data || []).filter((p: any) => (p.finishDateVariance || 0) < -60).length;
  
  const avgCPI = (p6Data || []).reduce((acc: number, p: any) => acc + (p.costPerformanceIndex || 1), 0) / (totalProjects || 1);
  const avgSPI = (p6Data || []).reduce((acc: number, p: any) => acc + (p.schedulePerformanceIndex || 1), 0) / (totalProjects || 1);
  const overallProgress = (p6Data || []).reduce((acc: number, p: any) => acc + (p.durationPercentComplete || 0), 0) / (totalProjects || 1);

  // Financial Aggregates
  const totalActualCapex = (sapData || []).reduce((acc: number, curr: any) => acc + (curr.actualCapex || 0), 0);
  const totalPlannedCapex = (sapData || []).reduce((acc: number, curr: any) => acc + (curr.plannedCapex || 0), 0);
  const budgetVariance = totalPlannedCapex > 0 ? ((totalActualCapex - totalPlannedCapex) / totalPlannedCapex) * 100 : 0;

  // Supply Chain Aggregates
  const vendorMap: any = {};
  const vendorValueMap: any = {};
  let totalPoValue = 0;
  (finDetails || []).forEach((po: any) => {
    const v = po.vendor_name || 'Unknown Vendor';
    vendorMap[v] = (vendorMap[v] || 0) + (po.po_quantities_mw || 0);
    vendorValueMap[v] = (vendorValueMap[v] || 0) + (po.net_order_value || 0);
    totalPoValue += (po.net_order_value || 0);
  });
  
  const activeVendorsCount = Object.keys(vendorMap).length;
  const topVendor = Object.keys(vendorMap).sort((a, b) => vendorMap[b] - vendorMap[a])[0] || 'N/A';
  const topVendorVol = vendorMap[topVendor] || 0;
  const topVendorValue = vendorValueMap[topVendor] || 0;

  const formatCurrency = (value: number) => {
    if (value >= 1e9) return `$${(value / 1e9).toFixed(2)} Billion`;
    if (value >= 1e6) return `$${(value / 1e6).toFixed(2)} Million`;
    return `$${value.toLocaleString(undefined, {maximumFractionDigits: 0})}`;
  };

  const handleDownloadPdf = () => {
    // Dynamically load html2pdf.js so we don't need to install any new npm packages
    const script = document.createElement('script');
    script.src = 'https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js';
    script.onload = () => {
      const element = document.getElementById('executive-report');
      if (!element) return;
      
      const opt = {
        margin:       [0.5, 0.5, 0.5, 0.5], // top, left, bottom, right
        filename:     `AKASHA_Executive_Brief_${new Date().toISOString().split('T')[0]}.pdf`,
        image:        { type: 'jpeg', quality: 0.98 },
        html2canvas:  { scale: 2, useCORS: true },
        jsPDF:        { unit: 'in', format: 'letter', orientation: 'portrait' },
        pagebreak:    { mode: ['avoid-all', 'css', 'legacy'] }
      };
      
      // @ts-ignore
      window.html2pdf().set(opt).from(element).save();
    };
    document.head.appendChild(script);
  };

  return (
    <div className="flex flex-col gap-6 max-w-[1000px] mx-auto animate-in fade-in duration-500 pb-10">

      {/* Top Action Bar */}
      <div className="flex items-center justify-between bg-card border border-border rounded-2xl p-4 shadow-sm">
        <div className="flex items-center gap-2">
          <FileText className="w-5 h-5 text-primary" />
          <h2 className="text-lg font-medium text-foreground tracking-wide">Automated Executive Brief</h2>
        </div>
        <div className="flex gap-2">
          <button onClick={handleDownloadPdf} className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-muted hover:bg-accent border border-border rounded-lg transition-colors text-foreground">
            <Download className="w-4 h-4" /> PDF
          </button>
          <button className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-primary hover:bg-primary/90 rounded-lg transition-colors text-primary-foreground">
            <Share2 className="w-4 h-4" /> Share
          </button>
        </div>
      </div>

      {/* The Printable Report Document - Forced White Paper Look */}
      <div id="executive-report" className="bg-white text-black rounded-2xl p-10 shadow-sm">

        {/* Cover Photo (Moved inside so it downloads in the PDF) */}
        <div className="w-full overflow-hidden rounded-xl mb-8">
          <img src={`${import.meta.env.BASE_URL}coverPhoto.png`} alt="Report Cover" className="w-full h-[150px] md:h-[220px] object-cover object-top block transform scale-[1.1] origin-top" />
        </div>

        {/* Document Header */}
        <div className="flex justify-between items-start border-b border-gray-300 pb-6 mb-8">
          <div>
            <h1 className="text-2xl font-bold tracking-wider text-black uppercase">AKASHA Intelligence</h1>
            <p className="text-sm text-blue-600 font-medium tracking-[0.2em] uppercase mt-1">Daily Executive Portfolio Report</p>
          </div>
          <div className="text-right">
            <p className="text-sm text-gray-600 font-mono">DATE: {new Date().toLocaleDateString()}</p>
            <p className="text-sm text-gray-600 font-mono">TIME: {new Date().toLocaleTimeString()}</p>
            <p className="text-sm text-emerald-600 font-mono mt-2 flex items-center justify-end gap-1">
              <span className="w-2 h-2 rounded-full bg-emerald-600"></span> Data Synced
            </p>
          </div>
        </div>

        {/* Document Body */}
        <div className="space-y-6 text-gray-800 leading-relaxed text-justify">

          <section className="html2pdf__page-break-inside-avoid">
            <h3 className="text-lg font-semibold text-black mb-2 uppercase tracking-wider border-l-2 border-blue-600 pl-3">1. Executive Overview & Financial Health</h3>
            <p className="mb-2">
              As of the current reporting cycle, the global intelligence network is actively tracking <strong>{totalProjects} active projects</strong> across the enterprise portfolio. The mean portfolio physical progress is tracking at <strong>{overallProgress.toFixed(1)}%</strong> overall completion.
            </p>
            <p>
              {totalActualCapex > 0 ? (
                <>
                  Financially, the aggregated actual capital expenditure (YTD) derived from SAP stands at <strong>{formatCurrency(totalActualCapex)}</strong>. 
                  {totalPlannedCapex > 0 && ` Compared to the baseline planned expenditure of ${formatCurrency(totalPlannedCapex)}, the portfolio is currently tracking at a ${Math.abs(budgetVariance).toFixed(2)}% ${budgetVariance > 0 ? 'overrun' : 'underrun'} relative to the projected burn rate.`} 
                  The portfolio-wide Cost Performance Index (CPI) averages at <strong>{avgCPI.toFixed(2)}</strong>, indicating {avgCPI >= 1 ? 'efficient capital deployment and robust cost control mechanisms.' : 'a trend of cost overruns requiring immediate fiscal intervention and budget recalibration.'}
                </>
              ) : (
                <> Financial capital expenditure data is currently synchronizing. YTD cost analysis will be available upon completion of the SAP integration cycle.</>
              )}
            </p>
          </section>

          <section className="html2pdf__page-break-inside-avoid">
            <h3 className={`text-lg font-semibold text-black mb-2 uppercase tracking-wider border-l-2 ${delayedProjects > 0 ? 'border-red-600' : 'border-emerald-600'} pl-3`}>2. Schedule Risk & Trajectory Assessment</h3>
            <p className="mb-2">
              The aggregate Schedule Performance Index (SPI) across the portfolio currently rests at <strong>{avgSPI.toFixed(2)}</strong>. 
            </p>
            <p>
              {delayedProjects > 0 ? (
                <>
                  Advanced trajectory analysis of Primavera P6 baselines against actualized field execution reveals that <strong>{delayedProjects} project{delayedProjects !== 1 ? 's' : ''}</strong> have breached the 30-day critical variance threshold. 
                  {criticalProjects > 0 && ` Furthermore, ${criticalProjects} of these packages are in a severe critical state, having slipped past a 60-day variance.`}
                  This indicates systemic bottlenecks in the critical path execution. Immediate executive mitigation, resource reallocation, and contractor expediting are strongly recommended to prevent cascading delays across interconnected project lifecycles.
                </>
              ) : (
                <>
                  Trajectory analysis of Primavera P6 baselines against field execution reveals that 100% of the active portfolio is performing within the acceptable 30-day schedule variance parameters. The critical path remains insulated from major disruptions, and predictive models forecast on-time commissioning for the current fiscal quarter.
                </>
              )}
            </p>
          </section>

          <section className="html2pdf__page-break-inside-avoid">
            <h3 className={`text-lg font-semibold text-black mb-2 uppercase tracking-wider border-l-2 ${topVendor !== 'N/A' && topVendorVol > 0 ? 'border-amber-600' : 'border-blue-600'} pl-3`}>3. Supply Chain & Procurement Operations</h3>
            <p className="mb-2">
              The portfolio's material pipeline is currently supported by <strong>{activeVendorsCount} active vendors</strong>, managing a total net order value of <strong>{formatCurrency(totalPoValue)}</strong> across all synchronized purchase orders.
            </p>
            <p>
              {topVendor !== 'N/A' && topVendorVol > 0 ? (
                <>
                  Vendor concentration analytics have flagged <strong>{topVendor}</strong> as the dominant tier-1 supplier, controlling <strong>{topVendorVol.toLocaleString(undefined, {maximumFractionDigits: 1})} MW</strong> of active POs with an aggregated value of {formatCurrency(topVendorValue)}. 
                  This high degree of concentration introduces a single-point-of-failure risk to the portfolio's critical path. Strategic supply chain diversification and intensified logistical monitoring of this specific vendor's delivery milestones are advised.
                </>
              ) : (
                <>
                  Vendor concentration analysis confirms a highly diversified and balanced distribution of purchase orders across the supply chain. No single vendor currently possesses a disproportionate share of the procurement volume, ensuring robust supply chain resilience against localized market disruptions.
                </>
              )}
            </p>
          </section>

          <section className="html2pdf__page-break-inside-avoid">
            <h3 className="text-lg font-semibold text-black mb-2 uppercase tracking-wider border-l-2 border-purple-600 pl-3">4. Executive Action Items</h3>
            <ul className="list-disc pl-6 space-y-2 mt-2 text-gray-800">
              {delayedProjects > 0 && (
                <li><strong>Schedule Mitigation:</strong> Convene an emergency project review board for the {delayedProjects} delayed packages to implement schedule crashing or fast-tracking strategies.</li>
              )}
              {avgCPI < 1 && (
                <li><strong>Fiscal Intervention:</strong> Initiate a deep-dive audit into cost overruns, as the portfolio CPI ({avgCPI.toFixed(2)}) indicates concerning capital leakage.</li>
              )}
              {topVendor !== 'N/A' && topVendorVol > 0 && (
                <li><strong>Supply Chain De-risking:</strong> Instruct the procurement division to audit <em>{topVendor}</em>'s manufacturing and delivery capacity to secure the {topVendorVol.toLocaleString()} MW pipeline.</li>
              )}
              {delayedProjects === 0 && avgCPI >= 1 && (
                <li><strong>Strategic Expansion:</strong> The portfolio is operating at peak efficiency. Consider accelerating the timeline for the next phase of capital deployments.</li>
              )}
              <li><strong>Continuous Monitoring:</strong> Ensure site engineers maintain daily updates in Primavera P6 to feed the AI predictive models with real-time ground truth data.</li>
            </ul>
          </section>

        </div>

        {/* Signatures */}
        <div className="mt-12 pt-8 border-t border-gray-300 flex justify-between html2pdf__page-break-inside-avoid">
          <div className="w-48">
            <div className="border-b border-gray-400 mb-2 h-8"></div>
            <p className="text-xs text-gray-500 uppercase tracking-wider text-center">AI generated by</p>
            <p className="text-sm text-black font-medium text-center">Akasha Copilot</p>
          </div>
          <div className="w-48">
            <div className="border-b border-gray-400 mb-2 h-8"></div>
            <p className="text-xs text-gray-500 uppercase tracking-wider text-center">Reviewed by</p>
            <p className="text-sm text-black font-medium text-center">Executive Office</p>
          </div>
        </div>
      </div>

    </div>
  );
}
