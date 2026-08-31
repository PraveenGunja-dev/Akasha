/** @type {import('tailwindcss').Config} */

/* Every colour below resolves to a CSS variable declared in src/index.css.
   Both themes are carried by the variables, so a utility like
   `text-fg-secondary` is correct in light and dark with no `dark:` twin. */

/* Tailwind cannot put an alpha channel on a token that resolves to a hex, so
   every opacity utility on a semantic colour — `bg-primary/10`,
   `border-success/20`, `text-foreground/80` — matched no plugin and emitted
   nothing at all. 842 such utilities across 43 files were rendering as
   *absent*, not as tinted. color-mix restores the modifier without touching a
   single token definition in index.css: Tailwind substitutes <alpha-value>
   with the modifier, or with 1 when the utility carries none.
   Needs Chrome 111 / Safari 16.2 / Firefox 113 (all Feb 2023 or earlier). */
const tok = (name) =>
  `color-mix(in srgb, var(--${name}) calc(<alpha-value> * 100%), transparent)`;

const ramp = (name) =>
  Object.fromEntries(
    [50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950].map((s) => [
      s,
      tok(`${name}-${s}`),
    ])
  );

const statusTriad = (name) => ({
  DEFAULT: tok(`status-${name}-solid`),
  fg: tok(`status-${name}-fg`),
  bg: tok(`status-${name}-bg`),
  border: tok(`status-${name}-border`),
  solid: tok(`status-${name}-solid`),
});

export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx,js,jsx}"],
  theme: {
    extend: {
      colors: {
        /* ── Brand anchors ── */
        brand: {
          blue: tok("brand-blue"),
          purple: tok("brand-purple"),
          pink: tok("brand-pink"),
        },

        /* ── Neutral ramp: this is the interface ── */
        neutral: { 0: tok("neutral-0"), ...ramp("neutral") },

        /* ── Brand ramps ── */
        primary: {
          DEFAULT: tok("primary"),
          foreground: tok("primary-foreground"),
          ...ramp("primary"),
        },
        secondary: {
          DEFAULT: tok("secondary"),
          foreground: tok("secondary-foreground"),
          ...ramp("secondary"),
        },
        accent: {
          DEFAULT: tok("accent"),
          foreground: tok("accent-foreground"),
          ...ramp("accent"),
        },

        /* ── Surface elevation ladder ── */
        surface: {
          0: tok("surface-0"),
          1: tok("surface-1"),
          2: tok("surface-2"),
          3: tok("surface-3"),
          sunken: tok("surface-sunken"),
        },

        /* ── Foreground hierarchy ── */
        fg: {
          DEFAULT: tok("fg-primary"),
          primary: tok("fg-primary"),
          secondary: tok("fg-secondary"),
          tertiary: tok("fg-tertiary"),
          disabled: tok("fg-disabled"),
          "on-solid": tok("fg-on-solid"),
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
          DEFAULT: tok("border"),
          subtle: tok("border-subtle"),
          default: tok("border-default"),
          strong: tok("border-strong"),
        },
        input: tok("input"),
        ring: tok("ring"),

        /* ── Legacy semantic aliases (~4,000 existing call sites) ── */
        background: tok("background"),
        foreground: tok("foreground"),
        card: {
          DEFAULT: tok("card"),
          foreground: tok("card-foreground"),
        },
        popover: {
          DEFAULT: tok("popover"),
          foreground: tok("popover-foreground"),
        },
        muted: {
          DEFAULT: tok("muted"),
          foreground: tok("muted-foreground"),
        },
        destructive: {
          DEFAULT: tok("destructive"),
          foreground: tok("destructive-foreground"),
        },
        success: tok("success"),
        warning: tok("warning"),
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

      /* `animate-spin-slow` was used on the loading icon in both Intelligence
         screens but never declared anywhere, so those spinners sat frozen
         while the page reported it was analysing. */
      animation: {
        "spin-slow": "spin 3s linear infinite",
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
