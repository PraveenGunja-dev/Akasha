import { useState, useEffect, useRef } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { Lock, Mail, X, ArrowRight, Eye, EyeOff, Loader2, AlertTriangle, User } from "lucide-react";
import PresentationModal from "../components/ui/PresentationModal";
import { useAuth } from "../context/AuthContext";
import { useTheme } from '../hooks/useTheme';

const ROLE_ROUTES: Record<string, string> = {
  executive: '/ceo-dashboard',
  pmag: '/pmag',
  projects: '/projects',
  tc_ordering: '/tc-ordering',
  tc_stores: '/tc-stores',
};

/* ═══════════════════════════════════════════════════════════════════════════
   STARFIELD — twinkling dots
   ═══════════════════════════════════════════════════════════════════════════ */
function Starfield({ isDark }: { isDark: boolean }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const c = ref.current;
    if (!c) return;
    const ctx = c.getContext("2d")!;
    let id: number;
    const stars: { x: number; y: number; r: number; o: number; p: number; s: number }[] = [];
    const resize = () => { c.width = innerWidth; c.height = innerHeight; };
    resize();
    addEventListener("resize", resize);
    for (let i = 0; i < 260; i++)
      stars.push({ x: Math.random() * c.width, y: Math.random() * c.height, r: Math.random() * 1.2 + 0.2, o: Math.random() * 0.5 + 0.1, p: Math.random() * 6.28, s: Math.random() * 0.006 + 0.002 });
    const draw = () => {
      ctx.clearRect(0, 0, c.width, c.height);
      for (const s of stars) {
        s.p += s.s;
        const a = s.o * (0.5 + 0.5 * Math.sin(s.p));
        ctx.beginPath();
        ctx.arc(s.x, s.y, s.r, 0, 6.28);
        ctx.fillStyle = isDark ? `rgba(226,240,252,${a})` : `rgba(11,116,177,${a * 0.16})`;
        ctx.fill();
      }
      id = requestAnimationFrame(draw);
    };
    draw();
    return () => { cancelAnimationFrame(id); removeEventListener("resize", resize); };
  }, [isDark]);
  return <canvas ref={ref} style={{ position: "absolute", inset: 0, zIndex: 0, pointerEvents: "none" }} />;
}

/* ═══════════════════════════════════════════════════════════════════════════ */

/* Floating bokeh squares - size, top, left, delay, duration, blur */
const SQUARES = [
  { s: 56, t: '7%',  l: '3%',  d: '0s',   u: '15s', b: 0 },
  { s: 34, t: '4%',  l: '9%',  d: '2.4s', u: '18s', b: 1 },
  { s: 78, t: '11%', l: '20%', d: '4.1s', u: '17s', b: 2 },
  { s: 44, t: '5%',  l: '46%', d: '1.1s', u: '14s', b: 0 },
  { s: 30, t: '15%', l: '57%', d: '3.3s', u: '19s', b: 1 },
  { s: 64, t: '8%',  l: '70%', d: '5.2s', u: '16s', b: 0 },
  { s: 40, t: '3%',  l: '86%', d: '6.4s', u: '20s', b: 2 },
  { s: 52, t: '34%', l: '8%',  d: '2.9s', u: '21s', b: 1 },
  { s: 26, t: '44%', l: '93%', d: '4.8s', u: '17s', b: 0 },
  { s: 70, t: '54%', l: '77%', d: '1.7s', u: '22s', b: 3 },
  { s: 36, t: '62%', l: '14%', d: '5.9s', u: '18s', b: 2 },
  { s: 46, t: '72%', l: '88%', d: '3.6s', u: '20s', b: 1 },
  { s: 28, t: '78%', l: '30%', d: '0.8s', u: '16s', b: 0 },
];

