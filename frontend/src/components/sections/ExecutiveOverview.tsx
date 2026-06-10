import React, { useState, useEffect } from 'react';
import { 
  TrendingUp, TrendingDown, Activity, DollarSign, CalendarClock, 
  AlertTriangle, ShieldCheck, Zap, Package, Bot, PenTool
} from 'lucide-react';

const KPICard = ({ title, value, trend, trendValue, icon: Icon, color }: any) => (
  <div className="bg-card border border-border rounded-xl p-5 relative overflow-hidden group hover:border-primary/50 transition-colors">
    {/* Background Glow */}
    <div className={`absolute top-0 right-0 w-24 h-24 bg-${color}-500/10 blur-2xl rounded-full -mr-8 -mt-8 transition-opacity group-hover:opacity-100 opacity-50`}></div>
    
    <div className="flex justify-between items-start mb-4 relative z-10">
      <div>
        <h4 className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-1">{title}</h4>
        <div className="text-3xl font-light text-foreground tracking-tight">{value}</div>
      </div>
      <div className={`p-2.5 rounded-lg bg-muted border border-border`}>
        <Icon className={`w-5 h-5 text-${color}-400`} />
      </div>
    </div>
    
    <div className="flex items-center gap-2 relative z-10 mt-4">
      <div className={`flex items-center gap-1 text-xs font-medium ${trend === 'up' ? 'text-emerald-500' : trend === 'down' ? 'text-red-500' : 'text-amber-500'}`}>
        {trend === 'up' ? <TrendingUp className="w-3 h-3" /> : trend === 'down' ? <TrendingDown className="w-3 h-3" /> : <Activity className="w-3 h-3" />}
        {trendValue}
      </div>
      <span className="text-xs text-muted-foreground/70">vs last month</span>
    </div>
  </div>
);

