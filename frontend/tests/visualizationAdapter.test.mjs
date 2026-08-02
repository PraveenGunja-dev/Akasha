import assert from 'node:assert/strict';
import test from 'node:test';

import {
  ensureReadableTooltip,
  visualizationSpecToECharts,
} from '../src/features/chatbot/visualizationAdapter.ts';


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
});

test('radial progress charts keep hover tooltips enabled', () => {
  const radial = spec('radial_progress');
  radial.series[0].shape = 'bar';
  const option = visualizationSpecToECharts(radial);

  assert.equal(option.tooltip.trigger, 'item');
  assert.notEqual(option.tooltip.show, false);
});

test('legacy ECharts options receive a readable confined tooltip', () => {
  const option = ensureReadableTooltip({
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(0,0,0,0.85)' },
    series: [{ type: 'bar', data: [12] }],
  });

  assert.equal(option.tooltip.show, true);
  assert.equal(option.tooltip.renderMode, 'html');
  assert.equal(option.tooltip.confine, true);
  assert.equal(option.tooltip.textStyle.color, '#111827');
});
