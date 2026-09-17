import React, { useState, useEffect, useRef } from 'react';
import { formatDate } from '../../lib/utils';
import { Shield, FileText, CheckCircle, AlertTriangle, XCircle, Loader2, Calendar, Upload, X, HardHat, Factory } from 'lucide-react';
import ReactECharts from 'echarts-for-react';
import { formatProjectName } from '../../lib/projectName';

export default function ComplianceDashboard() {
  const [loading, setLoading] = useState(true);
  const [summaryData, setSummaryData] = useState<any>(null);
  const [complianceData, setComplianceData] = useState<any[]>([]);
  const [epcData, setEpcData] = useState<any[]>([]);
  const [insuranceData, setInsuranceData] = useState<any[]>([]);
  const [activeSection, setActiveSection] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const statutoryRef = useRef<HTMLDivElement>(null);
  const insuranceRef = useRef<HTMLDivElement>(null);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [sumRes, compRes, epcRes, insRes] = await Promise.all([
        fetch('/akasha/api/statutory/dashboard-summary'),
        fetch('/akasha/api/statutory/compliance'),
        fetch('/akasha/api/statutory/epc-status'),
        fetch('/akasha/api/statutory/insurance')
      ]);
      
      if (sumRes.ok) setSummaryData(await sumRes.json());
      if (compRes.ok) setComplianceData(await compRes.json());
      if (epcRes.ok) setEpcData(await epcRes.json());
      if (insRes.ok) setInsuranceData(await insRes.json());
    } catch (err) {
      console.error("Error fetching global compliance:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchData(); }, []);

  // Auto-dismiss upload message after 5s
  useEffect(() => {
    if (uploadMsg) {
      const t = setTimeout(() => setUploadMsg(null), 5000);
      return () => clearTimeout(t);
    }
  }, [uploadMsg]);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploading(true);
    setUploadMsg(null);
    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await fetch('/akasha/api/statutory/upload', { method: 'POST', body: formData });
      if (res.ok) {
        const data = await res.json();
        setUploadMsg({ type: 'success', text: `✓ Imported ${data.records_imported} records from "${data.filename}"` });
        await fetchData(); // Refresh all data
      } else {
        const err = await res.json().catch(() => ({ detail: 'Upload failed' }));
        setUploadMsg({ type: 'error', text: `✗ ${err.detail}` });
      }
    } catch {
      setUploadMsg({ type: 'error', text: '✗ Network error during upload' });
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const scrollToSection = (section: string) => {
    const next = activeSection === section ? null : section;
    setActiveSection(next);
    if (!next) return;
    const ref = section === 'insurance' ? insuranceRef : statutoryRef;
    if (ref.current) {
      setTimeout(() => ref.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 100);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center p-12 h-screen">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
        <span className="ml-3 text-muted-foreground font-medium">Loading Compliance Data...</span>
      </div>
    );
  }

  const renderStatus = (status: string) => {
    if (!status) return <span className="text-muted-foreground/50">-</span>;
    if (status.toLowerCase().includes('not available')) {
      return (
        <div className="flex items-center gap-1.5 text-destructive font-medium bg-destructive/10 px-2 py-0.5 rounded text-[10px] w-max">
          <XCircle className="w-3 h-3" />
          <span>Missing</span>
        </div>
      );
    }
    if (status.toLowerCase().includes('available')) {
      return (
        <div className="flex items-center gap-1.5 text-emerald-500 font-medium bg-emerald-500/10 px-2 py-0.5 rounded text-[10px] w-max">
          <CheckCircle className="w-3 h-3" />
          <span>Available</span>
        </div>
      );
    }
    return <span className="text-xs font-medium text-muted-foreground">{status}</span>;
  };

  const chartOption = {
    tooltip: { trigger: 'item', backgroundColor: '#fff', borderColor: '#e2e8f0' },
    series: [
      {
        type: 'pie',
        radius: ['50%', '70%'],
        avoidLabelOverlap: false,
        label: { show: false },
        itemStyle: { borderRadius: 4, borderColor: '#fff', borderWidth: 2 },
        data: [
          { value: summaryData?.overall_compliance_percent || 0, name: 'Compliant', itemStyle: { color: '#10B981' } },
          { value: 100 - (summaryData?.overall_compliance_percent || 0), name: 'Missing', itemStyle: { color: '#EF4444' } }
        ]
      }
    ]
  };

  return (
    <div className="w-full p-6 space-y-6 animate-in fade-in duration-300">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
            <Shield className="w-6 h-6 text-primary" />
            Global Approvals & Compliance
          </h1>
          <p className="text-muted-foreground mt-1">Portfolio-wide statutory, compliance, and insurance tracking</p>
        </div>
        {/* Upload Excel Button */}
        <div className="flex items-center gap-3">
          <input
            ref={fileInputRef}
            type="file"
            accept=".xlsx,.xls"
            className="hidden"
            onChange={handleUpload}
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50 shadow-sm"
          >
            {uploading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
            {uploading ? 'Uploading...' : 'Upload Excel'}
          </button>
        </div>
      </div>

      {/* Upload feedback toast */}
      {uploadMsg && (
        <div className={`flex items-center justify-between px-4 py-3 rounded-lg text-sm font-medium border animate-in slide-in-from-top-2 duration-300 ${uploadMsg.type === 'success' ? 'bg-emerald-500/10 text-emerald-600 border-emerald-500/20' : 'bg-destructive/10 text-destructive border-destructive/20'}`}>
          <span>{uploadMsg.text}</span>
          <button onClick={() => setUploadMsg(null)} className="ml-4 opacity-60 hover:opacity-100"><X className="w-4 h-4" /></button>
        </div>
      )}

      {/* 6 KPI Cards — 3 per row */}
      <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-6 gap-4">
        {/* Tracked Projects */}
        <div className="kpi-card bg-card border border-border rounded-xl p-4 shadow-sm relative overflow-hidden group hover:border-primary/50 transition-colors">
          <div className="flex items-center justify-between mb-4">
            <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground group-hover:text-foreground transition-colors">Tracked Projects</span>
            <div className="p-2 bg-primary/10 rounded-lg text-primary"><FileText className="w-4 h-4" /></div>
          </div>
          <div className="text-3xl font-light">{summaryData?.total_projects_tracked || 0}</div>
        </div>
        
        {/* Overall Compliance */}
        <div className="kpi-card bg-card border border-border rounded-xl p-4 shadow-sm relative overflow-hidden group hover:border-success/50 transition-colors">
          <div className="flex items-center justify-between mb-4">
            <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground group-hover:text-foreground transition-colors">Overall Compliance</span>
            <div className="p-2 bg-success/10 rounded-lg text-success"><CheckCircle className="w-4 h-4" /></div>
          </div>
          <div className="text-3xl font-light text-success">{summaryData?.overall_compliance_percent || 0}%</div>
        </div>
        
        {/* Missing CLRA */}
        <div
          onClick={() => scrollToSection('clra')}
          className={`kpi-card bg-card border rounded-xl p-4 shadow-sm relative overflow-hidden group transition-all cursor-pointer ${activeSection === 'clra' ? 'border-destructive ring-2 ring-destructive/30 shadow-md' : 'border-border hover:border-destructive/50'}`}
        >
          <div className="flex items-center justify-between mb-4">
            <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground group-hover:text-foreground transition-colors">Missing CLRA</span>
            <div className="p-2 bg-destructive/10 rounded-lg text-destructive"><AlertTriangle className="w-4 h-4" /></div>
          </div>
          <div className="text-3xl font-light text-destructive">{summaryData?.clra_missing_count || 0}</div>
          <div className="text-xs text-muted-foreground mt-1">Click to view</div>
        </div>
        
        {/* Missing BOCW */}
        <div
          onClick={() => scrollToSection('bocw')}
          className={`kpi-card bg-card border rounded-xl p-4 shadow-sm relative overflow-hidden group transition-all cursor-pointer ${activeSection === 'bocw' ? 'border-orange-500 ring-2 ring-orange-500/30 shadow-md' : 'border-border hover:border-orange-500/50'}`}
        >
          <div className="flex items-center justify-between mb-4">
            <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground group-hover:text-foreground transition-colors">Missing BOCW</span>
            <div className="p-2 bg-orange-500/10 rounded-lg text-orange-500"><HardHat className="w-4 h-4" /></div>
          </div>
          <div className="text-3xl font-light text-orange-500">{summaryData?.bocw_missing_count || 0}</div>
          <div className="text-xs text-muted-foreground mt-1">Click to view</div>
        </div>

        {/* Missing SPCB */}
        <div
          onClick={() => scrollToSection('spcb')}
          className={`kpi-card bg-card border rounded-xl p-4 shadow-sm relative overflow-hidden group transition-all cursor-pointer ${activeSection === 'spcb' ? 'border-purple-500 ring-2 ring-purple-500/30 shadow-md' : 'border-border hover:border-purple-500/50'}`}
        >
          <div className="flex items-center justify-between mb-4">
            <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground group-hover:text-foreground transition-colors">Missing SPCB</span>
            <div className="p-2 bg-purple-500/10 rounded-lg text-purple-500"><Factory className="w-4 h-4" /></div>
          </div>
          <div className="text-3xl font-light text-purple-500">{summaryData?.spcb_missing_count || 0}</div>
          <div className="text-xs text-muted-foreground mt-1">Click to view</div>
        </div>

        {/* Insurance Renewals */}
        <div
          onClick={() => scrollToSection('insurance')}
          className={`kpi-card bg-card border rounded-xl p-4 shadow-sm relative overflow-hidden group transition-all cursor-pointer ${activeSection === 'insurance' ? 'border-warning ring-2 ring-warning/30 shadow-md' : 'border-border hover:border-warning/50'}`}
        >
          <div className="flex items-center justify-between mb-4">
            <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground group-hover:text-foreground transition-colors">Insurance Renewals</span>
            <div className="p-2 bg-warning/10 rounded-lg text-warning"><Calendar className="w-4 h-4" /></div>
          </div>
          <div className="text-3xl font-light text-warning">{summaryData?.insurance_renewals_pending || 0}</div>
          <div className="text-xs text-muted-foreground mt-1">Click to view</div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div
          ref={statutoryRef}
          className={`lg:col-span-2 bg-card border rounded-xl shadow-sm overflow-hidden transition-all duration-300 ${
            activeSection && ['clra', 'bocw', 'spcb'].includes(activeSection)
              ? activeSection === 'clra' ? 'border-destructive ring-2 ring-destructive/20'
              : activeSection === 'bocw' ? 'border-orange-500 ring-2 ring-orange-500/20'
              : 'border-purple-500 ring-2 ring-purple-500/20'
            : 'border-border'
          }`}
        >
          <div className="px-5 py-4 border-b border-border bg-muted/30 flex items-center justify-between">
            <h3 className="font-semibold flex items-center gap-2">
              <FileText className="w-4 h-4 text-primary" />
              Statutory Checklist (Portfolio View)
              {activeSection && ['clra', 'bocw', 'spcb'].includes(activeSection) && (
                <span className="ml-2 px-2 py-0.5 rounded-full text-[10px] font-bold uppercase bg-muted text-foreground border border-border">
                  Showing: {activeSection.toUpperCase()} Missing
                </span>
              )}
            </h3>
            {activeSection && ['clra', 'bocw', 'spcb'].includes(activeSection) && (
              <button
                onClick={() => setActiveSection(null)}
                className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1 px-2 py-1 rounded hover:bg-muted transition-colors"
              >
                <X className="w-3 h-3" /> Clear Filter
              </button>
            )}
          </div>
          <div className="overflow-x-auto max-h-[500px] overflow-y-auto custom-scrollbar">
            <table className="w-full text-left text-sm whitespace-nowrap">
              <thead className="sticky top-0 bg-muted/95 backdrop-blur-sm z-10 shadow-sm">
                <tr className="text-xs uppercase tracking-wider text-muted-foreground">
                  <th className="p-4 font-semibold">P6 Project</th>
                  <th className="p-4 font-semibold">SPV</th>
                  <th className="p-4 font-semibold">EPC</th>
                  <th className="p-4 font-semibold">GST</th>
                  <th className="p-4 font-semibold">BOCW</th>
                  <th className="p-4 font-semibold">CLRA</th>
                  <th className="p-4 font-semibold">SPCB</th>
                  <th className="p-4 font-semibold">Insurance</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {(activeSection === 'clra'
                  ? complianceData.filter(r => r.clra_status?.toLowerCase().includes('not available'))
                  : activeSection === 'bocw'
                  ? complianceData.filter(r => r.bocw_status?.toLowerCase().includes('not available'))
                  : activeSection === 'spcb'
                  ? complianceData.filter(r => r.spcb_status?.toLowerCase().includes('not available'))
                  : complianceData
                ).map((row, idx) => (
                  <tr key={idx} className="hover:bg-muted/30 transition-colors">
                    <td className="p-4 font-medium max-w-[200px] truncate" title={formatProjectName(row.p6_project_name || row.project_name)}>{formatProjectName(row.p6_project_name || row.project_name) || '—'}</td>
                    <td className="p-4">{row.spv_code || '—'}</td>
                    <td className="p-4 font-mono text-xs">{row.epc_partner || '—'}</td>
                    <td className="p-4">{renderStatus(row.gst_status)}</td>
                    <td className="p-4">{renderStatus(row.bocw_status)}</td>
                    <td className="p-4">{renderStatus(row.clra_status)}</td>
                    <td className="p-4">{renderStatus(row.spcb_status)}</td>
                    <td className="p-4">{renderStatus(row.insurance_status)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
        
        <div className="bg-card border border-border rounded-xl shadow-sm overflow-hidden flex flex-col">
          <div className="px-5 py-4 border-b border-border bg-muted/30">
            <h3 className="font-semibold flex items-center gap-2">
              <Shield className="w-4 h-4 text-primary" />
              Compliance Score
            </h3>
          </div>
          <div className="flex-1 p-6 flex flex-col items-center justify-center">
            <div className="w-full h-[250px] relative">
              <ReactECharts option={chartOption} style={{ height: '100%', width: '100%' }} />
              <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
                <span className="text-3xl font-light">{summaryData?.overall_compliance_percent || 0}%</span>
              </div>
            </div>
            <div className="mt-4 text-center">
              <p className="text-sm text-muted-foreground">Portfolio-wide document availability</p>
              <div className="mt-4 flex gap-4 justify-center">
                <div className="flex items-center gap-2 text-xs">
                  <div className="w-3 h-3 rounded-sm bg-emerald-500"></div> Available
                </div>
                <div className="flex items-center gap-2 text-xs">
                  <div className="w-3 h-3 rounded-sm bg-destructive"></div> Missing
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Insurance Tracking (Global View) */}
      {insuranceData.length > 0 && (
        <div
          ref={insuranceRef}
          className={`bg-card border rounded-xl shadow-sm overflow-hidden mt-6 transition-all duration-300 ${activeSection === 'insurance' ? 'border-warning ring-2 ring-warning/20' : 'border-border'}`}
        >
          <div className="px-5 py-4 border-b border-border bg-muted/30 flex items-center justify-between">
            <h3 className="font-semibold flex items-center gap-2">
              <Shield className="w-4 h-4 text-primary" />
              Insurance Policies (Portfolio View)
            </h3>
            {activeSection === 'insurance' && (
              <button
                onClick={() => setActiveSection(null)}
                className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1 px-2 py-1 rounded hover:bg-muted transition-colors"
              >
                <X className="w-3 h-3" /> Clear Highlight
              </button>
            )}
          </div>
          <div className="overflow-x-auto max-h-[400px] overflow-y-auto custom-scrollbar">
            <table className="w-full text-left text-sm whitespace-nowrap">
              <thead className="sticky top-0 bg-muted/95 backdrop-blur-sm z-10 shadow-sm">
                <tr className="text-xs uppercase tracking-wider text-muted-foreground">
                  <th className="p-4 font-semibold">P6 Project</th>
                  <th className="p-4 font-semibold">Insurance Company</th>
                  <th className="p-4 font-semibold">EPC / Cap</th>
                  <th className="p-4 font-semibold">Policy No.</th>
                  <th className="p-4 font-semibold">Sum Insured</th>
                  <th className="p-4 font-semibold">Premium</th>
                  <th className="p-4 font-semibold">Expiry Date</th>
                  <th className="p-4 font-semibold text-center">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {insuranceData.map((ins, idx) => (
                  <tr key={idx} className="hover:bg-muted/30 transition-colors">
                    <td className="p-4 font-medium max-w-[200px] truncate" title={formatProjectName(ins.p6_project_name || ins.project_name)}>{formatProjectName(ins.p6_project_name || ins.project_name) || '—'}</td>
                    <td className="p-4 font-bold text-foreground">{ins.insurance_company || 'Pending Insurer'}</td>
                    <td className="p-4">
                      <div className="flex flex-col">
                        <span>{ins.epc_vendor || '—'}</span>
                        <span className="text-xs text-muted-foreground">{ins.capacity_mwac ? `${ins.capacity_mwac} MW` : ''}</span>
                      </div>
                    </td>
                    <td className="p-4 font-mono text-xs text-muted-foreground">{ins.policy_number || 'TBA'}</td>
                    <td className="p-4 font-mono text-primary font-medium">{ins.sum_insured ? `₹${ins.sum_insured} Cr` : '—'}</td>
                    <td className="p-4 font-mono text-pink-500 font-medium">{ins.premium_incl_gst ? `₹${(ins.premium_incl_gst / 10000000).toFixed(2)} Cr` : '—'}</td>
                    <td className="p-4">{ins.policy_expiry ? formatDate(ins.policy_expiry) : '—'}</td>
                    <td className="p-4 text-center">
                      {ins.renewal_alert === 'Live' ? (
                        <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-emerald-500/10 text-emerald-500 border border-emerald-500/20">Live</span>
                      ) : ins.renewal_alert === 'Renewal' ? (
                        <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-amber-500/10 text-amber-500 border border-amber-500/20">Renewal Due</span>
                      ) : (
                        <span className="text-muted-foreground text-xs">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
