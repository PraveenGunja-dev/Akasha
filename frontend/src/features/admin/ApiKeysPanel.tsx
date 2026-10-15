import { useCallback, useEffect, useState } from 'react';
import { Copy, Check, KeyRound, Plus } from 'lucide-react';
import { Dialog, PageHeader, StatusPill } from '../../components/ui/primitives';
import { adminApi, apiKeysApi, btn, field, fmtWhen } from './adminApi';
import type { ApiKeyRow } from './adminApi';

/* Keys for systems (not people) that read the integration API, /api/v1.
   Read-only, optionally limited to portfolios, revocable. The key is shown
   once at creation; only its hash is stored, so it cannot be shown again. */

export default function ApiKeysPanel() {
  const [keys, setKeys] = useState<ApiKeyRow[]>([]);
  const [clusters, setClusters] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [creating, setCreating] = useState(false);
  const [revoking, setRevoking] = useState<ApiKeyRow | null>(null);
  const [secret, setSecret] = useState<{ name: string; key: string } | null>(null);

  const load = useCallback(async () => {
    try {
      const [k, c] = await Promise.all([apiKeysApi.list(), adminApi.portfolios()]);
      setKeys(k);
      setClusters(c);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-4">
      <PageHeader title="API keys"
        subtitle="For systems that read the integration API (/api/v1). Read-only; send as the X-API-Key header. A key is shown once."
        right={<button type="button" className={btn.primary} onClick={() => setCreating(true)}><Plus className="h-3.5 w-3.5" /> New key</button>} />
      {error && <p role="alert" className="rounded-lg border border-[var(--status-critical-border)] bg-[var(--status-critical-bg)] px-3 py-2 text-xs text-[var(--status-critical-fg)]">{error}</p>}

      <div className="bento-card overflow-x-auto p-0">
        <table className="w-full min-w-[760px] text-[12px]">
          <thead className="border-b border-border bg-[var(--neutral-100)] text-left text-[10px] uppercase tracking-wider text-muted-foreground">
            <tr className="[&>th]:px-3 [&>th]:py-2 [&>th]:font-semibold">
              <th>Used by</th><th>Key</th><th>Portfolios</th><th>Status</th><th>Last used</th><th>Expires</th><th className="text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading && <tr><td colSpan={7} className="px-3 py-6 text-center text-muted-foreground">Loading keys…</td></tr>}
            {!loading && keys.length === 0 && <tr><td colSpan={7} className="px-3 py-6 text-center text-muted-foreground">No keys yet. Create one for each system that reads the API.</td></tr>}
            {keys.map(k => (
              <tr key={k.id} className={`border-b border-[var(--border-subtle)] last:border-0 ${k.state === 'active' ? '' : 'text-muted-foreground'}`}>
                <td className="px-3 py-2 font-medium text-foreground">{k.name}</td>
                <td className="px-3 py-2 font-mono text-[11px]">{k.prefix}…</td>
                <td className="px-3 py-2">{k.portfolios.length ? k.portfolios.join(', ') : 'All portfolios'}</td>
                <td className="px-3 py-2"><StatusPill tone={k.state === 'active' ? 'healthy' : k.state === 'expired' ? 'watch' : 'neutral'}>{k.state[0].toUpperCase() + k.state.slice(1)}</StatusPill></td>
                <td className="whitespace-nowrap px-3 py-2 tabular-nums">{k.last_used_at ? `${fmtWhen(k.last_used_at)} · ${k.use_count}×` : 'Never'}</td>
                <td className="whitespace-nowrap px-3 py-2 tabular-nums">{k.expires_at ? fmtWhen(k.expires_at) : 'No expiry'}</td>
                <td className="px-3 py-2 text-right">
                  {k.state === 'active' && <button type="button" className={btn.ghost} onClick={() => setRevoking(k)}>Revoke</button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {creating && <NewKey clusters={clusters} onClose={() => setCreating(false)}
        onCreated={(name, key) => { setCreating(false); setSecret({ name, key }); load(); }} />}

      <Dialog open={!!revoking} onClose={() => setRevoking(null)} size="sm" title="Revoke key?"
        description={revoking ? `${revoking.name} (${revoking.prefix}…)` : undefined}
        footer={<>
          <button type="button" className={btn.secondary} onClick={() => setRevoking(null)}>Cancel</button>
          <button type="button" className={btn.danger} data-autofocus="" onClick={async () => {
            try { await apiKeysApi.revoke(revoking!.id); setRevoking(null); load(); } catch (e) { setRevoking(null); setError((e as Error).message); }
          }}>Revoke key</button>
        </>}>
        <p className="text-[13px] text-muted-foreground">The system using it is refused from its next call. This cannot be undone; issue a new key to restore access.</p>
      </Dialog>

      <Dialog open={!!secret} onClose={() => setSecret(null)} size="md" title="Key created"
        description="Copy it now and hand it to the system owner over a private channel. It will not be shown again."
        footer={<button type="button" className={btn.primary} onClick={() => setSecret(null)}>Done</button>}>
        {secret && <KeyBox name={secret.name} value={secret.key} />}
      </Dialog>
    </div>
  );
}

function KeyBox({ name, value }: { name: string; value: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="space-y-2">
      <div className="text-xs text-muted-foreground">{name}</div>
      <div className="flex items-center gap-2">
        <code className="flex-1 break-all rounded-lg border border-border bg-[var(--surface-sunken)] px-3 py-2 font-mono text-[12px] text-foreground">{value}</code>
        <button type="button" className={btn.secondary} onClick={async () => {
          try { await navigator.clipboard.writeText(value); setCopied(true); window.setTimeout(() => setCopied(false), 2000); } catch { /* select manually */ }
        }}>{copied ? <><Check className="h-3.5 w-3.5" /> Copied</> : <><Copy className="h-3.5 w-3.5" /> Copy</>}</button>
      </div>
      <p className="text-[11px] text-muted-foreground">Use: <code className="font-mono">curl -H "X-API-Key: {value.slice(0, 10)}…" https://&lt;host&gt;/akasha/api/v1/projects</code></p>
    </div>
  );
}

function NewKey({ clusters, onClose, onCreated }: {
  clusters: string[]; onClose: () => void; onCreated: (name: string, key: string) => void;
}) {
  const [name, setName] = useState('');
  const [all, setAll] = useState(true);
  const [picked, setPicked] = useState<string[]>([]);
  const [days, setDays] = useState('365');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const valid = name.trim() && (all || picked.length > 0);
  const create = async () => {
    setBusy(true);
    setError('');
    try {
      const r = await apiKeysApi.create({ name: name.trim(), portfolios: all ? [] : picked, expires_in_days: days ? Number(days) : null });
      onCreated(name.trim(), r.key);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  };
  return (
    <Dialog open onClose={onClose} busy={busy} title="New API key" description="Read-only access to /api/v1, limited to the portfolios chosen."
      footer={<>
        <button type="button" className={btn.secondary} onClick={onClose} disabled={busy}>Cancel</button>
        <button type="button" className={btn.primary} onClick={create} disabled={!valid || busy}><KeyRound className="h-3.5 w-3.5" /> {busy ? 'Creating…' : 'Create key'}</button>
      </>}>
      <div className="grid gap-3">
        <label className="block text-xs font-medium text-foreground">Used by
          <input className={`${field} mt-1`} value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Analytics team – Power BI" data-autofocus="" />
        </label>
        <label className="block text-xs font-medium text-foreground">Expires after
          <select className={`${field} mt-1`} value={days} onChange={e => setDays(e.target.value)}>
            <option value="30">30 days</option><option value="90">90 days</option><option value="180">180 days</option>
            <option value="365">1 year</option><option value="730">2 years</option>
          </select>
        </label>
        <fieldset>
          <legend className="text-xs font-medium text-foreground">Portfolios</legend>
          <div className="mt-1.5 flex gap-2">
            {[{ v: true, l: 'All portfolios' }, { v: false, l: 'Selected' }].map(o => (
              <label key={o.l} className={`cursor-pointer rounded-lg border px-3 py-1.5 text-[12px] focus-within:ring-2 focus-within:ring-primary ${all === o.v ? 'border-primary bg-primary/10 font-semibold text-primary' : 'border-border text-foreground hover:bg-muted'}`}>
                <input type="radio" name="key-scope" className="sr-only" checked={all === o.v} onChange={() => setAll(o.v)} />{o.l}
              </label>
            ))}
          </div>
          {!all && (
            <div className="mt-2 grid gap-1.5 sm:grid-cols-2">
              {clusters.map(c => (
                <label key={c} className="flex cursor-pointer items-center gap-2 rounded-md border border-border px-2.5 py-1.5 text-[12px] hover:bg-muted">
                  <input type="checkbox" className="h-3.5 w-3.5 rounded border-border text-primary focus:ring-primary"
                    checked={picked.includes(c)} onChange={() => setPicked(p => p.includes(c) ? p.filter(x => x !== c) : [...p, c])} />{c}
                </label>
              ))}
            </div>
          )}
        </fieldset>
        {error && <p role="alert" className="text-xs text-[var(--status-critical-fg)]">{error}</p>}
      </div>
    </Dialog>
  );
}
