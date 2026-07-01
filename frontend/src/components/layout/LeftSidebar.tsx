import React, { useState } from 'react';
import {
  Home, Command, Network, MessageSquare, FileText, Search, Activity,
  Settings, Zap, X, ChevronLeft, ChevronRight, BarChart2, Share2
} from 'lucide-react';

interface SidebarProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
  isMobileOpen?: boolean;
  onCloseMobile?: () => void;
}

export default function LeftSidebar({ activeTab, setActiveTab, isMobileOpen = false, onCloseMobile }: SidebarProps) {
  const [collapsed, setCollapsed] = useState(false);

  const menuSections = [
    {
      title: "Dashboard",
      items: [
        { id: 'overview', label: 'Overview', icon: Home },
        { id: 'capacity_overview', label: 'Capacity Overview', icon: BarChart2 },
        { id: 'project360', label: 'Project 360', icon: Command },
      ]
    }
  ];

  const aiSections = [
    { id: 'ai_copilot', label: 'Ask Akasha', icon: MessageSquare },
    { id: 'executive_brief', label: 'Briefing', icon: FileText },
    { id: 'smart_search', label: 'Search', icon: Search },
    { id: 'project_map', label: 'Project Map', icon: Network },
    { id: 'knowledge_graph', label: 'Knowledge Graph', icon: Share2 },
    { id: 'simulation_lab', label: 'Simulation', icon: Activity },
  ];

  const adminSections = [
    { id: 'reports', label: 'Reports', icon: FileText },
    { id: 'admin', label: 'Admin', icon: Settings },
  ];

  const handleTabClick = (id: string) => {
    setActiveTab(id);
    if (onCloseMobile) onCloseMobile();
  };

  // Whether we show labels (expanded desktop or mobile drawer)
  const showLabel = !collapsed || isMobileOpen;

  const NavItem = ({ item, accent = false }: { item: { id: string; label: string; icon: any }; accent?: boolean }) => {
    const isActive = activeTab === item.id;
    return (
      <div className="relative group">
        {/* Tooltip when collapsed */}
        {collapsed && !isMobileOpen && (
          <div className="absolute left-full ml-2 top-1/2 -translate-y-1/2 px-2.5 py-1 rounded-md bg-slate-800 text-white text-[11px] font-medium whitespace-nowrap opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity z-[60] shadow-lg">
            {item.label}
          </div>
        )}
        <button
          onClick={() => handleTabClick(item.id)}
          title={collapsed ? item.label : undefined}
          className={`w-full flex items-center gap-2.5 rounded-lg text-[13px] font-medium transition-all duration-150
            ${collapsed && !isMobileOpen ? 'justify-center p-2.5' : 'px-3 py-2'}
            ${isActive
              ? 'bg-[#0b74b1] text-white shadow-sm shadow-[#0b74b1]/25'
              : accent
                ? 'text-slate-600 dark:text-slate-300 hover:bg-[#0b74b1]/5 dark:hover:bg-[#0b74b1]/20 hover:text-[#0b74b1] dark:hover:text-[#38bdf8]'
                : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-900 dark:hover:text-white'
            }`}
        >
          <item.icon className={`w-[18px] h-[18px] shrink-0 transition-colors ${isActive ? 'text-white' : accent ? 'text-[#0b74b1]/70 dark:text-[#38bdf8]/70 group-hover:text-[#0b74b1] dark:group-hover:text-[#38bdf8]' : 'text-slate-400 group-hover:text-slate-600 dark:group-hover:text-slate-300'}`} />
          {showLabel && <span className="truncate leading-none">{item.label}</span>}
        </button>
      </div>
    );
  };

  const sidebarInner = (
    <div className="flex flex-col h-full">
      {/* ─── Brand Bar ─── */}
      <div className={`flex items-center shrink-0 border-b border-slate-100 dark:border-slate-800 h-[73px] ${collapsed && !isMobileOpen ? 'justify-center px-2' : 'px-4 justify-between'}`}>
        <div className="flex items-center overflow-hidden">
          {!showLabel && (
            <span className="text-[22px] font-heading font-black tracking-tighter leading-none uppercase bg-gradient-to-r from-[#0b74b1] via-[#76489d] to-[#bc3860] text-transparent bg-clip-text mx-auto">A</span>
          )}
          {showLabel && (
            <div className="flex flex-col min-w-0 py-1">
              <span className="text-[24px] font-heading font-black tracking-tighter leading-none uppercase bg-gradient-to-r from-[#0b74b1] via-[#76489d] to-[#bc3860] text-transparent bg-clip-text">AKASHA</span>
              <span className="text-[9px] font-bold text-[#0b74b1] uppercase tracking-[0.25em] mt-0.5">Execution Platform</span>
            </div>
          )}
        </div>
        {/* Mobile close */}
        {isMobileOpen && (
          <button onClick={onCloseMobile} className="md:hidden p-1 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 rounded">
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
              <h3 className="px-3 mb-1 text-[10px] font-bold uppercase tracking-[0.15em] text-slate-400 dark:text-slate-500">
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
              <Zap className="w-3 h-3 text-[#0b74b1] dark:text-[#38bdf8]" />
              <h3 className="text-[10px] font-bold uppercase tracking-[0.15em] text-[#0b74b1] dark:text-[#38bdf8]">Platform Tools</h3>
            </div>
          ) : (
            <div className="flex justify-center my-1">
              <div className="w-5 h-px bg-[#0b74b1]/30" />
            </div>
          )}
          {aiSections.map((item) => <NavItem key={item.id} item={item} accent />)}
        </div>

        {/* Admin */}
        <div className="flex flex-col gap-0.5 mt-auto pt-3 border-t border-slate-100 dark:border-slate-800">
          {adminSections.map((item) => <NavItem key={item.id} item={item} />)}
        </div>
      </nav>

      {/* ─── Collapse toggle (desktop only) ─── */}
      <div className="hidden md:flex shrink-0 border-t border-slate-100 dark:border-slate-800 px-2.5 py-2">
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="w-full flex items-center justify-center gap-2 py-1.5 rounded-lg text-slate-400 dark:text-slate-500 hover:text-slate-600 dark:hover:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors text-xs font-medium"
        >
          {collapsed ? <ChevronRight className="w-4 h-4" /> : (
            <>
              <ChevronLeft className="w-4 h-4" />
              <span>Collapse</span>
            </>
          )}
        </button>
      </div>
    </div>
  );

  return (
    <>
      {/* Desktop sidebar */}
      <aside
        className={`hidden md:block h-screen bg-white dark:bg-slate-900 border-r border-slate-200 dark:border-slate-800 z-50 shrink-0 transition-[width] duration-200 ease-in-out
          ${collapsed ? 'w-[60px]' : 'w-[210px]'}`}
      >
        {sidebarInner}
      </aside>

      {/* Mobile overlay */}
      {isMobileOpen && (
        <div className="fixed inset-0 bg-black/30 z-[100] md:hidden" onClick={onCloseMobile} />
      )}

      {/* Mobile drawer */}
      <aside
        className={`fixed inset-y-0 left-0 w-[250px] bg-white dark:bg-slate-900 border-r border-slate-200 dark:border-slate-800 z-[101] transform transition-transform duration-200 ease-in-out md:hidden
          ${isMobileOpen ? 'translate-x-0' : '-translate-x-full'}`}
      >
        {sidebarInner}
      </aside>
    </>
  );
}
