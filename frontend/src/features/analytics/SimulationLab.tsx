import React, { useState, useEffect } from 'react';
import { Search, ShieldAlert, Activity, AlertTriangle, Zap, CheckCircle2, ChevronRight, BarChart2, Eye, BrainCircuit, PlaySquare, Lightbulb, Sliders, Check, FileText, FastForward, Target, CloudRain, Wind, Bell } from 'lucide-react';
import ReactECharts from 'echarts-for-react';

// Location coordinates for weather lookup (from ProjectMap)
const SUBSTATION_COORDS: Record<string, { lat: number, lng: number }> = {
  'khavda': { lat: 24.024, lng: 69.337 },
  'bhuj': { lat: 23.379, lng: 69.592 },
  'bhadla': { lat: 27.618, lng: 72.206 },
  'fatehgarh': { lat: 26.285, lng: 71.100 },
  'ramgarh': { lat: 27.471, lng: 70.494 },
  'bikaner': { lat: 28.373, lng: 73.171 },
  'rajasthan': { lat: 27.0, lng: 74.2 },
  'gujarat': { lat: 23.0, lng: 72.5 },
  'halvad': { lat: 22.911, lng: 71.231 },
  'lakadia': { lat: 23.394, lng: 70.598 },
  'banaskantha': { lat: 24.090, lng: 72.000 },
  'sikar': { lat: 27.612, lng: 75.088 },
  'mandvi': { lat: 22.833, lng: 69.355 },
  'pirana': { lat: 22.872, lng: 72.557 },
  'mandsaur': { lat: 24.207, lng: 75.171 },
};

