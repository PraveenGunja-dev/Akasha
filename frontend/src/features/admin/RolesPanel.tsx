import { useCallback, useEffect, useMemo, useState } from 'react';
import { Lock, Plus, Trash2 } from 'lucide-react';
import { Dialog, PageHeader, StatusPill } from '../../components/ui/primitives';
import { useAuth } from '../../context/AuthContext';
import { adminApi, btn, field } from './adminApi';
import type { AdminRole, PermissionDef } from './adminApi';

/* Roles and what they grant. The permission catalogue comes from the server
   (services/access.py); which role holds which permission is data, edited
   here. The server repeats every rule shown: only a superadmin can grant the
   administration permissions, Super Admin always holds everything, built-in
   roles cannot be deleted. */

const GROUP_ORDER = ['Dashboards', 'Portfolio access', 'Data', 'Administration'];
const GROUP_NOTE: Record<string, string> = {
  'Portfolio access': 'Without "All portfolios" the user sees only the portfolios ticked, and only on portfolio-aware screens (PMAG).',
  Administration: 'Only a superadmin can grant or remove these.',
};

export default function RolesPanel() {
  const { user: me, can } = useAuth();
  const [roles, setRoles] = useState<AdminRole[]>([]);
  const [perms, setPerms] = useState<PermissionDef[]>([]);
  const [selected, setSelected] = useState<string>('');
  const [draft, setDraft] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [creating, setCreating] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const canEdit = can('roles.manage');
  const isSuper = me?.role === 'superadmin';

  const load = useCallback(async (keep?: string) => {
    try {
      const [r, p] = await Promise.all([adminApi.roles(), adminApi.permissions()]);
      setRoles(r);
      setPerms(p);
      const pick = r.find(x => x.key === (keep ?? selected)) ?? r[0];
      if (pick) { setSelected(pick.key); setDraft(new Set(pick.permissions)); }
    } catch (e) {
      setError((e as Error).message);
    }
  }, [selected]);
  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const role = roles.find(r => r.key === selected);
  const groups = useMemo(() => GROUP_ORDER.map(g => ({ g, items: perms.filter(p => p.group === g) })).filter(x => x.items.length), [perms]);
  const dirty = !!role && (draft.size !== role.permissions.length || role.permissions.some(p => !draft.has(p)));
  const readOnly = !canEdit || !role || role.locked;

  const select = (key: string) => {
    const r = roles.find(x => x.key === key);
    if (!r) return;
    setSelected(key);
    setDraft(new Set(r.permissions));
    setError('');
  };
  const toggle = (key: string) => setDraft(prev => {
    const next = new Set(prev);
    if (next.has(key)) next.delete(key); else next.add(key);
    return next;
  });
  const save = async () => {
    if (!role) return;
    setBusy(true);
    setError('');
    try {
      await adminApi.updateRole(role.key, { permissions: [...draft] });
      setNotice(`${role.name} saved. Users with this role get the change on their next request.`);
      window.setTimeout(() => setNotice(''), 5000);
      await load(role.key);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <PageHeader title="Roles & permissions" subtitle="What each role can open and do. Assign roles to people under Users."
        right={canEdit && <button type="button" className={btn.primary} onClick={() => setCreating(true)}><Plus className="h-3.5 w-3.5" /> New role</button>} />
      {error && <p role="alert" className="rounded-lg border border-[var(--status-critical-border)] bg-[var(--status-critical-bg)] px-3 py-2 text-xs text-[var(--status-critical-fg)]">{error}</p>}

      <div className="grid gap-4 lg:grid-cols-[260px_1fr]">
        <ul className="bento-card h-fit divide-y divide-[var(--border-subtle)] p-0" aria-label="Roles">
          {roles.map(r => (
            <li key={r.key}>
              <button type="button" onClick={() => select(r.key)} aria-current={r.key === selected ? 'true' : undefined}
                className={`flex w-full items-center justify-between gap-2 px-3 py-2.5 text-left text-[12px] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary ${r.key === selected ? 'bg-primary/10' : 'hover:bg-muted'}`}>
                <span className="min-w-0">
                  <span className={`flex items-center gap-1.5 ${r.key === selected ? 'font-semibold text-primary' : 'font-medium text-foreground'}`}>
                    {r.name}{r.locked && <Lock className="h-3 w-3 text-muted-foreground" aria-label="Fixed" />}
                  </span>
                  <span className="block truncate text-[11px] text-muted-foreground">{r.key}</span>
                </span>
                <span className="shrink-0 text-[11px] tabular-nums text-muted-foreground">{r.user_count} user{r.user_count === 1 ? '' : 's'}</span>
              </button>
            </li>
          ))}
        </ul>

        {role && (
          <section className="bento-card p-0" aria-label={`${role.name} permissions`}>
            <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border px-4 py-3">
              <div className="min-w-0">
                <h2 className="flex items-center gap-2 text-[14px] font-semibold text-foreground">
                  {role.name}
                  {role.is_system && <StatusPill tone="neutral">Built-in</StatusPill>}
                </h2>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  {role.locked ? 'Super Admin always holds every permission, including any added later.' : role.description}
                </p>
              </div>
              {canEdit && !role.is_system && (
                <button type="button" className={btn.ghost} onClick={() => setDeleting(true)} disabled={role.user_count > 0}
                  title={role.user_count > 0 ? 'Move this role’s users to another role first' : 'Delete role'}>
                  <Trash2 className="h-3.5 w-3.5" /> Delete
                </button>
              )}
            </div>

            <div className="divide-y divide-[var(--border-subtle)]">
              {groups.map(({ g, items }) => (
                <fieldset key={g} className="px-4 py-3">
                  <legend className="float-left w-full text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">{g}</legend>
                  {GROUP_NOTE[g] && <p className="clear-both pt-0.5 text-[11px] text-muted-foreground">{GROUP_NOTE[g]}</p>}
                  <div className="clear-both grid gap-x-6 gap-y-2 pt-2 sm:grid-cols-2">
                    {items.map(p => {
                      const adminLocked = g === 'Administration' && !isSuper;
                      const coveredByAll = g === 'Portfolio access' && p.key !== 'portfolio.all' && draft.has('portfolio.all');
                      const disabled = readOnly || adminLocked || coveredByAll;
                      const checked = role.locked || draft.has(p.key) || coveredByAll;
                      return (
                        <label key={p.key} className={`flex items-start gap-2 text-[12px] ${disabled ? 'cursor-default' : 'cursor-pointer'}`}>
                          <input type="checkbox" className="mt-0.5 h-3.5 w-3.5 rounded border-border text-primary focus:ring-primary disabled:opacity-60"
                            checked={checked} disabled={disabled} onChange={() => toggle(p.key)} />
                          <span>
                            <span className={`font-medium ${disabled && !checked ? 'text-muted-foreground' : 'text-foreground'}`}>{p.label}</span>
                            <span className="block text-[11px] leading-snug text-muted-foreground">{p.description}</span>
                          </span>
                        </label>
                      );
                    })}
                  </div>
                </fieldset>
              ))}
            </div>

            {!readOnly && (
              <div className="flex items-center justify-end gap-2 border-t border-border px-4 py-3">
                {notice && <span role="status" className="mr-auto text-xs text-[var(--status-healthy-fg)]">{notice}</span>}
                <button type="button" className={btn.secondary} disabled={!dirty || busy} onClick={() => setDraft(new Set(role.permissions))}>Discard</button>
                <button type="button" className={btn.primary} disabled={!dirty || busy} onClick={save}>{busy ? 'Saving…' : 'Save permissions'}</button>
              </div>
            )}
          </section>
        )}
      </div>

      {creating && <NewRole onClose={() => setCreating(false)} onCreated={async key => { setCreating(false); await load(key); }} />}
      <Dialog open={deleting && !!role} onClose={() => setDeleting(false)} size="sm" title={`Delete ${role?.name}?`}
        description="The role is removed. This cannot be undone."
        footer={<>
          <button type="button" className={btn.secondary} onClick={() => setDeleting(false)}>Cancel</button>
          <button type="button" className={btn.danger} data-autofocus="" onClick={async () => {
            try { await adminApi.deleteRole(role!.key); setDeleting(false); await load(''); } catch (e) { setDeleting(false); setError((e as Error).message); }
          }}>Delete role</button>
        </>} />
    </div>
  );
}

function NewRole({ onClose, onCreated }: { onClose: () => void; onCreated: (key: string) => void }) {
  const [name, setName] = useState('');
  const [key, setKey] = useState('');
  const [keyTouched, setKeyTouched] = useState(false);
  const [description, setDescription] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const derived = name.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '').replace(/^(\d)/, 'r_$1').slice(0, 31);
  const finalKey = keyTouched ? key : derived;
  const valid = name.trim() && /^[a-z][a-z0-9_]{2,30}$/.test(finalKey);
  const create = async () => {
    setBusy(true);
    setError('');
    try {
      await adminApi.createRole({ key: finalKey, name: name.trim(), description: description.trim(), permissions: [] });
      onCreated(finalKey);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  };
  return (
    <Dialog open onClose={onClose} busy={busy} title="New role" description="Create it, then tick its permissions."
      footer={<>
        <button type="button" className={btn.secondary} onClick={onClose} disabled={busy}>Cancel</button>
        <button type="button" className={btn.primary} onClick={create} disabled={!valid || busy}>{busy ? 'Creating…' : 'Create role'}</button>
      </>}>
      <div className="grid gap-3">
        <label className="block text-xs font-medium text-foreground">Name
          <input className={`${field} mt-1`} value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Site Engineer – Wind" data-autofocus="" />
        </label>
        <label className="block text-xs font-medium text-foreground">Key <span className="font-normal text-muted-foreground">(permanent identifier)</span>
          <input className={`${field} mt-1 font-mono`} value={finalKey} onChange={e => { setKeyTouched(true); setKey(e.target.value.toLowerCase()); }} />
        </label>
        <label className="block text-xs font-medium text-foreground">Description
          <input className={`${field} mt-1`} value={description} onChange={e => setDescription(e.target.value)} />
        </label>
        {error && <p role="alert" className="text-xs text-[var(--status-critical-fg)]">{error}</p>}
      </div>
    </Dialog>
  );
}
