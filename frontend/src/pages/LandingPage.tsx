import * as THREE from 'three';
import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Moon, Sun } from "lucide-react";
import adaniLogo from "../assets/adani-dpr-icon.ico";
import PhotonBeam from "../components/ui/photon-beam";
import PresentationModal from "../components/ui/PresentationModal";

export default function LandingPage() {
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const [showPresentation, setShowPresentation] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    if (theme === "dark") {
      document.documentElement.classList.add("dark");
    } else {
      document.documentElement.classList.remove("dark");
    }
  }, [theme]);

  const toggleTheme = () => {
    setTheme(theme === "light" ? "dark" : "light");
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
          className="p-2.5 rounded-full hover:bg-muted/80 transition-colors text-foreground"
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
                  onClick={() => navigate('/dashboard')}
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
    </div>
  );
}
