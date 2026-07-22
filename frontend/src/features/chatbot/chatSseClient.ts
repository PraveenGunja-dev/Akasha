export interface ChatSseEvent {
  type: string;
  content?: string;
  question?: string;
  message?: string;
  suggestions?: string[];
  metadata?: any;
  message_id?: number;
  data_as_of?: string | null;
  latency_ms?: number;
  intent?: string;
  sources?: string[];
  freshness?: Record<string, { as_of?: string | null }>;
  [key: string]: any;
}

export interface ChatRequestPayload {
  message: string;
  history?: any[];
  projectId?: string;
  sessionId?: string;
  isDeepAnalysis?: boolean;
  imageData?: string | null;
  mode?: 'auto' | 'fast' | 'analysis';
  client_version?: string;
}

interface StreamChatOptions {
  token?: string | null;
  signal?: AbortSignal;
  onEvent: (event: ChatSseEvent) => void;
}

export async function streamChat(
  payload: ChatRequestPayload,
  { token, signal, onEvent }: StreamChatOptions
): Promise<void> {
  const response = await fetch('/akasha/api/chat', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(payload),
    signal,
  });

  if (!response.ok) {
    let detail = 'Connection failed';
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch {
      detail = response.statusText || detail;
    }
    throw new Error(detail);
  }

  if (!response.body) {
    throw new Error('Streaming response was empty.');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split('\n\n');
    buffer = events.pop() || '';

    for (const eventText of events) {
      const data = parseSseData(eventText);
      if (data) onEvent(data);
    }
  }

  buffer += decoder.decode();
  const trailing = parseSseData(buffer);
  if (trailing) onEvent(trailing);
}

function parseSseData(eventText: string): ChatSseEvent | null {
  const dataLines = eventText
    .split('\n')
    .filter(line => line.startsWith('data:'))
    .map(line => line.slice(5).trimStart());

  if (dataLines.length === 0) return null;

  try {
    return JSON.parse(dataLines.join('\n'));
  } catch {
    return null;
  }
}

export function metadataFromEvent(event: ChatSseEvent): any {
  return event.metadata || {
    message_id: event.message_id,
    data_as_of: firstFreshnessTimestamp(event.freshness),
    latency_ms: event.latency_ms,
    intent: event.intent,
    sources: { tables: event.sources || [] },
  };
}

function firstFreshnessTimestamp(freshness?: Record<string, { as_of?: string | null }>): string | null {
  if (!freshness) return null;
  const item = Object.values(freshness).find(value => value?.as_of);
  return item?.as_of || null;
}
