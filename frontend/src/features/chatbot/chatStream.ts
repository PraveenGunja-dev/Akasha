import {
  getChatSourceNames,
  normalizeChatMetadata,
  type ChatMessageMetadata,
  type ChatSources,
} from './chatContract.ts';

export type { ChatSources } from './chatContract.ts';
export type ChatStreamMetadata = ChatMessageMetadata;

interface ChatStreamEventBase {
  request_id?: string;
  stream_version?: string;
  sequence?: number;
  session_id?: string;
  run_id?: string;
}

export type ChatTerminalStatus = 'completed' | 'failed' | 'cancelled' | 'interrupted';

export type ChatStreamEvent =
  | (ChatStreamEventBase & { type: 'start'; session_id: string; user_message_id: number; assistant_message_id?: number; engine?: string })
  | (ChatStreamEventBase & { type: 'status'; status: string })
  | (ChatStreamEventBase & { type: 'token'; content: string })
  | (ChatStreamEventBase & { type: 'visualization'; chart_type?: string; title?: string; spec?: unknown })
  | (ChatStreamEventBase & { type: 'metadata'; metadata: ChatStreamMetadata; suggestions: string[] })
  | (ChatStreamEventBase & { type: 'error'; code?: string; error?: string; detail?: string; message?: string })
  | (ChatStreamEventBase & { type: 'cancelled'; message_id: number; status: 'cancelled' })
  | (ChatStreamEventBase & { type: 'done'; session_id: string; message_id: number; status: ChatTerminalStatus; engine?: string })
  | (ChatStreamEventBase & { type: 'unknown'; eventType: string; payload: Record<string, unknown> });

export class ChatStreamError extends Error {
  readonly requestId?: string;

