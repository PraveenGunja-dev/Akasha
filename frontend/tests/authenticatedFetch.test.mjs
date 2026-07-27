import assert from 'node:assert/strict';
import test from 'node:test';


test('adds bearer tokens only to same-origin Akasha API requests', async () => {
  const requests = [];
  let unauthorized = 0;
  globalThis.window = {
    location: { origin: 'https://akasha.example' },
    fetch: async (input, init) => {
      requests.push({ input: String(input), headers: new Headers(init?.headers) });
      return new Response(null, { status: String(input).includes('unauthorized') ? 401 : 200 });
    },
  };
  const { configureAuthenticatedFetch, installAuthenticatedFetch } = await import(
    '../src/auth/authenticatedFetch.ts'
  );
  configureAuthenticatedFetch(async () => 'entra-token', () => { unauthorized += 1; });
  installAuthenticatedFetch();

  await window.fetch('/akasha/api/chat/sessions');
  await window.fetch('https://api.open-meteo.com/v1/forecast');
  await window.fetch('/akasha/api/unauthorized');

  assert.equal(requests[0].headers.get('Authorization'), 'Bearer entra-token');
  assert.equal(requests[1].headers.get('Authorization'), null);
  assert.equal(requests[2].headers.get('Authorization'), 'Bearer entra-token');
  assert.equal(unauthorized, 1);
});

test('development identity headers are scoped to Akasha API requests', async () => {
  const requests = [];
  globalThis.window = {
    location: { origin: 'https://akasha.example' },
    fetch: async (input, init) => {
      requests.push({ input: String(input), headers: new Headers(init?.headers) });
      return new Response(null, { status: 200 });
    },
  };
  const module = await import('../src/auth/authenticatedFetch.ts?development');
  module.configureAuthenticatedFetch(
    async () => null,
    () => {},
    () => ({ userId: '12345678-abcd', role: 'pmag' }),
  );
  module.installAuthenticatedFetch();
  await window.fetch('/akasha/api/chat/sessions');
  await window.fetch('https://api.open-meteo.com/v1/forecast');
  assert.equal(requests[0].headers.get('X-Akasha-Dev-User'), '12345678-abcd');
  assert.equal(requests[0].headers.get('X-Akasha-Dev-Role'), 'pmag');
  assert.equal(requests[1].headers.get('X-Akasha-Dev-User'), null);
});
