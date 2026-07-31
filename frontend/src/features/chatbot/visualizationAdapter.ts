import type { EChartsOption } from 'echarts';

import type { VisualizationSeriesV1, VisualizationSpecV1 } from './visualizationTypes';

const SEMANTIC_COLORS: Record<string, string> = {
  primary: '#2563EB',
  progress: '#059669',
  warning: '#D97706',
  critical: '#DC2626',
  neutral: '#98A2B3',
  teal: '#0891B2',
};

function color(name: string): string {
  return SEMANTIC_COLORS[name] ?? SEMANTIC_COLORS.primary;
}

function valueFormatter(series: VisualizationSeriesV1): string {
  if (series.value_format === 'percent') return '{value}%';
  if (series.value_format === 'days') return '{value}d';
  return '{value}';
}

const textStyle = { color: 'var(--foreground)' };
const mutedTextStyle = { color: 'var(--muted-foreground)' };

function baseOption(spec: VisualizationSpecV1): EChartsOption {
  return {
    animationDuration: 550,
    animationEasing: 'cubicOut',
    aria: {
      enabled: true,
      decal: { show: true },
      description: spec.accessibility_description,
    },
    textStyle: { fontFamily: 'Inter, ui-sans-serif, system-ui, sans-serif' },
    tooltip: {
      trigger: spec.shape === 'donut' ? 'item' : 'axis',
      backgroundColor: 'rgba(0,0,0,0.85)',
      textStyle: { color: '#fff' },
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
      name: spec.x_axis_title ?? undefined,
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
    })),
  };
}

function radialProgress(spec: VisualizationSpecV1): EChartsOption {
  const values = spec.series[0]?.values ?? [];
  const count = Math.max(1, spec.categories.length);
  return {
    ...baseOption(spec),
    tooltip: { show: false },
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
    ] : { type: 'value', axisLabel: mutedTextStyle },
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
