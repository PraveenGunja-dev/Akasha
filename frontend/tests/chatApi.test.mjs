import assert from 'node:assert/strict';
import test from 'node:test';

import {
  createChatSession,
  hasLegacyBrowserChats,
  listChatSessions,
  migrateLegacyBrowserChats,
  sendChatMessage,
  submitChatFeedback,
} from '../src/features/chatbot/chatApi.ts';


class MemoryStorage {
  values = new Map();
  get length() { return this.values.size; }
  key(index) { return [...this.values.keys()][index] ?? null; }
  getItem(key) { return this.values.get(key) ?? null; }
  setItem(key, value) { this.values.set(key, String(value)); }
  removeItem(key) { this.values.delete(key); }
  clear() { this.values.clear(); }
}

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

test('creates a session through the server-generated session API', async () => {
  globalThis.localStorage = new MemoryStorage();
  let request;
  globalThis.fetch = async (url, init) => {
    request = { url, init };
    return jsonResponse({ session_id: 'a'.repeat(32), title: 'Test' }, 201);
  };
  const session = await createChatSession('Test');
  assert.equal(session.session_id, 'a'.repeat(32));
  assert.equal(request.url, '/akasha/api/chat/sessions');
  assert.equal(request.init.method, 'POST');
  assert.deepEqual(JSON.parse(request.init.body), { title: 'Test' });
});

test('loads every page of chat history', async () => {
  const firstPage = Array.from({ length: 100 }, (_, index) => ({
    session_id: `session-${index}`,
  }));
  const secondPage = [{ session_id: 'session-100' }, { session_id: 'session-101' }];
  const requests = [];
  globalThis.fetch = async url => {
    requests.push(url);
    return jsonResponse(requests.length === 1 ? firstPage : secondPage);
  };

  const sessions = await listChatSessions();

  assert.equal(sessions.length, 102);
  assert.deepEqual(requests, [
    '/akasha/api/chat/sessions?skip=0&limit=100',
    '/akasha/api/chat/sessions?skip=100&limit=100',
  ]);
});

test('legacy migration clears imported items incrementally and is retry-safe', async () => {
  globalThis.localStorage = new MemoryStorage();
  localStorage.setItem('akasha_threads_v2', JSON.stringify([
    { id: 1, title: 'One' },
    { id: 2, title: 'Two' },
  ]));
  localStorage.setItem('akasha_msgs_1', JSON.stringify([{ type: 'user', content: 'First' }]));
  localStorage.setItem('akasha_msgs_2', JSON.stringify([{ type: 'bot', content: 'Second' }]));
  let calls = 0;
  globalThis.fetch = async () => {
    calls += 1;
    if (calls === 2) return jsonResponse({ detail: 'Temporary failure' }, 503);
    return jsonResponse({ session_id: String(calls).repeat(32) }, 201);
  };

  await assert.rejects(() => migrateLegacyBrowserChats(true), /Temporary failure/);
  assert.equal(localStorage.getItem('akasha_msgs_1'), null);
  assert.ok(localStorage.getItem('akasha_msgs_2'));
  assert.deepEqual(JSON.parse(localStorage.getItem('akasha_threads_v2')), [{ id: 2, title: 'Two' }]);

  const imported = await migrateLegacyBrowserChats(true);
  assert.equal(imported, 1);
  assert.equal(hasLegacyBrowserChats(), false);
});

test('declining migration removes unscoped browser history', async () => {
  globalThis.localStorage = new MemoryStorage();
  localStorage.setItem('akasha_threads_v2', '[]');
  localStorage.setItem('akasha_msgs_orphan', '[]');
  globalThis.fetch = async () => { throw new Error('No API call expected'); };
  assert.equal(hasLegacyBrowserChats(), true);
  assert.equal(await migrateLegacyBrowserChats(false), 0);
  assert.equal(hasLegacyBrowserChats(), false);
});

test('rejects non-ok chat and feedback responses with server details', async () => {
  globalThis.fetch = async url => jsonResponse({ detail: `Rejected ${url}` }, 422);
  await assert.rejects(
    () => sendChatMessage({ message: 'Hello', sessionId: 'a'.repeat(32) }),
    /Rejected \/akasha\/api\/chat/,
  );
  await assert.rejects(
    () => submitChatFeedback({ messageId: 4, feedbackType: 'thumbs_up' }),
    /Rejected \/akasha\/api\/chat\/messages\/4\/feedback/,
  );
});
