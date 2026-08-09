import type { EChartsOption } from 'echarts';

import type {
  VisualizationChannelV2,
  VisualizationSeriesV1,
  VisualizationSpecV1,
  VisualizationSpecV2,
} from './visualizationTypes';

const SEMANTIC_COLORS: Record<string, string> = {
  primary: '#0B74B0',
  progress: '#75479C',
  warning: '#BD3861',
  critical: '#B42318',
  neutral: '#98A2B3',
  teal: '#BD3861',
};

const ADANI_PALETTE = ['#0B74B0', '#75479C', '#BD3861', '#4B91BC', '#966EB5', '#CC6787'];
const TOOLTIP_CSS = 'max-width:300px;max-height:190px;overflow:hidden;border-radius:10px;box-shadow:0 10px 30px rgba(0,0,0,0.18);line-height:1.35;';

function color(name: string): string {
  return SEMANTIC_COLORS[name] ?? SEMANTIC_COLORS.primary;
}

function valueFormatter(series: VisualizationSeriesV1): string {
  if (series.value_format === 'percent') return '{value}%';
  if (series.value_format === 'days') return '{value}d';
  return '{value}';
}

interface TooltipParam {
  axisValueLabel?: string;
  color?: string;
  name?: string;
  seriesName?: string;
  value?: unknown;
  data?: unknown;
}

