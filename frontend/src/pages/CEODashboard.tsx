import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, useLocation, useSearchParams } from 'react-router-dom';
import { motion } from 'framer-motion';
import { X } from 'lucide-react';
import LeftSidebar from '../components/layout/LeftSidebar';
import TopHeader from '../components/layout/TopHeader';

import ExecutiveOverview from '../features/dashboard/ExecutiveOverview';
import Project360 from '../features/projects/Project360';
import PortfolioHealth from '../features/dashboard/PortfolioHealth';
import P6View from '../components/dashboards/P6View';
import SAPView from '../components/dashboards/SAPView';
import ProcurementIntelligence from '../features/analytics/ProcurementIntelligence';
import MaterialIntelligence from '../features/analytics/MaterialIntelligence';
import RiskCommandCenter from '../features/dashboard/RiskCommandCenter';
import PredictiveAnalytics from '../features/dashboard/PredictiveAnalytics';
import DecisionCenter from '../features/dashboard/DecisionCenter';
import ReportsInsights from '../features/analytics/ReportsInsights';
import CapacityOverview from '../features/dashboard/CapacityOverview';

// Phase 6 AI Modules
import AICopilot from '../features/chatbot/AICopilot';
import ExecutiveBriefing from '../features/dashboard/ExecutiveBriefing';
import SmartSearch from '../features/analytics/SmartSearch';
import KnowledgeGraph from '../features/analytics/KnowledgeGraph';
import ProjectMap from '../features/projects/ProjectMap';

import TransmissionDataViewer from '../features/analytics/TransmissionDataViewer';
import ScenarioSimulationPanel from '../components/layout/ScenarioSimulationPanel';
import SimulationLab from '../features/analytics/SimulationLab';
import ProjectWorkspace from '../features/projects/ProjectWorkspace';
import QualityCommandCenter from '../features/quality/QualityCommandCenter';
import { clearDashboardQueryCache, getCachedDashboardJson } from '../services/dashboardQueryCache';
import { replayPaneAnimations } from '../features/dashboard/replayPaneAnimations';

