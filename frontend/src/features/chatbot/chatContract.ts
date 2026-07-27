export type ChatSources = string[] | { tables?: string[]; systems?: unknown[]; sources?: unknown[] };

export interface ChatMessageMetadata {
  message_id?: number;
  data_as_of?: string | null;
  latency_ms?: number;
  intent?: string;
  request_id?: string;
  sources?: ChatSources;
  suggestions?: string[];
  [key: string]: unknown;
}

interface MetadataFields {
  sources?: unknown;
  suggestions?: unknown;
}

const SOURCE_NAMES: Record<string, string> = {
  p6: 'Oracle Primavera P6',
  sap: 'SAP',
  tc: 'Transmission Control',
  pulse: 'Pulse',
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function sourceName(value: string): string {
  const lower = value.toLowerCase();
  if (lower.includes('primavera') || lower.includes('p6')) return SOURCE_NAMES.p6;
  if (lower.includes('sap') || lower.includes('mt_poamount')) return SOURCE_NAMES.sap;
  if (lower.includes('teamcenter') || lower.includes('tc_')) return SOURCE_NAMES.tc;
  if (lower.includes('pulse') || lower.includes('notification')) return SOURCE_NAMES.pulse;
  return value;
}

export function normalizeChatMetadata(value: unknown, fields: MetadataFields = {}): ChatMessageMetadata {
  const raw = isRecord(value) ? value : {};
  const metadata: ChatMessageMetadata = { ...raw };
  const sources = fields.sources ?? raw.sources;
  const suggestions = fields.suggestions ?? raw.suggestions;

  if (sources !== undefined) metadata.sources = sources as ChatSources;
  if (Array.isArray(suggestions)) {
    metadata.suggestions = suggestions.filter((item): item is string => typeof item === 'string');
  }
  return metadata;
}

export function mergeChatMetadata(
  current: ChatMessageMetadata | undefined,
  next: ChatMessageMetadata,
): ChatMessageMetadata {
  return { ...(current || {}), ...next };
}

export function getChatSourceNames(value: unknown): string[] {
  let sources: unknown[] = [];
  if (Array.isArray(value)) sources = value;
  else if (isRecord(value)) {
    if (Array.isArray(value.tables)) sources = value.tables;
    else if (Array.isArray(value.systems)) sources = value.systems;
    else if (Array.isArray(value.sources)) sources = value.sources;
  }
  return [...new Set(sources.flatMap(item => {
    if (typeof item === 'string') return [sourceName(item)];
    if (isRecord(item) && typeof item.source_system === 'string') return [sourceName(item.source_system)];
    return [];
  }))];
}
