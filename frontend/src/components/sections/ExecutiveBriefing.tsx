import React, { useState, useEffect } from 'react';
import { FileText, AlertTriangle, TrendingDown, Clock, ShieldAlert, CheckCircle2, ChevronRight, Play, ServerCrash } from 'lucide-react';

export default function ExecutiveBriefing() {
  const [loading, setLoading] = useState(true);
  const [briefing, setBriefing] = useState<any>(null);
  const [error, setError] = useState('');
  const [date] = useState(new Date().toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' }));

  useEffect(() => {
    const fetchBriefing = async () => {
      try {
        const response = await fetch('/akasha/api/generate-briefing');
        if (!response.ok) throw new Error('Failed to generate AI Briefing');
        const data = await response.json();
        setBriefing(data);
      } catch (err: any) {
        setError(err.message || 'Error connecting to AI Core');
      } finally {
        setLoading(false);
      }
    };
    fetchBriefing();
  }, []);

  const getIcon = (type: string, color: string) => {
    if (color.includes('EF4444') || type.toLowerCase().includes('critical')) return <ShieldAlert className={`w-5 h-5 text-[${color}]`} />;
    if (color.includes('F59E0B') || type.toLowerCase().includes('risk')) return <TrendingDown className={`w-5 h-5 text-[${color}]`} />;
    if (color.includes('10B981') || type.toLowerCase().includes('milestone')) return <CheckCircle2 className={`w-5 h-5 text-[${color}]`} />;
    return <AlertTriangle className={`w-5 h-5 text-[${color}]`} />;
  };

  return (
    <div className="flex flex-col h-full w-full max-w-[1200px] mx-auto animate-in fade-in duration-500 pb-10 mt-6">
      
      {/* Header */}
      <div className="flex items-end justify-between mb-8">
        <div>
          <h2 className="text-3xl font-light text-foreground tracking-wide flex items-center gap-3">
             <FileText className="w-8 h-8 text-primary" />
             Executive <span className="font-bold">Briefing</span>
          </h2>
          <p className="text-sm text-primary mt-2 uppercase tracking-widest font-semibold ml-11">{date}</p>
        </div>
        
        <div className="flex gap-3">
          <button className="bg-muted hover:bg-accent text-foreground px-4 py-2 rounded-lg text-sm transition-colors border border-border flex items-center gap-2">
            <Play className="w-4 h-4" /> Listen to Audio Brief
          </button>
          <button className="bg-primary hover:bg-primary/90 text-primary-foreground px-4 py-2 rounded-lg text-sm transition-colors shadow-[0_0_15px_rgba(59,130,246,0.4)]">
            Export PDF
          </button>
        </div>
      </div>

      {loading ? (
        <div className="flex-1 flex flex-col items-center justify-center space-y-6">
           <div className="w-16 h-16 relative">
              <div className="absolute inset-0 border-4 border-muted rounded-full"></div>
              <div className="absolute inset-0 border-4 border-primary rounded-full border-t-transparent animate-spin"></div>
           </div>
           <div className="text-muted-foreground font-mono text-sm tracking-widest uppercase animate-pulse">
             Generating Executive Intelligence via AKASHA AI...
           </div>
        </div>
      ) : error ? (
        <div className="flex-1 flex flex-col items-center justify-center space-y-4">
           <ServerCrash className="w-12 h-12 text-red-500" />
           <p className="text-red-500 font-medium">{error}</p>
           <p className="text-muted-foreground/70 text-sm">Please ensure the AI API Key is set in your backend environment.</p>
        </div>
      ) : briefing ? (
        <div className="space-y-6 animate-in slide-in-from-bottom-8 duration-700">
          
          {/* Executive Summary Card */}
          <div className="bg-muted border-l-4 border-l-primary border-y border-r border-border/50 rounded-xl p-8 shadow-2xl relative overflow-hidden">
             <div className="absolute top-0 right-0 w-64 h-64 bg-primary/5 rounded-full blur-[80px] pointer-events-none"></div>
             
             <h3 className="text-xs font-bold text-muted-foreground/70 uppercase tracking-widest mb-4">AI Topline Summary</h3>
             <p className="text-lg text-foreground/90 leading-relaxed max-w-4xl">
               {briefing.toplineSummary}
             </p>
          </div>

          {/* Grid of Key Actions */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {briefing.keyActions?.map((action: any, idx: number) => (
              <div key={idx} className="bg-card border border-border/50 rounded-xl p-6 hover:border-border transition-colors group cursor-pointer relative overflow-hidden">
                <div className={`absolute inset-0 opacity-0 group-hover:opacity-10 transition-opacity`} style={{ backgroundColor: action.color }}></div>
                <div className="flex items-center gap-3 mb-4">
                  <div className="w-10 h-10 rounded-lg flex items-center justify-center shrink-0" style={{ backgroundColor: `${action.color}15`, border: `1px solid ${action.color}30` }}>
                    {getIcon(action.type, action.color)}
                  </div>
                  <h3 className="text-sm font-bold text-foreground uppercase tracking-wider">{action.type}</h3>
                </div>
                <h4 className="text-foreground font-semibold mb-2">{action.title}</h4>
                <p className="text-sm text-muted-foreground mb-4 line-clamp-3">
                  {action.description}
                </p>
                <div className="flex items-center text-xs font-bold uppercase tracking-widest group-hover:translate-x-1 transition-transform" style={{ color: action.color }}>
                  Take Action <ChevronRight className="w-4 h-4 ml-1" />
                </div>
              </div>
            ))}
          </div>
          
          {/* Detailed Narrative */}
          <div className="bg-card border border-border/50 rounded-xl p-8">
             <h3 className="text-xs font-bold text-muted-foreground/70 uppercase tracking-widest mb-6 border-b border-border/50 pb-4">Deep Dive Analysis</h3>
             
             <div className="space-y-6">
                {briefing.deepDive?.map((item: any, idx: number) => (
                  <div key={idx}>
                     <h4 className="text-foreground font-medium mb-2 flex items-center gap-2">
                       <Clock className="w-4 h-4 text-primary" /> {item.title}
                     </h4>
                     <p className="text-sm text-muted-foreground leading-relaxed">
                       {item.description}
                     </p>
                  </div>
                ))}
             </div>
          </div>

        </div>
      ) : null}
    </div>
  );
}
