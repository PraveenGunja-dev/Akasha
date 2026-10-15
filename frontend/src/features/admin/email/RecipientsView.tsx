/* Distribution groups: who receives each group's emails, at which level of
   intimation, and optionally only for some portfolios (a member with no
   portfolios covers all of them). People are picked from Akasha's users;
   an address outside Akasha can still be typed in. */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Pencil, Plus, Search, Trash2, X } from 'lucide-react';
import { Dialog, StatusPill, cx } from '../../../components/ui/primitives';
import { btn, field } from '../adminApi';
import { emailApi } from './emailApi';
import type { Catalogue, EmailTemplate, Recipient, UserOption } from './emailApi';

type Level = 1 | 2 | 3;
type Form = { id?: number; group_key: string; name: string; email: string; portfolios: string[]; level: Level; active: boolean };
const EMPTY: Form = { group_key: 'tc_ordering', name: '', email: '', portfolios: [], level: 1, active: true };

/* What each level means for delivery (engine.members): L1 hears every alert;
   L2 / L3 only once an alert has escalated that far (overdue orders: 7 / 14 days). */
const LEVELS: { value: Level; label: string; hint: string }[] = [
  { value: 1, label: 'L1 · First notice', hint: 'Every alert for the group, from the first email' },
  { value: 2, label: 'L2 · Escalation', hint: 'Only once an alert escalates - an order 7 days overdue' },
  { value: 3, label: 'L3 · Senior escalation', hint: 'Only at the top step - an order 14 days overdue' },
];

/* What each group is for - who should be in it. */
const GROUP_PURPOSE: Record<string, string> = {
  tc_ordering: 'Places module orders and raises approval requests',
  tc_head: 'Approves module orders',
  projects: 'Site execution - schedule changes, delays, stock',
  pmag: 'Governance - delays and escalations',
  executive: 'Leadership - senior escalations',
  tc_stores: 'Receipts, GRN and site stock',
  finance: 'Finance checklists for payment release',
  admin: 'Data feeds - sync failures',
};

