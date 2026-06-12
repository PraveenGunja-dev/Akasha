import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
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

// Phase 6 AI Modules
import AICopilot from '../components/sections/AICopilot';
import ExecutiveBriefing from '../components/sections/ExecutiveBriefing';
import SmartSearch from '../components/sections/SmartSearch';
import KnowledgeGraph from '../components/sections/KnowledgeGraph';

import TransmissionDataViewer from '../components/sections/TransmissionDataViewer';
import ScenarioSimulationPanel from '../components/layout/ScenarioSimulationPanel';
import SimulationLab from '../components/sections/SimulationLab';
import ProjectWorkspace from '../components/sections/ProjectWorkspace';
import DataIntegrationHub from '../components/sections/DataIntegrationHub';

export default function CEODashboard() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<string>("overview");
  const [previousTab, setPreviousTab] = useState<string>("overview");
  const [isCopilotOpen, setIsCopilotOpen] = useState(false);
  const [selectedProject, setSelectedProject] = useState<string>("All");

  // API Data State
  const [dashboardData, setDashboardData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  // Briefing Data State
  const [briefing, setBriefing] = useState<any>(null);
  const [briefingLoading, setBriefingLoading] = useState(true);
  const [briefingError, setBriefingError] = useState('');

  const [p6Data, setP6Data] = useState<any[]>([]);
  const [sapData, setSapData] = useState<any[]>([]);
  const [logisticsData, setLogisticsData] = useState<any[]>([]);
  const [finDetails, setFinDetails] = useState<any[]>([]);
  const [logDetails, setLogDetails] = useState<any[]>([]);

  const handleOpenProject = (id: string) => {
    navigate(`/dashboard/project/${id}`);
  };

  // Fetch Data
  useEffect(() => {
    const fetchData = async () => {
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

    fetchData();
  }, [selectedProject]); // removed briefing from dependencies so it only runs when project changes

  // To cleanly track which modules are implemented
  const implementedModules = [
    'overview', 'project360', 'health', 'schedule', 'financial', 'procurement', 'material', 
    'risk', 'predictive', 'admin', 'reports', 'transmission_data',
    'ai_copilot', 'executive_brief', 'smart_search', 'knowledge_graph', 'simulation_lab'
  ];

  const handleTabChange = (tab: string) => {
    if (tab === 'ai_copilot') {
      setIsCopilotOpen(true);
    } else {
      setPreviousTab(tab);
      setActiveTab(tab);
    }
  };

  return (
    <div className="flex min-h-screen w-full bg-background text-foreground">
      
      {/* 1. Left Navigation Rail */}
      <div className="sticky top-0 h-screen shrink-0 z-40">
        <LeftSidebar activeTab={activeTab} setActiveTab={handleTabChange} />
      </div>
      
      {/* Middle Area: Header + Scrollable Content */}
      <div className="flex-1 flex flex-col min-w-0 relative bg-background">
        
        {/* 2. Top Global Header (hidden for full-screen Copilot) */}
        {activeTab !== 'ai_copilot' && (
          <div className="sticky top-0 z-40 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 border-b border-border">
            <TopHeader 
              selectedProject={selectedProject} 
              setSelectedProject={setSelectedProject} 
              masterProjects={Array.from(new Set(dashboardData?.projects?.map((p:any) => p.project_name) || []))} 
              onOpenCopilot={() => setIsCopilotOpen(!isCopilotOpen)}
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
                  setIsCopilotOpen(true);
                }} 
              />
            )}
            {activeTab === 'simulation_lab' && <SimulationLab p6Data={p6Data} dashboardData={dashboardData} />}
          </div>
        ) : (
          /* 3b. Normal Dashboard Area */
          <main className="flex-1 p-6 relative">
            
            {/* Subtle Background Elements */}
            <div className="absolute top-0 left-1/4 w-[800px] h-[500px] bg-[#3B82F6] opacity-[0.03] blur-[150px] rounded-full pointer-events-none z-0"></div>

            <div className="relative z-10">
              {projectId ? (
                <div className="w-full h-full min-h-[calc(100vh-120px)]">
                  <ProjectWorkspace 
                    projectId={projectId} 
                    onBack={() => navigate('/dashboard')} 
                  />
                </div>
              ) : (
                <>
                  {activeTab === 'overview' && <ExecutiveOverview dashboardData={dashboardData} briefing={briefing} briefingLoading={briefingLoading} briefingError={briefingError} />}
                  {activeTab === 'project360' && <Project360 onOpenProject={handleOpenProject} />}
                  {activeTab === 'data_integration' && <DataIntegrationHub />}
              {activeTab === 'health' && <PortfolioHealth p6Data={p6Data} logisticsData={logisticsData} />}
              {activeTab === 'schedule' && <P6View p6Data={p6Data} loading={loading} />}
              {activeTab === 'financial' && <SAPView sapData={sapData} logisticsData={logisticsData} finDetails={finDetails} logDetails={logDetails} loading={loading} />}
              {activeTab === 'procurement' && <ProcurementIntelligence finDetails={finDetails} />}
              {activeTab === 'material' && <MaterialIntelligence logDetails={logDetails} logisticsData={logisticsData} />}
              {activeTab === 'transmission_data' && <TransmissionDataViewer dashboardData={dashboardData} />}
              {activeTab === 'risk' && <RiskCommandCenter p6Data={p6Data} finDetails={finDetails} />}
              {activeTab === 'predictive' && <PredictiveAnalytics p6Data={p6Data} />}
              {activeTab === 'admin' && <DecisionCenter p6Data={p6Data} finDetails={finDetails} />}
              {activeTab === 'reports' && <ReportsInsights p6Data={p6Data} sapData={sapData} finDetails={finDetails} />}
              
              {/* AI Modules */}
              {activeTab === 'executive_brief' && <ExecutiveBriefing />}
              {activeTab === 'smart_search' && <SmartSearch onOpenProject={handleOpenProject} />}
              {activeTab === 'knowledge_graph' && <KnowledgeGraph />}
              
              {/* Placeholders for unbuilt sections */}
              {!implementedModules.includes(activeTab) && (
                <div className="flex items-center justify-center h-[500px] border-2 border-dashed border-border rounded-2xl bg-card/50 backdrop-blur-sm">
                  <div className="text-center">
                    <h2 className="text-2xl font-light text-muted-foreground mb-2 uppercase tracking-widest">{activeTab.replace('_', ' ')} Module</h2>
                    <p className="text-sm text-muted-foreground/70">This module is currently in development (Awaiting Database Integration).</p>
                  </div>
                </div>
              )}
                </>
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
    </div>
  );
}
