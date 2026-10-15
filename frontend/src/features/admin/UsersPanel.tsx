import { useCallback, useEffect, useMemo, useState } from 'react';
import { Copy, Check, Clock3, KeyRound, Lock, LockOpen, LogOut, Pencil, Plus, Search, UserX, UserCheck, Users as UsersIcon } from 'lucide-react';
import { Dialog, KPITile, PageHeader, StatusPill } from '../../components/ui/primitives';
import { useAuth } from '../../context/AuthContext';
import { adminApi, btn, field, fmtWhen } from './adminApi';
import type { AdminRole, AdminUser } from './adminApi';

/* User administration. Every rule (who may grant superadmin, last-superadmin,
   no self-demotion) is enforced by the server; this screen shows its answer. */

type Confirm = { kind: 'reset' | 'deactivate' | 'end'; user: AdminUser } | null;

export default function UsersPanel() {
  const { user: me } = useAuth();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [roles, setRoles] = useState<AdminRole[]>([]);
  const [clusters, setClusters] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [roleFilter, setRoleFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | 'active' | 'inactive' | 'locked'>('active');
  const [editing, setEditing] = useState<AdminUser | 'new' | null>(null);
  const [confirm, setConfirm] = useState<Confirm>(null);
  const [secret, setSecret] = useState<{ username: string; password: string; created: boolean } | null>(null);
  const [notice, setNotice] = useState('');

  const load = useCallback(async () => {
    setError('');
    try {
      const [u, r, c] = await Promise.all([adminApi.users(), adminApi.roles(), adminApi.portfolios()]);
      setUsers(u);
      setRoles(r);
      setClusters(c);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return users.filter(u =>
      (!q || [u.display_name, u.username, u.email].some(v => v.toLowerCase().includes(q))) &&
      (!roleFilter || u.role === roleFilter) &&
      (statusFilter === 'all' || (statusFilter === 'active' && u.is_active) ||
        (statusFilter === 'inactive' && !u.is_active) || (statusFilter === 'locked' && u.locked)));
  }, [users, query, roleFilter, statusFilter]);

  const counts = {
    active: users.filter(u => u.is_active).length,
    locked: users.filter(u => u.locked).length,
  };
  const isSuper = me?.role === 'superadmin';
  const weekAgo = Date.now() - 7 * 86_400_000;
  const recent = users.filter(u => u.last_login_at && new Date(u.last_login_at + 'Z').getTime() > weekAgo).length;
  const due = users.filter(u => u.is_active && u.must_change_password).length;
  const flash = (msg: string) => { setNotice(msg); window.setTimeout(() => setNotice(''), 4000); };

  return (
    <div className="space-y-4">
      <PageHeader title="Users"
        subtitle={`${counts.active} active${counts.locked ? ` · ${counts.locked} locked` : ''} · accounts are deactivated, never deleted, so the audit trail stays whole`}
        right={<button type="button" className={btn.primary} onClick={() => setEditing('new')}><Plus className="h-3.5 w-3.5" /> Add user</button>} />

      <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        <KPITile icon={UsersIcon} label="Active users" value={String(counts.active)} denominator={String(users.length)} loading={loading}
          onClick={() => setStatusFilter('active')} />
        <KPITile icon={Clock3} label="Signed in this week" value={String(recent)} loading={loading} />
        <KPITile icon={KeyRound} label="Password change due" value={String(due)} loading={loading}
          tone={due ? 'watch' : 'neutral'} subtext="Temporary password not yet replaced" />
        <KPITile icon={Lock} label="Locked" value={String(counts.locked)} loading={loading}
          tone={counts.locked ? 'critical' : 'neutral'} subtext="After 5 failed sign-ins" onClick={() => setStatusFilter('locked')} />
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-[220px] flex-1 sm:max-w-xs">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <input aria-label="Search users" value={query} onChange={e => setQuery(e.target.value)} placeholder="Search name, username, email"
            className={`${field} py-1.5 pl-8`} />
        </div>
        <select aria-label="Filter by role" value={roleFilter} onChange={e => setRoleFilter(e.target.value)} className={`${field.replace("w-full ", "")} w-auto py-1.5`}>
          <option value="">All roles</option>
          {roles.map(r => <option key={r.key} value={r.key}>{r.name}</option>)}
        </select>
        <select aria-label="Filter by status" value={statusFilter} onChange={e => setStatusFilter(e.target.value as typeof statusFilter)} className={`${field.replace("w-full ", "")} w-auto py-1.5`}>
          <option value="active">Active</option>
          <option value="locked">Locked</option>
          <option value="inactive">Deactivated</option>
          <option value="all">All</option>
        </select>
        {notice && <span role="status" className="text-xs text-[var(--status-healthy-fg)]">{notice}</span>}
      </div>

      {error && <p role="alert" className="rounded-lg border border-[var(--status-critical-border)] bg-[var(--status-critical-bg)] px-3 py-2 text-xs text-[var(--status-critical-fg)]">{error}</p>}

      <div className="bento-card overflow-x-auto p-0">
        <table className="w-full min-w-[760px] text-[12px]">
          <thead className="border-b border-border bg-[var(--neutral-100)] text-left text-[10px] uppercase tracking-wider text-muted-foreground">
            <tr className="[&>th]:px-3 [&>th]:py-2 [&>th]:font-semibold">
              <th>User</th><th>Role · portfolios</th><th>Status</th><th>Last sign-in</th><th className="text-right">Sessions</th><th className="text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading && <tr><td colSpan={6} className="px-3 py-6 text-center text-muted-foreground">Loading users…</td></tr>}
            {!loading && shown.length === 0 && <tr><td colSpan={6} className="px-3 py-6 text-center text-muted-foreground">No users match.</td></tr>}
            {shown.map(u => {
              const self = u.id === me?.id;
              const protectedRow = u.role === 'superadmin' && !isSuper;
              return (
                <tr key={u.id} className={`border-b border-[var(--border-subtle)] last:border-0 hover:bg-[var(--surface-sunken)] ${u.is_active ? '' : 'text-muted-foreground'}`}>
                  <td className="px-3 py-2">
                    <div className="font-medium text-foreground">{u.display_name}{self && <span className="ml-1.5 text-[10px] font-normal text-muted-foreground">(you)</span>}</div>
                    <div className="text-[11px] text-muted-foreground">{u.username}{u.email && ` · ${u.email}`}</div>
                  </td>
                  <td className="px-3 py-2">
                    <div>{u.role_name}</div>
                    <div className="text-[11px] text-muted-foreground">{u.portfolios.length ? u.portfolios.join(', ') : 'All portfolios'}</div>
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex flex-wrap gap-1">
                      {!u.is_active ? <StatusPill tone="neutral">Deactivated</StatusPill>
                        : u.locked ? <StatusPill tone="critical">Locked</StatusPill>
                        : <StatusPill tone="healthy">Active</StatusPill>}
                      {u.is_active && u.must_change_password && <StatusPill tone="watch">Password change due</StatusPill>}
                    </div>
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 tabular-nums">{u.last_login_at ? fmtWhen(u.last_login_at) : <span className="text-muted-foreground">Never</span>}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{u.active_sessions || <span className="text-muted-foreground">0</span>}</td>
                  <td className="px-3 py-2">
                    {protectedRow ? <span className="block text-right text-[11px] text-muted-foreground">Superadmin only</span> : (
                      <div className="flex justify-end gap-0.5">
                        <button type="button" className={btn.ghost} onClick={() => setEditing(u)} title="Edit"><Pencil className="h-3.5 w-3.5" /><span className="sr-only">Edit {u.username}</span></button>
                        {u.locked && <button type="button" className={btn.ghost} title="Unlock" onClick={async () => {
                          try { await adminApi.unlock(u.id); flash(`${u.username} unlocked`); load(); } catch (e) { setError((e as Error).message); }
                        }}><LockOpen className="h-3.5 w-3.5" /><span className="sr-only">Unlock {u.username}</span></button>}
                        {!self && u.is_active && <>
                          <button type="button" className={btn.ghost} title="Reset password" onClick={() => setConfirm({ kind: 'reset', user: u })}><KeyRound className="h-3.5 w-3.5" /><span className="sr-only">Reset password for {u.username}</span></button>
                          {u.active_sessions > 0 && <button type="button" className={btn.ghost} title="End sessions" onClick={() => setConfirm({ kind: 'end', user: u })}><LogOut className="h-3.5 w-3.5" /><span className="sr-only">End sessions for {u.username}</span></button>}
                          <button type="button" className={btn.ghost} title="Deactivate" onClick={() => setConfirm({ kind: 'deactivate', user: u })}><UserX className="h-3.5 w-3.5" /><span className="sr-only">Deactivate {u.username}</span></button>
                        </>}
                        {!self && !u.is_active && <button type="button" className={btn.ghost} title="Reactivate" onClick={async () => {
                          try { await adminApi.updateUser(u.id, { is_active: true }); flash(`${u.username} reactivated`); load(); } catch (e) { setError((e as Error).message); }
                        }}><UserCheck className="h-3.5 w-3.5" /><span className="sr-only">Reactivate {u.username}</span></button>}
                      </div>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {editing && (
        <UserForm user={editing === 'new' ? null : editing} roles={roles} clusters={clusters} isSuper={isSuper} selfId={me?.id}
          onClose={() => setEditing(null)}
          onSaved={(result) => {
            setEditing(null);
            if (result.temp) setSecret({ username: result.username, password: result.temp, created: true });
            else flash(`${result.username} saved`);
            load();
          }} />
      )}

      <ConfirmAction confirm={confirm} onClose={() => setConfirm(null)}
        onDone={(msg, temp) => {
          const u = confirm!.user;
          setConfirm(null);
          if (temp) setSecret({ username: u.username, password: temp, created: false });
          else flash(msg);
          load();
        }} />

      <Dialog open={!!secret} onClose={() => setSecret(null)} size="sm"
        title={secret?.created ? 'User created' : 'Password reset'}
        description="This temporary password is shown once. Give it to the user over a private channel; they must set their own at first sign-in."
        footer={<button type="button" className={btn.primary} onClick={() => setSecret(null)}>Done</button>}>
        {secret && <SecretBox username={secret.username} password={secret.password} />}
      </Dialog>
    </div>
  );
}

function SecretBox({ username, password }: { username: string; password: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="space-y-2">
      <div className="text-xs text-muted-foreground">Username</div>
      <div className="font-mono text-sm text-foreground">{username}</div>
      <div className="pt-1 text-xs text-muted-foreground">Temporary password</div>
      <div className="flex items-center gap-2">
        <code className="flex-1 rounded-lg border border-border bg-[var(--surface-sunken)] px-3 py-2 font-mono text-sm tracking-wide text-foreground">{password}</code>
        <button type="button" className={btn.secondary} onClick={async () => {
          try { await navigator.clipboard.writeText(password); setCopied(true); window.setTimeout(() => setCopied(false), 2000); } catch { /* select manually */ }
        }}>{copied ? <><Check className="h-3.5 w-3.5" /> Copied</> : <><Copy className="h-3.5 w-3.5" /> Copy</>}</button>
      </div>
    </div>
  );
}

function UserForm({ user, roles, clusters, isSuper, selfId, onClose, onSaved }: {
  user: AdminUser | null; roles: AdminRole[]; clusters: string[]; isSuper: boolean; selfId?: number;
  onClose: () => void; onSaved: (r: { username: string; temp: string | null }) => void;
}) {
  const [username, setUsername] = useState(user?.username ?? '');
  const [name, setName] = useState(user?.display_name ?? '');
  const [email, setEmail] = useState(user?.email ?? '');
  const [role, setRole] = useState(user?.role ?? roles.find(r => r.key !== 'superadmin')?.key ?? '');
  const [picked, setPicked] = useState<string[]>(user?.portfolios ?? []);
  const [allPortfolios, setAllPortfolios] = useState(!user || user.portfolios.length === 0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const self = user?.id === selfId;
  const portfoliosApply = role !== 'superadmin';
  const portfolios = allPortfolios || !portfoliosApply ? [] : picked;
  const assignable = roles.filter(r => isSuper || r.key !== 'superadmin');
  const chosen = roles.find(r => r.key === role);
  const usernameOk = /^[A-Za-z0-9._-]{3,40}$/.test(username);
  const valid = (user || usernameOk) && name.trim() && role && (!email || /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email))
    && (allPortfolios || !portfoliosApply || picked.length > 0);

  const save = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!valid) return;
    setBusy(true);
    setError('');
    try {
      if (user) {
        await adminApi.updateUser(user.id, { display_name: name, email, ...(self ? {} : { role, portfolios }) });
        onSaved({ username: user.username, temp: null });
      } else {
        const r = await adminApi.createUser({ username, display_name: name, email: email || undefined, role, portfolios });
        onSaved({ username, temp: r.temporary_password });
      }
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  };

  return (
    <Dialog open onClose={onClose} busy={busy} title={user ? `Edit ${user.username}` : 'Add user'}
      description={user ? 'Changing the role or portfolios signs the user out so their access reloads.' : 'A one-time temporary password is generated; the user sets their own at first sign-in.'}
      footer={<>
        <button type="button" className={btn.secondary} onClick={onClose} disabled={busy}>Cancel</button>
        <button type="button" className={btn.primary} onClick={() => save()} disabled={!valid || busy}>{busy ? 'Saving…' : user ? 'Save changes' : 'Create user'}</button>
      </>}>
      <form onSubmit={save} className="grid gap-3 sm:grid-cols-2" noValidate>
        <label className="block text-xs font-medium text-foreground">Username
          <input className={`${field} mt-1`} value={username} onChange={e => setUsername(e.target.value.trim())} disabled={!!user}
            autoComplete="off" data-autofocus={user ? undefined : ''} aria-invalid={!user && !!username && !usernameOk} />
          {!user && username && !usernameOk && <span className="mt-1 block text-[11px] text-[var(--status-critical-fg)]">3–40 letters, digits, dot, dash or underscore</span>}
        </label>
        <label className="block text-xs font-medium text-foreground">Full name
          <input className={`${field} mt-1`} value={name} onChange={e => setName(e.target.value)} data-autofocus={user ? '' : undefined} />
        </label>
        <label className="block text-xs font-medium text-foreground sm:col-span-2">Email <span className="font-normal text-muted-foreground">(optional, also accepted at sign-in)</span>
          <input type="email" className={`${field} mt-1`} value={email} onChange={e => setEmail(e.target.value.trim())} autoComplete="off" />
        </label>
        <label className="block text-xs font-medium text-foreground sm:col-span-2">Role
          <select className={`${field} mt-1`} value={role} onChange={e => setRole(e.target.value)} disabled={self}>
            {assignable.map(r => <option key={r.key} value={r.key}>{r.name}</option>)}
          </select>
          {self && <span className="mt-1 block text-[11px] text-muted-foreground">You cannot change your own role.</span>}
          {chosen && !self && <span className="mt-1 block text-[11px] font-normal leading-snug text-muted-foreground">{chosen.description}</span>}
        </label>
        {portfoliosApply && !self && (
          <fieldset className="sm:col-span-2">
            <legend className="text-xs font-medium text-foreground">Portfolio access</legend>
            <p className="mt-0.5 text-[11px] text-muted-foreground">Which projects this person sees on every dashboard. The server enforces it.</p>
            <div className="mt-2 flex flex-wrap gap-2" role="radiogroup" aria-label="Portfolio access">
              {[{ v: true, l: 'All portfolios' }, { v: false, l: 'Selected portfolios' }].map(o => (
                <label key={o.l} className={`cursor-pointer rounded-lg border px-3 py-1.5 text-[12px] transition-colors focus-within:ring-2 focus-within:ring-primary ${allPortfolios === o.v ? 'border-primary bg-primary/10 font-semibold text-primary' : 'border-border text-foreground hover:bg-muted'}`}>
                  <input type="radio" name="portfolio-mode" className="sr-only" checked={allPortfolios === o.v} onChange={() => setAllPortfolios(o.v)} />
                  {o.l}
                </label>
              ))}
            </div>
            {!allPortfolios && (
              <div className="mt-2 grid gap-1.5 sm:grid-cols-2">
                {clusters.map(c => (
                  <label key={c} className="flex cursor-pointer items-center gap-2 rounded-md border border-border px-2.5 py-1.5 text-[12px] text-foreground hover:bg-muted">
                    <input type="checkbox" className="h-3.5 w-3.5 rounded border-border text-primary focus:ring-primary"
                      checked={picked.includes(c)} onChange={() => setPicked(p => p.includes(c) ? p.filter(x => x !== c) : [...p, c])} />
                    {c}
                  </label>
                ))}
                {picked.length === 0 && <span className="text-[11px] text-[var(--status-critical-fg)] sm:col-span-2">Tick at least one portfolio.</span>}
              </div>
            )}
          </fieldset>
        )}
        {error && <p role="alert" className="text-xs text-[var(--status-critical-fg)] sm:col-span-2">{error}</p>}
        <button type="submit" className="hidden" />
      </form>
    </Dialog>
  );
}

const CONFIRM_TEXT = {
  reset: { title: 'Reset password?', body: 'A new temporary password is generated, every session of this user ends, and they must set their own password at next sign-in.', cta: 'Reset password', danger: false },
  end: { title: 'End all sessions?', body: 'The user is signed out on every device and must sign in again.', cta: 'End sessions', danger: false },
  deactivate: { title: 'Deactivate account?', body: 'The user can no longer sign in and every session ends. The account and its history are kept and can be reactivated.', cta: 'Deactivate', danger: true },
};

function ConfirmAction({ confirm, onClose, onDone }: {
  confirm: Confirm; onClose: () => void; onDone: (msg: string, temp?: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => { setError(''); setBusy(false); }, [confirm]);
  if (!confirm) return null;
  const t = CONFIRM_TEXT[confirm.kind];
  const u = confirm.user;
  const run = async () => {
    setBusy(true);
    setError('');
    try {
      if (confirm.kind === 'reset') { const r = await adminApi.resetPassword(u.id); onDone('', r.temporary_password); }
      else if (confirm.kind === 'end') { const r = await adminApi.endSessions(u.id); onDone(`${r.sessions_ended} session(s) ended for ${u.username}`); }
      else { await adminApi.updateUser(u.id, { is_active: false }); onDone(`${u.username} deactivated`); }
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  };
  return (
    <Dialog open onClose={onClose} busy={busy} size="sm" title={t.title}
      description={<><span className="font-medium text-foreground">{u.display_name}</span> ({u.username})</>}
      footer={<>
        <button type="button" className={btn.secondary} onClick={onClose} disabled={busy}>Cancel</button>
        <button type="button" className={t.danger ? btn.danger : btn.primary} onClick={run} disabled={busy} data-autofocus="">{busy ? 'Working…' : t.cta}</button>
      </>}>
      <p className="text-[13px] leading-relaxed text-muted-foreground">{t.body}</p>
      {error && <p role="alert" className="mt-2 text-xs text-[var(--status-critical-fg)]">{error}</p>}
    </Dialog>
  );
}
