import { useTheme } from '../../hooks/useTheme';
import React, { useState, useEffect, useRef } from 'react';
import { Bell, ChevronDown, Moon, Sun, Sparkles, Menu, Activity, RefreshCw, BookOpen, FlaskConical } from 'lucide-react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import DashboardSwitcher from '../auth/DashboardSwitcher';
import { toast } from 'sonner';
import NotificationDropdown from './NotificationDropdown';
import PMAGThreadPanel from './PMAGThreadPanel';

/* The portfolio / phase filters live in the URL, and any link that navigates to
   a bare path dropped them - the header then read "Ongoing / All Portfolios"
   again. The last choice is kept here and put back when a page opens without
   it. Choosing the defaults explicitly is stored too, so it is never mistaken
   for a dropped filter; a URL that carries filters (a shared link) wins. */
const FILTER_KEY = 'akasha.filters';
type StoredFilters = { portfolio?: string; phase?: string };
const readFilters = (): StoredFilters => {
  try { return JSON.parse(localStorage.getItem(FILTER_KEY) || '{}') || {}; } catch { return {}; }
};
const writeFilters = (patch: StoredFilters) => {
  try { localStorage.setItem(FILTER_KEY, JSON.stringify({ ...readFilters(), ...patch })); } catch { /* storage unavailable */ }
};

/* betaToggle is passed only on pages that have a Beta copy (the Ordering
   Schedule); without it the button is not rendered. */
