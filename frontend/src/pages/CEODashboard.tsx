import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { X } from 'lucide-react';
import LeftSidebar from '../components/layout/LeftSidebar';
import TopHeader from '../components/layout/TopHeader';

import ExecutiveOverview from '../components/sections/ExecutiveOverview';
import Project360 from '../components/sections/Project360';
import PortfolioHealth from '../components/sections/PortfolioHealth';
import P6View from '../components/dashboards/P6View';
import SAPView from '../components/dashboards/SAPView';
import ProcurementIntelligence from '../components/sections/ProcurementIntelligence';
import MaterialIntelligence from '../components/sections/MaterialIntelligence';
import RiskCommandCenter from '../components/sections/RiskCommandCenter';
import PredictiveAnalytics from '../components/sections/PredictiveAnalytics';
import DecisionCenter from '../components/sections/DecisionCenter';
import ReportsInsights from '../components/sections/ReportsInsights';
import CapacityOverview from '../components/sections/CapacityOverview';

// Phase 6 AI Modules
import AICopilot from '../components/sections/AICopilot';
import ExecutiveBriefing from '../components/sections/ExecutiveBriefing';
import SmartSearch from '../components/sections/SmartSearch';
import KnowledgeGraph from '../components/sections/KnowledgeGraph';
import ProjectMap from '../components/sections/ProjectMap';

import TransmissionDataViewer from '../components/sections/TransmissionDataViewer';
import ScenarioSimulationPanel from '../components/layout/ScenarioSimulationPanel';
import SimulationLab from '../components/sections/SimulationLab';
import ProjectWorkspace from '../components/sections/ProjectWorkspace';

