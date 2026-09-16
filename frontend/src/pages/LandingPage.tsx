import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowRight, GitMerge, Layers, ShieldCheck, Database, Calendar,
  Network, Activity, FileText, BarChart2, CheckCircle, Command,
} from "lucide-react";
import PresentationModal from "../components/ui/PresentationModal";
import { useAuth } from "../context/AuthContext";

const ROLE_ROUTES: Record<string, string> = {
  executive: '/ceo-dashboard',
  pmag: '/pmag',
  projects: '/projects',
  tc_ordering: '/tc-ordering',
  tc_stores: '/tc-stores',
};

/* What the platform is for. Each line is a claim the product actually makes
   good on — provenance, coverage, auditability — not a feature boast. */
const PILLARS = [
  { icon: GitMerge, name: 'Reconciled', detail: 'Every figure traces back to the system it came from.' },
  { icon: Layers, name: 'Complete', detail: 'Eight ingest paths resolving onto one project record.' },
  { icon: ShieldCheck, name: 'Auditable', detail: 'The counts behind every percentage, on demand.' },
];

/* Modules the nav rail actually ships. */
const MODULES = [
  { name: 'SAP Intelligence', detail: 'Purchase orders, delivery and consumption', icon: Database },
  { name: 'P6 & DPR', detail: 'Schedule progress and daily reporting', icon: Calendar },
  { name: 'Transmission', detail: 'Corridor and substation build status', icon: Network },
  { name: 'Quality', detail: 'Non-conformances and inspection requests', icon: Activity },
  { name: 'E-Invoice', detail: 'Invoice capture and reconciliation', icon: FileText },
  { name: 'Capacity', detail: 'Commissioned, in-progress and upcoming MW', icon: BarChart2 },
  { name: 'Approvals', detail: 'Statutory and compliance clearances', icon: CheckCircle },
  { name: 'Project 360', detail: 'Every system against one project identity', icon: Command },
];

/* Deterministic star field — computed once at module load from a fixed seed so
   the pattern never reshuffles between renders. Static marks, no animation
   loop: the motion in this hero comes from the rings alone. */
const STARS = (() => {
  let seed = 20260916;
  const rand = () => {
    seed = (seed * 1664525 + 1013904223) % 4294967296;
    return seed / 4294967296;
  };
  return Array.from({ length: 110 }, () => ({
    cx: +(rand() * 1200).toFixed(1),
    cy: +(rand() * 760).toFixed(1),
    r: +(rand() * 1.1 + 0.4).toFixed(2),
    o: +(rand() * 0.3 + 0.07).toFixed(2),
    dur: +(rand() * 5 + 3.5).toFixed(2),
    delay: +(rand() * 6).toFixed(2),
  }));
})();

/* ═══════════════════════════════════════════════════════════════════════════
   ORBIT FIELD
   One motif, not five: concentric rings centred behind the headline, with
   three arc segments revolving at different rates. Colours come from the
   brand ramp, which is theme-stable, so this canvas stays dark regardless of
   the app's light/dark setting.
   ═══════════════════════════════════════════════════════════════════════════ */
function OrbitField() {
  const RINGS = [150, 240, 330, 430, 540, 660];
  return (
    <svg
      className="lp-orbit"
      viewBox="0 0 1200 760"
      preserveAspectRatio="xMidYMid slice"
      aria-hidden="true"
    >
      <defs>
        <radialGradient id="lp-core" cx="50%" cy="46%" r="50%">
          <stop offset="0%" stopColor="var(--brand-blue)" stopOpacity="0.34" />
          <stop offset="38%" stopColor="var(--brand-purple)" stopOpacity="0.16" />
          <stop offset="100%" stopColor="var(--brand-purple)" stopOpacity="0" />
        </radialGradient>
      </defs>

      <rect width="1200" height="760" fill="url(#lp-core)" />

      {/* Drifting, twinkling particle field */}
      <g className="lp-drift">
        {STARS.map((s, i) => (
          <circle
            key={i} cx={s.cx} cy={s.cy} r={s.r} fill="#dce9f7"
            className="lp-star"
            style={{
              ['--o' as string]: s.o,
              animationDuration: `${s.dur}s`,
              animationDelay: `${s.delay}s`,
            }}
          />
        ))}
      </g>

      {/* Static rings */}
      <g fill="none" stroke="#9ac4eb" strokeOpacity="0.1" strokeWidth="1">
        {RINGS.map((r) => <circle key={r} cx="600" cy="350" r={r} />)}
      </g>

      {/* Revolving arcs, each led by a particle. A dash on an SVG circle starts
          at 3 o'clock and runs clockwise, so the particle is placed at arc
          length `len` around from there — otherwise it floats off the stroke
          and reads as a stray dot. Rotation pivots on the shared ring centre in
          view-box units, so a group's bounding box never shifts it. */}
      {[
        { cls: 'lp-arc-1', r: 240, stroke: 'var(--primary-300)', op: 0.6, w: 1.5, len: 210 },
        { cls: 'lp-arc-2', r: 330, stroke: 'var(--secondary-400)', op: 0.5, w: 1.5, len: 150 },
        { cls: 'lp-arc-3', r: 540, stroke: 'var(--primary-400)', op: 0.32, w: 1, len: 300 },
      ].map(({ cls, r, stroke, op, w, len }) => {
        const a = len / r;
        const px = +(600 + r * Math.cos(a)).toFixed(2);
        const py = +(350 + r * Math.sin(a)).toFixed(2);
        return (
          <g key={cls} className={`lp-arc ${cls}`}>
            <circle
              cx="600" cy="350" r={r} fill="none" strokeLinecap="round"
              stroke={stroke} strokeOpacity={op} strokeWidth={w}
              strokeDasharray={`${len} ${2 * Math.PI * r}`}
            />
            <circle cx={px} cy={py} r="9" fill={stroke} opacity="0.14" />
            <circle cx={px} cy={py} r="2.8" fill={stroke} opacity="0.95" />
          </g>
        );
      })}
    </svg>
  );
}

