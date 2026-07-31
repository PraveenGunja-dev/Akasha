export interface ChartVisualization {
  schema_version?: 'visualization.v1' | string;
  chart_type?: string;
  title?: string;
  subtitle?: string;
  summary?: string;
  accessibility_description?: string;
  data_as_of?: string;
  data_table?: Array<Record<string, unknown>>;
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

export function isVisualizationSpecV1(value: unknown): value is VisualizationSpecV1 {
  if (!value || typeof value !== 'object') return false;
  const candidate = value as Partial<VisualizationSpecV1>;
  return candidate.schema_version === 'visualization.v1'
    && typeof candidate.chart_id === 'string'
    && ['horizontal_bar', 'vertical_bar', 'donut', 'combo', 'radial_progress', 'lollipop'].includes(String(candidate.shape))
    && Array.isArray(candidate.categories)
    && Array.isArray(candidate.series);
}
