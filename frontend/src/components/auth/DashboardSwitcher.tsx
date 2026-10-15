import { useEffect, useRef, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { Check, ChevronDown, KeyRound, LayoutGrid, LogOut } from 'lucide-react';
import { useAuth, ADMIN_PERMISSIONS } from '../../context/AuthContext';
import { ADMIN_ICON, DASHBOARD_ICONS, FALLBACK_ICON, dashboardKeyForPath, rememberDashboard } from './dashboardMeta';

/* The account menu in every header: which dashboard you are in, the others
   your role opens, the admin console, password and sign-out. With a single
   dashboard and no admin rights it is just the account menu. */
export default function DashboardSwitcher({ compact = false }: { compact?: boolean }) {
  const { user, logout, canAny } = useAuth();
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => { document.removeEventListener('mousedown', onDown); document.removeEventListener('keydown', onKey); };
  }, [open]);
  useEffect(() => setOpen(false), [pathname]);

  if (!user) return null;
  const currentKey = pathname.startsWith('/admin') ? 'admin' : dashboardKeyForPath(pathname, user.dashboards);
  const current = user.dashboards.find(d => d.key === currentKey);
  const CurrentIcon = currentKey === 'admin' ? ADMIN_ICON : (currentKey && DASHBOARD_ICONS[currentKey]) || FALLBACK_ICON;
  const currentLabel = currentKey === 'admin' ? 'Admin console' : current?.label ?? 'Dashboards';
  const isAdmin = canAny(ADMIN_PERMISSIONS);
  const initials = user.display_name.split(/\s+/).map(w => w[0]).join('').slice(0, 2).toUpperCase();

  const signOut = async () => { await logout(); navigate('/login', { replace: true }); };
  const item = 'flex w-full items-center gap-2 px-3 py-1.5 text-left text-[12px] text-foreground hover:bg-muted focus-visible:bg-muted focus-visible:outline-none';

  return (
    <div className="relative" ref={ref}>
      <button type="button" onClick={() => setOpen(o => !o)} aria-haspopup="menu" aria-expanded={open}
        className="flex items-center gap-2 rounded-lg border border-border bg-card py-1 pl-1 pr-2 text-[12px] font-semibold text-foreground shadow-sm transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary">
        <span className="flex h-6 w-6 items-center justify-center rounded-md bg-primary/10 text-[10px] font-bold text-primary" aria-hidden>{initials}</span>
        {!compact && (
          <span className="hidden items-center gap-1.5 sm:flex">
            <CurrentIcon className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />
            {currentLabel}
          </span>
        )}
        <ChevronDown className={`h-3.5 w-3.5 text-muted-foreground transition-transform ${open ? 'rotate-180' : ''}`} aria-hidden />
      </button>

      {open && (
        <div role="menu" className="absolute right-0 top-full z-50 mt-1.5 w-64 overflow-hidden rounded-lg border border-border bg-card py-1 shadow-lg">
          <div className="border-b border-border px-3 py-2">
            <p className="truncate text-[12px] font-semibold text-foreground">{user.display_name}</p>
            <p className="truncate text-[11px] text-muted-foreground">
              {user.username} · {user.role_name}
              {!user.portfolio_access.all && user.portfolio_access.clusters.length > 0 && ` · ${user.portfolio_access.clusters.join(', ')}`}
            </p>
          </div>

          {user.dashboards.length > 0 && (
            <div className="border-b border-border py-1">
              <p className="px-3 pb-0.5 pt-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Switch dashboard</p>
              {user.dashboards.map(d => {
                const Icon = DASHBOARD_ICONS[d.key] ?? FALLBACK_ICON;
                const active = d.key === currentKey;
                return (
                  <Link key={d.key} to={d.route} role="menuitem" aria-current={active ? 'page' : undefined}
                    onClick={() => rememberDashboard(user.id, d.key)}
                    className={`${item} ${active ? 'font-semibold' : ''}`}>
                    <Icon className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />
                    <span className="flex-1">{d.label}</span>
                    {active && <Check className="h-3.5 w-3.5 text-primary" aria-hidden />}
                  </Link>
                );
              })}
              {user.dashboards.length > 1 && (
                <Link to="/workspaces" role="menuitem" className={`${item} text-muted-foreground`}>
                  <LayoutGrid className="h-3.5 w-3.5" aria-hidden /> All dashboards
                </Link>
              )}
            </div>
          )}

          <div className="py-1">
            {isAdmin && (
              <Link to="/admin" role="menuitem" className={item}>
                <ADMIN_ICON className="h-3.5 w-3.5 text-muted-foreground" aria-hidden /> Admin console
              </Link>
            )}
            <Link to="/account/password" role="menuitem" className={item}>
              <KeyRound className="h-3.5 w-3.5 text-muted-foreground" aria-hidden /> Change password
            </Link>
            <button type="button" role="menuitem" onClick={signOut} className={`${item} text-destructive hover:bg-destructive/10`}>
              <LogOut className="h-3.5 w-3.5" aria-hidden /> Sign out
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
