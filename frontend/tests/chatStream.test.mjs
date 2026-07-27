import assert from 'node:assert/strict';
import test from 'node:test';

import {
  ChatStreamError,
  formatChatError,
  getChatRequestId,
  getChatStreamError,
  readChatStream,
} from '../src/features/chatbot/chatStream.ts';

const encoder = new TextEncoder();

function streamingResponse(chunks, requestId = 'header-request') {
  return new Response(new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  }), {
    headers: { 'X-Request-ID': requestId },
  });
}

async function collectEvents(response) {
  const events = [];
  for await (const event of readChatStream(response)) events.push(event);
  return events;
}

test('retains request IDs across split, unknown, and final unterminated SSE frames', async () => {
  const response = streamingResponse([
    'data: {"type":"token","content":"hel',
    'lo","request_id":"event-token"}\n\n',
    'data: {"type":"progress","request_id":"event-unknown","step":1}\n\n',
    'data: {"type":"metadata","metadata":{},"suggestions":[],"request_id":"event-metadata"}\n\n',
    'data: {"type":"done","session_id":"legacy","message_id":1,"request_id":"event-done"}',
  ]);

  assert.equal(getChatRequestId(response), 'header-request');
  const events = await collectEvents(response);
  assert.deepEqual(events.map(event => [event.type, event.request_id]), [
    ['token', 'event-token'],
    ['unknown', 'event-unknown'],
    ['metadata', 'event-metadata'],
    ['done', 'event-done'],
  ]);
});

test('retains typed error correlation and formats its sanitized message', async () => {
  const [event] = await collectEvents(streamingResponse([
    'data: {"type":"error","error":{"code":"chat_stream_failed","message":"The chat response could not be completed."},"request_id":"event-error"}\n\n',
    'data: {"type":"done","session_id":"legacy","message_id":1,"status":"failed","request_id":"event-error"}\n\n',
  ]));

  assert.equal(event.type, 'error');
  assert.equal(event.request_id, 'event-error');
  assert.equal(getChatStreamError(event), 'The chat response could not be completed.');
  const error = new ChatStreamError(getChatStreamError(event), event.request_id);
  assert.equal(
    formatChatError(error),
    'The chat response could not be completed. (Request ID: event-error)',
  );
});

test('attaches the response header request ID to HTTP errors', async () => {
  const response = new Response(JSON.stringify({ detail: 'Service unavailable.' }), {
    status: 503,
    headers: {
      'Content-Type': 'application/json',
      'X-Request-ID': 'http-request',
    },
  });

  await assert.rejects(
    async () => collectEvents(response),
    error => {
      assert.ok(error instanceof ChatStreamError);
      assert.equal(error.requestId, 'http-request');
      assert.equal(formatChatError(error), 'Service unavailable. (Request ID: http-request)');
      return true;
    },
  );
});

test('parses the Phase 1 start, status, and done lifecycle contract', async () => {
  const events = await collectEvents(streamingResponse([
    'data: {"type":"start","session_id":"abc123","user_message_id":41,"request_id":"req-1"}\n\n',
    'data: {"type":"status","status":"analyzing","request_id":"req-1"}\n\n',
    'data: {"type":"done","session_id":"abc123","message_id":42,"request_id":"req-1"}\n\n',
  ]));
  assert.deepEqual(events, [
    { type: 'start', session_id: 'abc123', user_message_id: 41, request_id: 'req-1' },
    { type: 'status', status: 'analyzing', request_id: 'req-1' },
    { type: 'done', session_id: 'abc123', message_id: 42, status: 'completed', request_id: 'req-1' },
  ]);
});

test('validates the Phase 2 correlated lifecycle and cancellation terminal state', async () => {
  const common = '"stream_version":"2.0","session_id":"session","run_id":"run","request_id":"req-2"';
  const events = await collectEvents(streamingResponse([
    `data: {"type":"start","sequence":1,"user_message_id":7,"assistant_message_id":8,${common}}\n\n`,
    `data: {"type":"status","sequence":2,"status":"running",${common}}\n\n`,
    `data: {"type":"cancelled","sequence":3,"message_id":8,"status":"cancelled",${common}}\n\n`,
    `data: {"type":"done","sequence":4,"message_id":8,"status":"cancelled",${common}}\n\n`,
  ]));

  assert.deepEqual(events.map(event => [event.type, event.sequence, event.run_id]), [
    ['start', 1, 'run'],
    ['status', 2, 'run'],
    ['cancelled', 3, 'run'],
    ['done', 4, 'run'],
  ]);
  assert.equal(events.at(-1).status, 'cancelled');
});

test('rejects a clean EOF without a terminal done event', async () => {
  await assert.rejects(
    async () => collectEvents(streamingResponse([
      'data: {"type":"token","content":"partial","request_id":"req-partial"}\n\n',
    ])),
    /ended before a terminal event/,
  );
});
