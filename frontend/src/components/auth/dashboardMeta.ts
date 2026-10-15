import { Gauge, Briefcase, FolderKanban, ClipboardList, Warehouse, ShieldCheck, LayoutGrid } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

/** Icon per dashboard key (the list of dashboards itself comes from the server). */
export const DASHBOARD_ICONS: Record<string, LucideIcon> = {
  executive: Gauge,
  pmag: Briefcase,
  projects: FolderKanban,
  tc_ordering: ClipboardList,
  tc_stores: Warehouse,
};
export const ADMIN_ICON = ShieldCheck;
export const FALLBACK_ICON = LayoutGrid;

/** The dashboard key whose route the current path sits under, if any. */
export function dashboardKeyForPath(path: string, dashboards: { key: string; route: string }[]): string | null {
  if (path.startsWith('/wind-dashboard')) return 'executive';
  const hit = dashboards.find(d => path === d.route || path.startsWith(d.route + '/'));
  return hit?.key ?? null;
}

// Per-browser convenience only: which dashboard this user opened last, to mark
// it on the picker. Never used for access.
const LAST_KEY = (userId: number) => `akasha_last_dashboard_${userId}`;
export function rememberDashboard(userId: number, key: string) {
  try { localStorage.setItem(LAST_KEY(userId), key); } catch { /* not remembered */ }
}
export function lastDashboard(userId: number): string | null {
  try { return localStorage.getItem(LAST_KEY(userId)); } catch { return null; }
}
