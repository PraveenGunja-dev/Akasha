import React, { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { fetchMappings, createMapping, updateMapping, deleteMapping, fetchUnmappedOptions } from '../services/mappingApi';
import type { ProjectMapping, ProjectMappingCreate, UnmappedOptions } from '../services/mappingApi';
import { Plus, Edit2, Trash2, X, Search, Save, AlertCircle, Map, Users, Settings, Database, Activity } from 'lucide-react';

const AdminDashboard: React.FC = () => {
  const [activeTab, setActiveTab] = useState('mappings');

  const tabs = [
    { id: 'mappings', label: 'Project Mappings', icon: <Map size={18} /> },
    { id: 'users', label: 'User Management', icon: <Users size={18} /> },
    { id: 'settings', label: 'System Settings', icon: <Settings size={18} /> },
    { id: 'integrations', label: 'Data Integrations', icon: <Database size={18} /> },
  ];

  return (
    <div className="flex h-screen bg-background text-foreground overflow-hidden">
      {/* Sidebar Navigation */}
      <div className="w-64 bg-card border-r border-border shrink-0 flex flex-col shadow-sm z-10">
        <div className="p-6 border-b border-border flex items-center gap-3">
          <div className="p-2 bg-primary/10 rounded-lg">
            <Activity className="text-primary w-5 h-5" />
          </div>
          <div>
            <h1 className="font-semibold tracking-wide text-base">AKASHA Admin</h1>
            <p className="text-muted-foreground text-xs">Control Center</p>
          </div>
        </div>
        
        <nav className="flex-1 p-4 space-y-1">
          {tabs.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors ${
                activeTab === tab.id 
                  ? 'bg-primary/10 text-primary font-medium' 
                  : 'text-muted-foreground hover:bg-secondary hover:text-foreground'
              }`}
            >
              {tab.icon}
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      {/* Main Content Area */}
      <main className="flex-1 overflow-y-auto bg-background p-8">
        <AnimatePresence mode="wait">
          <motion.div
            key={activeTab}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.2 }}
            className="max-w-7xl mx-auto w-full"
          >
            {activeTab === 'mappings' && <MappingsTab />}
            {activeTab === 'users' && <PlaceholderTab title="User Management" />}
            {activeTab === 'settings' && <PlaceholderTab title="System Settings" />}
            {activeTab === 'integrations' && <PlaceholderTab title="Data Integrations" />}
          </motion.div>
        </AnimatePresence>
      </main>
    </div>
  );
};

export default AdminDashboard;

// -----------------------------------------------------
// Mappings Tab Component
// -----------------------------------------------------

const MappingsTab: React.FC = () => {
  const [mappings, setMappings] = useState<ProjectMapping[]>([]);
  const [unmappedOptions, setUnmappedOptions] = useState<UnmappedOptions>({ unmapped_transmission: [], unmapped_p6: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  const [isPanelOpen, setIsPanelOpen] = useState(false);
  const [editingMapping, setEditingMapping] = useState<ProjectMapping | null>(null);
  const [formData, setFormData] = useState<ProjectMappingCreate>({});
  
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const [data, options] = await Promise.all([
        fetchMappings(),
        fetchUnmappedOptions()
      ]);
      setMappings(data);
      setUnmappedOptions(options);
      setError(null);
    } catch (err: any) {
      setError(err.message || 'Failed to load mappings');
    } finally {
      setLoading(false);
    }
  };

  const handleOpenPanel = (mapping?: ProjectMapping) => {
    if (mapping) {
      setEditingMapping(mapping);
      const { id, ...rest } = mapping;
      setFormData(rest);
    } else {
      setEditingMapping(null);
      setFormData({});
    }
    setIsPanelOpen(true);
  };

  const handleClosePanel = () => {
    setIsPanelOpen(false);
    setEditingMapping(null);
    setFormData({});
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value } = e.target;
    const numericFields = ['capacity_mwac', 'capacity_mwdc'];
    setFormData(prev => ({
      ...prev,
      [name]: numericFields.includes(name) ? (value ? parseFloat(value) : undefined) : value
    }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      if (editingMapping) {
        await updateMapping(editingMapping.id, formData);
      } else {
        await createMapping(formData);
      }
      await loadData();
      handleClosePanel();
    } catch (err: any) {
      setError(err.message || 'Failed to save mapping');
    }
  };

  const handleDelete = async (id: number) => {
    if (!window.confirm('Are you sure you want to delete this mapping?')) return;
    try {
      await deleteMapping(id);
      await loadData();
    } catch (err: any) {
      setError(err.message || 'Failed to delete mapping');
    }
  };

  const filteredMappings = mappings.filter(m => 
    (m.project?.toLowerCase().includes(searchQuery.toLowerCase())) ||
    (m.project_name_from_p6?.toLowerCase().includes(searchQuery.toLowerCase())) ||
    (m.spv_name?.toLowerCase().includes(searchQuery.toLowerCase()))
  );

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center mb-2">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight">Project Mappings</h2>
          <p className="text-muted-foreground mt-1 text-sm">Align Transmission, P6, and SAP data sources.</p>
        </div>
        <button 
          onClick={() => handleOpenPanel()}
          className="flex items-center gap-2 bg-primary hover:bg-primary/90 text-primary-foreground px-4 py-2 rounded-lg transition-colors text-sm font-medium shadow-sm"
        >
          <Plus size={16} />
          New Mapping
        </button>
      </div>

      {error && (
        <div className="bg-destructive/10 border border-destructive/20 text-destructive p-4 rounded-lg flex items-center gap-3 text-sm">
          <AlertCircle size={18} />
          <p>{error}</p>
        </div>
      )}

      {/* Table Card */}
      <div className="bento-card overflow-hidden">
        {/* Toolbar */}
        <div className="p-4 border-b border-border bg-card flex items-center justify-between">
          <div className="relative w-full max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" size={16} />
            <input 
              type="text" 
              placeholder="Search mappings..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-background border border-input focus:border-primary focus:ring-1 focus:ring-primary rounded-md pl-9 pr-4 py-1.5 text-sm outline-none transition-all"
            />
          </div>
          <div className="text-xs text-muted-foreground font-medium">
            {filteredMappings.length} Record{filteredMappings.length !== 1 ? 's' : ''}
          </div>
        </div>

        {/* Data Table */}
        <div className="overflow-x-auto">
          <table className="intel-table">
            <thead>
              <tr>
                <th>Transmission Project</th>
                <th>P6 Source Name</th>
                <th>SAP SPV</th>
                <th>Capacity</th>
                <th className="text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={5} className="px-6 py-12 text-center text-muted-foreground">
                    <div className="flex flex-col items-center justify-center gap-3">
                       <Activity className="w-5 h-5 animate-pulse text-primary" />
                       Loading mappings...
                    </div>
                  </td>
                </tr>
              ) : filteredMappings.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-6 py-12 text-center text-muted-foreground">
                    No mappings match your search criteria.
                  </td>
                </tr>
              ) : (
                filteredMappings.map((mapping) => (
                  <tr key={mapping.id}>
                    <td className="font-medium text-foreground">
                      {mapping.project || <span className="text-muted-foreground italic">None</span>}
                    </td>
                    <td>{mapping.project_name_from_p6 || '-'}</td>
                    <td>{mapping.spv_name || '-'}</td>
                    <td>{mapping.capacity_mwac ? `${mapping.capacity_mwac} MW` : '-'}</td>
                    <td className="text-right">
                      <div className="flex items-center justify-end gap-2">
                        <button 
                          onClick={() => handleOpenPanel(mapping)}
                          className="text-muted-foreground hover:text-primary transition-colors p-1.5 rounded-md hover:bg-secondary"
                          title="Edit"
                        >
                          <Edit2 size={14} />
                        </button>
                        <button 
                          onClick={() => handleDelete(mapping.id)}
                          className="text-muted-foreground hover:text-destructive transition-colors p-1.5 rounded-md hover:bg-destructive/10"
                          title="Delete"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Right Side Panel (Drawer) */}
      <AnimatePresence>
        {isPanelOpen && (
          <>
            {/* Backdrop */}
            <motion.div 
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={handleClosePanel}
              className="fixed inset-0 bg-background/80 backdrop-blur-sm z-40"
            />
            
            {/* Panel */}
            <motion.div 
              initial={{ x: '100%' }}
              animate={{ x: 0 }}
              exit={{ x: '100%' }}
              transition={{ type: 'spring', damping: 25, stiffness: 200 }}
              className="fixed inset-y-0 right-0 w-full sm:w-[450px] bg-card border-l border-border shadow-2xl z-50 flex flex-col"
            >
              <div className="p-5 border-b border-border flex justify-between items-center">
                <h3 className="text-lg font-semibold">
                  {editingMapping ? 'Edit Project Mapping' : 'Create New Mapping'}
                </h3>
                <button 
                  onClick={handleClosePanel}
                  className="p-2 text-muted-foreground hover:text-foreground hover:bg-secondary rounded-full transition-colors"
                >
                  <X size={16} />
                </button>
              </div>

              <div className="p-6 overflow-y-auto flex-1 custom-scrollbar">
                <form id="side-panel-form" onSubmit={handleSubmit} className="space-y-5">
                  
                  <div className="space-y-1.5">
                    <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Transmission Project Name <span className="lowercase normal-case font-normal">(Comma separated for multiple)</span></label>
                    <input 
                      list="transmission-options"
                      type="text" 
                      name="project"
                      value={formData.project || ''}
                      onChange={handleChange}
                      className="w-full bg-background border border-input focus:border-primary focus:ring-1 focus:ring-primary rounded-md px-3 py-2 text-sm outline-none transition-all"
                      placeholder="Select or type..."
                    />
                    <datalist id="transmission-options">
                      {unmappedOptions.unmapped_transmission.map(opt => (
                        <option key={opt} value={opt} />
                      ))}
                    </datalist>
                  </div>

                  <div className="space-y-1.5">
                    <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">P6 Project Name</label>
                    <input 
                      list="p6-options"
                      type="text" 
                      name="project_name_from_p6"
                      value={formData.project_name_from_p6 || ''}
                      onChange={handleChange}
                      className="w-full bg-background border border-input focus:border-primary focus:ring-1 focus:ring-primary rounded-md px-3 py-2 text-sm outline-none transition-all"
                      placeholder="Select or type..."
                    />
                    <datalist id="p6-options">
                      {unmappedOptions.unmapped_p6.map(opt => (
                        <option key={opt} value={opt} />
                      ))}
                    </datalist>
                  </div>
                  
                  <div className="space-y-1.5">
                    <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">P6 Project ID</label>
                    <input 
                      type="text" 
                      name="project_id"
                      value={formData.project_id || ''}
                      onChange={handleChange}
                      className="w-full bg-background border border-input focus:border-primary focus:ring-1 focus:ring-primary rounded-md px-3 py-2 text-sm outline-none transition-all"
                    />
                  </div>

                  <div className="space-y-1.5">
                    <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">SPV Name</label>
                    <input 
                      type="text" 
                      name="spv_name"
                      value={formData.spv_name || ''}
                      onChange={handleChange}
                      className="w-full bg-background border border-input focus:border-primary focus:ring-1 focus:ring-primary rounded-md px-3 py-2 text-sm outline-none transition-all"
                    />
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-1.5">
                      <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">SPV Plant Code</label>
                      <input 
                        type="text" 
                        name="spv_plant_code"
                        value={formData.spv_plant_code || ''}
                        onChange={handleChange}
                        className="w-full bg-background border border-input focus:border-primary focus:ring-1 focus:ring-primary rounded-md px-3 py-2 text-sm outline-none transition-all"
                      />
                    </div>
                    <div className="space-y-1.5">
                      <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Capacity (MW AC)</label>
                      <input 
                        type="number" 
                        step="0.01"
                        name="capacity_mwac"
                        value={formData.capacity_mwac || ''}
                        onChange={handleChange}
                        className="w-full bg-background border border-input focus:border-primary focus:ring-1 focus:ring-primary rounded-md px-3 py-2 text-sm outline-none transition-all"
                      />
                    </div>
                  </div>

                </form>
              </div>

              <div className="p-5 border-t border-border bg-card flex justify-end gap-3">
                <button 
                  type="button"
                  onClick={handleClosePanel}
                  className="px-4 py-2 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
                >
                  Cancel
                </button>
                <button 
                  type="submit"
                  form="side-panel-form"
                  className="flex items-center gap-2 bg-primary hover:bg-primary/90 text-primary-foreground px-5 py-2 rounded-md transition-colors text-sm font-medium shadow-sm"
                >
                  <Save size={16} />
                  Save Changes
                </button>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
};

// -----------------------------------------------------
// Placeholder Tab Component
// -----------------------------------------------------

const PlaceholderTab: React.FC<{ title: string }> = ({ title }) => (
  <div className="bento-card p-12 flex flex-col items-center justify-center text-center min-h-[400px]">
    <div className="w-16 h-16 bg-secondary rounded-full flex items-center justify-center mb-4">
      <Settings className="w-8 h-8 text-muted-foreground" />
    </div>
    <h3 className="text-xl font-medium mb-2">{title}</h3>
    <p className="text-muted-foreground max-w-sm text-sm">
      This section is under construction. It will provide dedicated administration tools for {title.toLowerCase()} in future updates.
    </p>
  </div>
);
