import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { Moon, Sun } from 'lucide-react';
import { Sidebar, SidebarBody, SidebarLink, SIDEBAR_TRANSITION } from '../ui/sidebar';
import DashboardSwitcher from '../auth/DashboardSwitcher';
import { useTheme } from '../../hooks/useTheme';

/* The app's left rail and top header, shared by every signed-in screen
   outside the Executive dashboard (which keeps its own): the dashboard
   picker, the role dashboards and the admin console. Same rail as the
   Executive - an icon strip that opens over the page on hover - so moving
   between screens never changes the frame. */

export interface RailItem {
  id: string;
  label: string;
  icon: React.JSX.Element;
}

export interface RailGroup {
  title: string;
  items: RailItem[];
}

const iconFor = (el: React.JSX.Element, on: boolean) =>
  React.cloneElement(el as React.ReactElement<{ className?: string }>, {
    className: `w-[17px] h-[17px] shrink-0 transition-colors duration-200 ${on ? 'text-white' : 'text-muted-foreground group-hover/sidebar:text-foreground'}`,
  });

export function AppRail({ subtitle, groups, footer = [], active, onSelect }: {
  /** Line under the AKASHA wordmark, e.g. "PMAG dashboard". */
  subtitle: string;
  groups: RailGroup[];
  /** Pinned to the bottom of the rail. */
  footer?: RailItem[];
  active: string;
  onSelect: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const link = (item: RailItem) => (
    <SidebarLink key={item.id} active={active === item.id}
      link={{ label: item.label, href: '#', icon: iconFor(item.icon, active === item.id) }}
      onClick={e => { e.preventDefault(); onSelect(item.id); }} />
  );
  return (
    <Sidebar open={open} setOpen={setOpen} animate>
      <SidebarBody className="h-full justify-between gap-2 border-r border-border bg-card p-0 text-foreground">
        <div className="custom-scrollbar flex flex-1 flex-col overflow-y-auto overflow-x-hidden">
          <div className="mb-2 flex h-[73px] shrink-0 items-center gap-2.5 px-4">
            <span className="flex h-5 w-6 shrink-0 items-center justify-center">
              <span className="bg-gradient-to-br from-brand-blue via-brand-purple to-brand-pink bg-clip-text text-[22px] font-black uppercase leading-none tracking-tighter text-transparent">A</span>
            </span>
            <motion.div initial={false} animate={{ opacity: open ? 1 : 0, x: open ? 0 : -6 }} transition={SIDEBAR_TRANSITION}
              className="flex min-w-0 flex-col whitespace-nowrap">
              <span className="bg-gradient-to-r from-brand-blue via-brand-purple to-brand-pink bg-clip-text text-[18px] font-black uppercase leading-none tracking-tighter text-transparent">AKASHA</span>
              <span className="mt-0.5 text-[8px] font-bold uppercase tracking-[0.22em] text-primary">{subtitle}</span>
            </motion.div>
          </div>
          <nav className="flex flex-col gap-4 px-2.5" aria-label={subtitle}>
            {groups.map(g => (
              <div key={g.title} className="flex flex-col gap-0.5">
                <div className="relative mb-0.5 h-4 shrink-0">
                  <motion.h3 initial={false} animate={{ opacity: open ? 1 : 0 }} transition={SIDEBAR_TRANSITION}
                    className="absolute bottom-0 left-4 whitespace-nowrap text-[9px] font-bold uppercase tracking-[0.12em] text-muted-foreground">
                    {g.title}
                  </motion.h3>
                  <motion.div initial={false} animate={{ opacity: open ? 0 : 1 }} transition={SIDEBAR_TRANSITION}
                    className="absolute bottom-1.5 left-[26px] h-px w-6 bg-border" />
                </div>
                {g.items.map(link)}
              </div>
            ))}
          </nav>
        </div>
        {footer.length > 0 && (
          <div className="mt-auto flex shrink-0 flex-col gap-0.5 border-t border-border px-2.5 pb-2 pt-2">{footer.map(link)}</div>
        )}
      </SidebarBody>
    </Sidebar>
  );
}

/** Header: where you are on the left; filters (children), theme and the account menu on the right. */
export function AppHeader({ kicker, title, children }: { kicker: string; title: string; children?: React.ReactNode }) {
  const [theme, , toggleTheme] = useTheme();
  return (
    <header className="flex h-[73px] shrink-0 items-center justify-between gap-3 border-b border-border bg-card px-4 shadow-sm sm:px-5">
      <div className="min-w-0 pl-10 md:pl-0">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">{kicker}</p>
        <h1 className="truncate text-[15px] font-semibold text-foreground">{title}</h1>
      </div>
      <div className="flex items-center gap-1.5 sm:gap-2">
        {children}
        <button type="button" onClick={toggleTheme} aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
          className="rounded-lg p-2 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary">
          {theme === 'dark' ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
        </button>
        <DashboardSwitcher />
      </div>
    </header>
  );
}

/** Rail + sticky header + scrolling main: the frame every one of these screens uses. */
export function AppFrame({ rail, header, children }: { rail: React.ReactNode; header: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen w-full bg-[var(--background)]">
      <div className="sticky top-0 z-[80] h-screen shrink-0">{rail}</div>
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="sticky top-0 z-[60]">{header}</div>
        <main className="flex-1 p-4 sm:p-6">{children}</main>
      </div>
    </div>
  );
}
