/** @type {import('tailwindcss').Config} */

/* Every colour below resolves to a CSS variable declared in src/index.css.
   Both themes are carried by the variables, so a utility like
   `text-fg-secondary` is correct in light and dark with no `dark:` twin. */

const ramp = (name) =>
  Object.fromEntries(
    [50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950].map((s) => [
      s,
      `var(--${name}-${s})`,
    ])
  );

const statusTriad = (name) => ({
  DEFAULT: `var(--status-${name}-solid)`,
  fg: `var(--status-${name}-fg)`,
  bg: `var(--status-${name}-bg)`,
  border: `var(--status-${name}-border)`,
  solid: `var(--status-${name}-solid)`,
});

export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx,js,jsx}"],
  theme: {
    extend: {
      colors: {
        /* ── Brand anchors ── */
        brand: {
          blue: "var(--brand-blue)",
          purple: "var(--brand-purple)",
          pink: "var(--brand-pink)",
        },

        /* ── Neutral ramp: this is the interface ── */
        neutral: { 0: "var(--neutral-0)", ...ramp("neutral") },

        /* ── Brand ramps ── */
        primary: {
          DEFAULT: "var(--primary)",
          foreground: "var(--primary-foreground)",
          ...ramp("primary"),
        },
        secondary: {
          DEFAULT: "var(--secondary)",
          foreground: "var(--secondary-foreground)",
          ...ramp("secondary"),
        },
        accent: {
          DEFAULT: "var(--accent)",
          foreground: "var(--accent-foreground)",
          ...ramp("accent"),
        },

        /* ── Surface elevation ladder ── */
        surface: {
          0: "var(--surface-0)",
          1: "var(--surface-1)",
          2: "var(--surface-2)",
          3: "var(--surface-3)",
          sunken: "var(--surface-sunken)",
        },

        /* ── Foreground hierarchy ── */
        fg: {
          DEFAULT: "var(--fg-primary)",
          primary: "var(--fg-primary)",
          secondary: "var(--fg-secondary)",
          tertiary: "var(--fg-tertiary)",
          disabled: "var(--fg-disabled)",
          "on-solid": "var(--fg-on-solid)",
        },

        /* ── Status system: five states + one AI accent ──
           Reserved. Never use these as chart series colours. */
        status: {
          critical: statusTriad("critical"),
          risk: statusTriad("risk"),
          watch: statusTriad("watch"),
          healthy: statusTriad("healthy"),
          done: statusTriad("done"),
          ai: statusTriad("ai"),
        },

        /* ── Lines ── */
        border: {
          DEFAULT: "var(--border)",
          subtle: "var(--border-subtle)",
          default: "var(--border-default)",
          strong: "var(--border-strong)",
        },
        input: "var(--input)",
        ring: "var(--ring)",

        /* ── Legacy semantic aliases (~4,000 existing call sites) ── */
        background: "var(--background)",
        foreground: "var(--foreground)",
        card: {
          DEFAULT: "var(--card)",
          foreground: "var(--card-foreground)",
        },
        popover: {
          DEFAULT: "var(--popover)",
          foreground: "var(--popover-foreground)",
        },
        muted: {
          DEFAULT: "var(--muted)",
          foreground: "var(--muted-foreground)",
        },
        destructive: {
          DEFAULT: "var(--destructive)",
          foreground: "var(--destructive-foreground)",
        },
        success: "var(--success)",
        warning: "var(--warning)",
      },

      /* 12px ceiling on data surfaces. `rounded-full` stays for dots and avatars. */
      borderRadius: {
        sm: "var(--r-sm)",
        DEFAULT: "var(--r-md)",
        md: "var(--r-md)",
        lg: "var(--r-lg)",
        xl: "var(--r-xl)",
        "2xl": "var(--r-xl)", // clamped — was 16px
        "3xl": "var(--r-xl)", // clamped — was 24px
      },

      /* Two elevation steps plus an overlay step. */
      boxShadow: {
        none: "none",
        sm: "var(--elev-1)",
        DEFAULT: "var(--elev-1)",
        md: "var(--elev-2)",
        lg: "var(--elev-2)",
        xl: "var(--elev-overlay)",
        "2xl": "var(--elev-overlay)",
        overlay: "var(--elev-overlay)",
        card: "var(--shadow-card)",
        "card-hover": "var(--shadow-card-hover)",
      },

      fontFamily: {
        sans: ["Adani", "ui-sans-serif", "system-ui", "sans-serif"],
        heading: ["Adani", "ui-sans-serif", "system-ui", "sans-serif"],
      },

      transitionTimingFunction: {
        DEFAULT: "cubic-bezier(0.2, 0, 0, 1)",
        ease: "cubic-bezier(0.2, 0, 0, 1)",
      },
      transitionDuration: {
        DEFAULT: "160ms",
        fast: "120ms",
        base: "160ms",
        slow: "200ms",
      },
    },
  },
  plugins: [require("@tailwindcss/typography")],
};