export default function TopHeader({ selectedProject, setSelectedProject, masterProjects, onOpenCopilot, onToggleSidebar, onSyncData, isSyncing, onNavigateToSimulation, betaToggle }: any) {
  const [theme, , toggleTheme] = useTheme();
  const navigate = useNavigate();
  const { projectId } = useParams();
  const { user } = useAuth();
  const portfolioOptions = user?.portfolio_access.all === false
    ? user.portfolio_access.clusters
    : ['All Portfolios', ...(user?.portfolio_access.clusters ?? [])];
  const [searchParams, setSearchParams] = useSearchParams();
  const currentPortfolio = searchParams.get('portfolio') || (user?.portfolio_access.all === false ? user.portfolio_access.clusters[0] ?? '' : 'All Portfolios');
  const currentPhase = searchParams.get('phase') || 'Ongoing';

  useEffect(() => {
    const urlPortfolio = searchParams.get('portfolio');
    const urlPhase = searchParams.get('phase');
    const saved = readFilters();
    const restorePortfolio = !urlPortfolio && saved.portfolio && saved.portfolio !== 'All Portfolios';
    const restorePhase = !urlPhase && saved.phase && saved.phase !== 'Ongoing';
    if (restorePortfolio || restorePhase) {
      setSearchParams(prev => {
        if (restorePortfolio) prev.set('portfolio', saved.portfolio as string);
        if (restorePhase) prev.set('phase', saved.phase as string);
        return prev;
      }, { replace: true });
      return;
    }
    // The URL is the truth from here (including a shared link); remember it.
    writeFilters({ portfolio: urlPortfolio || 'All Portfolios', phase: urlPhase || 'Ongoing' });
  }, [searchParams, setSearchParams]);
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


  useEffect(() => {
  }, [theme]);

  return (
    <>
    <header className="h-[73px] bg-card border-b border-border shadow-sm flex items-center justify-between px-5 shrink-0 z-40">
      
      {/* Left: hamburger (mobile) & Title */}
      <div className="flex items-center gap-3 flex-1">
        <button 
          onClick={onToggleSidebar}
          className="md:hidden p-2 -ml-1 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
          aria-label="Menu"
        >
          <Menu className="w-5 h-5" />
        </button>
      </div>

      {/* Right: project selector + actions */}
      <div className="flex items-center gap-1 sm:gap-2">

        {/* Beta toggle - Ordering Schedule only */}
        {betaToggle && (
          <button
            type="button"
            onClick={betaToggle.onToggle}
            aria-pressed={betaToggle.active}
            title={betaToggle.active ? 'Back to the live Ordering Schedule' : 'Open the Beta Ordering Schedule'}
            className={`flex items-center gap-1.5 px-3 py-1.5 mr-1 rounded-lg border text-[12px] font-semibold transition-colors shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-blue/50 ${betaToggle.active ? 'border-primary-400 bg-primary-100 text-primary-700' : 'border-border bg-card hover:bg-muted text-foreground'}`}
          >
            <FlaskConical className="w-3.5 h-3.5" />
            <span>Beta</span>
          </button>
        )}

        {/* Phase Dropdown */}
        <div 
          className="relative mr-1"
          ref={phaseRef}
        >
          <button 
            onClick={() => setIsPhaseOpen(!isPhaseOpen)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border bg-card hover:bg-muted text-foreground text-[12px] font-semibold transition-colors shadow-sm"
          >
            <span>{currentPhase === 'ALL' ? 'All Phases' : currentPhase}</span>
            <ChevronDown className={`w-3.5 h-3.5 text-muted-foreground transition-transform ${isPhaseOpen ? 'rotate-180' : ''}`} />
          </button>
          <div className={`absolute top-full right-0 mt-1 w-36 py-1 bg-card rounded-lg shadow-lg border border-border transition-all z-50 ${isPhaseOpen ? 'opacity-100 visible translate-y-0' : 'opacity-0 invisible -translate-y-2'}`}>
            {['Ongoing', 'Commissioned', 'ALL'].map(p => (
              <button
                key={p}
                onClick={() => {
                  writeFilters({ phase: p });
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
                className={`w-full text-left px-4 py-2 text-[12px] transition-colors ${currentPhase === p ? 'bg-primary-100 text-primary-700 font-bold' : 'text-foreground hover:bg-muted'}`}
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
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border bg-card hover:bg-muted text-foreground text-[12px] font-semibold transition-colors shadow-sm"
          >
            <span>{currentPortfolio === 'All Portfolios' ? 'All Portfolios' : currentPortfolio}</span>
            <ChevronDown className={`w-3.5 h-3.5 text-muted-foreground transition-transform ${isPortfolioOpen ? 'rotate-180' : ''}`} />
          </button>
          <div className={`absolute top-full right-0 mt-1 w-48 py-1 bg-card rounded-lg shadow-lg border border-border transition-all z-50 ${isPortfolioOpen ? 'opacity-100 visible translate-y-0' : 'opacity-0 invisible -translate-y-2'}`}>
            {portfolioOptions.map(p => (
              <button
                key={p}
                onClick={() => {
                  writeFilters({ portfolio: p });
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
                className={`w-full text-left px-4 py-2 text-[12px] transition-colors ${currentPortfolio === p ? 'bg-primary-100 text-primary-700 font-bold' : 'text-foreground hover:bg-muted'}`}
              >
                {p}
              </button>
            ))}
          </div>
        </div>

        {/* Sync Data Button */}
        {onSyncData && user?.permissions.includes('data.sync') && (
          <button 
            onClick={onSyncData}
            disabled={isSyncing}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-primary-200 bg-card hover:bg-primary-50 text-foreground text-[12px] font-semibold transition-colors shadow-sm mr-2 ${isSyncing ? 'opacity-50 cursor-not-allowed' : ''}`}
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isSyncing ? 'animate-spin text-sky-500' : ''}`} />
            <span className="hidden lg:inline">{isSyncing ? 'Syncing...' : 'Sync All Data'}</span>
          </button>
        )}

        {/* Ask Akasha */}
        <button 
          onClick={onOpenCopilot} 
          className="flex items-center gap-1.5 px-3 py-1.5 mr-2 rounded-lg text-white text-[12px] font-semibold transition-all shadow-md hover:shadow-lg border border-primary-400/50 hover:scale-[1.02] active:scale-[0.98]"
          style={{ background: 'var(--linearPrimarySecondary)' }}
          title="Ask Akasha — Project Intelligence AI Copilot"
        >
          <Sparkles className="w-3.5 h-3.5 animate-pulse" />
          <span className="hidden lg:inline text-shadow-sm">Ask Akasha</span>
        </button>

        {/* User Guide */}
        <a 
          href="/AKASHA_USER_GUIDE.docx" 
          download
          className="flex items-center gap-1.5 px-3 py-1.5 mr-2 rounded-lg bg-status-healthy text-white text-[12px] font-semibold transition-colors shadow-sm hover:opacity-90"
        >
          <BookOpen className="w-3.5 h-3.5" />
          <span className="hidden lg:inline text-shadow-sm">User Guide</span>
        </a>

        <button 
          onClick={toggleTheme} 
          className="hidden sm:block p-2 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
        >
          {theme === 'dark' ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
        </button>

        {/* Bell */}
        <div className="relative" ref={notificationRef}>
            <button onClick={() => setShowNotifications(!showNotifications)} className="relative p-2 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors">
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
        
        {/* Account & dashboard switcher */}
        <div className="ml-1"><DashboardSwitcher /></div>
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
