import React, { useState, useEffect } from 'react';
import { Brain, AlertTriangle, ArrowRight, ShieldAlert, Target, Shield, Clock, Activity } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

export default function PortfolioIntelligence() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const navigate = useNavigate();

  useEffect(() => {
    const fetchPortfolio = async () => {
      try {
        const res = await fetch('/akasha/api/intelligence/portfolio/summary');
        if (!res.ok) throw new Error('Failed to fetch portfolio intelligence');
        const json = await res.json();
        setData(json);
      } catch (err: any) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };
    fetchPortfolio();
  }, []);

  if (loading) {
    return (
      <div className="intelligence-card p-12 flex flex-col items-center justify-center text-center animate-pulse">
        <Brain className="w-12 h-12 text-primary/50 mb-4 animate-spin-slow" />
        <h3 className="text-xl font-semibold mb-2">Analyzing Portfolio Telemetry...</h3>
        <p className="text-muted-foreground max-w-md">The Intelligence Engine is processing data across all active projects.</p>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="intelligence-card p-12 flex flex-col items-center justify-center text-center">
        <AlertTriangle className="w-12 h-12 text-destructive mb-4" />
        <h3 className="text-xl font-semibold mb-2">Analysis Failed</h3>
        <p className="text-muted-foreground">{error}</p>
      </div>
    );
  }

  const {
    total_projects, delayed_projects, critical_projects, at_risk_projects,
    portfolio_health, hotspots
  } = data;

  return (
    <div className="space-y-6">
      
      {/* Portfolio Top Line */}
      <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
        <div className="intelligence-card p-5 bg-card flex flex-col justify-center">
          <div className="text-sm font-medium uppercase tracking-wider text-muted-foreground mb-1">Portfolio Health</div>
          <div className="text-3xl font-bold flex items-baseline gap-2 text-primary">
            {portfolio_health} <span className="text-lg font-normal text-muted-foreground">/100</span>
          </div>
        </div>
        <div className="intelligence-card p-5 bg-card flex flex-col justify-center">
          <div className="text-sm font-medium uppercase tracking-wider text-muted-foreground mb-1">Total Projects</div>
          <div className="text-3xl font-bold">{total_projects}</div>
        </div>
        <div className="intelligence-card p-5 border border-destructive/20 bg-destructive/5 flex flex-col justify-center">
          <div className="text-sm font-medium uppercase tracking-wider text-destructive mb-1">Critical Projects</div>
          <div className="text-3xl font-bold text-destructive">{critical_projects}</div>
        </div>
        <div className="intelligence-card p-5 border border-orange-500/20 bg-orange-500/5 flex flex-col justify-center">
          <div className="text-sm font-medium uppercase tracking-wider text-orange-500 mb-1">At Risk</div>
          <div className="text-3xl font-bold text-orange-500">{at_risk_projects}</div>
        </div>
        <div className="intelligence-card p-5 bg-card flex flex-col justify-center">
          <div className="text-sm font-medium uppercase tracking-wider text-muted-foreground mb-1">Delayed</div>
          <div className="text-3xl font-bold">{delayed_projects}</div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Hotspots */}
        <div className="intelligence-card p-6 border-destructive/20 bg-destructive/[0.02]">
          <h3 className="text-lg font-bold mb-4 flex items-center gap-2">
            <ShieldAlert className="w-5 h-5 text-destructive" /> Top Hotspots (Action Required)
          </h3>
          <div className="space-y-3">
            {hotspots && hotspots.length > 0 ? (
              hotspots.map((hotspot: any, idx: number) => (
                <div key={idx} onClick={() => navigate(`/ceo-dashboard/project/${hotspot.project_id}`)} className="p-4 rounded-lg border border-border bg-card hover:bg-muted/50 cursor-pointer transition-colors flex items-center justify-between">
                  <div>
                    <h4 className="font-semibold text-foreground mb-1">{hotspot.project_name}</h4>
                    <div className="flex items-center gap-4 text-xs">
                      <span className="flex items-center gap-1 text-destructive font-bold"><Activity className="w-3 h-3" /> Health: {hotspot.health}/100</span>
                      <span className="flex items-center gap-1 text-orange-500"><Clock className="w-3 h-3" /> Delay: {hotspot.delay} days</span>
                    </div>
                  </div>
                  <ArrowRight className="w-5 h-5 text-muted-foreground/50" />
                </div>
              ))
            ) : (
              <div className="text-sm text-muted-foreground p-4 bg-muted/50 rounded-lg">No critical hotspots identified.</div>
            )}
          </div>
        </div>

        {/* Aggregate Actions */}
        <div className="intelligence-card p-6">
          <h3 className="text-lg font-bold mb-4 flex items-center gap-2">
            <Target className="w-5 h-5 text-primary" /> Systemic Bottlenecks
          </h3>
          <div className="space-y-4">
            <div className="p-4 rounded-lg border border-border bg-card">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-bold text-foreground">Supply Chain / Logistics</span>
                <span className="text-xs px-2 py-1 bg-destructive/10 text-destructive rounded font-bold uppercase">High Impact</span>
              </div>
              <p className="text-sm text-muted-foreground">Multiple projects in Rajasthan and Khavda are experiencing delays in material dispatch, primarily WTG towers and MMS structures.</p>
            </div>
            
            <div className="p-4 rounded-lg border border-border bg-card">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-bold text-foreground">Land Acquisition & ROW</span>
                <span className="text-xs px-2 py-1 bg-orange-500/10 text-orange-500 rounded font-bold uppercase">Medium Impact</span>
              </div>
              <p className="text-sm text-muted-foreground">Right of Way (ROW) issues are impacting transmission line stringing in 3 active projects.</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
