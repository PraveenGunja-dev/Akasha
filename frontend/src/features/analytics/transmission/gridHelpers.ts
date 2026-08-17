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
  /** Traced route from tc_line_geometry, as [lat, lng] points. Null when unmatched,
   *  in which case the map falls back to a straight substation-to-substation chord. */
  path?: [number, number][] | null;
  path_source?: string | null;
  path_confidence?: 'high' | 'medium' | 'low' | null;
  path_length_km?: number | null;
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

// Reserved status palette - fixed, never themed, and never reused as series colors.
// Validated for separation on both surfaces (worst adjacent CVD ΔE 11.3, normal-vision
// ΔE 27.6). Warning sits below 3:1 on a light surface by design, so status is always
// paired with a written label in the legend and popups rather than carried by hue alone.
export const STATUS_META: Record<string, { label: string; color: string; dash?: string }> = {
  charged: { label: "Charged", color: "#0ca30c" },
  in_progress: { label: "In Progress", color: "#fab219", dash: "6, 8" },
  under_bidding: { label: "Under Bidding", color: "#d03b3b", dash: "2, 6" },
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