export default function LandingPage() {
  const [showPresentation, setShowPresentation] = useState(false);
  const navigate = useNavigate();
  const { isAuthenticated, user } = useAuth();

  useEffect(() => {
    if (isAuthenticated && user) navigate(ROLE_ROUTES[user.role] || '/ceo-dashboard', { replace: true });
  }, [isAuthenticated, user, navigate]);

  return (
    <>
      <style>{`
/* The landing owns its canvas: a dark stage built from the neutral ramp, which
   does not flip with the app theme. */
.lp-root{--lp-bg:#050912;--lp-panel:rgba(255,255,255,.04);
  --lp-line:rgba(154,196,235,.14);--lp-fg:#f4f8fc;--lp-fg-2:rgba(217,233,247,.74);
  --lp-fg-3:rgba(217,233,247,.5);
  position:relative;min-height:100vh;display:flex;flex-direction:column;
  background:var(--lp-bg);color:var(--lp-fg)}

.lp-stage{position:relative;overflow:hidden}
.lp-orbit{position:absolute;top:0;left:50%;transform:translateX(-50%);
  width:min(1500px,150vw);height:100%;pointer-events:none;z-index:0}

@keyframes lp-rev{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}
.lp-arc{transform-box:view-box;transform-origin:600px 350px;
  animation:lp-rev linear infinite}
.lp-arc-1{animation-duration:34s}
.lp-arc-2{animation-duration:46s;animation-direction:reverse}
.lp-arc-3{animation-duration:64s}

/* Particles: a slow parallax drift across the field, with each mark breathing
   on its own clock so the field never pulses in unison. */
@keyframes lp-twinkle{0%,100%{opacity:var(--o)}50%{opacity:calc(var(--o) * 3)}}
.lp-star{opacity:var(--o);animation:lp-twinkle ease-in-out infinite}
@keyframes lp-driftxy{0%,100%{transform:translate3d(0,0,0)}50%{transform:translate3d(-18px,-12px,0)}}
.lp-drift{animation:lp-driftxy 42s ease-in-out infinite}

/* The horizon line that closes the stage off from the sections below. */
.lp-stage::after{content:'';position:absolute;left:0;right:0;bottom:0;height:1px;
  background:linear-gradient(90deg,transparent,var(--lp-line) 22%,var(--lp-line) 78%,transparent)}

.lp-pill{display:inline-flex;align-items:center;gap:8px;padding:6px 14px;border-radius:999px;
  background:var(--lp-panel);border:1px solid var(--lp-line);
  font-size:12px;font-weight:500;color:var(--lp-fg-2)}
.lp-pill-dot{width:5px;height:5px;border-radius:50%;background:var(--primary-400);
  box-shadow:0 0 8px var(--primary-400)}

/* One luminous accent, not a three-stop ramp: against near-black, a gradient
   that travels into purple and pink loses contrast exactly where the sentence
   needs to land. The brand ramp still carries the wordmark. */
.lp-title{color:var(--primary-300);
  text-shadow:0 0 60px rgba(67,167,221,.28)}

.lp-cta{box-shadow:0 8px 32px -8px rgba(11,116,177,.65)}
.lp-cta:hover{box-shadow:0 10px 38px -8px rgba(11,116,177,.8)}

@media(prefers-reduced-motion:reduce){
  .lp-arc,.lp-star,.lp-drift{animation:none}
}
      `}</style>

      <div className="lp-root">

        {/* ── Top bar ── */}
        <header className="relative z-20 border-b" style={{ borderColor: 'var(--lp-line)' }}>
          <div className="mx-auto flex h-14 w-full max-w-[1180px] items-center justify-between px-6">
            <div className="flex items-baseline gap-2">
              <span className="bg-gradient-to-r from-brand-blue via-brand-purple to-brand-pink bg-clip-text text-[19px] font-black uppercase leading-none tracking-tighter text-transparent">
                Akasha
              </span>
              <span className="hidden text-[9px] font-bold uppercase tracking-[0.22em] sm:inline" style={{ color: 'var(--lp-fg-3)' }}>
                Execution Platform
              </span>
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={() => setShowPresentation(true)}
                className="rounded-lg px-2.5 py-1.5 text-[12px] font-semibold transition-colors hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-400"
                style={{ color: 'var(--lp-fg-2)' }}
              >
                Documentation
              </button>
              <button
                onClick={() => navigate('/login')}
                className="rounded-lg bg-primary-500 px-3.5 py-1.5 text-[12px] font-semibold text-white transition-colors hover:bg-primary-400 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-400"
              >
                Sign in
              </button>
            </div>
          </div>
        </header>

        {/* ── Hero stage ── */}
        <section className="lp-stage flex-1">
          <OrbitField />

          <div className="relative z-10 mx-auto w-full max-w-[1180px] px-6 pb-16 pt-16 text-center md:pt-20">
            <span className="lp-pill">
              <span className="lp-pill-dot" />
              Cross-platform intelligence · Adani Green Energy
            </span>

            <p className="mt-7 text-[13px] font-semibold uppercase tracking-[0.16em]" style={{ color: 'var(--lp-fg-3)' }}>
              Akasha Execution Platform
            </p>

            <h1 className="lp-title mx-auto mt-4 max-w-[15ch] text-[clamp(40px,5.8vw,70px)] font-bold leading-[1.04] tracking-[-0.028em]">
              One project truth across every system
            </h1>

            <p className="mt-5 text-[18px] font-semibold md:text-[20px]" style={{ color: 'var(--lp-fg)' }}>
              Eight systems. One identity.
            </p>

            <p className="mx-auto mt-3.5 max-w-[620px] text-[14px] leading-relaxed md:text-[15px]" style={{ color: 'var(--lp-fg-2)' }}>
              Schedule, procurement, materials, quality, transmission and invoicing —
              joined against a single canonical project record, so portfolio reporting
              reconciles instead of contradicting itself.
            </p>

            <div className="mt-9 flex justify-center">
              <button
                onClick={() => navigate('/login')}
                className="lp-cta group flex items-center gap-2.5 rounded-xl bg-primary-500 px-7 py-3.5 text-[15px] font-bold text-white transition-colors hover:bg-primary-400 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-400 focus-visible:ring-offset-0"
              >
                Sign in to the platform
                <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
              </button>
            </div>

            {/* Pillars */}
            <ul className="mx-auto mt-16 grid max-w-[940px] grid-cols-1 gap-4 text-left sm:grid-cols-3">
              {PILLARS.map(({ icon: Icon, name, detail }) => (
                <li
                  key={name}
                  className="rounded-xl border p-5"
                  style={{ borderColor: 'var(--lp-line)', background: 'var(--lp-panel)' }}
                >
                  <span
                    className="inline-flex h-8 w-8 items-center justify-center rounded-lg border"
                    style={{ borderColor: 'var(--lp-line)' }}
                  >
                    <Icon className="h-4 w-4 text-primary-400" strokeWidth={1.75} />
                  </span>
                  <p className="mt-3.5 text-[14px] font-bold" style={{ color: 'var(--lp-fg)' }}>{name}</p>
                  <p className="mt-1.5 text-[12.5px] leading-relaxed" style={{ color: 'var(--lp-fg-3)' }}>
                    {detail}
                  </p>
                </li>
              ))}
            </ul>
          </div>
        </section>

        {/* ── Modules ── */}
        <section className="relative z-10 mx-auto w-full max-w-[1180px] px-6 py-20">
          <h2 className="text-[11px] font-bold uppercase tracking-[0.14em]" style={{ color: 'var(--lp-fg-3)' }}>
            Modules
          </h2>
          <ul className="mt-6 grid grid-cols-1 gap-px overflow-hidden rounded-xl sm:grid-cols-2 lg:grid-cols-4"
            style={{ background: 'var(--lp-line)' }}>
            {MODULES.map(({ name, detail, icon: Icon }) => (
              <li key={name} className="p-5" style={{ background: 'var(--lp-bg)' }}>
                <Icon className="h-4 w-4 text-primary-400" strokeWidth={1.75} />
                <p className="mt-3 text-[13px] font-semibold" style={{ color: 'var(--lp-fg)' }}>{name}</p>
                <p className="mt-1 text-[12px] leading-relaxed" style={{ color: 'var(--lp-fg-3)' }}>{detail}</p>
              </li>
            ))}
          </ul>
        </section>

        {/* ── Footer ── */}
        <footer className="relative z-10 border-t" style={{ borderColor: 'var(--lp-line)' }}>
          <div className="mx-auto flex w-full max-w-[1180px] flex-wrap items-center justify-between gap-2 px-6 py-6">
            <p className="text-[11px]" style={{ color: 'var(--lp-fg-3)' }}>
              Akasha Execution Platform — Adani Green Energy Limited
            </p>
            <p className="text-[11px]" style={{ color: 'var(--lp-fg-3)' }}>Internal use only</p>
          </div>
        </footer>

        <PresentationModal isOpen={showPresentation} onClose={() => setShowPresentation(false)} totalSlides={10} />
      </div>
    </>
  );
}
