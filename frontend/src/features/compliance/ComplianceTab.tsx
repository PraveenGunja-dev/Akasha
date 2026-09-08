import React, { useState, useEffect } from 'react';
import { Shield, FileText, CheckCircle, AlertTriangle, XCircle, Loader2, Calendar, Clock } from 'lucide-react';

interface ComplianceTabProps {
  projectId: string;
}

export default function ComplianceTab({ projectId }: ComplianceTabProps) {
  const [loading, setLoading] = useState(true);
  const [complianceData, setComplianceData] = useState<any[]>([]);
  const [insuranceData, setInsuranceData] = useState<any[]>([]);
  const [p6Approvals, setP6Approvals] = useState<any[]>([]);
  const [epcData, setEpcData] = useState<any[]>([]);

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        const [compRes, insRes, p6Res, epcRes] = await Promise.all([
          fetch(`/akasha/api/statutory/compliance/${projectId}`),
          fetch(`/akasha/api/statutory/insurance`), 
          fetch(`/akasha/api/statutory/p6-approvals/${projectId}`),
          fetch(`/akasha/api/statutory/epc-status/${projectId}`)
        ]);

        if (compRes.ok) {
          const compJson = await compRes.json();
          setComplianceData(compJson);
        }
        
        if (insRes.ok) {
          const insJson = await insRes.json();
          // Filter insurance for this project by project_id
          const filteredIns = insJson.filter((i: any) => i.project_id === projectId);
          setInsuranceData(filteredIns);
        }

        if (p6Res.ok) {
          const p6Json = await p6Res.json();
          setP6Approvals(p6Json);
        }

        if (epcRes.ok) {
          const epcJson = await epcRes.json();
          setEpcData(epcJson);
        }
      } catch (err) {
        console.error("Error fetching compliance data:", err);
      } finally {
        setLoading(false);
      }
    };

    if (projectId) {
      fetchData();
    }
  }, [projectId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center p-12">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
        <span className="ml-3 text-muted-foreground font-medium">Loading Compliance & Approvals...</span>
      </div>
    );
  }

  const getDeadlineStatus = (dateString: string | null) => {
    if (!dateString) return null;
    const date = new Date(dateString);
    const now = new Date();
    const diffTime = date.getTime() - now.getTime();
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
    if (diffDays < 0) return 'expired';
    if (diffDays <= 30) return 'expiring_soon';
    return 'valid';
  };

  const renderStatus = (status: string) => {
    if (!status) return <span className="text-muted-foreground/50">-</span>;
    if (status.toLowerCase().includes('not available')) {
      return (
        <div className="flex items-center gap-1.5 text-destructive font-medium bg-destructive/10 px-2.5 py-1 rounded-md text-xs w-max">
          <XCircle className="w-3.5 h-3.5" />
          <span>Not Available</span>
        </div>
      );
    }
    if (status.toLowerCase().includes('available')) {
      return (
        <div className="flex items-center gap-1.5 text-emerald-500 font-medium bg-emerald-500/10 px-2.5 py-1 rounded-md text-xs w-max">
          <CheckCircle className="w-3.5 h-3.5" />
          <span>Available</span>
        </div>
      );
    }
    return <span className="text-xs font-medium text-muted-foreground">{status}</span>;
  };

  return (
    <div className="space-y-6">

      {/* 1. Statutory Checklist */}
      <div className="bg-card border border-border rounded-xl overflow-hidden shadow-sm">
        <div className="px-5 py-4 border-b border-border bg-muted/30 flex items-center gap-2">
          <Shield className="w-5 h-5 text-primary" />
          <h3 className="font-semibold">Statutory Documents Status</h3>
        </div>
        
        {complianceData.length === 0 ? (
          <div className="p-6 text-center text-muted-foreground text-sm">No statutory records found for this project.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-border bg-muted/10 text-xs uppercase tracking-wider text-muted-foreground">
                  <th className="p-4 font-semibold">EPC Partner</th>
                  <th className="p-4 font-semibold">Capacity</th>
                  <th className="p-4 font-semibold">GST</th>
                  <th className="p-4 font-semibold">BOCW</th>
                  <th className="p-4 font-semibold">CLRA</th>
                  <th className="p-4 font-semibold">SPCB</th>
                  <th className="p-4 font-semibold">Sub Lease</th>
                  <th className="p-4 font-semibold">Insurance</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border text-sm">
                {complianceData.map((row, idx) => (
                  <tr key={idx} className="hover:bg-muted/30 transition-colors">
                    <td className="p-4 font-medium">{row.epc_partner || '—'}</td>
                    <td className="p-4">{row.capacity_mwac ? `${row.capacity_mwac} MW` : '—'}</td>
                    <td className="p-4">{renderStatus(row.gst_status)}</td>
                    <td className="p-4">{renderStatus(row.bocw_status)}</td>
                    <td className="p-4">{renderStatus(row.clra_status)}</td>
                    <td className="p-4">{renderStatus(row.spcb_status)}</td>
                    <td className="p-4">{renderStatus(row.sub_lease_status)}</td>
                    <td className="p-4">{renderStatus(row.insurance_status)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* 1b. EPC Detailed Dates */}
      {epcData.length > 0 && (
        <div className="bg-card border border-border rounded-xl overflow-hidden shadow-sm">
          <div className="px-5 py-4 border-b border-border bg-muted/30 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Calendar className="w-5 h-5 text-primary" />
              <h3 className="font-semibold">EPC Partner Dates & Licensing</h3>
            </div>
            <div className="text-xs font-medium text-muted-foreground bg-muted px-2.5 py-1 rounded-md">
              Source: Statutory Status Master
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-border bg-muted/10 text-xs uppercase tracking-wider text-muted-foreground">
                  <th className="p-4 font-semibold">EPC Partner</th>
                  <th className="p-4 font-semibold">Plot</th>
                  <th className="p-4 font-semibold">BOCW Commencement</th>
                  <th className="p-4 font-semibold">BOCW Validity</th>
                  <th className="p-4 font-semibold">FTC Date</th>
                  <th className="p-4 font-semibold">CLRA Details</th>
                  <th className="p-4 font-semibold">GST Details</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border text-sm">
                {epcData.map((row, idx) => {
                  const bocwStatus = getDeadlineStatus(row.bocw_validity_date);
                  return (
                    <tr key={idx} className="hover:bg-muted/30 transition-colors">
                      <td className="p-4 font-bold text-foreground">{row.epc_partner || '—'}</td>
                      <td className="p-4">{row.plot || '—'}</td>
                      <td className="p-4 text-muted-foreground font-medium">{row.bocw_commencement_date ? new Date(row.bocw_commencement_date).toLocaleDateString('en-GB') : '—'}</td>
                      <td className="p-4">
                        {row.bocw_validity_date ? (
                          <div className="flex items-center gap-2">
                            <span className={`font-semibold ${bocwStatus === 'expired' ? 'text-destructive' : bocwStatus === 'expiring_soon' ? 'text-orange-500' : 'text-foreground'}`}>
                              {new Date(row.bocw_validity_date).toLocaleDateString('en-GB')}
                            </span>
                            {bocwStatus === 'expired' && <span title="Expired"><AlertTriangle className="w-3.5 h-3.5 text-destructive" /></span>}
                            {bocwStatus === 'expiring_soon' && <span title="Expiring Soon"><Clock className="w-3.5 h-3.5 text-orange-500" /></span>}
                          </div>
                        ) : '—'}
                      </td>
                      <td className="p-4 text-primary font-semibold">{row.ftc_date ? new Date(row.ftc_date).toLocaleDateString('en-GB') : '—'}</td>
                      <td className="p-4 max-w-[200px] truncate" title={row.clra_license_status}>{row.clra_license_status || '—'}</td>
                      <td className="p-4 max-w-[200px] truncate" title={row.gst_obtained}>{row.gst_obtained || '—'}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* 3. Insurance Details */}
      <div className="bg-card border border-border rounded-xl overflow-hidden shadow-sm">
        <div className="px-5 py-4 border-b border-border bg-muted/30 flex items-center gap-2">
          <FileText className="w-5 h-5 text-primary" />
          <h3 className="font-semibold">Insurance Policies</h3>
        </div>
        
        {insuranceData.length === 0 ? (
          <div className="p-6 text-center text-muted-foreground text-sm">No insurance records found for this project.</div>
        ) : (
          <div className="divide-y divide-border">
            {insuranceData.map((ins, idx) => {
              const expiryStatus = getDeadlineStatus(ins.policy_expiry);
              const isExpired = expiryStatus === 'expired';
              const isExpiringSoon = expiryStatus === 'expiring_soon';
              
              return (
                <div key={idx} className={`p-5 flex flex-col md:flex-row gap-6 md:items-center justify-between transition-colors ${isExpired ? 'bg-destructive/5 hover:bg-destructive/10' : isExpiringSoon ? 'bg-orange-500/5 hover:bg-orange-500/10' : 'hover:bg-muted/20'}`}>
                  <div className="flex-1 space-y-1">
                    <div className="flex items-center gap-2">
                      <h4 className={`font-bold text-base ${isExpired ? 'text-destructive' : isExpiringSoon ? 'text-orange-500' : ''}`}>{ins.insurance_company || 'Pending Insurer'}</h4>
                      {!isExpired && !isExpiringSoon && ins.renewal_alert === 'Live' ? (
                        <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-emerald-500/10 text-emerald-500 border border-emerald-500/20">Live</span>
                      ) : isExpired ? (
                        <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-destructive/10 text-destructive border border-destructive/20 flex items-center gap-1"><AlertTriangle className="w-3 h-3"/> Expired</span>
                      ) : isExpiringSoon ? (
                        <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-orange-500/10 text-orange-500 border border-orange-500/20 flex items-center gap-1"><Clock className="w-3 h-3"/> Renewal Due</span>
                      ) : ins.renewal_alert === 'Renewal' ? (
                        <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-amber-500/10 text-amber-500 border border-amber-500/20">Renewal Due</span>
                      ) : null}
                    </div>
                    <div className="text-sm text-muted-foreground flex items-center gap-4">
                      <span>EPC: <strong className="text-foreground">{ins.epc_vendor}</strong></span>
                      <span>Cap: <strong className="text-foreground">{ins.capacity_mwac} MW</strong></span>
                      <span>Policy: <strong className="text-foreground">{ins.policy_number || 'TBA'}</strong></span>
                    </div>
                  </div>
                  
                  <div className={`flex flex-wrap gap-6 text-sm px-5 py-3 rounded-lg border ${isExpired ? 'bg-destructive/10 border-destructive/20' : isExpiringSoon ? 'bg-orange-500/10 border-orange-500/20' : 'bg-muted/30 border-border/50'}`}>
                    <div>
                      <div className={`text-xs uppercase tracking-wider mb-1 ${isExpired ? 'text-destructive/70' : isExpiringSoon ? 'text-orange-500/70' : 'text-muted-foreground'}`}>Sum Insured</div>
                      <div className="font-mono font-medium">{ins.sum_insured ? `₹${ins.sum_insured} Cr` : '—'}</div>
                    </div>
                    <div>
                      <div className={`text-xs uppercase tracking-wider mb-1 ${isExpired ? 'text-destructive/70' : isExpiringSoon ? 'text-orange-500/70' : 'text-muted-foreground'}`}>Expiry Date</div>
                      <div className={`font-medium ${isExpired ? 'text-destructive font-bold' : isExpiringSoon ? 'text-orange-500 font-bold' : 'text-foreground'}`}>{ins.policy_expiry ? new Date(ins.policy_expiry).toLocaleDateString('en-GB') : '—'}</div>
                    </div>
                    <div>
                      <div className={`text-xs uppercase tracking-wider mb-1 ${isExpired ? 'text-destructive/70' : isExpiringSoon ? 'text-orange-500/70' : 'text-muted-foreground'}`}>Premium</div>
                      <div className="font-mono font-medium">{ins.premium_incl_gst ? `₹${(ins.premium_incl_gst / 10000000).toFixed(2)} Cr` : '—'}</div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* 4. P6 Statutory Milestones (Moved to Bottom) */}
      <div className="bg-card border border-border rounded-xl overflow-hidden shadow-sm mt-8">
        <div className="px-5 py-4 border-b border-border bg-muted/30 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Calendar className="w-5 h-5 text-primary" />
            <h3 className="font-semibold">Major Statutory Milestones (CEA, FTC, COD)</h3>
          </div>
          <div className="text-xs font-medium text-muted-foreground bg-muted px-2.5 py-1 rounded-md">
            Source: Live P6 Schedule
          </div>
        </div>
        
        {p6Approvals.length === 0 ? (
          <div className="p-6 text-center text-muted-foreground text-sm">No major statutory P6 activities found.</div>
        ) : (
          <div className="overflow-x-auto max-h-[350px] overflow-y-auto custom-scrollbar">
            <table className="w-full text-left border-collapse">
              <thead className="sticky top-0 bg-muted/95 backdrop-blur-sm z-10 shadow-sm">
                <tr className="text-xs uppercase tracking-wider text-muted-foreground">
                  <th className="p-4 font-semibold">Activity Name</th>
                  <th className="p-4 font-semibold">Baseline Date</th>
                  <th className="p-4 font-semibold">Forecast Date</th>
                  <th className="p-4 font-semibold">Actual Date</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border text-sm">
                {p6Approvals.map((act, idx) => {
                  const isComplete = act.percent_complete === 100 || act.status === 'Completed';
                  const baselineDate = act.baseline_finish_date || act.planned_finish_date;
                  const forecastDate = act.finish_date;
                  const actualDate = act.actual_finish_date;
                  
                  return (
                    <tr key={idx} className="hover:bg-muted/30 transition-colors">
                      <td className="p-4">
                        <div className="font-semibold text-foreground">{act.name}</div>
                        <div className="text-xs font-mono text-muted-foreground mt-0.5">{act.activity_id}</div>
                      </td>
                      <td className="p-4 text-muted-foreground font-medium">
                        {baselineDate ? new Date(baselineDate).toLocaleDateString('en-GB') : '—'}
                      </td>
                      <td className="p-4 text-primary font-semibold">
                        {forecastDate ? new Date(forecastDate).toLocaleDateString('en-GB') : '—'}
                      </td>
                      <td className="p-4 text-emerald-600 font-semibold">
                        {actualDate ? new Date(actualDate).toLocaleDateString('en-GB') : (isComplete ? new Date(forecastDate).toLocaleDateString('en-GB') : '—')}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

    </div>
  );
}
