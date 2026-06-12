import React, { useState, useEffect } from 'react';
import { Search, Bell, User, Clock, Activity, ChevronDown, Moon, Sun, LogOut, Bot, Sparkles } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

export default function TopHeader({ selectedProject, setSelectedProject, masterProjects, onOpenCopilot }: any) {
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
        <div className="flex items-center gap-3 pl-2">
          {/* Ask Akasha Copilot */}
          <button 
            onClick={onOpenCopilot} 
            className="flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-gradient-to-r from-primary/10 to-purple-500/10 hover:from-primary/20 hover:to-purple-500/20 border border-primary/20 text-foreground transition-all shadow-sm group"
            title="Ask AKASHA AI"
          >
            <Sparkles className="w-4 h-4 text-primary group-hover:scale-110 transition-transform" />
            <span className="text-sm font-semibold tracking-wide bg-gradient-to-r from-primary to-purple-400 bg-clip-text text-transparent">Ask Akasha</span>
          </button>

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
          
          {/* Profile / Logout */}
          <div className="relative group ml-2">
            <div className="h-8 w-8 rounded-full bg-gradient-to-tr from-[#3B82F6] to-[#75479C] p-[2px] cursor-pointer">
              <div className="h-full w-full rounded-full bg-card flex items-center justify-center">
                 <User className="w-4 h-4 text-foreground" />
              </div>
            </div>
            
            {/* Dropdown Menu */}
            <div className="absolute right-0 top-full mt-2 w-36 bg-card border border-border rounded-md shadow-lg py-1 z-50 opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all">
               <button onClick={() => navigate('/')} className="w-full text-left px-4 py-2 text-sm text-foreground hover:bg-muted transition-colors flex items-center gap-2">
                 <LogOut className="w-4 h-4 text-red-500" />
                 <span>Logout</span>
               </button>
            </div>
          </div>
        </div>

      </div>
    </header>
  );
}
