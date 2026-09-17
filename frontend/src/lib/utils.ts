import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const pad2 = (n: number) => String(n).padStart(2, '0');

/** dd-mm-yy — the platform-wide date format. Use for every displayed date;
 *  never re-derive a locale string at the call site. Accepts an ISO string,
 *  epoch ms, or a Date; returns '—' for anything missing or unparsable so
 *  callers don't need their own fallback just to catch a bad date. */
export function formatDate(value: string | number | Date | null | undefined): string {
  if (value == null || value === '') return '—';
  const d = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(d.getTime())) return '—';
  return `${pad2(d.getDate())}-${pad2(d.getMonth() + 1)}-${String(d.getFullYear()).slice(-2)}`;
}

/** dd-mm-yy, HH:MM (24-hour, local time). */
export function formatDateTime(value: string | number | Date | null | undefined): string {
  if (value == null || value === '') return '—';
  const d = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(d.getTime())) return '—';
  return `${formatDate(d)}, ${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
}
