import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Loader2, User, Eye, EyeOff, AlertCircle } from 'lucide-react';

const ROLE_ROUTES: Record<string, string> = {
  executive: '/ceo-dashboard',
  pmag: '/pmag',
  projects: '/projects',
  tc_ordering: '/tc-ordering',
  tc_stores: '/tc-stores',
};

export default function LoginPage() {
  const { login, isAuthenticated, user } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  // If already logged in, redirect to their dashboard
  useEffect(() => {
    if (isAuthenticated && user) {
      navigate(ROLE_ROUTES[user.role] || '/ceo-dashboard', { replace: true });
    }
  }, [isAuthenticated, user, navigate]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    const result = await login(username, password);
    setLoading(false);

    if (!result.success) {
      setError(result.message);
    }
    // If successful, the useEffect above will handle navigation
  };

  const field =
    'w-full rounded-lg border border-input bg-surface-1 px-3 py-2.5 text-[14px] text-fg-primary placeholder:text-fg-disabled transition-colors focus:outline-none focus-visible:border-primary-600 focus-visible:ring-2 focus-visible:ring-primary/20';

  return (
    <div className="flex min-h-screen bg-surface-0">

      {/* Context panel — carries the brand so the form itself can stay plain.
          Hidden on small screens where the form is the only thing that matters. */}
      <aside className="relative hidden w-[42%] max-w-[560px] flex-col justify-between bg-neutral-900 p-12 lg:flex">
        <div className="flex items-baseline gap-2">
          <span className="bg-gradient-to-r from-brand-blue via-brand-purple to-brand-pink bg-clip-text text-[22px] font-black uppercase leading-none tracking-tighter text-transparent">
            Akasha
          </span>
          <span className="text-[9px] font-bold uppercase tracking-[0.22em] text-neutral-500">
            Execution Platform
          </span>
        </div>

        <div className="max-w-[380px]">
          <h2 className="text-[26px] font-semibold leading-[1.25] tracking-[-0.015em] text-neutral-0">
            One canonical project identity across eight enterprise systems.
          </h2>
          <p className="mt-4 text-[13px] leading-relaxed text-neutral-400">
            Schedule, procurement, materials, quality, transmission and invoicing —
            joined, reconciled and reported against a single source of project truth.
          </p>
        </div>

        <p className="text-[11px] text-neutral-600">Adani Green Energy Limited</p>
      </aside>

      {/* Sign-in */}
      <main className="flex flex-1 items-center justify-center px-6 py-12">
        <div className="w-full max-w-[360px]">

          {/* Brand repeats here only where the context panel is not rendered. */}
          <div className="mb-8 lg:hidden">
            <span className="bg-gradient-to-r from-brand-blue via-brand-purple to-brand-pink bg-clip-text text-[22px] font-black uppercase leading-none tracking-tighter text-transparent">
              Akasha
            </span>
          </div>

          <h1 className="text-[20px] font-semibold tracking-[-0.015em] text-fg-primary">Sign in</h1>
          <p className="mt-1 text-[13px] text-fg-tertiary">Use your Akasha platform credentials.</p>

          <form onSubmit={handleSubmit} className="mt-8 space-y-4">
            <div>
              <label htmlFor="username" className="mb-1.5 block text-[12px] font-semibold text-fg-secondary">
                Username
              </label>
              <div className="relative">
                <User className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-fg-disabled" />
                <input
                  id="username"
                  type="text"
                  value={username}
                  onChange={e => setUsername(e.target.value)}
                  className={`${field} pl-9`}
                  placeholder="Enter your username"
                  autoComplete="username"
                  required
                />
              </div>
            </div>

            <div>
              <label htmlFor="password" className="mb-1.5 block text-[12px] font-semibold text-fg-secondary">
                Password
              </label>
              <div className="relative">
                <input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  className={`${field} pr-10`}
                  placeholder="Enter your password"
                  autoComplete="current-password"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                  className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded p-1.5 text-fg-tertiary transition-colors hover:text-fg-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>

            {error && (
              <p
                role="alert"
                className="flex items-start gap-2 rounded-lg border border-status-critical-border bg-status-critical-bg px-3 py-2.5 text-[12px] font-medium text-status-critical-fg"
              >
                <AlertCircle className="mt-px h-3.5 w-3.5 shrink-0" />
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={loading || !username.trim() || !password.trim()}
              className="flex w-full items-center justify-center gap-2 rounded-lg bg-primary-600 py-2.5 text-[14px] font-semibold text-white transition-colors hover:bg-primary-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:cursor-not-allowed disabled:opacity-40"
            >
              {loading && <Loader2 className="h-4 w-4 animate-spin" />}
              {loading ? 'Signing in…' : 'Sign in'}
            </button>
          </form>

          <p className="mt-10 text-[11px] text-fg-disabled lg:hidden">
            Akasha Execution Platform — Adani Green Energy Limited
          </p>
        </div>
      </main>
    </div>
  );
}
