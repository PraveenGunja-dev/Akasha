import React, { useState } from 'react';
import {
  Home, Command, Network, MessageSquare, FileText, Activity,
  Settings, Zap, BarChart2, Share2, Database, Package,
  Calendar, Brain, CheckCircle, HardHat } from 'lucide-react';
import { Sidebar, SidebarBody, SidebarLink, SIDEBAR_TRANSITION } from '../ui/sidebar';
import { motion } from 'framer-motion';

interface SidebarProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
  isMobileOpen?: boolean;
  onCloseMobile?: () => void;
}

export default function LeftSidebar({ activeTab, setActiveTab, onCloseMobile }: SidebarProps) {
  const [open, setOpen] = useState(false);

  const menuSections = [
    {
      title: "Dashboard",
      items: [
        { id: 'overview', label: 'Overview', icon: <Home /> },
        { id: 'capacity_overview', label: 'Capacity Overview', icon: <BarChart2 /> },
        { id: 'installation_planner', label: 'Ordering Schedule', icon: <HardHat /> },
        { id: 'project360', label: 'Project 360', icon: <Command /> },
      ]
    },
    {
      title: "Applications",
      items: [
        { id: 'financial', label: 'SAP Intelligence', icon: <Database /> },
        { id: 'einvoice_intelligence', label: 'E-Invoice Intelligence', icon: <FileText /> },
        { id: 'transmission_data', label: 'Transmission', icon: <Network /> },
        { id: 'quality', label: 'Quality', icon: <Activity /> },
        { id: 'approvals', label: 'Approval', icon: <CheckCircle /> },
        { id: 'schedule', label: 'P6 & DPR', icon: <Calendar /> },
      ]
    }
  ];

  const aiSections = [
    { id: 'ai_copilot', label: 'Ask Akasha', icon: <MessageSquare /> },
    { id: 'project_map', label: 'Project Map', icon: <Network /> },
    { id: 'knowledge_graph', label: 'Knowledge Graph', icon: <Share2 /> },
    { id: 'simulation_lab', label: 'Simulation Lab', icon: <Brain /> },
  ];

  const adminSections = [
    { id: 'reports', label: 'Executive Report', icon: <FileText /> },
    { id: 'admin', label: 'Admin', icon: <Settings /> },
  ];

  const handleTabClick = (e: React.MouseEvent, id: string) => {
    e.preventDefault();
    setActiveTab(id);
    if (onCloseMobile) onCloseMobile();
  };

  /** Icons are sized here so every rail glyph shares one optical weight. */
  const navIcon = (icon: React.JSX.Element, isActive: boolean, accent = false) =>
    React.cloneElement(icon as React.ReactElement<{ className?: string }>, {
      className: `w-[17px] h-[17px] shrink-0 transition-colors duration-200 ${
        isActive
          ? 'text-white'
          : accent
            ? 'text-brand-purple/80 group-hover/sidebar:text-brand-purple'
            : 'text-muted-foreground group-hover/sidebar:text-foreground'
      }`,
    });

  /** Fixed-height header: the label crossfades with a hairline, so collapsing
      changes no box heights and the list below never shifts. */
  const SectionHeading = ({ label, accent = false }: { label: string; accent?: boolean }) => (
    <div className="relative mb-0.5 h-4 shrink-0">
      <motion.div
        initial={false}
        animate={{ opacity: open ? 1 : 0 }}
        transition={SIDEBAR_TRANSITION}
        className="absolute bottom-0 left-4 flex items-center gap-1.5 whitespace-nowrap"
      >
        {accent && <Zap className="h-2.5 w-2.5 text-brand-purple" />}
        <h3 className={`text-[9px] font-bold uppercase tracking-[0.12em] ${accent ? 'text-brand-purple' : 'text-muted-foreground'}`}>
          {label}
        </h3>
      </motion.div>
      <motion.div
        initial={false}
        animate={{ opacity: open ? 0 : 1 }}
        transition={SIDEBAR_TRANSITION}
        className={`absolute bottom-1.5 left-[26px] h-px w-6 ${accent ? 'bg-brand-purple/40' : 'bg-border'}`}
      />
    </div>
  );

  return (
    <Sidebar open={open} setOpen={setOpen} animate={true}>
      <SidebarBody className="h-full justify-between gap-2 border-r border-border bg-card p-0 text-foreground">

        <div className="custom-scrollbar flex flex-1 flex-col overflow-y-auto overflow-x-hidden">
          {/* Brand — the mark holds the rail centre, the wordmark fades in beside it */}
          <div className="mb-2 flex h-[73px] shrink-0 items-center gap-2.5 px-4">
            <span className="flex h-5 w-6 shrink-0 items-center justify-center">
              <span className="bg-gradient-to-br from-brand-blue via-brand-purple to-brand-pink bg-clip-text text-[22px] font-black uppercase leading-none tracking-tighter text-transparent">
                A
              </span>
            </span>
            <motion.div
              initial={false}
              animate={{ opacity: open ? 1 : 0, x: open ? 0 : -6 }}
              transition={SIDEBAR_TRANSITION}
              className="flex min-w-0 flex-col whitespace-nowrap"
            >
              <span className="bg-gradient-to-r from-brand-blue via-brand-purple to-brand-pink bg-clip-text text-[18px] font-black uppercase leading-none tracking-tighter text-transparent">
                AKASHA
              </span>
              <span className="mt-0.5 text-[8px] font-bold uppercase tracking-[0.22em] text-primary">
                Execution Platform
              </span>
            </motion.div>
          </div>

          {/* Navigation */}
          <div className="flex flex-col gap-4 px-2.5">
            {menuSections.map((section, idx) => (
              <div key={idx} className="flex flex-col gap-0.5">
                <SectionHeading label={section.title} />
                {section.items.map((item) => (
                  <SidebarLink
                    key={item.id}
                    active={activeTab === item.id}
                    link={{
                      label: item.label,
                      href: "#",
                      icon: navIcon(item.icon, activeTab === item.id),
                    }}
                    onClick={(e) => handleTabClick(e, item.id)}
                  />
                ))}
              </div>
            ))}

            <div className="flex flex-col gap-0.5">
              <SectionHeading label="Platform Tools" accent />
              {aiSections.map((item) => (
                <SidebarLink
                  key={item.id}
                  active={activeTab === item.id}
                  link={{
                    label: item.label,
                    href: "#",
                    icon: navIcon(item.icon, activeTab === item.id, true),
                  }}
                  onClick={(e) => handleTabClick(e, item.id)}
                />
              ))}
            </div>
          </div>
        </div>

        {/* Admin — identity lives in the header's user menu */}
        <div className="mt-auto flex shrink-0 flex-col gap-0.5 border-t border-border px-2.5 pb-2 pt-2">
          {adminSections.map((item) => (
            <SidebarLink
              key={item.id}
              active={activeTab === item.id}
              link={{
                label: item.label,
                href: "#",
                icon: navIcon(item.icon, activeTab === item.id),
              }}
              onClick={(e) => handleTabClick(e, item.id)}
            />
          ))}

        </div>
      </SidebarBody>
    </Sidebar>
  );
}
