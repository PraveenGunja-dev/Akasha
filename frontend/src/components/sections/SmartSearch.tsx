import React, { useState } from 'react';
import { Search, FileText, Database, ArrowRight, Activity, Command, Package, Building2 } from 'lucide-react';

export default function SmartSearch({ onOpenProject }: { onOpenProject?: (id: string) => void }) {
  const [query, setQuery] = useState('');
  const [isSearching, setIsSearching] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);

  const [results, setResults] = useState<any[]>([]);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    
    setIsSearching(true);
    setHasSearched(true);
    
    try {
      const response = await fetch(`/akasha/api/dashboard/search?q=${encodeURIComponent(query)}`);
      const data = await response.json();
      setResults(data || []);
    } catch (err) {
      console.error('Search failed', err);
      setResults([]);
    } finally {
      setIsSearching(false);
    }
  };

  const getIconAndColor = (type: string) => {
    switch(type) {
      case 'Project': return { icon: Command, color: 'text-red-500', bg: 'bg-red-500/10' };
      case 'Purchase Order': return { icon: FileText, color: 'text-primary', bg: 'bg-primary/10' };
      case 'Material Component': return { icon: Package, color: 'text-emerald-500', bg: 'bg-emerald-500/10' };
      case 'Vendor': return { icon: Building2, color: 'text-amber-500', bg: 'bg-amber-500/10' };
      default: return { icon: Database, color: 'text-muted-foreground', bg: 'bg-muted' };
    }
  };

  const handleResultClick = (result: any) => {
    if (onOpenProject) {
      // If it's a project, open it directly. If it's a PO/Material, we could ideally
      // find its associated project, but for now passing the raw value will either 
      // open the workspace if it's a valid project ID, or show an empty state.
      onOpenProject(result.raw);
    }
  };

  return (
    <div className="flex flex-col items-center min-h-[calc(100vh-100px)] w-full animate-in fade-in duration-500 py-10 px-6 relative">
      
      {/* Background Graphic */}
      <div className="absolute top-1/3 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-gradient-to-br from-primary/5 to-emerald-500/5 rounded-full blur-[100px] pointer-events-none -z-10"></div>

      {/* Header (Animates up when searched) */}
      <div className={`transition-all duration-700 flex flex-col items-center ${hasSearched ? 'mt-0' : 'mt-32'}`}>
        <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-muted to-background border border-border flex items-center justify-center mb-6 shadow-2xl">
           <Search className="w-8 h-8 text-primary" />
        </div>
        <h1 className="text-3xl font-light text-foreground tracking-widest mb-2">AKASHA <span className="font-bold">SMART SEARCH</span></h1>
        <p className="text-sm text-muted-foreground/70 mb-8 font-mono">Global Enterprise Index • Connected to SAP R/3 & P6</p>

        {/* Search Bar */}
        <form onSubmit={handleSearch} className="w-full max-w-2xl relative group">
          <div className="absolute -inset-1 bg-gradient-to-r from-primary to-blue-400 rounded-2xl blur opacity-20 group-hover:opacity-40 transition duration-500"></div>
          <div className="relative bg-card border border-border/50 rounded-xl flex items-center p-2 shadow-2xl">
            <Search className="w-5 h-5 text-muted-foreground/70 ml-4" />
            <input 
              type="text" 
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search across projects, POs, vendors, and materials..."
              className="flex-1 bg-transparent border-none focus:outline-none text-foreground py-3 px-4 placeholder-muted-foreground/50 text-lg"
            />
            <button 
              type="submit"
              className="bg-muted hover:bg-primary text-foreground hover:text-primary-foreground px-6 py-3 rounded-lg transition-colors font-medium flex items-center gap-2 border border-border hover:border-primary"
            >
              Search <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        </form>

        {/* Filters (Pre-search) */}
        {!hasSearched && (
          <div className="mt-10 flex gap-4 animate-in slide-in-from-bottom-4 duration-700 delay-200">
            {['All Entities', 'Projects', 'Purchase Orders', 'Materials', 'Vendors'].map((filter, i) => (
              <button key={i} className="px-4 py-1.5 rounded-full border border-border/50 text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-muted transition-colors">
                {filter}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Results Area */}
      {hasSearched && (
        <div className="w-full max-w-4xl mt-12 animate-in slide-in-from-bottom-8 duration-500">
          
          <div className="flex items-center justify-between border-b border-border/50 pb-4 mb-6">
            <span className="text-sm text-muted-foreground">Found {results.length} results for "<span className="text-foreground font-medium">{query}</span>"</span>
            <span className="text-xs font-mono text-muted-foreground/70 bg-muted px-2 py-1 rounded">0.043s</span>
          </div>

          {isSearching ? (
             <div className="space-y-4">
               {[1, 2, 3].map((skeleton) => (
                 <div key={skeleton} className="w-full h-24 bg-card border border-border/50 rounded-xl animate-pulse flex p-5 gap-4">
                   <div className="w-10 h-10 rounded-lg bg-muted"></div>
                   <div className="flex-1 space-y-3 py-1">
                     <div className="h-4 bg-muted rounded w-1/3"></div>
                     <div className="h-3 bg-muted rounded w-2/3"></div>
                   </div>
                 </div>
               ))}
             </div>
          ) : (
             <div className="space-y-4">
               {results.map((result) => {
                 const style = getIconAndColor(result.type);
                 return (
                 <div 
                    key={result.id} 
                    onClick={() => handleResultClick(result)}
                    className="group bg-card border border-border/50 hover:border-primary/50 rounded-xl p-5 flex gap-4 cursor-pointer transition-all hover:shadow-[0_0_20px_rgba(59,130,246,0.1)]"
                 >
                   <div className={`w-12 h-12 rounded-lg flex items-center justify-center shrink-0 ${style.bg}`}>
                     <style.icon className={`w-5 h-5 ${style.color}`} />
                   </div>
                   <div className="flex-1">
                     <div className="flex items-center gap-2 mb-1">
                       <h3 className="text-lg font-semibold text-foreground/90 group-hover:text-primary transition-colors">{result.title}</h3>
                       <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider bg-muted text-muted-foreground">{result.type}</span>
                     </div>
                     <p className="text-sm text-muted-foreground leading-relaxed">{result.snippet}</p>
                   </div>
                   <div className="flex items-center pr-2">
                     <ArrowRight className="w-5 h-5 text-muted-foreground/50 group-hover:text-primary transition-colors group-hover:translate-x-1" />
                   </div>
                 </div>
               )})}
             </div>
          )}

        </div>
      )}

    </div>
  );
}
