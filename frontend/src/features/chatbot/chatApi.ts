import {
  normalizeChatMetadata,
  type ChatMessageMetadata,
  type ChatSources,
} from './chatContract.ts';

export interface ChatSessionSummary {
  session_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  preview: string;
  source: string;
}

export interface StoredChatMessage {
  id: number;
  role: 'user' | 'assistant';
  content: string;
  status: 'running' | 'completed' | 'failed' | 'cancelled' | 'interrupted';
  run_id?: string | null;
  engine?: 'legacy' | 'langgraph' | null;
  model?: string | null;
  error_code?: string | null;
  created_at: string;
  sources: ChatSources;
  visualizations: Array<{ chart_type?: string; title?: string; spec: unknown }>;
  feedback_status: 'none' | 'liked' | 'disliked';
  metadata?: ChatMessageMetadata;
}

export interface ChatSessionDetail extends ChatSessionSummary {
  messages: StoredChatMessage[];
}

export interface ChatFeedbackRequest {
  messageId: number;
  feedbackType: 'thumbs_up' | 'thumbs_down';
}

export interface SendChatRequest {
  message: string;
  sessionId: string;
  projectId?: string;
  isDeepAnalysis?: boolean;
  imageData?: string | null;
}

async function responseError(response: Response): Promise<Error> {
  const fallback = `Chat request failed (${response.status}${response.statusText ? ` ${response.statusText}` : ''}).`;
  try {
    const body: unknown = await response.clone().json();
    if (typeof body === 'object' && body !== null) {
      const detail = (body as Record<string, unknown>).detail;
      const error = (body as Record<string, unknown>).error;
      const message = (body as Record<string, unknown>).message;
      const value = [detail, error, message].find(item => typeof item === 'string');
      if (typeof value === 'string') return new Error(value);
    }
  } catch {
    // Use the status-based message for empty or non-JSON responses.
  }
  return new Error(fallback);
}

async function requireOk(response: Response): Promise<Response> {
  if (!response.ok) throw await responseError(response);
  return response;
}

async function apiJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  await requireOk(response);
  return response.json();
}

export function getStoredChatMetadata(message: StoredChatMessage): ChatMessageMetadata {
  return normalizeChatMetadata(message.metadata, {
    sources: message.sources,
  });
}

export async function listChatSessions(): Promise<ChatSessionSummary[]> {
  const pageSize = 100;
  const sessions: ChatSessionSummary[] = [];
  for (let skip = 0; ; skip += pageSize) {
    const page = await apiJson<ChatSessionSummary[]>(
      `/akasha/api/chat/sessions?skip=${skip}&limit=${pageSize}`,
    );
    sessions.push(...page);
    if (page.length < pageSize) return sessions;
  }
}

export function createChatSession(title?: string): Promise<ChatSessionSummary> {
  return apiJson('/akasha/api/chat/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  });
}

export function getChatSession(sessionId: string): Promise<ChatSessionDetail> {
  return apiJson(`/akasha/api/chat/sessions/${encodeURIComponent(sessionId)}`);
}

export function renameChatSession(sessionId: string, title: string): Promise<ChatSessionSummary> {
  return apiJson(`/akasha/api/chat/sessions/${encodeURIComponent(sessionId)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  });
}

export async function deleteChatSession(sessionId: string): Promise<void> {
  const response = await fetch(`/akasha/api/chat/sessions/${encodeURIComponent(sessionId)}`, { method: 'DELETE' });
  await requireOk(response);
}

export async function sendChatMessage(request: SendChatRequest, signal?: AbortSignal): Promise<Response> {
  const response = await fetch('/akasha/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
    signal,
  });
  return requireOk(response);
}

export function cancelChatRun(runId: string): Promise<{ run_id: string; status: string }> {
  return apiJson(`/akasha/api/chat/runs/${encodeURIComponent(runId)}/cancel`, { method: 'POST' });
}

export function submitChatFeedback(request: ChatFeedbackRequest): Promise<{ id: number; changed: boolean }> {
  return apiJson(`/akasha/api/chat/messages/${encodeURIComponent(request.messageId)}/feedback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      feedback_type: request.feedbackType,
    }),
  });
}

interface LegacyThread {
  id: number | string;
  title?: string;
}

interface LegacyMessage {
  type?: string;
  content?: string;
  timestamp?: string;
}

function clearLegacyChatStorage() {
  const keys = Array.from({ length: localStorage.length }, (_, index) => localStorage.key(index))
    .filter((key): key is string => Boolean(key));
  keys.filter(key => key.startsWith('akasha_msgs_')).forEach(key => localStorage.removeItem(key));
  localStorage.removeItem('akasha_threads_v2');
  localStorage.removeItem('akasha_active_thread');
}

export function hasLegacyBrowserChats(): boolean {
  if (localStorage.getItem('akasha_threads_v2')) return true;
  return Array.from({ length: localStorage.length }, (_, index) => localStorage.key(index))
    .some(key => Boolean(key?.startsWith('akasha_msgs_')));
}

export async function migrateLegacyBrowserChats(importChats: boolean): Promise<number> {
  let imported = 0;
  if (importChats) {
    let threads: LegacyThread[];
    try {
      threads = JSON.parse(localStorage.getItem('akasha_threads_v2') || '[]');
    } catch {
      threads = [];
    }
    let remainingThreads = threads.slice(0, 100);
    for (const thread of [...remainingThreads]) {
      let messages: LegacyMessage[];
      try {
        messages = JSON.parse(localStorage.getItem(`akasha_msgs_${thread.id}`) || '[]');
      } catch {
        messages = [];
      }
      const safeMessages = messages
        .filter(message => (message.type === 'user' || message.type === 'bot') && typeof message.content === 'string' && message.content.trim())
        .slice(0, 200)
        .map(message => ({ type: message.type, content: message.content!.slice(0, 50_000), timestamp: message.timestamp }));
      if (!safeMessages.length) continue;
      await apiJson('/akasha/api/chat/sessions/legacy-import', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: (thread.title || 'Imported conversation').slice(0, 100), messages: safeMessages }),
      });
      imported += 1;
      localStorage.removeItem(`akasha_msgs_${thread.id}`);
      remainingThreads = remainingThreads.filter(item => item.id !== thread.id);
      localStorage.setItem('akasha_threads_v2', JSON.stringify(remainingThreads));
    }
  } else {
    clearLegacyChatStorage();
    return imported;
  }
  clearLegacyChatStorage();
  return imported;
}
