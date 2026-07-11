import { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { motion, AnimatePresence } from 'framer-motion';
import ReactECharts from 'echarts-for-react';
import {
  Home, Activity, TrendingUp, AlertTriangle, Layers, Wifi, Bell,
  Search, ChevronLeft, ChevronRight, LogOut, RefreshCw,
  Zap, X, Menu, LayoutDashboard, CheckCircle2, Clock,
  Calendar, XCircle, ArrowUpRight, ArrowDownRight, Minus, Shield,
  Moon, Sun, User, Sparkles, Network, FileText, BrainCircuit
} from 'lucide-react';
import ScenarioSimulationPanel from '../components/layout/ScenarioSimulationPanel';
import DataIntegrationHub from '../features/analytics/DataIntegrationHub';
import TransmissionDataViewer from '../features/analytics/TransmissionDataViewer';
import ReportsInsights from '../features/analytics/ReportsInsights';
import SmartSearch from '../features/analytics/SmartSearch';
import ProjectMap from '../features/projects/ProjectMap';
import ExecutiveBriefing from '../features/dashboard/ExecutiveBriefing';
import PortfolioHealth from '../features/dashboard/PortfolioHealth';
import Project360 from '../features/projects/Project360';
import RiskCommandCenter from '../features/dashboard/RiskCommandCenter';
import CapacityOverview from '../features/dashboard/CapacityOverview';

import PMAGOverview from './pmag/PMAGOverview';
import PMAGDPRTracker from './pmag/PMAGDPRTracker';
import GridStatus from './pmag/GridStatus';
import ReportsAnalytics from './pmag/ReportsAnalytics';
import TeamManagement from './pmag/TeamManagement';
import SiteMonitoring from './pmag/SiteMonitoring';
import ProjectWorkspace from '../features/projects/ProjectWorkspace';

interface DashboardData {
  summary: {
    total_projects: number; on_track: number; at_risk: number; delayed: number;
    avg_completion: number; milestones_due_this_week: number; milestones_overdue: number;
  };
  project_health: any[];
  sv_chart: any[];
  critical_path: any[];
  dpr_tracker: any[];
  connectivity: any[];
  alerts: any[];
}

export default function PMAGDashboard() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [collapsed, setCollapsed] = useState(false);
  const [activeSection, setActiveSection] = useState(() => {
    return sessionStorage.getItem('pmagActiveSection') || 'overview';
  });
  const [previousSection, setPreviousSection] = useState('overview');
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [theme, setTheme] = useState<'light' | 'dark'>('light');
  const [isMobileOpen, setIsMobileOpen] = useState(false);
  const [isCopilotOpen, setIsCopilotOpen] = useState(false);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [searchParams] = useSearchParams();
  const portfolio = searchParams.get('portfolio');

  // Additional data for integrated AI/Report components
  const [dashboardData, setDashboardData] = useState<any>(null);
  const [p6Data, setP6Data] = useState<any[]>([]);
  const [sapData, setSapData] = useState<any[]>([]);
  const [finDetails, setFinDetails] = useState<any[]>([]);

  const [reportsData, setReportsData] = useState<any>(null);
  const [teamData, setTeamData] = useState<any>(null);
  const [siteMonitoringData, setSiteMonitoringData] = useState<any>(null);
  const [isSyncing, setIsSyncing] = useState(false);

  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark');
  }, [theme]);

  const loadAllData = () => {
    setLoading(true);
    const portfolioQuery = portfolio ? `?portfolio=${encodeURIComponent(portfolio)}` : '';
    
    fetch(`/akasha/api/pmag/dashboard${portfolioQuery}`)
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));

    // Fetch data for the integrated deep-dive modules
    Promise.all([
      fetch(`/akasha/api/dashboard/summary${portfolioQuery}`),
      fetch(`/akasha/api/summary${portfolioQuery}`),
      fetch(`/akasha/api/financials${portfolioQuery}`),
      fetch(`/akasha/api/financials/details${portfolioQuery}`)
    ]).then(async ([dashRes, p6Res, sapRes, finDetRes]) => {
      setDashboardData(await dashRes.json());
      setP6Data(await p6Res.json());
      setSapData(await sapRes.json());
      setFinDetails(await finDetRes.json());
    }).catch(console.error);

    Promise.all([
      fetch(`/akasha/api/pmag/reports${portfolioQuery}`),
      fetch(`/akasha/api/pmag/team${portfolioQuery}`),
      fetch(`/akasha/api/pmag/site-monitoring${portfolioQuery}`)
    ]).then(async ([repRes, teamRes, siteRes]) => {
      setReportsData(await repRes.json());
      setTeamData(await teamRes.json());
      setSiteMonitoringData(await siteRes.json());
    }).catch(console.error);
  };

  useEffect(() => {
    loadAllData();
  }, [portfolio]);

  const handleSyncData = async () => {
    setIsSyncing(true);
    try {
      await Promise.allSettled([
        fetch('/akasha/api/sharepoint/sync', { method: 'POST' }),
        fetch('/akasha/api/tc/sync', { method: 'POST' }),
        fetch('/akasha/api/mapping/sync', { method: 'POST' }),
        fetch('/akasha/api/p6/sync', { method: 'POST' }),
        fetch('/akasha/api/capacity/sync', { method: 'POST' })
      ]);
    } catch (error) {
      console.error("Sync failed:", error);
    }
    loadAllData();
    setIsSyncing(false);
  };

  const handleLogout = () => { logout(); navigate('/', { replace: true }); };

  // ─── Sidebar Groups ───
  const sidebarGroups = [
    {
      title: "DASHBOARD",
      items: [
        { id: 'overview', label: 'Portfolio', icon: Home },
        { id: 'site_monitoring', label: 'Site Monitoring', icon: Activity },
        { id: 'grid_status', label: 'Grid Status', icon: Network },
      ]
    },
    {
      title: "DATA & INSIGHTS",
      items: [
        { id: 'executive_brief', label: 'Briefing', icon: FileText },
        { id: 'smart_search', label: 'Search', icon: Search },
        { id: 'project_map', label: 'Project Map', icon: BrainCircuit },
      ]
    },
    {
      title: "ADMINISTRATION",
      items: [
        { id: 'reports', label: 'Reports', icon: FileText },
        { id: 'team', label: 'Team', icon: User },
      ]
    }
  ];

  // ─── Sidebar Component (matches LeftSidebar.tsx style) ───
  const showLabel = !collapsed || isMobileOpen;

  const NavItem = ({ item }: { item: { id: string, label: string, icon: any } }) => {
    const isActive = activeSection === item.id;
    return (
      <div className="relative group/nav">
        {collapsed && !isMobileOpen && (
          <div className="absolute left-full ml-2 top-1/2 -translate-y-1/2 px-2.5 py-1 rounded-md bg-slate-800 text-white text-[11px] font-medium whitespace-nowrap opacity-0 pointer-events-none group-hover/nav:opacity-100 transition-opacity z-[60] shadow-lg">
            {item.label}
          </div>
        )}
        <button
          onClick={() => {
            if (item.id === 'ai_copilot') {
              setIsCopilotOpen(true);
            } else {
              setPreviousSection(activeSection);
              setActiveSection(item.id);
              setSelectedProjectId(null); // Clear selected project when navigating sidebar
              sessionStorage.setItem('pmagActiveSection', item.id);
              if (isMobileOpen) setIsMobileOpen(false);
            }
          }}
          className={`w-full flex items-center gap-2.5 rounded-lg text-[13px] font-medium transition-all duration-150
            ${collapsed && !isMobileOpen ? 'justify-center p-2.5' : 'px-3 py-2'}
            ${isActive && item.id !== 'ai_copilot'
              ? 'bg-[#0b74b1] text-white shadow-sm shadow-[#0b74b1]/25'
              : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-900 dark:hover:text-white'
            }`}
        >
          <item.icon className={`w-[18px] h-[18px] shrink-0 transition-colors ${isActive ? 'text-white' : 'text-slate-400 group-hover/nav:text-slate-600 dark:group-hover/nav:text-slate-300'}`} />
          {showLabel && <span className="truncate leading-none">{item.label}</span>}
        </button>
      </div>
    );
  };

  const sidebarInner = (
    <div className="flex flex-col h-full">
      {/* Brand Bar */}
      <div className={`flex items-center shrink-0 border-b border-slate-100 dark:border-slate-800 h-[73px] ${collapsed && !isMobileOpen ? 'justify-center px-2' : 'px-4 justify-between'}`}>
        <div className="flex items-center overflow-hidden">
          {!showLabel && (
            <span className="text-[22px] font-heading font-black tracking-tighter leading-none uppercase bg-gradient-to-r from-[#0b74b1] via-[#76489d] to-[#bc3860] text-transparent bg-clip-text mx-auto">A</span>
          )}
          {showLabel && (
            <div className="flex flex-col min-w-0 py-1">
              <span className="text-[24px] font-heading font-black tracking-tighter leading-none uppercase bg-gradient-to-r from-[#0b74b1] via-[#76489d] to-[#bc3860] text-transparent bg-clip-text">AKASHA</span>
              <span className="text-[9px] font-bold text-[#0b74b1] uppercase tracking-[0.25em] mt-0.5">PMAG Dashboard</span>
            </div>
          )}
        </div>
        {isMobileOpen && (
          <button onClick={() => setIsMobileOpen(false)} className="md:hidden p-1 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 rounded">
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* Nav items */}
      <nav className="flex-1 overflow-y-auto custom-scrollbar px-2.5 py-3 flex flex-col gap-5">
        {sidebarGroups.map((group, groupIdx) => (
          <div key={groupIdx} className="flex flex-col gap-0.5">
            {showLabel && (
              <h3 className="px-3 mb-1.5 text-[10px] font-bold uppercase tracking-[0.15em] text-slate-400 dark:text-slate-500">
                {group.title}
              </h3>
            )}
            {group.items.map(item => <NavItem key={item.id} item={item} />)}
          </div>
        ))}

        {/* Bottom section */}
        <div className="flex flex-col gap-0.5 mt-auto pt-3 border-t border-slate-100 dark:border-slate-800">
          {showLabel && (
            <div className="px-3 py-1.5 mb-1">
              <p className="text-[12px] font-bold text-slate-900 dark:text-white truncate">{user?.display_name}</p>
              <p className="text-[10px] text-slate-400 font-medium uppercase tracking-wider">{user?.role}</p>
            </div>
          )}
          <button onClick={handleLogout} className={`w-full flex items-center gap-2 rounded-lg text-[12px] font-medium text-slate-500 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors ${collapsed && !isMobileOpen ? 'justify-center p-2.5' : 'px-3 py-2'}`}>
            <LogOut className="w-4 h-4" />
            {showLabel && <span>Sign Out</span>}
          </button>
        </div>
      </nav>

      {/* Collapse toggle */}
      <div className="hidden md:flex shrink-0 border-t border-slate-100 dark:border-slate-800 px-2.5 py-2">
        <button onClick={() => setCollapsed(!collapsed)} className="w-full flex items-center justify-center gap-2 py-1.5 rounded-lg text-slate-400 dark:text-slate-500 hover:text-slate-600 dark:hover:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors text-xs font-medium">
          {collapsed ? <ChevronRight className="w-4 h-4" /> : (<><ChevronLeft className="w-4 h-4" /><span>Collapse</span></>)}
        </button>
      </div>
    </div>
  );

  if (loading || !data) {
    return (
      <div className="min-h-screen bg-[var(--background)] flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <div className="w-10 h-10 border-3 border-[#0b74b1] border-t-transparent rounded-full animate-spin" />
          <p className="text-sm font-medium text-muted-foreground">Loading PMAG Dashboard...</p>
        </div>
      </div>
    );
  }

  const { summary, project_health, sv_chart, critical_path, dpr_tracker, connectivity, alerts } = data;
  const filteredProjects = project_health.filter(p => p.name.toLowerCase().includes(searchQuery.toLowerCase()));

  return (
    <div className="flex min-h-screen w-full bg-[var(--background)]">
      {/* ─── Sidebar (identical structure to LeftSidebar.tsx) ─── */}
      <aside className={`hidden md:block h-screen bg-white dark:bg-slate-900 border-r border-slate-200 dark:border-slate-800 z-50 shrink-0 transition-[width] duration-200 ease-in-out sticky top-0 ${collapsed ? 'w-[60px]' : 'w-[210px]'}`}>
        {sidebarInner}
      </aside>

      {isMobileOpen && <div className="fixed inset-0 bg-black/30 z-[100] md:hidden" onClick={() => setIsMobileOpen(false)} />}
      <aside className={`fixed inset-y-0 left-0 w-[250px] bg-white dark:bg-slate-900 border-r border-slate-200 dark:border-slate-800 z-[101] transform transition-transform duration-200 ease-in-out md:hidden ${isMobileOpen ? 'translate-x-0' : '-translate-x-full'}`}>
        {sidebarInner}
      </aside>

      {/* ─── Main Content (same structure as CEODashboard) ─── */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top Header (matches TopHeader.tsx) */}
        <header className="h-[73px] bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800 flex items-center justify-between px-2 sm:px-4 shrink-0 z-40 sticky top-0">
          <div className="flex items-center gap-3 flex-1">
            <button onClick={() => setIsMobileOpen(true)} className="md:hidden p-2 -ml-1 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors">
              <Menu className="w-5 h-5" />
            </button>
            <div className="hidden md:flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-[#0b74b1]/10 flex items-center justify-center">
                <LayoutDashboard className="w-4 h-4 text-[#0b74b1]" />
              </div>
              <span className="font-bold text-gray-900 dark:text-white text-sm tracking-tight">PMAG — Portfolio Management & Governance</span>
            </div>
          </div>
          <div className="flex items-center gap-1 sm:gap-2">
            
            <button 
              onClick={handleSyncData}
              disabled={isSyncing}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300 text-[12px] font-semibold transition-colors shadow-sm mr-2 ${isSyncing ? 'opacity-50 cursor-not-allowed' : ''}`}
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isSyncing ? 'animate-spin text-[#0b74b1]' : ''}`} />
              <span className="hidden lg:inline">{isSyncing ? 'Syncing...' : 'Sync All Data'}</span>
            </button>

            {/* Ask Akasha Button */}
            <button 
              onClick={() => setIsCopilotOpen(!isCopilotOpen)} 
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#0b74b1] hover:bg-[#0966a0] text-white text-[12px] font-semibold transition-colors shadow-sm shadow-[#0b74b1]/20 mr-2"
            >
              <Sparkles className="w-3.5 h-3.5" />
              <span className="hidden lg:inline">Ask Akasha</span>
            </button>

            <div className="relative hidden lg:block">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400" />
              <input value={searchQuery} onChange={e => setSearchQuery(e.target.value)} placeholder="Search projects..."
                className="pl-9 pr-4 py-1.5 w-52 rounded-lg bg-gray-100 dark:bg-gray-800 text-[12px] text-gray-700 dark:text-gray-200 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-[#0b74b1]/20 border border-transparent transition-all" />
            </div>
            <button onClick={() => setTheme(t => t === 'light' ? 'dark' : 'light')} className="p-2 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors">
              {theme === 'dark' ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
            </button>
            <button className="relative p-2 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors">
              <Bell className="w-4 h-4" />
              {alerts.length > 0 && <span className="absolute top-1.5 right-1.5 w-1.5 h-1.5 rounded-full bg-red-500" />}
            </button>
            <div className="relative group ml-0.5">
              <div className="w-8 h-8 rounded-full bg-gradient-to-br from-[#0b74b1] to-[#76489d] p-[1.5px] cursor-pointer">
                <div className="w-full h-full rounded-full bg-white dark:bg-gray-900 flex items-center justify-center">
                  <User className="w-3.5 h-3.5 text-gray-500" />
                </div>
              </div>
              <div className="absolute right-0 top-full mt-1.5 w-44 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg shadow-lg py-1 z-50 opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all origin-top-right scale-95 group-hover:scale-100">
                <div className="px-3 py-2 border-b border-gray-100 dark:border-gray-800">
                  <p className="text-[12px] font-semibold text-gray-900 dark:text-white">{user?.display_name}</p>
                  <p className="text-[11px] text-gray-400 truncate">{user?.role}</p>
                </div>
                <button onClick={handleLogout} className="w-full text-left px-3 py-1.5 text-[12px] text-red-600 hover:bg-red-50 dark:hover:bg-red-900/10 transition-colors flex items-center gap-1.5">
                  <LogOut className="w-3.5 h-3.5" /> Sign Out
                </button>
              </div>
            </div>
          </div>
        </header>

        {/* Dashboard Content */}
        <main className="flex-1 p-4">
          <AnimatePresence mode="wait">
            {selectedProjectId ? (
              <motion.div
                key="workspace"
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
                transition={{ duration: 0.2 }}
                className="h-[calc(100vh-100px)] bg-white dark:bg-gray-900 rounded-2xl shadow-sm border border-gray-100 dark:border-gray-800 overflow-hidden relative"
              >
                <div className="absolute inset-0 overflow-y-auto">
                  <ProjectWorkspace projectId={selectedProjectId} onBack={() => setSelectedProjectId(null)} />
                </div>
              </motion.div>
            ) : (
            <motion.div
              key={activeSection}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.2 }}
              className="space-y-4"
            >
              {/* ─── 1. Portfolio Overview ─── */}
              {activeSection === 'overview' && (
                <PMAGOverview
                  summary={summary}
                  filteredProjects={filteredProjects}
                  sv_chart={sv_chart}
                  critical_path={critical_path}
                  dpr_tracker={dpr_tracker}
                  connectivity={connectivity}
                  alerts={alerts}
                  theme={theme}
                />
              )}

              {/* ─── NEW PMAG TABS ─── */}
              {activeSection === 'site_monitoring' && (
                <SiteMonitoring data={siteMonitoringData} theme={theme} />
              )}
              {activeSection === 'grid_status' && (
                <GridStatus connectivity={connectivity} critical_path={critical_path} theme={theme} />
              )}
              {activeSection === 'reports' && (
                <ReportsAnalytics data={reportsData} theme={theme} />
              )}
              {activeSection === 'team' && (
                <TeamManagement data={teamData} theme={theme} />
              )}

              {/* ─── FULL PAGE COMPONENTS ─── */}
              {activeSection === 'project360' && <Project360 onOpenProject={(id) => setSelectedProjectId(id)} />}

              {/* ─── EXTRA MODULES ─── */}
              {activeSection === 'smart_search' && <SmartSearch onOpenProject={(id) => setSelectedProjectId(id)} />}
              {activeSection === 'project_map' && <ProjectMap projects={project_health} onOpenProject={(id) => setSelectedProjectId(id)} theme={theme} />}
              {activeSection === 'executive_brief' && <ExecutiveBriefing />}

            </motion.div>
            )}
          </AnimatePresence>
        </main>
      </div>

      {/* 4. Floating AI Copilot Panel */}
      <ScenarioSimulationPanel 
        isOpen={isCopilotOpen}
        setIsOpen={setIsCopilotOpen}
        onMaximize={() => {
          setActiveSection('ai_copilot');
          sessionStorage.setItem('pmagActiveSection', 'ai_copilot');
          setIsCopilotOpen(false);
        }} 
      />
    </div>
  );
}
