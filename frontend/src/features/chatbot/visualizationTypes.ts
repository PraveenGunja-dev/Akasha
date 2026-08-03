export interface ChartVisualization {
  schema_version?: 'visualization.v1' | string;
  chart_type?: string;
  title?: string;
  subtitle?: string;
  summary?: string;
  accessibility_description?: string;
  data_as_of?: string;
  data_table?: Array<Record<string, unknown>>;
  report_inclusion?: 'auto' | 'include' | 'exclude';
  spec: unknown;
}

export type VisualizationShape = 'horizontal_bar' | 'vertical_bar' | 'donut' | 'combo' | 'radial_progress' | 'lollipop';
export type VisualizationSeriesShape = 'bar' | 'line' | 'donut';
export type VisualizationValueFormat = 'integer' | 'decimal' | 'percent' | 'days';

export interface VisualizationSeriesV1 {
  name: string;
  shape: VisualizationSeriesShape;
  values: Array<number | null>;
  semantic_color: string;
  value_format: VisualizationValueFormat;
  axis_index: number;
  item_semantic_colors?: string[] | null;
  stack_group?: string | null;
}

export interface VisualizationSpecV1 {
  schema_version: 'visualization.v1';
  chart_id: string;
  chart_type: string;
  shape: VisualizationShape;
  title: string;
  subtitle?: string | null;
  summary: string;
  accessibility_description: string;
  categories: string[];
  series: VisualizationSeriesV1[];
  x_axis_title?: string | null;
  y_axis_title?: string | null;
  data_as_of?: string | null;
  source_tables: string[];
  data_table: Array<Record<string, unknown>>;
  spec_hash: string;
}

export type VisualizationShapeV2 =
  | 'line'
  | 'bar'
  | 'horizontal_bar'
  | 'stacked_bar'
  | 'scatter'
  | 'heatmap'
  | 'waterfall'
  | 'donut';
export type VisualizationFieldTypeV2 = 'categorical' | 'temporal' | 'quantitative' | 'boolean';
export type VisualizationValueFormatV2 = VisualizationValueFormat | 'mw';

export interface VisualizationChannelV2 {
  field: string;
  label: string;
  field_type: VisualizationFieldTypeV2;
  value_format?: VisualizationValueFormatV2 | null;
  unit?: string | null;
  axis_index?: number;
}

export interface VisualizationEncodingV2 {
  x?: VisualizationChannelV2 | null;
  y: VisualizationChannelV2[];
  color?: VisualizationChannelV2 | null;
  label?: VisualizationChannelV2 | null;
}

export interface VisualizationSpecV2 {
  schema_version: 'visualization.v2';
  chart_id: string;
  chart_type: string;
  shape: VisualizationShapeV2;
  title: string;
  subtitle?: string | null;
  summary: string;
  accessibility_description: string;
  encoding: VisualizationEncodingV2;
  data: Array<Record<string, string | number | boolean | null>>;
  data_as_of?: string | null;
  source_tables: string[];
  spec_hash: string;
}

export function isVisualizationSpecV1(value: unknown): value is VisualizationSpecV1 {
  if (!value || typeof value !== 'object') return false;
  const candidate = value as Partial<VisualizationSpecV1>;
  return candidate.schema_version === 'visualization.v1'
    && typeof candidate.chart_id === 'string'
    && ['horizontal_bar', 'vertical_bar', 'donut', 'combo', 'radial_progress', 'lollipop'].includes(String(candidate.shape))
    && Array.isArray(candidate.categories)
    && Array.isArray(candidate.series);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isChannelV2(value: unknown): value is VisualizationChannelV2 {
  if (!isRecord(value)) return false;
  return typeof value.field === 'string'
    && typeof value.label === 'string'
    && ['categorical', 'temporal', 'quantitative', 'boolean'].includes(String(value.field_type));
}

export function isVisualizationSpecV2(value: unknown): value is VisualizationSpecV2 {
  if (!isRecord(value) || value.schema_version !== 'visualization.v2') return false;
  if (typeof value.chart_id !== 'string' || typeof value.chart_type !== 'string') return false;
  if (!['line', 'bar', 'horizontal_bar', 'stacked_bar', 'scatter', 'heatmap', 'waterfall', 'donut'].includes(String(value.shape))) return false;
  if (typeof value.title !== 'string' || typeof value.summary !== 'string' || typeof value.accessibility_description !== 'string') return false;
  if (!isRecord(value.encoding) || !Array.isArray(value.encoding.y) || !value.encoding.y.every(isChannelV2)) return false;
  if (value.encoding.x != null && !isChannelV2(value.encoding.x)) return false;
  if (value.encoding.color != null && !isChannelV2(value.encoding.color)) return false;
  if (value.encoding.label != null && !isChannelV2(value.encoding.label)) return false;
  if (!Array.isArray(value.data) || value.data.length > 500 || !value.data.every(row => {
    if (!isRecord(row)) return false;
    return Object.values(row).every(item => item === null
      || typeof item === 'string'
      || typeof item === 'boolean'
      || (typeof item === 'number' && Number.isFinite(item)));
  })) return false;
  const fields = new Set(value.data.flatMap(row => Object.keys(row)));
  const channels = [value.encoding.x, ...value.encoding.y, value.encoding.color, value.encoding.label]
    .filter((channel): channel is VisualizationChannelV2 => Boolean(channel));
  return channels.every(channel => fields.has(channel.field))
    && Array.isArray(value.source_tables)
    && value.source_tables.every(item => typeof item === 'string')
    && typeof value.spec_hash === 'string'
    && value.spec_hash.startsWith('sha256:');
}
