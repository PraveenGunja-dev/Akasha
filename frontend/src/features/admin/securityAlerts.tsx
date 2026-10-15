import { useEffect, useSyncExternalStore } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { useAuth } from '../../context/AuthContext';
import { adminApi } from './adminApi';
import type { AlertSummary } from './adminApi';
import { alertSentence } from './events';

/* Security alerts for people who hold audit.view: one poller for the whole
   app (every minute, and when the tab regains focus), read by the badges in
   the account menu, the admin rail and the dashboard picker. A new alert
   raises a toast once per browser. */

const POLL_MS = 60_000;
let summary: AlertSummary | null = null;
const listeners = new Set<() => void>();
const emit = () => listeners.forEach(l => l());

export async function refreshAlerts(): Promise<AlertSummary | null> {
  try {
    summary = await adminApi.alertSummary();
  } catch {
    summary = null;
  }
  emit();
  return summary;
}

/** Open alerts, or null when not polled (no audit.view) or unavailable. */
export function useAlertSummary(): AlertSummary | null {
  return useSyncExternalStore(
    cb => { listeners.add(cb); return () => { listeners.delete(cb); }; },
    () => summary,
  );
}

const seenKey = (userId: number) => `akasha.alerts.seen.${userId}`;
const readSeen = (userId: number): number | null => {
  try { const v = localStorage.getItem(seenKey(userId)); return v ? Number(v) : null; } catch { return null; }
};
const writeSeen = (userId: number, id: number) => {
  try { localStorage.setItem(seenKey(userId), String(id)); } catch { /* private mode: toast again next load */ }
};

/** Mount once inside the router. Polls only for users who may see alerts. */
export function SecurityAlertWatcher() {
  const { user, can } = useAuth();
  const navigate = useNavigate();
  const allowed = !!user && can('audit.view') && !user.must_change_password;
  const userId = user?.id;

  useEffect(() => {
    if (!allowed || userId === undefined) {
      summary = null;
      emit();
      return;
    }
    let stopped = false;
    const tick = async () => {
      const s = await refreshAlerts();
      if (stopped || !s?.latest) return;
      const seen = readSeen(userId);
      if (seen !== null && s.latest.id <= seen) return;
      writeSeen(userId, s.latest.id);
      const review = { label: 'Review', onClick: () => navigate('/admin/alerts') };
      const more = s.open > 1 ? ` (${s.open} open)` : '';
      const notify = s.latest.severity === 'critical' ? toast.error : toast.warning;
      notify(`Security alert${more}`, { description: alertSentence(s.latest), action: review, duration: 12_000 });
    };
    tick();
    const timer = window.setInterval(() => { if (document.visibilityState === 'visible') tick(); }, POLL_MS);
    const onFocus = () => tick();
    window.addEventListener('focus', onFocus);
    return () => { stopped = true; window.clearInterval(timer); window.removeEventListener('focus', onFocus); };
  }, [allowed, userId, navigate]);

  return null;
}