function escapeHtml(value: unknown): string {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function tooltipScalar(value: unknown): unknown {
  if (!Array.isArray(value)) return value;
  return value.find(item => typeof item === 'number' || typeof item === 'string') ?? '';
}

function tooltipValue(value: unknown, format?: VisualizationSeriesV1['value_format']): string {
  const scalar = tooltipScalar(value);
  if (scalar === null || scalar === undefined || scalar === '') return 'Not available';
  const number = typeof scalar === 'number' ? scalar : Number(scalar);
  const display = Number.isFinite(number)
    ? new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(number)
    : String(scalar);
  if (format === 'percent') return `${display}%`;
  if (format === 'days') return `${display} days`;
  return display;
}

function tooltipFormatter(spec: VisualizationSpecV1, input: unknown): string {
  const params = (Array.isArray(input) ? input : [input]).filter(
    (item): item is TooltipParam => Boolean(item && typeof item === 'object'),
  ).slice(0, 6);
  if (!params.length) return '';
  const heading = params[0].axisValueLabel || params[0].name;
  const rows = params.map(param => {
    const series = spec.series.find(item => item.name === param.seriesName);
    const swatch = typeof param.color === 'string' ? param.color : color(series?.semantic_color ?? 'primary');
    return `<div style="display:flex;align-items:center;justify-content:space-between;gap:16px;margin-top:5px;">`
      + `<span style="display:flex;align-items:center;gap:7px;min-width:0;">`
      + `<span style="width:9px;height:9px;border-radius:999px;background:${escapeHtml(swatch)};flex:0 0 auto;"></span>`
      + `<span>${escapeHtml(param.seriesName || param.name || 'Value')}</span></span>`
      + `<strong style="font-weight:600;white-space:nowrap;">${escapeHtml(tooltipValue(param.value, series?.value_format))}</strong>`
      + `</div>`;
  }).join('');
  return `${heading ? `<div style="font-weight:600;margin-bottom:2px;">${escapeHtml(heading)}</div>` : ''}${rows}`;
}

function tooltipTheme() {
  const dark = typeof document !== 'undefined' && document.documentElement.classList.contains('dark');
  return dark
    ? { background: '#111827', foreground: '#f9fafb', border: '#374151' }
    : { background: '#ffffff', foreground: '#111827', border: '#d1d5db' };
}

const textStyle = { color: 'var(--foreground)' };
const mutedTextStyle = { color: 'var(--muted-foreground)' };

function baseOption(spec: VisualizationSpecV1): EChartsOption {
  const tooltipColors = tooltipTheme();
  return {
    animationDuration: 550,
    animationEasing: 'cubicOut',
    aria: {
      enabled: true,
      decal: { show: false },
      description: spec.accessibility_description,
    },
    textStyle: { fontFamily: 'Aptos, Avenir Next, Segoe UI, sans-serif' },
    tooltip: {
      trigger: spec.shape === 'donut' ? 'item' : 'axis',
      renderMode: 'html',
      confine: true,
      backgroundColor: tooltipColors.background,
      borderColor: tooltipColors.border,
      borderWidth: 1,
      padding: [10, 12],
      textStyle: { color: tooltipColors.foreground, fontSize: 12 },
      extraCssText: TOOLTIP_CSS,
      formatter: input => tooltipFormatter(spec, input),
    },
  };
}

function horizontalBar(spec: VisualizationSpecV1): EChartsOption {
  const multiple = spec.series.length > 1;
  return {
    ...baseOption(spec),
    legend: multiple ? { bottom: 0, textStyle } : { show: false },
    grid: { left: '3%', right: '8%', top: 20, bottom: multiple ? 42 : 20, containLabel: true },
    xAxis: {
      type: 'value',
      name: undefined,
      axisLabel: { ...mutedTextStyle, formatter: valueFormatter(spec.series[0]) },
      splitLine: { lineStyle: { color: 'var(--border)', opacity: 0.25 } },
    },
    yAxis: {
      type: 'category',
      data: spec.categories,
      inverse: true,
      axisLabel: { ...textStyle, width: 150, overflow: 'truncate' },
      axisLine: { lineStyle: { color: 'var(--border)' } },
    },
    series: spec.series.map(series => ({
      name: series.name,
      type: 'bar',
      stack: series.stack_group ?? undefined,
      data: series.values.map((value, index) => ({
        value,
        itemStyle: {
          color: color(series.item_semantic_colors?.[index] ?? series.semantic_color),
          borderRadius: [0, 6, 6, 0],
        },
      })),
      barMaxWidth: 26,
      label: spec.series.length === 1 ? {
        show: true,
        position: 'right',
        formatter: series.value_format === 'percent' ? '{c}%' : '{c}',
        color: 'var(--foreground)',
        fontWeight: 600,
      } : undefined,
    })),
  };
}

function donut(spec: VisualizationSpecV1): EChartsOption {
  const series = spec.series[0];
  return {
    ...baseOption(spec),
    legend: { bottom: 0, left: 'center', textStyle },
    series: [{
      name: series.name,
      type: 'pie',
      radius: ['42%', '68%'],
      center: ['50%', '44%'],
      label: { show: false },
      itemStyle: { borderRadius: 6, borderColor: 'var(--card)', borderWidth: 3 },
      data: spec.categories.map((name, index) => ({
        name,
        value: series.values[index] ?? 0,
        itemStyle: { color: color(series.item_semantic_colors?.[index] ?? series.semantic_color) },
      })),
    }],
  };
}

function verticalBar(spec: VisualizationSpecV1): EChartsOption {
  return {
    ...baseOption(spec),
    legend: { bottom: 0, textStyle },
    grid: { left: 48, right: 20, top: 20, bottom: 62, containLabel: true },
    xAxis: {
      type: 'category',
      data: spec.categories,
      axisLabel: { ...textStyle, width: 130, overflow: 'truncate' },
      axisLine: { lineStyle: { color: 'var(--border)' } },
    },
    yAxis: {
      type: 'value',
      name: spec.y_axis_title ?? spec.x_axis_title ?? undefined,
      axisLabel: mutedTextStyle,
      splitLine: { lineStyle: { color: 'var(--border)', opacity: 0.25 } },
    },
    series: spec.series.map(series => ({
      name: series.name,
      type: 'bar',
      data: series.values,
      barMaxWidth: 34,
      itemStyle: { color: color(series.semantic_color), borderRadius: [6, 6, 0, 0] },
      label: spec.categories.length <= 8 ? {
        show: true,
        position: 'top',
        color: 'var(--foreground)',
        fontSize: 11,
        fontWeight: 600,
      } : undefined,
    })),
  };
}

function radialProgress(spec: VisualizationSpecV1): EChartsOption {
  const values = spec.series[0]?.values ?? [];
  const count = Math.max(1, spec.categories.length);
  return {
    ...baseOption(spec),
    tooltip: {
      ...(baseOption(spec).tooltip as object),
      trigger: 'item',
    },
    series: spec.categories.map((name, index) => {
      const value = Number(values[index] ?? 0);
      const centerX = count === 1 ? 50 : 25 + (50 * index / Math.max(1, count - 1));
      return {
        name,
        type: 'gauge',
        center: [`${centerX}%`, '50%'],
        radius: count <= 2 ? '62%' : '44%',
        min: 0,
        max: 100,
        startAngle: 220,
        endAngle: -40,
        progress: { show: true, width: 15, roundCap: true, itemStyle: { color: color('primary') } },
        axisLine: { lineStyle: { width: 15, color: [[1, 'var(--muted)']] } },
        axisTick: { show: false },
        splitLine: { show: false },
        axisLabel: { show: false },
        pointer: { show: false },
        anchor: { show: false },
        title: {
          show: true,
          offsetCenter: [0, '58%'],
          color: 'var(--foreground)',
          fontSize: 11,
          width: count <= 2 ? 145 : 105,
          overflow: 'truncate',
        },
        detail: {
          valueAnimation: true,
          offsetCenter: [0, '5%'],
          formatter: '{value}%',
          color: 'var(--foreground)',
          fontSize: 23,
          fontWeight: 600,
        },
        data: [{ value, name }],
      };
    }),
  };
}

function lollipop(spec: VisualizationSpecV1): EChartsOption {
  const series = spec.series[0];
  const values = series.values.map(value => Number(value ?? 0));
  return {
    ...baseOption(spec),
    grid: { left: '3%', right: '10%', top: 20, bottom: 28, containLabel: true },
    xAxis: {
      type: 'value',
      name: spec.x_axis_title ?? undefined,
      axisLabel: { ...mutedTextStyle, formatter: valueFormatter(series) },
      splitLine: { lineStyle: { color: 'var(--border)', opacity: 0.25 } },
    },
    yAxis: {
      type: 'category',
      inverse: true,
      data: spec.categories,
      axisLabel: { ...textStyle, width: 150, overflow: 'truncate' },
      axisLine: { lineStyle: { color: 'var(--border)' } },
    },
    series: [
      {
        name: series.name,
        type: 'bar',
        data: values.map((value, index) => ({
          value,
          itemStyle: { color: color(series.item_semantic_colors?.[index] ?? series.semantic_color) },
        })),
        barWidth: 3,
        silent: true,
      },
      {
        name: series.name,
        type: 'scatter',
        symbolSize: 17,
        data: values.map((value, index) => ({
          value: [value, index],
          itemStyle: { color: color(series.item_semantic_colors?.[index] ?? series.semantic_color) },
          label: {
            show: true,
            position: 'right',
            formatter: series.value_format === 'days' ? `${value}d` : String(value),
            color: 'var(--foreground)',
            fontWeight: 600,
          },
        })),
      },
    ],
  };
}

function combo(spec: VisualizationSpecV1): EChartsOption {
  const hasSecondaryAxis = spec.series.some(series => series.axis_index === 1);
  const percentOnly = spec.series.every(series => series.value_format === 'percent');
  return {
    ...baseOption(spec),
    legend: { top: 0, right: 8, textStyle },
    grid: { left: 42, right: 52, top: 48, bottom: 44, containLabel: true },
    xAxis: {
      type: 'category',
      data: spec.categories,
      axisLabel: { ...mutedTextStyle, hideOverlap: true },
      axisLine: { lineStyle: { color: 'var(--border)' } },
    },
    yAxis: hasSecondaryAxis ? [
      {
        type: 'value',
        name: 'Activities',
        minInterval: 1,
        axisLabel: mutedTextStyle,
        splitLine: { lineStyle: { color: 'var(--border)', opacity: 0.25 } },
      },
      {
        type: 'value',
        name: 'Cumulative',
        min: 0,
        max: 100,
        axisLabel: { ...mutedTextStyle, formatter: '{value}%' },
        splitLine: { show: false },
      },
    ] : {
      type: 'value',
      name: spec.y_axis_title ?? undefined,
      min: percentOnly ? 0 : undefined,
      max: percentOnly ? 100 : undefined,
      axisLabel: percentOnly ? { ...mutedTextStyle, formatter: '{value}%' } : mutedTextStyle,
      splitLine: { lineStyle: { color: 'var(--border)', opacity: 0.25 } },
    },
    series: spec.series.map(series => series.shape === 'line' ? {
      name: series.name,
      type: 'line',
      yAxisIndex: series.axis_index,
      data: series.values,
      smooth: 0.24,
      symbol: 'circle',
      symbolSize: 6,
      lineStyle: { color: color(series.semantic_color), width: 3 },
      itemStyle: { color: color(series.semantic_color), borderColor: 'var(--card)', borderWidth: 2 },
      areaStyle: { color: color(series.semantic_color), opacity: 0.08 },
    } : {
      name: series.name,
      type: 'bar',
      yAxisIndex: series.axis_index,
      data: series.values,
      barMaxWidth: 18,
      itemStyle: { color: color(series.semantic_color), borderRadius: [5, 5, 0, 0] },
    }),
  };
}

export function visualizationSpecToECharts(spec: VisualizationSpecV1): EChartsOption {
  if (spec.shape === 'horizontal_bar') return horizontalBar(spec);
  if (spec.shape === 'vertical_bar') return verticalBar(spec);
  if (spec.shape === 'donut') return donut(spec);
  if (spec.shape === 'radial_progress') return radialProgress(spec);
  if (spec.shape === 'lollipop') return lollipop(spec);
  return combo(spec);
}

function channelAxisFormatter(channel: VisualizationChannelV2 | undefined): string | undefined {
  if (channel?.value_format === 'percent') return '{value}%';
  if (channel?.value_format === 'days') return '{value}d';
  if (channel?.value_format === 'mw') return '{value} MW';
  return undefined;
}

function v2TooltipFormatter(spec: VisualizationSpecV2, input: unknown): string {
  const params = (Array.isArray(input) ? input : [input]).filter(
    (item): item is TooltipParam => Boolean(item && typeof item === 'object'),
  ).slice(0, 6);
  if (!params.length) return '';
  const firstRecord = params[0].value && typeof params[0].value === 'object' && !Array.isArray(params[0].value)
    ? params[0].value as Record<string, unknown>
    : params[0].data && typeof params[0].data === 'object' && 'raw' in params[0].data
      ? (params[0].data as { raw: Record<string, unknown> }).raw
      : undefined;
  const heading = params[0].axisValueLabel
    || (spec.encoding.label && firstRecord ? firstRecord[spec.encoding.label.field] : undefined)
    || params[0].name;
  const rows = params.map(param => {
    const channel = spec.encoding.y.find(item => item.label === param.seriesName)
      || (spec.encoding.color?.label === param.seriesName ? spec.encoding.color : undefined)
      || spec.encoding.y[0]
      || spec.encoding.color;
    const record = param.value && typeof param.value === 'object' && !Array.isArray(param.value)
      ? param.value as Record<string, unknown>
      : param.data && typeof param.data === 'object' && 'raw' in param.data
        ? (param.data as { raw: Record<string, unknown> }).raw
        : undefined;
    const rawValue = channel && record
      ? record[channel.field]
      : Array.isArray(param.value)
        ? param.value[param.value.length - 1]
        : param.value;
    return `<div style="display:flex;align-items:center;justify-content:space-between;gap:16px;margin-top:5px;">`
      + `<span>${escapeHtml(channel?.label || param.seriesName || 'Value')}</span>`
      + `<strong style="font-weight:600;white-space:nowrap;">${escapeHtml(tooltipValue(rawValue, channel?.value_format === 'mw' ? 'decimal' : channel?.value_format ?? undefined))}${channel?.value_format === 'mw' ? ' MW' : ''}</strong>`
      + `</div>`;
  }).join('');
  return `${heading ? `<div style="font-weight:600;margin-bottom:2px;">${escapeHtml(heading)}</div>` : ''}${rows}`;
}

function v2BaseOption(spec: VisualizationSpecV2): EChartsOption {
  const tooltipColors = tooltipTheme();
  return {
    animationDuration: 550,
    animationEasing: 'cubicOut',
    aria: { enabled: true, decal: { show: false }, description: spec.accessibility_description },
    textStyle: { fontFamily: 'Aptos, Avenir Next, Segoe UI, sans-serif' },
    tooltip: {
      trigger: spec.shape === 'scatter' || spec.shape === 'donut' || spec.shape === 'heatmap' ? 'item' : 'axis',
      renderMode: 'html',
      confine: true,
      backgroundColor: tooltipColors.background,
      borderColor: tooltipColors.border,
      borderWidth: 1,
      textStyle: { color: tooltipColors.foreground, fontSize: 12 },
      extraCssText: TOOLTIP_CSS,
      formatter: input => v2TooltipFormatter(spec, input),
    },
  };
}

function cartesianV2(spec: VisualizationSpecV2): EChartsOption {
  const dimension = spec.encoding.x!;
  const horizontal = spec.shape === 'horizontal_bar';
  const categoryAxis = {
    type: 'category' as const,
    name: dimension.label,
    axisLabel: { ...mutedTextStyle, hideOverlap: true, width: 150, overflow: 'truncate' as const },
    axisLine: { lineStyle: { color: 'var(--border)' } },
  };
  const primaryMetric = spec.encoding.y.find(metric => (metric.axis_index ?? 0) === 0) ?? spec.encoding.y[0];
  const secondaryMetric = spec.encoding.y.find(metric => metric.axis_index === 1);
  const valueAxisFor = (metric: VisualizationChannelV2 | undefined, position: 'left' | 'right' = 'left') => ({
    type: 'value' as const,
    name: metric?.label,
    position,
    axisLabel: { ...mutedTextStyle, formatter: channelAxisFormatter(metric) },
    splitLine: { lineStyle: { color: 'var(--border)', opacity: 0.25 } },
  });
  const valueAxis = valueAxisFor(primaryMetric);
  return {
    ...v2BaseOption(spec),
    dataset: { source: spec.data },
    legend: spec.encoding.y.length > 1 ? { top: 0, right: 8, textStyle } : { show: false },
    grid: { left: 42, right: 36, top: spec.encoding.y.length > 1 ? 48 : 24, bottom: 44, containLabel: true },
    xAxis: horizontal ? valueAxis : categoryAxis,
    yAxis: horizontal
      ? { ...categoryAxis, inverse: true }
      : secondaryMetric
        ? [valueAxis, { ...valueAxisFor(secondaryMetric, 'right'), splitLine: { show: false } }]
        : valueAxis,
    series: spec.encoding.y.map((metric, index) => ({
      name: metric.label,
      type: spec.shape === 'line' ? 'line' : 'bar',
      yAxisIndex: horizontal ? undefined : metric.axis_index ?? 0,
      encode: horizontal
        ? { x: metric.field, y: dimension.field }
        : { x: dimension.field, y: metric.field },
      stack: spec.shape === 'stacked_bar' ? 'total' : undefined,
      smooth: spec.shape === 'line' ? 0.2 : undefined,
      showSymbol: spec.shape === 'line' ? spec.data.length <= 30 : undefined,
      barMaxWidth: spec.shape === 'line' ? undefined : 24,
      lineStyle: spec.shape === 'line' ? { color: color(['primary', 'progress', 'warning', 'teal'][index] ?? 'primary'), width: 3 } : undefined,
      itemStyle: {
        color: color(['primary', 'progress', 'warning', 'teal'][index] ?? 'primary'),
        borderRadius: horizontal ? [0, 5, 5, 0] : [5, 5, 0, 0],
      },
      label: spec.shape !== 'line' && spec.data.length <= 8 ? {
        show: true,
        position: horizontal ? 'right' : 'top',
        color: 'var(--foreground)',
        fontSize: 11,
        fontWeight: 600,
      } : undefined,
    })),
  } as EChartsOption;
}

function scatterV2(spec: VisualizationSpecV2): EChartsOption {
  const x = spec.encoding.x!;
  const y = spec.encoding.y[0];
  return {
    ...v2BaseOption(spec),
    dataset: { source: spec.data },
    grid: { left: 48, right: 30, top: 24, bottom: 48, containLabel: true },
    xAxis: {
      type: 'value', name: x.label,
      axisLabel: { ...mutedTextStyle, formatter: channelAxisFormatter(x) },
      splitLine: { lineStyle: { color: 'var(--border)', opacity: 0.25 } },
    },
    yAxis: {
      type: 'value', name: y.label,
      axisLabel: { ...mutedTextStyle, formatter: channelAxisFormatter(y) },
      splitLine: { lineStyle: { color: 'var(--border)', opacity: 0.25 } },
    },
    series: [{
      name: `${x.label} vs ${y.label}`,
      type: 'scatter',
      symbolSize: 15,
      encode: {
        x: x.field,
        y: y.field,
        tooltip: [spec.encoding.label?.field, x.field, y.field].filter(Boolean),
        itemName: spec.encoding.label?.field,
      },
      itemStyle: { color: color('primary'), opacity: 0.82 },
    }],
  } as EChartsOption;
}

function heatmapV2(spec: VisualizationSpecV2): EChartsOption {
  const x = spec.encoding.x!;
  const y = spec.encoding.y[0];
  const metric = spec.encoding.color!;
  const xValues = [...new Set(spec.data.map(row => String(row[x.field] ?? 'Unknown')))];
  const yValues = [...new Set(spec.data.map(row => String(row[y.field] ?? 'Unknown')))];
  const values = spec.data.map(row => Number(row[metric.field] ?? 0));
  const maximum = Math.max(...values, 0);
  return {
    ...v2BaseOption(spec),
    grid: { left: 40, right: 72, top: 20, bottom: 52, containLabel: true },
    xAxis: { type: 'category', name: x.label, data: xValues, axisLabel: { ...mutedTextStyle, hideOverlap: true } },
    yAxis: { type: 'category', name: y.label, data: yValues, axisLabel: { ...mutedTextStyle, width: 140, overflow: 'truncate' } },
    visualMap: {
      min: 0, max: maximum || 1, calculable: true, orient: 'vertical', right: 0, top: 'middle',
      inRange: { color: ['#F4F8FB', '#9CC7DF', '#0B74B0', '#75479C', '#BD3861'] },
      textStyle,
    },
    series: [{
      name: metric.label,
      type: 'heatmap',
      data: spec.data.map(row => ({
        value: [
          xValues.indexOf(String(row[x.field] ?? 'Unknown')),
          yValues.indexOf(String(row[y.field] ?? 'Unknown')),
          Number(row[metric.field] ?? 0),
        ],
        raw: row,
      })),
      label: { show: xValues.length * yValues.length <= 60, color: 'var(--foreground)' },
      emphasis: { itemStyle: { shadowBlur: 8, shadowColor: 'rgba(0,0,0,0.25)' } },
    }],
  } as EChartsOption;
}

function donutV2(spec: VisualizationSpecV2): EChartsOption {
  const dimension = spec.encoding.x!;
  const metric = spec.encoding.y[0];
  return {
    ...v2BaseOption(spec),
    legend: { bottom: 0, type: 'scroll', textStyle },
    series: [{
      name: metric.label,
      type: 'pie',
      radius: ['42%', '70%'],
      center: ['50%', '45%'],
      label: { show: false },
      emphasis: { label: { show: true, fontWeight: 'bold' } },
      data: spec.data.map((row, index) => ({
        name: String(row[dimension.field] ?? 'Unknown'),
        value: Number(row[metric.field] ?? 0),
        itemStyle: { color: color(['primary', 'progress', 'warning', 'teal', 'critical', 'neutral'][index] ?? 'primary') },
      })),
    }],
  } as EChartsOption;
}

function waterfallV2(spec: VisualizationSpecV2): EChartsOption {
  const dimension = spec.encoding.x!;
  const metric = spec.encoding.y[0];
  let running = 0;
  const helper: number[] = [];
  const positive: Array<number | string> = [];
  const negative: Array<number | string> = [];
  spec.data.forEach(row => {
    const value = Number(row[metric.field] ?? 0);
    if (value >= 0) {
      helper.push(running);
      positive.push(value);
      negative.push('-');
    } else {
      helper.push(running + value);
      positive.push('-');
      negative.push(Math.abs(value));
    }
    running += value;
  });
  return {
    ...v2BaseOption(spec),
    grid: { left: 42, right: 28, top: 24, bottom: 48, containLabel: true },
    xAxis: { type: 'category', name: dimension.label, data: spec.data.map(row => String(row[dimension.field] ?? 'Unknown')), axisLabel: { ...mutedTextStyle, hideOverlap: true } },
    yAxis: { type: 'value', name: metric.label, axisLabel: { ...mutedTextStyle, formatter: channelAxisFormatter(metric) }, splitLine: { lineStyle: { color: 'var(--border)', opacity: 0.25 } } },
    series: [
      { type: 'bar', stack: 'waterfall', silent: true, itemStyle: { color: 'transparent' }, data: helper },
      { name: 'Increase', type: 'bar', stack: 'waterfall', itemStyle: { color: color('progress') }, data: positive },
      { name: 'Decrease', type: 'bar', stack: 'waterfall', itemStyle: { color: color('critical') }, data: negative },
    ],
  } as EChartsOption;
}

export function visualizationSpecV2ToECharts(spec: VisualizationSpecV2): EChartsOption {
  if (spec.shape === 'scatter') return scatterV2(spec);
  if (spec.shape === 'heatmap') return heatmapV2(spec);
  if (spec.shape === 'waterfall') return waterfallV2(spec);
  if (spec.shape === 'donut') return donutV2(spec);
  return cartesianV2(spec);
}

export function ensureReadableTooltip(option: EChartsOption): EChartsOption {
  const tooltipColors = tooltipTheme();
  const existing = option.tooltip && !Array.isArray(option.tooltip) ? option.tooltip : {};
  const quietAxis = (axis: unknown): unknown => {
    if (Array.isArray(axis)) return axis.map(quietAxis);
    if (!axis || typeof axis !== 'object') return axis;
    const value = axis as Record<string, unknown>;
    return {
      ...value,
      axisLine: { ...((value.axisLine as object) ?? {}), lineStyle: { color: 'var(--border)', opacity: 0.65 } },
      axisTick: { ...((value.axisTick as object) ?? {}), show: false },
      axisLabel: { ...((value.axisLabel as object) ?? {}), color: 'var(--muted-foreground)', hideOverlap: true },
      splitLine: { ...((value.splitLine as object) ?? {}), lineStyle: { color: 'var(--border)', opacity: 0.22 } },
      nameTextStyle: { ...((value.nameTextStyle as object) ?? {}), color: 'var(--muted-foreground)', fontSize: 11 },
    };
  };
  const rawSeries = Array.isArray(option.series) ? option.series : option.series ? [option.series] : [];
  const styledSeries = rawSeries.map((raw, index) => {
    if (!raw || typeof raw !== 'object') return raw;
    const series = raw as Record<string, unknown>;
    const type = String(series.type ?? 'bar');
    const seriesColor = ADANI_PALETTE[index % ADANI_PALETTE.length];
    const itemStyle = { ...((series.itemStyle as object) ?? {}), color: seriesColor };
    if (type === 'pie') {
      const data = Array.isArray(series.data) ? series.data.map((item, itemIndex) => {
        const itemColor = ADANI_PALETTE[itemIndex % ADANI_PALETTE.length];
        return item && typeof item === 'object'
          ? { ...(item as object), itemStyle: { ...(((item as Record<string, unknown>).itemStyle as object) ?? {}), color: itemColor } }
          : { value: item, itemStyle: { color: itemColor } };
      }) : series.data;
      return {
        ...series,
        radius: ['44%', '69%'],
        center: ['50%', '45%'],
        roseType: undefined,
        label: { show: false },
        labelLine: { show: false },
        itemStyle: { ...itemStyle, borderRadius: 6, borderColor: 'var(--card)', borderWidth: 3 },
        data,
      };
    }
    if (type === 'line') {
      return {
        ...series,
        smooth: 0.22,
        showSymbol: true,
        symbol: 'circle',
        symbolSize: 6,
        lineStyle: { ...((series.lineStyle as object) ?? {}), color: seriesColor, width: 3 },
        itemStyle: { ...itemStyle, borderColor: 'var(--card)', borderWidth: 2 },
        areaStyle: series.areaStyle ? { color: seriesColor, opacity: 0.06 } : undefined,
      };
    }
    if (type === 'bar') {
      return {
        ...series,
        barMaxWidth: 26,
        itemStyle: { ...itemStyle, borderRadius: [5, 5, 0, 0] },
      };
    }
    if (type === 'scatter') {
      return { ...series, symbolSize: series.symbolSize ?? 14, itemStyle: { ...itemStyle, opacity: 0.84 } };
    }
    return { ...series, itemStyle };
  });
  const visibleZoom = Array.isArray(option.dataZoom)
    ? option.dataZoom.filter(item => item && typeof item === 'object' && (item as { type?: string }).type === 'inside')
    : option.dataZoom && typeof option.dataZoom === 'object' && (option.dataZoom as { type?: string }).type === 'inside'
      ? option.dataZoom
      : undefined;
  return {
    ...option,
    color: ADANI_PALETTE,
    backgroundColor: 'transparent',
    animationDuration: 520,
    animationEasing: 'cubicOut',
    textStyle: { fontFamily: 'Aptos, Avenir Next, Segoe UI, sans-serif' },
    aria: {
      ...((option.aria as object) ?? {}),
      enabled: true,
      decal: { show: false },
    },
    title: Array.isArray(option.title)
      ? option.title.map(item => ({ ...item, show: false }))
      : option.title && typeof option.title === 'object'
        ? { ...option.title, show: false }
        : option.title,
    toolbox: { show: false },
    dataZoom: visibleZoom,
    legend: option.legend
      ? { ...(Array.isArray(option.legend) ? option.legend[0] : option.legend), bottom: 0, top: undefined, type: 'plain', icon: 'circle', textStyle }
      : option.legend,
    grid: option.grid
      ? { ...(Array.isArray(option.grid) ? option.grid[0] : option.grid), top: 24, bottom: 48, containLabel: true }
      : option.grid,
    xAxis: quietAxis(option.xAxis) as EChartsOption['xAxis'],
    yAxis: quietAxis(option.yAxis) as EChartsOption['yAxis'],
    series: styledSeries as EChartsOption['series'],
    tooltip: {
      ...existing,
      show: true,
      renderMode: 'html',
      confine: true,
      backgroundColor: tooltipColors.background,
      borderColor: tooltipColors.border,
      borderWidth: 1,
      textStyle: {
        ...(existing.textStyle ?? {}),
        color: tooltipColors.foreground,
        fontSize: 12,
      },
      extraCssText: TOOLTIP_CSS,
    },
  };
}

export function expandedChartTooltip(option: EChartsOption): EChartsOption {
  const existing = option.tooltip && !Array.isArray(option.tooltip) ? option.tooltip : {};
  return {
    ...option,
    tooltip: {
      ...existing,
      trigger: 'item',
      triggerOn: 'mousemove',
      confine: true,
      enterable: false,
      axisPointer: { show: false },
      extraCssText: TOOLTIP_CSS,
    },
  };
}
