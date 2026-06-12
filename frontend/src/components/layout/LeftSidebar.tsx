import React, { useState } from 'react';
import { 
  Home, PieChart, Activity, Calendar, DollarSign, PenTool, 
  ShoppingCart, Truck, Users, ShieldAlert, TrendingUp, 
  Bot, FileText, Settings, Search, Network, BrainCircuit,
  ChevronLeft, ChevronRight, User, Bell, Command, Zap
} from 'lucide-react';

interface SidebarProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
}

export default function LeftSidebar({ activeTab, setActiveTab }: SidebarProps) {
  const [isCollapsed, setIsCollapsed] = useState(false);

  const menuSections = [
    {
      title: "Core Dashboard",
      items: [
        { id: 'overview', label: 'Executive Overview', icon: Home },
        { id: 'project360', label: 'Project 360', icon: Command },
        { id: 'data_integration', label: 'Data Integration', icon: Network },
      ]
    }
  ];

  const aiSections = [
    { id: 'ai_copilot', label: 'AI Copilot', icon: Bot },
    { id: 'executive_brief', label: 'Executive Briefing', icon: FileText },
    { id: 'smart_search', label: 'Smart Search', icon: Search },
    { id: 'knowledge_graph', label: 'Knowledge Graph', icon: Network },
  ];

  const adminSections = [
    { id: 'reports', label: 'Reports & Insights', icon: FileText },
    { id: 'admin', label: 'Administration', icon: Settings },
  ];

  return (
    <aside 
      className={`relative flex flex-col h-full bg-background border-r border-border transition-all duration-300 ease-in-out z-50
        ${isCollapsed ? 'w-20' : 'w-[280px]'}`}
    >
      {/* Collapse Toggle */}
      <button 
        onClick={() => setIsCollapsed(!isCollapsed)}
        className="absolute -right-3 top-8 bg-card border border-border hover:bg-primary hover:border-primary hover:text-primary-foreground text-muted-foreground p-1 rounded-full z-50 transition-colors flex items-center justify-center"
      >
        {isCollapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
      </button>

      {/* Header / Brand */}
      <div className={`p-6 pb-4 flex flex-col justify-center border-b border-border/50 ${isCollapsed ? 'items-center px-0' : ''}`}>
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl overflow-hidden shrink-0 border border-primary/20">
             <img src={`${import.meta.env.BASE_URL}akasha_hero_bg.png`} alt="AKASHA" className="w-full h-full object-cover" />
          </div>
          {!isCollapsed && (
            <div className="flex flex-col overflow-hidden whitespace-nowrap animate-in fade-in duration-300">
              <h1 className="text-xl font-bold text-foreground tracking-wide">AKASHA</h1>
              <span className="text-[9px] font-semibold text-primary uppercase tracking-[0.2em]">Intelligence Platform</span>
            </div>
          )}
        </div>
        {!isCollapsed && (
           <div className="mt-4 flex items-center gap-2 px-2 py-1 bg-muted rounded text-[10px] font-mono text-muted-foreground border border-border w-fit">
             <div className="w-1.5 h-1.5 rounded-full bg-success"></div>
             ENV: ENTERPRISE PROD
           </div>
        )}
      </div>

      {/* Navigation Scroll Area */}
      <div className="flex-1 overflow-y-auto overflow-x-hidden scrollbar-hide py-4 px-3 flex flex-col gap-6">
        
        {/* Standard Sections */}
        {menuSections.map((section, idx) => (
          <div key={idx} className="flex flex-col gap-1">
            {!isCollapsed && (
              <h3 className="px-3 text-[10px] font-bold uppercase tracking-widest text-muted-foreground/70 mb-2 truncate">
                {section.title}
              </h3>
            )}
            
            {section.items.map((item) => {
              const isActive = activeTab === item.id;
              return (
                <div key={item.id} className="relative group">
                  {/* Tooltip for Collapsed State */}
                  {isCollapsed && (
                    <div className="absolute left-14 top-1/2 -translate-y-1/2 bg-card border border-border text-foreground text-xs px-3 py-1.5 rounded-md opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity whitespace-nowrap z-50 shadow-xl">
                      {item.label}
                    </div>
                  )}
                  
                  <button
                    onClick={() => setActiveTab(item.id)}
                    className={`relative w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-200
                      ${isActive 
                        ? 'bg-primary/10 text-foreground' 
                        : 'text-muted-foreground hover:bg-muted hover:text-foreground'
                      }
                      ${isCollapsed ? 'justify-center px-0' : 'justify-start'}
                    `}
                  >
                    {/* Active Indicator Bar */}
                    {isActive && (
                      <div className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-5 bg-primary rounded-r-md"></div>
                    )}
                    
                    <item.icon className={`shrink-0 transition-transform duration-200 ${isActive ? 'text-primary' : ''} ${!isCollapsed && 'group-hover:translate-x-1'} ${isCollapsed ? 'w-5 h-5' : 'w-4 h-4'}`} />
                    
                    {!isCollapsed && (
                      <span className="text-sm font-medium tracking-wide truncate">{item.label}</span>
                    )}
                  </button>
                </div>
              );
            })}
          </div>
        ))}

        {/* AI Section */}
        <div className="flex flex-col gap-1 relative">
           {!isCollapsed && (
              <div className="px-3 mb-2 flex items-center gap-2">
                 <Zap className="w-3 h-3 text-primary" />
                 <h3 className="text-[10px] font-bold uppercase tracking-widest text-primary truncate">
                   Akasha AI
                 </h3>
              </div>
           )}
           
           {aiSections.map((item) => {
              const isActive = activeTab === item.id;
              return (
                <div key={item.id} className="relative group z-10">
                  {isCollapsed && (
                    <div className="absolute left-14 top-1/2 -translate-y-1/2 bg-primary border border-primary/50 text-primary-foreground text-xs font-semibold px-3 py-1.5 rounded-md opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity whitespace-nowrap z-50">
                      {item.label}
                    </div>
                  )}
                  <button
                    onClick={() => setActiveTab(item.id)}
                    className={`relative w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-200
                      ${isActive 
                        ? 'bg-primary/10 text-foreground border border-primary/30' 
                        : 'text-primary hover:bg-primary/5 hover:text-foreground'
                      }
                      ${isCollapsed ? 'justify-center px-0' : 'justify-start'}
                    `}
                  >
                    {isActive && (
                      <div className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-5 bg-primary rounded-r-md"></div>
                    )}
                    <item.icon className={`shrink-0 transition-transform duration-200 ${isActive ? 'text-primary' : 'text-primary'} ${!isCollapsed && 'group-hover:translate-x-1'} ${isCollapsed ? 'w-5 h-5' : 'w-4 h-4'}`} />
                    {!isCollapsed && (
                      <span className="text-sm font-medium tracking-wide truncate">{item.label}</span>
                    )}
                  </button>
                </div>
              );
            })}
        </div>

        {/* Administration */}
        <div className="flex flex-col gap-1 mt-4 pt-4 border-t border-border/50">
           {adminSections.map((item) => {
              const isActive = activeTab === item.id;
              return (
                <div key={item.id} className="relative group">
                  {isCollapsed && (
                    <div className="absolute left-14 top-1/2 -translate-y-1/2 bg-card border border-border text-foreground text-xs px-3 py-1.5 rounded-md opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity whitespace-nowrap z-50 shadow-xl">
                      {item.label}
                    </div>
                  )}
                  <button
                    onClick={() => setActiveTab(item.id)}
                    className={`relative w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-200
                      ${isActive 
                        ? 'bg-primary/10 text-foreground' 
                        : 'text-muted-foreground hover:bg-muted hover:text-foreground'
                      }
                      ${isCollapsed ? 'justify-center px-0' : 'justify-start'}
                    `}
                  >
                    {isActive && (
                      <div className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-5 bg-primary rounded-r-md"></div>
                    )}
                    <item.icon className={`shrink-0 transition-transform duration-200 ${isActive ? 'text-primary' : ''} ${!isCollapsed && 'group-hover:rotate-45'} ${isCollapsed ? 'w-5 h-5' : 'w-4 h-4'}`} />
                    {!isCollapsed && (
                      <span className="text-sm font-medium tracking-wide truncate">{item.label}</span>
                    )}
                  </button>
                </div>
              );
            })}
        </div>
      </div>

      {/* Footer / User Profile */}
      <div className={`p-4 border-t border-border/50 bg-muted/30 ${isCollapsed ? 'flex justify-center' : ''}`}>
        <div className={`flex items-center gap-3 ${isCollapsed ? 'justify-center' : 'justify-start'}`}>
          <div className="relative shrink-0">
             <div className="w-9 h-9 rounded-full bg-card flex items-center justify-center border border-border">
               <User className="w-5 h-5 text-muted-foreground" />
             </div>
             <div className="absolute bottom-0 right-0 w-2.5 h-2.5 bg-success rounded-full border-2 border-background"></div>
          </div>
          {!isCollapsed && (
            <div className="flex flex-col flex-1 truncate">
              <span className="text-sm font-medium text-foreground truncate">Executive Office</span>
              <span className="text-xs text-muted-foreground/70 truncate">ceo@adani.com</span>
            </div>
          )}
          {!isCollapsed && (
             <button className="text-muted-foreground hover:text-foreground transition-colors p-1">
               <Bell className="w-4 h-4" />
             </button>
          )}
        </div>
      </div>

    </aside>
  );
}