export default function CEODashboard() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<string>(() => {
    return sessionStorage.getItem('ceoActiveTab') || "overview";
  });
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

  // Reset project when returning to root dashboard via explicit back button
  useEffect(() => {
    if (!projectId && location.state?.reset) {
      setSelectedProject("All");
      // Clear the state so it doesn't trigger again on a simple refresh
      navigate('/dashboard', { replace: true, state: {} });
    }
  }, [projectId, location, navigate]);

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

  const handleOpenProject = (id: string) => {
    navigate(`/dashboard/project/${id}`);
  };

  // Fetch Data
  const loadAllData = async () => {
    setLoading(true);
    try {
      const query = selectedProject !== 'All' ? `?project_name=${encodeURIComponent(selectedProject)}` : '';
      
      const [dashRes, p6Res, sapRes, logRes, finDetRes, logDetRes] = await Promise.all([
        fetch(`/akasha/api/dashboard/summary`),
        fetch(`/akasha/api/summary${query}`),
        fetch(`/akasha/api/financials${query}`),
        fetch(`/akasha/api/logistics${query}`),
        fetch(`/akasha/api/financials/details${query}`),
        fetch(`/akasha/api/logistics/details${query}`)
      ]);

      const [dash, p6, sap, log, fDet, lDet] = await Promise.all([
        dashRes.json(),
        p6Res.json(),
        sapRes.json(),
        logRes.json(),
        finDetRes.json(),
        logDetRes.json()
      ]);

      setDashboardData(dash);
      setP6Data(p6);
      setSapData(sap);
      setLogisticsData(log);
      setFinDetails(fDet);
      setLogDetails(lDet);
      // Only fetch briefing once if not loaded
      if (!briefing && selectedProject === 'All') {
        try {
          const bRes = await fetch('/akasha/api/generate-briefing');
          if (bRes.ok) {
            const bData = await bRes.json();
            setBriefing(bData);
          } else {
            setBriefingError('Failed to generate AI Briefing');
          }
        } catch (e: any) {
          setBriefingError(e.message || 'Error connecting to AI Core');
        } finally {
          setBriefingLoading(false);
        }
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
    loadAllData();
  }, [selectedProject]);

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
        fetch('/akasha/api/capacity/sync', { method: 'POST' })
      ]);
    } catch (error) {
      console.error("Sync failed:", error);
    }
    await loadAllData();
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
      navigate('/dashboard');
    };
    window.addEventListener('open-simulation-lab', handleOpenSimulation);
    return () => window.removeEventListener('open-simulation-lab', handleOpenSimulation);
  }, [navigate, dashboardData]);

  // To cleanly track which modules are implemented
  const implementedModules = [
    'overview', 'project360', 'health', 'schedule', 'financial', 'procurement', 'material', 
    'risk', 'predictive', 'admin', 'reports', 'transmission_data', 'capacity_overview',
    'ai_copilot', 'executive_brief', 'smart_search', 'project_map', 'knowledge_graph', 'simulation_lab'
  ];

  const handleTabChange = (tab: string) => {
    if (tab === 'ai_copilot') {
      setIsCopilotOpen(true);
    } else {
      setPreviousTab(activeTab);
      setActiveTab(tab);
      sessionStorage.setItem('ceoActiveTab', tab);
      if (tab !== 'simulation_lab') {
        setSimulationContext(null);
      }
      if (projectId) {
        navigate('/dashboard');
      }
    }
  };

  return (
    <div className="flex min-h-screen w-full bg-[var(--background)]">
      
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
        
        {/* 2. Top Global Header (hidden for full-screen Copilot) */}
        {activeTab !== 'ai_copilot' && (
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
        )}
        
        {/* 3a. Full-bleed AI Copilot or Simulation Lab (no padding, no scroll wrapper) */}
        {activeTab === 'ai_copilot' || activeTab === 'simulation_lab' ? (
          <div className="flex-1 min-h-0 p-4 overflow-hidden flex flex-col">
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
        ) : (
          /* 3b. Normal Dashboard Area */
          <main className="flex-1 p-4">
            <div className="w-full">
              {projectId ? (
                <div className="w-full h-full min-h-[calc(100vh-120px)]">
                  <ProjectWorkspace 
                    projectId={projectId} 
                    onBack={() => navigate('/dashboard', { state: { reset: true } })} 
                  />
                </div>
              ) : (
                <AnimatePresence mode="wait">
                  <motion.div
                    key={activeTab}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -10 }}
                    transition={{ duration: 0.2 }}
                  >
                    {activeTab === 'overview' && <ExecutiveOverview dashboardData={dashboardData} briefing={briefing} briefingLoading={briefingLoading} briefingError={briefingError} />}
                    {activeTab === 'project360' && <Project360 onOpenProject={handleOpenProject} />}
                    {activeTab === 'health' && <PortfolioHealth p6Data={p6Data} logisticsData={logisticsData} />}
                    {activeTab === 'schedule' && <P6View p6Data={p6Data} loading={loading} />}
                    {activeTab === 'financial' && <SAPView sapData={sapData} logisticsData={logisticsData} finDetails={finDetails} logDetails={logDetails} loading={loading} />}
                    {activeTab === 'procurement' && <ProcurementIntelligence finDetails={finDetails} />}
                    {activeTab === 'material' && <MaterialIntelligence logDetails={logDetails} logisticsData={logisticsData} />}
                    {activeTab === 'transmission_data' && <TransmissionDataViewer dashboardData={dashboardData} />}
                    {activeTab === 'risk' && <RiskCommandCenter p6Data={p6Data} finDetails={finDetails} />}
                    {activeTab === 'predictive' && <PredictiveAnalytics p6Data={p6Data} />}
                    {activeTab === 'admin' && <DecisionCenter p6Data={p6Data} finDetails={finDetails} />}
                    {activeTab === 'reports' && <ReportsInsights p6Data={p6Data} sapData={sapData} finDetails={finDetails} dashboardData={dashboardData} />}
                    
                    {activeTab === 'capacity_overview' && <CapacityOverview />}
                    {/* AI Modules */}
                    {activeTab === 'executive_brief' && <ExecutiveBriefing />}
                    {activeTab === 'smart_search' && <SmartSearch onOpenProject={handleOpenProject} />}
                    {activeTab === 'project_map' && <ProjectMap projects={dashboardData?.project_health || []} onOpenProject={handleOpenProject} />}
                    {activeTab === 'knowledge_graph' && <KnowledgeGraph />}
                    
                    {/* Placeholders for unbuilt sections */}
                    {!implementedModules.includes(activeTab) && (
                      <div className="flex items-center justify-center h-[500px] border-2 border-dashed border-slate-300 dark:border-slate-700 rounded-2xl bg-white/50 dark:bg-slate-900/50">
                        <div className="text-center">
                          <h2 className="text-2xl font-semibold text-slate-400 mb-2">{activeTab.replace('_', ' ')} Module</h2>
                          <p className="text-sm text-slate-500">This module is currently in development.</p>
                        </div>
                      </div>
                    )}
                  </motion.div>
                </AnimatePresence>
              )}
            </div>
          </main>
        )}
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
          <div className="bg-[var(--background)] w-full h-full max-w-[1400px] max-h-[90vh] rounded-2xl shadow-2xl overflow-hidden flex flex-col relative border border-gray-200 dark:border-gray-800">
            <button 
              onClick={() => setModalSimulationContext(null)}
              className="absolute top-4 right-4 z-[110] p-2 bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-full transition-colors text-gray-500"
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
