import React, { useState, useEffect, useRef } from 'react';
import { Bell, User, ChevronDown, Moon, Sun, LogOut, Sparkles, Menu, RefreshCw, BookOpen, Layers, GitBranch } from 'lucide-react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import NotificationDropdown from './NotificationDropdown';
import PMAGThreadPanel from './PMAGThreadPanel';
import { cx } from '../ui/primitives/cx';

/* One button scale for the whole header. Anything that is not the single AI
   action is quiet — the toolbar should read as chrome, not compete with the
   page beneath it. */
const BTN_SECONDARY =
  'flex items-center gap-1.5 rounded-lg border border-border bg-card px-2.5 py-1.5 text-[12px] font-semibold text-fg-secondary transition-colors hover:border-brand-blue/40 hover:text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:opacity-50';
const BTN_ICON =
  'rounded-lg p-1.5 text-fg-tertiary transition-colors hover:bg-muted hover:text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-primary';

/** Scope menus: keyboard reachable, Escape to close, click-outside to dismiss. */
function ScopeMenu({
  label, icon: Icon, value, options, labels, onChange, width = 'min-w-[170px]',
}: {
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  value: string;
  options: string[];
  labels?: Record<string, string>;
  onChange: (v: string) => void;
  width?: string;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={`${label}: ${labels?.[value] ?? value}`}
        className={BTN_SECONDARY}
      >
        <Icon className="h-3.5 w-3.5 text-fg-tertiary" />
        <span className="max-w-[140px] truncate">{labels?.[value] ?? value}</span>
        <ChevronDown className={cx('h-3.5 w-3.5 shrink-0 transition-transform', open && 'rotate-180')} />
      </button>

      {open && (
        <ul
          role="listbox"
          aria-label={label}
          className={cx('surface-raised absolute left-0 top-full z-50 mt-1 overflow-hidden py-1', width)}
        >
          {options.map((o) => (
            <li key={o} role="option" aria-selected={o === value}>
              <button
                onClick={() => { onChange(o); setOpen(false); }}
                className={cx(
                  'block w-full px-3 py-1.5 text-left text-[12px] transition-colors hover:bg-brand-blue/10 focus:outline-none focus-visible:bg-brand-blue/10',
                  o === value ? 'font-bold text-brand-blue' : 'text-fg-secondary',
                )}
              >
                {labels?.[o] ?? o}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function TopHeader({ onOpenCopilot, onToggleSidebar, onSyncData, isSyncing, onNavigateToSimulation }: any) {
  const [theme, setTheme] = useState<'light' | 'dark'>('light');
  const navigate = useNavigate();
  const { projectId } = useParams();
  const { user, logout } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const currentPortfolio = searchParams.get('portfolio') || 'All Portfolios';
  const currentPhase = searchParams.get('phase') || 'Ongoing';

  const [notifications, setNotifications] = useState<any[]>([]);
  const [hasMoreNotifs, setHasMoreNotifs] = useState(true);
  const [showNotifications, setShowNotifications] = useState(false);
  const [showUserMenu, setShowUserMenu] = useState(false);
  const [selectedNotification, setSelectedNotification] = useState<any | null>(null);
  const notificationRef = useRef<HTMLDivElement>(null);
  const userMenuRef = useRef<HTMLDivElement>(null);
  const LIMIT = 50;

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (notificationRef.current && !notificationRef.current.contains(event.target as Node)) {
        setShowNotifications(false);
      }
      if (userMenuRef.current && !userMenuRef.current.contains(event.target as Node)) {
        setShowUserMenu(false);
      }
    };
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { setShowNotifications(false); setShowUserMenu(false); }
    };
    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleKey);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleKey);
    };
  }, []);
  const unreadCount = notifications.filter(n => n.action_status === 'Pending').length;

  const fetchNotifications = async (reset = false) => {
    try {
      const currentSkip = reset ? 0 : notifications.length;
      let url = `/akasha/api/notifications/?skip=${currentSkip}&limit=${LIMIT}`;
      if (projectId) url += `&project_id=${projectId}`;
      if (currentPhase && currentPhase !== 'ALL') url += `&phase=${currentPhase}`;
      const res = await fetch(url);
      if (res.ok) {
        const data = await res.json();
        if (data.length < LIMIT) setHasMoreNotifs(false);
        else setHasMoreNotifs(true);
        setNotifications(prev => reset ? data : [...prev, ...data]);
      }
    } catch (e) {
      console.error('Failed to fetch notifications:', e);
    }
  };

  const loadMoreNotifications = () => {
    fetchNotifications(false);
  };

  useEffect(() => {
    fetchNotifications(true);
    const interval = setInterval(() => fetchNotifications(true), 60000);
    return () => clearInterval(interval);
  }, [projectId, currentPhase]);

  const handleSignOut = () => {
    logout();
    navigate('/', { replace: true });
  };

  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark');
  }, [theme]);

  return (
    <>
    <header className="flex h-[73px] shrink-0 items-center justify-between gap-3 border-b border-border bg-card px-4 z-40">

      {/* Left: scope — what the whole screen is filtered to */}
      <div className="flex min-w-0 items-center gap-2">
        <button
          onClick={onToggleSidebar}
          className={`md:hidden -ml-1 ${BTN_ICON}`}
          aria-label="Open navigation"
        >
          <Menu className="h-5 w-5" />
        </button>

        <ScopeMenu
          label="Phase"
          icon={GitBranch}
          value={currentPhase}
          options={['Ongoing', 'Commissioned', 'ALL']}
          labels={{ ALL: 'All phases' }}
          width="min-w-[150px]"
          onChange={(p) => setSearchParams(prev => {
            if (p === 'Ongoing') prev.delete('phase'); else prev.set('phase', p);
            return prev;
          })}
        />

        <ScopeMenu
          label="Portfolio"
          icon={Layers}
          value={currentPortfolio}
          options={['All Portfolios', 'Solar Khavda', 'Solar Rajasthan', 'Wind', 'BESS']}
          width="min-w-[190px]"
          onChange={(p) => setSearchParams(prev => {
            if (p === 'All Portfolios') prev.delete('portfolio'); else prev.set('portfolio', p);
            return prev;
          })}
        />
      </div>

      {/* Right: actions */}
      <div className="flex shrink-0 items-center gap-2">

        {onSyncData && (
          <button onClick={onSyncData} disabled={isSyncing} className={BTN_SECONDARY}>
            <RefreshCw className={cx('h-3.5 w-3.5 text-fg-tertiary', isSyncing && 'animate-spin')} />
            <span className="hidden lg:inline">{isSyncing ? 'Syncing…' : 'Sync data'}</span>
          </button>
        )}

        {/* The one emphasised action in the toolbar. */}
        <button
          onClick={onOpenCopilot}
          className="flex items-center gap-1.5 rounded-lg bg-gradient-to-r from-brand-blue to-brand-purple px-3 py-1.5 text-[12px] font-semibold text-white transition-opacity hover:opacity-90 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          title="Ask Akasha — project intelligence copilot"
        >
          <Sparkles className="h-3.5 w-3.5" />
          <span className="hidden lg:inline">Ask Akasha</span>
        </button>

        <div className="mx-0.5 hidden h-5 w-px bg-border sm:block" />

        <a
          href="/AKASHA_USER_GUIDE.docx"
          download
          className={`hidden sm:block ${BTN_ICON}`}
          title="Download user guide"
          aria-label="Download user guide"
        >
          <BookOpen className="h-4 w-4" />
        </a>

        <button
          onClick={() => setTheme(t => t === 'light' ? 'dark' : 'light')}
          className={`hidden sm:block ${BTN_ICON}`}
          title={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
          aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
        >
          {theme === 'dark' ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
        </button>

        {/* Notifications */}
        <div className="relative" ref={notificationRef}>
          <button
            onClick={() => setShowNotifications(!showNotifications)}
            aria-haspopup="menu"
            aria-expanded={showNotifications}
            aria-label={unreadCount > 0 ? `Notifications, ${unreadCount} pending` : 'Notifications'}
            className={`relative ${BTN_ICON}`}
          >
            <Bell className="h-4 w-4" />
            {unreadCount > 0 && (
              <span className="absolute right-1 top-1 h-2 w-2 rounded-full bg-status-critical-solid ring-2 ring-card" />
            )}
          </button>

          {showNotifications && (
            <NotificationDropdown
              notifications={notifications}
              onClose={() => setShowNotifications(false)}
              onLoadMore={loadMoreNotifications}
              hasMore={hasMoreNotifs}
              onSimulate={(projId: string, context?: any) => {
                setShowNotifications(false);
                if (onNavigateToSimulation) onNavigateToSimulation(projId, context);
              }}
            />
          )}
        </div>

        {/* Identity */}
        <div className="relative" ref={userMenuRef}>
          <button
            onClick={() => setShowUserMenu(o => !o)}
            aria-haspopup="menu"
            aria-expanded={showUserMenu}
            aria-label="Account menu"
            className="flex items-center gap-1.5 rounded-lg p-1 transition-colors hover:bg-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          >
            <span className="flex h-7 w-7 items-center justify-center rounded-full border border-border bg-surface-sunken">
              <User className="h-3.5 w-3.5 text-fg-secondary" />
            </span>
            <ChevronDown className={cx('hidden h-3.5 w-3.5 text-fg-tertiary transition-transform sm:block', showUserMenu && 'rotate-180')} />
          </button>

          {showUserMenu && (
            <div role="menu" className="surface-raised absolute right-0 top-full z-50 mt-1 w-48 overflow-hidden py-1">
              <div className="border-b border-border px-3 py-2">
                <p className="truncate text-[12px] font-semibold text-foreground">{user?.display_name || 'User'}</p>
                <p className="truncate text-[11px] capitalize text-fg-tertiary">{user?.role || 'executive'}</p>
              </div>
              <button
                role="menuitem"
                onClick={handleSignOut}
                className="flex w-full items-center gap-1.5 px-3 py-2 text-left text-[12px] text-status-critical-fg transition-colors hover:bg-status-critical-bg focus:outline-none focus-visible:bg-status-critical-bg"
              >
                <LogOut className="h-3.5 w-3.5" />
                Sign out
              </button>
            </div>
          )}
        </div>
      </div>
    </header>

    {selectedNotification && (
      <PMAGThreadPanel 
        notification={selectedNotification} 
        onClose={() => setSelectedNotification(null)}
        onResolved={() => {
          fetchNotifications();
          setSelectedNotification(null);
        }}
      />
    )}
    </>
  );
}
