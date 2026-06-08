import { useState, useEffect } from "react";
import { Moon, Sun } from "lucide-react";
import adaniLogo from "../assets/adani-dpr-icon.ico";

export default function Header() {
  const [theme, setTheme] = useState<"light" | "dark">("light");

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
    <header className="absolute top-0 w-full z-50 px-8 py-5 flex items-center justify-between border-b border-white/10 dark:border-white/5 bg-background/40 backdrop-blur-md transition-all duration-300">
      <div className="flex items-center gap-3">
        <div className="w-40 h-16 flex items-center justify-center overflow-hidden">
          <img src={adaniLogo} alt="Adani Logo" className="w-full h-full object-contain dark:brightness-110" />
        </div>
      </div>

      <div className="flex items-center gap-6">
        <button
          onClick={toggleTheme}
          className="p-2.5 rounded-full hover:bg-muted/80 backdrop-blur-sm transition-colors text-foreground shadow-sm"
        >
          {theme === "light" ? <Moon size={20} /> : <Sun size={20} />}
        </button>
        <button className="bg-primary hover:bg-primary/90 text-primary-foreground font-medium py-2.5 px-6 rounded-lg flex items-center gap-2 transition-all shadow-lg hover:shadow-primary/30 text-base">
          Sign In
        </button>
      </div>
    </header>
  );
}
