/* ── Theme, in one place ──
   Four screens used to hold their own theme state and toggle the `dark` class
   themselves — the landing page defaulting to dark, the header, PMAG dashboard
   and top bar to light — with nothing persisted. Moving between them flipped
   the theme underneath the user.

   This is the single source: one stored preference, one place that writes the
   class, and a subscription so every toggle on screen agrees. */
export type Theme = 'light' | 'dark';

const KEY = 'akasha-theme';
const listeners = new Set<(t: Theme) => void>();

/** Stored preference, else the OS setting, else light. */
export function getStoredTheme(): Theme {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved === 'light' || saved === 'dark') return saved;
  } catch {
    /* Private mode and blocked site data both throw here; fall through to the
       OS preference rather than failing to render. */
  }
  try {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  } catch {
    return 'light';
  }
}

/** Write the class without touching storage — used for the pre-render pass. */
export function applyTheme(theme: Theme): void {
  document.documentElement.classList.toggle('dark', theme === 'dark');
  document.documentElement.setAttribute('data-theme', theme);
}

/** Change the theme everywhere and remember it. */
export function setTheme(theme: Theme): void {
  applyTheme(theme);
  try {
    localStorage.setItem(KEY, theme);
  } catch {
    /* Not persisting is survivable; flipping the class is the part that matters. */
  }
  listeners.forEach((fn) => fn(theme));
}

export function toggleTheme(): Theme {
  const next: Theme = getCurrentTheme() === 'dark' ? 'light' : 'dark';
  setTheme(next);
  return next;
}

export function getCurrentTheme(): Theme {
  return document.documentElement.classList.contains('dark') ? 'dark' : 'light';
}

export function subscribe(fn: (t: Theme) => void): () => void {
  listeners.add(fn);
  return () => { listeners.delete(fn); };
}
