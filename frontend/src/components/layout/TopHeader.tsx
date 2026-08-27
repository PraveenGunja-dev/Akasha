import React, { useState, useEffect, useRef } from 'react';
import { Bell, User, ChevronDown, Moon, Sun, LogOut, Sparkles, Menu, Activity, LayoutDashboard, RefreshCw, BookOpen } from 'lucide-react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { toast } from 'sonner';
import NotificationDropdown from './NotificationDropdown';
import PMAGThreadPanel from './PMAGThreadPanel';

export default function TopHeader({ selectedProject, setSelectedProject, masterProjects, onOpenCopilot, onToggleSidebar, onSyncData, isSyncing, onNavigateToSimulation }: any) {
  const [theme, setTheme] = useState<'light' | 'dark'>('light');
  const navigate = useNavigate();
  const { projectId } = useParams();
  const { user, logout } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const currentPortfolio = searchParams.get('portfolio') || 'All Portfolios';
  const currentPhase = searchParams.get('phase') || 'Ongoing';
  const [isPortfolioOpen, setIsPortfolioOpen] = useState(false);
  const [isPhaseOpen, setIsPhaseOpen] = useState(false);

  const [notifications, setNotifications] = useState<any[]>([]);
  const [hasMoreNotifs, setHasMoreNotifs] = useState(true);
  const [showNotifications, setShowNotifications] = useState(false);
  const [selectedNotification, setSelectedNotification] = useState<any | null>(null);
  const notificationRef = useRef<HTMLDivElement>(null);
  const portfolioRef = useRef<HTMLDivElement>(null);
  const phaseRef = useRef<HTMLDivElement>(null);
  const LIMIT = 50;

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (notificationRef.current && !notificationRef.current.contains(event.target as Node)) {
        setShowNotifications(false);
      }
      if (portfolioRef.current && !portfolioRef.current.contains(event.target as Node)) {
        setIsPortfolioOpen(false);
      }
      if (phaseRef.current && !phaseRef.current.contains(event.target as Node)) {
        setIsPhaseOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);
  const unreadCount = notifications.filter(n => n.action_status === 'Pending').length;

  const fetchNotifications = async (reset = false) => {
    try {
      const currentSkip = reset ? 0 : notifications.length;
      let url = `/akasha/api/notifications/?skip=${currentSkip}&limit=${LIMIT}`;
      if (projectId) url += `&project_id=${projectId}`;
      if (currentPhase && currentPhase !== 'ALL') url += `&phase=${currentPhase}`;
      const res = await fetch(url);
      if (res.ok) {
        const data = await res.json();
        if (data.length < LIMIT) setHasMoreNotifs(false);
        else setHasMoreNotifs(true);
        setNotifications(prev => reset ? data : [...prev, ...data]);
      }
    } catch (e) {
      console.error('Failed to fetch notifications:', e);
    }
  };

  const loadMoreNotifications = () => {
    fetchNotifications(false);
  };

  useEffect(() => {
    fetchNotifications(true);
    const interval = setInterval(() => fetchNotifications(true), 60000);
    return () => clearInterval(interval);
  }, [projectId, currentPhase]);

  const handleSignOut = () => {
    logout();
    navigate('/', { replace: true });
  };

  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark');
  }, [theme]);

  return (
    <>
    <header className="h-[73px] bg-card border-b border-border dark:border-border shadow-sm flex items-center justify-between px-4 shrink-0 z-40">
      
      {/* Left: hamburger (mobile) & Title */}
      <div className="flex items-center gap-3 flex-1">
        <button 
          onClick={onToggleSidebar}
          className="md:hidden p-2 -ml-1 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
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
        
        {/* Phase Dropdown */}
        <div 
          className="relative mr-1"
          ref={phaseRef}
        >
          <button 
            onClick={() => setIsPhaseOpen(!isPhaseOpen)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border dark:border-gray-700 bg-card hover:bg-muted dark:hover:bg-gray-700/50 text-foreground text-[12px] font-semibold transition-colors shadow-sm"
          >
            <span>{currentPhase === 'ALL' ? 'All Phases' : currentPhase}</span>
            <ChevronDown className={`w-3.5 h-3.5 text-muted-foreground transition-transform ${isPhaseOpen ? 'rotate-180' : ''}`} />
          </button>
          <div className={`absolute top-full right-0 mt-1 w-36 py-1 bg-card rounded-lg shadow-lg border border-muted dark:border-gray-700 transition-all z-50 ${isPhaseOpen ? 'opacity-100 visible translate-y-0' : 'opacity-0 invisible -translate-y-2'}`}>
            {['Ongoing', 'Commissioned', 'ALL'].map(p => (
              <button
                key={p}
                onClick={() => {
                  setSearchParams(prev => {
                    if (p === 'Ongoing') {
                      prev.delete('phase'); // Ongoing is default
                    } else {
                      prev.set('phase', p);
                    }
                    return prev;
                  });
                  setIsPhaseOpen(false);
                }}
                className={`w-full text-left px-4 py-2 text-[12px] transition-colors ${currentPhase === p ? 'bg-sky-50 dark:bg-sky-500/10 text-sky-600 dark:text-sky-400 font-bold' : 'text-foreground dark:text-muted-foreground hover:bg-muted dark:hover:bg-gray-700/50'}`}
              >
                {p === 'ALL' ? 'All Phases' : p}
              </button>
            ))}
          </div>
        </div>

        {/* Portfolio Dropdown */}
        <div 
          className="relative mr-2"
          ref={portfolioRef}
        >
          <button 
            onClick={() => setIsPortfolioOpen(!isPortfolioOpen)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border dark:border-gray-700 bg-card hover:bg-muted dark:hover:bg-gray-700/50 text-foreground text-[12px] font-semibold transition-colors shadow-sm"
          >
            <span>{currentPortfolio === 'All Portfolios' ? 'All Portfolios' : currentPortfolio}</span>
            <ChevronDown className={`w-3.5 h-3.5 text-muted-foreground transition-transform ${isPortfolioOpen ? 'rotate-180' : ''}`} />
          </button>
          <div className={`absolute top-full right-0 mt-1 w-48 py-1 bg-card rounded-lg shadow-lg border border-muted dark:border-gray-700 transition-all z-50 ${isPortfolioOpen ? 'opacity-100 visible translate-y-0' : 'opacity-0 invisible -translate-y-2'}`}>
            {['All Portfolios', 'Solar Khavda', 'Solar Rajasthan', 'Wind', 'BESS'].map(p => (
              <button
                key={p}
                onClick={() => {
                  setSearchParams(prev => {
                    if (p === 'All Portfolios') {
                      prev.delete('portfolio');
                    } else {
                      prev.set('portfolio', p);
                    }
                    return prev;
                  });
                  setIsPortfolioOpen(false);
                }}
                className={`w-full text-left px-4 py-2 text-[12px] transition-colors ${currentPortfolio === p ? 'bg-sky-50 dark:bg-sky-500/10 text-sky-600 dark:text-sky-400 font-bold' : 'text-foreground dark:text-muted-foreground hover:bg-muted dark:hover:bg-gray-700/50'}`}
              >
                {p}
              </button>
            ))}
          </div>
        </div>

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

        {/* Ask Akasha 
        <button 
          onClick={onOpenCopilot} 
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-sky-500 hover:bg-sky-400 text-white text-[12px] font-semibold transition-colors shadow-[0_0_15px_rgba(14,165,233,0.3)] border border-sky-400/50"
        >
          <Sparkles className="w-3.5 h-3.5" />
          <span className="hidden lg:inline text-shadow-sm">Ask Akasha</span>
        </button>
        */}

        {/* User Guide */}
        <a 
          href="/AKASHA_USER_GUIDE.docx" 
          download
          className="flex items-center gap-1.5 px-3 py-1.5 mr-2 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-white text-[12px] font-semibold transition-colors shadow-sm"
        >
          <BookOpen className="w-3.5 h-3.5" />
          <span className="hidden lg:inline text-shadow-sm">User Guide</span>
        </a>

        <button 
          onClick={() => setTheme(t => t === 'light' ? 'dark' : 'light')} 
          className="hidden sm:block p-2 rounded-lg text-muted-foreground hover:text-foreground hover:bg-black/5 dark:hover:bg-white/5 transition-colors"
        >
          {theme === 'dark' ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
        </button>

        {/* Bell */}
        <div className="relative" ref={notificationRef}>
            <button onClick={() => setShowNotifications(!showNotifications)} className="relative p-2 rounded-lg text-muted-foreground hover:text-foreground hover:bg-black/5 dark:hover:bg-white/5 transition-colors">
            <Bell className="w-4 h-4" />
            {unreadCount > 0 && <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-red-500 ring-[1.5px] ring-background" />}
            </button>
            
            {showNotifications && (
                <NotificationDropdown 
                    notifications={notifications}
                    onClose={() => setShowNotifications(false)}
                    onLoadMore={loadMoreNotifications}
                    hasMore={hasMoreNotifs}
                    onSimulate={(projId: string, context?: any) => {
                        setShowNotifications(false);
                        if (onNavigateToSimulation) onNavigateToSimulation(projId, context);
                    }}
                />
            )}
        </div>
        
        {/* Avatar */}
        <div className="relative group ml-0.5">
          <div className="w-8 h-8 rounded-full bg-gradient-to-br from-sky-400 to-purple-500 p-[1.5px] cursor-pointer shadow-[0_0_10px_rgba(14,165,233,0.2)]">
            <div className="w-full h-full rounded-full bg-background flex items-center justify-center">
               <User className="w-3.5 h-3.5 text-muted-foreground" />
            </div>
          </div>
          <div className="absolute right-0 top-full mt-1.5 w-44 bg-card border border-border dark:border-border rounded-lg shadow-lg py-1 z-50 opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all origin-top-right scale-95 group-hover:scale-100">
             <div className="px-3 py-2 border-b border-muted dark:border-border">
               <p className="text-[12px] font-semibold text-foreground dark:text-white">{user?.display_name || 'User'}</p>
               <p className="text-[11px] text-muted-foreground truncate">{user?.role || 'executive'}</p>
             </div>
             <button onClick={handleSignOut} className="w-full text-left px-3 py-1.5 text-[12px] text-destructive hover:bg-destructive/10 dark:hover:bg-red-900/10 transition-colors flex items-center gap-1.5">
               <LogOut className="w-3.5 h-3.5" />
               Sign Out
             </button>
          </div>
        </div>
      </div>
    </header>

    {selectedNotification && (
      <PMAGThreadPanel 
        notification={selectedNotification} 
        onClose={() => setSelectedNotification(null)}
        onResolved={() => {
          fetchNotifications();
          setSelectedNotification(null);
        }}
      />
    )}
    </>
  );
}
