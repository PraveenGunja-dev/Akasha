import React, { useState, useEffect } from 'react';
import { Shield, FileText, CheckCircle, AlertTriangle, XCircle, Loader2, Calendar } from 'lucide-react';
import ReactECharts from 'echarts-for-react';

export default function ComplianceDashboard() {
  const [loading, setLoading] = useState(true);
  const [summaryData, setSummaryData] = useState<any>(null);
  const [complianceData, setComplianceData] = useState<any[]>([]);
  const [epcData, setEpcData] = useState<any[]>([]);
  const [insuranceData, setInsuranceData] = useState<any[]>([]);

  useEffect(() => {
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
    fetchData();
  }, []);

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
    <div className="p-6 space-y-6 max-w-[1600px] mx-auto animate-in fade-in duration-300">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
            <Shield className="w-6 h-6 text-primary" />
            Global Approvals & Compliance
          </h1>
          <p className="text-muted-foreground mt-1">Portfolio-wide statutory, compliance, and insurance tracking</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-card border border-border rounded-xl p-5 shadow-sm relative overflow-hidden group hover:border-primary/50 transition-colors">
          <div className="flex items-center justify-between mb-4">
            <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground group-hover:text-foreground transition-colors">Tracked Projects</span>
            <div className="p-2 bg-primary/10 rounded-lg text-primary"><FileText className="w-4 h-4" /></div>
          </div>
          <div className="text-3xl font-light">{summaryData?.total_projects_tracked || 0}</div>
        </div>
        
        <div className="bg-card border border-border rounded-xl p-5 shadow-sm relative overflow-hidden group hover:border-success/50 transition-colors">
          <div className="flex items-center justify-between mb-4">
            <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground group-hover:text-foreground transition-colors">Overall Compliance</span>
            <div className="p-2 bg-success/10 rounded-lg text-success"><CheckCircle className="w-4 h-4" /></div>
          </div>
          <div className="text-3xl font-light text-success">{summaryData?.overall_compliance_percent || 0}%</div>
        </div>
        
        <div className="bg-card border border-border rounded-xl p-5 shadow-sm relative overflow-hidden group hover:border-destructive/50 transition-colors">
          <div className="flex items-center justify-between mb-4">
            <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground group-hover:text-foreground transition-colors">Missing CLRA</span>
            <div className="p-2 bg-destructive/10 rounded-lg text-destructive"><AlertTriangle className="w-4 h-4" /></div>
          </div>
          <div className="text-3xl font-light text-destructive">{summaryData?.clra_missing_count || 0}</div>
          <div className="text-xs text-muted-foreground mt-1">Offline letters submitted</div>
        </div>
        
        <div className="bg-card border border-border rounded-xl p-5 shadow-sm relative overflow-hidden group hover:border-warning/50 transition-colors">
          <div className="flex items-center justify-between mb-4">
            <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground group-hover:text-foreground transition-colors">Insurance Renewals</span>
            <div className="p-2 bg-warning/10 rounded-lg text-warning"><Calendar className="w-4 h-4" /></div>
          </div>
          <div className="text-3xl font-light text-warning">{summaryData?.insurance_renewals_pending || 0}</div>
          <div className="text-xs text-muted-foreground mt-1">Pending action</div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bg-card border border-border rounded-xl shadow-sm overflow-hidden">
          <div className="px-5 py-4 border-b border-border bg-muted/30">
            <h3 className="font-semibold flex items-center gap-2">
              <FileText className="w-4 h-4 text-primary" />
              Statutory Checklist (Portfolio View)
            </h3>
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
                {complianceData.map((row, idx) => (
                  <tr key={idx} className="hover:bg-muted/30 transition-colors">
                    <td className="p-4 font-medium max-w-[200px] truncate" title={row.p6_project_name || row.project_name}>{row.p6_project_name || row.project_name || '—'}</td>
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

      {/* EPC Detailed Dates (Global View) */}
      {epcData.length > 0 && (
        <div className="bg-card border border-border rounded-xl shadow-sm overflow-hidden mt-6">
          <div className="px-5 py-4 border-b border-border bg-muted/30">
            <h3 className="font-semibold flex items-center gap-2">
              <Calendar className="w-4 h-4 text-primary" />
              EPC Partner Dates & Licensing (Portfolio View)
            </h3>
          </div>
          <div className="overflow-x-auto max-h-[400px] overflow-y-auto custom-scrollbar">
            <table className="w-full text-left text-sm whitespace-nowrap">
              <thead className="sticky top-0 bg-muted/95 backdrop-blur-sm z-10 shadow-sm">
                <tr className="text-xs uppercase tracking-wider text-muted-foreground">
                  <th className="p-4 font-semibold">P6 Project</th>
                  <th className="p-4 font-semibold">EPC Partner</th>
                  <th className="p-4 font-semibold">Plot</th>
                  <th className="p-4 font-semibold">BOCW Commencement</th>
                  <th className="p-4 font-semibold">BOCW Validity</th>
                  <th className="p-4 font-semibold">FTC Date</th>
                  <th className="p-4 font-semibold">CLRA Details</th>
                  <th className="p-4 font-semibold">GST Details</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {epcData.map((row, idx) => (
                  <tr key={idx} className="hover:bg-muted/30 transition-colors">
                    <td className="p-4 font-medium max-w-[200px] truncate" title={row.p6_project_name || row.project_name}>{row.p6_project_name || row.project_name || '—'}</td>
                    <td className="p-4 font-bold text-foreground">{row.epc_partner || '—'}</td>
                    <td className="p-4">{row.plot || '—'}</td>
                    <td className="p-4 text-muted-foreground font-medium">{row.bocw_commencement_date ? new Date(row.bocw_commencement_date).toLocaleDateString('en-GB') : '—'}</td>
                    <td className="p-4 text-foreground font-semibold">{row.bocw_validity_date ? new Date(row.bocw_validity_date).toLocaleDateString('en-GB') : '—'}</td>
                    <td className="p-4 text-primary font-semibold">{row.ftc_date ? new Date(row.ftc_date).toLocaleDateString('en-GB') : '—'}</td>
                    <td className="p-4 max-w-[200px] truncate" title={row.clra_license_status}>{row.clra_license_status || '—'}</td>
                    <td className="p-4 max-w-[200px] truncate" title={row.gst_obtained}>{row.gst_obtained || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Insurance Tracking (Global View) */}
      {insuranceData.length > 0 && (
        <div className="bg-card border border-border rounded-xl shadow-sm overflow-hidden mt-6">
          <div className="px-5 py-4 border-b border-border bg-muted/30 flex items-center justify-between">
            <h3 className="font-semibold flex items-center gap-2">
              <Shield className="w-4 h-4 text-primary" />
              Insurance Policies (Portfolio View)
            </h3>
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
                    <td className="p-4 font-medium max-w-[200px] truncate" title={ins.p6_project_name || ins.project_name}>{ins.p6_project_name || ins.project_name || '—'}</td>
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
                    <td className="p-4">{ins.policy_expiry ? new Date(ins.policy_expiry).toLocaleDateString('en-GB') : '—'}</td>
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
