import * as echarts from 'echarts';

/**
 * AKASHA CHART SYSTEM
 * ───────────────────────────────────────────────────────────────────────────
 * One theme for all 19 ECharts surfaces. Charts render to canvas and cannot
 * read CSS variables, so these values mirror the tokens in src/index.css.
 * If you change a token there, change its twin here.
 *
 * Rules this encodes:
 *   1. Status colours (red / amber / green / blue) are RESERVED for state.
 *      They never appear as a categorical series colour — otherwise a series
 *      that happens to land on red reads as "critical".
 *   2. The categorical palette is therefore drawn from brand blue → purple →
 *      pink plus two cool extenders, at controlled lightness so adjacent
 *      series stay separable (including for deuteranopia).
 *   3. Axis and gridline values differ per theme so both pass AA. The old
 *      code used #94a3b8 for axis labels in both themes, which fails on light.
 *
 * Usage:
 *   import { useChartTheme } from '@/lib/chartTheme';
 *   const { themeName } = useChartTheme();
 *   <ReactECharts theme={themeName} option={...} />
 *
 * Passing `theme` re-initialises the chart when it changes, so charts follow
 * the light/dark toggle automatically.
 */

import { useEffect, useState } from 'react';

/* ═══════════════ PALETTES ═══════════════ */

/** Categorical series. Ordered by separability — use in sequence. */
export const CATEGORICAL_LIGHT = [
  '#0b74b1', // brand blue
  '#76489d', // brand purple
  '#bc3860', // brand pink
  '#2a9d8f', // teal
  '#4c6ef5', // indigo
  '#7d8797', // neutral (use for "Other" / residual)
] as const;

export const CATEGORICAL_DARK = [
  '#43a7dd',
  '#b08ecd',
  '#e37b9d',
  '#4ec8b8',
  '#7f96f8',
  '#98a2b3',
] as const;

/** Sequential ramp (low → high). For volume, intensity, heatmaps. */
export const SEQUENTIAL_LIGHT = [
  '#eff8fd', '#d8eefa', '#b3ddf4', '#7fc5eb', '#43a7dd', '#0b74b1', '#0a5d8f',
] as const;

export const SEQUENTIAL_DARK = [
  '#0a2942', '#104163', '#0d4e76', '#0a5d8f', '#0b74b1', '#43a7dd', '#7fc5eb',
] as const;

/**
 * Status colours — for encoding state only (RAG bars, risk marks, variance).
 * Mirrors --status-*-solid.
 */
export const STATUS_LIGHT = {
  critical: '#d92d20',
  risk: '#f79009',
  watch: '#c4741f',
  healthy: '#12b76a',
  done: '#2e90fa',
  ai: '#76489d',
  neutral: '#98a2b3',
} as const;

export const STATUS_DARK = {
  critical: '#f04438',
  risk: '#f79009',
  watch: '#d68a35',
  healthy: '#12b76a',
  done: '#2e90fa',
  ai: '#9469b7',
  neutral: '#667085',
} as const;

/** Diverging ramp for variance (behind ← on plan → ahead). */
export const DIVERGING_LIGHT = ['#d92d20', '#f79009', '#e4e7ec', '#43a7dd', '#0b74b1'] as const;
export const DIVERGING_DARK = ['#f04438', '#f79009', '#344054', '#43a7dd', '#7fc5eb'] as const;

/* ═══════════════ THEME CHROME ═══════════════ */

interface Chrome {
  fgPrimary: string;
  fgSecondary: string;
  fgTertiary: string;
  gridLine: string;
  axisLine: string;
  surface1: string;
  surface2: string;
  borderSubtle: string;
}

const LIGHT: Chrome = {
  fgPrimary: '#101828',
  fgSecondary: '#475467',
  fgTertiary: '#667085',   // AA on white — replaces the old #94a3b8
  gridLine: '#f1f3f6',
  axisLine: '#e4e7ec',
  surface1: '#ffffff',
  surface2: '#ffffff',
  borderSubtle: '#e4e7ec',
};

const DARK: Chrome = {
  fgPrimary: '#eaedf1',
  fgSecondary: '#a8b2c1',
  fgTertiary: '#7d8797',
  gridLine: '#1c2433',
  axisLine: '#273040',
  surface1: '#10151f',
  surface2: '#161d2a',
  borderSubtle: '#1f2836',
};

const FONT =
  "Adani, ui-sans-serif, system-ui, -apple-system, 'Segoe UI', sans-serif";

