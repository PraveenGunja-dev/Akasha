import { useCallback, useEffect, useState } from 'react';
import type { CapacityAction, ActionStatus, ActionPriority } from './types';

/* ═══════════════════════════════════════════════════════════════════════════
   CAPACITY ACTIONS

   A real store, not a button that fires an alert. Actions persist across
   reloads and are shared by every component through a module-level
   subscription, so "Track" in Risks and the count in the header cannot drift
   apart.

   Persistence is localStorage today. `capacityActionService` is the seam: swap
   its four methods for API calls and nothing in the UI changes. It is
   deliberately async so that swap does not become a refactor.
   ═══════════════════════════════════════════════════════════════════════════ */

const STORAGE_KEY = 'akasha.capacity.actions.v1';

const read = (): CapacityAction[] => {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];   // private mode, cleared storage, or a corrupt value
  }
};

const write = (actions: CapacityAction[]) => {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(actions));
  } catch {
    /* Storage unavailable — the in-memory store still serves this session. */
  }
};

export const capacityActionService = {
  async list(): Promise<CapacityAction[]> {
    return read();
  },
  async create(
    input: Omit<CapacityAction, 'id' | 'createdAt' | 'updatedAt' | 'status'> & { status?: ActionStatus },
  ): Promise<CapacityAction> {
    const now = new Date().toISOString();
    const action: CapacityAction = {
      ...input,
      status: input.status ?? 'Open',
      id: `act-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      createdAt: now,
      updatedAt: now,
    };
    write([action, ...read()]);
    return action;
  },
  async update(id: string, patch: Partial<CapacityAction>): Promise<CapacityAction[]> {
    const next = read().map((a) =>
      a.id === id ? { ...a, ...patch, updatedAt: new Date().toISOString() } : a,
    );
    write(next);
    return next;
  },
  async remove(id: string): Promise<CapacityAction[]> {
    const next = read().filter((a) => a.id !== id);
    write(next);
    return next;
  },
};

/* One store for the whole page, so every consumer sees the same list. */
let cache: CapacityAction[] | null = null;
const listeners = new Set<(a: CapacityAction[]) => void>();
const publish = (next: CapacityAction[]) => {
  cache = next;
  listeners.forEach((l) => l(next));
};

export function useCapacityActions() {
  const [actions, setActions] = useState<CapacityAction[]>(cache ?? []);
  const [loading, setLoading] = useState(cache === null);

  useEffect(() => {
    listeners.add(setActions);
    if (cache === null) {
      capacityActionService.list().then((a) => { publish(a); setLoading(false); });
    }
    return () => { listeners.delete(setActions); };
  }, []);

  const createAction = useCallback(async (input: {
    title: string;
    description: string;
    priority: ActionPriority;
    owner: string;
    dueDate: string;
    affectedProjects: string[];
    affectedMW: number;
    sourceInsightId?: string;
  }) => {
    const created = await capacityActionService.create(input);
    publish([created, ...(cache ?? [])]);
    return created;
  }, []);

  const updateAction = useCallback(async (id: string, patch: Partial<CapacityAction>) => {
    publish(await capacityActionService.update(id, patch));
  }, []);

  const removeAction = useCallback(async (id: string) => {
    publish(await capacityActionService.remove(id));
  }, []);

  const setStatus = useCallback(
    (id: string, status: ActionStatus) => updateAction(id, { status }),
    [updateAction],
  );

  const trackedIds = new Set(
    actions.filter((a) => a.status !== 'Dismissed' && a.sourceInsightId).map((a) => a.sourceInsightId as string),
  );

  const openCount = actions.filter((a) => a.status === 'Open' || a.status === 'In Progress').length;

  return { actions, loading, createAction, updateAction, removeAction, setStatus, trackedIds, openCount };
}

/** Default due date: two weeks out, the review cadence these sit on. */
export const defaultDueDate = () => {
  const d = new Date();
  d.setDate(d.getDate() + 14);
  return d.toISOString().slice(0, 10);
};
