import assert from 'node:assert/strict';
import test from 'node:test';

import {
  clearDevelopmentSession,
  getDevelopmentIdentity,
  startDevelopmentSession,
} from '../src/auth/developmentIdentity.ts';


class MemoryStorage {
  values = new Map();
  get length() { return this.values.size; }
  key(index) { return [...this.values.keys()][index] ?? null; }
  getItem(key) { return this.values.get(key) ?? null; }
  setItem(key, value) { this.values.set(key, String(value)); }
  removeItem(key) { this.values.delete(key); }
  clear() { this.values.clear(); }
}

function resetStorage() {
  globalThis.localStorage = new MemoryStorage();
  globalThis.sessionStorage = new MemoryStorage();
}

test('development profile survives logout and a later login', () => {
  resetStorage();
  const first = startDevelopmentSession('executive', () => 'executive-user-1234');

  clearDevelopmentSession();
  assert.equal(getDevelopmentIdentity(), null);
  const restored = startDevelopmentSession('executive', () => 'must-not-be-used');

  assert.deepEqual(restored, first);
  assert.deepEqual(getDevelopmentIdentity(), first);
});

test('existing session identities are migrated to persistent profiles', () => {
  resetStorage();
  sessionStorage.setItem('akasha_dev_user', 'legacy-user-1234');
  sessionStorage.setItem('akasha_dev_role', 'pmag');

  assert.deepEqual(getDevelopmentIdentity(), {
    userId: 'legacy-user-1234',
    role: 'pmag',
  });
  clearDevelopmentSession();

  assert.deepEqual(
    startDevelopmentSession('pmag', () => 'must-not-be-used'),
    { userId: 'legacy-user-1234', role: 'pmag' },
  );
});

test('development roles retain separate private profiles', () => {
  resetStorage();
  const executive = startDevelopmentSession('executive', () => 'executive-user-1234');
  clearDevelopmentSession();
  const pmag = startDevelopmentSession('pmag', () => 'pmag-user-123456');
  clearDevelopmentSession();

  assert.notEqual(executive.userId, pmag.userId);
  assert.deepEqual(
    startDevelopmentSession('executive', () => 'must-not-be-used'),
    executive,
  );
});