export default function SimulationLab({ p6Data = [], dashboardData = {}, initialProject = 'All', simulationContext }: any) {
  const [activeStep, setActiveStep] = useState(1);
  const [isScanning, setIsScanning] = useState(false);
  const [scanProgress, setScanProgress] = useState(0);
  const [showResults, setShowResults] = useState(false);

  const validProjects = dashboardData?.projects || [];
  let projects: any[] = Array.from(new Map(validProjects.map((p: any) => {
    const uniqueId = (p.mapping_id && p.mapping_id !== 'Not Found') ? p.mapping_id : (p.p6_project_name || p.p6?.id || p.project_name);
    return [uniqueId, {
      id: uniqueId,
      name: p.p6_project_name || p.p6?.id || p.project_name,
      raw_project_name: p.project_name,
      risk: p.p6?.health === 'Delayed' ? 85 : 40,
      spi: p.p6?.spi || p.p6?.schedule_performance_index || 0.85,
      critical: p.p6?.health === 'Delayed' || (p.p6?.spi && p.p6?.spi < 0.8),
      capacity: p.capacity_mwac ? Number(p.capacity_mwac).toFixed(1) : 0,
      progress: p.p6?.progress || 0
    }];
  })).values()).sort((a: any, b: any) => b.risk - a.risk);

  // Auto-inject missing initialProject (e.g., Transmission projects not in summary payload)
  if (initialProject && initialProject !== 'All') {
    const match = projects.find((p: any) => p.id === initialProject || p.name === initialProject || p.raw_project_name === initialProject);
    if (!match) {
      projects.push({
        id: initialProject,
        name: initialProject,
        raw_project_name: initialProject,
        risk: 90,
        spi: 0,
        critical: true,
        capacity: 0,
        progress: 0
      });
    }
  }

  const [selectedProject, setSelectedProject] = useState<string>(initialProject !== 'All' ? initialProject : (projects[0]?.id || 'All'));
  const [simulationData, setSimulationData] = useState<any>(null);
  const [autoRunPending, setAutoRunPending] = useState(false);

  // Sync with dashboard if initialProject changes dynamically
  useEffect(() => {
    if (initialProject && initialProject !== 'All') {
      const match = projects.find((p: any) => p.id === initialProject || p.name === initialProject || p.raw_project_name === initialProject);
      setSelectedProject(match ? match.id : initialProject);
    }
  }, [initialProject, projects.length]);

  // Jump to Step 2 if launched from a notification (simulationContext provided)
  useEffect(() => {
    if (simulationContext) {
      setActiveStep(2);
      if (simulationContext.message) {
        setCustomScenario(`Address delay: ${simulationContext.message}`);
      }
    }
  }, [simulationContext]);

  // Step 2 What-If Parameters
  const [recoveryPriority, setRecoveryPriority] = useState('Balanced');
  const [weatherMonsoon, setWeatherMonsoon] = useState('Normal');
  const [weatherWind, setWeatherWind] = useState('Normal');
  const [weatherData, setWeatherData] = useState<any>(null);
  const [weatherLoading, setWeatherLoading] = useState(false);
  const [projectNotifications, setProjectNotifications] = useState<any[]>([]);
  const [addedCrews, setAddedCrews] = useState(0);
  const [allowOvertime, setAllowOvertime] = useState(false);
  const [customScenario, setCustomScenario] = useState('');

  const [isGeneratingStrategies, setIsGeneratingStrategies] = useState(false);
  const [strategies, setStrategies] = useState<any[]>([]);
  const [selectedStrategyId, setSelectedStrategyId] = useState<string | null>(null);

  // Step 3 & 4 & 5 States
  const [simulationTimeline, setSimulationTimeline] = useState<any>(null);
  const [simulationPhase, setSimulationPhase] = useState<'config' | 'running' | 'complete'>('config');
  const [analysisDepth, setAnalysisDepth] = useState('Standard');
  const [accuracyLevel, setAccuracyLevel] = useState('High');
  const [simIterations, setSimIterations] = useState(0);
  const [simConvergence, setSimConvergence] = useState<number[]>([]);
  const [executionTasks, setExecutionTasks] = useState<any[]>([]);
  const [executionProgress, setExecutionProgress] = useState(0);
  const [reportData, setReportData] = useState<any>(null);
  const [resolvedTasks, setResolvedTasks] = useState<number[]>([]);

  const steps = [
    { id: 1, label: 'Detect', status: activeStep === 1 ? 'in-progress' : activeStep > 1 ? 'completed' : 'pending' },
    { id: 2, label: 'Strategies', status: activeStep === 2 ? 'in-progress' : activeStep > 2 ? 'completed' : 'pending' },
    { id: 3, label: 'Execute', status: activeStep === 3 ? 'in-progress' : activeStep > 3 ? 'completed' : 'pending' }
  ];

  // Helpers
  const isAll = selectedProject === 'All';
  const currentSpi = isAll
    ? (projects.reduce((acc: any, p: any) => acc + p.spi, 0) / (projects.length || 1)).toFixed(2)
    : (projects.find((p: any) => p.id === selectedProject)?.spi || 0);

  const currentRisk = isAll
    ? Math.round(projects.reduce((acc: any, p: any) => acc + p.risk, 0) / (projects.length || 1))
    : (projects.find((p: any) => p.id === selectedProject)?.risk || 40);

  const currentCompletion = isAll
    ? Math.round(projects.reduce((acc: any, p: any) => acc + p.progress, 0) / (projects.length || 1))
    : Math.round(projects.find((p: any) => p.id === selectedProject)?.progress || 0);

  const targetMw = isAll
    ? Math.round(projects.reduce((acc: any, p: any) => acc + (p.capacity || 0), 0))
    : (projects.find((p: any) => p.id === selectedProject)?.capacity || 0);

  const getProjectPayload = () => {
    if (isAll) {
      return {
        project_name: 'Entire Portfolio',
        health: currentRisk > 60 ? 'Delayed' : 'On Track',
        spi: currentSpi,
        progress: currentCompletion,
        capacity_mwac: targetMw
      };
    }
    const found = validProjects.find((p: any) =>
      p.mapping_id === selectedProject ||
      p.project_name === selectedProject ||
      p.p6_project_name === selectedProject ||
      p.p6?.id === selectedProject
    );
    if (found) return found;
    // Fallback for injected transmission projects
    return {
      project_name: selectedProject,
      health: 'Delayed',
      spi: 0,
      progress: 0,
      capacity_mwac: 0
    };
  };

  // ==========================================
  // STEP 1: DETECT
  // ==========================================
  useEffect(() => {
    if (simulationContext) {
      const issueDetails = simulationContext.message || 'General Delay';
      const component = simulationContext.block ? `${simulationContext.block} ${simulationContext.activity_name || ''}` : simulationContext.activity_name;

      const prompt = `Analyze recovery options for the following delay:\nComponent: ${component || 'Unknown'}\nIssue: ${issueDetails}`;
      setCustomScenario(prompt);

      if (activeStep === 1 && !isScanning && !showResults) {
        // Skip detection step and immediately jump to Strategies generation based on the notification
        setActiveStep(2);
        
        // Use a short timeout to ensure state is settled before calling the API
        setTimeout(() => {
          generateStrategies();
        }, 300);
      }
    }
  }, [simulationContext]);

  useEffect(() => {
    if (autoRunPending && selectedProject !== 'All') {
      const timer = setTimeout(() => {
        runSimulation();
        setAutoRunPending(false);
      }, 300);
      return () => clearTimeout(timer);
    }
  }, [selectedProject, autoRunPending]);

  // Weather Auto-Fetch Effect
  useEffect(() => {
    // Reset simulation state when project changes (unless handling a notification)
    if (!simulationContext) {
      setActiveStep(1);
      setIsScanning(false);
      setShowResults(false);
      setSimulationData(null);
      setStrategies([]);
      setSelectedStrategyId(null);
    }
    if (!selectedProject || selectedProject === 'All') {
      setWeatherData(null);
      return;
    }

    // Find project to get location name
    const proj = projects.find((p: any) => p.id === selectedProject);
    const projName = (proj?.raw_project_name || proj?.name || selectedProject).toLowerCase();

    // Try to match with SUBSTATION_COORDS
    let coords = null;
    for (const [key, value] of Object.entries(SUBSTATION_COORDS)) {
      if (projName.includes(key)) {
        coords = value;
        break;
      }
    }

    if (coords) {
      setWeatherLoading(true);
      fetch(`https://api.open-meteo.com/v1/forecast?latitude=${coords.lat}&longitude=${coords.lng}&daily=precipitation_sum,wind_speed_10m_max&timezone=auto&forecast_days=14`)
        .then(res => res.json())
        .then(data => {
          setWeatherData(data);

          if (data?.daily) {
            // Auto-classify Monsoon
            const avgRain = data.daily.precipitation_sum.reduce((a: number, b: number) => a + b, 0) / data.daily.precipitation_sum.length;
            if (avgRain > 40) setWeatherMonsoon('Severe');
            else if (avgRain > 10) setWeatherMonsoon('Heavy');
            else setWeatherMonsoon('Normal');

            // Auto-classify Wind
            const maxWind = Math.max(...data.daily.wind_speed_10m_max);
            if (maxWind > 30) setWeatherWind('High Alerts');
            else setWeatherWind('Normal');
          }
          setWeatherLoading(false);
        })
        .catch(() => {
          setWeatherLoading(false);
        });
    } else {
      setWeatherData(null);
    }
  }, [selectedProject]);


  const runSimulation = async () => {
    setIsScanning(true);
    setScanProgress(0);
    setShowResults(false);

    const interval = setInterval(() => {
      setScanProgress(p => p >= 90 ? 90 : p + 2);
    }, 100);

    try {
      const projectDetails = getProjectPayload();

      // Fetch all notifications for this project in parallel
      let allNotifs: any[] = [];
      try {
        const notifRes = await fetch('/akasha/api/notifications/');
        if (notifRes.ok) {
          const allN = await notifRes.json();
          const projName = projectDetails.project_name || selectedProject;
          allNotifs = allN.filter((n: any) => n.project_name === projName);
          setProjectNotifications(allNotifs);
        }
      } catch (e) { /* ignore notification fetch errors */ }

      const response = await fetch('/akasha/api/simulation-lab', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project: projectDetails,
          notification_context: simulationContext || null,
          all_notifications: allNotifs.slice(0, 15)
        })
      });

      const data = await response.json();
      setSimulationData(data);

      clearInterval(interval);
      setScanProgress(100);

      setTimeout(() => {
        setIsScanning(false);
        setShowResults(true);
      }, 500);
    } catch (error) {
      clearInterval(interval);
      setIsScanning(false);
      console.error("Simulation failed", error);
    }
  };

  // ==========================================
  // STEP 2: STRATEGIES
  // ==========================================
  const generateStrategies = async () => {
    setIsGeneratingStrategies(true);
    setStrategies([]);
    setSelectedStrategyId(null);
    try {
      const projectDetails = getProjectPayload();
      const response = await fetch('/akasha/api/simulation-lab/strategies', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project: projectDetails,
          constraints: {
            priority: recoveryPriority,
            weather_monsoon: weatherMonsoon,
            weather_wind: weatherWind,
            added_crews: addedCrews,
            allow_overtime: allowOvertime,
            custom_scenario: customScenario
          },
          notification_context: simulationContext || null,
          all_notifications: projectNotifications.slice(0, 10)
        })
      });
      const data = await response.json();
      setStrategies(data.strategies || []);
      if (data.strategies?.length > 0) {
        setSelectedStrategyId(data.strategies.find((s: any) => s.recommended)?.id || data.strategies[0].id);
      }
    } catch (error) {
      console.error("Strategies generation failed", error);
    } finally {
      setIsGeneratingStrategies(false);
    }
  };

  // Auto-generate strategies if triggered by notification
  useEffect(() => {
    if (activeStep === 2 && simulationContext && strategies.length === 0 && !isGeneratingStrategies) {
      generateStrategies();
    }
  }, [activeStep, simulationContext]);

  // ==========================================
  // STEP 3: SIMULATE
  // ==========================================
  const proceedToSimulation = () => {
    setActiveStep(3);
    startActualSimulation();
  };

  const startActualSimulation = async () => {
    setSimulationPhase('running');
    setSimIterations(0);
    setSimConvergence([]);

    // Simulate loading animation
    let iters = 0;
    const loader = setInterval(() => {
      iters += 300;
      if (iters >= 10000) {
        clearInterval(loader);
        setSimulationPhase('complete');
      } else {
        setSimIterations(iters);
        setSimConvergence(prev => [...prev, 70 + Math.random() * 20]);
      }
    }, 150);

    try {
      const projectDetails = getProjectPayload();
      const selStrat = strategies.find(s => s.id === selectedStrategyId) || {};
      const response = await fetch('/akasha/api/simulation-lab/simulate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project: projectDetails, strategy: selStrat, notification_context: simulationContext || null })
      });
      const data = await response.json();
      setSimulationTimeline(data);
    } catch (e) { console.error(e); }
  };

  // ==========================================
  // STEP 4: EXECUTE
  // ==========================================
  const executeStrategy = async () => {
    setActiveStep(3);
    setExecutionProgress(0);
    try {
      const projectDetails = getProjectPayload();
      const selStrat = strategies.find(s => s.id === selectedStrategyId) || {};
      const response = await fetch('/akasha/api/simulation-lab/execute', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project: projectDetails, strategy: selStrat })
      });
      const data = await response.json();
      setExecutionTasks(data.tasks);

      // Animate execution progress
      let p = 0;
      const execInterval = setInterval(() => {
        p += 5;
        setExecutionProgress(p);
        if (p >= 100) {
          clearInterval(execInterval);
        }
      }, 150);

    } catch (e) { console.error(e); }
  };

  // ==========================================
  // STEP 5: REPORT
  // ==========================================
  const generateFinalReport = async () => {
    setActiveStep(4);
    try {
      const projectDetails = getProjectPayload();
      const selStrat = strategies.find(s => s.id === selectedStrategyId) || {};
      const response = await fetch('/akasha/api/simulation-lab/report', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project: projectDetails, strategy: selStrat, notification_context: simulationContext || null })
      });
      const data = await response.json();
      setReportData(data);
    } catch (e) { console.error(e); }
  };

  const impactData = simulationData?.variance?.schedule_impact || {};
  const impactKeys = Object.keys(impactData).length > 0 ? Object.keys(impactData) : ['Foundation', 'Module Inst.', 'Grid Conn.'];
  const impactValues = Object.keys(impactData).length > 0 ? Object.values(impactData) : [0, 0, 0];

  const scheduleImpactChartOptions = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: '3%', right: '4%', bottom: '3%', top: '10%', containLabel: true },
    xAxis: {
      type: 'value', name: 'Days Delayed',
      axisLabel: { color: 'var(--muted-foreground)' },
      splitLine: { lineStyle: { color: 'var(--border)' } }
    },
    yAxis: {
      type: 'category',
      data: impactKeys,
      axisLabel: { color: 'var(--foreground)', fontWeight: 'bold' }
    },
    series: [
      {
        name: 'Impact',
        type: 'bar',
        data: impactValues,
        itemStyle: { color: '#EF4444' }
      }
    ]
  };

  const radarOptions = {
    backgroundColor: 'transparent',
    tooltip: {},
    radar: {
      indicator: [
        { name: 'Feasibility', max: 100 },
        { name: 'Cost Eff.', max: 100 },
        { name: 'Speed', max: 100 },
        { name: 'Risk Reduction', max: 100 },
        { name: 'Confidence', max: 100 }
      ],
      axisName: { color: 'var(--muted-foreground)', fontWeight: 'bold' },
      splitLine: { lineStyle: { color: 'var(--border)', opacity: 0.5 } },
      splitArea: { show: false }
    },
    series: [{
      type: 'radar',
      data: [
        {
          value: strategies.find(s => s.id === selectedStrategyId)?.radar_data || [50, 50, 50, 50, 50],
          name: 'Strategy Profile',
          areaStyle: { color: 'rgba(59, 130, 246, 0.2)' },
          lineStyle: { color: '#3B82F6', width: 2 },
          itemStyle: { color: '#3B82F6' }
        }
      ]
    }]
  };

  const timelineData = Array.isArray(simulationTimeline) ? simulationTimeline : (simulationTimeline?.timeline || []);

  const timelineOptions = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    legend: { bottom: 0, textStyle: { color: 'var(--foreground)' } },
    grid: { left: '3%', right: '4%', bottom: '10%', top: '5%', containLabel: true },
    xAxis: { type: 'category', data: timelineData.map((t: any) => t.month) || [], axisLabel: { color: 'var(--foreground)' } },
    yAxis: { type: 'value', name: 'Completion %', max: 100, axisLabel: { color: 'var(--foreground)' }, splitLine: { lineStyle: { color: 'var(--border)' } } },
    series: [
      { name: 'Baseline Trajectory', type: 'line', data: timelineData.map((t: any) => t.baseline) || [], itemStyle: { color: '#EF4444' }, lineStyle: { width: 3, type: 'dashed' } },
      { name: 'Simulated Strategy', type: 'line', data: timelineData.map((t: any) => t.simulated) || [], itemStyle: { color: '#10B981' }, lineStyle: { width: 3 }, areaStyle: { color: 'rgba(16, 185, 129, 0.1)' } }
    ]
  };

  const convergenceChartOptions = {
    backgroundColor: 'transparent',
    grid: { left: '2%', right: '2%', bottom: '5%', top: '10%', containLabel: false },
    xAxis: { type: 'category', boundaryGap: false, show: false },
    yAxis: { type: 'value', min: 0, max: 100, show: false },
    series: [{
      type: 'line',
      smooth: true,
      data: simConvergence,
      lineStyle: { color: '#8B5CF6', width: 2 },
      areaStyle: {
        color: 'rgba(139, 92, 246, 0.1)'
      },
      itemStyle: { color: '#8B5CF6' },
      symbol: 'none'
    }]
  };

  const baseP10 = simulationTimeline?.baseline?.completion_dates?.p10 || '';
  const baseP50 = simulationTimeline?.baseline?.completion_dates?.p50 || '';
  const baseP90 = simulationTimeline?.baseline?.completion_dates?.p90 || '';

  const simP10 = simulationTimeline?.simulated?.completion_dates?.p10 || '';
  const simP50 = simulationTimeline?.simulated?.completion_dates?.p50 || '';
  const simP90 = simulationTimeline?.simulated?.completion_dates?.p90 || '';

  const getDayDiff = (d1: string, d2: string) => {
    if (!d1 || !d2) return 0;
    return Math.round((new Date(d1).getTime() - new Date(d2).getTime()) / (1000 * 3600 * 24));
  };

  const histogramOptions = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { bottom: 0, textStyle: { color: 'var(--foreground)' } },
    grid: { left: '3%', right: '4%', bottom: '15%', top: '10%', containLabel: true },
    xAxis: {
      type: 'value',
      name: 'Variance (Days from Baseline P50)',
      axisLabel: { color: 'var(--muted-foreground)', fontSize: 10 }
    },
    yAxis: { type: 'category', data: ['P10 (Optimistic)', 'P50 (Most Likely)', 'P90 (Pessimistic)'], axisLabel: { color: 'var(--foreground)', fontSize: 10 } },
    series: [
      {
        name: 'Baseline',
        type: 'bar',
        data: simulationTimeline ? [getDayDiff(baseP10, baseP50), 0, getDayDiff(baseP90, baseP50)] : [-15, 0, 25],
        itemStyle: { color: '#EF4444' }
      },
      {
        name: 'Simulated Strategy',
        type: 'bar',
        data: simulationTimeline ? [getDayDiff(simP10, baseP50), getDayDiff(simP50, baseP50), getDayDiff(simP90, baseP50)] : [-25, -10, 10],
        itemStyle: { color: '#10B981' }
      }
    ]
  };

  return (
    <div className="h-full flex flex-col overflow-hidden">

      {/* HEADER & STEPS */}
      <div className="shrink-0 flex justify-between items-center pb-4 border-b border-border mb-4">
        <div className="flex items-center gap-2 text-primary font-bold tracking-wide">
          <Activity className="w-5 h-5" />
          <h2>SIMULATION LAB</h2>
        </div>

        <div className="flex items-center gap-2 p-1.5 rounded-full bg-background/40 backdrop-blur-xl border border-border/50 shadow-sm">
            {steps.map((step, idx) => {
              const isActive = step.status === 'in-progress';
              const isCompleted = step.status === 'completed';
              
              return (
                <div 
                  key={step.id} 
                  className={`relative flex items-center justify-center h-10 rounded-full transition-all duration-500 ease-out cursor-pointer ${
                    isActive 
                      ? 'px-5 bg-gradient-to-r from-blue-600 to-indigo-600 shadow-[0_0_20px_rgba(79,70,229,0.4)]' 
                      : isCompleted 
                        ? 'w-10 bg-success/100/10 hover:bg-success/100/20' 
                        : 'w-10 bg-transparent hover:bg-muted'
                  }`}
                  onClick={() => { if (isCompleted) setActiveStep(step.id); }}
                >
                  {/* Icon / Number */}
                  <div className={`flex items-center justify-center ${isActive ? 'text-white mr-2' : isCompleted ? 'text-success' : 'text-muted-foreground'}`}>
                    {isCompleted ? <CheckCircle2 className="w-5 h-5" /> : <span className="text-sm font-bold">{step.id}</span>}
                  </div>
                  
                  {/* Label (Only visible when active) */}
                  <div 
                    className={`overflow-hidden transition-all duration-500 ${
                      isActive ? 'max-w-[120px] opacity-100' : 'max-w-0 opacity-0'
                    }`}
                  >
                    <span className="text-sm font-bold text-white whitespace-nowrap">
                      {step.label}
                    </span>
                  </div>

                  {/* Connecting Dot (between steps) */}
                  {idx < steps.length - 1 && !isActive && (
                    <div className="absolute -right-2 top-1/2 -translate-y-1/2 w-1 h-1 rounded-full bg-border"></div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

      <div className="flex-1 overflow-y-auto pb-20 pr-2" onWheel={(e) => e.stopPropagation()} onTouchMove={(e) => e.stopPropagation()}>
        <div className="w-full space-y-6">

          {/* ========================================== */}
          {/* STEP 1: DETECT */}
          {/* ========================================== */}
          {activeStep === 1 && (
            <>
              {/* Context Banner */}
              {simulationContext && (
                <div className="bg-warning/100/10 border border-warning/20 rounded-xl p-4 mb-6 animate-in fade-in slide-in-from-top-4">
                  <div className="flex items-start gap-3">
                    <div className="bg-warning/100/20 p-2 rounded-lg">
                      <Bell className="w-5 h-5 text-warning" />
                    </div>
                    <div>
                      <h4 className="text-sm font-bold text-warning dark:text-warning uppercase tracking-widest mb-1">Triggered by Notification</h4>
                      <p className="text-sm font-medium text-foreground">
                        {simulationContext.change_type} on <span className="font-bold">{simulationContext.block || ''} {simulationContext.activity_name}</span>
                      </p>
                      {simulationContext.old_value && simulationContext.new_value && (
                        <p className="text-xs text-muted-foreground mt-1">
                          Changed from <span className="line-through">{simulationContext.old_value}</span> to <span className="font-bold">{simulationContext.new_value}</span>
                        </p>
                      )}
                      {simulationContext.message && (
                        <p className="text-xs text-muted-foreground mt-1 bg-background/50 p-2 rounded border border-border/50">"{simulationContext.message}"</p>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {/* Scope Selector */}
              {(isScanning || showResults) ? (
                /* Compact project indicator when simulation is active */
                <div className="bg-card rounded-xl border border-border shadow-sm px-5 py-3 flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center">
                      <Activity className="w-4 h-4 text-primary" />
                    </div>
                    <div>
                      <p className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest">Simulating</p>
                      <p className="text-sm font-bold text-foreground">{isAll ? 'Entire Portfolio' : (projects.find((p: any) => p.id === selectedProject)?.name || selectedProject)}</p>
                    </div>
                    {!isAll && (() => {
                      const proj = projects.find((p: any) => p.id === selectedProject);
                      return proj ? (
                        <div className="flex items-center gap-2 ml-3">
                          <span className={`text-[9px] font-extrabold uppercase tracking-widest px-2 py-0.5 rounded-md ${proj.critical ? 'bg-destructive/100/15 text-destructive border border-destructive/20' : 'bg-warning/100/15 text-warning border border-warning/20'}`}>
                            SPI {proj.spi}
                          </span>
                          <span className="text-[11px] font-semibold text-muted-foreground flex items-center gap-1">
                            <Zap className="w-3 h-3 text-success" />{proj.capacity} MW
                          </span>
                        </div>
                      ) : null;
                    })()}
                  </div>
                  <button
                    onClick={() => { setShowResults(false); setIsScanning(false); setScanProgress(0); setSimulationData(null); }}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border bg-muted hover:bg-muted text-xs font-semibold text-muted-foreground hover:text-foreground transition-colors"
                  >
                    <Search className="w-3.5 h-3.5" /> Change Project
                  </button>
                </div>
              ) : (
                /* Full project selector when idle */
                <div className="bg-card rounded-xl border border-border shadow-sm p-5">
                  <h3 className="text-xs font-bold text-muted-foreground uppercase tracking-widest mb-3">Select Scope</h3>
                  <div className="relative mb-4">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                    <input type="text" placeholder={`Search ${projects.length} tracked projects...`} className="w-full bg-muted border border-border rounded-lg pl-10 pr-4 py-2 text-sm focus:outline-none focus:border-primary transition-colors text-foreground placeholder:text-muted-foreground" />
                  </div>

                  <div className="flex items-center gap-4 overflow-x-auto pb-4 custom-scrollbar" onWheel={(e) => e.stopPropagation()} onTouchMove={(e) => e.stopPropagation()}>
                    <div
                      onClick={() => setSelectedProject('All')}
                      className={`shrink-0 flex flex-col justify-center items-center gap-2 px-6 h-[96px] min-w-[140px] rounded-2xl border cursor-pointer transition-all relative overflow-hidden ${selectedProject === 'All' ? 'border-primary bg-primary/10 shadow-[0_8px_30px_rgba(79,70,229,0.15)] ring-1 ring-primary/30 text-primary' : 'border-border bg-card hover:bg-muted text-muted-foreground hover:text-foreground'}`}
                    >
                      {selectedProject === 'All' && <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-blue-600 to-indigo-600"></div>}
                      <Activity className={`w-6 h-6 ${selectedProject === 'All' ? 'text-primary' : ''}`} />
                      <span className="font-bold text-sm tracking-wide">All Projects</span>
                    </div>
                    {projects.map((p: any) => (
                      <div
                        key={p.id}
                        onClick={() => setSelectedProject(p.id)}
                        className={`group shrink-0 flex flex-col justify-between p-3.5 h-[96px] rounded-2xl border cursor-pointer transition-all min-w-[260px] max-w-[280px] relative overflow-hidden ${selectedProject === p.id ? 'border-primary bg-primary/5 shadow-[0_8px_30px_rgba(79,70,229,0.12)] ring-1 ring-primary/30' : 'border-border bg-card hover:border-primary/40 hover:shadow-md'}`}
                      >
                        {/* Active Indicator Line */}
                        {selectedProject === p.id && <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-blue-600 to-indigo-600"></div>}

                        <div className="flex items-start justify-between gap-3">
                          <div className="flex flex-col overflow-hidden w-full">
                            <span className="text-[13px] font-extrabold text-foreground truncate group-hover:text-primary transition-colors mb-0.5" title={p.name}>{p.name}</span>
                            <div className="flex items-center gap-2 text-[10px] font-bold text-muted-foreground uppercase tracking-widest">
                              <span className="flex items-center gap-1">
                                <ShieldAlert className={`w-3 h-3 ${p.critical ? 'text-destructive' : 'text-warning'}`} />
                                Risk: <span className={p.critical ? 'text-destructive dark:text-destructive' : 'text-warning dark:text-warning'}>{p.risk}</span>
                              </span>
                              <span className="w-1 h-1 rounded-full bg-border"></span>
                              <span className={p.critical ? 'text-destructive dark:text-destructive' : 'text-warning dark:text-warning'}>
                                SPI: {p.spi}
                              </span>
                            </div>
                          </div>
                        </div>
                        
                        <div className="flex items-center justify-between pt-2 border-t border-border/50">
                          <div className="flex items-center gap-1.5">
                            <div className={`relative flex h-2 w-2`}>
                              {p.critical && <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span>}
                              <span className={`relative inline-flex rounded-full h-2 w-2 ${p.critical ? 'bg-destructive/100' : 'bg-warning/100'}`}></span>
                            </div>
                            <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">{p.critical ? 'Critical Delay' : 'At Risk'}</span>
                          </div>
                          <span className="flex items-baseline gap-1 text-[11px] font-extrabold text-foreground bg-muted px-2 py-0.5 rounded-md">
                            <Zap className="w-3 h-3 text-success shrink-0" /> {p.capacity} <span className="text-[9px] text-muted-foreground">MW</span>
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {!isScanning && !showResults && (
                <button
                  onClick={runSimulation}
                  className="w-full bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white font-bold py-4 rounded-xl shadow-lg transition-all flex items-center justify-center gap-2 animate-in fade-in zoom-in duration-300"
                >
                  <Zap className="w-5 h-5 fill-current" /> Run Problem Detection
                </button>
              )}

              {isScanning && (
                <div className="bg-card rounded-xl border border-blue-500/30 shadow-lg p-6 animate-in fade-in slide-in-from-bottom-4">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2 text-primary font-bold">
                      <Search className="w-5 h-5 animate-pulse" /> Scanning Data...
                    </div>
                    <div className="text-primary font-mono font-bold">{scanProgress}%</div>
                  </div>
                  <div className="w-full h-1.5 bg-muted rounded-full overflow-hidden mb-6">
                    <div className="h-full bg-gradient-to-r from-blue-500 via-indigo-500 to-purple-500" style={{ width: `${scanProgress}%`, transition: 'width 0.1s linear' }}></div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div className="bg-primary/10/50 border border-primary/20 rounded-lg p-4">
                      <div className="flex items-center gap-2 text-primary font-bold text-xs uppercase tracking-widest mb-3">
                        <Eye className="w-4 h-4" /> Seeing
                      </div>
                      <ul className="space-y-2 text-xs font-medium text-foreground/80 list-disc pl-4">
                        <li className={scanProgress > 10 ? 'opacity-100' : 'opacity-30 transition-opacity'}>Reading live schedules for {selectedProject}...</li>
                        <li className={scanProgress > 30 ? 'opacity-100' : 'opacity-30 transition-opacity'}>Scanning SPI/CPI metrics...</li>
                        <li className={scanProgress > 50 ? 'opacity-100 text-primary font-semibold' : 'opacity-30 transition-opacity'}>Pulling supply chain data from SAP MM...</li>
                      </ul>
                    </div>
                    <div className="bg-primary/10/50 border border-primary/20 rounded-lg p-4">
                      <div className="flex items-center gap-2 text-primary font-bold text-xs uppercase tracking-widest mb-3">
                        <Activity className="w-4 h-4" /> Analyzing
                      </div>
                      <ul className="space-y-2 text-xs font-medium text-foreground/80 list-disc pl-4">
                        <li className={scanProgress > 40 ? 'opacity-100' : 'opacity-0 transition-opacity'}>{selectedProject} SPI vs threshold...</li>
                        <li className={scanProgress > 60 ? 'opacity-100' : 'opacity-0 transition-opacity'}>Analyzing weather overlap...</li>
                        <li className={scanProgress > 80 ? 'opacity-100 text-primary font-semibold' : 'opacity-0 transition-opacity'}>Cross-referencing budget variance...</li>
                      </ul>
                    </div>
                    <div className="bg-success/10/50 border border-success/20 rounded-lg p-4">
                      <div className="flex items-center gap-2 text-success font-bold text-xs uppercase tracking-widest mb-3">
                        <PlaySquare className="w-4 h-4" /> Doing
                      </div>
                      <ul className="space-y-2 text-xs font-medium text-foreground/80 list-disc pl-4">
                        <li className={scanProgress > 60 ? 'opacity-100' : 'opacity-0 transition-opacity'}>Querying baselines...</li>
                        <li className={scanProgress > 80 ? 'opacity-100' : 'opacity-0 transition-opacity'}>Running anomaly detection...</li>
                        <li className={scanProgress > 95 ? 'opacity-100 text-success font-semibold' : 'opacity-0 transition-opacity'}>Classifying issues...</li>
                      </ul>
                    </div>
                  </div>
                </div>
              )}

              {showResults && (
                <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
                  <div className="grid grid-cols-4 gap-4">
                    <div className="bg-card rounded-xl border border-border shadow-sm p-5">
                      <div className="text-xs font-bold text-muted-foreground uppercase tracking-widest mb-1 flex items-center gap-1.5"><Activity className="w-4 h-4" /> SPI</div>
                      <div className={`text-3xl font-bold ${currentSpi < 0.85 ? 'text-destructive' : 'text-success'}`}>{currentSpi}</div>
                    </div>
                    <div className="bg-card rounded-xl border border-border shadow-sm p-5">
                      <div className="text-xs font-bold text-muted-foreground uppercase tracking-widest mb-1 flex items-center gap-1.5"><ShieldAlert className="w-4 h-4" /> Risk Score</div>
                      <div className={`text-3xl font-bold ${currentRisk > 70 ? 'text-destructive' : 'text-success'}`}>{currentRisk}</div>
                    </div>
                    <div className="bg-card rounded-xl border border-border shadow-sm p-5">
                      <div className="text-xs font-bold text-muted-foreground uppercase tracking-widest mb-1 flex items-center gap-1.5"><BarChart2 className="w-4 h-4" /> Completion</div>
                      <div className="text-3xl font-bold text-warning">{currentCompletion}%</div>
                    </div>
                    <div className="bg-card rounded-xl border border-border shadow-sm p-5">
                      <div className="text-xs font-bold text-muted-foreground uppercase tracking-widest mb-1 flex items-center gap-1.5"><Zap className="w-4 h-4" /> Target MW</div>
                      <div className="text-3xl font-bold text-foreground">{targetMw || '0'} MW</div>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    {/* AI Detected Issues Panel */}
                    <div className="bg-card rounded-xl border border-border shadow-sm overflow-hidden flex flex-col h-[400px]">
                      <div className="bg-muted px-5 py-4 border-b border-border flex items-center gap-3 shrink-0">
                        <AlertTriangle className="w-5 h-5 text-warning" />
                        <h3 className="font-bold text-foreground">Detected Issues</h3>
                      </div>
                      <div className="p-4 flex-1 overflow-y-auto space-y-4 pr-2 custom-scrollbar" onWheel={(e) => e.stopPropagation()} onTouchMove={(e) => e.stopPropagation()}>
                        {simulationData?.issues?.map((issue: any, i: number) => (
                          <div key={i} className={`flex gap-3 p-4 bg-muted hover:bg-muted rounded-xl transition-colors border-l-4 ${issue.severity === 'Critical' ? 'border-red-500' : 'border-amber-500'}`}>
                            <div className={`mt-1 w-2.5 h-2.5 rounded-full shrink-0 ${issue.severity === 'Critical' ? 'bg-destructive/100 shadow-[0_0_8px_rgba(239,68,68,0.5)]' : 'bg-warning/100'}`}></div>
                            <div className="flex-1">
                              <div className="flex items-center justify-between mb-2">
                                <span className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full ${issue.severity === 'Critical' ? 'text-destructive bg-destructive/10' : 'text-warning bg-warning/10'}`}>{issue.severity}</span>
                              </div>
                              <p className="text-sm text-foreground/90 leading-relaxed">{issue.title}</p>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Notification History Panel */}
                    {(projectNotifications && projectNotifications.length > 0) ? (
                      <div className="bg-card rounded-xl border border-border shadow-sm p-5 flex flex-col h-[400px]">
                        <h3 className="text-sm font-bold mb-4 uppercase tracking-widest text-muted-foreground border-b border-border pb-2 shrink-0 flex items-center gap-2">
                          <Bell className="w-4 h-4" /> Notification History
                        </h3>
                        <div className="flex-1 overflow-y-auto pr-2 custom-scrollbar space-y-2" onWheel={(e) => e.stopPropagation()} onTouchMove={(e) => e.stopPropagation()}>
                          {(() => {
                            const grouped = projectNotifications.reduce((acc: any, notif: any) => {
                              const block = notif.block || 'General Updates';
                              if (!acc[block]) acc[block] = [];
                              acc[block].push(notif);
                              return acc;
                            }, {});

                            return Object.entries(grouped).map(([block, notifs]: [string, any]) => (
                              <details key={block} className="group border border-border rounded-lg overflow-hidden" open={block !== 'General Updates'}>
                                <summary className="flex items-center justify-between p-3 cursor-pointer bg-muted hover:bg-muted transition-colors font-bold text-xs uppercase tracking-wider text-foreground select-none list-none [&::-webkit-details-marker]:hidden">
                                  <div className="flex items-center gap-2">
                                    <div className="w-5 h-5 rounded flex items-center justify-center bg-background border border-border shadow-sm text-[10px] group-open:bg-primary group-open:text-primary-foreground transition-colors">
                                      {notifs.length}
                                    </div>
                                    {block}
                                  </div>
                                  <ChevronRight className="w-4 h-4 text-muted-foreground group-open:rotate-90 transition-transform" />
                                </summary>
                                <div className="p-2 space-y-2 bg-card border-t border-border">
                                  {notifs.map((notif: any, i: number) => (
                                    <div key={notif.id || i} className="p-2.5 bg-muted border border-border rounded flex flex-col gap-1.5 shadow-sm">
                                      <div className="flex items-center justify-between">
                                        <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">{new Date(notif.created_at).toLocaleDateString()}</span>
                                        <span className={`text-[9px] font-bold uppercase px-2 py-0.5 rounded-full ${notif.change_type?.includes('Delay') || notif.change_type?.includes('Slip') ? 'bg-destructive/100/10 text-destructive' : 'bg-primary/100/10 text-primary'}`}>
                                          {notif.change_type || notif.category}
                                        </span>
                                      </div>
                                      <p className="text-xs font-semibold text-foreground">{notif.activity_name}</p>
                                      <p className="text-[11px] text-muted-foreground line-clamp-2">{notif.message}</p>
                                    </div>
                                  ))}
                                </div>
                              </details>
                            ));
                          })()}
                        </div>
                      </div>
                    ) : (
                      <div className="bg-card rounded-xl border border-border shadow-sm p-5 flex flex-col h-[400px]">
                        {/* Schedule Impact Chart Panel */}
                        <h3 className="text-sm font-bold mb-4 uppercase tracking-widest text-muted-foreground border-b border-border pb-2 shrink-0">Schedule Impact Forecast</h3>
                        <div className="flex-1 min-h-0">
                          <ReactECharts option={scheduleImpactChartOptions} style={{height: '100%', width: '100%'}} />
                        </div>
                      </div>
                    )}
                  </div>

                  <button 
                    onClick={() => setActiveStep(2)}
                    className="w-full bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white font-bold py-4 rounded-xl shadow-lg transition-all flex items-center justify-center gap-2 mt-6"
                  >
                    <FastForward className="w-5 h-5 fill-current" /> Proceed to Strategy Selection
                  </button>
                </div>
              )}
        </>
          )}

        {/* ========================================== */}
        {/* STEP 2: STRATEGIES */}
        {/* ========================================== */}
        {activeStep === 2 && (
          <div className="flex gap-6 animate-in fade-in">
            {/* Constraints Sidebar */}
            <div className="w-[320px] shrink-0 bg-card border border-border rounded-xl shadow-sm p-5 flex flex-col gap-6">
              <div className="flex items-center gap-2 border-b border-border pb-3">
                <Sliders className="w-4 h-4 text-primary" />
                <h3 className="font-bold uppercase tracking-wider text-sm">Constraints</h3>
              </div>

              <div>
                <label className="text-xs font-bold text-muted-foreground uppercase tracking-widest mb-2 block">Recovery Priority</label>
                <div className="flex bg-muted p-1 rounded-lg border border-border">
                  {['Fastest', 'Balanced', 'Cheapest'].map(p => (
                    <button
                      key={p}
                      onClick={() => setRecoveryPriority(p)}
                      className={`flex-1 text-xs font-bold py-1.5 rounded transition-all ${recoveryPriority === p ? 'bg-background shadow text-foreground' : 'text-muted-foreground hover:text-foreground'}`}
                    >
                      {p}
                    </button>
                  ))}
                </div>
              </div>

              <div className="space-y-4">
                {/* Weather Live Panel */}
                <div className="bg-gradient-to-br from-slate-50 to-slate-100 dark:from-slate-800/50 dark:to-slate-900/50 border border-border dark:border-slate-700 p-3 rounded-lg relative overflow-hidden">
                  <div className="absolute top-0 right-0 w-24 h-24 bg-primary/100/10 rounded-full blur-2xl -translate-y-1/2 translate-x-1/3"></div>
                  <div className="relative z-10">
                    <div className="flex items-center gap-2 mb-3">
                      <CloudRain className="w-4 h-4 text-primary" />
                      <h4 className="text-xs font-bold uppercase tracking-widest text-foreground dark:text-muted-foreground">Live Weather Context</h4>
                    </div>

                    {weatherLoading ? (
                      <div className="text-xs text-muted-foreground animate-pulse">Fetching 14-day forecast...</div>
                    ) : weatherData ? (
                      <div className="space-y-3">
                        {/* Monsoon Row */}
                        <div>
                          <div className="flex items-center justify-between mb-1.5">
                            <span className="text-[11px] font-semibold text-muted-foreground">Rainfall (14d avg)</span>
                            <span className="text-[10px] font-bold bg-primary/10 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300 px-1.5 py-0.5 rounded">
                              {weatherMonsoon}
                            </span>
                          </div>
                          <div className="flex bg-background border border-border rounded-md overflow-hidden">
                            {['Normal', 'Heavy', 'Severe'].map(w => (
                              <button
                                key={w}
                                onClick={() => setWeatherMonsoon(w)}
                                className={`flex-1 text-[10px] font-bold py-1 transition-all ${weatherMonsoon === w ? 'bg-primary/100 text-white' : 'text-muted-foreground hover:bg-muted'}`}
                              >
                                {w}
                              </button>
                            ))}
                          </div>
                        </div>

                        {/* Wind Row */}
                        <div>
                          <div className="flex items-center justify-between mb-1.5">
                            <span className="text-[11px] font-semibold text-muted-foreground">Wind (Max)</span>
                            <span className="text-[10px] font-bold bg-teal-100 text-teal-700 dark:bg-teal-900/40 dark:text-teal-300 px-1.5 py-0.5 rounded">
                              {weatherWind}
                            </span>
                          </div>
                          <div className="flex bg-background border border-border rounded-md overflow-hidden">
                            {['Normal', 'High Alerts'].map(w => (
                              <button
                                key={w}
                                onClick={() => setWeatherWind(w)}
                                className={`flex-1 text-[10px] font-bold py-1 transition-all ${weatherWind === w ? 'bg-teal-500 text-white' : 'text-muted-foreground hover:bg-muted'}`}
                              >
                                {w}
                              </button>
                            ))}
                          </div>
                        </div>
                      </div>
                    ) : (
                      <div className="text-xs text-muted-foreground">No weather data for this location. Standard conditions assumed.</div>
                    )}
                  </div>
                </div>

                <div>
                  <div className="flex justify-between text-xs font-bold mb-2">
                    <span className="text-muted-foreground uppercase tracking-widest">Add Foundation Crews</span>
                    <span className="text-success">+{addedCrews} Crews</span>
                  </div>
                  <input type="range" min="0" max="5" value={addedCrews} onChange={e => setAddedCrews(Number(e.target.value))} className="w-full accent-emerald-500 h-1.5 bg-muted rounded-lg appearance-none cursor-pointer" />
                  <div className="flex justify-between text-[10px] text-muted-foreground mt-1"><span>0</span><span>+5</span></div>
                </div>

                <div>
                  <label className="text-xs font-bold text-muted-foreground uppercase tracking-widest mb-2 block">Custom Scenario</label>
                  <textarea
                    rows={3}
                    placeholder="e.g. What if module delivery is delayed by 3 weeks?"
                    value={customScenario}
                    onChange={e => setCustomScenario(e.target.value)}
                    className="w-full bg-muted border border-border rounded-lg p-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary resize-none placeholder:text-muted-foreground/50"
                  />
                </div>
              </div>

              <div className="border-t border-border pt-4 space-y-3">
                <h4 className="text-xs font-bold text-muted-foreground uppercase tracking-widest">Execution Constraints</h4>
                <label className="flex items-center gap-3 cursor-pointer">
                  <div className={`w-10 h-5 rounded-full p-1 transition-colors ${allowOvertime ? 'bg-success/100' : 'bg-muted-foreground/30'}`} onClick={() => setAllowOvertime(!allowOvertime)}>
                    <div className={`w-3 h-3 bg-white rounded-full transition-transform ${allowOvertime ? 'translate-x-5' : 'translate-x-0'}`}></div>
                  </div>
                  <span className="text-sm font-medium">Allow overtime shifts</span>
                </label>
              </div>

              <button
                onClick={generateStrategies}
                disabled={isGeneratingStrategies}
                className="w-full mt-auto bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white font-bold py-3 rounded-lg shadow transition-all flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <Activity className="w-4 h-4 fill-current" />
                {isGeneratingStrategies ? 'Generating...' : 'Generate Strategies'}
              </button>
            </div>

            {/* Main Area */}
            <div className="flex-1 flex flex-col gap-4">
              {!strategies.length && !isGeneratingStrategies ? (
                <div className="flex-1 border-2 border-dashed border-border rounded-xl flex items-center justify-center bg-white/50">
                  <div className="text-center max-w-sm">
                    <div className="w-16 h-16 bg-muted rounded-full flex items-center justify-center mx-auto mb-4"><Activity className="w-8 h-8 text-muted-foreground" /></div>
                    <h3 className="font-bold text-lg mb-2">Ready to Generate</h3>
                    <p className="text-sm text-muted-foreground">Configure your recovery priority and constraints, then click <strong className="text-foreground">Generate Strategies</strong> to get optimized recovery options.</p>
                  </div>
                </div>
              ) : isGeneratingStrategies ? (
                <div className="flex-1 border border-border rounded-xl flex items-center justify-center bg-card shadow-sm">
                  <div className="text-center max-w-sm">
                    <div className="w-16 h-16 bg-purple-100 rounded-full flex items-center justify-center mx-auto mb-4 animate-pulse"><Activity className="w-8 h-8 text-purple-600" /></div>
                    <h3 className="font-bold text-lg mb-2 animate-pulse">Running Strategy Models...</h3>
                    <p className="text-sm text-muted-foreground">Simulating thousands of permutations against your constraints.</p>
                  </div>
                </div>
              ) : (
                <div className="flex gap-6 h-full">
                  {/* Strategies List */}
                  <div className="flex-1 space-y-4 overflow-y-auto pb-4 custom-scrollbar pr-2" onWheel={(e) => e.stopPropagation()} onTouchMove={(e) => e.stopPropagation()}>
                    <div className="flex items-center justify-between mb-2">
                      <h3 className="font-bold flex items-center gap-2"><Activity className="w-4 h-4 text-purple-600" /> Generated Strategies</h3>
                      <span className="text-xs font-bold bg-purple-100 text-purple-700 px-2 py-0.5 rounded uppercase tracking-wider">{strategies.length} Options</span>
                    </div>

                    {strategies.map((strat: any) => (
                      <div
                        key={strat.id}
                        onClick={() => setSelectedStrategyId(strat.id)}
                        className={`p-4 rounded-xl border-2 cursor-pointer transition-all ${selectedStrategyId === strat.id ? 'border-primary bg-primary/5 shadow-md' : 'border-border bg-card hover:border-primary/50'}`}
                      >
                        <div className="flex items-center gap-3 mb-2">
                          <div className={`w-4 h-4 rounded-full border-2 flex items-center justify-center ${selectedStrategyId === strat.id ? 'border-primary' : 'border-muted-foreground'}`}>
                            {selectedStrategyId === strat.id && <div className="w-2 h-2 bg-primary rounded-full" />}
                          </div>
                          <h4 className="font-bold text-foreground">{strat.title}</h4>
                          {strat.recommended && <span className="ml-auto text-[10px] font-bold uppercase tracking-wider bg-purple-100 text-purple-700 px-2 py-0.5 rounded">Recommended</span>}
                          <span className="text-[10px] font-bold uppercase tracking-wider bg-success/10 text-success px-2 py-0.5 rounded">Viable</span>
                        </div>
                        <p className="text-sm text-muted-foreground pl-7 mb-4">{strat.description}</p>
                        <div className="pl-7 flex items-center gap-4">
                          <div className="text-xs font-medium border border-border px-2 py-1 rounded bg-background"><span className="text-warning font-bold">Cost ∆:</span> +₹{strat.cost_impact_cr} Cr</div>
                          <div className="text-xs font-medium border border-border px-2 py-1 rounded bg-background"><span className="text-success font-bold">Time ∆:</span> {strat.time_saved_days < 0 ? '' : '+'}{strat.time_saved_days} days</div>
                          <div className="text-xs font-medium border border-border px-2 py-1 rounded bg-background"><span className="text-success font-bold">Risk -:</span> {strat.risk_reduction_pct}%</div>
                          <div className="text-xs font-medium text-muted-foreground ml-auto">Confidence: {strat.ai_confidence_pct}%</div>
                        </div>
                      </div>
                    ))}
                  </div>

                  {/* Radar Profile */}
                  <div className="w-[300px] shrink-0 bg-card border border-border rounded-xl shadow-sm p-5 flex flex-col">
                    <h4 className="text-xs font-bold text-muted-foreground uppercase tracking-widest border-b border-border pb-3 mb-4">Strategy Profile</h4>
                    <div className="flex-1 min-h-[250px] -mx-4">
                      <ReactECharts option={radarOptions} style={{ height: '100%', width: '100%' }} />
                    </div>
                    <div className="border-t border-border pt-4 mt-2">
                      <h5 className="text-xs font-bold text-foreground mb-3">{strategies.find(s => s.id === selectedStrategyId)?.title}</h5>
                      <div className="space-y-2">
                        <div className="flex justify-between text-xs"><span className="text-muted-foreground">Cost Impact</span><span className="font-bold text-warning">+₹{strategies.find(s => s.id === selectedStrategyId)?.cost_impact_cr} Cr</span></div>
                        <div className="flex justify-between text-xs"><span className="text-muted-foreground">Time Impact</span><span className="font-bold text-success">{strategies.find(s => s.id === selectedStrategyId)?.time_saved_days} days</span></div>
                        <div className="flex justify-between text-xs"><span className="text-muted-foreground">Risk Reduction</span><span className="font-bold text-success">{strategies.find(s => s.id === selectedStrategyId)?.risk_reduction_pct}%</span></div>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {strategies.length > 0 && !isGeneratingStrategies && (
                <button
                  onClick={executeStrategy}
                  className="w-full bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-600 hover:to-teal-600 text-white font-bold py-4 rounded-xl shadow-lg transition-all flex items-center justify-center gap-2 mt-auto"
                >
                  <CheckCircle2 className="w-5 h-5 fill-current" /> Execute Strategy
                </button>
              )}
            </div>
          </div>
        )}

        {/* ========================================== */}
        {/* STEP 3: EXECUTE */}
        {/* ========================================== */}
        {activeStep === 3 && (
          <div className="max-w-3xl mx-auto mt-10 space-y-8 animate-in fade-in zoom-in-95 duration-500">
            <div className="text-center space-y-4">
              <div className="w-20 h-20 bg-success/10 rounded-full flex items-center justify-center mx-auto mb-6 shadow-[0_0_30px_rgba(16,185,129,0.3)]">
                <Activity className="w-10 h-10 text-success animate-pulse" />
              </div>
              <h2 className="text-2xl font-bold">Executing AI Strategy</h2>
              <p className="text-muted-foreground">Pushing tasks and automated decisions to SAP and PMAG...</p>

              <div className="w-full max-w-md mx-auto h-2 bg-muted rounded-full overflow-hidden mt-8">
                <div className="h-full bg-success/100 transition-all duration-300" style={{ width: `${executionProgress}%` }}></div>
              </div>
            </div>

            <div className="bg-card border border-border rounded-xl shadow-sm p-6 mt-8 space-y-4">
              <h3 className="text-xs font-bold text-muted-foreground uppercase tracking-widest border-b border-border pb-3">Automated Actions</h3>
              {executionTasks.map((t: any, i: number) => {
                const isResolved = resolvedTasks.includes(i);
                return (
                  <div key={i} className={`flex items-center gap-4 p-3 rounded-lg border transition-all ${isResolved ? 'bg-success/10/50 border-success/20' : 'bg-muted border-border opacity-60 hover:opacity-100'}`}>
                    <button 
                      onClick={() => !isResolved && setResolvedTasks(prev => [...prev, i])}
                      className={`w-6 h-6 rounded-md flex items-center justify-center shrink-0 border transition-all cursor-pointer ${isResolved ? 'bg-success/100 text-white border-emerald-500 shadow-sm' : 'bg-background text-transparent border-muted-foreground hover:border-primary'}`}
                    >
                      <Check className="w-4 h-4" />
                    </button>
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-[10px] font-bold uppercase tracking-wider bg-background border border-border px-1.5 py-0.5 rounded">{t.system}</span>
                        <span className="font-bold text-sm text-foreground">{t.action}</span>
                      </div>
                      <p className="text-xs text-muted-foreground">{t.description}</p>
                    </div>
                    <div className={`ml-auto text-[10px] font-bold uppercase tracking-wider ${isResolved ? 'text-success' : 'text-muted-foreground'}`}>
                      {isResolved ? 'Success' : 'Pending'}
                    </div>
                  </div>
                );
              })}
            </div>

            {executionTasks.length > 0 && resolvedTasks.length === executionTasks.length && (
              <div className="mt-8 bg-success/10 dark:bg-success/100/10 border border-success/20 dark:border-success/20 rounded-xl p-6 text-center animate-in slide-in-from-bottom-4 shadow-sm">
                <CheckCircle2 className="w-12 h-12 text-success mx-auto mb-4" />
                <h3 className="text-xl font-bold text-success dark:text-success">Issue Resolved</h3>
                <p className="text-success/80 dark:text-success/80 mt-2 font-medium">All automated actions and required tasks have been successfully processed and pushed to their respective systems.</p>
              </div>
            )}
          </div>
        )}

        {/* STEP 4: REPORT has been removed per user request */}
        {false && activeStep === 4 && (
          <div className="max-w-4xl mx-auto space-y-6 animate-in fade-in">
            <div className="bg-card border border-border rounded-xl shadow-lg p-8 relative overflow-hidden">
              <div className="absolute top-0 left-0 w-full h-2 bg-gradient-to-r from-blue-500 via-indigo-500 to-purple-500"></div>

              <div className="flex justify-between items-start mb-8">
                <div>
                  <h1 className="text-3xl font-bold text-foreground mb-2">Executive Execution Report</h1>
                  <p className="text-muted-foreground font-medium">Generated by AKASHA AI Simulation Engine</p>
                </div>
                <div className="text-right">
                  <div className="text-xs font-bold text-muted-foreground uppercase tracking-widest mb-1">Project</div>
                  <div className="font-bold text-primary text-lg">{selectedProject}</div>
                  <div className="text-xs text-muted-foreground">{new Date().toLocaleDateString()}</div>
                </div>
              </div>

              {reportData ? (
                <div className="space-y-8">
                  <div className="grid grid-cols-3 gap-4 border-y border-border py-6">
                    <div>
                      <div className="text-xs font-bold text-muted-foreground uppercase tracking-widest mb-1">Strategy Applied</div>
                      <div className="font-bold text-foreground">{strategies.find(s => s.id === selectedStrategyId)?.title}</div>
                    </div>
                    <div>
                      <div className="text-xs font-bold text-muted-foreground uppercase tracking-widest mb-1">Projected Time Saved</div>
                      <div className="font-bold text-success">{strategies.find(s => s.id === selectedStrategyId)?.time_saved_days} Days</div>
                    </div>
                    <div>
                      <div className="text-xs font-bold text-muted-foreground uppercase tracking-widest mb-1">Cost Variation</div>
                      <div className="font-bold text-warning">+₹{strategies.find(s => s.id === selectedStrategyId)?.cost_impact_cr} Cr</div>
                    </div>
                  </div>

                  <div className="prose prose-sm max-w-none text-foreground/80 space-y-6">
                    {reportData.executiveSummary && (
                      <div>
                        <h3 className="text-lg font-bold text-foreground mb-2">Executive Summary</h3>
                        <p className="leading-relaxed">{reportData.executiveSummary}</p>
                      </div>
                    )}
                    {reportData.keyFindings && reportData.keyFindings.length > 0 && (
                      <div>
                        <h3 className="text-lg font-bold text-foreground mb-2">Key Findings</h3>
                        <ul className="list-disc pl-5 space-y-1">
                          {reportData.keyFindings.map((f: string, i: number) => <li key={i}>{f}</li>)}
                        </ul>
                      </div>
                    )}
                    {reportData.riskAssessment && (
                      <div>
                        <h3 className="text-lg font-bold text-foreground mb-2">Risk Assessment</h3>
                        <p className="leading-relaxed">{reportData.riskAssessment}</p>
                      </div>
                    )}
                    {reportData.rootCauseAnalysis && (
                      <div>
                        <h3 className="text-lg font-bold text-foreground mb-2">Root Cause Analysis</h3>
                        <p className="leading-relaxed">{reportData.rootCauseAnalysis}</p>
                      </div>
                    )}
                    {reportData.recommendedActions && reportData.recommendedActions.length > 0 && (
                      <div>
                        <h3 className="text-lg font-bold text-foreground mb-2">Recommended Actions</h3>
                        <ul className="list-disc pl-5 space-y-1">
                          {reportData.recommendedActions.map((f: string, i: number) => <li key={i}>{f}</li>)}
                        </ul>
                      </div>
                    )}
                    {reportData.expectedOutcome && (
                      <div>
                        <h3 className="text-lg font-bold text-foreground mb-2">Expected Outcome</h3>
                        <p className="leading-relaxed">{reportData.expectedOutcome}</p>
                      </div>
                    )}
                  </div>
                </div>
              ) : (
                <div className="py-20 flex flex-col items-center justify-center text-muted-foreground">
                  <FileText className="w-10 h-10 mb-4 animate-pulse opacity-50" />
                  <p>Generating Executive Report...</p>
                </div>
              )}
            </div>

            <button
              onClick={() => {
                setActiveStep(1);
                setIsScanning(false);
                setShowResults(false);
                setSimulationData(null);
                setStrategies([]);
                setSelectedStrategyId(null);
              }}
              className="mx-auto block text-sm font-bold text-primary hover:underline"
            >
              Return to Simulation Lab Start
            </button>
          </div>
        )}

      </div>
    </div>
    </div >
  );
}
