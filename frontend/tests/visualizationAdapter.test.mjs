import assert from 'node:assert/strict';
import test from 'node:test';

import {
  expandedChartTooltip,
  ensureReadableTooltip,
  visualizationSpecToECharts,
  visualizationSpecV2ToECharts,
} from '../src/features/chatbot/visualizationAdapter.ts';
import { isVisualizationSpecV2 } from '../src/features/chatbot/visualizationTypes.ts';


function spec(shape = 'combo') {
  return {
    schema_version: 'visualization.v1',
    chart_id: 'project.test',
    chart_type: 'planned_vs_actual_progress',
    shape,
    title: 'Planned vs Actual',
    summary: 'Comparison',
    accessibility_description: 'Planned and actual activity finishes.',
    categories: ['2026-01-31'],
    series: [
      {
        name: 'Planned activity finishes',
        shape: 'line',
        values: [42],
        semantic_color: 'primary',
        value_format: 'percent',
        axis_index: 0,
      },
    ],
    source_tables: ['p6_activity'],
    data_table: [],
    spec_hash: 'sha256:test',
  };
}

test('tooltip formatter renders the hovered label, series, and formatted value', () => {
  const option = visualizationSpecToECharts(spec());
  const formatter = option.tooltip.formatter;

  const html = formatter([{
    axisValueLabel: '2026-01-31',
    seriesName: 'Planned activity finishes',
    value: 42,
    color: '#2563EB',
  }]);

  assert.match(html, /2026-01-31/);
  assert.match(html, /Planned activity finishes/);
  assert.match(html, /42%/);
  assert.equal(option.tooltip.renderMode, 'html');
  assert.equal(option.tooltip.confine, true);
  assert.equal(option.aria.decal.show, false);
});

test('radial progress charts keep hover tooltips enabled', () => {
  const radial = spec('radial_progress');
  radial.series[0].shape = 'bar';
  const option = visualizationSpecToECharts(radial);

  assert.equal(option.tooltip.trigger, 'item');
  assert.notEqual(option.tooltip.show, false);
});

test('expanded charts show only the directly hovered item in a bounded tooltip', () => {
  const option = expandedChartTooltip(visualizationSpecToECharts(spec()));

  assert.equal(option.tooltip.trigger, 'item');
  assert.equal(option.tooltip.confine, true);
  assert.equal(option.tooltip.enterable, false);
  assert.match(option.tooltip.extraCssText, /max-height:190px/);
  assert.match(option.tooltip.extraCssText, /overflow:hidden/);
});

test('legacy ECharts options receive a readable confined tooltip', () => {
  const option = ensureReadableTooltip({
    title: { text: 'Duplicated chart title' },
    toolbox: { show: true },
    dataZoom: [{ type: 'slider' }, { type: 'inside' }],
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(0,0,0,0.85)' },
    series: [{ type: 'bar', data: [12], itemStyle: { color: '#059669' } }],
  });

  assert.equal(option.tooltip.show, true);
  assert.equal(option.tooltip.renderMode, 'html');
  assert.equal(option.tooltip.confine, true);
  assert.equal(option.tooltip.textStyle.color, '#111827');
  assert.equal(option.title.show, false);
  assert.equal(option.toolbox.show, false);
  assert.equal(option.dataZoom.length, 1);
  assert.equal(option.dataZoom[0].type, 'inside');
  assert.equal(option.series[0].itemStyle.color, '#0B74B0');
  assert.equal(option.aria.decal.show, false);
});

function specV2(shape = 'bar') {
  return {
    schema_version: 'visualization.v2',
    chart_id: 'dynamic.test',
    chart_type: 'portfolio.procurement_schedule',
    shape,
    title: 'Procurement and Schedule',
    summary: 'Validated comparison.',
    accessibility_description: 'Procurement and schedule comparison.',
    encoding: {
      x: { field: 'project', label: 'Project', field_type: 'categorical', axis_index: 0 },
      y: [
        { field: 'fulfillment', label: 'Fulfilment', field_type: 'quantitative', value_format: 'percent', unit: 'percent', axis_index: 0 },
        { field: 'delay', label: 'Delay', field_type: 'quantitative', value_format: 'days', unit: 'days', axis_index: 1 },
      ],
    },
    data: [{ project: 'Project One', fulfillment: 60, delay: 30 }],
    source_tables: ['p6_project', 'mt_poamount'],
    spec_hash: 'sha256:test',
  };
}

test('V2 grouped bars render compatible dual unit axes', () => {
  const dynamic = specV2();
  assert.equal(isVisualizationSpecV2(dynamic), true);
  const option = visualizationSpecV2ToECharts(dynamic);

  assert.equal(Array.isArray(option.yAxis), true);
  assert.equal(option.yAxis[0].axisLabel.formatter, '{value}%');
  assert.equal(option.yAxis[1].axisLabel.formatter, '{value}d');
  assert.equal(option.series[1].yAxisIndex, 1);
  assert.deepEqual(option.dataset.source, dynamic.data);
});

test('V2 heatmaps use only declared data fields', () => {
  const dynamic = specV2('heatmap');
  dynamic.encoding = {
    x: { field: 'month', label: 'Month', field_type: 'temporal', axis_index: 0 },
    y: [{ field: 'block', label: 'Block', field_type: 'categorical', axis_index: 0 }],
    color: { field: 'delayed', label: 'Delayed activities', field_type: 'quantitative', value_format: 'integer', axis_index: 0 },
  };
  dynamic.data = [{ month: '2026-08', block: 'BLOCK-01', delayed: 2 }];

  const option = visualizationSpecV2ToECharts(dynamic);

  assert.deepEqual(option.series[0].data, [{
    value: [0, 0, 2],
    raw: { month: '2026-08', block: 'BLOCK-01', delayed: 2 },
  }]);
  assert.deepEqual(option.xAxis.data, ['2026-08']);
  assert.deepEqual(option.yAxis.data, ['BLOCK-01']);
});

test('V2 runtime guard rejects missing fields and oversized data', () => {
  const missing = specV2();
  missing.data = [{ project: 'Project One', fulfillment: 60 }];
  assert.equal(isVisualizationSpecV2(missing), false);

  const oversized = specV2();
  oversized.data = Array.from({ length: 501 }, (_, index) => ({
    project: `Project ${index}`,
    fulfillment: 50,
    delay: 1,
  }));
  assert.equal(isVisualizationSpecV2(oversized), false);
});
