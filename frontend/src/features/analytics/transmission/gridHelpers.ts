export interface TcEdge {
  id: string;
  region: string;
  from: string;
  from_label: string;
  to: string;
  to_label: string;
  contractor?: string;
  voltage?: string;
  length?: string;
  status?: string;
  normalized_status?: string;
  erection?: string;
  foundation?: string;
  stringing?: string;
  expected_date?: string;
  mapping_id?: number | null;
  projects: string[];
}

export interface TcNode {
  id: string;
  region: string;
  label: string;
  type: string;
  status: string;
  x?: number;
  y?: number;
}

export const STATUS_META: Record<string, { label: string; color: string; dash?: string }> = {
  charged: { label: "Charged", color: "#10b981" },
  in_progress: { label: "In Progress", color: "#f59e0b", dash: "6, 8" },
  under_bidding: { label: "Under Bidding", color: "#ef4444", dash: "2, 6" },
};

export function statusMeta(normalizedStatus?: string) {
  return STATUS_META[normalizedStatus || ""] || { label: normalizedStatus || "Unknown", color: "#94a3b8", dash: "4, 4" };
}

export function voltageWeight(voltage?: string): number {
  if (!voltage) return 2;
  const match = voltage.match(/\d+/);
  if (!match) return 2;
  const kv = parseInt(match[0], 10);
  if (kv >= 765) return 5;
  if (kv >= 500) return 4;
  if (kv >= 400) return 3;
  return 2;
}

// foundation/erection/stringing come as "done/total" strings (e.g. "192/197"), not percentages.
export function parseStageProgress(value?: string): { done: number; total: number; pct: number } {
  if (!value) return { done: 0, total: 0, pct: 0 };
  const parts = value.split("/").map((p) => parseFloat(p.trim()));
  if (parts.length === 2 && !isNaN(parts[0]) && !isNaN(parts[1]) && parts[1] > 0) {
    return { done: parts[0], total: parts[1], pct: Math.min(100, Math.round((parts[0] / parts[1]) * 100)) };
  }
  const single = parseFloat(value);
  if (!isNaN(single)) return { done: single, total: 100, pct: Math.min(100, Math.round(single)) };
  return { done: 0, total: 0, pct: 0 };
}

export function edgeCompletionPct(edge: TcEdge): number {
  if (edge.normalized_status === "charged") return 100;
  const f = parseStageProgress(edge.foundation).pct;
  const e = parseStageProgress(edge.erection).pct;
  const s = parseStageProgress(edge.stringing).pct;
  return Math.round((f + e + s) / 3);
}

export function parseLengthKm(length?: string): number {
  if (!length) return 0;
  const n = parseFloat(length);
  return isNaN(n) ? 0 : n;
}
