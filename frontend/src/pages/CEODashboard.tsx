import React, { useState, useEffect } from 'react';
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
import ProjectWorkspace from '../components/sections/ProjectWorkspace';
import DataIntegrationHub from '../components/sections/DataIntegrationHub';

export default function CEODashboard() {
  const [activeTab, setActiveTab] = useState<string>("overview");
  const [previousTab, setPreviousTab] = useState<string>("overview");
  const [isCopilotOpen, setIsCopilotOpen] = useState(false);
  const [selectedProject, setSelectedProject] = useState<string>("All");

  // API Data State
  const [dashboardData, setDashboardData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);

  const [p6Data, setP6Data] = useState<any[]>([]);
  const [sapData, setSapData] = useState<any[]>([]);
  const [logisticsData, setLogisticsData] = useState<any[]>([]);
  const [finDetails, setFinDetails] = useState<any[]>([]);
  const [logDetails, setLogDetails] = useState<any[]>([]);

  // Fetch Data
  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        const query = selectedProject !== 'All' ? `?project_name=${encodeURIComponent(selectedProject)}` : '';
        
        const [dashRes, p6Res, sapRes, logRes, finDetRes, logDetRes] = await Promise.all([
          fetch(`http://localhost:8000/api/dashboard/summary`),
          fetch(`http://localhost:8000/api/summary${query}`),
          fetch(`http://localhost:8000/api/financials${query}`),
          fetch(`http://localhost:8000/api/logistics${query}`),
          fetch(`http://localhost:8000/api/financials/details${query}`),
          fetch(`http://localhost:8000/api/logistics/details${query}`)
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
      } catch (error) {
        console.error("Error fetching dashboard data:", error);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [selectedProject]);

  // To cleanly track which modules are implemented
  const implementedModules = [
    'overview', 'project360', 'health', 'schedule', 'financial', 'procurement', 'material', 
    'risk', 'predictive', 'admin', 'reports', 'transmission_data',
    'ai_copilot', 'executive_brief', 'smart_search', 'knowledge_graph'
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
    <div className="flex h-screen w-full bg-background text-foreground overflow-hidden">
      
      {/* 1. Left Navigation Rail */}
      <LeftSidebar activeTab={activeTab} setActiveTab={handleTabChange} />
      
      {/* Middle Area: Header + Scrollable Content */}
      <div className="flex-1 flex flex-col min-w-0 relative bg-background">
        
        {/* 2. Top Global Header (hidden for full-screen Copilot) */}
        {activeTab !== 'ai_copilot' && (
          <TopHeader 
            selectedProject={selectedProject} 
            setSelectedProject={setSelectedProject} 
            masterProjects={Array.from(new Set(dashboardData?.projects?.map((p:any) => p.project_name) || []))} 
          />
        )}
        
        {/* 3a. Full-bleed AI Copilot (no padding, no scroll wrapper) */}
        {activeTab === 'ai_copilot' ? (
          <div className="flex-1 min-h-0 p-4">
            <AICopilot 
              onMinimize={() => {
                setActiveTab(previousTab);
                setIsCopilotOpen(true);
              }} 
            />
          </div>
        ) : (
          /* 3b. Normal Dashboard Area */
          <main className="flex-1 overflow-y-auto p-6 scroll-smooth custom-scrollbar relative">
            
            {/* Subtle Background Elements */}
            <div className="absolute top-0 left-1/4 w-[800px] h-[500px] bg-[#3B82F6] opacity-[0.03] blur-[150px] rounded-full pointer-events-none z-0"></div>

            <div className="relative z-10">
              {selectedProjectId ? (
                <ProjectWorkspace 
                  projectId={selectedProjectId} 
                  onBack={() => setSelectedProjectId(null)} 
                />
              ) : (
                <>
                  {activeTab === 'overview' && <ExecutiveOverview dashboardData={dashboardData} />}
                  {activeTab === 'project360' && <Project360 onOpenProject={setSelectedProjectId} />}
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
              {activeTab === 'smart_search' && <SmartSearch />}
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
          onMaximize={() => {
            setActiveTab('ai_copilot');
            setIsCopilotOpen(false);
          }} 
        />
      )}
    </div>
  );
}
