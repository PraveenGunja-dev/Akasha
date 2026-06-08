import React, { useState, useEffect } from 'react';
import { Search, Bell, User, Clock, Activity, ChevronDown, Moon, Sun, Home } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

export default function TopHeader({ selectedProject, setSelectedProject, masterProjects }: any) {
  const [theme, setTheme] = useState<'light' | 'dark'>('light');
  const navigate = useNavigate();

  useEffect(() => {
    if (theme === 'dark') {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  }, [theme]);

  const toggleTheme = () => {
    setTheme(theme === 'light' ? 'dark' : 'light');
  };

  return (
    <header className="h-[72px] bg-card border-b border-border flex items-center justify-between px-6 shrink-0 z-10 shadow-sm">
      
      {/* Left side: Global Search */}
      <div className="flex-1 max-w-md">
        <div className="relative group">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500 group-focus-within:text-[#3B82F6] transition-colors" />
          <input 
            type="text" 
            placeholder="Search projects, risks, or ask AI..." 
            className="w-full bg-muted border border-border focus:border-primary/50 rounded-lg py-2 pl-10 pr-4 text-sm text-foreground placeholder-muted-foreground/70 focus:outline-none focus:ring-1 focus:ring-primary/50 transition-all shadow-inner"
          />
          <div className="absolute right-3 top-1/2 -translate-y-1/2 flex gap-1">
             <kbd className="hidden sm:inline-block bg-background border border-border rounded px-1.5 text-[10px] text-muted-foreground font-mono">⌘</kbd>
             <kbd className="hidden sm:inline-block bg-background border border-border rounded px-1.5 text-[10px] text-muted-foreground font-mono">K</kbd>
          </div>
        </div>
      </div>

      {/* Center/Right: Project Selector & Status */}
      <div className="flex items-center gap-6">
        
        {/* Connected Systems Status */}
        <div className="hidden lg:flex items-center gap-4 text-xs font-medium text-muted-foreground border-r border-border pr-6">
           <div className="flex items-center gap-1.5">
             <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 shadow-[0_0_5px_theme(colors.emerald.500)]"></div>
             P6
           </div>
           <div className="flex items-center gap-1.5">
             <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 shadow-[0_0_5px_theme(colors.emerald.500)]"></div>
             SAP
           </div>
           <div className="flex items-center gap-1.5 opacity-50">
             <div className="w-1.5 h-1.5 rounded-full bg-muted-foreground"></div>
             ENG
           </div>
            <div className="flex items-center gap-1.5 ml-2 text-[10px] text-muted-foreground/70">
             <Activity className="w-3 h-3 text-emerald-500" /> Real-time Data
           </div>
        </div>

        {/* Project Selector */}
        <div className="flex items-center gap-2 bg-muted border border-border hover:border-muted-foreground rounded-lg px-3 py-1.5 transition-colors cursor-pointer relative group">
           <div className="w-5 h-5 rounded bg-[#3B82F6]/20 flex items-center justify-center">
             <Activity className="w-3 h-3 text-[#3B82F6]" />
           </div>
           <select 
              value={selectedProject}
              onChange={(e) => setSelectedProject(e.target.value)}
              className="appearance-none bg-transparent text-sm font-semibold text-foreground focus:outline-none pr-6 cursor-pointer max-w-[150px] truncate"
            >
              <option value="All" className="bg-background text-foreground py-2">Global Portfolio</option>
              {masterProjects.map((proj: string) => (
                  <option key={proj} value={proj} className="bg-background text-foreground py-2">{proj}</option>
              ))}
            </select>
            <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none group-hover:text-foreground transition-colors" />
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2 pl-2">
          {/* Theme Toggle */}
          <button 
            onClick={toggleTheme} 
            className="p-2 rounded-full hover:bg-accent text-muted-foreground hover:text-accent-foreground transition-colors"
            title={theme === 'dark' ? 'Switch to Light Mode' : 'Switch to Dark Mode'}
          >
            {theme === 'dark' ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
          </button>

          {/* Notifications */}
          <button className="relative p-2 rounded-full hover:bg-accent text-muted-foreground hover:text-accent-foreground transition-colors">
            <Bell className="w-5 h-5" />
            <span className="absolute top-1 right-1.5 w-2 h-2 rounded-full bg-[#EF4444] border-2 border-card"></span>
          </button>

          {/* Home */}
          <button 
            onClick={() => navigate('/')} 
            className="p-2 rounded-full hover:bg-accent text-muted-foreground hover:text-accent-foreground transition-colors"
            title="Back to Home"
          >
            <Home className="w-5 h-5" />
          </button>
          
          <div className="h-8 w-8 rounded-full bg-gradient-to-tr from-[#3B82F6] to-[#75479C] p-[2px] cursor-pointer">
            <div className="h-full w-full rounded-full bg-card flex items-center justify-center">
               <User className="w-4 h-4 text-foreground" />
            </div>
          </div>
        </div>

      </div>
    </header>
  );
}
