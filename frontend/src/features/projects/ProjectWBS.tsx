import React, { useState, useMemo } from 'react';
import { Layers, ChevronDown, ChevronRight, CheckCircle2, Clock, PlayCircle, Save, X, Edit2, Loader2, AlertTriangle } from 'lucide-react';

const statusColors: any = {
  'Completed': 'bg-success/10 text-success border-success/20',
  'In Progress': 'bg-primary/10 text-primary border-primary/20',
  'Not Started': 'bg-muted0/10 text-muted-foreground border-slate-500/20',
};

const getStatusIcon = (status: string) => {
  if (status === 'Completed') return <CheckCircle2 className="w-3.5 h-3.5" />;
  if (status === 'In Progress') return <PlayCircle className="w-3.5 h-3.5" />;
  return <Clock className="w-3.5 h-3.5" />;
};

interface ActivityRowProps {
  act: any;
  onUpdateActivity: (id: string, data: any) => Promise<boolean>;
}

const ActivityRow = ({ act, onUpdateActivity }: ActivityRowProps) => {
  const [isEditing, setIsEditing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  // Safe extraction of resources
  const resources = act.resources || {};
  const labor = resources["Labor"] || { p6ObjectId: null, plannedUnits: '', actualUnits: '' };
  const material = resources["Material"] || { p6ObjectId: null, plannedUnits: '', actualUnits: '' };

  const [editData, setEditData] = useState({
    status: act.status || 'Not Started',
    forecastStartDate: act.forecastStartDate || '',
    forecastFinishDate: act.forecastFinishDate || '',
    baselineStartDate: act.baselineStartDate || '',
    baselineFinishDate: act.baselineFinishDate || '',
    actualStartDate: act.actualStartDate || '',
    actualFinishDate: act.actualFinishDate || '',
    
    laborBudgetedUnits: labor.plannedUnits || '',
    laborActualUnits: labor.actualUnits || '',
    materialBudgetedUnits: material.plannedUnits || '',
    materialActualUnits: material.actualUnits || '',
  });

  const handleSave = async () => {
    setIsSaving(true);
    setError(null);
    
    // Format payload
    const payload = {
      status: editData.status,
      start_date: editData.forecastStartDate ? `${editData.forecastStartDate}T00:00:00+05:30` : null,
      finish_date: editData.forecastFinishDate ? `${editData.forecastFinishDate}T00:00:00+05:30` : null,
      actual_start_date: editData.actualStartDate ? `${editData.actualStartDate}T00:00:00+05:30` : null,
      actual_finish_date: editData.actualFinishDate ? `${editData.actualFinishDate}T00:00:00+05:30` : null,
      baseline_start_date: editData.baselineStartDate ? `${editData.baselineStartDate}T00:00:00+05:30` : null,
      baseline_finish_date: editData.baselineFinishDate ? `${editData.baselineFinishDate}T00:00:00+05:30` : null,
      resources: {} as Record<string, any>
    };
    
    if (labor.p6ObjectId) {
      payload.resources["Labor"] = {
        p6ObjectId: labor.p6ObjectId,
        plannedUnits: editData.laborBudgetedUnits ? Number(editData.laborBudgetedUnits) : null,
        actualUnits: editData.laborActualUnits ? Number(editData.laborActualUnits) : null,
      };
    }
    if (material.p6ObjectId) {
      payload.resources["Material"] = {
        p6ObjectId: material.p6ObjectId,
        plannedUnits: editData.materialBudgetedUnits ? Number(editData.materialBudgetedUnits) : null,
        actualUnits: editData.materialActualUnits ? Number(editData.materialActualUnits) : null,
      };
    }

    const res = await fetch(`/akasha/api/p6/activities/${act.p6ObjectId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    
    if (res.ok) {
      setIsEditing(false);
      // Ideally refresh data here
    } else {
      try {
        const errData = await res.json();
        setError(errData.detail || "Failed to push update to Oracle P6.");
      } catch (e) {
        setError(`Failed to push update (Status ${res.status})`);
      }
    }
    setIsSaving(false);
  };

  const isDelayed = false; 

  return (
    <div className={`flex flex-col border-b border-border/30 hover:bg-muted transition-colors ${isDelayed ? 'bg-destructive/5' : ''}`}>
      {/* View Mode Row / Edit Mode Header Row */}
      <div className="grid grid-cols-12 gap-4 py-2.5 px-4 items-center">
        <div className="col-span-5 flex flex-col gap-1">
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium text-foreground">{act.name}</span>
            {isDelayed && (
              <span className="flex items-center gap-1 text-[10px] font-bold text-destructive bg-destructive/10 px-1.5 py-0.5 rounded">
                <AlertTriangle className="w-3 h-3" /> DELAYED
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-mono text-muted-foreground">{act.activityId}</span>
            <span className={`flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[9px] font-bold tracking-wider uppercase border ${statusColors[editData.status] || statusColors['Not Started']}`}>
              {getStatusIcon(editData.status)} {editData.status}
            </span>
          </div>
        </div>
        
        {isEditing ? (
           <div className="col-span-7 flex justify-end gap-2 items-center">
              <span className="text-xs font-semibold text-primary mr-2">EDITING ACTIVITY</span>
              <button className="flex items-center gap-1 bg-success/10 text-success border border-success/20 px-3 py-1 rounded hover:bg-success/20 transition-colors text-xs font-semibold" onClick={handleSave} disabled={isSaving}>
                {isSaving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />} SAVE TO P6
              </button>
              <button className="flex items-center gap-1 bg-muted border border-border px-3 py-1 rounded hover:bg-muted transition-colors text-xs font-semibold text-muted-foreground" onClick={() => { setIsEditing(false); setError(null); }} disabled={isSaving}>
                <X className="w-3 h-3" /> CANCEL
              </button>
           </div>
        ) : (
          <>
            <div className="col-span-2 flex flex-col gap-0.5">
              <span className="text-[10px] uppercase tracking-wider text-muted-foreground">Forecast Start</span>
              <span className="text-xs font-mono">{act.forecastStartDate || '—'}</span>
            </div>
            <div className="col-span-2 flex flex-col gap-0.5">
              <span className="text-[10px] uppercase tracking-wider text-muted-foreground">Forecast Finish</span>
              <span className="text-xs font-mono">{act.forecastFinishDate || '—'}</span>
            </div>
            <div className="col-span-2 flex flex-col gap-0.5">
              <span className="text-[10px] uppercase tracking-wider text-muted-foreground">Baseline Finish</span>
              <span className="text-xs font-mono text-muted-foreground/70">{act.baselineFinishDate || '—'}</span>
            </div>
            <div className="col-span-1 flex justify-end">
              <button className="h-6 w-6 flex items-center justify-center rounded-md opacity-0 group-hover:opacity-100 hover:bg-primary/10 hover:text-primary transition-all" onClick={() => setIsEditing(true)}>
                <Edit2 className="w-3 h-3" />
              </button>
            </div>
          </>
        )}
      </div>

      {/* Expanded Edit Form */}
      {isEditing && (
        <div className="px-4 pb-4 pt-2 border-t border-border/20 bg-background/50 grid grid-cols-12 gap-6 relative">
          {error && <div className="absolute top-0 left-0 right-0 bg-destructive/10 text-destructive text-xs text-center py-1 font-semibold">{error}</div>}
          
          <div className="col-span-12 md:col-span-5 grid grid-cols-2 gap-4">
            <div className="col-span-2">
              <label className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider block mb-1">Status</label>
              <select 
                value={editData.status} 
                onChange={(e) => setEditData({...editData, status: e.target.value})}
                className="w-full text-xs bg-card border border-border rounded px-3 py-2 outline-none focus:border-primary/50"
              >
                <option value="Not Started">Not Started</option>
                <option value="In Progress">In Progress</option>
                <option value="Completed">Completed</option>
              </select>
            </div>

            <div>
              <label className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider block mb-1">Forecast Start</label>
              <input type="date" value={editData.forecastStartDate} onChange={(e) => setEditData({...editData, forecastStartDate: e.target.value})} className="w-full text-xs bg-card border border-border rounded px-2 py-1.5 outline-none focus:border-primary/50" />
            </div>
            <div>
              <label className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider block mb-1">Forecast Finish</label>
              <input type="date" value={editData.forecastFinishDate} onChange={(e) => setEditData({...editData, forecastFinishDate: e.target.value})} className="w-full text-xs bg-card border border-border rounded px-2 py-1.5 outline-none focus:border-primary/50" />
            </div>

            <div>
              <label className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider block mb-1">Baseline Start</label>
              <input type="date" value={editData.baselineStartDate} onChange={(e) => setEditData({...editData, baselineStartDate: e.target.value})} className="w-full text-xs bg-card border border-border rounded px-2 py-1.5 outline-none focus:border-primary/50" />
            </div>
            <div>
              <label className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider block mb-1">Baseline Finish</label>
              <input type="date" value={editData.baselineFinishDate} onChange={(e) => setEditData({...editData, baselineFinishDate: e.target.value})} className="w-full text-xs bg-card border border-border rounded px-2 py-1.5 outline-none focus:border-primary/50" />
            </div>

            <div>
              <label className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider block mb-1">Actual Start</label>
              <input type="date" value={editData.actualStartDate} onChange={(e) => setEditData({...editData, actualStartDate: e.target.value})} className="w-full text-xs bg-card border border-border rounded px-2 py-1.5 outline-none focus:border-primary/50" />
            </div>
            <div>
              <label className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider block mb-1">Actual Finish</label>
              <input type="date" value={editData.actualFinishDate} onChange={(e) => setEditData({...editData, actualFinishDate: e.target.value})} className="w-full text-xs bg-card border border-border rounded px-2 py-1.5 outline-none focus:border-primary/50" />
            </div>
          </div>

          {/* Resources Block */}
          <div className="col-span-12 md:col-span-7 bg-card rounded-lg border border-border p-3">
             <h4 className="text-xs font-semibold text-foreground mb-3 flex items-center gap-2"><Layers className="w-3.5 h-3.5" /> Resource Assignments</h4>
             
             <div className="grid grid-cols-12 gap-2 text-[10px] font-bold text-muted-foreground uppercase tracking-wider mb-2 px-2">
                <div className="col-span-4">Type</div>
                <div className="col-span-4">Budgeted Units</div>
                <div className="col-span-4">Actual Units</div>
             </div>

             <div className="flex flex-col gap-2">
               {/* Labor */}
               {labor.p6ObjectId ? (
                 <div className="grid grid-cols-12 gap-2 items-center px-2 py-1 hover:bg-muted rounded">
                   <div className="col-span-4 text-xs text-foreground font-medium flex items-center gap-1"><div className="w-2 h-2 rounded-full bg-primary/100"></div> Labor</div>
                   <div className="col-span-4"><input type="number" step="0.1" value={editData.laborBudgetedUnits} onChange={(e) => setEditData({...editData, laborBudgetedUnits: e.target.value})} className="w-full text-xs bg-background border border-border rounded px-2 py-1 outline-none" /></div>
                   <div className="col-span-4"><input type="number" step="0.1" value={editData.laborActualUnits} onChange={(e) => setEditData({...editData, laborActualUnits: e.target.value})} className="w-full text-xs bg-background border border-border rounded px-2 py-1 outline-none" /></div>
                 </div>
               ) : <div className="px-2 text-xs text-muted-foreground/50 italic">No Labor resources assigned</div>}

               {/* Material */}
               {material.p6ObjectId ? (
                 <div className="grid grid-cols-12 gap-2 items-center px-2 py-1 hover:bg-muted rounded">
                   <div className="col-span-4 text-xs text-foreground font-medium flex items-center gap-1"><div className="w-2 h-2 rounded-full bg-warning/100"></div> Material</div>
                   <div className="col-span-4"><input type="number" step="0.1" value={editData.materialBudgetedUnits} onChange={(e) => setEditData({...editData, materialBudgetedUnits: e.target.value})} className="w-full text-xs bg-background border border-border rounded px-2 py-1 outline-none" /></div>
                   <div className="col-span-4"><input type="number" step="0.1" value={editData.materialActualUnits} onChange={(e) => setEditData({...editData, materialActualUnits: e.target.value})} className="w-full text-xs bg-background border border-border rounded px-2 py-1 outline-none" /></div>
                 </div>
               ) : <div className="px-2 text-xs text-muted-foreground/50 italic">No Material resources assigned</div>}
             </div>
          </div>
        </div>
      )}
    </div>
  );
};

const WBSNode = ({ node, level, onUpdateActivity }: any) => {
  const [isExpanded, setIsExpanded] = useState(false);
  
  if (node.activities.length === 0 && node.children.length === 0) return null;

  return (
    <div className="border-l border-border/30 ml-4 pl-2 my-1">
      <div 
        className="flex items-center gap-2 py-2 px-2 hover:bg-muted cursor-pointer rounded transition-colors group"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        {isExpanded ? <ChevronDown className="w-3.5 h-3.5 text-primary" /> : <ChevronRight className="w-3.5 h-3.5 text-muted-foreground group-hover:text-primary" />}
        <span className="text-[11px] font-mono font-bold text-muted-foreground bg-muted px-1.5 py-0.5 rounded">{node.code}</span>
        <span className="text-sm font-semibold text-foreground/90">{node.name}</span>
        <span className="text-[10px] text-muted-foreground ml-auto bg-background border border-border px-1.5 rounded-full">
          {node.activities.length} acts
        </span>
      </div>

      {isExpanded && (
        <div className="mt-1 flex flex-col gap-1">
          {node.activities.map((act: any) => (
            <div key={act.activityId} className="ml-6 group bg-background/50 rounded-lg border border-border/50 shadow-sm overflow-hidden mb-1">
               <ActivityRow act={act} onUpdateActivity={onUpdateActivity} />
            </div>
          ))}
          {node.children.map((child: any) => (
            <WBSNode key={child.wbsObjectId} node={child} level={level + 1} onUpdateActivity={onUpdateActivity} />
          ))}
        </div>
      )}
    </div>
  );
};

export const ProjectWBS = ({ p6Data }: { p6Data: any }) => {
  const [filter, setFilter] = useState('All');
  const statuses = ['All', 'Completed', 'In Progress', 'Not Started'];

  const onUpdateActivity = async (id: string, data: any) => {
    // Moved fetch logic directly to ActivityRow for better error handling
    return false;
  };

  const rootNodes = useMemo(() => {
    if (!p6Data?.wbsNodes || !p6Data?.allActivities) return [];

    const wbsMap = new Map();
    p6Data.wbsNodes.forEach((n: any) => {
      wbsMap.set(n.wbsObjectId, { ...n, children: [], activities: [] });
    });

    const roots: any[] = [];
    wbsMap.forEach((n) => {
      if (n.parentObjectId && wbsMap.has(n.parentObjectId)) {
        wbsMap.get(n.parentObjectId).children.push(n);
      } else {
        roots.push(n);
      }
    });

    const filteredActs = filter === 'All' 
      ? p6Data.allActivities 
      : p6Data.allActivities.filter((a: any) => a.status === filter);

    filteredActs.forEach((act: any) => {
      if (act.wbsObjectId && wbsMap.has(act.wbsObjectId)) {
        wbsMap.get(act.wbsObjectId).activities.push(act);
      } else if (roots.length > 0) {
        roots[0].activities.push(act); // fallback
      }
    });

    // Cleanup empty nodes
    const pruneEmpty = (node: any): boolean => {
      node.children = node.children.filter(pruneEmpty);
      return node.activities.length > 0 || node.children.length > 0;
    };

    const prunedRoots = roots.filter(pruneEmpty);
    
    // Sort all levels numerically by extracting the leading number from the code
    const sortWBS = (nodes: any[]) => {
      nodes.sort((a, b) => {
        const getNum = (code: string) => {
          if (!code) return 999999;
          const strCode = String(code).trim();
          const match = strCode.match(/^(\d+)/);
          return match ? parseInt(match[1], 10) : 999999;
        };
        return getNum(a.code) - getNum(b.code);
      });
      nodes.forEach(n => sortWBS(n.children));
    };
    
    sortWBS(prunedRoots);
    return prunedRoots;
  }, [p6Data, filter]);

  if (!p6Data?.wbsNodes || p6Data.wbsNodes.length === 0) {
    return (
      <div className="p-12 text-center border border-dashed border-border rounded-xl">
        <Layers className="w-8 h-8 text-muted-foreground/30 mx-auto mb-3" />
        <p className="text-muted-foreground">WBS Hierarchy not available. Please run P6 sync.</p>
      </div>
    );
  }

  return (
    <div className="intelligence-card p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
          <Layers className="w-4 h-4 text-primary/70" /> P6 WBS Hierarchy
          <span className="text-[10px] font-mono text-muted-foreground ml-2 bg-muted px-2 py-0.5 rounded">{p6Data.allActivities.length}</span>
        </h3>
        <div className="flex gap-1 bg-muted border border-border rounded-lg p-0.5">
          {statuses.map(s => (
            <button key={s} onClick={() => setFilter(s)}
              className={`px-3 py-1 text-[10px] font-bold uppercase tracking-wider rounded-md transition-all ${filter === s ? 'bg-primary text-primary-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'
                }`}>{s}</button>
          ))}
        </div>
      </div>
      
      <div className="rounded-xl border border-border bg-card p-4 overflow-hidden">
        {rootNodes.map((root: any) => (
          <WBSNode key={root.wbsObjectId} node={root} level={0} onUpdateActivity={onUpdateActivity} />
        ))}
        {rootNodes.length === 0 && (
          <div className="text-center py-8 text-sm text-muted-foreground">
            No activities match the current filter.
          </div>
        )}
      </div>
    </div>
  );
};
