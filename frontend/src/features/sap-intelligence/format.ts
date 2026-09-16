/* SAP Intelligence — formatters. Indian grouping throughout; crore is the unit
   of the book, so values arrive in Cr and are never re-divided here. */
import type { POStatus, Severity } from './types';

const inr = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 });
const inr2 = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 });
const num = new Intl.NumberFormat('en-IN');

export const fmtCr = (v: number | null | undefined, opts: { decimals?: 0 | 2; sign?: boolean } = {}): string => {
  if (v == null || Number.isNaN(v)) return '—';
  const f = opts.decimals === 2 ? inr2 : inr;
  const s = f.format(Math.abs(v));
  return `${opts.sign && v > 0 ? '+' : v < 0 ? '−' : ''}₹${s} Cr`;
};

export const fmtNum = (v: number | null | undefined): string => (v == null ? '—' : num.format(v));

/** Compact figure for tight tiles: 6,413 stays 6,413; 51,269 → 51.3k. */
export const fmtCompact = (v: number | null | undefined): string => {
  if (v == null) return '—';
  if (Math.abs(v) < 10_000) return num.format(Math.round(v));
  if (Math.abs(v) < 1_000_000) return `${(v / 1000).toFixed(1)}k`;
  return `${(v / 1_000_000).toFixed(1)}M`;
};

export const fmtPct = (v: number | null | undefined, decimals = 1): string => (v == null ? '—' : `${v.toFixed(decimals)}%`);

export const fmtDate = (iso: string | null | undefined): string => {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
};

export const fmtDateTime = (iso: string | null | undefined): string => {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString('en-IN', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
};

export const STATUS_LABEL: Record<POStatus, string> = {
  pending: 'Pending', partial: 'Partially delivered', delivered: 'Delivered', cancelled: 'Cancelled',
};

/** Status → design-system tone. Pending is a normal state, not a warning. */
export const STATUS_TONE: Record<POStatus, 'neutral' | 'watch' | 'done' | 'critical'> = {
  pending: 'neutral', partial: 'watch', delivered: 'done', cancelled: 'critical',
};

export const SEVERITY_TONE: Record<Severity, 'neutral' | 'risk' | 'critical' | 'healthy'> = {
  info: 'neutral', warning: 'risk', critical: 'critical', success: 'healthy',
};

export const relativeAge = (iso: string | null | undefined, staleAfterHours = 48): { label: string; stale: boolean } => {
  if (!iso) return { label: 'never', stale: true };
  const ms = Date.now() - new Date(iso).getTime();
  const h = ms / 36e5;
  const stale = h > staleAfterHours;
  if (h < 1) return { label: 'just now', stale };
  if (h < 24) return { label: `${Math.round(h)}h ago`, stale };
  return { label: `${Math.round(h / 24)}d ago`, stale };
};
