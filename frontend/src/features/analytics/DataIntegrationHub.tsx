import React, { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { 
  Network, Database, ArrowRightLeft, 
  Server, Share2, Search,
  RefreshCw, X, Save,
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

  const fetchIntegrations = async (nocache = false) => {
    try {
      const url = nocache ? '/akasha/api/dashboard/summary?nocache=true' : '/akasha/api/dashboard/summary';
      const res = await fetch(url);
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
      const mapRes = await fetch('/akasha/api/mapping/sync', { method: 'POST' });
      const [p6Res, spRes, tcRes] = await Promise.all([
        fetch('/akasha/api/p6/sync', { method: 'POST' }),
        fetch('/akasha/api/sharepoint/sync', { method: 'POST' }),
        fetch('/akasha/api/tc/sync', { method: 'POST' })
      ]);

      const errors = [];
      if (!mapRes.ok) {
          const errData = await mapRes.json().catch(() => ({}));
          errors.push(errData.detail || "Mapping Sync Failed");
      }
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
      
      await fetchIntegrations(true);
    } catch (err: any) {
      console.error("Failed to sync:", err);
      setSyncError(err.message || "Failed to connect to backend");
    } finally {
      setLoading(false);
    }
  };

  const fetchP6ConfigStatus = async () => {
    try {
      const res = await fetch('/akasha/api/p6/config-status');
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
      const res = await fetch('/akasha/api/p6/update-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ new_password: newPassword.trim() })
      });
      const data = await res.json();
      if (res.ok) {
        setPasswordUpdateResult({ success: "Password updated successfully!" });
        setNewPassword('');
        fetchP6ConfigStatus();
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
        const res = await fetch(`/akasha/api/dashboard/projects/${project.mapping_id}`);
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

      const response = await fetch(`/akasha/api/p6/projects/${p6_id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || "Failed to push to P6");
      }

      await handleSyncAll();

      if (editingProject?.mapping_id) {
        const res = await fetch(`/akasha/api/dashboard/projects/${editingProject.mapping_id}`);
        if (res.ok) {
          const freshData = await res.json();
          setProjectDetails(freshData);
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

  const filteredData = data
    .filter(p => 
      p.project_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (p.p6?.id || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
      (p.spv_plant_code || '').toLowerCase().includes(searchTerm.toLowerCase())
    )
    .sort((a, b) => {
      let scoreA = 0;
      if (a.p6?.id) scoreA++;
      if (a.sap?.po_value > 0 || a.sap?.inventory_items > 0) scoreA++;
      if (a.tc?.has_data) scoreA++;

      let scoreB = 0;
      if (b.p6?.id) scoreB++;
      if (b.sap?.po_value > 0 || b.sap?.inventory_items > 0) scoreB++;
      if (b.tc?.has_data) scoreB++;

      return scoreB - scoreA;
    });

  return (
    <div className="flex flex-col h-full w-full max-w-[1600px] mx-auto transition-opacity duration-300 pb-8 px-4">
      
      {/* ── Page Header ── */}
      <div className="flex items-end justify-between gap-4 mb-6 pt-4">
        <div>
          <div className="text-[11px] font-semibold text-muted-foreground tracking-widest uppercase mb-1">Data Pipeline</div>
          <h2 className="text-2xl font-semibold text-foreground tracking-tight flex items-center gap-2">
            Integration Hub
          </h2>
        </div>
        <button 
          onClick={handleSyncAll}
          disabled={loading}
          className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground hover:bg-primary/90 transition-colors rounded-md text-sm font-medium disabled:opacity-50 shadow-sm"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          {loading ? 'Syncing...' : 'Sync Data'}
        </button>
      </div>

      {syncError && (
        <div className="mb-6 p-4 bg-destructive/100/10 border border-destructive/20 rounded-md flex items-start gap-3 text-destructive text-sm">
          <AlertTriangle className="w-5 h-5 shrink-0 mt-0.5" />
          <div>
            <h4 className="font-semibold mb-1">Live Sync Failed</h4>
            <p className="text-destructive/80">{syncError}</p>
          </div>
        </div>
      )}

      {/* P6 Password Expiry Warning Banner */}
      {p6ConfigStatus && p6ConfigStatus.is_expiring_soon && (
        <div className="mb-6 p-4 bg-warning/100/10 border border-warning/20 rounded-md flex items-center justify-between text-warning dark:text-warning">
          <div className="flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 shrink-0 mt-0.5" />
            <div>
              <h4 className="font-semibold mb-1">Oracle P6 Credential Expiry</h4>
              <p className="text-sm opacity-90">
                Your API password expires in <span className="font-bold">{p6ConfigStatus.days_remaining} days</span>. 
                Please update it in Oracle P6, then update here.
              </p>
            </div>
          </div>
          <button 
            onClick={() => setShowPasswordModal(true)}
            className="ml-4 px-4 py-2 bg-warning/100 text-white hover:bg-amber-600 text-sm font-medium rounded-md transition-colors shadow-sm"
          >
            Update
          </button>
        </div>
      )}

      {/* ── System Status Cards ── */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <SystemCard 
          icon={Database} 
          name="Primavera P6" 
          status="Connected" 
          color="blue"
          metrics={[{label: "Projects Mapped", val: data.filter(d => d.p6?.id).length}]} 
        />
        <SystemCard 
          icon={Server} 
          name="SAP S/4HANA" 
          status="Connected" 
          color="emerald"
          metrics={[{label: "Finance Records", val: data.filter(d => d.spv_plant_code && d.spv_plant_code.toLowerCase() !== 'nan').length}]} 
        />
        <SystemCard 
          icon={Share2} 
          name="Transmission Grid (TC)" 
          status="Active Sync" 
          color="purple"
          metrics={[{label: "Network Edges", val: data.reduce((sum, d) => sum + (d.tc?.data?.khavda?.length || 0) + (d.tc?.data?.rajasthan?.length || 0), 0)}]} 
        />
      </div>

      {/* ── Master Projects Table ── */}
      <div className="bg-card rounded-xl border border-border shadow-sm flex flex-col flex-1 min-h-[500px] overflow-hidden">
        {/* Toolbar */}
        <div className="px-4 py-3 border-b border-border flex justify-between items-center bg-muted">
          <div className="relative w-72">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <input 
              type="text" 
              placeholder="Search mappings..." 
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full bg-background border border-border rounded-md py-1.5 pl-9 pr-3 text-sm focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary transition-shadow"
            />
          </div>
          <span className="text-xs text-muted-foreground font-medium">
            {filteredData.length} Mappings Active
          </span>
        </div>

        {/* Table Area */}
        <div className="overflow-x-auto flex-1 relative min-h-[400px]">
          {loading && (
            <div className="absolute inset-0 z-50 bg-background/50 backdrop-blur-[2px] flex flex-col items-center justify-center">
              <RefreshCw className="w-8 h-8 text-primary animate-spin mb-4" />
              <h3 className="text-sm font-medium text-foreground">Syncing Enterprise Data</h3>
            </div>
          )}
          <table className="w-full text-sm text-left">
            <thead className="bg-muted text-muted-foreground text-[11px] font-semibold uppercase tracking-wider sticky top-0 z-10 border-b border-border">
              <tr>
                <th className="px-5 py-3 font-medium">Project Entity</th>
                <th className="px-5 py-3 font-medium">Primavera P6</th>
                <th className="px-5 py-3 font-medium">SAP Logistics</th>
                <th className="px-5 py-3 font-medium">Transmission JSON</th>
                <th className="px-5 py-3 font-medium text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/50 text-foreground">
              {!loading && filteredData.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-5 py-8 text-center text-muted-foreground">
                    No matching records found.
                  </td>
                </tr>
              ) : (
                filteredData.map((proj, idx) => (
                  <tr key={idx} className="hover:bg-muted transition-colors">
                    {/* Master Info */}
                    <td className="px-5 py-3">
                      <div className="font-medium">{proj.project_name}</div>
                      <div className="text-[11px] text-muted-foreground mt-1 line-clamp-1" title={proj.p6_project_name}>
                        {proj.p6_project_name}
                      </div>
                      <div className="text-[11px] font-medium text-muted-foreground mt-0.5">{proj.capacity_mwac || proj.capacity_mw || 0} MW</div>
                    </td>
                    
                    {/* P6 Data */}
                    <td className="px-5 py-3">
                      {proj.p6?.id ? (
                        <div className="flex flex-col gap-1.5">
                          <div className="text-xs font-medium">{proj.p6.id}</div>
                          <div className="flex items-center gap-1.5 text-[11px]">
                            <span className={`w-2 h-2 rounded-full ${proj.p6.health === 'On Track' ? 'bg-success/100' : proj.p6.health === 'Delayed' ? 'bg-destructive/100' : 'bg-warning/100'}`}></span>
                            <span className="text-muted-foreground">{proj.p6.health}</span>
                          </div>
                        </div>
                      ) : (
                        <span className="text-xs text-muted-foreground italic">Unmapped</span>
                      )}
                    </td>

                    {/* SAP Data */}
                    <td className="px-5 py-3">
                      {proj.spv_plant_code ? (
                        <div className="flex flex-col gap-1.5">
                          <div className="text-xs font-medium">{proj.spv_plant_code}</div>
                          <div className="text-[11px] text-muted-foreground font-mono tabular-nums">
                            PO: ₹{proj.sap?.po_value ? (proj.sap.po_value / 10000000).toFixed(2) : '0.00'} Cr
                          </div>
                        </div>
                      ) : (
                        <span className="text-xs text-muted-foreground italic">Unmapped</span>
                      )}
                    </td>

                    {/* Transmission Data */}
                    <td className="px-5 py-3">
                      {proj.tc?.has_data ? (
                        <div className="flex items-center gap-1.5">
                          <span className="w-2 h-2 rounded-full bg-purple-500"></span>
                          <span className="text-[11px] font-medium text-muted-foreground">{proj.tc.status}</span>
                        </div>
                      ) : (
                        <span className="text-xs text-muted-foreground italic">No Link</span>
                      )}
                    </td>

                    {/* Actions */}
                    <td className="px-5 py-3 text-right">
                      <button 
                        onClick={() => handleViewClick(proj)}
                        className="text-xs font-medium text-primary hover:text-primary/80 transition-colors inline-flex items-center gap-1"
                      >
                        Details &rarr;
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
      {editingProject && createPortal(
        <div className="fixed inset-0 flex items-center justify-center bg-black/40 p-4" style={{ zIndex: 9999 }}>
          <div className="w-full max-w-5xl bg-card border border-border shadow-xl rounded-xl overflow-hidden animate-in fade-in zoom-in-95 duration-200">
            
            {/* Header */}
            <div className="px-5 py-4 border-b border-border flex justify-between items-center bg-muted">
              <div>
                <h3 className="font-semibold text-foreground text-lg" style={{ textWrap: 'balance' }}>
                  {editingProject.p6_project_name || editingProject.project_name}
                </h3>
                <p className="text-[11px] text-muted-foreground mt-1">
                  ID: {editingProject.p6?.id || 'UNMAPPED'} • {editingProject.capacity_mwac || editingProject.capacity_mw || 0} MW
                </p>
              </div>
              <button 
                onClick={() => setEditingProject(null)}
                className="text-muted-foreground hover:text-foreground p-1.5 rounded-md hover:bg-muted transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Body */}
            <div className="p-5">
              {loadingDetails ? (
                <div className="flex flex-col items-center justify-center py-12">
                  <RefreshCw className="w-6 h-6 text-muted-foreground animate-spin mb-3" />
                  <p className="text-sm text-muted-foreground">Loading details...</p>
                </div>
              ) : (
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
                  
                  {/* Column 1: Primavera P6 */}
                  <div className="col-span-1 border border-border rounded-lg p-4 bg-background">
                    <div className="flex items-center justify-between mb-4 pb-3 border-b border-border/50">
                      <h4 className="font-semibold text-sm flex items-center gap-2 text-foreground">
                        <Database className="w-4 h-4 text-muted-foreground" /> P6 Schedule
                      </h4>
                      {editingProject.p6?.id && (
                        <button 
                          onClick={() => setIsEditingP6(!isEditingP6)}
                          className="text-[11px] font-medium text-primary hover:underline"
                        >
                          {isEditingP6 ? 'Cancel' : 'Edit'}
                        </button>
                      )}
                    </div>

                    {!editingProject.p6?.id ? (
                      <div className="text-sm text-muted-foreground italic text-center py-4">Not mapped to P6</div>
                    ) : isEditingP6 ? (
                      <div className="space-y-3">
                        <div className="space-y-1">
                          <label className="text-[10px] font-medium text-muted-foreground uppercase">Status</label>
                          <select 
                            value={editForm.status}
                            onChange={(e) => setEditForm({...editForm, status: e.target.value})}
                            className="w-full bg-background border border-border rounded-md px-2 py-1.5 text-sm focus:outline-none focus:border-primary transition-colors"
                          >
                            <option value="On Track">On Track</option>
                            <option value="Delayed">Delayed</option>
                            <option value="Critical">Critical</option>
                            <option value="Completed">Completed</option>
                          </select>
                        </div>
                        <div className="grid grid-cols-2 gap-3 mt-3">
                          <div className="space-y-1">
                            <label className="text-[10px] font-medium text-muted-foreground uppercase">Actual Start</label>
                            <input type="date" value={editForm.start_date ? editForm.start_date.substring(0, 10) : ''} onChange={(e) => setEditForm({...editForm, start_date: e.target.value})} className="w-full border border-border rounded-md px-2 py-1 text-xs" />
                          </div>
                          <div className="space-y-1">
                            <label className="text-[10px] font-medium text-muted-foreground uppercase">Actual Finish</label>
                            <input type="date" value={editForm.finish_date ? editForm.finish_date.substring(0, 10) : ''} onChange={(e) => setEditForm({...editForm, finish_date: e.target.value})} className="w-full border border-border rounded-md px-2 py-1 text-xs" />
                          </div>
                          <div className="space-y-1">
                            <label className="text-[10px] font-medium text-muted-foreground uppercase">Planned Start</label>
                            <input type="date" value={editForm.planned_start_date ? editForm.planned_start_date.substring(0, 10) : ''} onChange={(e) => setEditForm({...editForm, planned_start_date: e.target.value})} className="w-full border border-border rounded-md px-2 py-1 text-xs" />
                          </div>
                          <div className="space-y-1">
                            <label className="text-[10px] font-medium text-muted-foreground uppercase">Sched Finish</label>
                            <input type="date" value={editForm.scheduled_finish_date ? editForm.scheduled_finish_date.substring(0, 10) : ''} onChange={(e) => setEditForm({...editForm, scheduled_finish_date: e.target.value})} className="w-full border border-border rounded-md px-2 py-1 text-xs" />
                          </div>
                          <div className="space-y-1">
                            <label className="text-[10px] font-medium text-muted-foreground uppercase">Base Start</label>
                            <input type="date" value={editForm.baseline_start_date ? editForm.baseline_start_date.substring(0, 10) : ''} onChange={(e) => setEditForm({...editForm, baseline_start_date: e.target.value})} className="w-full border border-border rounded-md px-2 py-1 text-xs" />
                          </div>
                          <div className="space-y-1">
                            <label className="text-[10px] font-medium text-muted-foreground uppercase">Base Finish</label>
                            <input type="date" value={editForm.baseline_finish_date ? editForm.baseline_finish_date.substring(0, 10) : ''} onChange={(e) => setEditForm({...editForm, baseline_finish_date: e.target.value})} className="w-full border border-border rounded-md px-2 py-1 text-xs" />
                          </div>
                        </div>
                        <button 
                          onClick={handlePushToP6}
                          disabled={isPushing}
                          className="w-full mt-3 flex items-center justify-center gap-2 px-3 py-1.5 bg-primary text-primary-foreground font-medium rounded-md hover:bg-primary/90 transition-colors text-sm disabled:opacity-50"
                        >
                          {isPushing ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                          {isPushing ? 'Saving...' : 'Save Updates'}
                        </button>
                        {pushError && <p className="text-destructive text-[11px] mt-1">{pushError}</p>}
                        {pushSuccess && <p className="text-success text-[11px] mt-1">Saved successfully</p>}
                      </div>
                    ) : (
                      <div className="space-y-2 text-[13px]">
                        <div className="flex justify-between py-1 border-b border-border/40">
                          <span className="text-muted-foreground">Status</span>
                          <span className="font-medium text-foreground">{editingProject.p6.health}</span>
                        </div>
                        <div className="flex justify-between py-1 border-b border-border/40">
                          <span className="text-muted-foreground">Start Date</span>
                          <span>{editingProject.p6.start_date ? new Date(editingProject.p6.start_date).toLocaleDateString() : 'N/A'}</span>
                        </div>
                        <div className="flex justify-between py-1 border-b border-border/40">
                          <span className="text-muted-foreground">Finish Date</span>
                          <span>{editingProject.p6.finish_date ? new Date(editingProject.p6.finish_date).toLocaleDateString() : 'N/A'}</span>
                        </div>
                        <div className="flex justify-between py-1 border-b border-border/40">
                          <span className="text-muted-foreground">Planned Start</span>
                          <span>{editingProject.p6.planned_start_date ? new Date(editingProject.p6.planned_start_date).toLocaleDateString() : 'N/A'}</span>
                        </div>
                        <div className="flex justify-between py-1 border-b border-border/40">
                          <span className="text-muted-foreground">Scheduled Finish</span>
                          <span>{editingProject.p6.scheduled_finish_date ? new Date(editingProject.p6.scheduled_finish_date).toLocaleDateString() : 'N/A'}</span>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Column 2: SAP */}
                  <div className="col-span-1 border border-border rounded-lg p-4 bg-background">
                    <h4 className="font-semibold text-sm flex items-center gap-2 text-foreground mb-4 pb-3 border-b border-border/50">
                      <Server className="w-4 h-4 text-muted-foreground" /> SAP Financials
                    </h4>
                    {projectDetails?.sap && (projectDetails.sap.inventory?.length > 0 || projectDetails.sap.po?.length > 0 || projectDetails.sap.inventory_summary > 0) ? (
                      <div className="space-y-4">
                        <div className="grid grid-cols-2 gap-3">
                          <div className="p-3 border border-border rounded-md bg-muted">
                            <div className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">Inventory Val</div>
                            <div className="text-base font-mono tabular-nums text-foreground">₹{projectDetails.sap.inventory?.reduce((sum: number, i: any) => sum + (i.value_unrestricted || 0), 0) / 10000000 > 0 ? (projectDetails.sap.inventory?.reduce((sum: number, i: any) => sum + (i.value_unrestricted || 0), 0) / 10000000).toFixed(2) : '0.00'} Cr</div>
                          </div>
                          <div className="p-3 border border-border rounded-md bg-muted">
                            <div className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">PO Value</div>
                            <div className="text-base font-mono tabular-nums text-foreground">₹{projectDetails.sap.po?.reduce((sum: number, po: any) => sum + (po.net_order_value_inr || 0), 0) / 10000000 > 0 ? (projectDetails.sap.po?.reduce((sum: number, po: any) => sum + (po.net_order_value_inr || 0), 0) / 10000000).toFixed(2) : '0.00'} Cr</div>
                          </div>
                        </div>
                        
                        {projectDetails.sap.po && projectDetails.sap.po.length > 0 && (
                          <div className="mt-4">
                            <h5 className="text-[11px] font-medium text-muted-foreground mb-2">Recent Purchase Orders</h5>
                            <div className="space-y-1.5 max-h-[180px] overflow-y-auto pr-1">
                              {projectDetails.sap.po.map((po: any, i: number) => (
                                <div key={i} className="flex justify-between items-center py-1.5 px-2 rounded-md hover:bg-muted transition-colors text-xs gap-2">
                                  <span className="font-mono text-muted-foreground">{po.purchasing_document}</span>
                                  <span className="truncate flex-1 text-foreground" title={po.vendor_name}>{po.vendor_name}</span>
                                  <span className="font-mono tabular-nums text-foreground whitespace-nowrap">₹{((po.net_order_value_inr || 0) / 10000000).toFixed(2)}</span>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    ) : (
                      <div className="text-sm text-muted-foreground italic text-center py-4">No SAP financial records</div>
                    )}
                  </div>

                  {/* Column 3: Transmission */}
                  <div className="col-span-1 border border-border rounded-lg p-4 bg-background">
                    <h4 className="font-semibold text-sm flex items-center gap-2 text-foreground mb-4 pb-3 border-b border-border/50">
                      <Share2 className="w-4 h-4 text-muted-foreground" /> Transmission Grid
                    </h4>
                    {projectDetails?.tc && (projectDetails.tc.khavda_edges?.length > 0 || projectDetails.tc.rajasthan_edges?.length > 0) ? (
                      <div className="space-y-4">
                        <div className="grid grid-cols-2 gap-3">
                          <div className="p-3 border border-border rounded-md bg-muted">
                            <div className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">Khavda Nodes</div>
                            <div className="text-base font-semibold text-foreground">{projectDetails.tc.khavda_edges?.length || 0}</div>
                          </div>
                          <div className="p-3 border border-border rounded-md bg-muted">
                            <div className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">Rajasthan Nodes</div>
                            <div className="text-base font-semibold text-foreground">{projectDetails.tc.rajasthan_edges?.length || 0}</div>
                          </div>
                        </div>
                        
                        <div className="mt-4">
                           <h5 className="text-[11px] font-medium text-muted-foreground mb-2">Network Edges</h5>
                           <div className="space-y-1.5 max-h-[180px] overflow-y-auto pr-1">
                             {[...(projectDetails.tc.khavda_edges || []), ...(projectDetails.tc.rajasthan_edges || [])].map((edge: any, i: number) => (
                               <div key={i} className="flex flex-col py-1.5 px-2 rounded-md hover:bg-muted transition-colors text-xs gap-1">
                                 <div className="flex justify-between items-center font-medium">
                                   <span className="truncate flex-1" title={edge.project}>{edge.project}</span>
                                   <div className="flex gap-1 shrink-0 text-[10px]">
                                     <span className="text-muted-foreground border border-border px-1 rounded">{edge.phase}</span>
                                     <span className="text-muted-foreground border border-border px-1 rounded">{edge.voltage}</span>
                                   </div>
                                 </div>
                                 <div className="flex justify-between items-center text-muted-foreground">
                                   <div className="flex items-center gap-1.5 truncate max-w-[150px]">
                                     <span className="truncate" title={edge.from_label || edge.from_node}>{edge.from_label || edge.from_node}</span>
                                     <ArrowRightLeft className="w-2.5 h-2.5 shrink-0" />
                                     <span className="truncate" title={edge.to_label || edge.to_node}>{edge.to_label || edge.to_node}</span>
                                   </div>
                                   <span className="shrink-0 text-[10px] uppercase font-medium ml-2">
                                     {edge.normalizedStatus === 'completed' ? 'Charged' : (String(edge.status).match(/^\d+$/) ? `WIP ${edge.status}%` : edge.status || 'WIP')}
                                   </span>
                                 </div>
                               </div>
                             ))}
                           </div>
                        </div>
                      </div>
                    ) : (
                      <div className="text-sm text-muted-foreground italic text-center py-4">No transmission edges mapped</div>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>,
        document.body
      )}

      {/* ── Password Update Modal ── */}
      {showPasswordModal && createPortal(
        <div className="fixed inset-0 flex items-center justify-center bg-black/40 p-4" style={{ zIndex: 9999 }}>
          <div className="w-full max-w-sm bg-card border border-border shadow-xl rounded-xl overflow-hidden animate-in fade-in zoom-in-95 duration-200">
            <div className="px-5 py-4 border-b border-border flex justify-between items-center bg-muted">
              <h3 className="font-semibold text-foreground">Update P6 Credentials</h3>
              <button 
                onClick={() => setShowPasswordModal(false)}
                className="text-muted-foreground hover:text-foreground p-1 rounded-md hover:bg-muted transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            
            <div className="p-5 space-y-4">
              <p className="text-sm text-muted-foreground">
                Enter your new Oracle Primavera P6 API password. It will be securely encoded and saved.
              </p>
              
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">New Password</label>
                <input 
                  type="password" 
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder="••••••••" 
                  className="w-full bg-background border border-border rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary transition-shadow"
                />
              </div>
              
              {passwordUpdateResult && (
                <div className={`p-3 rounded-md text-sm ${passwordUpdateResult.error ? 'bg-destructive/100/10 text-destructive' : 'bg-success/100/10 text-success'}`}>
                  {passwordUpdateResult.error || passwordUpdateResult.success}
                </div>
              )}
              
              <div className="pt-2">
                <button 
                  onClick={handleUpdatePassword}
                  disabled={passwordUpdating || !newPassword}
                  className="w-full px-4 py-2 rounded-md text-sm font-medium bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50 flex justify-center items-center gap-2"
                >
                  {passwordUpdating && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
                  {passwordUpdating ? 'Updating...' : 'Save Password'}
                </button>
              </div>
            </div>
          </div>
        </div>,
        document.body
      )}
    </div>
  );
}

function SystemCard({ icon: Icon, name, status, color, metrics }: any) {
  const dotMap: any = {
    blue: "bg-primary/100",
    emerald: "bg-success/100",
    purple: "bg-purple-500"
  };

  return (
    <div className="p-5 rounded-xl border border-border bg-card flex flex-col justify-between shadow-sm">
      <div className="flex justify-between items-start mb-4">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-md bg-muted text-muted-foreground">
            <Icon className="w-4 h-4" />
          </div>
          <div>
            <h3 className="font-medium text-sm text-foreground">{name}</h3>
            <div className="flex items-center gap-1.5 mt-0.5 text-[11px] text-muted-foreground">
              <div className={`w-1.5 h-1.5 rounded-full ${dotMap[color] || 'bg-muted0'}`}></div>
              {status}
            </div>
          </div>
        </div>
      </div>
      <div className="flex gap-4 border-t border-border/50 pt-4 mt-auto">
        {metrics.map((m: any, i: number) => (
          <div key={i}>
            <div className="text-[10px] font-medium text-muted-foreground mb-0.5">{m.label}</div>
            <div className="text-xl font-semibold text-foreground tracking-tight">{m.val}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
