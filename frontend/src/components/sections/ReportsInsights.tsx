import React from 'react';
import { FileText, Printer, Download, Share2 } from 'lucide-react';

export default function ReportsInsights({ p6Data, sapData, finDetails }: any) {
  
  // Aggregate data for the report
  const totalProjects = p6Data?.length || 0;
  const delayedProjects = (p6Data || []).filter((p: any) => (p.finishDateVariance || 0) < -30).length;
  const totalCapex = (sapData || []).reduce((acc: number, curr: any) => acc + (curr.actualCapex || 0), 0);
  
  // Find top vendor
  const vendorMap: any = {};
  (finDetails || []).forEach((po: any) => {
      const v = po.vendor_name || 'Unknown Vendor';
      vendorMap[v] = (vendorMap[v] || 0) + po.po_quantities_mw;
  });
  const topVendor = Object.keys(vendorMap).sort((a,b) => vendorMap[b] - vendorMap[a])[0] || 'N/A';
  const topVendorVol = vendorMap[topVendor] || 0;

  const handlePrint = () => {
    window.print();
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
           <button onClick={handlePrint} className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-muted hover:bg-accent border border-border rounded-lg transition-colors text-foreground">
             <Printer className="w-4 h-4" /> Print
           </button>
           <button className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-muted hover:bg-accent border border-border rounded-lg transition-colors text-foreground">
             <Download className="w-4 h-4" /> PDF
           </button>
           <button className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-primary hover:bg-primary/90 rounded-lg transition-colors text-primary-foreground">
             <Share2 className="w-4 h-4" /> Share
           </button>
         </div>
      </div>

      {/* The Printable Report Document */}
      <div id="executive-report" className="bg-muted border border-border rounded-2xl p-10 shadow-[0_10px_40px_rgba(0,0,0,0.5)]">
         
         {/* Document Header */}
         <div className="flex justify-between items-start border-b border-border/50 pb-6 mb-8">
           <div>
             <h1 className="text-2xl font-bold tracking-wider text-foreground uppercase">AKASHA Intelligence</h1>
             <p className="text-sm text-primary font-medium tracking-[0.2em] uppercase mt-1">Daily Executive Portfolio Report</p>
           </div>
           <div className="text-right">
             <p className="text-sm text-muted-foreground font-mono">DATE: {new Date().toLocaleDateString()}</p>
             <p className="text-sm text-muted-foreground font-mono">TIME: {new Date().toLocaleTimeString()}</p>
             <p className="text-sm text-emerald-500 font-mono mt-2 flex items-center justify-end gap-1">
               <span className="w-2 h-2 rounded-full bg-emerald-500"></span> Data Synced
             </p>
           </div>
         </div>

         {/* Document Body */}
         <div className="space-y-8 text-foreground/90 leading-relaxed text-justify">
           
           <section>
             <h3 className="text-lg font-semibold text-foreground mb-3 uppercase tracking-wider border-l-2 border-primary pl-3">1. Portfolio Overview</h3>
             <p>
               As of today, the global portfolio consists of <strong>{totalProjects} active projects</strong> managed across Primavera P6. 
               The total aggregated actual capital expenditure (YTD) derived from SAP Financials currently stands at <strong>${totalCapex > 1000 ? (totalCapex/1000).toFixed(2) + ' Billion' : totalCapex.toFixed(1) + ' Million'}</strong>.
             </p>
           </section>

           <section>
             <h3 className="text-lg font-semibold text-foreground mb-3 uppercase tracking-wider border-l-2 border-red-500 pl-3">2. Schedule Risk Assessment</h3>
             <p>
               Analysis of current baseline vs. actual finish dates indicates that <strong>{delayedProjects} projects</strong> have slipped past a 30-day critical variance threshold. 
               Immediate executive review is recommended for these packages to prevent cascading supply chain delays.
             </p>
           </section>

           <section>
             <h3 className="text-lg font-semibold text-foreground mb-3 uppercase tracking-wider border-l-2 border-amber-500 pl-3">3. Procurement & Supply Chain</h3>
             <p>
               Vendor concentration analysis flags <strong>{topVendor}</strong> as the current highest volume supplier, holding active POs totaling <strong>{topVendorVol.toFixed(1)} MW</strong>. 
               Monitoring this vendor's delivery schedule is critical to maintaining the portfolio's critical path.
             </p>
           </section>

         </div>

         {/* Signatures */}
         <div className="mt-16 pt-8 border-t border-border/50 flex justify-between">
            <div className="w-48">
              <div className="border-b border-border mb-2 h-8"></div>
              <p className="text-xs text-muted-foreground/70 uppercase tracking-wider text-center">AI generated by</p>
              <p className="text-sm text-foreground/90 font-medium text-center">Akasha Copilot</p>
            </div>
            <div className="w-48">
              <div className="border-b border-border mb-2 h-8"></div>
              <p className="text-xs text-muted-foreground/70 uppercase tracking-wider text-center">Reviewed by</p>
              <p className="text-sm text-foreground/90 font-medium text-center">Executive Office</p>
            </div>
         </div>
      </div>
      
    </div>
  );
}
