import React, { useState, useEffect } from 'react';
import { 
  Network, Database, ArrowRightLeft, 
  Server, HardDrive, Share2, Search,
  RefreshCw, Edit3, X, Save, CheckCircle2,
  AlertTriangle
} from 'lucide-react';

export default function DataIntegrationHub() {
  const [data, setData] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  
  // Edit Modal State
  const [editingProject, setEditingProject] = useState<any | null>(null);
  const [editForm, setEditForm] = useState<any>({});
  const [isPushing, setIsPushing] = useState(false);
  const [pushSuccess, setPushSuccess] = useState(false);
  const [pushError, setPushError] = useState<string | null>(null);
  
  const [isEditingP6, setIsEditingP6] = useState(false);
  const [projectDetails, setProjectDetails] = useState<any | null>(null);
  const [loadingDetails, setLoadingDetails] = useState(false);

  const [syncError, setSyncError] = useState<string | null>(null);
  
  // P6 Password Expiry State
  const [p6ConfigStatus, setP6ConfigStatus] = useState<any>(null);
  const [showPasswordModal, setShowPasswordModal] = useState(false);
  const [newPassword, setNewPassword] = useState('');
  const [passwordUpdating, setPasswordUpdating] = useState(false);
  const [passwordUpdateResult, setPasswordUpdateResult] = useState<{success?: string, error?: string} | null>(null);

  const fetchIntegrations = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/dashboard/summary');
      const json = await res.json();
      setData(json.projects || []);
    } catch (err) {
      console.error("Failed to fetch integration data:", err);
    }
  };

  const handleSyncAll = async () => {
    setLoading(true);
    setSyncError(null);
    try {
      // Trigger all syncs concurrently
      const [p6Res, spRes, tcRes] = await Promise.all([
        fetch('http://localhost:8000/api/p6/sync', { method: 'POST' }),
        fetch('http://localhost:8000/api/sharepoint/sync', { method: 'POST' }),
        fetch('http://localhost:8000/api/tc/sync', { method: 'POST' })
      ]);

      const errors = [];
      if (!p6Res.ok) {
          const errData = await p6Res.json().catch(() => ({}));
          errors.push(errData.detail || "P6 Sync Failed");
      }
      if (!spRes.ok) {
          const errData = await spRes.json().catch(() => ({}));
          errors.push(errData.detail || "SharePoint Sync Failed");
      }
      if (!tcRes.ok) {
          const errData = await tcRes.json().catch(() => ({}));
          errors.push(errData.detail || "TC Sync Failed");
      }

      if (errors.length > 0) {
        setSyncError(errors.join(" | "));
      }
      
      // Fetch the updated dashboard summary
      await fetchIntegrations();
    } catch (err: any) {
      console.error("Failed to sync:", err);
      setSyncError(err.message || "Failed to connect to backend");
    } finally {
      setLoading(false);
    }
  };

  const fetchP6ConfigStatus = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/p6/config-status');
      if (res.ok) {
        const data = await res.json();
        setP6ConfigStatus(data);
      }
    } catch (err) {
      console.error("Failed to fetch P6 config status:", err);
    }
  };

  useEffect(() => {
    setLoading(true);
    fetchIntegrations().finally(() => setLoading(false));
    fetchP6ConfigStatus();
  }, []);

  const handleUpdatePassword = async () => {
    if (!newPassword.trim()) return;
    setPasswordUpdating(true);
    setPasswordUpdateResult(null);
    try {
      const res = await fetch('http://localhost:8000/api/p6/update-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ new_password: newPassword.trim() })
      });
      const data = await res.json();
      if (res.ok) {
        setPasswordUpdateResult({ success: "Password updated successfully!" });
        setNewPassword('');
        fetchP6ConfigStatus(); // refresh status
        setTimeout(() => setShowPasswordModal(false), 2000);
      } else {
        setPasswordUpdateResult({ error: data.detail || "Update failed" });
      }
    } catch (err: any) {
      setPasswordUpdateResult({ error: err.message || "Failed to connect" });
    } finally {
      setPasswordUpdating(false);
    }
  };

  const handleViewClick = async (project: any) => {
    setEditingProject(project);
    setIsEditingP6(false);
    setPushSuccess(false);
    setPushError(null);
    setProjectDetails(null);

    setEditForm({
      name: project.p6_project_name || project.project_name,
      status: project.p6?.health || 'On Track',
      start_date: project.p6?.start_date || '',
      finish_date: project.p6?.finish_date || '',
      planned_start_date: project.p6?.planned_start_date || '',
      scheduled_finish_date: project.p6?.scheduled_finish_date || '',
      data_date: project.p6?.data_date || '',
      must_finish_by_date: project.p6?.must_finish_by_date || '',
      baseline_start_date: project.p6?.baseline_start_date || '',
      baseline_finish_date: project.p6?.baseline_finish_date || '',
    });

    if (project.mapping_id) {
      setLoadingDetails(true);
      try {
        const res = await fetch(`http://localhost:8000/api/dashboard/projects/${project.mapping_id}`);
        if (res.ok) {
          const data = await res.json();
          setProjectDetails(data);
        }
      } catch (err) {
        console.error(err);
      } finally {
        setLoadingDetails(false);
      }
    }
  };

  const handlePushToP6 = async () => {
    if (!editingProject) return;
    setIsPushing(true);
    setPushSuccess(false);
    setPushError(null);

    try {
      const p6_id = editingProject.p6?.id;
      if (!p6_id) {
        throw new Error("No P6 ID found for this project.");
      }

      const payload = Object.fromEntries(
        Object.entries(editForm).map(([k, v]) => [k, v === '' ? null : v])
      );

      const response = await fetch(`http://localhost:8000/api/p6/projects/${p6_id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || "Failed to push to P6");
      }

      // Success pushed to P6! Now wait for P6 to sync and return the REAL data.
      await handleSyncAll(); // This will trigger a P6 sync and refresh the table

      // Also refresh the modal details if it's open
      if (editingProject?.mapping_id) {
        const res = await fetch(`http://localhost:8000/api/dashboard/projects/${editingProject.mapping_id}`);
        if (res.ok) {
          const freshData = await res.json();
          setProjectDetails(freshData);
          
          // Update the edit form with the fresh P6 data just to be safe
          if (freshData.p6) {
            setEditForm({
              name: freshData.p6.name || freshData.mapping?.p6ProjectName || freshData.mapping?.tcProjectName || '',
              status: freshData.p6.status || 'On Track',
              start_date: freshData.p6.start_date || '',
              finish_date: freshData.p6.finish_date || '',
              planned_start_date: freshData.p6.planned_start_date || '',
              scheduled_finish_date: freshData.p6.scheduled_finish_date || '',
              data_date: freshData.p6.data_date || '',
              must_finish_by_date: freshData.p6.must_finish_by_date || '',
              baseline_start_date: freshData.p6.baseline_start_date || '',
              baseline_finish_date: freshData.p6.baseline_finish_date || '',
            });
          }
        }
      }

      setPushSuccess(true);
      setIsEditingP6(false);

    } catch (error: any) {
      setPushError(error.message);
    } finally {
      setIsPushing(false);
    }
  };

  const filteredData = data.filter(p => 
    p.project_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    (p.p6?.id || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
    (p.spv_plant_code || '').toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="flex flex-col h-full w-full max-w-[1800px] mx-auto animate-in fade-in duration-500 pb-8">
      
      {/* ── Page Header ── */}
      <div className="flex items-end justify-between gap-4 mb-4">
        <div>
          <div className="section-label mb-1">DATA PIPELINE</div>
          <h2 className="text-3xl font-light text-foreground tracking-wide flex items-center gap-3">
            <Network className="w-8 h-8 text-primary" />
            Integration Hub
          </h2>
        </div>
        <button 
          onClick={handleSyncAll}
          disabled={loading}
          className="flex items-center gap-2 px-4 py-2 bg-card border border-border hover:border-primary/50 hover:bg-primary/10 transition-all rounded-xl text-sm disabled:opacity-50"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          {loading ? 'Syncing...' : 'Sync All'}
        </button>
      </div>

      {syncError && (
        <div className="mb-6 p-4 bg-red-500/10 border border-red-500/30 rounded-xl flex items-start gap-3 text-red-400">
          <AlertTriangle className="w-5 h-5 shrink-0 mt-0.5" />
          <div>
            <h4 className="text-sm font-bold uppercase tracking-wider mb-1">Live Sync Failed</h4>
            <p className="text-sm text-red-400/80">{syncError}</p>
          </div>
        </div>
      )}

      {/* P6 Password Expiry Warning Banner */}
      {p6ConfigStatus && p6ConfigStatus.is_expiring_soon && (
        <div className="mb-6 p-4 bg-amber-500/10 border border-amber-500/30 rounded-xl flex items-center justify-between text-amber-500 shadow-lg shadow-amber-500/5 backdrop-blur-sm animate-in fade-in slide-in-from-top-4">
          <div className="flex items-start gap-3">
            <AlertTriangle className="w-6 h-6 shrink-0 mt-0.5 animate-pulse text-amber-400" />
            <div>
              <h4 className="text-base font-bold tracking-wide mb-1 text-amber-400">Action Required: Oracle P6 Credential Expiry</h4>
              <p className="text-sm text-amber-500/90 leading-relaxed">
                Your Primavera P6 API password will expire in <span className="font-bold text-amber-300">{p6ConfigStatus.days_remaining} days</span>. 
                Please update it in Oracle P6, then update the integration credentials here to prevent sync failures.
              </p>
            </div>
          </div>
          <button 
            onClick={() => setShowPasswordModal(true)}
            className="ml-4 shrink-0 px-4 py-2 bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 border border-amber-500/30 font-semibold rounded-lg transition-colors shadow-sm text-sm"
          >
            Update Credentials
          </button>
        </div>
      )}

      {/* ── System Status Cards ── */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        <SystemCard 
          icon={Database} 
          name="Primavera P6" 
          status="Connected" 
          color="blue"
          metrics={[{label: "Projects", val: data.filter(d => d.p6?.id).length}]} 
        />
        <SystemCard 
          icon={Server} 
          name="SAP S/4HANA" 
          status="Connected" 
          color="emerald"
          metrics={[{label: "Mapped", val: data.filter(d => d.spv_plant_code && d.spv_plant_code.toLowerCase() !== 'nan').length}]} 
        />
        <SystemCard 
          icon={Share2} 
          name="Transmission Grid (TC)" 
          status="Active Sync" 
          color="purple"
          metrics={[{label: "Edges", val: data.filter(d => d.tc?.has_data).length}]} 
        />
      </div>

      {/* ── Master Projects Table ── */}
      <div className="glass-card rounded-2xl overflow-hidden shadow-lg border border-border/50 flex flex-col flex-1 min-h-[500px]">
        {/* Toolbar */}
        <div className="p-4 border-b border-border/50 flex justify-between items-center bg-card/30">
          <div className="relative w-72">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <input 
              type="text" 
              placeholder="Search mappings..." 
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full bg-background border border-border rounded-xl py-2 pl-10 pr-4 text-sm focus:outline-none focus:border-primary/50 transition-colors"
            />
          </div>
          <span className="text-xs text-muted-foreground font-mono bg-black/20 px-3 py-1 rounded-md border border-border">
            {filteredData.length} Mappings Active
          </span>
        </div>

        {/* Table Area */}
        <div className="overflow-x-auto flex-1 relative min-h-[400px]">
          {loading && (
            <div className="absolute inset-0 z-50 bg-background/80 backdrop-blur-md flex flex-col items-center justify-center">
              <div className="relative flex items-center justify-center">
                <div className="absolute w-24 h-24 bg-primary/20 rounded-full blur-xl animate-pulse"></div>
                <RefreshCw className="w-12 h-12 text-primary animate-spin relative z-10" />
              </div>
              <h3 className="mt-6 text-xl font-semibold text-foreground tracking-wide">Syncing Live Enterprise Data</h3>
              <p className="text-sm text-muted-foreground mt-3 max-w-md text-center leading-relaxed">
                Establishing secure connection to Oracle Primavera P6. Downloading full portfolio schedules and variances. <br/><span className="text-primary/80 font-medium">This may take 30-45 seconds.</span>
              </p>
            </div>
          )}
          <table className="w-full text-sm text-left whitespace-nowrap">
            <thead className="bg-muted/30 text-muted-foreground uppercase tracking-widest text-[10px] font-bold sticky top-0 z-10 backdrop-blur-md border-b border-border">
              <tr>
                <th className="px-6 py-4">Project Entity</th>
                <th className="px-6 py-4">Primavera P6</th>
                <th className="px-6 py-4">SAP Finance/Logistics</th>
                <th className="px-6 py-4">Transmission JSON</th>
                <th className="px-6 py-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/30">
              {!loading && filteredData.length === 0 ? (
                <tr>
                  <td colSpan={5} className="p-8 text-center text-muted-foreground">
                    No matching records found.
                  </td>
                </tr>
              ) : (
                filteredData.map((proj, idx) => (
                  <tr key={idx} className="hover:bg-muted/10 transition-colors group">
                    {/* Master Info */}
                    <td className="px-6 py-4">
                      <div className="font-semibold text-foreground">{proj.project_name}</div>
                      <div className="text-[10px] text-muted-foreground mt-0.5 max-w-[200px] truncate" title={proj.p6_project_name}>
                        P6 Name: <span className="font-medium text-foreground/80">{proj.p6_project_name}</span>
                      </div>
                      <div className="text-[10px] text-primary/70 mt-0.5">{proj.capacity_mwac || proj.capacity_mw || 0} MW</div>
                    </td>
                    
                    {/* P6 Data */}
                    <td className="px-6 py-4">
                      {proj.p6?.id ? (
                        <div className="flex flex-col gap-1">
                          <div className="flex items-center gap-2">
                            <span className={`w-1.5 h-1.5 rounded-full ${proj.p6.health === 'On Track' ? 'bg-emerald-500' : proj.p6.health === 'Delayed' ? 'bg-red-500' : 'bg-amber-500'}`}></span>
                            <span className="font-mono text-xs text-muted-foreground">{proj.p6.id}</span>
                          </div>
                          <div className="text-xs flex items-center gap-2">
                            Status: <span className="font-medium text-foreground">{proj.p6.health}</span>
                          </div>
                        </div>
                      ) : (
                        <span className="text-xs text-muted-foreground/50 italic">Unmapped</span>
                      )}
                    </td>

                    {/* SAP Data */}
                    <td className="px-6 py-4">
                      {proj.spv_plant_code ? (
                        <div className="flex flex-col gap-1">
                          <span className="font-mono text-xs text-muted-foreground bg-emerald-500/10 text-emerald-400 px-2 py-0.5 rounded border border-emerald-500/20 w-fit">
                            {proj.spv_plant_code}
                          </span>
                          <div className="text-xs">
                            Inv: <span className="font-medium">{proj.sap?.inventory_mw || 0} MW</span>
                          </div>
                        </div>
                      ) : (
                        <span className="text-xs text-muted-foreground/50 italic">Unmapped</span>
                      )}
                    </td>

                    {/* Transmission Data */}
                    <td className="px-6 py-4">
                      <div className="relative group/tc">
                        <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[10px] font-bold uppercase tracking-wider border cursor-help transition-all ${
                          proj.tc?.has_data ? 'border-purple-500/30 text-purple-400 bg-purple-500/10 hover:bg-purple-500/20' : 'border-border text-muted-foreground'
                        }`}>
                          {proj.tc?.status || 'No Link'}
                        </span>
                        {/* Hover JSON Tooltip */}
                        {proj.tc?.has_data && (
                          <div className="absolute left-full top-1/2 -translate-y-1/2 ml-2 hidden group-hover/tc:block z-50">
                            <div className="bg-[#0B1020]/95 backdrop-blur-xl border border-purple-500/30 p-3 rounded-xl shadow-2xl w-[250px]">
                              <div className="flex items-center gap-2 mb-2 pb-2 border-b border-white/10">
                                <Share2 className="w-3 h-3 text-purple-400" />
                                <h4 className="text-[9px] text-purple-400 font-bold uppercase tracking-wider">Payload Snippet</h4>
                              </div>
                              <pre className="text-[9px] text-green-400/90 font-mono whitespace-pre-wrap overflow-hidden max-h-[100px]">
                                {JSON.stringify(proj.tc.data, null, 2)}
                              </pre>
                            </div>
                          </div>
                        )}
                      </div>
                    </td>

                    {/* Actions */}
                    <td className="px-6 py-4 text-right">
                      <button 
                        onClick={() => handleViewClick(proj)}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all bg-primary/10 text-primary hover:bg-primary/20 border border-primary/20"
                      >
                        <Search className="w-3.5 h-3.5" /> View Details
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* ── Edit Modal ── */}
      {editingProject && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-background/80 backdrop-blur-sm p-4">
          <div className="w-full max-w-7xl bg-card border border-border shadow-2xl rounded-2xl overflow-hidden animate-in zoom-in-95 duration-200">
            
            {/* Header */}
            <div className="px-6 py-4 border-b border-border/50 flex justify-between items-center bg-muted/20">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-primary/20 flex items-center justify-center text-primary">
                  <Database className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="font-semibold text-foreground text-lg">{editingProject.p6_project_name || editingProject.project_name}</h3>
                  <p className="text-[10px] text-muted-foreground uppercase tracking-widest font-mono mt-0.5">
                    ID: {editingProject.p6?.id || 'UNMAPPED'} | System: {editingProject.project_name}
                  </p>
                </div>
              </div>
              <button 
                onClick={() => setEditingProject(null)}
                className="text-muted-foreground hover:text-foreground p-1 rounded-md hover:bg-muted transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Body */}
            <div className="p-6">
              {loadingDetails ? (
                <div className="flex flex-col items-center justify-center py-12">
                  <RefreshCw className="w-8 h-8 text-primary animate-spin mb-4" />
                  <p className="text-muted-foreground">Loading mapped integrations...</p>
                </div>
              ) : (
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                  
                  {/* Column 1: Primavera P6 */}
                  <div className="col-span-1 lg:col-span-1 border border-border/50 rounded-xl p-4 bg-muted/5 flex flex-col">
                    <div className="flex items-center justify-between mb-4 pb-2 border-b border-border/50">
                      <div className="flex items-center gap-2 text-blue-400">
                        <Database className="w-4 h-4" />
                        <h4 className="font-bold uppercase tracking-wider text-xs">Primavera P6</h4>
                      </div>
                      {editingProject.p6?.id && (
                        <button 
                          onClick={() => setIsEditingP6(!isEditingP6)}
                          className={`text-xs px-2 py-1 rounded border transition-colors ${isEditingP6 ? 'bg-red-500/10 text-red-500 border-red-500/20 hover:bg-red-500/20' : 'bg-primary/10 text-primary border-primary/20 hover:bg-primary/20'}`}
                        >
                          {isEditingP6 ? 'Cancel Edit' : 'Edit P6 Dates'}
                        </button>
                      )}
                    </div>

                    {!editingProject.p6?.id ? (
                      <div className="flex-1 flex items-center justify-center text-sm text-muted-foreground italic">
                        Not mapped to P6
                      </div>
                    ) : isEditingP6 ? (
                      <div className="space-y-4 animate-in fade-in duration-300">
                        <div className="space-y-1">
                          <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Status</label>
                          <select 
                            value={editForm.status}
                            onChange={(e) => setEditForm({...editForm, status: e.target.value})}
                            className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-primary/50 transition-colors appearance-none"
                          >
                            <option value="On Track">On Track</option>
                            <option value="Delayed">Delayed</option>
                            <option value="Critical">Critical</option>
                            <option value="Completed">Completed</option>
                          </select>
                        </div>
                        <div className="grid grid-cols-2 gap-3 mt-4">
                          <div className="space-y-1">
                            <label className="text-[10px] font-medium text-primary uppercase">Actual Start</label>
                            <input type="date" value={editForm.start_date ? editForm.start_date.substring(0, 10) : ''} onChange={(e) => setEditForm({...editForm, start_date: e.target.value})} className="w-full bg-background text-foreground [color-scheme:dark] border border-border rounded-md px-2 py-1.5 text-xs focus:border-primary/50" />
                          </div>
                          <div className="space-y-1">
                            <label className="text-[10px] font-medium text-primary uppercase">Actual Finish</label>
                            <input type="date" value={editForm.finish_date ? editForm.finish_date.substring(0, 10) : ''} onChange={(e) => setEditForm({...editForm, finish_date: e.target.value})} className="w-full bg-background text-foreground [color-scheme:dark] border border-border rounded-md px-2 py-1.5 text-xs focus:border-primary/50" />
                          </div>
                          <div className="space-y-1">
                            <label className="text-[10px] font-medium text-muted-foreground uppercase">Planned Start</label>
                            <input type="date" value={editForm.planned_start_date ? editForm.planned_start_date.substring(0, 10) : ''} onChange={(e) => setEditForm({...editForm, planned_start_date: e.target.value})} className="w-full bg-background text-foreground [color-scheme:dark] border border-border rounded-md px-2 py-1.5 text-xs focus:border-primary/50" />
                          </div>
                          <div className="space-y-1">
                            <label className="text-[10px] font-medium text-muted-foreground uppercase">Sched Finish</label>
                            <input type="date" value={editForm.scheduled_finish_date ? editForm.scheduled_finish_date.substring(0, 10) : ''} onChange={(e) => setEditForm({...editForm, scheduled_finish_date: e.target.value})} className="w-full bg-background text-foreground [color-scheme:dark] border border-border rounded-md px-2 py-1.5 text-xs focus:border-primary/50" />
                          </div>
                          <div className="space-y-1">
                            <label className="text-[10px] font-medium text-muted-foreground uppercase">Data Date</label>
                            <input type="date" value={editForm.data_date ? editForm.data_date.substring(0, 10) : ''} onChange={(e) => setEditForm({...editForm, data_date: e.target.value})} className="w-full bg-background text-foreground [color-scheme:dark] border border-border rounded-md px-2 py-1.5 text-xs focus:border-primary/50" />
                          </div>
                          <div className="space-y-1">
                            <label className="text-[10px] font-medium text-muted-foreground uppercase">Must Finish</label>
                            <input type="date" value={editForm.must_finish_by_date ? editForm.must_finish_by_date.substring(0, 10) : ''} onChange={(e) => setEditForm({...editForm, must_finish_by_date: e.target.value})} className="w-full bg-background text-foreground [color-scheme:dark] border border-border rounded-md px-2 py-1.5 text-xs focus:border-primary/50" />
                          </div>
                          <div className="space-y-1">
                            <label className="text-[10px] font-medium text-emerald-500 uppercase">Base Start</label>
                            <input type="date" value={editForm.baseline_start_date ? editForm.baseline_start_date.substring(0, 10) : ''} onChange={(e) => setEditForm({...editForm, baseline_start_date: e.target.value})} className="w-full bg-background text-foreground [color-scheme:dark] border border-border rounded-md px-2 py-1.5 text-xs focus:border-emerald-500/50" />
                          </div>
                          <div className="space-y-1">
                            <label className="text-[10px] font-medium text-emerald-500 uppercase">Base Finish</label>
                            <input type="date" value={editForm.baseline_finish_date ? editForm.baseline_finish_date.substring(0, 10) : ''} onChange={(e) => setEditForm({...editForm, baseline_finish_date: e.target.value})} className="w-full bg-background text-foreground [color-scheme:dark] border border-border rounded-md px-2 py-1.5 text-xs focus:border-emerald-500/50" />
                          </div>
                        </div>
                        <button 
                          onClick={handlePushToP6}
                          disabled={isPushing}
                          className="w-full mt-4 flex items-center justify-center gap-2 px-4 py-2 bg-primary text-primary-foreground font-semibold rounded-lg hover:bg-primary/90 transition-all disabled:opacity-50"
                        >
                          {isPushing ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                          {isPushing ? 'Pushing...' : 'Save & Push to P6'}
                        </button>
                        {pushError && <p className="text-red-500 text-xs mt-2">{pushError}</p>}
                        {pushSuccess && <p className="text-emerald-500 text-xs mt-2">Success!</p>}
                      </div>
                    ) : (
                      <div className="space-y-3 text-sm">
                        <div className="flex justify-between items-center py-1 border-b border-border/30">
                          <span className="text-muted-foreground">ID</span>
                          <span className="font-mono">{editingProject.p6.id}</span>
                        </div>
                        <div className="flex justify-between items-center py-1 border-b border-border/30">
                          <span className="text-muted-foreground">Status</span>
                          <span className="font-medium text-primary">{editingProject.p6.health}</span>
                        </div>
                        <div className="flex justify-between items-center py-1 border-b border-border/30">
                          <span className="text-muted-foreground">Start Date</span>
                          <span>{editingProject.p6.start_date ? new Date(editingProject.p6.start_date).toLocaleDateString() : 'N/A'}</span>
                        </div>
                        <div className="flex justify-between items-center py-1 border-b border-border/30">
                          <span className="text-muted-foreground">Finish Date</span>
                          <span>{editingProject.p6.finish_date ? new Date(editingProject.p6.finish_date).toLocaleDateString() : 'N/A'}</span>
                        </div>
                        <div className="flex justify-between items-center py-1 border-b border-border/30">
                          <span className="text-muted-foreground">Planned Start</span>
                          <span>{editingProject.p6.planned_start_date ? new Date(editingProject.p6.planned_start_date).toLocaleDateString() : 'N/A'}</span>
                        </div>
                        <div className="flex justify-between items-center py-1 border-b border-border/30">
                          <span className="text-muted-foreground">Scheduled Finish</span>
                          <span>{editingProject.p6.scheduled_finish_date ? new Date(editingProject.p6.scheduled_finish_date).toLocaleDateString() : 'N/A'}</span>
                        </div>
                        <div className="flex justify-between items-center py-1 border-b border-border/30">
                          <span className="text-muted-foreground text-emerald-500">Baseline Start</span>
                          <span className="text-emerald-400">{editingProject.p6.baseline_start_date ? new Date(editingProject.p6.baseline_start_date).toLocaleDateString() : 'N/A'}</span>
                        </div>
                        <div className="flex justify-between items-center py-1 border-b border-border/30">
                          <span className="text-muted-foreground text-emerald-500">Baseline Finish</span>
                          <span className="text-emerald-400">{editingProject.p6.baseline_finish_date ? new Date(editingProject.p6.baseline_finish_date).toLocaleDateString() : 'N/A'}</span>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Column 2: SAP */}
                  <div className="col-span-1 lg:col-span-1 border border-border/50 rounded-xl p-4 bg-muted/5 flex flex-col">
                    <div className="flex items-center gap-2 text-emerald-400 mb-4 pb-2 border-b border-border/50">
                      <Server className="w-4 h-4" />
                      <h4 className="font-bold uppercase tracking-wider text-xs">SAP Logistics & Finance</h4>
                    </div>
                    {projectDetails?.sap && (projectDetails.sap.inventory?.length > 0 || projectDetails.sap.po?.length > 0 || projectDetails.sap.inventory_summary > 0) ? (
                      <div className="space-y-4">
                        <div className="grid grid-cols-2 gap-4">
                          <div className="p-3 bg-card border border-border/50 rounded-lg">
                            <div className="text-[10px] text-muted-foreground uppercase tracking-widest mb-1">Inventory (MW)</div>
                            <div className="text-lg font-light text-foreground">{projectDetails.sap.inventory_summary?.toFixed(1) || 0}</div>
                          </div>
                          <div className="p-3 bg-card border border-border/50 rounded-lg">
                            <div className="text-[10px] text-muted-foreground uppercase tracking-widest mb-1">PO Quantity (MW)</div>
                            <div className="text-lg font-light text-foreground">{projectDetails.sap.po_summary?.toFixed(1) || 0}</div>
                          </div>
                        </div>
                        
                        {projectDetails.sap.po && projectDetails.sap.po.length > 0 && (
                          <div className="mt-4">
                            <h5 className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest mb-2">Recent POs</h5>
                            <div className="space-y-2 max-h-[200px] overflow-y-auto pr-2">
                              {projectDetails.sap.po.map((po: any, i: number) => (
                                <div key={i} className="flex justify-between items-center p-2 rounded bg-background border border-border/50 text-xs">
                                  <span className="font-mono text-emerald-400">{po.purchasing_document}</span>
                                  <span className="text-muted-foreground truncate max-w-[100px] text-right" title={po.vendor_name}>{po.vendor_name}</span>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    ) : (
                      <div className="flex-1 flex flex-col items-center justify-center text-sm text-muted-foreground italic gap-2 text-center px-4">
                        <Server className="w-8 h-8 opacity-20" />
                        <p>No active SAP inventory or PO records found for this plant code.</p>
                      </div>
                    )}
                  </div>

                  {/* Column 3: Transmission */}
                  <div className="col-span-1 lg:col-span-1 border border-border/50 rounded-xl p-4 bg-muted/5 flex flex-col">
                    <div className="flex items-center gap-2 text-purple-400 mb-4 pb-2 border-b border-border/50">
                      <Share2 className="w-4 h-4" />
                      <h4 className="font-bold uppercase tracking-wider text-xs">Transmission Network</h4>
                    </div>
                    {projectDetails?.tc && (projectDetails.tc.khavda_edges?.length > 0 || projectDetails.tc.rajasthan_edges?.length > 0) ? (
                      <div className="space-y-4">
                        <div className="grid grid-cols-2 gap-4">
                          <div className="p-3 bg-card border border-border/50 rounded-lg">
                            <div className="text-[10px] text-muted-foreground uppercase tracking-widest mb-1">Khavda Edges</div>
                            <div className="text-lg font-light text-foreground">{projectDetails.tc.khavda_edges?.length || 0}</div>
                          </div>
                          <div className="p-3 bg-card border border-border/50 rounded-lg">
                            <div className="text-[10px] text-muted-foreground uppercase tracking-widest mb-1">Rajasthan Edges</div>
                            <div className="text-lg font-light text-foreground">{projectDetails.tc.rajasthan_edges?.length || 0}</div>
                          </div>
                        </div>
                        
                        {/* Edge List Sample */}
                        <div className="mt-4">
                           <h5 className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest mb-2">Network Paths</h5>
                           <div className="space-y-2 max-h-[200px] overflow-y-auto pr-2">
                             {[...(projectDetails.tc.khavda_edges || []), ...(projectDetails.tc.rajasthan_edges || [])].map((edge: any, i: number) => (
                               <div key={i} className="flex flex-col p-2.5 rounded bg-background border border-border/50 text-xs gap-1.5 hover:bg-muted/30 transition-colors">
                                 <div className="flex justify-between items-center text-purple-400 font-mono text-[10px] font-bold">
                                   <span className="truncate max-w-[200px]" title={edge.project}>{edge.project}</span>
                                   <div className="flex gap-1.5 shrink-0">
                                     <span className="px-1.5 py-0.5 rounded bg-purple-500/10 text-purple-400 border border-purple-500/20">{edge.phase}</span>
                                     <span className="px-1.5 py-0.5 rounded bg-purple-500/10 text-purple-400 border border-purple-500/20">{edge.voltage}</span>
                                   </div>
                                 </div>
                                 <div className="flex justify-between items-center text-muted-foreground text-[10px]">
                                   <div className="flex items-center gap-1.5 truncate max-w-[150px]">
                                     <span className="truncate" title={edge.from_label || edge.from_node}>{edge.from_label || edge.from_node}</span>
                                     <ArrowRightLeft className="w-2.5 h-2.5 shrink-0" />
                                     <span className="truncate" title={edge.to_label || edge.to_node}>{edge.to_label || edge.to_node}</span>
                                   </div>
                                   <span className={`shrink-0 ml-2 px-1.5 py-0.5 rounded text-[10px] font-bold tracking-widest uppercase ${
                                     edge.normalizedStatus === 'completed' 
                                       ? 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/20' 
                                       : 'bg-amber-500/10 text-amber-500 border border-amber-500/20'
                                   }`}>
                                     {edge.normalizedStatus === 'completed' 
                                       ? 'CHARGED' 
                                       : (String(edge.status).match(/^\d+$/) ? `WIP - ${edge.status}%` : edge.status || 'WIP')}
                                   </span>
                                 </div>
                               </div>
                             ))}
                           </div>
                        </div>
                      </div>
                    ) : (
                      <div className="flex-1 flex flex-col items-center justify-center text-sm text-muted-foreground italic gap-2 text-center px-4">
                        <Share2 className="w-8 h-8 opacity-20" />
                        <p>No transmission network edges found mapping to this project.</p>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── Password Update Modal ── */}
      {showPasswordModal && (
        <div className="fixed inset-0 z-[200] flex items-center justify-center bg-background/80 backdrop-blur-md p-4 animate-in fade-in">
          <div className="w-full max-w-md bg-card border border-border shadow-2xl rounded-2xl overflow-hidden animate-in zoom-in-95 duration-200">
            <div className="px-6 py-4 border-b border-border/50 flex justify-between items-center bg-muted/20">
              <div className="flex items-center gap-2 text-amber-400">
                <Database className="w-5 h-5" />
                <h3 className="font-semibold text-lg">Update P6 Credentials</h3>
              </div>
              <button 
                onClick={() => setShowPasswordModal(false)}
                className="text-muted-foreground hover:text-foreground p-1 rounded-md hover:bg-muted transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            
            <div className="p-6 space-y-4">
              <p className="text-sm text-muted-foreground mb-4">
                Enter your new Oracle Primavera P6 password. We will securely encode it and update the system configuration automatically.
              </p>
              
              <div className="space-y-1.5">
                <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">New Password</label>
                <input 
                  type="password" 
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder="Enter new password" 
                  className="w-full bg-background border border-border rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:border-amber-500/50 transition-colors"
                />
              </div>

              {passwordUpdateResult?.error && (
                <div className="p-3 bg-red-500/10 border border-red-500/20 text-red-400 rounded-lg text-xs">
                  {passwordUpdateResult.error}
                </div>
              )}
              {passwordUpdateResult?.success && (
                <div className="p-3 bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 rounded-lg text-xs flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4" /> {passwordUpdateResult.success}
                </div>
              )}

              <div className="pt-4 flex justify-end gap-3 border-t border-border/50">
                <button 
                  onClick={() => setShowPasswordModal(false)}
                  className="px-4 py-2 rounded-lg text-sm font-medium hover:bg-muted transition-colors text-muted-foreground"
                >
                  Cancel
                </button>
                <button 
                  onClick={handleUpdatePassword}
                  disabled={passwordUpdating || !newPassword}
                  className="px-4 py-2 rounded-lg text-sm font-semibold bg-amber-500 text-amber-950 hover:bg-amber-400 transition-colors disabled:opacity-50 flex items-center gap-2 shadow-lg shadow-amber-500/20"
                >
                  {passwordUpdating && <RefreshCw className="w-4 h-4 animate-spin" />}
                  {passwordUpdating ? 'Updating...' : 'Save & Update'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}

function SystemCard({ icon: Icon, name, status, color, metrics }: any) {
  const colorMap: any = {
    blue: "bg-blue-500/10 text-blue-400 border-blue-500/20 shadow-[0_0_15px_rgba(59,130,246,0.1)]",
    emerald: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20 shadow-[0_0_15px_rgba(16,185,129,0.1)]",
    purple: "bg-purple-500/10 text-purple-400 border-purple-500/20 shadow-[0_0_15px_rgba(168,85,247,0.1)]"
  };

  const dotMap: any = {
    blue: "bg-blue-500 shadow-[0_0_5px_theme(colors.blue.500)]",
    emerald: "bg-emerald-500 shadow-[0_0_5px_theme(colors.emerald.500)]",
    purple: "bg-purple-500 shadow-[0_0_5px_theme(colors.purple.500)]"
  };

  return (
    <div className={`p-5 rounded-2xl border backdrop-blur-sm ${colorMap[color]} flex flex-col justify-between`}>
      <div className="flex justify-between items-start mb-4">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-background/50 border border-current/20">
            <Icon className="w-5 h-5" />
          </div>
          <div>
            <h3 className="font-semibold text-sm text-foreground">{name}</h3>
            <div className="flex items-center gap-1.5 mt-1 text-xs opacity-80">
              <div className={`w-1.5 h-1.5 rounded-full animate-pulse ${dotMap[color]}`}></div>
              {status}
            </div>
          </div>
        </div>
      </div>
      <div className="flex gap-4 border-t border-current/10 pt-4 mt-auto">
        {metrics.map((m: any, i: number) => (
          <div key={i}>
            <div className="text-[10px] uppercase tracking-widest font-bold opacity-60 mb-0.5">{m.label}</div>
            <div className="text-xl font-light">{m.val}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