export default function LandingPage() {
  const [theme, setTheme] = useTheme();
  const [showPresentation, setShowPresentation] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  // /login is this page with the sign-in panel open (protected pages send
  // people here, and back to where they were going afterwards).
  const [showLogin, setShowLogin] = useState(location.pathname === '/login');
  const from = (location.state as { from?: string } | null)?.from;
  const { isAuthenticated, user, login } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [loginError, setLoginError] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (location.pathname === '/login') setShowLogin(true); }, [location.pathname]);
  const closeLogin = () => {
    setShowLogin(false);
    setLoginError('');
    if (location.pathname === '/login') navigate('/', { replace: true });
  };
  const submitLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoginError('');
    setBusy(true);
    const r = await login(username.trim(), password);
    setBusy(false);
    if (!r.success) setLoginError(r.message);
  };
  const isDark = theme === "dark";

  useEffect(() => {
  }, [isDark]);

  useEffect(() => {
    if (isAuthenticated && user) navigate(from || ROLE_ROUTES[user.role] || '/ceo-dashboard', { replace: true });
  }, [isAuthenticated, user, navigate, from]);

  return (
    <>
      <style>{`
/* ══════════ ADANI BRAND RAMP ══════════
   blue #0b74b1 · purple #75479c · magenta #bc3860 — the only hues on this page. */
.lp{--ad-blue:#0b74b1;--ad-blue-lt:#4aa3dd;--ad-purple:#75479c;--ad-magenta:#bc3860;
  --ad-grad:linear-gradient(100deg,#4aa3dd 0%,#0b74b1 24%,#75479c 58%,#bc3860 88%)}

/* ══════════ ROOT ══════════ */
.lp{position:relative;width:100%;min-height:100vh;overflow:hidden;font-family:"Adani",system-ui,sans-serif;transition:background .7s ease,color .5s}
/* Sign-in open: one page. The background keeps the full width; the hero
   moves into the left part and the sign-in form sits on the same background
   on the right - no second surface, no seam. */
.lp-hero,.lp-foot,.lp-topbar{transition:padding .6s cubic-bezier(.22,1,.36,1)}
.lp-brand,.lp-title{transition:font-size .6s cubic-bezier(.22,1,.36,1),color .5s}
.lp-cta{transition:opacity .3s ease,transform .3s ease,background-position .4s ease,box-shadow .3s ease}
.lp-open .lp-cta{opacity:0;transform:translateY(6px);pointer-events:none}
@media(min-width:1024px){
  .lp-open .lp-hero{padding-left:48px;padding-right:calc(42vw + 24px)}
  .lp-open .lp-foot{z-index:210}   /* stays bottom-right, above the sign-in side */
  .lp-open .lp-topbar{padding-right:calc(42vw + 40px)}
  .lp-open .lp-brand{font-size:clamp(3.2rem,6.6vw,6.4rem)}
  .lp-open .lp-title{font-size:clamp(1.25rem,1.9vw,1.85rem)}
}
.lp.dk{background:radial-gradient(ellipse 100% 74% at 50% 122%,#173163 0%,#0d1a3a 34%,#070c1c 64%,#03050d 100%);color:#fff}
.lp.lt{background:radial-gradient(ellipse 104% 66% at 50% 126%,#e4edf9 0%,#f4f8fd 32%,#fff 62%,#fff 100%);color:#0f172a}

/* ══════════ NEBULA — slow drifting deep-space colour ══════════ */
.lp-neb{position:absolute;border-radius:50%;z-index:0;pointer-events:none;filter:blur(90px)}
.lp-neb.a{width:52vw;height:42vh;left:-8vw;top:6vh;animation:drift1 26s ease-in-out infinite}
.lp-neb.b{width:46vw;height:38vh;right:-6vw;top:22vh;animation:drift2 32s ease-in-out infinite}
.dk .lp-neb.a{background:radial-gradient(circle at 50% 50%,rgba(117,71,156,.24),transparent 68%)}
.dk .lp-neb.b{background:radial-gradient(circle at 50% 50%,rgba(11,116,177,.22),transparent 68%)}
.lt .lp-neb.a{background:radial-gradient(circle at 50% 50%,rgba(117,71,156,.055),transparent 68%)}
.lt .lp-neb.b{background:radial-gradient(circle at 50% 50%,rgba(11,116,177,.06),transparent 68%)}
@keyframes drift1{0%,100%{transform:translate3d(0,0,0)}50%{transform:translate3d(40px,-30px,0)}}
@keyframes drift2{0%,100%{transform:translate3d(0,0,0)}50%{transform:translate3d(-46px,26px,0)}}

/* ══════════ GRID ══════════ */
.lp-grid{position:absolute;inset:0;z-index:1;pointer-events:none;background-size:80px 80px;
  mask-image:radial-gradient(ellipse 62% 58% at 50% 38%,#000 8%,transparent 74%);
  -webkit-mask-image:radial-gradient(ellipse 62% 58% at 50% 38%,#000 8%,transparent 74%)}
.dk .lp-grid{background-image:linear-gradient(rgba(154,196,235,.045) 1px,transparent 1px),linear-gradient(90deg,rgba(154,196,235,.045) 1px,transparent 1px)}
.lt .lp-grid{background-image:linear-gradient(rgba(11,116,177,.04) 1px,transparent 1px),linear-gradient(90deg,rgba(11,116,177,.04) 1px,transparent 1px)}

/* ══════════ FLOATING SQUARES ══════════ */
.lp-sq-layer{position:absolute;inset:0;z-index:1;pointer-events:none;overflow:hidden}
.lp-sq{position:absolute;border-radius:6px;pointer-events:none;
  animation:sqf var(--dur,16s) ease-in-out infinite;animation-delay:var(--delay,0s);
  filter:blur(var(--blur,0px));transition:background .6s,border-color .6s,box-shadow .6s}
.dk .lp-sq{background:linear-gradient(140deg,rgba(74,163,221,.10),rgba(117,71,156,.03));border:1px solid rgba(74,163,221,.16);box-shadow:0 0 30px rgba(11,116,177,.10)}
.lt .lp-sq{background:linear-gradient(140deg,rgba(11,116,177,.045),rgba(117,71,156,.015));border:1px solid rgba(11,116,177,.12);box-shadow:0 0 30px rgba(11,116,177,.04)}
@keyframes sqf{
  0%,100%{transform:translate3d(0,0,0) rotate(0deg);opacity:.22}
  50%{transform:translate3d(8px,-30px,0) rotate(4deg);opacity:.95}}

/* ══════════ HORIZON AURA ══════════ */
.lp-aura{position:absolute;left:50%;bottom:-26vh;transform:translateX(-50%);width:132vw;height:76vh;
  border-radius:50%;z-index:1;pointer-events:none;filter:blur(44px);animation:aurab 9s ease-in-out infinite}
.dk .lp-aura{background:radial-gradient(ellipse at center,rgba(117,71,156,.30) 0%,rgba(11,116,177,.16) 38%,rgba(188,56,96,.06) 58%,transparent 74%)}
.lt .lp-aura{background:radial-gradient(ellipse at center,rgba(117,71,156,.11) 0%,rgba(11,116,177,.06) 40%,transparent 72%)}
@keyframes aurab{0%,100%{opacity:.75}50%{opacity:1}}

/* ══════════ PLANET HORIZON — crest at ~72vh ══════════ */
.lp-planet{position:absolute;left:50%;bottom:-118vh;transform:translateX(-50%);
  width:280vw;height:140vh;border-radius:50%;z-index:2;pointer-events:none;
  transition:border-color .7s,box-shadow .7s,background .7s}
.dk .lp-planet{
  border-top:2px solid rgba(138,96,190,.85);
  background:radial-gradient(ellipse 44% 24% at 50% 0%,rgba(117,71,156,.16),transparent 62%);
  box-shadow:
    0 -8px 30px rgba(74,163,221,.34),
    0 -32px 100px rgba(117,71,156,.22),
    0 -76px 210px rgba(188,56,96,.10)}
.lt .lp-planet{
  border-top:2px solid rgba(117,71,156,.45);
  background:radial-gradient(ellipse 44% 24% at 50% 0%,rgba(117,71,156,.07),transparent 62%);
  box-shadow:
    0 -8px 30px rgba(11,116,177,.15),
    0 -32px 100px rgba(117,71,156,.09),
    0 -76px 210px rgba(188,56,96,.04)}

/* ══════════ TOP BAR — theme toggle only ══════════ */
.lp-topbar{position:absolute;top:0;left:0;right:0;z-index:50;display:flex;justify-content:flex-end;padding:26px 40px}
.lp-theme{width:42px;height:42px;display:flex;align-items:center;justify-content:center;border-radius:50%;
  cursor:pointer;font-size:16px;font-family:inherit;backdrop-filter:blur(8px);
  transition:background .25s,border-color .25s,color .25s,transform .35s}
.dk .lp-theme{background:rgba(74,163,221,.07);border:1px solid rgba(154,196,235,.18);color:rgba(222,236,248,.7)}
.dk .lp-theme:hover{background:rgba(74,163,221,.16);border-color:rgba(117,71,156,.6);color:#fff;transform:rotate(18deg)}
.lt .lp-theme{background:rgba(255,255,255,.8);border:1px solid rgba(11,116,177,.18);color:rgba(15,23,42,.55)}
.lt .lp-theme:hover{border-color:rgba(117,71,156,.45);color:#75479c;transform:rotate(18deg)}

/* ══════════ HERO ══════════ */
.lp-hero{position:absolute;inset:0;z-index:10;display:flex;align-items:center;padding:0 40px;margin-top:-70px}
.lp-hero-inner{display:flex;flex-direction:column;align-items:center;text-align:center;width:100%;max-width:980px;margin:0 auto}
.lp-rise{animation:rise .9s cubic-bezier(.16,1,.3,1) both}
@keyframes rise{from{opacity:0;transform:translateY(24px)}to{opacity:1;transform:none}}

/* Pill */
.lp-pill{display:inline-flex;align-items:center;gap:10px;padding:8px 20px;border-radius:999px;font-size:13px;font-weight:500;letter-spacing:.03em;margin-bottom:38px;transition:all .5s}
.dk .lp-pill{background:rgba(74,163,221,.07);border:1px solid rgba(117,71,156,.3);color:rgba(222,236,248,.65)}
.lt .lp-pill{background:rgba(11,116,177,.05);border:1px solid rgba(11,116,177,.18);color:rgba(10,93,143,.8)}
.lp-pill-dot{width:6px;height:6px;border-radius:50%;background:var(--ad-blue-lt);box-shadow:0 0 10px rgba(74,163,221,.9);animation:pdot 2s ease-in-out infinite}
@keyframes pdot{0%,100%{opacity:.45;transform:scale(1)}50%{opacity:1;transform:scale(1.4)}}
.lp-pill-sep{display:inline-block;width:1px;height:14px;margin:0 2px;transition:background .5s}
.dk .lp-pill-sep{background:rgba(154,196,235,.22)}
.lt .lp-pill-sep{background:rgba(11,116,177,.22)}

/* Akasha brand mark */
.lp-brand{position:relative;display:inline-block;line-height:1;margin:0 0 26px;
  font-size:clamp(3.6rem,11vw,10rem);font-weight:900;letter-spacing:-.02em}
.lp-brand::after{content:'';position:absolute;left:50%;top:52%;transform:translate(-50%,-50%);
  width:155%;height:215%;z-index:0;pointer-events:none;filter:blur(52px);border-radius:50%;
  background:radial-gradient(ellipse at center,rgba(117,71,156,.32) 0%,rgba(11,116,177,.15) 42%,transparent 72%);
  animation:halo 7s ease-in-out infinite}
.lt .lp-brand::after{background:radial-gradient(ellipse at center,rgba(117,71,156,.11) 0%,rgba(11,116,177,.06) 42%,transparent 72%)}
@keyframes halo{0%,100%{opacity:.7;transform:translate(-50%,-50%) scale(1)}50%{opacity:1;transform:translate(-50%,-50%) scale(1.06)}}

.lp-brand-txt,.lp-brand-glow{
  background:var(--ad-grad);
  -webkit-background-clip:text;background-clip:text;color:transparent;
  -webkit-text-fill-color:transparent}
.lp-brand-txt{position:relative;z-index:2;display:block}
.lp-brand-glow{position:absolute;inset:0;z-index:1;pointer-events:none;user-select:none;
  filter:blur(28px);opacity:.9;animation:brandPulse 7s ease-in-out infinite}
.lt .lp-brand-glow{filter:blur(18px);opacity:.32}
@keyframes brandPulse{0%,100%{opacity:.6}50%{opacity:1}}

/* Supporting line */
.lp-title{font-size:clamp(1.5rem,3vw,2.5rem);font-weight:600;line-height:1.25;letter-spacing:-.015em;margin:0 0 26px;transition:color .5s}
.dk .lp-title{color:rgba(255,255,255,.92)}
.lt .lp-title{color:rgba(15,23,42,.88)}

/* Copy + action */
.lp-desc{font-size:16px;line-height:1.8;font-weight:400;max-width:660px;margin:0 auto 40px;transition:color .5s}
.dk .lp-desc{color:rgba(214,231,246,.45)}
.lt .lp-desc{color:rgba(15,23,42,.52)}
.lp-actions{display:flex;align-items:center;justify-content:center;gap:14px;flex-wrap:wrap}

/* Get Started — the single solid CTA, full Adani ramp */
.lp-cta{position:relative;overflow:hidden;display:inline-flex;align-items:center;gap:10px;padding:15px 36px;border-radius:12px;font-size:15px;font-weight:600;border:none;cursor:pointer;color:#fff;
  background:var(--ad-grad);background-size:160% 100%;background-position:0% 50%;
  transition:background-position .6s ease,box-shadow .3s,transform .3s;font-family:inherit}
.dk .lp-cta{box-shadow:0 6px 28px rgba(117,71,156,.42)}
.lt .lp-cta{box-shadow:0 6px 22px rgba(117,71,156,.28)}
.lp-cta:hover{background-position:100% 50%;transform:translateY(-2px)}
.dk .lp-cta:hover{box-shadow:0 10px 44px rgba(117,71,156,.6)}
.lt .lp-cta:hover{box-shadow:0 10px 34px rgba(117,71,156,.42)}
.lp-cta-arrow{transition:transform .3s}
.lp-cta:hover .lp-cta-arrow{transform:translateX(4px)}

/* Login — the previous link treatment, now sitting beside Get Started */
.lp-login{position:relative;display:inline-flex;align-items:center;padding:8px 6px;margin-left:8px;
  background:none;border:none;font-family:inherit;font-size:15px;font-weight:600;letter-spacing:.01em;
  cursor:pointer;transition:color .25s}
.lp-login::after{content:'';position:absolute;left:6px;right:6px;bottom:3px;height:1.5px;border-radius:2px;
  background:var(--ad-grad);transform:scaleX(0);transform-origin:left;transition:transform .3s cubic-bezier(.16,1,.3,1)}
.lp-login:hover::after{transform:scaleX(1)}
.dk .lp-login{color:#7db9e4}
.dk .lp-login:hover{color:#fff}
.lt .lp-login{color:#0a5d8f}
.lt .lp-login:hover{color:#75479c}

/* ══════════ FOOTER — Documentation lives down here now ══════════ */
.lp-foot{position:absolute;left:0;right:0;bottom:34px;z-index:20;display:flex;justify-content:flex-end;padding-right:48px}
.lp-foot-link{position:relative;display:inline-flex;align-items:center;gap:8px;padding:8px 4px;
  background:none;border:none;font-family:inherit;font-size:14px;font-weight:500;letter-spacing:.02em;
  cursor:pointer;transition:color .25s}
.lp-foot-link::after{content:'';position:absolute;left:0;right:0;bottom:2px;height:1.5px;border-radius:2px;
  background:var(--ad-grad);transform:scaleX(0);transform-origin:left;transition:transform .3s cubic-bezier(.16,1,.3,1)}
.lp-foot-link:hover::after{transform:scaleX(1)}
.dk .lp-foot-link{color:rgba(214,231,246,.5)}
.dk .lp-foot-link:hover{color:#fff}
.lt .lp-foot-link{color:rgba(15,23,42,.5)}
.lt .lp-foot-link:hover{color:#0a5d8f}

@media(prefers-reduced-motion:reduce){
  .lp-sq,.lp-aura,.lp-neb,.lp-rise,.lp-pill-dot,.lp-brand::after,.lp-brand-glow{animation:none}
}

/* ══════════ RESPONSIVE ══════════ */
@media(max-width:900px){
  .lp-desc{font-size:15px}
  .lp-brand-glow{filter:blur(16px)}
  .lp-hero,.lp-topbar{padding-left:24px;padding-right:24px}
  .lp-hero{margin-top:-20px}
  .lp-pill{margin-bottom:26px}
  .lp-actions{flex-direction:column;width:100%}
  .lp-cta{width:100%;max-width:300px;justify-content:center}
  .lp-login{margin-left:0}
  .lp-foot{bottom:24px;padding-right:24px}
  .lp-planet{bottom:-124vh;width:400vw}
}
      `}</style>

      <div className={`lp ${isDark ? 'dk' : 'lt'} ${showLogin ? 'lp-open' : ''}`}>
        {/* Background layers */}
        <Starfield isDark={isDark} />
        <div className="lp-grid" />

        {/* Floating squares - spread across the field for depth */}
        <div className="lp-sq-layer">
          {SQUARES.map((q, i) => (
            <div
              key={i}
              className="lp-sq"
              style={{
                width: q.s, height: q.s, top: q.t, left: q.l,
                '--dur': q.u,
                '--delay': q.d,
                '--blur': q.b + 'px',
              } as React.CSSProperties}
            />
          ))}
        </div>

        {/* Nebula + horizon aura */}
        <div className="lp-neb a" />
        <div className="lp-neb b" />
        <div className="lp-aura" />

        {/* Planet arc */}
        <div className="lp-planet" />

        {/* ── Top bar — theme toggle only; moves into the sign-in header while that is open ── */}
        {!showLogin && (
          <div className="lp-topbar">
            <button className="lp-theme" onClick={() => setTheme(isDark ? 'light' : 'dark')} title="Toggle theme">
              {isDark ? '☀' : '☾'}
            </button>
          </div>
        )}

        {/* ── Hero — centred stack ── */}
        <div className="lp-hero">
          <div className="lp-hero-inner">
            <div className="lp-pill lp-rise">
              <span className="lp-pill-dot" />
              Akasha Platform
              <span className="lp-pill-sep" />
              Unified Intelligence
            </div>

            {/* Glowing Akasha brand mark */}
            <h1 className="lp-brand lp-rise" style={{ animationDelay: '.08s' }}>
              <span className="lp-brand-glow" aria-hidden="true">Akasha</span>
              <span className="lp-brand-txt">Akasha</span>
            </h1>

            <p className="lp-title lp-rise" style={{ animationDelay: '.16s' }}>
              The future of renewable energy intelligence.
            </p>

            <p className="lp-desc lp-rise" style={{ animationDelay: '.22s' }}>
              Cross-platform analytics engine that joins eight enterprise systems against
              one canonical project identity. Dashboards, intelligence, and AI copilot — on one screen.
            </p>

            <div className="lp-actions lp-rise" style={{ animationDelay: '.28s' }}>
              <button className="lp-cta" onClick={() => setShowLogin(true)}>
                Get Started
                <ArrowRight size={18} className="lp-cta-arrow" />
              </button>
            </div>
          </div>
        </div>

        {/* ── Footer — Documentation ── */}
        <div className="lp-foot">
          <button className="lp-foot-link" onClick={() => setShowPresentation(true)}>
            Documentation
            <ArrowRight size={14} />
          </button>
        </div>

        {/* ── Presentation Modal ── */}
        <PresentationModal isOpen={showPresentation} onClose={() => setShowPresentation(false)} totalSlides={10} />

        {/* ── Sign-in panel: slides in on the right while the landing page
             narrows to the left and keeps running beside it (desktop); covers
             the screen on small displays. ── */}
        <AnimatePresence>
          {showLogin && (
            <motion.aside key="login" role="dialog" aria-modal="false" aria-labelledby="signin-title"
              className={`fixed inset-y-0 right-0 z-[200] flex w-full flex-col overflow-y-auto lg:w-[42vw]
                          ${isDark ? 'text-white max-lg:bg-[#070c1c]' : 'text-slate-900 max-lg:bg-white'}`}
              initial={{ x: 48, opacity: 0 }} animate={{ x: 0, opacity: 1 }} exit={{ x: 48, opacity: 0 }}
              transition={{ duration: 0.55, ease: [0.22, 1, 0.36, 1] }}
              onKeyDown={(e) => { if (e.key === 'Escape') closeLogin(); }}>

              {/* Header: close, then theme toggle last */}
              <header className="flex shrink-0 items-center justify-end gap-3 px-8 pt-7 sm:px-12">
                <button type="button" onClick={closeLogin} aria-label="Close sign-in"
                  className={`rounded-full p-2 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#4aa3dd]/50
                              ${isDark ? 'text-white/40 hover:bg-white/10 hover:text-white' : 'text-slate-400 hover:bg-slate-100 hover:text-slate-700'}`}>
                  <X className="h-5 w-5" />
                </button>
                <button className="lp-theme" onClick={() => setTheme(isDark ? 'light' : 'dark')} title="Toggle theme">
                  {isDark ? '☀' : '☾'}
                </button>
              </header>

              {/* Form, centred in the remaining height */}
              <div className="flex flex-1 items-center px-8 py-10 sm:px-12">
                <motion.div className="mx-auto w-full max-w-[380px]"
                  initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
                  transition={{ duration: 0.45, delay: 0.2, ease: 'easeOut' }}>
                  <p className={`text-[12px] font-semibold uppercase tracking-[0.14em] ${isDark ? 'text-[#4aa3dd]' : 'text-[#0b74b1]'}`}>Welcome back</p>
                  <h2 id="signin-title" className="mt-2 text-[26px] font-semibold leading-tight tracking-tight">Sign in to your account</h2>
                  <p className={`mt-2 text-[14px] ${isDark ? 'text-white/55' : 'text-slate-500'}`}>
                    Use your Adani work username and password.
                  </p>

                  <form onSubmit={submitLogin} className="mt-8 space-y-5" noValidate>
                    {[
                      { id: 'lp-username', label: 'Username', icon: User, type: 'text', value: username, set: setUsername,
                        ph: 'Admin_akasha', auto: 'username' },
                      { id: 'lp-password', label: 'Password', icon: Lock, type: showPw ? 'text' : 'password', value: password,
                        set: setPassword, ph: 'Enter your password', auto: 'current-password' },
                    ].map(({ id, label, icon: Icon, type, value, set, ph, auto }) => (
                      <div key={id}>
                        <label htmlFor={id} className={`mb-2 block text-[13px] font-medium ${isDark ? 'text-white/80' : 'text-slate-700'}`}>{label}</label>
                        <div className="relative">
                          <Icon className={`pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 ${isDark ? 'text-white/35' : 'text-slate-400'}`} />
                          <input id={id} type={type} value={value} onChange={(e) => set(e.target.value)} placeholder={ph}
                            autoComplete={auto} autoFocus={id === 'lp-username'} required aria-invalid={!!loginError}
                            className={`h-11 w-full rounded-xl border pl-10 text-[14px] transition-colors focus:outline-none focus:ring-2
                                        ${id === 'lp-password' ? 'pr-11' : 'pr-3.5'}
                                        ${isDark ? 'border-white/10 bg-white/[0.04] text-white placeholder:text-white/25 hover:border-white/20 focus:border-[#4aa3dd]/70 focus:ring-[#4aa3dd]/20'
                                          : 'border-slate-200 bg-slate-50/60 text-slate-900 placeholder:text-slate-400 hover:border-slate-300 focus:border-[#0b74b1] focus:bg-white focus:ring-[#0b74b1]/15'}`} />
                          {id === 'lp-password' && (
                            <button type="button" onClick={() => setShowPw((v) => !v)} aria-label={showPw ? 'Hide password' : 'Show password'}
                              className={`absolute right-2 top-1/2 -translate-y-1/2 rounded-lg p-2 transition-colors ${isDark ? 'text-white/40 hover:text-white' : 'text-slate-400 hover:text-slate-700'}`}>
                              {showPw ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                            </button>
                          )}
                        </div>
                      </div>
                    ))}

                    <AnimatePresence>
                      {loginError && (
                        <motion.div role="alert" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }}
                          exit={{ opacity: 0, height: 0 }} transition={{ duration: 0.2 }}
                          className="flex items-start gap-2 overflow-hidden rounded-xl border border-[#bc3860]/30 bg-[#bc3860]/10 px-3.5 py-3 text-[13px] text-[#e05a82]">
                          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" /> {loginError}
                        </motion.div>
                      )}
                    </AnimatePresence>

                    <button type="submit" disabled={busy || !email.trim() || !password}
                      className="mt-1 flex h-11 w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-[#0b74b1] to-[#75479c]
                                 text-[14px] font-semibold text-white transition-all hover:shadow-[0_6px_24px_rgba(117,71,156,0.35)]
                                 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:shadow-none
                                 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#4aa3dd]/60 focus-visible:ring-offset-2
                                 focus-visible:ring-offset-transparent">
                      {busy ? <><Loader2 className="h-4 w-4 animate-spin" /> Signing in…</> : <>Sign in <ArrowRight className="h-4 w-4" /></>}
                    </button>
                  </form>

                  <p className={`mt-6 text-[12px] leading-relaxed ${isDark ? 'text-white/40' : 'text-slate-400'}`}>
                    Access is managed by the Akasha team. Contact them if you need an account.
                  </p>
                </motion.div>
              </div>

            </motion.aside>
          )}
        </AnimatePresence>
      </div>
    </>
  );
}