export default function CEODashboard() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<string>(() => {
    return sessionStorage.getItem('ceoActiveTab') || "overview";
  });
  const [visitedTabs, setVisitedTabs] = useState<Set<string>>(() => new Set([
    sessionStorage.getItem('ceoActiveTab') || 'overview',
  ]));
  const [previousTab, setPreviousTab] = useState<string>("overview");
  const [isCopilotOpen, setIsCopilotOpen] = useState(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [selectedProject, setSelectedProject] = useState<string>("All");
  const [simulationContext, setSimulationContext] = useState<any>(null);
  const [modalSimulationContext, setModalSimulationContext] = useState<any>(null);

  const [dashboardData, setDashboardData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const location = useLocation();

  // Load saved tab from session storage or default to 'overview'
  useEffect(() => {
    const savedTab = sessionStorage.getItem('ceoActiveTab');
    if (savedTab && implementedModules.includes(savedTab)) {
      setActiveTab(savedTab);
    }
  }, []);

  useEffect(() => {
    setVisitedTabs(current => {
      if (current.has(activeTab)) return current;
      return new Set([...current, activeTab]);
    });
  }, [activeTab]);

  useEffect(() => {
    replayPaneAnimations(activeTab);
  }, [activeTab]);

  // Reset project when returning to root dashboard via explicit back button
  useEffect(() => {
    if (!projectId && location.state?.reset) {
      setSelectedProject("All");
      // Clear the state so it doesn't trigger again on a simple refresh
      navigate('/ceo-dashboard', { replace: true, state: {} });
    }
  }, [projectId, location, navigate]);

  const [searchParams] = useSearchParams();
  const portfolio = searchParams.get('portfolio');

  // Briefing Data State
  const [briefing, setBriefing] = useState<any>(null);
  const [briefingLoading, setBriefingLoading] = useState(true);
  const [briefingError, setBriefingError] = useState('');

  const [p6Data, setP6Data] = useState<any[]>([]);
  const [sapData, setSapData] = useState<any[]>([]);
  const [logisticsData, setLogisticsData] = useState<any[]>([]);
  const [finDetails, setFinDetails] = useState<any[]>([]);
  const [logDetails, setLogDetails] = useState<any[]>([]);
  const [isSyncing, setIsSyncing] = useState(false);
  const selectedProjectId = selectedProject === 'All'
    ? undefined
    : dashboardData?.projects?.find((project: any) =>
        project.project_name === selectedProject || project.p6_project_name === selectedProject
      )?.project_id || '__unavailable__';

  const handleOpenProject = (id: string) => {
    navigate(`/ceo-dashboard/project/${id}`);
  };

  const loadActivePaneData = async (force = false) => {
    if (force || !dashboardData || !visitedTabs.has(activeTab)) setLoading(true);
    try {
      const portfolioParams = new URLSearchParams();
      if (portfolio) portfolioParams.set('portfolio', portfolio);
      const portfolioQuery = portfolioParams.size ? `?${portfolioParams.toString()}` : '';
      const scopedParams = new URLSearchParams(portfolioParams);
      if (selectedProject !== 'All') scopedParams.set('project_name', selectedProject);
      const scopedQuery = scopedParams.size ? `?${scopedParams.toString()}` : '';

      const dashboard = await getCachedDashboardJson<any>(
        `/akasha/api/dashboard/summary${portfolioQuery}`,
        { force },
      );
      setDashboardData(dashboard);

      const needsP6 = new Set(['health', 'schedule', 'simulation_lab', 'admin', 'reports']);
      const needsFinancialSummary = new Set(['financial', 'reports']);
      const needsLogisticsSummary = new Set(['health', 'financial', 'material']);
      const needsFinancialDetails = new Set(['financial', 'procurement', 'admin', 'reports']);
      const needsLogisticsDetails = new Set(['financial', 'material']);
      const requests: Promise<void>[] = [];

      if (needsP6.has(activeTab)) {
        requests.push(getCachedDashboardJson<any[]>(`/akasha/api/summary${scopedQuery}`, { force }).then(setP6Data));
      }
      if (needsFinancialSummary.has(activeTab)) {
        requests.push(getCachedDashboardJson<any[]>(`/akasha/api/financials${scopedQuery}`, { force }).then(setSapData));
      }
      if (needsLogisticsSummary.has(activeTab)) {
        requests.push(getCachedDashboardJson<any[]>(`/akasha/api/logistics${scopedQuery}`, { force }).then(setLogisticsData));
      }
      if (needsFinancialDetails.has(activeTab)) {
        requests.push(getCachedDashboardJson<any[]>(`/akasha/api/financials/details${scopedQuery}`, { force }).then(setFinDetails));
      }
      if (needsLogisticsDetails.has(activeTab)) {
        requests.push(getCachedDashboardJson<any[]>(`/akasha/api/logistics/details${scopedQuery}`, { force }).then(setLogDetails));
      }
      await Promise.all(requests);

      if (activeTab === 'overview' && !briefing && selectedProject === 'All') {
        getCachedDashboardJson<any>('/akasha/api/generate-briefing', { force })
          .then(setBriefing)
          .catch(error => setBriefingError(error.message || 'Error connecting to AI Core'))
          .finally(() => setBriefingLoading(false));
      } else if (selectedProject !== 'All') {
        setBriefingLoading(false);
      }
    } catch (error) {
      console.error("Failed to fetch dashboard data:", error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadActivePaneData();
  }, [activeTab, selectedProject, portfolio]);

  const handleNavigateToSimulation = (projId: string, context?: any) => {
    setSelectedProject(projId);
    if (context) {
      setModalSimulationContext(context);
    } else {
      setActiveTab('simulation_lab');
      sessionStorage.setItem('ceoActiveTab', 'simulation_lab');
    }
  };

  const handleSyncData = async () => {
    setIsSyncing(true);
    try {
      await Promise.allSettled([
        fetch('/akasha/api/sharepoint/sync', { method: 'POST' }),
        fetch('/akasha/api/tc/sync', { method: 'POST' }),
        fetch('/akasha/api/mapping/sync', { method: 'POST' }),
        fetch('/akasha/api/p6/sync', { method: 'POST' }),
        fetch('/akasha/api/capacity/sync', { method: 'POST' }),
        fetch('/akasha/api/pulse/sync', { method: 'POST' })
      ]);
    } catch (error) {
      console.error("Sync failed:", error);
    }
    clearDashboardQueryCache();
    await loadActivePaneData(true);
    setIsSyncing(false);
  };

  useEffect(() => {
    const handleOpenSimulation = (e: any) => {
      if (e.detail?.projectId) {
        // The projectId from ProjectWorkspace is a P6 ID (e.g. "FY25-P43").
        // We need to resolve it to the project_name used in the dashboard.
        const p6Id = e.detail.projectId;
        const matchedProject = dashboardData?.projects?.find(
          (p: any) => p.p6?.id === p6Id || p.project_name === p6Id
        );
        if (matchedProject) {
          setSelectedProject(matchedProject.project_name);
        } else {
          setSelectedProject(p6Id);
        }
      }
      setActiveTab('simulation_lab');
      sessionStorage.setItem('ceoActiveTab', 'simulation_lab');
      navigate('/ceo-dashboard');
    };
    window.addEventListener('open-simulation-lab', handleOpenSimulation);
    return () => window.removeEventListener('open-simulation-lab', handleOpenSimulation);
  }, [navigate, dashboardData]);

  // To cleanly track which modules are implemented
  const implementedModules = [
    'overview', 'project360', 'health', 'schedule', 'financial', 'procurement', 'material', 
    'risk', 'predictive', 'admin', 'reports', 'transmission_data', 'capacity_overview',
    'ai_copilot', 'executive_brief', 'smart_search', 'project_map', 'knowledge_graph', 'simulation_lab',
    'quality'
  ];

  const handleTabChange = (tab: string) => {
    setPreviousTab(activeTab);
    setActiveTab(tab);
    sessionStorage.setItem('ceoActiveTab', tab);
    if (tab !== 'simulation_lab') {
      setSimulationContext(null);
    }
    if (projectId) {
      navigate('/ceo-dashboard');
    }
  };

  return (
    <div className={`flex w-full bg-[var(--background)] ${activeTab === 'ai_copilot' ? 'h-screen overflow-hidden' : 'min-h-screen'}`}>
      
      {/* 1. Left Navigation Rail */}
      <div className="sticky top-0 h-screen shrink-0 z-50">
        <LeftSidebar 
          activeTab={activeTab} 
          setActiveTab={handleTabChange} 
          isMobileOpen={isSidebarOpen}
          onCloseMobile={() => setIsSidebarOpen(false)}
        />
      </div>
      
      {/* Middle Area: Header + Scrollable Content */}
      <div className="flex-1 flex flex-col min-w-0">
        
        {/* 2. Top Global Header */}
        <div className="sticky top-0 z-[60]">
          <TopHeader 
            selectedProject={selectedProject} 
            setSelectedProject={setSelectedProject} 
            masterProjects={dashboardData?.projects || []} 
            onNavigateToSimulation={handleNavigateToSimulation}
            onOpenCopilot={() => setIsCopilotOpen(!isCopilotOpen)}
            onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)}
            onSyncData={handleSyncData}
            isSyncing={isSyncing}
          />
        </div>
        
        {/* 3a. Full-bleed AI Copilot or Simulation Lab (no padding, no scroll wrapper) */}
        <div className={activeTab === 'ai_copilot' || activeTab === 'simulation_lab'
          ? 'flex-1 min-h-0 p-4 overflow-hidden flex flex-col'
          : 'hidden'}>
            {activeTab === 'ai_copilot' && (
              <AICopilot 
                onMinimize={() => {
                  setActiveTab(previousTab);
                  sessionStorage.setItem('ceoActiveTab', previousTab);
                  setIsCopilotOpen(true);
                }} 
              />
            )}
            {activeTab === 'simulation_lab' && <SimulationLab p6Data={p6Data} dashboardData={dashboardData} initialProject={selectedProject} simulationContext={simulationContext} />}
        </div>

        {/* 3b. Normal Dashboard Area remains mounted to preserve pane state. */}
        <main className={activeTab === 'ai_copilot' || activeTab === 'simulation_lab' ? 'hidden' : 'flex-1 p-4'}>
            <div className="w-full">
              {projectId ? (
                <div className="w-full h-full min-h-[calc(100vh-120px)]">
                  <ProjectWorkspace 
                    projectId={projectId} 
                    onBack={() => navigate('/ceo-dashboard', { state: { reset: true } })} 
                  />
                </div>
              ) : (
                <>
                  {Array.from(visitedTabs).map(tab => (
                    <motion.div
                      key={tab}
                      data-dashboard-pane={tab}
                      className={tab === activeTab ? 'block' : 'hidden'}
                      initial={{ opacity: 0, y: 10 }}
                      animate={tab === activeTab
                        ? { opacity: 1, y: 0 }
                        : { opacity: 0, y: 10 }}
                      transition={{ duration: 0.2 }}
                    >
                      {tab === 'overview' && <ExecutiveOverview dashboardData={dashboardData} briefing={briefing} briefingLoading={briefingLoading} briefingError={briefingError} />}
                      {tab === 'project360' && <Project360 onOpenProject={handleOpenProject} />}
                      {tab === 'health' && <PortfolioHealth p6Data={p6Data} logisticsData={logisticsData} />}
                      {tab === 'schedule' && <P6View p6Data={p6Data} loading={loading} />}
                      {tab === 'financial' && <SAPView sapData={sapData} logisticsData={logisticsData} finDetails={finDetails} logDetails={logDetails} loading={loading} />}
                      {tab === 'procurement' && <ProcurementIntelligence finDetails={finDetails} />}
                      {tab === 'material' && <MaterialIntelligence logDetails={logDetails} logisticsData={logisticsData} />}
                      {tab === 'transmission_data' && <TransmissionDataViewer dashboardData={dashboardData} />}
                      {tab === 'risk' && <RiskCommandCenter p6Data={p6Data} finDetails={finDetails} selectedProjectId={selectedProjectId} />}
                      {tab === 'predictive' && <PredictiveAnalytics p6Data={p6Data} selectedProjectId={selectedProjectId} />}
                      {tab === 'admin' && <DecisionCenter p6Data={p6Data} finDetails={finDetails} />}
                      {tab === 'reports' && <ReportsInsights p6Data={p6Data} sapData={sapData} finDetails={finDetails} dashboardData={dashboardData} />}
                      {tab === 'capacity_overview' && <CapacityOverview />}
                      {tab === 'executive_brief' && <ExecutiveBriefing />}
                      {tab === 'smart_search' && <SmartSearch onOpenProject={handleOpenProject} />}
                      {tab === 'project_map' && <ProjectMap projects={dashboardData?.projects || []} onOpenProject={handleOpenProject} />}
                      {tab === 'knowledge_graph' && <KnowledgeGraph />}
                      {tab === 'quality' && <QualityCommandCenter />}
                      {!implementedModules.includes(tab) && (
                        <div className="flex items-center justify-center h-[500px] border-2 border-dashed border-border dark:border-slate-700 rounded-2xl bg-white/50 dark:bg-gray-900/50">
                          <div className="text-center">
                            <h2 className="text-2xl font-semibold text-muted-foreground mb-2">{tab.replace('_', ' ')} Module</h2>
                            <p className="text-sm text-muted-foreground">This module is currently in development.</p>
                          </div>
                        </div>
                      )}
                    </motion.div>
                  ))}
                </>
              )}
            </div>
        </main>
      </div>
      
      {/* 4. Floating AI Copilot Panel */}
      {activeTab !== 'ai_copilot' && (
        <ScenarioSimulationPanel 
          isOpen={isCopilotOpen}
          setIsOpen={setIsCopilotOpen}
          projectId={projectId}
          onMaximize={() => {
            setActiveTab('ai_copilot');
            setIsCopilotOpen(false);
          }} 
        />
      )}
      
      {/* 5. Notification Simulation Modal */}
      {modalSimulationContext && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 md:p-8">
          <div className="bg-[var(--background)] w-full h-full max-w-[1400px] max-h-[90vh] rounded-2xl shadow-2xl overflow-hidden flex flex-col relative border border-border dark:border-border">
            <button 
              onClick={() => setModalSimulationContext(null)}
              className="absolute top-4 right-4 z-[110] p-2 bg-muted dark:bg-card hover:bg-gray-200 dark:hover:bg-gray-700 rounded-full transition-colors text-muted-foreground"
            >
              <X className="w-5 h-5" />
            </button>
            <div className="flex-1 overflow-hidden w-full h-full relative p-6 md:p-8">
              <SimulationLab 
                p6Data={p6Data} 
                dashboardData={dashboardData} 
                initialProject={selectedProject} 
                simulationContext={modalSimulationContext} 
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
