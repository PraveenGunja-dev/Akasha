import React from 'react';
import { Network, ZoomIn, ZoomOut, Maximize, Filter, Database, Box, Building2, TrendingUp } from 'lucide-react';

export default function KnowledgeGraph() {
  
  return (
    <div className="flex flex-col h-[calc(100vh-100px)] w-full rounded-2xl border border-border/50 overflow-hidden bg-background shadow-2xl animate-in fade-in duration-500 relative">
      
      {/* Overlay Toolbar */}
      <div className="absolute top-6 left-6 z-10">
        <h2 className="text-xl font-light text-foreground tracking-widest flex items-center gap-3">
           <Network className="w-5 h-5 text-primary" />
           AKASHA <span className="font-bold">GRAPH</span>
        </h2>
        <p className="text-xs text-muted-foreground/70 mt-1 uppercase tracking-widest font-semibold ml-8">Ontology Visualization</p>
      </div>
      
      <div className="absolute top-6 right-6 z-10 flex items-center gap-2 bg-muted/80 backdrop-blur-md p-1.5 rounded-lg border border-border/50 shadow-lg">
        <button className="p-2 hover:bg-accent rounded transition-colors text-muted-foreground hover:text-foreground" title="Filter Nodes">
          <Filter className="w-4 h-4" />
        </button>
        <div className="w-px h-4 bg-border"></div>
        <button className="p-2 hover:bg-accent rounded transition-colors text-muted-foreground hover:text-foreground" title="Zoom In">
          <ZoomIn className="w-4 h-4" />
        </button>
        <button className="p-2 hover:bg-accent rounded transition-colors text-muted-foreground hover:text-foreground" title="Zoom Out">
          <ZoomOut className="w-4 h-4" />
        </button>
        <button className="p-2 hover:bg-accent rounded transition-colors text-muted-foreground hover:text-foreground" title="Fit to Screen">
          <Maximize className="w-4 h-4" />
        </button>
      </div>
      
      {/* Graph Legend */}
      <div className="absolute bottom-6 left-6 z-10 flex flex-col gap-2 bg-muted/80 backdrop-blur-md p-4 rounded-xl border border-border/50 shadow-lg">
        <div className="text-[10px] font-bold text-muted-foreground/70 uppercase tracking-widest mb-1">Entity Types</div>
        <div className="flex items-center gap-3 text-xs text-foreground/90">
          <div className="w-3 h-3 rounded-full bg-red-500"></div> Project Node
        </div>
        <div className="flex items-center gap-3 text-xs text-foreground/90">
          <div className="w-3 h-3 rounded bg-primary"></div> Purchase Order Node
        </div>
        <div className="flex items-center gap-3 text-xs text-foreground/90">
          <div className="w-0 h-0 border-l-[6px] border-l-transparent border-r-[6px] border-r-transparent border-b-[10px] border-b-emerald-500"></div> Material Node
        </div>
        <div className="flex items-center gap-3 text-xs text-foreground/90">
          <div className="w-3 h-3 rounded-sm rotate-45 bg-amber-500"></div> Vendor Node
        </div>
      </div>

      {/* Simulated Graph Canvas (SVG) */}
      <div className="flex-1 w-full h-full bg-background relative overflow-hidden cursor-move">
        {/* Grid Background */}
        <div className="absolute inset-0 opacity-10 pointer-events-none" 
             style={{ backgroundImage: 'radial-gradient(var(--primary) 1px, transparent 1px)', backgroundSize: '40px 40px' }}>
        </div>
        
        {/* SVG Edges connecting the nodes */}
        <svg className="absolute inset-0 w-full h-full pointer-events-none z-0">
          <path d="M 400 300 Q 550 150 700 200" fill="none" stroke="var(--primary)" strokeWidth="1" strokeDasharray="4,4" className="animate-pulse opacity-50" />
          <path d="M 400 300 Q 450 450 600 500" fill="none" stroke="var(--border)" strokeWidth="2" />
          <path d="M 400 300 Q 250 200 150 350" fill="none" stroke="var(--border)" strokeWidth="2" />
          <path d="M 700 200 Q 800 150 900 300" fill="none" stroke="#10B981" strokeWidth="1" strokeDasharray="4,4" className="animate-pulse opacity-50" />
          <path d="M 600 500 Q 750 450 850 550" fill="none" stroke="var(--border)" strokeWidth="2" />
        </svg>

        {/* Nodes (Absolute Positioned for simulation) */}
        
        {/* Central Project Node */}
        <div className="absolute top-[300px] left-[400px] -translate-x-1/2 -translate-y-1/2 z-10 group cursor-pointer">
          <div className="relative flex flex-col items-center">
            <div className="w-16 h-16 rounded-full bg-muted border-2 border-red-500 flex items-center justify-center relative z-10 group-hover:scale-110 transition-transform">
               <TrendingUp className="w-6 h-6 text-red-500" />
            </div>
            <div className="absolute top-full mt-3 bg-muted border border-border/50 px-3 py-2 rounded-lg shadow-xl whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity z-20 pointer-events-none">
              <div className="text-xs font-bold text-foreground mb-1">ACL_A1_FT_125 MW</div>
              <div className="text-[10px] text-red-500 font-mono">Critical • 0d Var</div>
            </div>
          </div>
        </div>

        {/* Purchase Order Node 1 */}
        <div className="absolute top-[200px] left-[700px] -translate-x-1/2 -translate-y-1/2 z-10 group cursor-pointer">
          <div className="relative flex flex-col items-center">
            <div className="w-12 h-12 rounded bg-muted border-2 border-primary flex items-center justify-center relative z-10 group-hover:scale-110 transition-transform">
               <Database className="w-5 h-5 text-primary" />
            </div>
            <div className="absolute top-full mt-3 bg-muted border border-border/50 px-3 py-2 rounded-lg shadow-xl whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity z-20 pointer-events-none">
              <div className="text-xs font-bold text-foreground mb-1">PO-4910082</div>
              <div className="text-[10px] text-muted-foreground font-mono">Value: $4.2M</div>
            </div>
          </div>
        </div>

        {/* Purchase Order Node 2 */}
        <div className="absolute top-[500px] left-[600px] -translate-x-1/2 -translate-y-1/2 z-10 group cursor-pointer">
          <div className="relative flex flex-col items-center">
            <div className="w-12 h-12 rounded bg-muted border-2 border-primary flex items-center justify-center relative z-10 group-hover:scale-110 transition-transform">
               <Database className="w-5 h-5 text-muted-foreground/70" />
            </div>
            <div className="absolute top-full mt-3 bg-muted border border-border/50 px-3 py-2 rounded-lg shadow-xl whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity z-20 pointer-events-none">
              <div className="text-xs font-bold text-foreground mb-1">PO-4910115</div>
              <div className="text-[10px] text-muted-foreground font-mono">Value: $1.8M</div>
            </div>
          </div>
        </div>

        {/* Material Node */}
        <div className="absolute top-[300px] left-[900px] -translate-x-1/2 -translate-y-1/2 z-10 group cursor-pointer">
          <div className="relative flex flex-col items-center">
            <div className="w-10 h-10 flex items-center justify-center relative z-10 group-hover:scale-110 transition-transform">
               <div className="absolute inset-0 w-0 h-0 border-l-[20px] border-l-transparent border-r-[20px] border-r-transparent border-b-[34px] border-b-emerald-500"></div>
               <Box className="w-4 h-4 text-background z-10 mt-3" />
            </div>
            <div className="absolute top-full mt-5 bg-muted border border-border/50 px-3 py-2 rounded-lg shadow-xl whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity z-20 pointer-events-none">
              <div className="text-xs font-bold text-foreground mb-1">Solar Modules (425W)</div>
              <div className="text-[10px] text-emerald-500 font-mono">In Transit: 42 MW</div>
            </div>
          </div>
        </div>

        {/* Vendor Node */}
        <div className="absolute top-[350px] left-[150px] -translate-x-1/2 -translate-y-1/2 z-10 group cursor-pointer">
          <div className="relative flex flex-col items-center">
            <div className="w-14 h-14 bg-muted border-2 border-amber-500 rounded-lg rotate-45 flex items-center justify-center relative z-10 group-hover:scale-110 transition-transform">
               <Building2 className="w-5 h-5 text-amber-500 -rotate-45" />
            </div>
            <div className="absolute top-full mt-6 bg-muted border border-border/50 px-3 py-2 rounded-lg shadow-xl whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity z-20 pointer-events-none">
              <div className="text-xs font-bold text-foreground mb-1">ADANI GREEN</div>
              <div className="text-[10px] text-muted-foreground font-mono">Risk Profile: Low</div>
            </div>
          </div>
        </div>
        
      </div>
    </div>
  );
}
