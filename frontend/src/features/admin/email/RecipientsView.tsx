/* Distribution groups: who receives each group's emails, optionally only for
   some portfolios (a member with no portfolios covers all of them). */
import { useCallback, useEffect, useState } from 'react';
import { Pencil, Plus, Trash2 } from 'lucide-react';
import { Dialog, StatusPill } from '../../../components/ui/primitives';
import { btn, field } from '../adminApi';
import { emailApi } from './emailApi';
import type { Catalogue, Recipient } from './emailApi';

type Form = { id?: number; group_key: string; name: string; email: string; portfolios: string[]; active: boolean };
const EMPTY: Form = { group_key: 'tc_ordering', name: '', email: '', portfolios: [], active: true };

export default function RecipientsView() {
  const [rows, setRows] = useState<Recipient[]>([]);
  const [cat, setCat] = useState<Catalogue | null>(null);
  const [form, setForm] = useState<Form | null>(null);
  const [remove, setRemove] = useState<Recipient | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => { emailApi.recipients().then(setRows).catch(e => setError((e as Error).message)); }, []);
  useEffect(() => { load(); emailApi.catalogue().then(setCat).catch(() => undefined); }, [load]);

  const save = async () => {
    if (!form) return;
    setBusy(true); setError('');
    try {
      const body = { group_key: form.group_key, name: form.name, email: form.email, portfolios: form.portfolios, active: form.active };
      if (form.id) await emailApi.updateRecipient(form.id, body); else await emailApi.addRecipient(body);
      setForm(null); load();
    } catch (e) {
      setError((e as Error).message);
    } finally { setBusy(false); }
  };

  const groups = cat?.groups ?? [];
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="max-w-[720px] text-[12.5px] text-muted-foreground">
          Templates address groups, never people, so a change of person is made once here. Limit someone to their portfolios
          and they only receive emails about those projects.
        </p>
        <button type="button" className={btn.primary} onClick={() => { setError(''); setForm({ ...EMPTY }); }}><Plus className="h-3.5 w-3.5" />Add recipient</button>
      </div>
      {error && !form && <p role="alert" className="rounded-lg border border-[var(--status-critical-border)] bg-[var(--status-critical-bg)] px-3 py-2 text-xs text-[var(--status-critical-fg)]">{error}</p>}

      <div className="grid gap-3 lg:grid-cols-2">
        {groups.map(g => {
          const members = rows.filter(r => r.group_key === g.key);
          return (
            <section key={g.key} className="bento-card p-0">
              <header className="flex items-center justify-between border-b border-border px-4 py-2.5">
                <h3 className="text-[13px] font-semibold text-foreground">{g.label}</h3>
                <span className="text-[11.5px] text-muted-foreground">{members.filter(m => m.active).length} active</span>
              </header>
              {members.length === 0 ? (
                <p className="px-4 py-3 text-[12px] text-muted-foreground">No one yet - emails to this group are held back and logged as “No recipients”.</p>
              ) : (
                <ul>
                  {members.map(m => (
                    <li key={m.id} className="flex items-start justify-between gap-3 border-b border-[var(--border-subtle)] px-4 py-2 last:border-0">
                      <div className="min-w-0 text-[12.5px]">
                        <span className="font-medium text-foreground">{m.name || m.email}</span>
                        {m.name && <span className="ml-1.5 text-muted-foreground">{m.email}</span>}
                        <span className="block text-[11px] text-muted-foreground">{m.portfolios.length ? m.portfolios.join(', ') : 'All portfolios'}</span>
                      </div>
                      <div className="flex shrink-0 items-center gap-1">
                        {!m.active && <StatusPill tone="neutral">Paused</StatusPill>}
                        <button type="button" className={btn.ghost} aria-label={`Edit ${m.email}`}
                          onClick={() => { setError(''); setForm({ id: m.id, group_key: m.group_key, name: m.name, email: m.email, portfolios: m.portfolios, active: m.active }); }}>
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

      <Dialog open={!!form} onClose={() => setForm(null)} busy={busy} title={form?.id ? 'Edit recipient' : 'Add recipient'}
        footer={<><button type="button" className={btn.secondary} onClick={() => setForm(null)}>Cancel</button>
          <button type="button" className={btn.primary} disabled={busy || !form?.email} onClick={save}>{busy ? 'Saving…' : 'Save'}</button></>}>
        {form && (
          <div className="space-y-3">
            {error && <p role="alert" className="rounded-md bg-[var(--status-critical-bg)] px-3 py-2 text-xs text-[var(--status-critical-fg)]">{error}</p>}
            <label className="block text-[12px] font-medium text-foreground">Group
              <select className={`${field} mt-1`} value={form.group_key} onChange={e => setForm({ ...form, group_key: e.target.value })}>
                {groups.map(g => <option key={g.key} value={g.key}>{g.label}</option>)}
              </select>
            </label>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="block text-[12px] font-medium text-foreground">Name
                <input className={`${field} mt-1`} value={form.name} maxLength={120} onChange={e => setForm({ ...form, name: e.target.value })} />
              </label>
              <label className="block text-[12px] font-medium text-foreground">Email
                <input className={`${field} mt-1`} type="email" value={form.email} placeholder="name@adani.com" onChange={e => setForm({ ...form, email: e.target.value })} />
              </label>
            </div>
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
