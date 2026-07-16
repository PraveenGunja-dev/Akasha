import * as THREE from 'three';
import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Moon, Sun, Lock, User, Eye, EyeOff, Loader2, X } from "lucide-react";
import adaniLogo from "../assets/adani-dpr-icon.ico";
import PhotonBeam from "../components/ui/photon-beam";
import PresentationModal from "../components/ui/PresentationModal";
import { useAuth } from "../context/AuthContext";

const ROLE_ROUTES: Record<string, string> = {
  executive: '/dashboard',
  pmag: '/pmag',
  projects: '/projects',
  tc_ordering: '/tc-ordering',
  tc_stores: '/tc-stores',
};

export default function LandingPage() {
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const [showPresentation, setShowPresentation] = useState(false);
  const [showLogin, setShowLogin] = useState(false);
  const navigate = useNavigate();
  const { login, isAuthenticated, user } = useAuth();

  // Login form state
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (theme === "dark") {
      document.documentElement.classList.add("dark");
    } else {
      document.documentElement.classList.remove("dark");
    }
  }, [theme]);

  // If already logged in, redirect to their dashboard
  useEffect(() => {
    if (isAuthenticated && user) {
      navigate(ROLE_ROUTES[user.role] || '/dashboard', { replace: true });
    }
  }, [isAuthenticated, user, navigate]);

  const toggleTheme = () => {
    setTheme(theme === "light" ? "dark" : "light");
  };

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    navigate('/dashboard', { replace: true });
  };

  const openLogin = () => {
    navigate('/dashboard', { replace: true });
  };

  return (
    <div className="relative min-h-screen overflow-hidden bg-background text-foreground transition-colors duration-500">

      {/* Top bar with logo and theme toggle */}
      <div className="absolute top-0 w-full z-50 px-8 py-5 flex items-center justify-between">
        <div className="w-40 h-16 flex items-center justify-center overflow-hidden">
          <img src={adaniLogo} alt="Adani Logo" className="w-full h-full object-contain dark:brightness-110" />
        </div>
        <button
          onClick={toggleTheme}
          className="p-2.5 rounded-full hover:bg-muted transition-colors text-foreground"
        >
          {theme === "light" ? <Moon size={22} /> : <Sun size={22} />}
        </button>
      </div>

      {/* Full-page hero with PhotonBeam background */}
      <div className="relative w-full h-screen overflow-hidden">

        {/* PhotonBeam natively handles Light/Dark mode without any CSS filters */}
        <div className="absolute inset-0 z-0">
          <PhotonBeam
            key={theme}
            colorBg={theme === "light" ? "#f7f7f7" : "#080808"}
            colorLine="#0B74B0"
            useColor2={true}
            useColor3={true}
            colorSignal="#0B74B0"
            colorSignal2="#75479C"
            colorSignal3="#BD3861"
            lineCount={90}
            spreadHeight={120}
            curveLength={120}
            straightLength={0}
            targetId="akasha-title"
            tailThickness={0.2}
            signalCount={94}
            speedGlobal={0.345}
            trailLength={3}
            bloomStrength={theme === "light" ? 0 : 1.5}
            blending={theme === "light" ? THREE.NormalBlending : THREE.AdditiveBlending}
          />
        </div>

        {/* Text on the left side */}
        <div className="absolute inset-0 z-10 flex items-center px-12 lg:px-24">
          <div className="flex flex-col items-start space-y-5 max-w-2xl">
            <p className="text-xl md:text-2xl text-[#0B74B0] font-medium tracking-widest uppercase">
              Welcome to the Unified Workspace
            </p>
            <h1
              id="akasha-title"
              className="text-7xl md:text-[9rem] lg:text-[11rem] font-bold drop-shadow-2xl tracking-tight leading-none bg-[linear-gradient(to_left,#0B74B0,#75479C,#BD3861,#0B74B0,#75479C,#BD3861)] text-transparent bg-clip-text bg-[length:200%_auto] animate-gradient-flow"
              style={{ fontFamily: "Adani, sans-serif", paddingRight: "0.1em" }}
            >
              Akasha
            </h1>
            <p className="text-lg md:text-2xl text-muted-foreground font-light max-w-xl">
              Next-generation project analytics and intelligence platform.
            </p>

            <div className="relative w-full h-0">
              <div className="absolute top-6 left-0 flex items-center gap-6 whitespace-nowrap">
                <button 
                  onClick={openLogin}
                  className="px-6 py-2 bg-[#0B74B0] hover:bg-[#096296] text-white rounded-xl font-medium text-lg transition-all duration-300 shadow-[0_0_20px_rgba(11,116,176,0.4)] hover:shadow-[0_0_30px_rgba(11,116,176,0.6)] hover:-translate-y-1"
                >
                  Login
                </button>
                <button 
                  onClick={() => setShowPresentation(true)}
                  className="px-6 py-2 bg-transparent border border-white/20 hover:border-[#75479C] text-foreground rounded-xl font-medium text-lg transition-all duration-300 hover:bg-white/5 backdrop-blur-sm hover:shadow-[0_0_20px_rgba(117,71,156,0.3)] hover:-translate-y-1 block text-center"
                >
                  Documentation
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
      
      <PresentationModal 
        isOpen={showPresentation} 
        onClose={() => setShowPresentation(false)} 
        totalSlides={10} 
      />

      {/* ─── Login Modal Overlay ─── */}
      {showLogin && (
        <div className="fixed inset-0 z-[200] flex items-center justify-center">
          {/* Backdrop */}
          <div 
            className="absolute inset-0 bg-black/60 backdrop-blur-md animate-in fade-in duration-300"
            onClick={() => setShowLogin(false)}
          />

          {/* Modal Card */}
          <div className="relative z-10 w-full max-w-[420px] mx-4 animate-in zoom-in-95 slide-in-from-bottom-4 duration-300">
            
            {/* Glass Card */}
            <div className="backdrop-blur-2xl bg-white/[0.06] border border-white/[0.1] rounded-[28px] p-8 shadow-2xl shadow-black/40">
              
              {/* Close button */}
              <button 
                onClick={() => setShowLogin(false)}
                className="absolute top-5 right-5 p-2 rounded-full text-white/30 hover:text-white/70 hover:bg-white/10 transition-all"
              >
                <X className="w-5 h-5" />
              </button>

              {/* Header */}
              <div className="mb-7">
                <div className="flex items-center gap-3 mb-4">
                  <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary via-[#75479c] to-accent flex items-center justify-center shadow-lg shadow-primary/30">
                    <Lock className="w-5 h-5 text-white" />
                  </div>
                  <div>
                    <h2 className="text-xl font-bold text-white">Sign In</h2>
                    <p className="text-xs text-white/40 font-medium">Access your Akasha dashboard</p>
                  </div>
                </div>
              </div>

              <form onSubmit={handleLogin} className="space-y-5">
                {/* Username */}
                <div>
                  <label className="block text-[11px] font-semibold text-white/50 uppercase tracking-wider mb-2">Username</label>
                  <div className="relative">
                    <User className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-white/30" />
                    <input
                      type="text"
                      value={username}
                      onChange={e => setUsername(e.target.value)}
                      className="w-full pl-11 pr-4 py-3.5 rounded-xl bg-white/[0.06] border border-white/[0.08] text-white placeholder-white/20 focus:outline-none focus:border-primary/60 focus:bg-white/[0.1] transition-all text-[15px]"
                      placeholder="Enter your username"
                      autoComplete="username"
                      autoFocus
                      required
                    />
                  </div>
                </div>

                {/* Password */}
                <div>
                  <label className="block text-[11px] font-semibold text-white/50 uppercase tracking-wider mb-2">Password</label>
                  <div className="relative">
                    <Lock className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-white/30" />
                    <input
                      type={showPassword ? 'text' : 'password'}
                      value={password}
                      onChange={e => setPassword(e.target.value)}
                      className="w-full pl-11 pr-12 py-3.5 rounded-xl bg-white/[0.06] border border-white/[0.08] text-white placeholder-white/20 focus:outline-none focus:border-primary/60 focus:bg-white/[0.1] transition-all text-[15px]"
                      placeholder="Enter your password"
                      autoComplete="current-password"
                      required
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute right-4 top-1/2 -translate-y-1/2 text-white/30 hover:text-white/60 transition-colors"
                    >
                      {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                </div>

                {/* Error */}
                {error && (
                  <div className="flex items-center gap-2.5 px-4 py-3 rounded-xl bg-destructive/100/10 border border-destructive/20 text-destructive text-sm font-medium animate-in slide-in-from-top-2 duration-200">
                    <div className="w-1.5 h-1.5 rounded-full bg-destructive/100 shrink-0" />
                    {error}
                  </div>
                )}

                {/* Submit */}
                <button
                  type="submit"
                  disabled={loading || !username.trim() || !password.trim()}
                  className="w-full py-3.5 rounded-xl bg-gradient-to-r from-primary via-[#4a60c5] to-[#75479c] text-white font-bold text-[15px] transition-all duration-300 hover:shadow-[0_0_30px_rgba(11,116,176,0.4)] hover:scale-[1.01] active:scale-[0.99] disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:shadow-none disabled:hover:scale-100 flex items-center justify-center gap-2"
                >
                  {loading ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      Signing in...
                    </>
                  ) : (
                    'Sign In'
                  )}
                </button>
              </form>

              {/* Footer hint */}
              <p className="text-center text-[11px] text-white/20 mt-5">
                Akasha Execution Platform — Adani Green Energy Limited
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

