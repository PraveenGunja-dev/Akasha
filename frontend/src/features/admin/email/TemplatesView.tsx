/* Email templates: the list, and the editor with a live preview against a
   real project, the variable list, test send, version history and restore. */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ArrowLeft, Download, History, RotateCcw, Save, Search, Send, SendHorizontal } from 'lucide-react';
import { Dialog, StatusPill, cx } from '../../../components/ui/primitives';
import { useAuth } from '../../../context/AuthContext';
import { btn, field, fmtWhen } from '../adminApi';
import { emailApi, SEVERITY_META } from './emailApi';
import type { Alert, Level } from '../../alerts/alertsApi';
import type { Catalogue, EmailTemplate, Preview, ProjectOption, Severity, TemplateVersion } from './emailApi';
import { LevelBadge } from '../../alerts/AlertDetail';
import { AckMark, AlertDialog, AlertsTable } from './AlertsView';

/** Who an email at each level reaches (engine.members). */
const LEVEL_WHO: Record<Level, string> = {
  1: 'L1 members only',
  2: 'L1 and L2 members',
  3: 'Everyone - L1, L2 and L3',
};

export default function TemplatesView() {
  const [rows, setRows] = useState<EmailTemplate[]>([]);
  const [cat, setCat] = useState<Catalogue | null>(null);
  const [projects, setProjects] = useState<ProjectOption[]>([]);
  const [editing, setEditing] = useState<string | null>(null);
  const [levelOf, setLevelOf] = useState<EmailTemplate | null>(null);
  const [error, setError] = useState('');

  const load = useCallback(() => {
    emailApi.templates().then(setRows).catch(e => setError((e as Error).message));
  }, []);
  useEffect(() => {
    load();
    emailApi.catalogue().then(setCat).catch(() => undefined);
    emailApi.projects().then(setProjects).catch(() => undefined);
  }, [load]);

  const groupName = (k: string) => cat?.groups.find(g => g.key === k)?.label ?? k;
  const current = rows.find(r => r.key === editing);
  if (current && cat) {
    return <Editor tpl={current} cat={cat} projects={projects} groupName={groupName}
      onBack={() => { setEditing(null); load(); }} onSaved={t => setRows(rs => rs.map(r => (r.key === t.key ? t : r)))} />;
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-[12.5px] text-muted-foreground">Every template starts switched off. Turn one on once its groups have recipients.</p>
        <button type="button" className={btn.secondary} onClick={() => emailApi.exportTemplates().catch(e => setError((e as Error).message))}>
          <Download className="h-3.5 w-3.5" />Export templates
        </button>
      </div>
      {error && <p role="alert" className="rounded-lg border border-[var(--status-critical-border)] bg-[var(--status-critical-bg)] px-3 py-2 text-xs text-[var(--status-critical-fg)]">{error}</p>}
      <div className="bento-card overflow-x-auto p-0">
        <table className="w-full min-w-[900px] text-[12px]">
          <thead className="border-b border-border bg-[var(--neutral-100)] text-left text-[10px] uppercase tracking-wider text-muted-foreground">
            <tr className="[&>th]:px-3 [&>th]:py-2 [&>th]:font-semibold"><th>Template</th><th>When it is sent</th><th>To · Cc</th><th>Severity</th><th>Level · acknowledged</th><th>On / off</th><th>Version</th><th>Last sent</th></tr>
          </thead>
          <tbody>
            {rows.map(t => (
              <tr key={t.key} tabIndex={0} onClick={() => setEditing(t.key)} onKeyDown={e => { if (e.key === 'Enter') setEditing(t.key); }}
                className="cursor-pointer border-b border-[var(--border-subtle)] align-top last:border-0 hover:bg-[var(--surface-sunken)] focus-visible:bg-[var(--surface-sunken)] focus-visible:outline-none">
                <td className="px-3 py-2">
                  <span className="font-semibold text-foreground">{t.name}</span>
                  <span className="block text-[11px] text-muted-foreground">{t.category}{t.attach_snapshot ? ' · PDF snapshot attached' : ''}</span>
                  {t.problems.length > 0 && <span className="mt-0.5 block text-[11px] text-[var(--status-critical-fg)]">{t.problems[0]}</span>}
                </td>
                <td className="max-w-[280px] px-3 py-2 text-muted-foreground">{t.description}</td>
                <td className="px-3 py-2">
                  <span className="text-foreground">{t.to_groups.map(groupName).join(', ') || '—'}</span>
                  {t.cc_groups.length > 0 && <span className="block text-[11px] text-muted-foreground">Cc {t.cc_groups.map(groupName).join(', ')}</span>}
                </td>
                <td className="px-3 py-2"><StatusPill tone={SEVERITY_META[t.severity].tone}>{SEVERITY_META[t.severity].label}</StatusPill></td>
                <td className="px-3 py-2"><LevelCell t={t} onOpen={() => setLevelOf(t)} /></td>
                <td className="px-3 py-2">
                  {t.trigger === 'manual'
                    ? <span className="text-[11px] text-muted-foreground" title="Sent when someone uses it (requests or decides an approval), not on a schedule">When used</span>
                    : <EnabledSwitch t={t} onSaved={saved => setRows(rs => rs.map(r => (r.key === saved.key ? saved : r)))} />}
                </td>
                <td className="whitespace-nowrap px-3 py-2 text-muted-foreground">v{t.version}{t.updated_by && <span className="block text-[11px]">{t.updated_by}</span>}</td>
                <td className="whitespace-nowrap px-3 py-2 tabular-nums text-muted-foreground">{t.last_sent_at ? fmtWhen(t.last_sent_at) : 'Never'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <LevelDialog tpl={levelOf} onClose={() => { setLevelOf(null); load(); }} />
    </div>
  );
}

/* On / off from the list. Saved like any edit - a new version in History,
   with who switched it - so a switch is never silent. Errors (e.g. no To
   group to send to) show on the row. */
function EnabledSwitch({ t, onSaved }: { t: EmailTemplate; onSaved: (t: EmailTemplate) => void }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const flip = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setBusy(true); setErr('');
    try {
      onSaved(await emailApi.saveTemplate(t.key, {
        name: t.name, severity: t.severity, subject: t.subject, body: t.body, to_groups: t.to_groups, cc_groups: t.cc_groups,
        config: t.config, attach_snapshot: t.attach_snapshot, level: t.level, ack_required: t.ack_required,
        enabled: !t.enabled, note: t.enabled ? 'Switched off from the template list' : 'Switched on from the template list',
      }));
    } catch (x) {
      setErr((x as Error).message);
    } finally { setBusy(false); }
  };
  return (
    <div onClick={e => e.stopPropagation()} onKeyDown={e => e.stopPropagation()}>
      <button type="button" role="switch" aria-checked={t.enabled} disabled={busy} onClick={flip}
        aria-label={`${t.name}: ${t.enabled ? 'on - switch off' : 'off - switch on'}`}
        className={cx('inline-flex items-center gap-2 rounded-full py-0.5 pl-0.5 pr-2.5 text-[11.5px] font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 disabled:opacity-60',
          t.enabled ? 'bg-[var(--status-healthy-bg)] text-[var(--status-healthy-fg)]' : 'bg-muted text-muted-foreground hover:text-foreground')}>
        <span aria-hidden className={cx('relative h-4 w-7 rounded-full transition-colors', t.enabled ? 'bg-[var(--status-healthy-solid)]' : 'bg-border')}>
          <span className={cx('absolute top-0.5 h-3 w-3 rounded-full bg-white shadow transition-[left]', t.enabled ? 'left-3.5' : 'left-0.5')} />
        </span>
        {busy ? '…' : t.enabled ? 'On' : 'Off'}
      </button>
      {err && <p role="alert" className="mt-1 max-w-[200px] text-[11px] text-[var(--status-critical-fg)]">{err}</p>}
    </div>
  );
}

/* The template's level of intimation and, in two colours, how its open
   alerts stand: green acknowledged, amber still waiting - with the latest
   acknowledgement. Click for every alert, who acknowledged and when. */
function LevelCell({ t, onOpen }: { t: EmailTemplate; onOpen: () => void }) {
  const a = t.alerts;
  return (
    <button type="button" onClick={e => { e.stopPropagation(); onOpen(); }} onKeyDown={e => e.stopPropagation()}
      aria-label={`${t.name}: level ${t.level}, ${a.acknowledged} acknowledged, ${a.awaiting} awaiting - show alerts`}
      className="-mx-1.5 -my-1 block rounded-md px-1.5 py-1 text-left hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40">
      <span className="flex items-center gap-2">
        <span className="flex items-center gap-0.5">
          {stagesOf(t).map(st => <LevelBadge key={st.level} level={st.level} title={`${st.when} - to ${LEVEL_WHO[st.level as Level]}`} />)}
        </span>
        {!t.ack_required ? <span className="text-[11px] text-muted-foreground">No acknowledgement</span>
          : a.open === 0 ? <span className="text-[11px] text-muted-foreground">No open alerts</span>
            : (
              <span className="flex items-center gap-2.5 text-[11.5px] tabular-nums">
                <span className="inline-flex items-center gap-1" title="Acknowledged"><AckMark acknowledged />{a.acknowledged}</span>
                <span className="inline-flex items-center gap-1" title="Awaiting acknowledgement"><AckMark acknowledged={false} />{a.awaiting}</span>
              </span>
            )}
      </span>
      {t.ack_required && a.last_ack && (
        <span className="mt-0.5 block max-w-[190px] truncate text-[11px] text-muted-foreground" title={`${a.last_ack.by} · ${fmtWhen(a.last_ack.at)}${a.last_ack.project ? ` · ${a.last_ack.project}` : ''}`}>
          {a.last_ack.by} · {fmtWhen(a.last_ack.at)}
        </span>
      )}
    </button>
  );
}

function LevelDialog({ tpl, onClose }: { tpl: EmailTemplate | null; onClose: () => void }) {
  const [rows, setRows] = useState<Alert[] | null>(null);
  const [status, setStatus] = useState<'open' | 'resolved'>('open');
  const [open, setOpen] = useState<number | null>(null);
  const [error, setError] = useState('');
  const load = useCallback(() => {
    if (!tpl) return;
    setRows(null); setError('');
    emailApi.alerts({ template: tpl.key, status }).then(r => setRows(r.alerts)).catch(e => setError((e as Error).message));
  }, [tpl, status]);
  useEffect(load, [load]);
  useEffect(() => { setStatus('open'); }, [tpl?.key]);
  if (!tpl) return null;
  const a = tpl.alerts;
  return (
    <>
      <Dialog open={!!tpl && open == null} onClose={onClose} size="lg" title={tpl.name}
        description={`${stagesOf(tpl).map(st => `L${st.level} ${st.when}`).join(' · ')}.${tpl.ack_required ? ' To recipients acknowledge it in Akasha.' : ' No acknowledgement asked.'}`}
        footer={<button type="button" className={btn.secondary} onClick={onClose}>Close</button>}>
        <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-[12px]">
          <span className="inline-flex items-center gap-1.5"><AckMark acknowledged /><b className="tabular-nums">{a.acknowledged}</b> acknowledged</span>
          <span className="inline-flex items-center gap-1.5"><AckMark acknowledged={false} /><b className="tabular-nums">{a.awaiting}</b> awaiting</span>
          <span className="text-muted-foreground">open alerts whose latest email was this template</span>
          <div role="tablist" aria-label="Open or closed" className="ml-auto inline-flex rounded-lg border border-border p-0.5">
            {(['open', 'resolved'] as const).map(s => (
              <button key={s} type="button" role="tab" aria-selected={status === s} onClick={() => setStatus(s)}
                className={cx('rounded-md px-2.5 py-0.5 text-[12px] font-semibold', status === s ? 'bg-muted text-foreground' : 'text-muted-foreground hover:text-foreground')}>
                {s === 'open' ? 'Open' : 'Closed'}
              </button>
            ))}
          </div>
        </div>
        {error && <p role="alert" className="text-[12px] text-[var(--status-critical-fg)]">{error}</p>}
        {!rows ? <p className="py-6 text-center text-[12px] text-muted-foreground">Loading…</p>
          : rows.length === 0 ? <p className="py-6 text-center text-[12px] text-muted-foreground">{status === 'open' ? 'No open alerts from this template.' : 'No closed alerts from this template.'}</p>
            : <AlertsTable rows={rows} onOpen={setOpen} showTemplate={false} />}
      </Dialog>
      <AlertDialog id={open} onClose={() => setOpen(null)} onChanged={load} />
    </>
  );
}

type Draft = Pick<EmailTemplate, 'name' | 'severity' | 'subject' | 'body' | 'to_groups' | 'cc_groups' | 'attach_snapshot' | 'enabled' | 'level' | 'ack_required'> & { config: string };

function Editor({ tpl, cat, projects, groupName, onBack, onSaved }: {
  tpl: EmailTemplate; cat: Catalogue; projects: ProjectOption[]; groupName: (k: string) => string;
  onBack: () => void; onSaved: (t: EmailTemplate) => void;
}) {
  const { user } = useAuth();
  const initial = (t: EmailTemplate): Draft => ({
    name: t.name, severity: t.severity, subject: t.subject, body: t.body, to_groups: t.to_groups, cc_groups: t.cc_groups,
    attach_snapshot: t.attach_snapshot, enabled: t.enabled, config: JSON.stringify(t.config, null, 2),
    level: t.level, ack_required: t.ack_required,
  });
  const [base, setBase] = useState(tpl);
  const [d, setD] = useState<Draft>(initial(tpl));
  const [projectId, setProjectId] = useState('');
  const [preview, setPreview] = useState<Preview | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [msg, setMsg] = useState<{ tone: 'ok' | 'err'; text: string } | null>(null);
  const [saving, setSaving] = useState(false);
  const [note, setNote] = useState('');
  const [varQuery, setVarQuery] = useState('');
  const [dialog, setDialog] = useState<'' | 'history' | 'test' | 'send' | 'reset'>('');
  const [testTo, setTestTo] = useState(user?.email ?? '');
  const lastField = useRef<'subject' | 'body'>('body');
  const subjectRef = useRef<HTMLInputElement>(null);
  const bodyRef = useRef<HTMLTextAreaElement>(null);

  const dirty = JSON.stringify(d) !== JSON.stringify(initial(base));

  // Live preview, debounced, with unsaved edits.
  useEffect(() => {
    const t = window.setTimeout(() => {
      setPreviewing(true);
      emailApi.preview(tpl.key, { project_id: projectId || undefined, subject: d.subject, body: d.body, severity: d.severity,
        level: d.level, ack_required: d.ack_required })
        .then(setPreview).catch(e => setMsg({ tone: 'err', text: (e as Error).message })).finally(() => setPreviewing(false));
    }, 500);
    return () => window.clearTimeout(t);
  }, [tpl.key, projectId, d.subject, d.body, d.severity, d.level, d.ack_required]);

  const insert = (key: string) => {
    const token = `{{${key}}}`;
    const el = lastField.current === 'subject' ? subjectRef.current : bodyRef.current;
    const k = lastField.current;
    if (!el) return;
    const start = el.selectionStart ?? el.value.length, end = el.selectionEnd ?? el.value.length;
    const next = el.value.slice(0, start) + token + el.value.slice(end);
    setD(x => ({ ...x, [k]: next }));
    window.setTimeout(() => { el.focus(); el.setSelectionRange(start + token.length, start + token.length); }, 0);
  };

  const toggleGroup = (which: 'to_groups' | 'cc_groups', key: string) =>
    setD(x => ({ ...x, [which]: x[which].includes(key) ? x[which].filter(g => g !== key) : [...x[which], key] }));

  const save = async () => {
    let config: Record<string, unknown>;
    try { config = JSON.parse(d.config || '{}'); } catch { setMsg({ tone: 'err', text: 'Settings must be valid JSON' }); return; }
    setSaving(true); setMsg(null);
    try {
      const saved = await emailApi.saveTemplate(tpl.key, { ...d, config, note: note || undefined });
      setBase(saved); setD(initial(saved)); setNote(''); onSaved(saved);
      setMsg({ tone: 'ok', text: `Saved as version ${saved.version}` });
    } catch (e) {
      setMsg({ tone: 'err', text: (e as Error).message });
    } finally { setSaving(false); }
  };

  const afterRestore = (t: EmailTemplate, text: string) => { setBase(t); setD(initial(t)); onSaved(t); setDialog(''); setMsg({ tone: 'ok', text }); };

  const vars = useMemo(() => cat.variables.filter(v => !varQuery || `${v.key} ${v.label} ${v.meaning}`.toLowerCase().includes(varQuery.toLowerCase())), [cat.variables, varQuery]);
  const problems = preview?.problems ?? [];

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <button type="button" className={btn.ghost} onClick={onBack}><ArrowLeft className="h-3.5 w-3.5" />All templates</button>
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" className={btn.secondary} onClick={() => setDialog('history')}><History className="h-3.5 w-3.5" />History (v{base.version})</button>
          <button type="button" className={btn.secondary} onClick={() => setDialog('test')}><Send className="h-3.5 w-3.5" />Send test</button>
          {tpl.trigger === 'manual' && <button type="button" className={btn.secondary} onClick={() => setDialog('send')}><SendHorizontal className="h-3.5 w-3.5" />Send for a project</button>}
          <button type="button" className={btn.primary} disabled={!dirty || saving || problems.length > 0} onClick={save}><Save className="h-3.5 w-3.5" />{saving ? 'Saving…' : 'Save'}</button>
        </div>
      </div>
      {msg && <p role="status" className={cx('rounded-lg border px-3 py-2 text-xs', msg.tone === 'ok'
        ? 'border-[var(--status-healthy-border)] bg-[var(--status-healthy-bg)] text-[var(--status-healthy-fg)]'
        : 'border-[var(--status-critical-border)] bg-[var(--status-critical-bg)] text-[var(--status-critical-fg)]')}>{msg.text}</p>}

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        {/* Form */}
        <div className="bento-card space-y-3 p-4">
          <div>
            <h2 className="text-[15px] font-semibold text-foreground">{base.name}</h2>
            <p className="text-[12px] text-muted-foreground">{base.trigger_label}</p>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block text-[12px] font-medium text-foreground">Name
              <input className={`${field} mt-1`} value={d.name} onChange={e => setD({ ...d, name: e.target.value })} />
            </label>
            <label className="block text-[12px] font-medium text-foreground">Severity
              <select className={`${field} mt-1`} value={d.severity} onChange={e => setD({ ...d, severity: e.target.value as Severity })}>
                {(Object.keys(SEVERITY_META) as Severity[]).map(s => <option key={s} value={s}>{SEVERITY_META[s].label}</option>)}
              </select>
            </label>
          </div>
          <WhenSent tpl={tpl} config={d.config} groupName={groupName} onConfig={config => setD(x => ({ ...x, config }))} />
          {!STAGED.includes(tpl.trigger) && <fieldset>
            <legend className="text-[12px] font-medium text-foreground">Level - who gets this email</legend>
            <div className="mt-1 grid gap-1.5 sm:grid-cols-3">
              {([1, 2, 3] as const).map(l => (
                <label key={l} className={cx('flex cursor-pointer items-center gap-2 rounded-lg border px-2.5 py-2 text-[12px] transition-colors focus-within:ring-2 focus-within:ring-primary/40',
                  d.level === l ? 'border-primary bg-primary/5 text-foreground' : 'border-border text-muted-foreground hover:bg-muted/60')}>
                  <input type="radio" name="tpl-level" className="sr-only" checked={d.level === l} onChange={() => setD({ ...d, level: l })} />
                  <LevelBadge level={l} />
                  <span className="leading-snug">{LEVEL_WHO[l]}</span>
                </label>
              ))}
            </div>
            <p className="mt-1 text-[11px] text-muted-foreground">Each person's level is set in Distribution groups.</p>
          </fieldset>}
          <div className="flex flex-wrap gap-4 text-[12.5px]">
            <label className="inline-flex items-center gap-2"><input type="checkbox" checked={d.enabled} onChange={e => setD({ ...d, enabled: e.target.checked })} />Send automatically</label>
            <label className="inline-flex items-center gap-2"><input type="checkbox" checked={d.ack_required} onChange={e => setD({ ...d, ack_required: e.target.checked })} />To recipients acknowledge in Akasha</label>
            <label className="inline-flex items-center gap-2"><input type="checkbox" checked={d.attach_snapshot} onChange={e => setD({ ...d, attach_snapshot: e.target.checked })} />Attach project snapshot (PDF)</label>
          </div>
          {(['to_groups', 'cc_groups'] as const).map(which => (
            <fieldset key={which}>
              <legend className="text-[12px] font-medium text-foreground">{which === 'to_groups' ? 'To' : 'Cc'}</legend>
              <div className="mt-1 flex flex-wrap gap-1.5">
                {cat.groups.map(g => {
                  const on = d[which].includes(g.key);
                  return (
                    <button key={g.key} type="button" aria-pressed={on} onClick={() => toggleGroup(which, g.key)}
                      className={cx('rounded-full border px-2.5 py-1 text-[11.5px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40',
                        on ? 'border-primary bg-primary/10 text-primary' : 'border-border text-muted-foreground hover:text-foreground')}>{g.label}</button>
                  );
                })}
              </div>
            </fieldset>
          ))}
          <label className="block text-[12px] font-medium text-foreground">Subject
            <input ref={subjectRef} className={`${field} mt-1 font-mono text-[12px]`} value={d.subject}
              onFocus={() => { lastField.current = 'subject'; }} onChange={e => setD({ ...d, subject: e.target.value })} />
          </label>
          <label className="block text-[12px] font-medium text-foreground">Body
            <textarea ref={bodyRef} rows={16} className={`${field} mt-1 font-mono text-[12px] leading-relaxed`} value={d.body}
              onFocus={() => { lastField.current = 'body'; }} onChange={e => setD({ ...d, body: e.target.value })} />
          </label>
          <p className="text-[11px] leading-relaxed text-muted-foreground">
            “Label: value” lines become the details table · “Required Action: …” is highlighted · **text** is bold · a blank line starts a paragraph.
            A value Akasha does not have shows “Not available”.
          </p>
          <details className="rounded-lg border border-border px-3 py-2">
            <summary className="cursor-pointer text-[12px] font-medium text-foreground">Trigger settings (advanced)</summary>
            <textarea rows={6} className={`${field} mt-2 font-mono text-[11.5px]`} value={d.config} onChange={e => setD({ ...d, config: e.target.value })} />
            <p className="mt-1 text-[11px] text-muted-foreground">The same settings as “When it is sent”, as JSON - also the groups each overdue step adds (add_to, add_cc).</p>
          </details>
          <label className="block text-[12px] font-medium text-foreground">Change note (saved in history)
            <input className={`${field} mt-1`} value={note} maxLength={300} placeholder="What changed and why" onChange={e => setNote(e.target.value)} />
          </label>
        </div>

        {/* Preview + variables */}
        <div className="space-y-3">
          <div className="bento-card space-y-2 p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-[13px] font-semibold text-foreground">Preview {previewing && <span className="font-normal text-muted-foreground">· updating…</span>}</h3>
              <select aria-label="Preview with project" className={`${field.replace('w-full ', '')} w-auto max-w-[280px] py-1.5 text-[12px]`} value={projectId} onChange={e => setProjectId(e.target.value)}>
                <option value="">A project this would fire for</option>
                {projects.map(p => <option key={p.project_id} value={p.project_id}>{p.name} · {p.project_id}</option>)}
              </select>
            </div>
            {preview && (
              <>
                <p className="text-[12.5px]"><span className="text-muted-foreground">Subject:</span> <span className="font-semibold text-foreground">{preview.subject}</span></p>
                <p className="text-[11.5px] text-muted-foreground">
                  To: {preview.to.join(', ') || 'no recipients in these groups yet'}{preview.cc.length > 0 && ` · Cc: ${preview.cc.join(', ')}`}
                  {preview.project_name && ` · for ${preview.project_name}`}
                </p>
                {problems.length > 0 && <ul className="rounded-md bg-[var(--status-critical-bg)] px-3 py-2 text-[11.5px] text-[var(--status-critical-fg)]">{problems.map(p => <li key={p}>{p}</li>)}</ul>}
                {preview.empty.length > 0 && <p className="text-[11.5px] text-[var(--status-watch-fg)]">No value for this project: {preview.empty.map(v => `{{${v}}}`).join(', ')} - shown as “Not available”.</p>}
                <iframe title="Email preview" sandbox="" srcDoc={preview.html} className="h-[560px] w-full rounded-lg border border-border bg-white" />
              </>
            )}
          </div>
          <div className="bento-card p-4">
            <div className="mb-2 flex items-center justify-between gap-2">
              <h3 className="text-[13px] font-semibold text-foreground">Variables</h3>
              <div className="relative w-48">
                <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden />
                <input aria-label="Search variables" className={`${field} py-1 pl-7 text-[12px]`} value={varQuery} onChange={e => setVarQuery(e.target.value)} placeholder="Search" />
              </div>
            </div>
            <p className="mb-2 text-[11px] text-muted-foreground">Click to insert at the cursor in the subject or body.</p>
            <div className="max-h-[260px] space-y-0.5 overflow-auto pr-1">
              {vars.map(v => (
                <button key={v.key} type="button" onClick={() => insert(v.key)} title={v.meaning}
                  className="flex w-full items-baseline justify-between gap-3 rounded-md px-2 py-1 text-left hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40">
                  <span className="font-mono text-[11.5px] text-primary">{`{{${v.key}}}`}</span>
                  <span className="truncate text-[11px] text-muted-foreground">{v.label}</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      <HistoryDialog open={dialog === 'history'} tpl={base} onClose={() => setDialog('')}
        onRestored={t => afterRestore(t, `Restored - now version ${t.version}`)}
        onReset={() => setDialog('reset')} />
      <Dialog open={dialog === 'reset'} onClose={() => setDialog('')} title="Reset to the Akasha default?"
        description="The subject, body, groups and settings go back to the shipped text. The current version stays in history."
        footer={<><button type="button" className={btn.secondary} onClick={() => setDialog('')}>Cancel</button>
          <button type="button" className={btn.danger} onClick={() => emailApi.reset(tpl.key).then(t => afterRestore(t, `Reset - now version ${t.version}`)).catch(e => setMsg({ tone: 'err', text: (e as Error).message }))}>
            <RotateCcw className="h-3.5 w-3.5" />Reset</button></>} />
      <Dialog open={dialog === 'test'} onClose={() => setDialog('')} title="Send a test"
        description="The saved template, for the project chosen in the preview, to one address only - marked [TEST]."
        footer={<><button type="button" className={btn.secondary} onClick={() => setDialog('')}>Cancel</button>
          <button type="button" className={btn.primary} disabled={!testTo} onClick={() => {
            setDialog('');
            emailApi.test(tpl.key, testTo, projectId || undefined)
              .then(r => setMsg(r.status === 'failed' ? { tone: 'err', text: `Test failed: ${r.detail}` } : { tone: 'ok', text: `Test sent to ${testTo}` }))
              .catch(e => setMsg({ tone: 'err', text: (e as Error).message }));
          }}><Send className="h-3.5 w-3.5" />Send test</button></>}>
        {dirty && <p className="mb-2 text-[12px] text-[var(--status-watch-fg)]">Unsaved changes are not included - save first to test them.</p>}
        <label className="block text-[12px] font-medium text-foreground">Send to
          <input className={`${field} mt-1`} type="email" value={testTo} onChange={e => setTestTo(e.target.value)} />
        </label>
      </Dialog>
      <Dialog open={dialog === 'send'} onClose={() => setDialog('')} title="Send for a project"
        description="Sends this template now to its To and Cc groups for the project chosen in the preview."
        footer={<><button type="button" className={btn.secondary} onClick={() => setDialog('')}>Cancel</button>
          <button type="button" className={btn.primary} disabled={!projectId} onClick={() => {
            setDialog('');
            emailApi.sendFor(tpl.key, projectId)
              .then(r => setMsg(r.status === 'failed' ? { tone: 'err', text: `Not sent: ${r.detail}` } : { tone: 'ok', text: `Sent (${r.status}) to ${(r.to ?? []).join(', ')}` }))
              .catch(e => setMsg({ tone: 'err', text: (e as Error).message }));
          }}><SendHorizontal className="h-3.5 w-3.5" />Send</button></>}>
        <p className="text-[12.5px] text-muted-foreground">{projectId ? `Project: ${projects.find(p => p.project_id === projectId)?.name ?? projectId}` : 'Choose a project in the preview first.'}</p>
      </Dialog>
    </div>
  );
}

function HistoryDialog({ open, tpl, onClose, onRestored, onReset }: {
  open: boolean; tpl: EmailTemplate; onClose: () => void; onRestored: (t: EmailTemplate) => void; onReset: () => void;
}) {
  const [rows, setRows] = useState<TemplateVersion[]>([]);
  const [shown, setShown] = useState<number | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    if (!open) return;
    emailApi.versions(tpl.key).then(r => { setRows(r); setShown(r[0]?.version ?? null); }).catch(e => setError((e as Error).message));
  }, [open, tpl.key, tpl.version]);
  const v = rows.find(r => r.version === shown);
  return (
    <Dialog open={open} onClose={onClose} size="lg" title={`History · ${tpl.name}`}
      description="Every saved version. Restoring one saves it as a new version, so nothing is lost."
      footer={<><button type="button" className={btn.ghost} onClick={onReset}><RotateCcw className="h-3.5 w-3.5" />Reset to default</button>
        <button type="button" className={btn.secondary} onClick={onClose}>Close</button></>}>
      {error && <p role="alert" className="text-xs text-[var(--status-critical-fg)]">{error}</p>}
      <div className="grid gap-3 sm:grid-cols-[200px_minmax(0,1fr)]">
        <ul className="max-h-[420px] space-y-1 overflow-auto">
          {rows.map(r => (
            <li key={r.version}>
              <button type="button" onClick={() => setShown(r.version)}
                className={cx('w-full rounded-md px-2 py-1.5 text-left text-[12px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40',
                  r.version === shown ? 'bg-primary/10 text-foreground' : 'hover:bg-muted text-muted-foreground')}>
                <span className="font-semibold">v{r.version}</span>{r.version === tpl.version && ' · current'}
                <span className="block text-[11px]">{r.changed_by} · {fmtWhen(r.changed_at)}</span>
                {r.note && <span className="block truncate text-[11px] italic">{r.note}</span>}
              </button>
            </li>
          ))}
        </ul>
        {v && (
          <div className="min-w-0 space-y-2">
            <p className="text-[12px]"><span className="text-muted-foreground">Subject:</span> <span className="font-mono">{v.subject}</span></p>
            <p className="text-[11.5px] text-muted-foreground">To {v.to_groups.join(', ') || '—'} · Cc {v.cc_groups.join(', ') || '—'} · {v.enabled ? 'on' : 'off'}{v.attach_snapshot ? ' · PDF' : ''}</p>
            <pre className="max-h-[320px] overflow-auto whitespace-pre-wrap rounded-md border border-border bg-[var(--surface-sunken)] p-2 text-[11.5px]">{v.body}</pre>
            {v.version !== tpl.version && (
              <button type="button" className={btn.secondary} onClick={() => emailApi.restore(tpl.key, v.version).then(onRestored).catch(e => setError((e as Error).message))}>
                <RotateCcw className="h-3.5 w-3.5" />Restore version {v.version}</button>
            )}
          </div>
        )}
      </div>
    </Dialog>
  );
}

/* ── When it is sent ────────────────────────────────────────────────────────
   The trigger's timing as plain fields (they edit the same config JSON as
   the advanced box), and for module ordering the whole reminder ladder -
   every stage's day and level - so a change is seen in context. */

type Cfg = Record<string, unknown>;
interface Step { after_days: number; label?: string; add_to?: string[]; add_cc?: string[] }
const WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
const STAGED = ['ordering_due', 'ordering_overdue', 'project_delay', 'aop_due'];   // templates whose days set L1 / L2 / L3

function parseCfg(text: string): Cfg | null {
  try { const v = JSON.parse(text || '{}'); return v && typeof v === 'object' && !Array.isArray(v) ? v as Cfg : null; } catch { return null; }
}
const num = (v: unknown, dflt: number) => (typeof v === 'number' && Number.isFinite(v) ? v : dflt);

/* A whole number typed as text: no spinner, and the mouse wheel cannot
   change it. A valid number in range is applied as it is typed; anything else
   is shown as invalid and goes back to the last good value on leaving. */
function DayInput({ value, min, max, onChange, label }: {
  value: number | null; min: number; max: number; onChange: (n: number) => void; label: string;
}) {
  const [draft, setDraft] = useState(value == null ? '' : String(value));
  useEffect(() => { setDraft(value == null ? '' : String(value)); }, [value]);
  const n = Number(draft);
  const ok = draft !== '' && Number.isInteger(n) && n >= min && n <= max;
  return (
    <input type="text" inputMode="numeric" autoComplete="off" aria-label={label} aria-invalid={!ok}
      title={`${min} to ${max}`}
      className={cx(`${field.replace('w-full ', '')} w-20 py-1.5 tabular-nums`, !ok && 'border-[var(--status-critical-border)] focus:border-[var(--status-critical-border)]')}
      value={draft}
      onChange={e => {
        const v = e.target.value;
        if (!/^\d{0,3}$/.test(v)) return;
        setDraft(v);
        const k = Number(v);
        if (v !== '' && k >= min && k <= max) onChange(k);
      }}
      onBlur={() => { if (!ok) setDraft(value == null ? '' : String(value)); }} />
  );
}

function NumField({ label, value, min, max, suffix, onChange }: {
  label: string; value: number; min: number; max: number; suffix: string; onChange: (n: number) => void;
}) {
  return (
    <label className="flex flex-wrap items-center gap-2 text-[12.5px] text-foreground">
      <span>{label}</span>
      <DayInput value={value} min={min} max={max} onChange={onChange} label={label} />
      <span className="text-muted-foreground">{suffix}</span>
    </label>
  );
}

/** The template's levels and when each goes, for the list and dialog. */
function stagesOf(t: Pick<EmailTemplate, 'trigger' | 'config' | 'level'>): { level: number; when: string }[] {
  if (t.trigger === 'ordering_due') {
    const lv = t.config.levels as Record<string, number> | undefined;
    if (lv && typeof lv === 'object') {
      return Object.entries(lv).map(([k, v]) => ({ level: Number(k), when: `${v} days before the ordering date`, n: -Number(v) }))
        .filter(x => x.level >= 1 && x.level <= 3).sort((a, b) => a.n - b.n).map(({ level, when }) => ({ level, when }));
    }
    return [{ level: t.level, when: `${num(t.config.days_before, 30)} days before the ordering date` }];
  }
  if (t.trigger === 'project_delay' || t.trigger === 'aop_due') {
    const lv = (t.config.levels ?? {}) as Record<string, number>;
    const unit = t.trigger === 'project_delay' ? 'days late against the AOP' : 'days before the AOP';
    return Object.entries(lv).map(([k, v]) => ({ level: Number(k), when: `${v} ${unit}` })).filter(x => x.level >= 1 && x.level <= 3)
      .sort((a, b) => a.level - b.level);
  }
  if (t.trigger === 'ordering_overdue') {
    const steps = (Array.isArray(t.config.escalation) ? t.config.escalation as Step[] : []).slice().sort((a, b) => a.after_days - b.after_days);
    return steps.slice(0, 3).map((st, i) => ({ level: Math.max(t.level, i + 1), when: st.after_days ? `${st.after_days} days overdue` : 'when the date is missed' }));
  }
  return [{ level: t.level, when: 'when triggered' }];
}

function WhenSent({ tpl, config, groupName, onConfig }: {
  tpl: EmailTemplate; config: string; groupName: (k: string) => string; onConfig: (json: string) => void;
}) {
  const cfg = parseCfg(config);
  const set = (patch: Cfg) => onConfig(JSON.stringify({ ...(cfg ?? {}), ...patch }, null, 2));
  const trig = tpl.trigger;
  let body: React.ReactNode;

  if (!cfg) {
    body = <p className="text-[12px] text-[var(--status-critical-fg)]">The trigger settings at the bottom are not valid JSON - fix them to edit the timing here.</p>;
  } else if (trig === 'ordering_due') {
    const lv = (cfg.levels && typeof cfg.levels === 'object' ? cfg.levels : { [tpl.level]: num(cfg.days_before, 30) }) as Record<string, number>;
    const setLevel = (l: number, n: number) => {
      const next: Record<string, number> = { ...lv, [l]: n };
      const rest: Cfg = { ...cfg, levels: next };
      delete rest.days_before;
      onConfig(JSON.stringify(rest, null, 2));
    };
    const vals = [1, 2, 3].map(l => lv[String(l)]);
    const outOfOrder = vals.some((v, i) => i > 0 && v != null && vals[i - 1] != null && v >= vals[i - 1]!);
    body = (
      <LevelRows unit="days before the ordering date" outOfOrder={outOfOrder}
        rows={[1, 2, 3].map(l => ({ level: l, value: lv[String(l)] ?? null, onChange: (n: number) => setLevel(l, n), min: 1, max: 365 }))} />
    );
  } else if (trig === 'ordering_overdue') {
    const steps: Step[] = (Array.isArray(cfg.escalation) ? cfg.escalation as Step[] : []).slice().sort((a, b) => a.after_days - b.after_days);
    const setStep = (i: number, n: number) => set({ escalation: steps.map((st, j) => (j === i ? { ...st, after_days: n } : st)) });
    const outOfOrder = steps.some((st, i) => i > 0 && st.after_days <= steps[i - 1].after_days);
    body = (
      <LevelRows unit="days after the ordering date" outOfOrder={outOfOrder}
        rows={steps.map((st, i) => ({
          level: Math.min(i + 1, 3), value: st.after_days, onChange: (n: number) => setStep(i, n), min: 0, max: 180,
          extra: ((st.add_to?.length ?? 0) + (st.add_cc?.length ?? 0)) > 0
            ? `also ${[st.add_to?.length ? st.add_to.map(groupName).join(', ') : '', st.add_cc?.length ? `Cc ${st.add_cc.map(groupName).join(', ')}` : ''].filter(Boolean).join(' · ')}`
            : undefined,
        }))} />
    );
  } else if (trig === 'project_delay' || trig === 'aop_due') {
    const late = trig === 'project_delay';
    const lv = (cfg.levels && typeof cfg.levels === 'object' ? cfg.levels : {}) as Record<string, number>;
    const setLevel = (l: number, n: number) => set({ levels: { ...lv, [l]: n } });
    const vals = [1, 2, 3].map(l => lv[String(l)]);
    const outOfOrder = vals.some((v, i) => i > 0 && v != null && vals[i - 1] != null && (late ? v <= vals[i - 1]! : v >= vals[i - 1]!));
    body = (
      <div className="space-y-2">
        <p className="text-[12.5px] text-foreground">
          {late ? 'When COD runs later than the AOP (P6 baseline COD), going by the P6 forecast - or today, if that forecast has passed without COD:'
            : 'Before the AOP (P6 baseline COD) while COD is not achieved; once the AOP passes, the project-delay email takes over:'}
        </p>
        <LevelRows unit={late ? 'days late against the AOP' : 'days before the AOP'} outOfOrder={outOfOrder}
          rows={[1, 2, 3].map(l => ({ level: l, value: lv[String(l)] ?? null, onChange: (n: number) => setLevel(l, n), min: 0, max: 730 }))} />
      </div>
    );
  } else if (trig === 'ordering_today') {
    body = <p className="text-[12.5px] text-foreground">On the ordering date, if the phase is still not ordered.</p>;
  } else if (trig === 'awaiting_grn') {
    body = (
      <div className="space-y-1.5">
        <NumField label="Send when modules have been dispatched with no GRN for" value={num(cfg.min_days, 30)} min={1} max={365} suffix="days" onChange={n => set({ min_days: n })} />
        <NumField label="Then remind every" value={num(cfg.remind_every_days, 7)} min={1} max={90} suffix="days" onChange={n => set({ remind_every_days: n })} />
      </div>
    );
  } else if (trig === 'site_stock_low') {
    body = <NumField label="Send when modules on site fall to" value={num(cfg.min_stock_mwp, 5)} min={0} max={1000} suffix="MWp or less" onChange={n => set({ min_stock_mwp: n })} />;
  } else if (trig === 'sync_failed') {
    body = <NumField label="Send when a sync fails, or there is no successful sync for" value={num(cfg.stale_hours, 26)} min={1} max={720} suffix="hours" onChange={n => set({ stale_hours: n })} />;
  } else if (trig === 'weekly_digest') {
    body = (
      <label className="flex items-center gap-2 text-[12.5px] text-foreground">Send every
        <select className={`${field.replace('w-full ', '')} w-40 py-1.5`} value={num(cfg.weekday, 0)} onChange={e => set({ weekday: Number(e.target.value) })}>
          {WEEKDAYS.map((w, i) => <option key={w} value={i}>{w}</option>)}
        </select>
      </label>
    );
  } else if (trig === 'manual') {
    body = <p className="text-[12.5px] text-foreground">Only when someone sends it from this screen (Send for a project).</p>;
  } else {
    body = <p className="text-[12.5px] text-foreground">{tpl.trigger_label}</p>;
  }

  return (
    <section className="rounded-lg border border-border p-3" aria-labelledby="when-sent">
      <h3 id="when-sent" className="mb-2 text-[12px] font-semibold text-foreground">When it is sent</h3>
      {body}
    </section>
  );
}

/* One row per level: L1 / L2 / L3 and the day it goes. */
function LevelRows({ rows, unit, outOfOrder }: {
  rows: { level: number; value: number | null; onChange: (n: number) => void; min: number; max: number; extra?: string }[];
  unit: string; outOfOrder: boolean;
}) {
  return (
    <div className="space-y-1.5">
      {rows.map(r => (
        <label key={r.level} className="flex flex-wrap items-center gap-2 text-[12.5px] text-foreground">
          <LevelBadge level={r.level} />
          <DayInput value={r.value} min={r.min} max={r.max} onChange={r.onChange} label={`Level ${r.level}: ${unit}`} />
          <span className="text-muted-foreground">{unit}</span>
          <span className="text-[11.5px] text-muted-foreground">- to {LEVEL_WHO[r.level as Level]}{r.extra ? `; ${r.extra}` : ''}</span>
        </label>
      ))}
      {outOfOrder && <p role="alert" className="text-[11.5px] text-[var(--status-critical-fg)]">Each level must come after the one before (L1 first, L3 last).</p>}
      <p className="text-[11px] text-muted-foreground">If someone acknowledged with an expected date that has not passed (for module orders, on or before the ordering date), the next email stays at the current level instead of moving up.</p>
    </div>
  );
}
