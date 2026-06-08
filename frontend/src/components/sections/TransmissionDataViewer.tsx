import React, { useState, useEffect } from 'react';
import { rajasthanApi } from '../../services/rajasthanApi';
import { khavdaApi } from '../../services/khavdaApi';

export default function TransmissionDataViewer({ dashboardData }: { dashboardData?: any }) {
  const [data, setData] = useState<any>({
    rajasthanNetwork: null,
    khavdaProjects: null,
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchTransmissionData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [kProjectsRes, rNetworkRes] = await Promise.all([
        fetch('http://localhost:8000/api/tc/khavda/projects').then(r => r.json()).catch(e => ({ error: e.message })),
        fetch('http://localhost:8000/api/tc/rajasthan/network').then(r => r.json()).catch(e => ({ error: e.message }))
      ]);

      setData({
        rajasthanNetwork: rNetworkRes,
        khavdaProjects: kProjectsRes,
      });
    } catch (err: any) {
      setError(err.message || 'Error fetching transmission data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTransmissionData();
    // Refresh twice a day logic could be added here or in a global service
    // e.g. setInterval(fetchTransmissionData, 12 * 60 * 60 * 1000)
  }, []);

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-700">
      <div className="flex justify-between items-center bg-card/40 border border-border/50 p-6 rounded-2xl backdrop-blur-xl">
        <div>
          <h2 className="text-2xl font-light tracking-wide text-foreground">Transmission Data Explorer</h2>
          <p className="text-sm text-muted-foreground mt-1">Raw API Data from Rajasthan & Khavda Endpoints</p>
        </div>
        <button 
          onClick={fetchTransmissionData}
          className="px-4 py-2 bg-primary/20 text-primary border border-primary/30 rounded-full hover:bg-primary/30 transition-colors"
          disabled={loading}
        >
          {loading ? 'Fetching...' : 'Refresh Data'}
        </button>
      </div>

      {error && (
        <div className="p-4 bg-destructive/10 text-destructive border border-destructive/20 rounded-xl">
          {error}
        </div>
      )}

      {/* SECTION: UNIFIED PROJECT EXPLORER (Moved from Executive Overview) */}
      <div className="mt-8">
        <div className="flex items-center gap-3 mb-6">
          <div className="w-8 h-8 rounded-lg bg-gradient-premium flex items-center justify-center shadow-sm">
            <h3 className="text-white font-bold text-lg">M</h3>
          </div>
          <h2 className="text-xl font-medium text-foreground tracking-wide">Transmission Mapping Details</h2>
        </div>

        <div className="glass-card rounded-2xl overflow-hidden shadow-lg border border-white/20">
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="bg-muted/50 text-muted-foreground uppercase tracking-widest text-[10px] font-bold border-b border-border/50">
                <tr>
                  <th className="px-6 py-4">Project Name</th>
                  <th className="px-6 py-4">Capacity</th>
                  <th className="px-6 py-4">P6 Schedule</th>
                  <th className="px-6 py-4">SAP Inventory</th>
                  <th className="px-6 py-4">Transmission JSON</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/30">
                {/* Fallback to raw data if unified dashboardData is not passed */}
                {dashboardData?.projects?.map((proj: any, idx: number) => (
                  <tr key={idx} className="hover:bg-muted/30 transition-colors group">
                    <td className="px-6 py-4 font-medium text-foreground">{proj.project_name}</td>
                    <td className="px-6 py-4 text-muted-foreground">{proj.capacity_mw} MW</td>
                    <td className="px-6 py-4">
                      <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold ${
                        proj.p6.health === 'On Track' ? 'bg-emerald-500/10 text-emerald-600' :
                        proj.p6.health === 'Delayed' ? 'bg-red-500/10 text-red-600' : 'bg-gray-500/10 text-gray-500'
                      }`}>
                        {proj.p6.health}
                      </span>
                    </td>
                    <td className="px-6 py-4 font-mono">{proj.sap.inventory_mw} MW</td>
                    <td className="px-6 py-4">
                      <div className="relative group/tc">
                        <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium border cursor-help ${
                          proj.tc.has_data ? 'border-purple-500/30 text-purple-600 bg-purple-500/5' : 'border-border text-muted-foreground'
                        }`}>
                          {proj.tc.status}
                        </span>
                        {/* Hover JSON Tooltip */}
                        {proj.tc.has_data && (
                          <div className="absolute left-0 bottom-full mb-2 hidden group-hover/tc:block z-50">
                            <div className="bg-black/90 dark:bg-[#0B1020]/95 backdrop-blur-xl border border-white/20 p-4 rounded-xl shadow-2xl w-[300px]">
                              <h4 className="text-[10px] text-purple-400 font-bold uppercase tracking-wider mb-2">Transmission JSON</h4>
                              <div className="max-h-[200px] overflow-y-auto custom-scrollbar">
                                <pre className="text-[10px] text-green-400/90 font-mono whitespace-pre-wrap">
                                  {JSON.stringify(proj.tc.data, null, 2)}
                                </pre>
                              </div>
                            </div>
                          </div>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
      
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-8">
        <DataCard title="Raw Khavda Blocks API" data={data.khavdaProjects} />
        <DataCard title="Raw Rajasthan Edges API" data={data.rajasthanNetwork} />
      </div>
    </div>
  );
}

function DataCard({ title, data }: { title: string, data: any }) {
  return (
    <div className="bg-card/30 border border-border/40 rounded-2xl p-6 backdrop-blur-lg flex flex-col max-h-[500px]">
      <h3 className="text-lg font-medium text-foreground mb-4">{title}</h3>
      <div className="flex-1 overflow-auto bg-black/40 rounded-xl p-4 custom-scrollbar">
        {data ? (
          <pre className="text-xs text-muted-foreground whitespace-pre-wrap font-mono">
            {JSON.stringify(data, null, 2)}
          </pre>
        ) : (
          <p className="text-sm text-muted-foreground italic">No data available...</p>
        )}
      </div>
    </div>
  );
}
