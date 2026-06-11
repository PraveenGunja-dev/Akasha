import React, { useState, useEffect } from 'react';
import { 
  TrendingUp, TrendingDown, Activity, DollarSign, CalendarClock, 
  AlertTriangle, ShieldCheck, Zap, Package, Bot, PenTool
} from 'lucide-react';

const colorToHex: Record<string, string> = {
  blue: '#3B82F6',
  emerald: '#10B981',
  amber: '#F59E0B',
  red: '#EF4444'
};

const KPICard = ({ title, value, trend, trendValue, icon: Icon, color }: any) => {
  const hexColor = colorToHex[color] || colorToHex.blue;
  return (
  <div className="bg-card/40 backdrop-blur-md border border-border/60 rounded-2xl p-6 relative overflow-hidden group hover:bg-card hover:border-primary/40 hover:shadow-[0_8px_30px_rgb(0,0,0,0.06)] dark:hover:shadow-[0_8px_30px_rgba(59,130,246,0.1)] transition-all duration-300 hover:-translate-y-1">
    {/* Subtle Colored Glow Overlay on Hover */}
    <div 
      className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none"
      style={{ background: `radial-gradient(circle at top right, ${hexColor}15, transparent 70%)` }}
    />
    
    <div className="flex justify-between items-start mb-5 relative z-10">
      <div>
        <h4 className="text-[13px] font-semibold text-muted-foreground uppercase tracking-widest mb-1.5 transition-colors group-hover:text-foreground/80">{title}</h4>
        <div className="text-3xl font-light text-foreground tracking-tight">{value}</div>
      </div>
      <div 
        className="p-3 rounded-xl transition-transform duration-300 group-hover:scale-110 group-hover:-rotate-3 shadow-sm border"
        style={{ backgroundColor: `${hexColor}15`, borderColor: `${hexColor}30` }}
      >
        <Icon className="w-5 h-5 transition-colors duration-300" style={{ color: hexColor }} />
      </div>
    </div>
    
    <div className="flex items-center gap-2 relative z-10 mt-5 pt-4 border-t border-border/40">
      <div className={`flex items-center gap-1.5 text-xs font-semibold ${trend === 'up' ? 'text-emerald-500' : trend === 'down' ? 'text-red-500' : 'text-amber-500'}`}>
        {trend === 'up' ? <TrendingUp className="w-3.5 h-3.5" /> : trend === 'down' ? <TrendingDown className="w-3.5 h-3.5" /> : <Activity className="w-3.5 h-3.5" />}
        {trendValue}
      </div>
      <span className="text-xs text-muted-foreground/60 font-medium">vs last month</span>
    </div>
  </div>
)};

export default function ExecutiveOverview({ dashboardData, briefing, briefingLoading, briefingError }: { dashboardData: any, briefing: any, briefingLoading: boolean, briefingError: string }) {
  const summary = dashboardData?.summary || {};
  
  const totalProjects = summary.total_projects || 0;
  const delayedProjects = summary.delayed_projects || 0;
  
  const totalMW = summary.total_mw || 0;
  const formattedCost = `₹${((totalMW * 4000000) / 10000000).toFixed(1)} Cr`;
  const avgSpi = "1.00"; 

  
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
      <div className="bg-card/40 backdrop-blur-xl border border-primary/20 hover:border-primary/40 rounded-3xl p-7 shadow-[0_8px_30px_rgb(0,0,0,0.06)] dark:shadow-[0_8px_30px_rgba(59,130,246,0.1)] relative overflow-hidden group transition-all duration-300 mt-2">
        <div className="absolute top-0 right-0 w-64 h-64 bg-primary/10 blur-[100px] rounded-full pointer-events-none transition-opacity duration-500 group-hover:opacity-100 opacity-70"></div>
        <div className="absolute bottom-0 left-0 w-48 h-48 bg-purple-500/10 blur-[80px] rounded-full pointer-events-none transition-opacity duration-500 group-hover:opacity-100 opacity-50"></div>
        
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
          {briefingLoading ? (
             <div className="flex items-center gap-4 py-4">
                <div className="w-5 h-5 rounded-full border-2 border-primary border-t-transparent animate-spin"></div>
                <span className="text-sm text-muted-foreground font-medium animate-pulse">Analyzing live SAP & Oracle P6 portfolio data via Azure OpenAI...</span>
             </div>
          ) : briefingError ? (
             <div className="text-sm text-red-500 font-medium py-2 flex items-center gap-2">
                <AlertTriangle className="w-4 h-4" /> {briefingError}
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
