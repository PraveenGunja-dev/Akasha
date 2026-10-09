import { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { Eye, EyeOff, KeyRound, Loader2, Check, X } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';

/* Set a new password: required after an administrator creates the account or
   resets it, and available any time from the account menu. The rules shown
   here are the server's (services/security.py); the server re-checks them. */
const MIN = 10;

export default function ChangePassword() {
  const { user, changePassword, logout, homeFor } = useAuth();
  const navigate = useNavigate();
  const from = (useLocation().state as { from?: string } | null)?.from ?? null;
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  if (!user) return null;
  const forced = user.must_change_password;

  const rules = [
    { ok: next.length >= MIN, label: `At least ${MIN} characters` },
    { ok: !!next && !next.toLowerCase().includes(user.username.toLowerCase()), label: 'Does not contain your username' },
    { ok: !!next && next !== current, label: 'Different from the current password' },
    { ok: !!next && next === confirm, label: 'Both entries match' },
  ];
  const valid = !!current && rules.every(r => r.ok);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!valid) return;
    setBusy(true);
    setError('');
    const r = await changePassword(current, next);
    setBusy(false);
    if (!r.success) { setError(r.message); return; }
    navigate(homeFor({ ...user, must_change_password: false }, from), { replace: true });
  };

  const input = 'w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/30';

  return (
    <main className="flex min-h-screen items-center justify-center bg-background px-4 py-10">
      <form onSubmit={submit} className="bento-card w-full max-w-sm p-6" noValidate>
        <div className="flex items-center gap-2">
          <KeyRound className="h-5 w-5 text-primary" aria-hidden />
          <h1 className="text-base font-semibold text-foreground">{forced ? 'Set your password' : 'Change password'}</h1>
        </div>
        <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">
          {forced
            ? `Signed in as ${user.username} with a temporary password. Choose your own to continue.`
            : 'Other devices signed in to your account will be signed out.'}
        </p>

        <label className="mt-5 block text-xs font-medium text-foreground" htmlFor="cp-current">
          {forced ? 'Temporary password' : 'Current password'}
        </label>
        <input id="cp-current" type={show ? 'text' : 'password'} autoComplete="current-password" className={`${input} mt-1`}
          value={current} onChange={e => setCurrent(e.target.value)} required autoFocus />

        <label className="mt-3 block text-xs font-medium text-foreground" htmlFor="cp-new">New password</label>
        <div className="relative mt-1">
          <input id="cp-new" type={show ? 'text' : 'password'} autoComplete="new-password" className={`${input} pr-9`}
            value={next} onChange={e => setNext(e.target.value)} required aria-describedby="cp-rules" />
          <button type="button" onClick={() => setShow(s => !s)} aria-label={show ? 'Hide passwords' : 'Show passwords'}
            className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary">
            {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          </button>
        </div>

        <label className="mt-3 block text-xs font-medium text-foreground" htmlFor="cp-confirm">Confirm new password</label>
        <input id="cp-confirm" type={show ? 'text' : 'password'} autoComplete="new-password" className={`${input} mt-1`}
          value={confirm} onChange={e => setConfirm(e.target.value)} required />

        <ul id="cp-rules" className="mt-3 space-y-1">
          {rules.map(r => (
            <li key={r.label} className={`flex items-center gap-1.5 text-xs ${r.ok ? 'text-[var(--status-healthy-fg)]' : 'text-muted-foreground'}`}>
              {r.ok ? <Check className="h-3.5 w-3.5" aria-hidden /> : <X className="h-3.5 w-3.5" aria-hidden />}
              {r.label}
            </li>
          ))}
        </ul>

        {error && <p role="alert" className="mt-3 rounded-lg border border-[var(--status-critical-border)] bg-[var(--status-critical-bg)] px-3 py-2 text-xs text-[var(--status-critical-fg)]">{error}</p>}

        <button type="submit" disabled={!valid || busy}
          className="mt-5 flex w-full items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2">
          {busy && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
          {forced ? 'Set password and continue' : 'Change password'}
        </button>
        <div className="mt-3 text-center text-xs">
          {forced
            ? <button type="button" onClick={async () => { await logout(); navigate('/login', { replace: true }); }} className="text-muted-foreground hover:text-foreground hover:underline">Sign out</button>
            : <Link to={homeFor(user, from)} className="text-muted-foreground hover:text-foreground hover:underline">Cancel</Link>}
        </div>
      </form>
    </main>
  );
}