  constructor(message: string, requestId?: string) {
    super(message);
    this.name = 'ChatStreamError';
    this.requestId = requestId;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function optionalString(value: unknown): string | undefined {
  return typeof value === 'string' ? value : undefined;
}

function normalizeRequestId(value: unknown): string | undefined {
  const requestId = optionalString(value)?.trim();
  return requestId || undefined;
}

function parseEvent(frame: string): ChatStreamEvent | null {
  const data = frame
    .split(/\r\n|\r|\n/)
    .filter(line => line.startsWith('data:'))
    .map(line => line.slice(5).replace(/^ /, ''))
    .join('\n');

  if (!data || data === '[DONE]') return null;

  let payload: unknown;
  try {
    payload = JSON.parse(data);
  } catch {
    throw new ChatStreamError('The chat server returned a malformed stream event.');
  }

  if (!isRecord(payload) || typeof payload.type !== 'string') {
    throw new ChatStreamError('The chat server returned an invalid stream event.');
  }

  const request_id = normalizeRequestId(payload.request_id);
  const base: ChatStreamEventBase = { request_id };
  if (typeof payload.stream_version === 'string') base.stream_version = payload.stream_version;
  if (typeof payload.sequence === 'number') base.sequence = payload.sequence;
  if (typeof payload.session_id === 'string') base.session_id = payload.session_id;
  if (typeof payload.run_id === 'string') base.run_id = payload.run_id;

  switch (payload.type) {
    case 'start':
      if (typeof payload.session_id !== 'string' || typeof payload.user_message_id !== 'number') {
        throw new ChatStreamError('The chat server returned an invalid start event.', request_id);
      }
      return {
        ...base,
        type: 'start',
        session_id: payload.session_id,
        user_message_id: payload.user_message_id,
        ...(typeof payload.assistant_message_id === 'number' ? { assistant_message_id: payload.assistant_message_id } : {}),
        ...(optionalString(payload.engine) ? { engine: optionalString(payload.engine) } : {}),
      };
    case 'status':
      if (typeof payload.status !== 'string') {
        throw new ChatStreamError('The chat server returned an invalid status event.', request_id);
      }
      return { ...base, type: 'status', status: payload.status };
    case 'token':
      if (typeof payload.content !== 'string') {
        throw new ChatStreamError('The chat server returned an invalid token event.', request_id);
      }
      return { ...base, type: 'token', content: payload.content };
    case 'visualization':
      return {
        type: 'visualization',
        chart_type: optionalString(payload.chart_type),
        title: optionalString(payload.title),
        spec: payload.spec,
        ...base,
      };
    case 'metadata':
      if (!isRecord(payload.metadata)) {
        throw new ChatStreamError('The chat server returned an invalid metadata event.', request_id);
      }
      return {
        type: 'metadata',
        metadata: normalizeChatMetadata(payload.metadata, {
          sources: payload.sources,
          suggestions: payload.suggestions,
        }),
        suggestions: Array.isArray(payload.suggestions)
          ? payload.suggestions.filter((suggestion): suggestion is string => typeof suggestion === 'string')
          : [],
        ...base,
      };
    case 'error': {
      const nestedError = isRecord(payload.error) ? payload.error : undefined;
      return {
        ...base,
        type: 'error',
        code: optionalString(nestedError?.code) || optionalString(payload.code),
        error: optionalString(payload.error) || optionalString(nestedError?.message),
        detail: optionalString(payload.detail),
        message: optionalString(payload.message),
      };
    }
    case 'cancelled':
      if (typeof payload.message_id !== 'number') {
        throw new ChatStreamError('The chat server returned an invalid cancellation event.', request_id);
      }
      return { ...base, type: 'cancelled', message_id: payload.message_id, status: 'cancelled' };
    case 'done':
      if (typeof payload.session_id !== 'string' || typeof payload.message_id !== 'number') {
        throw new ChatStreamError('The chat server returned an invalid done event.', request_id);
      }
      return {
        ...base,
        type: 'done',
        session_id: payload.session_id,
        message_id: payload.message_id,
        status: payload.status === 'failed' || payload.status === 'cancelled' || payload.status === 'interrupted'
          ? payload.status
          : 'completed',
        ...(optionalString(payload.engine) ? { engine: optionalString(payload.engine) } : {}),
      };
    default:
      return { ...base, type: 'unknown', eventType: payload.type, payload };
  }
}

async function getResponseError(response: Response): Promise<string> {
  const fallback = `Chat request failed (${response.status}${response.statusText ? ` ${response.statusText}` : ''}).`;

  try {
    const body: unknown = JSON.parse(await response.text());
    if (!isRecord(body)) return fallback;
    return optionalString(body.detail) || optionalString(body.error) || optionalString(body.message) || fallback;
  } catch {
    return fallback;
  }
}

export function getChatSources(sources: ChatSources | undefined): string[] {
  return getChatSourceNames(sources);
}

export function getChatStreamError(event: Extract<ChatStreamEvent, { type: 'error' }>): string {
  return event.error || event.detail || event.message || 'The chat stream failed.';
}

export function getChatRequestId(response: Response): string | undefined {
  return normalizeRequestId(response.headers.get('X-Request-ID'));
}

export function formatChatError(
  error: unknown,
  fallbackRequestId?: string,
  fallbackMessage = 'Unknown chat error.',
): string {
  const message = error instanceof Error ? error.message : fallbackMessage;
  const requestId = error instanceof ChatStreamError ? error.requestId || fallbackRequestId : fallbackRequestId;
  return requestId ? `${message} (Request ID: ${requestId})` : message;
}

export async function* readChatStream(response: Response): AsyncGenerator<ChatStreamEvent> {
  const responseRequestId = getChatRequestId(response);
  if (!response.ok) throw new ChatStreamError(await getResponseError(response), responseRequestId);
  if (!response.body) throw new ChatStreamError('The chat server returned an empty response.', responseRequestId);

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let completed = false;
  let expectedSequence = 1;
  let streamSessionId: string | undefined;
  let streamRunId: string | undefined;

  const validateLifecycle = (event: ChatStreamEvent): ChatStreamEvent => {
    if (completed) throw new ChatStreamError('The chat server returned an event after completion.', event.request_id || responseRequestId);
    if (event.stream_version === '2.0') {
      if (event.sequence !== expectedSequence) {
        throw new ChatStreamError('The chat stream sequence is invalid.', event.request_id || responseRequestId);
      }
      expectedSequence += 1;
      streamSessionId ||= event.session_id;
      streamRunId ||= event.run_id;
      if (!event.session_id || !event.run_id || event.session_id !== streamSessionId || event.run_id !== streamRunId) {
        throw new ChatStreamError('The chat stream correlation is invalid.', event.request_id || responseRequestId);
      }
    }
    if (event.type === 'done') completed = true;
    return event;
  };

  const takeFrame = (): string | null => {
    const delimiter = /\r\n\r\n|\n\n|\r\r/.exec(buffer);
    if (!delimiter || delimiter.index === undefined) return null;
    const frame = buffer.slice(0, delimiter.index);
    buffer = buffer.slice(delimiter.index + delimiter[0].length);
    return frame;
  };

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let frame = takeFrame();
      while (frame !== null) {
        const event = parseEvent(frame);
        if (event) yield validateLifecycle(event);
        frame = takeFrame();
      }
    }

    buffer += decoder.decode();

    let frame = takeFrame();
    while (frame !== null) {
      const event = parseEvent(frame);
      if (event) yield validateLifecycle(event);
      frame = takeFrame();
    }

    if (buffer.trim()) {
      const event = parseEvent(buffer);
      if (event) yield validateLifecycle(event);
    }
    if (!completed) throw new ChatStreamError('The chat stream ended before a terminal event.', responseRequestId);
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') throw error;
    if (error instanceof ChatStreamError) {
      throw error.requestId ? error : new ChatStreamError(error.message, responseRequestId);
    }
    throw new ChatStreamError('The chat stream was interrupted.', responseRequestId);
  } finally {
    reader.releaseLock();
  }
}
