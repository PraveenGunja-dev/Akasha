import React, { useState, useEffect } from 'react';
import { Bell, User, ChevronDown, Moon, Sun, LogOut, Sparkles, Menu, Activity, LayoutDashboard, RefreshCw } from 'lucide-react';
import { useNavigate, useParams } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';

export default function TopHeader({ selectedProject, setSelectedProject, masterProjects, onOpenCopilot, onToggleSidebar, onSyncData, isSyncing }: any) {
  const [theme, setTheme] = useState<'light' | 'dark'>('light');
  const navigate = useNavigate();
  const { projectId } = useParams();
  const { user, logout } = useAuth();

  const handleSignOut = () => {
    logout();
    navigate('/', { replace: true });
  };

  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark');
  }, [theme]);

  return (
    <header className="h-[73px] bg-background/80 backdrop-blur-xl border-b border-border/50 flex items-center justify-between px-2 sm:px-4 shrink-0 z-40">
      
      {/* Left: hamburger (mobile) & Title */}
      <div className="flex items-center gap-3 flex-1">
        <button 
          onClick={onToggleSidebar}
          className="md:hidden p-2 -ml-1 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
          aria-label="Menu"
        >
          <Menu className="w-5 h-5" />
        </button>
        <div className="hidden md:flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-sky-500/10 flex items-center justify-center border border-sky-500/20 shadow-[0_0_10px_rgba(14,165,233,0.15)]">
            <LayoutDashboard className="w-4 h-4 text-sky-500" />
          </div>
          <span className="font-bold text-foreground text-sm tracking-tight">Akasha Execution Platform</span>
        </div>
      </div>

      {/* Right: project selector + actions */}
      <div className="flex items-center gap-1 sm:gap-2">
        
        {/* Project Selector - Removed per request */}

        {/* Sync Data Button */}
        {onSyncData && (
          <button 
            onClick={onSyncData}
            disabled={isSyncing}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-sky-500/20 bg-background hover:bg-sky-500/5 text-foreground text-[12px] font-semibold transition-colors shadow-sm mr-2 ${isSyncing ? 'opacity-50 cursor-not-allowed' : ''}`}
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isSyncing ? 'animate-spin text-sky-500' : ''}`} />
            <span className="hidden lg:inline">{isSyncing ? 'Syncing...' : 'Sync All Data'}</span>
          </button>
        )}

        {/* Ask Akasha */}
        <button 
          onClick={onOpenCopilot} 
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-sky-500 hover:bg-sky-400 text-white text-[12px] font-semibold transition-colors shadow-[0_0_15px_rgba(14,165,233,0.3)] border border-sky-400/50"
        >
          <Sparkles className="w-3.5 h-3.5" />
          <span className="hidden lg:inline text-shadow-sm">Ask Akasha</span>
        </button>

        <button 
          onClick={() => setTheme(t => t === 'light' ? 'dark' : 'light')} 
          className="hidden sm:block p-2 rounded-lg text-muted-foreground hover:text-foreground hover:bg-black/5 dark:hover:bg-white/5 transition-colors"
        >
          {theme === 'dark' ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
        </button>

        {/* Bell */}
        <button className="relative p-2 rounded-lg text-muted-foreground hover:text-foreground hover:bg-black/5 dark:hover:bg-white/5 transition-colors">
          <Bell className="w-4 h-4" />
          <span className="absolute top-1.5 right-1.5 w-1.5 h-1.5 rounded-full bg-red-500 shadow-[0_0_5px_rgba(239,68,68,0.5)]" />
        </button>
        
        {/* Avatar */}
        <div className="relative group ml-0.5">
          <div className="w-8 h-8 rounded-full bg-gradient-to-br from-sky-400 to-purple-500 p-[1.5px] cursor-pointer shadow-[0_0_10px_rgba(14,165,233,0.2)]">
            <div className="w-full h-full rounded-full bg-background flex items-center justify-center">
               <User className="w-3.5 h-3.5 text-muted-foreground" />
            </div>
          </div>
          <div className="absolute right-0 top-full mt-1.5 w-44 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg shadow-lg py-1 z-50 opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all origin-top-right scale-95 group-hover:scale-100">
             <div className="px-3 py-2 border-b border-gray-100 dark:border-gray-800">
               <p className="text-[12px] font-semibold text-gray-900 dark:text-white">{user?.display_name || 'User'}</p>
               <p className="text-[11px] text-gray-400 truncate">{user?.role || 'executive'}</p>
             </div>
             <button onClick={handleSignOut} className="w-full text-left px-3 py-1.5 text-[12px] text-red-600 hover:bg-red-50 dark:hover:bg-red-900/10 transition-colors flex items-center gap-1.5">
               <LogOut className="w-3.5 h-3.5" />
               Sign Out
             </button>
          </div>
        </div>
      </div>
    </header>
  );
}
