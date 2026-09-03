import React, { useState } from 'react';
import {
  Home, Command, Network, MessageSquare, FileText, Search, Activity,
  Settings, Zap, X, ChevronLeft, ChevronRight, BarChart2, Share2, Database,
  Calendar, ClipboardList, Brain, CheckCircle
} from 'lucide-react';

interface SidebarProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
  isMobileOpen?: boolean;
  onCloseMobile?: () => void;
}

export default function LeftSidebar({ activeTab, setActiveTab, isMobileOpen = false, onCloseMobile }: SidebarProps) {
  const [collapsed, setCollapsed] = useState(true);
  const [isHovered, setIsHovered] = useState(false);

  const menuSections = [
    {
      title: "Dashboard",
      items: [
        { id: 'overview', label: 'Overview', icon: Home },
        // { id: 'portfolio_intelligence', label: 'Intelligence Hub', icon: Brain },
        { id: 'capacity_overview', label: 'Capacity Overview', icon: BarChart2 },
        { id: 'project360', label: 'Project 360', icon: Command },
      ]
    },
    {
      title: "Applications",
      items: [
        { id: 'financial', label: 'SAP Intelligence', icon: Database },
        { id: 'einvoice_intelligence', label: 'E-Invoice Intelligence', icon: FileText },
        { id: 'transmission_data', label: 'Transmission', icon: Network },
        { id: 'quality', label: 'Quality', icon: Activity },
        { id: 'approvals', label: 'Approval', icon: CheckCircle },
        { id: 'schedule', label: 'P6 & DPR', icon: Calendar },
      ]
    }
  ];

  const aiSections = [
    // { id: 'ai_copilot', label: 'Ask Akasha', icon: MessageSquare },
    // { id: 'executive_brief', label: 'Briefing', icon: FileText },
    // { id: 'smart_search', label: 'Search', icon: Search },
    { id: 'project_map', label: 'Project Map', icon: Network },
    { id: 'knowledge_graph', label: 'Knowledge Graph', icon: Share2 },
    { id: 'simulation_lab', label: 'Simulation Lab', icon: Brain },
  ];

  const adminSections = [
    // { id: 'reports', label: 'Reports', icon: FileText },
    { id: 'admin', label: 'Admin', icon: Settings },
  ];

  const handleTabClick = (id: string) => {
    setActiveTab(id);
    if (onCloseMobile) onCloseMobile();
  };

  // Whether we show labels (expanded desktop or mobile drawer)
  const isEffectivelyCollapsed = collapsed && !isHovered;
  const showLabel = !isEffectivelyCollapsed || isMobileOpen;

  const NavItem = ({ item, accent = false }: { item: { id: string; label: string; icon: any }; accent?: boolean }) => {
    const isActive = activeTab === item.id;
    return (
      <div className="relative group">
        {/* Tooltip when collapsed */}
        {isEffectivelyCollapsed && !isMobileOpen && (
          <div className="absolute left-full ml-2 top-1/2 -translate-y-1/2 px-2.5 py-1 rounded-md bg-card text-white text-[11px] font-medium whitespace-nowrap opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity z-[60] shadow-lg">
            {item.label}
          </div>
        )}
        <button
          onClick={() => handleTabClick(item.id)}
          title={isEffectivelyCollapsed ? item.label : undefined}
          className={`w-full flex items-center gap-2.5 rounded-lg text-[13px] font-medium transition-all duration-150
            ${isEffectivelyCollapsed && !isMobileOpen ? 'justify-center p-2.5' : 'px-3 py-2'}
            ${isActive
              ? 'bg-primary text-white shadow-sm shadow-primary/25'
              : accent
                ? 'text-foreground dark:text-muted-foreground hover:bg-primary/5 dark:hover:bg-primary/20 hover:text-primary dark:hover:text-[#38bdf8]'
                : 'text-foreground dark:text-muted-foreground hover:bg-muted dark:hover:bg-card hover:text-foreground dark:hover:text-white'
            }`}
        >
          <item.icon className={`w-[18px] h-[18px] shrink-0 transition-colors ${isActive ? 'text-white' : accent ? 'text-primary/70 dark:text-[#38bdf8]/70 group-hover:text-primary dark:group-hover:text-[#38bdf8]' : 'text-muted-foreground group-hover:text-foreground dark:group-hover:text-muted-foreground'}`} />
          {showLabel && <span className="truncate leading-none">{item.label}</span>}
        </button>
      </div>
    );
  };

  const sidebarInner = (
    <div className="flex flex-col h-full">
      {/* ─── Brand Bar ─── */}
      <div className={`flex items-center shrink-0 border-b border-muted dark:border-border h-[73px] ${isEffectivelyCollapsed && !isMobileOpen ? 'justify-center px-2' : 'px-4 justify-between'}`}>
        <div className="flex items-center overflow-hidden">
          {!showLabel && (
            <span className="text-[22px] font-heading font-black tracking-tighter leading-none uppercase bg-gradient-to-r from-brand-blue via-brand-purple to-brand-pink text-transparent bg-clip-text mx-auto">A</span>
          )}
          {showLabel && (
            <div className="flex flex-col min-w-0 py-1">
              <span className="text-[24px] font-heading font-black tracking-tighter leading-none uppercase bg-gradient-to-r from-brand-blue via-brand-purple to-brand-pink text-transparent bg-clip-text">AKASHA</span>
              <span className="text-[9px] font-bold text-primary uppercase tracking-[0.25em] mt-0.5">Execution Platform</span>
            </div>
          )}
        </div>
        {/* Mobile close */}
        {isMobileOpen && (
          <button onClick={onCloseMobile} className="md:hidden p-1 text-muted-foreground hover:text-foreground dark:hover:text-muted-foreground rounded">
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* ─── Nav items ─── */}
      <nav className="flex-1 overflow-y-auto custom-scrollbar px-2.5 py-3 flex flex-col gap-4">

        {/* Core */}
        {menuSections.map((section, idx) => (
          <div key={idx} className="flex flex-col gap-0.5">
            {showLabel && (
              <h3 className="px-3 mb-1 text-[10px] font-bold uppercase tracking-[0.15em] text-muted-foreground dark:text-muted-foreground">
                {section.title}
              </h3>
            )}
            {section.items.map((item) => <NavItem key={item.id} item={item} />)}
          </div>
        ))}

        {/* AI */}
        <div className="flex flex-col gap-0.5">
          {showLabel ? (
            <div className="px-3 mb-1 flex items-center gap-1.5">
              <Zap className="w-3 h-3 text-primary dark:text-[#38bdf8]" />
              <h3 className="text-[10px] font-bold uppercase tracking-[0.15em] text-primary dark:text-[#38bdf8]">Platform Tools</h3>
            </div>
          ) : (
            <div className="flex justify-center my-1">
              <div className="w-5 h-px bg-primary/30" />
            </div>
          )}
          {aiSections.map((item) => <NavItem key={item.id} item={item} accent />)}
        </div>

        {/* Admin */}
        <div className="flex flex-col gap-0.5 mt-auto pt-3 border-t border-muted dark:border-border">
          {adminSections.map((item) => <NavItem key={item.id} item={item} />)}
        </div>
      </nav>

      {/* ─── Collapse toggle (desktop only) ─── 
      <div className="hidden md:flex shrink-0 border-t border-muted dark:border-border px-2.5 py-2">
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="w-full flex items-center justify-center gap-2 py-1.5 rounded-lg text-muted-foreground dark:text-muted-foreground hover:text-foreground dark:hover:text-muted-foreground hover:bg-muted dark:hover:bg-card transition-colors text-xs font-medium"
        >
          {isEffectivelyCollapsed ? <ChevronRight className="w-4 h-4" /> : (
            <>
              {collapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
              <span>{collapsed ? 'Pin Sidebar' : 'Collapse'}</span>
            </>
          )}
        </button>
      </div>
      */}
    </div>
  );

  return (
    <>
      {/* Desktop sidebar */}
      <aside
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
        className={`hidden md:block h-screen bg-card border-r border-border dark:border-border z-50 shrink-0 transition-[width] duration-200 ease-in-out
          ${isEffectivelyCollapsed ? 'w-[60px]' : 'w-[210px]'}`}
      >
        {sidebarInner}
      </aside>

      {/* Mobile overlay */}
      {isMobileOpen && (
        <div className="fixed inset-0 bg-black/30 z-[100] md:hidden" onClick={onCloseMobile} />
      )}

      {/* Mobile drawer */}
      <aside
        className={`fixed inset-y-0 left-0 w-[250px] bg-card border-r border-border dark:border-border z-[101] transform transition-transform duration-200 ease-in-out md:hidden
          ${isMobileOpen ? 'translate-x-0' : '-translate-x-full'}`}
      >
        {sidebarInner}
      </aside>
    </>
  );
}
