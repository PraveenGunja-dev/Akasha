/* Email templates: the list, and the editor with a live preview against a
   real project, the variable list, test send, version history and restore. */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ArrowLeft, Download, History, RotateCcw, Save, Search, Send, SendHorizontal } from 'lucide-react';
import { Dialog, StatusPill, cx } from '../../../components/ui/primitives';
import { useAuth } from '../../../context/AuthContext';
import { btn, field, fmtWhen } from '../adminApi';
import { emailApi, SEVERITY_META } from './emailApi';
import type { Catalogue, EmailTemplate, Preview, ProjectOption, Severity, TemplateVersion } from './emailApi';

export default function TemplatesView() {
  const [rows, setRows] = useState<EmailTemplate[]>([]);
  const [cat, setCat] = useState<Catalogue | null>(null);
  const [projects, setProjects] = useState<ProjectOption[]>([]);
  const [editing, setEditing] = useState<string | null>(null);
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
            <tr className="[&>th]:px-3 [&>th]:py-2 [&>th]:font-semibold"><th>Template</th><th>When it is sent</th><th>To · Cc</th><th>Severity</th><th>State</th><th>Version</th><th>Last sent</th></tr>
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
                <td className="px-3 py-2">{t.enabled ? <StatusPill tone="healthy">On</StatusPill> : <StatusPill tone="neutral">Off</StatusPill>}</td>
                <td className="whitespace-nowrap px-3 py-2 text-muted-foreground">v{t.version}{t.updated_by && <span className="block text-[11px]">{t.updated_by}</span>}</td>
                <td className="whitespace-nowrap px-3 py-2 tabular-nums text-muted-foreground">{t.last_sent_at ? fmtWhen(t.last_sent_at) : 'Never'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

type Draft = Pick<EmailTemplate, 'name' | 'severity' | 'subject' | 'body' | 'to_groups' | 'cc_groups' | 'attach_snapshot' | 'enabled'> & { config: string };

function Editor({ tpl, cat, projects, groupName, onBack, onSaved }: {
  tpl: EmailTemplate; cat: Catalogue; projects: ProjectOption[]; groupName: (k: string) => string;
  onBack: () => void; onSaved: (t: EmailTemplate) => void;
}) {
  const { user } = useAuth();
  const initial = (t: EmailTemplate): Draft => ({
    name: t.name, severity: t.severity, subject: t.subject, body: t.body, to_groups: t.to_groups, cc_groups: t.cc_groups,
    attach_snapshot: t.attach_snapshot, enabled: t.enabled, config: JSON.stringify(t.config, null, 2),
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
      emailApi.preview(tpl.key, { project_id: projectId || undefined, subject: d.subject, body: d.body, severity: d.severity })
        .then(setPreview).catch(e => setMsg({ tone: 'err', text: (e as Error).message })).finally(() => setPreviewing(false));
    }, 500);
    return () => window.clearTimeout(t);
  }, [tpl.key, projectId, d.subject, d.body, d.severity]);

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
          <div className="flex flex-wrap gap-4 text-[12.5px]">
            <label className="inline-flex items-center gap-2"><input type="checkbox" checked={d.enabled} onChange={e => setD({ ...d, enabled: e.target.checked })} />Send automatically</label>
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
            <p className="mt-1 text-[11px] text-muted-foreground">e.g. days_before, min_days, escalation steps (after_days, add_to, add_cc).</p>
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
