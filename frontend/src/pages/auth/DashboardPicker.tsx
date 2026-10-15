import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowRight, KeyRound, LayoutGrid, LogOut, ShieldCheck } from 'lucide-react';
import { useAuth, ADMIN_PERMISSIONS } from '../../context/AuthContext';
import { DASHBOARD_ICONS, FALLBACK_ICON, lastDashboard, rememberDashboard } from '../../components/auth/dashboardMeta';
import { AppFrame, AppHeader, AppRail } from '../../components/layout/AppRail';
import { containerVariants, itemVariants } from '../../components/ui/primitives';
import { DASHBOARDS } from '../../features/workspace/dashboards';
import HeroBanner from '../../components/layout/HeroBanner';

/* After sign-in: a personal greeting, then every dashboard the user's role
   opens, each in its own accent from the brand ramp (identity colours, not
   status), with what is inside it. Same rail and header as the dashboards. */

// Identity accents from the brand tokens (never the status palette).
const ACCENT: Record<string, string> = {
  executive: 'var(--brand-blue)',
  pmag: 'var(--brand-purple)',
  projects: 'var(--brand-pink)',
  tc_ordering: 'color-mix(in srgb, var(--brand-blue) 55%, var(--brand-purple))',
  tc_stores: 'color-mix(in srgb, var(--brand-purple) 50%, var(--brand-pink))',
};

function greeting(now = new Date()) {
  const h = now.getHours();
  if (h < 5) return 'Working late';
  if (h < 12) return 'Good morning';
  if (h < 17) return 'Good afternoon';
  return 'Good evening';
}

const WARM = [
  'Great to have you back.',
  'Everything you need is one click away.',
  'Your portfolio, ready when you are.',
];

