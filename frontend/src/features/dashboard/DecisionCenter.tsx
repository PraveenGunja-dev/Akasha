import React from 'react';
import { Target, CheckCircle, Clock, AlertTriangle, ArrowRight, DollarSign } from 'lucide-react';

export default function DecisionCenter({ p6Data, finDetails }: any) {
  
  // Synthesize Actionable Decisions based on actual data thresholds

  // 1. Schedule Actions (P6 delays > 30 days)
  const scheduleActions = (p6Data || [])
    .filter((p: any) => (p.finishDateVariance || 0) < -30)
    .sort((a: any, b: any) => b.finishDateVariance - a.finishDateVariance)
    .slice(0, 5) // Top 5 critical actions
    .map((p: any) => ({
      id: p.project_id,
      title: `Schedule Recovery Required: ${p.name}`,
      description: `Project has slipped by ${p.finishDateVariance} days past baseline finish date. Critical path intervention required.`,
      type: 'schedule',
      priority: 'high'
    }));

  // 2. Financial Actions (High Value PO Concentration > 500MW)
  const financialActions = (finDetails || [])
    .filter((po: any) => po.po_quantities_mw > 500)
    .sort((a: any, b: any) => b.po_quantities_mw - a.po_quantities_mw)
    .slice(0, 5)
    .map((po: any) => ({
      id: po.purchasing_document,
      title: `Vendor Risk Review: ${po.vendor_name}`,
      description: `Single Purchase Order (${po.purchasing_document}) accounts for ${po.po_quantities_mw.toFixed(1)} MW of exposure. Recommend diversification review.`,
      type: 'financial',
      priority: 'medium'
    }));

  const allActions = [...scheduleActions, ...financialActions];

  return (
    <div className="flex flex-col gap-6 max-w-[1600px] mx-auto animate-in fade-in duration-500 pb-10">
      
      <div className="flex items-center gap-3 mb-2">
        <Target className="w-6 h-6 text-primary" />
        <div>
          <h2 className="text-xl font-semibold text-foreground tracking-wide">CEO Decision Center</h2>
          <p className="text-sm text-muted-foreground">Executive action board generated from live P6 & SAP variances.</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        
        {/* KPI Summary Column */}
        <div className="col-span-1 flex flex-col gap-4">
           <div className="bg-card border border-border rounded-2xl p-6 shadow-sm">
             <h3 className="text-muted-foreground text-xs font-medium mb-2 uppercase tracking-wider">Total Pending Actions</h3>
             <p className="text-4xl font-light text-foreground">{allActions.length}</p>
           </div>
           <div className="bg-card border border-red-500/30 rounded-2xl p-6 shadow-sm">
             <h3 className="text-muted-foreground text-xs font-medium mb-2 uppercase tracking-wider flex items-center gap-2">
               <AlertTriangle className="w-4 h-4 text-red-500" /> High Priority
             </h3>
             <p className="text-4xl font-light text-red-500">{allActions.filter(a => a.priority === 'high').length}</p>
           </div>
        </div>

        {/* Action Board Column */}
        <div className="col-span-1 lg:col-span-3 bg-card border border-border rounded-2xl p-6 shadow-sm min-h-[500px]">
          <div className="flex items-center justify-between mb-6 pb-4 border-b border-border">
            <h3 className="text-lg font-medium text-foreground tracking-wide">Recommended Executive Actions</h3>
            <div className="flex gap-2">
               <span className="text-[10px] uppercase font-semibold tracking-wider bg-muted text-muted-foreground px-3 py-1.5 rounded-lg border border-border">Sort by Priority</span>
            </div>
          </div>

          <div className="space-y-4">
            {allActions.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-48 text-muted-foreground/70">
                 <CheckCircle className="w-12 h-12 mb-3 text-emerald-500/50" />
                 <p>No critical actions required at this time.</p>
              </div>
            ) : (
              allActions.map((action, idx) => (
                <div key={`${action.id}-${idx}`} className="group flex flex-col sm:flex-row gap-4 p-4 rounded-xl border border-border bg-muted hover:border-primary/50 transition-colors relative overflow-hidden">
                   
                   {/* Priority Indicator Line */}
                   <div className={`absolute left-0 top-0 bottom-0 w-1 ${action.priority === 'high' ? 'bg-red-500' : 'bg-amber-500'}`}></div>

                   <div className="flex-shrink-0 pl-2">
                      {action.type === 'schedule' ? (
                        <div className="p-3 bg-red-500/10 rounded-lg"><Clock className="w-6 h-6 text-red-500" /></div>
                      ) : (
                        <div className="p-3 bg-amber-500/10 rounded-lg"><DollarSign className="w-6 h-6 text-amber-500" /></div>
                      )}
                   </div>
                   
                   <div className="flex-1">
                     <div className="flex items-start justify-between mb-1">
                       <h4 className="text-base font-medium text-foreground">{action.title}</h4>
                       <span className={`text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded ${action.priority === 'high' ? 'bg-red-500/20 text-red-500' : 'bg-amber-500/20 text-amber-500'}`}>
                         {action.priority}
                       </span>
                     </div>
                     <p className="text-sm text-muted-foreground mb-4">{action.description}</p>
                     
                     <div className="flex flex-wrap gap-2">
                       <button className="flex items-center gap-1.5 text-xs font-semibold bg-primary hover:bg-blue-600 text-primary-foreground px-4 py-2 rounded-lg transition-colors">
                         Approve Intervention <CheckCircle className="w-3.5 h-3.5" />
                       </button>
                       <button className="flex items-center gap-1.5 text-xs font-medium bg-card hover:bg-accent border border-border text-foreground px-4 py-2 rounded-lg transition-colors">
                         Delegate to PM <ArrowRight className="w-3.5 h-3.5" />
                       </button>
                     </div>
                   </div>
                </div>
              ))
            )}
          </div>
        </div>

      </div>
    </div>
  );
}
