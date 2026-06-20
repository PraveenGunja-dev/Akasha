import React, { useState, useEffect } from 'react';
import { Bell, User, ChevronDown, Moon, Sun, LogOut, Sparkles, Menu, Activity, LayoutDashboard } from 'lucide-react';
import { useNavigate, useParams } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';

export default function TopHeader({ selectedProject, setSelectedProject, masterProjects, onOpenCopilot, onToggleSidebar }: any) {
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
    <header className="h-[73px] bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800 flex items-center justify-between px-2 sm:px-4 shrink-0 z-40">
      
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
          <div className="w-8 h-8 rounded-lg bg-[#0b74b1]/10 flex items-center justify-center">
            <LayoutDashboard className="w-4 h-4 text-[#0b74b1]" />
          </div>
          <span className="font-bold text-gray-900 dark:text-white text-sm tracking-tight">Akasha Execution Platform</span>
        </div>
      </div>

      {/* Right: project selector + actions */}
      <div className="flex items-center gap-1 sm:gap-2">
        
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
              {[...(masterProjects || [])].sort((a: any, b: any) => {
                let scoreA = 0;
                if (a.p6?.id) scoreA++;
                if (a.spv_plant_code && String(a.spv_plant_code).toLowerCase() !== 'nan') scoreA++;
                if (a.tc?.has_data) scoreA++;

                let scoreB = 0;
                if (b.p6?.id) scoreB++;
                if (b.spv_plant_code && String(b.spv_plant_code).toLowerCase() !== 'nan') scoreB++;
                if (b.tc?.has_data) scoreB++;

                return scoreB - scoreA;
              }).map((proj: any, idx: number) => (
                  <option key={idx} value={proj.project_name} className="bg-background text-foreground py-2">{proj.project_name}</option>
              ))}
            </select>
            <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none group-hover:text-foreground transition-colors" />
        </div>

        {/* Ask Akasha */}
        <button 
          onClick={onOpenCopilot} 
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#0b74b1] hover:bg-[#0966a0] text-white text-[12px] font-semibold transition-colors shadow-sm shadow-[#0b74b1]/20"
        >
          <Sparkles className="w-3.5 h-3.5" />
          <span className="hidden lg:inline">Ask Akasha</span>
        </button>

        <button 
          onClick={() => setTheme(t => t === 'light' ? 'dark' : 'light')} 
          className="hidden sm:block p-2 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
        >
          {theme === 'dark' ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
        </button>

        {/* Bell */}
        <button className="relative p-2 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors">
          <Bell className="w-4 h-4" />
          <span className="absolute top-1.5 right-1.5 w-1.5 h-1.5 rounded-full bg-red-500" />
        </button>
        
        {/* Avatar */}
        <div className="relative group ml-0.5">
          <div className="w-8 h-8 rounded-full bg-gradient-to-br from-[#0b74b1] to-[#76489d] p-[1.5px] cursor-pointer">
            <div className="w-full h-full rounded-full bg-white dark:bg-gray-900 flex items-center justify-center">
               <User className="w-3.5 h-3.5 text-gray-500" />
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