export default function DashboardPicker() {
  const { user, logout, canAny } = useAuth();
  const navigate = useNavigate();
  if (!user) return null;

  const firstName = user.display_name.split(' ')[0];
  const last = lastDashboard(user.id);
  const isAdmin = canAny(ADMIN_PERMISSIONS);
  const scope = user.portfolio_access;
  const warm = WARM[new Date().getDate() % WARM.length];
  const lastLogin = user.last_login_at
    ? new Date(user.last_login_at + (/[zZ]|[+-]\d\d:?\d\d$/.test(user.last_login_at) ? '' : 'Z'))
    : null;

  const open = (route: string, key: string) => { rememberDashboard(user.id, key); navigate(route); };
  const signOut = async () => { await logout(); navigate('/login', { replace: true }); };

  const railGroups = [
    { title: 'Home', items: [{ id: 'home', label: 'All dashboards', icon: <LayoutGrid /> }] },
    {
      title: 'Dashboards',
      items: user.dashboards.map(d => {
        const Icon = DASHBOARD_ICONS[d.key] ?? FALLBACK_ICON;
        return { id: d.key, label: d.label, icon: <Icon /> };
      }),
    },
  ];
  const footer = [
    ...(isAdmin ? [{ id: 'admin', label: 'Admin console', icon: <ShieldCheck /> }] : []),
    { id: 'password', label: 'Change password', icon: <KeyRound /> },
    { id: 'signout', label: 'Sign out', icon: <LogOut /> },
  ];
  const onRail = (id: string) => {
    if (id === 'home') return;
    if (id === 'admin') return navigate('/admin');
    if (id === 'password') return navigate('/account/password');
    if (id === 'signout') return signOut();
    const d = user.dashboards.find(x => x.key === id);
    if (d) open(d.route, d.key);
  };

  return (
    <AppFrame
      rail={<AppRail subtitle="Execution platform" groups={railGroups} footer={footer} active="home" onSelect={onRail} />}
      header={<AppHeader kicker="AKASHA" title="Your dashboards" />}>
      <motion.div variants={containerVariants} initial="hidden" animate="show" className="w-full space-y-6">
        {/* Greeting */}
        <motion.div variants={itemVariants}>
          <HeroBanner part1={`${greeting()},`} part2={firstName} sub={warm}>
            <div className="flex flex-wrap items-center gap-2 text-[12px]">
              <span className="rounded-full border border-border bg-card/80 px-2.5 py-1 font-semibold text-foreground backdrop-blur">{user.role_name}</span>
              <span className="rounded-full border border-border bg-card/80 px-2.5 py-1 text-muted-foreground backdrop-blur">
                {scope.all ? 'All portfolios' : scope.clusters.join(', ')}
              </span>
              <span className="rounded-full border border-border bg-card/80 px-2.5 py-1 text-muted-foreground backdrop-blur">
                {user.dashboards.length} dashboard{user.dashboards.length === 1 ? '' : 's'}
              </span>
              {lastLogin && (
                <span className="rounded-full border border-border bg-card/80 px-2.5 py-1 text-muted-foreground backdrop-blur">
                  Signed in {lastLogin.toLocaleString('en-IN', { weekday: 'short', day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}
                </span>
              )}
            </div>
          </HeroBanner>
        </motion.div>

        {/* Dashboards */}
        <section>
          <motion.h2 variants={itemVariants} className="section-label mb-3 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            Choose a dashboard
          </motion.h2>
          {user.dashboards.length === 0 ? (
            <p className="text-sm text-muted-foreground">No dashboard is assigned to your role yet. Ask an administrator for access.</p>
          ) : (
            <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-5">
              {user.dashboards.map(d => {
                const Icon = DASHBOARD_ICONS[d.key] ?? FALLBACK_ICON;
                const cfg = DASHBOARDS[d.key];
                const live = cfg?.kpis.filter(k => k.status === 'live' || k.status === 'partial').length ?? 0;
                const sections = cfg ? cfg.groups.reduce((n, g) => n + g.sections.length, 0) : null;
                return (
                  <motion.li key={d.key} variants={itemVariants}>
                    <button type="button" onClick={() => open(d.route, d.key)}
                      style={{ ['--kpi-accent' as string]: ACCENT[d.key] ?? 'var(--brand-blue)' }}
                      className="bento-card kpi-card cursor-pointer group flex h-full w-full flex-col p-5 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary">
                      <span className="flex items-start justify-between gap-3">
                        <span className="flex h-11 w-11 items-center justify-center rounded-xl text-white shadow-sm"
                          style={{ background: 'var(--kpi-accent)' }}>
                          <Icon className="h-5 w-5" aria-hidden />
                        </span>
                        {last === d.key && <span className="rounded-full border border-border bg-card px-2 py-0.5 text-[10px] text-muted-foreground">Last opened</span>}
                      </span>
                      <span className="mt-4 text-[16px] font-semibold text-foreground">{d.label}</span>
                      <span className="mt-1 flex-1 text-[12.5px] leading-snug text-muted-foreground">{d.description}</span>
                      <span className="mt-4 flex items-center justify-between border-t border-border/70 pt-3 text-[11.5px] text-muted-foreground">
                        <span>
                          {cfg ? <>{sections} sections · <b className="font-semibold text-foreground">{live}</b>/{cfg.kpis.length} KPIs live</> : 'Full portfolio command centre'}
                        </span>
                        <span className="inline-flex items-center gap-1 font-semibold" style={{ color: 'var(--kpi-accent)' }}>
                          Open <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" />
                        </span>
                      </span>
                    </button>
                  </motion.li>
                );
              })}
            </ul>
          )}
        </section>

        {/* Administration and account */}
        <section>
          <motion.h2 variants={itemVariants} className="section-label mb-3 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            {isAdmin ? 'Administration & account' : 'Account'}
          </motion.h2>
          <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {isAdmin && (
              <motion.li variants={itemVariants}>
                <QuickCard icon={<ShieldCheck className="h-5 w-5" />} title="Admin console"
                  text="Users, roles & permissions, API keys, audit log" onClick={() => navigate('/admin')} />
              </motion.li>
            )}
            <motion.li variants={itemVariants}>
              <QuickCard icon={<KeyRound className="h-5 w-5" />} title="Change password"
                text="Other devices are signed out when you change it" onClick={() => navigate('/account/password')} />
            </motion.li>
            <motion.li variants={itemVariants}>
              <QuickCard icon={<LogOut className="h-5 w-5" />} title="Sign out" text={`Signed in as ${user.username}`} onClick={signOut} />
            </motion.li>
          </ul>
        </section>
      </motion.div>
    </AppFrame>
  );
}

function QuickCard({ icon, title, text, onClick }: { icon: React.ReactNode; title: string; text: string; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick}
      className="bento-card group flex w-full items-center gap-3 p-4 text-left transition-colors hover:border-primary/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary">
      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-muted text-foreground">{icon}</span>
      <span className="min-w-0 flex-1">
        <span className="block text-[13.5px] font-semibold text-foreground">{title}</span>
        <span className="block truncate text-[12px] text-muted-foreground">{text}</span>
      </span>
      <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-primary" />
    </button>
  );
}
