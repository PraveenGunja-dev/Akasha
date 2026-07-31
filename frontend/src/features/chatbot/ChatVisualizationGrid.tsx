import { useMemo, useState } from 'react';
import type { EChartsOption } from 'echarts';
import ReactECharts from 'echarts-for-react';
import { BarChart3, CalendarDays, Maximize2, Table2, X } from 'lucide-react';
import { motion } from 'framer-motion';

import { visualizationSpecToECharts } from './visualizationAdapter';
import { isVisualizationSpecV1, type ChartVisualization } from './visualizationTypes';

interface ChatVisualizationGridProps {
  visualizations: ChartVisualization[];
}

function friendlyLabel(value: string): string {
  return value.replaceAll('_', ' ').replace(/\b\w/g, character => character.toUpperCase());
}

function ChartDataTable({ rows }: { rows: Array<Record<string, unknown>> }) {
  const columns = useMemo(
    () => Array.from(new Set(rows.flatMap(row => Object.keys(row)))).slice(0, 8),
    [rows],
  );
  if (!rows.length || !columns.length) return null;

  return (
    <div className="chat-chart-table-wrap">
      <table className="chat-chart-table">
        <thead><tr>{columns.map(column => <th key={column}>{friendlyLabel(column)}</th>)}</tr></thead>
        <tbody>
          {rows.slice(0, 100).map((row, rowIndex) => (
            <tr key={rowIndex}>
              {columns.map(column => <td key={column}>{String(row[column] ?? '—')}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function VisualizationCard({ visualization, index }: { visualization: ChartVisualization; index: number }) {
  const [showTable, setShowTable] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const semanticSpec = isVisualizationSpecV1(visualization.spec) ? visualization.spec : null;
  const rows = visualization.data_table ?? semanticSpec?.data_table ?? [];
  const option = useMemo(
    () => semanticSpec
      ? visualizationSpecToECharts(semanticSpec)
      : visualization.spec as EChartsOption,
    [semanticSpec, visualization.spec],
  );
  const renderChart = (isExpanded = false) => (
    <ReactECharts
      option={option}
      style={{ height: isExpanded ? 'min(72vh, 680px)' : 390, width: '100%' }}
      notMerge
      lazyUpdate
      opts={{ renderer: 'svg' }}
      aria-label={visualization.accessibility_description || visualization.title || 'Data visualization'}
    />
  );

  return (
    <motion.article
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.38, delay: Math.min(index * 0.08, 0.24) }}
      className="copilot-chart-card"
    >
      <header className="chart-header">
        <div className="chart-icon"><BarChart3 className="h-4 w-4" /></div>
        <div className="min-w-0 flex-1">
          <h3 className="chart-title">{visualization.title || 'Visualization'}</h3>
          {visualization.subtitle && <p className="chart-subtitle">{visualization.subtitle}</p>}
        </div>
        <div className="chart-actions">
          {rows.length > 0 && (
            <button type="button" onClick={() => setShowTable(value => !value)} title="Toggle data table">
              <Table2 className="h-3.5 w-3.5" />
            </button>
          )}
          <button type="button" onClick={() => setExpanded(true)} title="Expand visualization">
            <Maximize2 className="h-3.5 w-3.5" />
          </button>
          {visualization.chart_type && <span className="chart-type-badge">{friendlyLabel(visualization.chart_type)}</span>}
        </div>
      </header>
      {visualization.summary && <p className="chart-insight">{visualization.summary}</p>}
      <div className="chart-body">{renderChart()}</div>
      {showTable && <ChartDataTable rows={rows} />}
      {visualization.data_as_of && (
        <footer className="chart-freshness"><CalendarDays className="h-3.5 w-3.5" /> Data as of {visualization.data_as_of}</footer>
      )}

      {expanded && (
        <div className="chat-chart-modal" role="dialog" aria-modal="true" aria-label={visualization.title}>
          <div className="chat-chart-modal-card">
            <div className="chat-chart-modal-header">
              <div><h3>{visualization.title}</h3>{visualization.subtitle && <p>{visualization.subtitle}</p>}</div>
              <button type="button" onClick={() => setExpanded(false)} aria-label="Close expanded chart"><X className="h-5 w-5" /></button>
            </div>
            {renderChart(true)}
            {visualization.summary && <p className="chart-insight">{visualization.summary}</p>}
          </div>
        </div>
      )}
    </motion.article>
  );
}

export default function ChatVisualizationGrid({ visualizations }: ChatVisualizationGridProps) {
  if (!visualizations.length) return null;
  return (
    <section className={`chat-visualization-grid ${visualizations.length > 1 ? 'is-multi' : ''}`}>
      {visualizations.slice(0, 4).map((visualization, index) => (
        <VisualizationCard key={`${visualization.chart_type || 'chart'}-${index}`} visualization={visualization} index={index} />
      ))}
    </section>
  );
}