export default function RecipientsView() {
  const [rows, setRows] = useState<Recipient[]>([]);
  const [cat, setCat] = useState<Catalogue | null>(null);
  const [users, setUsers] = useState<UserOption[]>([]);
  const [templates, setTemplates] = useState<EmailTemplate[]>([]);
  const [form, setForm] = useState<Form | null>(null);
  const [remove, setRemove] = useState<Recipient | null>(null);
  const [level, setLevel] = useState<0 | Level>(0);
  const [query, setQuery] = useState('');
  const [searchOpen, setSearchOpen] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);
  useEffect(() => { if (searchOpen) searchRef.current?.focus(); }, [searchOpen]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => { emailApi.recipients().then(setRows).catch(e => setError((e as Error).message)); }, []);
  useEffect(() => {
    load();
    emailApi.catalogue().then(setCat).catch(() => undefined);
    emailApi.users().then(setUsers).catch(() => undefined);
    emailApi.templates().then(setTemplates).catch(() => undefined);
  }, [load]);

  const save = async () => {
    if (!form) return;
    setBusy(true); setError('');
    try {
      const body = { group_key: form.group_key, name: form.name, email: form.email, portfolios: form.portfolios, level: form.level, active: form.active };
      if (form.id) await emailApi.updateRecipient(form.id, body); else await emailApi.addRecipient(body);
      setForm(null); load();
    } catch (e) {
      setError((e as Error).message);
    } finally { setBusy(false); }
  };

  const groups = cat?.groups ?? [];
  const q = query.trim().toLowerCase();
  const shown = rows.filter(r => (!level || r.level === level) && (!q || `${r.name} ${r.email}`.toLowerCase().includes(q)));
  const count = (l: 0 | Level) => rows.filter(r => !l || r.level === l).length;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-[640px] text-[12.5px] text-muted-foreground">
          Templates address groups, never people, so a change of person is made once here. The level decides when someone is told:
          L1 at the first notice, L2 and L3 only when an alert escalates.
        </p>
        <div className="flex items-center gap-2">
          {searchOpen ? (
            <div className="relative w-56">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden />
              <input ref={searchRef} aria-label="Search recipients" className={`${field} py-1.5 pl-8 pr-7 text-[12px]`} value={query}
                onChange={e => setQuery(e.target.value)} placeholder="Name or email"
                onKeyDown={e => { if (e.key === 'Escape') { setQuery(''); setSearchOpen(false); } }}
                onBlur={() => { if (!query.trim()) setSearchOpen(false); }} />
              {query && (
                <button type="button" aria-label="Clear search" onMouseDown={e => e.preventDefault()} onClick={() => setQuery('')}
                  className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded p-0.5 text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40">
                  <X className="h-3.5 w-3.5" /></button>
              )}
            </div>
          ) : (
            <button type="button" className={`${btn.secondary} px-2`} aria-label="Search recipients" title="Search recipients"
              onClick={() => setSearchOpen(true)}><Search className="h-3.5 w-3.5" /></button>
          )}
          <select aria-label="Filter by level of intimation" className={`${field.replace('w-full ', '')} w-auto py-1.5 text-[12px]`}
            value={level} onChange={e => setLevel(Number(e.target.value) as 0 | Level)}>
            <option value={0}>All levels ({count(0)})</option>
            {LEVELS.map(l => <option key={l.value} value={l.value}>L{l.value} ({count(l.value)})</option>)}
          </select>
          <button type="button" className={btn.primary} onClick={() => { setError(''); setForm({ ...EMPTY }); }}><Plus className="h-3.5 w-3.5" />Add recipient</button>
        </div>
      </div>
      {error && !form && <p role="alert" className="rounded-lg border border-[var(--status-critical-border)] bg-[var(--status-critical-bg)] px-3 py-2 text-xs text-[var(--status-critical-fg)]">{error}</p>}

      <div className="grid gap-3 lg:grid-cols-2">
        {groups.map(g => {
          const members = shown.filter(r => r.group_key === g.key).sort((a, b) => a.level - b.level || a.email.localeCompare(b.email));
          const all = rows.filter(r => r.group_key === g.key);
          if ((level || q) && members.length === 0) return null;
          const receives = templates.filter(t => t.to_groups.includes(g.key) || t.cc_groups.includes(g.key));
          const live = receives.filter(t => t.enabled);
          const active = all.filter(m => m.active).length;
          return (
            <section key={g.key} className="bento-card flex flex-col p-0" aria-labelledby={`grp-${g.key}`}>
              <header className="flex items-start justify-between gap-3 px-4 pb-2.5 pt-3">
                <div className="min-w-0">
                  <h3 id={`grp-${g.key}`} className="text-[13.5px] font-semibold text-foreground">{g.label}</h3>
                  <p className="text-[11.5px] text-muted-foreground">{GROUP_PURPOSE[g.key] ?? ''}</p>
                </div>
                <div className="flex shrink-0 items-center gap-1.5">
                  <span className={cx('rounded-full px-2 py-0.5 text-[11px] font-semibold tabular-nums',
                    active ? 'bg-muted text-foreground' : 'bg-[var(--status-watch-bg)] text-[var(--status-watch-fg)]')}>
                    {active} {active === 1 ? 'person' : 'people'}
                  </span>
                  <button type="button" className={`${btn.ghost} px-1.5`} aria-label={`Add someone to ${g.label}`} title={`Add someone to ${g.label}`}
                    onClick={() => { setError(''); setForm({ ...EMPTY, group_key: g.key }); }}><Plus className="h-4 w-4" /></button>
                </div>
              </header>

              <div className="border-y border-[var(--border-subtle)] bg-[var(--surface-sunken)] px-4 py-2 text-[11.5px]">
                {receives.length === 0 ? <span className="text-muted-foreground">No template sends to this group.</span> : (
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="mr-0.5 text-muted-foreground">Receives</span>
                    {receives.map(t => (
                      <span key={t.key} title={`${t.name} - ${t.to_groups.includes(g.key) ? 'To' : 'Cc'}${t.enabled ? '' : ' (template off)'}`}
                        className={cx('inline-flex items-center gap-1 rounded border px-1.5 py-px',
                          t.enabled ? 'border-border bg-card text-foreground' : 'border-dashed border-border text-muted-foreground')}>
                        {t.name.replace(/^Module ordering - /, '')}
                        <span className="text-[10px] font-semibold text-muted-foreground">{t.to_groups.includes(g.key) ? 'To' : 'Cc'}</span>
                      </span>
                    ))}
                  </div>
                )}
              </div>

              {members.length === 0 ? (
                <div className="flex flex-1 items-center justify-between gap-3 px-4 py-3">
                  <p className={cx('text-[12px]', live.length ? 'text-[var(--status-watch-fg)]' : 'text-muted-foreground')}>
                    {live.length ? `No one yet - ${live.length} switched-on email${live.length === 1 ? '' : 's'} to this group ${live.length === 1 ? 'is' : 'are'} held back.` : 'No one yet.'}
                  </p>
                  <button type="button" className={btn.secondary} onClick={() => { setError(''); setForm({ ...EMPTY, group_key: g.key }); }}>
                    <Plus className="h-3.5 w-3.5" />Add person</button>
                </div>
              ) : (
                <ul className="flex-1">
                  {members.map(m => (
                    <li key={m.id} className="group flex items-center justify-between gap-3 border-b border-[var(--border-subtle)] px-4 py-2 last:border-0 hover:bg-[var(--surface-sunken)]">
                      <div className="flex min-w-0 items-center gap-2.5">
                        <Initials name={m.name || m.email} />
                        <div className="min-w-0 leading-tight">
                          <div className="flex items-center gap-1.5">
                            <span className="truncate text-[12.5px] font-medium text-foreground">{m.name || m.email}</span>
                            <span title={LEVELS[m.level - 1]?.hint}
                              className={cx('shrink-0 rounded px-1 py-px text-[10px] font-bold tabular-nums',
                                m.level === 1 ? 'bg-muted text-foreground' : 'bg-primary/10 text-primary')}>L{m.level}</span>
                            {!m.active && <StatusPill tone="neutral">Paused</StatusPill>}
                          </div>
                          <div className="truncate text-[11.5px] text-muted-foreground">
                            {m.name && <>{m.email} · </>}{m.portfolios.length ? m.portfolios.join(', ') : 'All portfolios'}
                          </div>
                          {!m.akasha_user && (
                            <div className="text-[11px] text-[var(--status-watch-fg)]" title="Acknowledging and approving need an Akasha sign-in with this email. An administrator can record it for them from the alert.">
                              Not an Akasha user - cannot acknowledge in Akasha
                            </div>
                          )}
                        </div>
                      </div>
                      <div className="flex shrink-0 items-center gap-0.5 opacity-70 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
                        <button type="button" className={btn.ghost} aria-label={`Edit ${m.email}`}
                          onClick={() => { setError(''); setForm({ id: m.id, group_key: m.group_key, name: m.name, email: m.email, portfolios: m.portfolios, level: m.level, active: m.active }); }}>
                          <Pencil className="h-3.5 w-3.5" /></button>
                        <button type="button" className={btn.ghost} aria-label={`Remove ${m.email}`} onClick={() => setRemove(m)}><Trash2 className="h-3.5 w-3.5" /></button>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          );
        })}
      </div>
      {(level !== 0 || q) && shown.length === 0 && <p className="text-center text-[12.5px] text-muted-foreground">No recipients match.</p>}

      <Dialog open={!!form} onClose={() => setForm(null)} busy={busy} title={form?.id ? 'Edit recipient' : 'Add recipient'}
        footer={<><button type="button" className={btn.secondary} onClick={() => setForm(null)}>Cancel</button>
          <button type="button" className={btn.primary} disabled={busy || !form?.email} onClick={save}>{busy ? 'Saving…' : 'Save'}</button></>}>
        {form && (
          <div className="space-y-4">
            {error && <p role="alert" className="rounded-md bg-[var(--status-critical-bg)] px-3 py-2 text-xs text-[var(--status-critical-fg)]">{error}</p>}
            <PersonPicker users={users} name={form.name} email={form.email}
              onPick={u => setForm({ ...form, name: u.name, email: u.email, portfolios: form.portfolios.length ? form.portfolios : u.portfolios })}
              onManual={(name, email) => setForm({ ...form, name, email })} />
            <label className="block text-[12px] font-medium text-foreground">Group
              <select className={`${field} mt-1`} value={form.group_key} onChange={e => setForm({ ...form, group_key: e.target.value })}>
                {groups.map(g => <option key={g.key} value={g.key}>{g.label}</option>)}
              </select>
            </label>
            <fieldset>
              <legend className="text-[12px] font-medium text-foreground">Level of intimation</legend>
              <div className="mt-1 grid gap-1.5 sm:grid-cols-3">
                {LEVELS.map(l => (
                  <label key={l.value} className={cx('cursor-pointer rounded-lg border px-2.5 py-2 transition-colors',
                    form.level === l.value ? 'border-primary bg-primary/5' : 'border-border hover:bg-muted/60')}>
                    <input type="radio" name="level" className="sr-only" checked={form.level === l.value} onChange={() => setForm({ ...form, level: l.value })} />
                    <span className="block text-[12px] font-semibold text-foreground">{l.label}</span>
                    <span className="block text-[11px] leading-snug text-muted-foreground">{l.hint}</span>
                  </label>
                ))}
              </div>
            </fieldset>
            <fieldset>
              <legend className="text-[12px] font-medium text-foreground">Portfolios <span className="font-normal text-muted-foreground">(none ticked = all)</span></legend>
              <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1.5">
                {(cat?.portfolios ?? []).map(p => (
                  <label key={p} className="inline-flex items-center gap-1.5 text-[12.5px]">
                    <input type="checkbox" checked={form.portfolios.includes(p)}
                      onChange={e => setForm({ ...form, portfolios: e.target.checked ? [...form.portfolios, p] : form.portfolios.filter(x => x !== p) })} />{p}
                  </label>
                ))}
              </div>
            </fieldset>
            <label className="inline-flex items-center gap-2 text-[12.5px]"><input type="checkbox" checked={form.active} onChange={e => setForm({ ...form, active: e.target.checked })} />Active (untick to pause without removing)</label>
          </div>
        )}
      </Dialog>
      <Dialog open={!!remove} onClose={() => setRemove(null)} title="Remove recipient?"
        description={remove ? `${remove.email} stops receiving ${groups.find(g => g.key === remove.group_key)?.label ?? remove.group_key} emails.` : ''}
        footer={<><button type="button" className={btn.secondary} onClick={() => setRemove(null)}>Cancel</button>
          <button type="button" className={btn.danger} onClick={() => remove && emailApi.removeRecipient(remove.id).then(() => { setRemove(null); load(); }).catch(e => setError((e as Error).message))}>Remove</button></>} />
    </div>
  );
}

/* Pick an Akasha user: a search field whose list opens on focus or typing
   (name, username, email, role, department), keyboard-navigable; or switch
   to typing a name and address for someone outside Akasha. */
function PersonPicker({ users, name, email, onPick, onManual }: {
  users: UserOption[]; name: string; email: string; onPick: (u: UserOption) => void; onManual: (name: string, email: string) => void;
}) {
  const known = users.find(u => u.email.toLowerCase() === email.toLowerCase());
  const [manual, setManual] = useState(!!email && !known);
  const [q, setQ] = useState('');
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const listRef = useRef<HTMLUListElement>(null);
  // Nothing until something is typed; then the best few - a name that
  // starts with the text first - so a long user list never fills the dialog.
  const SHOWN = 8;
  const { matches, total } = useMemo(() => {
    const s = q.trim().toLowerCase();
    if (!s) return { matches: [] as UserOption[], total: 0 };
    const rank = (u: UserOption) => (u.name.toLowerCase().startsWith(s) ? 0 : u.email.toLowerCase().startsWith(s) ? 1
      : u.name.toLowerCase().includes(` ${s}`) ? 2 : 3);
    const hits = users.filter(u => `${u.name} ${u.username} ${u.email} ${u.role} ${u.department}`.toLowerCase().includes(s))
      .sort((a, b) => rank(a) - rank(b) || a.name.localeCompare(b.name));
    return { matches: hits.slice(0, SHOWN), total: hits.length };
  }, [users, q]);
  useEffect(() => { setActive(0); }, [q]);
  useEffect(() => {
    listRef.current?.querySelector<HTMLElement>(`[data-index="${active}"]`)?.scrollIntoView({ block: 'nearest' });
  }, [active]);

  const choose = (u: UserOption) => { onPick(u); setQ(''); setOpen(false); };
  const looksLikeEmail = /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(q.trim());

  if (manual) {
    return (
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-[12px] font-medium text-foreground">Person outside Akasha</span>
          {users.length > 0 && <button type="button" className={btn.ghost} onClick={() => { setManual(false); onManual('', ''); }}>Pick an Akasha user instead</button>}
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block text-[12px] font-medium text-foreground">Name
            <input className={`${field} mt-1`} value={name} maxLength={120} data-autofocus onChange={e => onManual(e.target.value, email)} />
          </label>
          <label className="block text-[12px] font-medium text-foreground">Email
            <input className={`${field} mt-1`} type="email" value={email} placeholder="name@adani.com" onChange={e => onManual(name, e.target.value)} />
          </label>
        </div>
      </div>
    );
  }

  if (email) {
    return (
      <div>
        <span className="text-[12px] font-medium text-foreground">Person</span>
        <div className="mt-1 flex items-center justify-between gap-2 rounded-lg border border-border bg-[var(--surface-sunken)] px-3 py-2">
          <div className="flex min-w-0 items-center gap-2.5">
            <Initials name={name || email} />
            <div className="min-w-0 leading-tight">
              <div className="truncate text-[12.5px] font-medium text-foreground">{name || email}</div>
              <div className="truncate text-[11.5px] text-muted-foreground">{email}{known ? ` · ${known.role}` : ''}</div>
            </div>
          </div>
          <button type="button" className={btn.ghost} onClick={() => onManual('', '')}>Change</button>
        </div>
      </div>
    );
  }

  return (
    <div className="relative">
      <label className="block text-[12px] font-medium text-foreground" htmlFor="person-search">Person</label>
      <div className="relative mt-1">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden />
        <input id="person-search" data-autofocus role="combobox" aria-expanded={open} aria-controls="person-list" aria-autocomplete="list"
          aria-activedescendant={open && matches[active] ? `person-${matches[active].id}` : undefined}
          className={`${field} pl-8`} value={q} autoComplete="off"
          placeholder={users.length ? 'Search by name, email, role or department' : 'No Akasha users with an email yet'}
          onFocus={() => setOpen(true)} onBlur={() => setOpen(false)}
          onChange={e => { setQ(e.target.value); setOpen(true); }}
          onKeyDown={e => {
            if (e.key === 'ArrowDown') { e.preventDefault(); setOpen(true); setActive(a => Math.min(a + 1, matches.length - 1)); }
            else if (e.key === 'ArrowUp') { e.preventDefault(); setActive(a => Math.max(a - 1, 0)); }
            else if (e.key === 'Enter' && open && matches[active]) { e.preventDefault(); choose(matches[active]); }
            else if (e.key === 'Escape' && open) { e.stopPropagation(); setOpen(false); }   // close the list, not the dialog
          }} />
      </div>
      {open && (
        <div className="absolute left-0 right-0 z-20 mt-1 overflow-hidden rounded-lg border border-border bg-card shadow-lg"
          onMouseDown={e => e.preventDefault()}>
          <ul id="person-list" ref={listRef} role="listbox" aria-label="Akasha users" className="max-h-[240px] overflow-auto py-1">
            {matches.map((u, i) => (
              <li key={u.id} id={`person-${u.id}`} role="option" aria-selected={i === active} data-index={i}
                onMouseEnter={() => setActive(i)} onClick={() => choose(u)}
                className={cx('flex cursor-pointer items-center gap-2.5 px-3 py-1.5', i === active ? 'bg-muted' : '')}>
                <Initials name={u.name} />
                <div className="min-w-0 flex-1 leading-tight">
                  <div className="truncate text-[12.5px] font-medium text-foreground"><Mark text={u.name} q={q} /></div>
                  <div className="truncate text-[11.5px] text-muted-foreground"><Mark text={u.email} q={q} /></div>
                </div>
                <span className="shrink-0 text-right text-[11px] leading-tight text-muted-foreground">
                  {u.role}{u.department && <span className="block">{u.department}</span>}
                </span>
              </li>
            ))}
            {matches.length === 0 && (
              <li className="px-3 py-2 text-[12px] text-muted-foreground">
                {!users.length ? 'No Akasha users with an email yet.'
                  : !q.trim() ? `Type a name, email, role or department to find one of ${users.length} Akasha users.`
                    : `No Akasha user matches \u201c${q.trim()}\u201d.`}
              </li>
            )}
            {total > matches.length && (
              <li className="px-3 py-1.5 text-[11px] text-muted-foreground">Showing {matches.length} of {total} - keep typing to narrow it down.</li>
            )}
          </ul>
          <button type="button" className="flex w-full items-center gap-1.5 border-t border-border px-3 py-2 text-left text-[12px] font-medium text-primary hover:bg-muted focus-visible:bg-muted focus-visible:outline-none"
            onClick={() => { setManual(true); setOpen(false); onManual('', looksLikeEmail ? q.trim() : ''); }}>
            <Plus className="h-3.5 w-3.5" />{looksLikeEmail ? `Add ${q.trim()} (not in Akasha)` : 'Someone not in Akasha? Enter an email'}
          </button>
        </div>
      )}
    </div>
  );
}

function Initials({ name }: { name: string }) {
  const parts = name.replace(/@.*/, '').split(/[\s._-]+/).filter(Boolean);
  const text = ((parts[0]?.[0] ?? '') + (parts[1]?.[0] ?? '')).toUpperCase() || '?';
  return (
    <span aria-hidden className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/10 text-[11px] font-semibold text-primary">{text}</span>
  );
}

/** The matching part of a result, in bold. */
function Mark({ text, q }: { text: string; q: string }) {
  const s = q.trim();
  const i = s ? text.toLowerCase().indexOf(s.toLowerCase()) : -1;
  if (i < 0) return <>{text}</>;
  return <>{text.slice(0, i)}<b className="font-semibold text-foreground">{text.slice(i, i + s.length)}</b>{text.slice(i + s.length)}</>;
}