export default function ExecutiveOverview({ dashboardData }: { dashboardData: any }) {
  const summary = dashboardData?.summary || {};
  
  const totalProjects = summary.total_projects || 0;
  const delayedProjects = summary.delayed_projects || 0;
  
  const totalMW = summary.total_mw || 0;
  const formattedCost = `₹${((totalMW * 4000000) / 10000000).toFixed(1)} Cr`;
  const avgSpi = "1.00"; 
  
  // Calculate a stringified hash of the dashboardData to detect real data changes,
  // immune to reference changes and HMR.
  const currentDataHash = dashboardData ? JSON.stringify(dashboardData.summary || {}) : '';
  
  // Try to get cached data from sessionStorage
  const cachedStr = sessionStorage.getItem('akasha_briefing_data');
  const cachedHash = sessionStorage.getItem('akasha_briefing_hash');
  
  const parsedCache = cachedStr ? JSON.parse(cachedStr) : null;
  const isDataChanged = currentDataHash !== cachedHash || currentDataHash === '';
  
  const [loading, setLoading] = useState(isDataChanged || !parsedCache);
  const [briefing, setBriefing] = useState<any>(!isDataChanged ? parsedCache : null);
  const [error, setError] = useState('');

  useEffect(() => {
    // If data hasn't changed and we have a valid cache, don't fetch again
    if (!isDataChanged && parsedCache) {
      setLoading(false);
      setBriefing(parsedCache);
      return;
    }

    const fetchBriefing = async () => {
      setLoading(true);
      try {
        const response = await fetch('/akasha/api/generate-briefing');
        if (!response.ok) throw new Error('Failed to generate AI Briefing');
        const data = await response.json();
        
        sessionStorage.setItem('akasha_briefing_data', JSON.stringify(data));
        sessionStorage.setItem('akasha_briefing_hash', currentDataHash);
        
        setBriefing(data);
      } catch (err: any) {
        setError(err.message || 'Error connecting to AI Core');
      } finally {
        setLoading(false);
      }
    };
    
    // Only fetch if dashboard data is available (prevent fetching on initial null render)
    if (dashboardData) {
      fetchBriefing();
    }
  }, [currentDataHash]);
  
  return (
    <div className="flex flex-col gap-6 max-w-[1600px] mx-auto animate-in fade-in duration-500">
      
      {/* SECTION 1: EXECUTIVE COMMAND CENTER */}
      <div>
        <div className="flex items-center gap-2 mb-4">
          <Activity className="w-5 h-5 text-primary" />
          <h2 className="text-lg font-semibold text-foreground tracking-wide">Executive Command Center</h2>
        </div>
        
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <KPICard 
            title="Total Active Projects" 
            value={totalProjects} 
            trend="up" trendValue="+0 new" 
            icon={Activity} color="blue" 
          />
          <KPICard 
            title="Portfolio Health (SPI)" 
            value={avgSpi} 
            trend={Number(avgSpi) >= 1.0 ? "up" : "down"} trendValue="Live" 
            icon={CalendarClock} color={Number(avgSpi) >= 1.0 ? "emerald" : "amber"} 
          />
          <KPICard 
            title="Total Actual Cost" 
            value={formattedCost} 
            trend="up" trendValue="Live" 
            icon={DollarSign} color="emerald" 
          />
          <KPICard 
            title="Critical Delayed Projects" 
            value={delayedProjects} 
            trend="down" trendValue="Live" 
            icon={AlertTriangle} color="red" 
          />
        </div>
      </div>

      {/* SECTION 2: AI EXECUTIVE BRIEF */}
      <div className="bg-gradient-to-br from-card to-muted border border-primary/30 rounded-2xl p-6 shadow-[0_8px_32px_rgba(0,0,0,0.4)] relative overflow-hidden">
        <div className="absolute top-0 right-0 w-64 h-64 bg-primary/5 blur-[100px] rounded-full pointer-events-none"></div>
        
        <div className="flex justify-between items-start mb-4">
          <div className="flex items-center gap-3">
             <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary to-purple-600 p-[1px]">
                <div className="w-full h-full bg-background rounded-xl flex items-center justify-center">
                   <Bot className="w-5 h-5 text-foreground" />
                </div>
             </div>
             <div>
               <h3 className="text-lg font-medium text-foreground tracking-wide flex items-center gap-2">
                 Executive Intelligence Brief
                 <span className="text-[10px] bg-emerald-500/20 text-emerald-500 border border-emerald-500/30 px-2 py-0.5 rounded-full font-semibold uppercase tracking-wider">
                   Confidence: {briefing?.confidenceScore || 94}%
                 </span>
               </h3>
               <p className="text-xs text-muted-foreground">Generated automatically at {new Date().toLocaleTimeString()} based on latest sync.</p>
             </div>
          </div>
          
        </div>

        <div className="pl-14 pr-4 min-h-[100px] flex flex-col justify-center">
          {loading ? (
             <div className="flex items-center gap-4 py-4">
                <div className="w-5 h-5 rounded-full border-2 border-primary border-t-transparent animate-spin"></div>
                <span className="text-sm text-muted-foreground font-medium animate-pulse">Analyzing live SAP & Oracle P6 portfolio data via Groq...</span>
             </div>
          ) : error ? (
             <div className="text-sm text-red-500 font-medium py-2 flex items-center gap-2">
                <AlertTriangle className="w-4 h-4" /> {error}
             </div>
          ) : (
            <>
              <p className="text-sm text-foreground/90 leading-relaxed font-light text-justify border-l-2 border-primary/50 pl-4 py-1">
                <strong className="text-foreground font-semibold">Portfolio Summary:</strong> {briefing?.toplineSummary}
              </p>
              
              <div className="flex items-center gap-3 mt-4 text-xs font-medium flex-wrap">
                 <span className="text-muted-foreground/70">Key Drivers:</span>
                 {briefing?.keyActions?.map((action: any, idx: number) => (
                   <span key={idx} className="flex items-center gap-1 px-2.5 py-1 rounded-md" style={{ backgroundColor: `${action.color}15`, color: action.color, border: `1px solid ${action.color}30` }}>
                     <Zap className="w-3 h-3" /> {action.title}
                   </span>
                 ))}
              </div>
            </>
          )}
        </div>
      </div>

    </div>
  );
}