function buildTheme(c: Chrome, categorical: readonly string[]) {
  const axisCommon = {
    axisLine: { show: true, lineStyle: { color: c.axisLine, width: 1 } },
    axisTick: { show: false },
    axisLabel: {
      color: c.fgTertiary,
      fontSize: 11,
      fontFamily: FONT,
      fontWeight: 500,
    },
    nameTextStyle: {
      color: c.fgSecondary,
      fontSize: 11,
      fontWeight: 600,
      fontFamily: FONT,
    },
    splitLine: {
      show: true,
      lineStyle: { color: c.gridLine, width: 1, type: 'solid' as const },
    },
  };

  return {
    color: [...categorical],
    backgroundColor: 'transparent',

    textStyle: { fontFamily: FONT, color: c.fgSecondary },

    title: {
      textStyle: { color: c.fgPrimary, fontFamily: FONT, fontSize: 13, fontWeight: 600 },
      subtextStyle: { color: c.fgTertiary, fontFamily: FONT, fontSize: 11 },
    },

    /* Tabular figures in tooltips so values don't shimmy while hovering. */
    tooltip: {
      backgroundColor: c.surface2,
      borderColor: c.borderSubtle,
      borderWidth: 1,
      padding: [8, 10],
      extraCssText:
        'border-radius:8px;box-shadow:0 8px 24px -4px rgba(0,0,0,.14);' +
        'font-variant-numeric:tabular-nums lining-nums;',
      textStyle: { color: c.fgPrimary, fontSize: 12, fontFamily: FONT },
      axisPointer: {
        lineStyle: { color: c.axisLine },
        crossStyle: { color: c.axisLine },
        shadowStyle: { color: c.gridLine, opacity: 0.5 },
      },
    },

    legend: {
      textStyle: { color: c.fgSecondary, fontSize: 11, fontFamily: FONT },
      icon: 'roundRect',
      itemWidth: 8,
      itemHeight: 8,
      itemGap: 14,
    },

    grid: {
      left: 8,
      right: 12,
      top: 28,
      bottom: 4,
      containLabel: true,
      borderColor: c.borderSubtle,
    },

    categoryAxis: { ...axisCommon, splitLine: { show: false } },
    valueAxis: axisCommon,
    logAxis: axisCommon,
    timeAxis: axisCommon,

    /* Flat marks. No gradients, no glow, no drop shadow on data. */
    bar: {
      itemStyle: { borderRadius: [3, 3, 0, 0], borderWidth: 0 },
      barMaxWidth: 28,
    },
    line: {
      smooth: false,
      symbol: 'circle',
      symbolSize: 5,
      showSymbol: false,
      lineStyle: { width: 2 },
      emphasis: { focus: 'series' },
    },
    scatter: {
      itemStyle: { opacity: 0.8, borderWidth: 1, borderColor: c.surface1 },
    },
    pie: {
      itemStyle: { borderColor: c.surface1, borderWidth: 2 },
      label: { color: c.fgSecondary, fontSize: 11, fontFamily: FONT },
      labelLine: { lineStyle: { color: c.axisLine } },
    },
    gauge: {
      axisLine: { lineStyle: { color: [[1, c.gridLine]] } },
      axisLabel: { color: c.fgTertiary, fontSize: 10 },
      title: { color: c.fgSecondary, fontSize: 11 },
      detail: { color: c.fgPrimary, fontSize: 20, fontWeight: 600 },
    },
    funnel: {
      itemStyle: { borderColor: c.surface1, borderWidth: 1 },
      label: { color: c.fgSecondary, fontSize: 11, fontFamily: FONT },
    },

    visualMap: {
      textStyle: { color: c.fgTertiary, fontSize: 10, fontFamily: FONT },
    },
  };
}

export const AKASHA_LIGHT = 'akasha-light';
export const AKASHA_DARK = 'akasha-dark';

let registered = false;

/** Registers both themes with ECharts. Idempotent. */
export function registerChartThemes(): void {
  if (registered) return;
  echarts.registerTheme(AKASHA_LIGHT, buildTheme(LIGHT, CATEGORICAL_LIGHT));
  echarts.registerTheme(AKASHA_DARK, buildTheme(DARK, CATEGORICAL_DARK));
  registered = true;
}

// Register at module load so any importer is ready immediately.
registerChartThemes();

/* ═══════════════ REACT BINDING ═══════════════ */

function isDarkNow(): boolean {
  return typeof document !== 'undefined' &&
    document.documentElement.classList.contains('dark');
}

/**
 * Tracks the `dark` class on <html> and returns the matching theme name plus
 * the palettes for the active theme.
 *
 * Pass `themeName` to <ReactECharts theme={themeName} />. When it changes the
 * chart re-initialises against the new theme, so charts follow the toggle.
 */
export function useChartTheme() {
  const [dark, setDark] = useState<boolean>(isDarkNow);

  useEffect(() => {
    const el = document.documentElement;
    const obs = new MutationObserver(() => setDark(el.classList.contains('dark')));
    obs.observe(el, { attributes: true, attributeFilter: ['class'] });
    setDark(el.classList.contains('dark'));
    return () => obs.disconnect();
  }, []);

  return {
    isDark: dark,
    themeName: dark ? AKASHA_DARK : AKASHA_LIGHT,
    categorical: dark ? CATEGORICAL_DARK : CATEGORICAL_LIGHT,
    sequential: dark ? SEQUENTIAL_DARK : SEQUENTIAL_LIGHT,
    diverging: dark ? DIVERGING_DARK : DIVERGING_LIGHT,
    status: dark ? STATUS_DARK : STATUS_LIGHT,
    chrome: dark ? DARK : LIGHT,
  };
}

/** Series colour by index, wrapping. Use instead of inline hex. */
export function seriesColor(index: number, dark = isDarkNow()): string {
  const p = dark ? CATEGORICAL_DARK : CATEGORICAL_LIGHT;
  return p[index % p.length];
}

/** Maps a health/RAG string from P6, SAP or Pulse to its status colour. */
export function statusColor(
  state: string | null | undefined,
  dark = isDarkNow()
): string {
  const s = dark ? STATUS_DARK : STATUS_LIGHT;
  switch ((state ?? '').trim().toLowerCase()) {
    case 'critical':
    case 'delayed':
    case 'red':
    case 'overdue':
      return s.critical;
    case 'high risk':
    case 'at risk':
    case 'amber':
    case 'warning':
      return s.risk;
    case 'watchlist':
    case 'watch':
      return s.watch;
    case 'healthy':
    case 'on track':
    case 'green':
      return s.healthy;
    case 'completed':
    case 'commissioned':
    case 'closed':
    case 'done':
      return s.done;
    default:
      return s.neutral;
  }
}
