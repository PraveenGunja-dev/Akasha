import { useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import type { EChartsOption } from 'echarts';
import ReactECharts from 'echarts-for-react';
import { BarChart3, CalendarDays, FileCheck2, FileMinus2, FileQuestion, Maximize2, Minimize2, Table2 } from 'lucide-react';
import { motion } from 'framer-motion';

import {
  ensureReadableTooltip,
  visualizationSpecToECharts,
  visualizationSpecV2ToECharts,
} from './visualizationAdapter';
import {
  isVisualizationSpecV1,
  isVisualizationSpecV2,
  type ChartVisualization,
} from './visualizationTypes';

interface ChatVisualizationGridProps {
  visualizations: ChartVisualization[];
  onReportInclusionChange?: (index: number, value: 'auto' | 'include' | 'exclude') => Promise<void>;
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

function VisualizationCard({
  visualization,
  index,
  onReportInclusionChange,
}: {
  visualization: ChartVisualization;
  index: number;
  onReportInclusionChange?: ChatVisualizationGridProps['onReportInclusionChange'];
}) {
  const [showTable, setShowTable] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [savingInclusion, setSavingInclusion] = useState(false);
  const v1Spec = isVisualizationSpecV1(visualization.spec) ? visualization.spec : null;
  const v2Spec = isVisualizationSpecV2(visualization.spec) ? visualization.spec : null;
  const legacyOption = !v1Spec && !v2Spec && visualization.schema_version !== 'visualization.v2'
    && visualization.spec && typeof visualization.spec === 'object'
    ? visualization.spec as EChartsOption
    : null;
  const rows = visualization.data_table ?? v1Spec?.data_table ?? v2Spec?.data ?? [];
  const option = useMemo(
    () => v2Spec
      ? visualizationSpecV2ToECharts(v2Spec)
      : v1Spec
        ? visualizationSpecToECharts(v1Spec)
        : legacyOption
          ? ensureReadableTooltip(legacyOption)
          : null,
    [legacyOption, v1Spec, v2Spec],
  );
  const reportInclusion = visualization.report_inclusion ?? 'auto';
  const nextReportInclusion = reportInclusion === 'auto' ? 'include' : reportInclusion === 'include' ? 'exclude' : 'auto';
  const ReportIcon = reportInclusion === 'include' ? FileCheck2 : reportInclusion === 'exclude' ? FileMinus2 : FileQuestion;

  useEffect(() => {
    if (!expanded) return undefined;
    const previousOverflow = document.body.style.overflow;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setExpanded(false);
    };
    document.body.style.overflow = 'hidden';
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [expanded]);

  const renderChart = (isExpanded = false) => option ? (
      <ReactECharts
        option={option}
        style={{ height: isExpanded ? '100%' : 390, width: '100%' }}
        className={isExpanded ? 'chat-chart-expanded-canvas' : undefined}
        notMerge
        lazyUpdate
        opts={{ renderer: 'svg' }}
        aria-label={visualization.accessibility_description || visualization.title || 'Data visualization'}
      />
    ) : (
      <div role="status" className="flex h-full min-h-48 items-center justify-center px-6 text-center text-sm text-muted-foreground">
        This saved visualization uses an unsupported or invalid specification. Its validated data table remains available.
      </div>
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
          {onReportInclusionChange && (
            <button
              type="button"
              disabled={savingInclusion}
              onClick={async () => {
                setSavingInclusion(true);
                try {
                  await onReportInclusionChange(index, nextReportInclusion);
                } finally {
                  setSavingInclusion(false);
                }
              }}
              title={`Report selection: ${friendlyLabel(reportInclusion)}. Click for ${friendlyLabel(nextReportInclusion)}.`}
              aria-label={`Report selection is ${reportInclusion}`}
            >
              <ReportIcon className="h-3.5 w-3.5" />
            </button>
          )}
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

      {expanded && typeof document !== 'undefined' && createPortal(
        <div
          className="chat-chart-modal"
          role="dialog"
          aria-modal="true"
          aria-label={visualization.title || 'Expanded visualization'}
          onMouseDown={event => {
            if (event.currentTarget === event.target) setExpanded(false);
          }}
        >
          <div className="chat-chart-modal-card">
            <div className="chat-chart-modal-header">
              <div><h3>{visualization.title}</h3>{visualization.subtitle && <p>{visualization.subtitle}</p>}</div>
              <button
                type="button"
                className="chat-chart-restore-button"
                onClick={() => setExpanded(false)}
                aria-label="Restore chart to dashboard"
                title="Exit full screen"
              >
                <Minimize2 className="h-5 w-5" />
                <span>Restore</span>
              </button>
            </div>
            <div className="chat-chart-modal-body">{renderChart(true)}</div>
            {visualization.summary && <p className="chart-insight">{visualization.summary}</p>}
          </div>
        </div>,
        document.body,
      )}
    </motion.article>
  );
}

export default function ChatVisualizationGrid({ visualizations, onReportInclusionChange }: ChatVisualizationGridProps) {
  if (!visualizations.length) return null;
  return (
    <section className={`chat-visualization-grid ${visualizations.length > 1 ? 'is-multi' : ''}`}>
      {visualizations.slice(0, 4).map((visualization, index) => (
        <VisualizationCard
          key={`${visualization.chart_type || 'chart'}-${index}`}
          visualization={visualization}
          index={index}
          onReportInclusionChange={onReportInclusionChange}
        />
      ))}
    </section>
  );
}
