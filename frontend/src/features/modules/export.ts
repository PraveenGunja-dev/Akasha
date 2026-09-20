/* Module Deliveries — export.
   Mirrors the CEO's PDF tracker layout: title block, a merged two-row header
   with the month group spanning its sub-columns, grouped project rows, a
   totals line and the source-type summary. Built from the rows the user is
   looking at (current filter and grouping), via exceljs, which the project
   already ships for other reports.

   Columns with no live source (D/E, the month-wise plan) are written empty
   rather than filled with a derived guess — same as the screen. */
import { saveAs } from 'file-saver';
import type { ModuleDeliveriesSummary, ModuleProject, ModuleTotals } from './types';

/** Rolling 13-month window starting at the current month, so the plan header
 *  never goes stale (it used to be a fixed 'Aug-26'..'Aug-27' literal). */
function rollingForecastMonths(count = 13): string[] {
  const now = new Date();
  return Array.from({ length: count }, (_, i) => {
    const d = new Date(now.getFullYear(), now.getMonth() + i, 1);
    return `${d.toLocaleString('en-US', { month: 'short' })}-${String(d.getFullYear()).slice(-2)}`;
  });
}

export const FORECAST_MONTHS = rollingForecastMonths();

/** Leading columns, in PDF order. Each spans both header rows. */
const LEAD_COLUMNS: { label: string; width: number; numeric?: boolean }[] = [
  { label: 'Sr', width: 5 },
  { label: 'Project', width: 34 },
  { label: 'P6 Name', width: 30 },
  { label: 'SPV', width: 11 },
  { label: 'Plot', width: 9 },
  { label: 'Category', width: 11 },
  { label: 'Type', width: 9 },
  { label: 'MMS Type', width: 10 },
  { label: 'AGEL / EPC', width: 16 },
  { label: 'OL', width: 7, numeric: true },
  { label: 'Capacity\n(MWac)', width: 10, numeric: true },
  { label: 'Capacity\n(MWp)', width: 10, numeric: true },
  { label: 'Connectivity\nPhase', width: 13 },
  { label: 'LTA', width: 11 },
  { label: 'SCOD', width: 11 },
  { label: 'AOP\n(Plan)', width: 10 },
  { label: 'FTC\nDate', width: 11 },
  { label: 'TC\nDate', width: 11 },
  { label: 'Module\nDate', width: 11 },
  { label: 'Ordered\n(MWp)', width: 10, numeric: true },
  { label: 'Balance\nOrdering\n(MWp)', width: 11, numeric: true },
  { label: 'Total\nReceipt\n(MWp)', width: 10, numeric: true },
  { label: 'Erection\ndone\n(MWp)', width: 10, numeric: true },
  { label: 'Module\nInventory\n(MWp)', width: 11, numeric: true },
  { label: 'Under\nTransit\n(MWp)', width: 10, numeric: true },
  { label: 'Balance\nDispatch\n(MWp)', width: 11, numeric: true },
  { label: 'Status', width: 12 },
];

const MONTH_GROUP_LABEL = 'Month wise Module Requirement at Site (MWp)';
const TRAIL_COLUMN = { label: 'Remarks', width: 46 };

const LEAD_COUNT = LEAD_COLUMNS.length;                       // 25
const MONTH_COUNT = FORECAST_MONTHS.length + 1;               // 13 + Total
const TOTAL_COLS = LEAD_COUNT + MONTH_COUNT + 1;              // + Remarks

const STATUS_LABEL: Record<string, string> = {
  delivered: 'Delivered', in_progress: 'In Progress', ordered: 'Ordered', pending: 'Pending',
};
/** Status fills echo the tracker's own colour coding. State only — never categorical. */
const STATUS_FILL: Record<string, string> = {
  delivered: 'FFD1FADF', in_progress: 'FFFEF0C7', ordered: 'FFD1E9FF', pending: 'FFF2F4F7',
};

const INK = 'FF101828';
const HEADER_BG = 'FF101828';
const GRID = 'FFD0D5DD';
const BAND = 'FFF9FAFB';
const EMPTY_BG = 'FFFBFCFD';

const num = (v: number) => (v > 0 ? Math.round(v * 10) / 10 : null);

export function moduleExportName(ext: 'xlsx') {
  return `Khavda_Module_Deliveries_${new Date().toISOString().slice(0, 10)}.${ext}`;
}

export async function exportModuleDeliveriesXLSX(
  grouped: Record<string, ModuleProject[]>,
  totals: ModuleTotals,
  summary: ModuleDeliveriesSummary,
  filename: string,
) {
  const ExcelJS = await import('exceljs');
  const wb = new ExcelJS.Workbook();
  wb.creator = 'AKASHA';
  wb.created = new Date();

  const ws = wb.addWorksheet('Module Deliveries', {
    views: [{ state: 'frozen', xSplit: 2, ySplit: 5 }],
    pageSetup: {
      orientation: 'landscape', fitToPage: true, fitToWidth: 1, fitToHeight: 0,
      paperSize: 8, margins: { left: 0.2, right: 0.2, top: 0.3, bottom: 0.3, header: 0.1, footer: 0.1 },
    },
  });

  const lastCol = (n: number) => ws.getColumn(n).letter;

  /* ── Title block ─────────────────────────────────────────────────────── */
  ws.mergeCells(`A1:${lastCol(TOTAL_COLS)}1`);
  const title = ws.getCell('A1');
  title.value = 'Khavda FY 26-27 Solar Projects - Module Deliveries & Forecast';
  title.font = { bold: true, size: 14, color: { argb: INK } };
  title.alignment = { vertical: 'middle' };
  ws.getRow(1).height = 22;

  ws.mergeCells(`A2:L2`);
  const sub = ws.getCell('A2');
  sub.value = 'A. Khavda Solar Projects';
  sub.font = { bold: true, size: 10, color: { argb: INK } };

  ws.mergeCells(`M2:${lastCol(TOTAL_COLS)}2`);
  const asOf = ws.getCell('M2');
  asOf.value = `As of ${new Date(summary.generated_at).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' })}`
    + `  ·  ${summary.data_coverage.with_sap_data}/${summary.data_coverage.total_projects} projects with SAP data`;
  asOf.font = { size: 9, color: { argb: 'FF667085' } };
  asOf.alignment = { horizontal: 'right' };

  ws.getRow(3).height = 6;

  /* ── Header: row 4 spans, row 5 month sub-labels ─────────────────────── */
  const h1 = ws.getRow(4);
  const h2 = ws.getRow(5);
  h1.height = 42;
  h2.height = 16;

  LEAD_COLUMNS.forEach((c, i) => {
    const col = i + 1;
    ws.mergeCells(4, col, 5, col);
    ws.getCell(4, col).value = c.label;
    ws.getColumn(col).width = c.width;
  });

  const monthStart = LEAD_COUNT + 1;
  const monthEnd = LEAD_COUNT + MONTH_COUNT;
  ws.mergeCells(4, monthStart, 4, monthEnd);
  ws.getCell(4, monthStart).value = MONTH_GROUP_LABEL;
  [...FORECAST_MONTHS, 'Total'].forEach((mo, i) => {
    const col = monthStart + i;
    ws.getCell(5, col).value = mo;
    ws.getColumn(col).width = 8;
  });

  const remarksCol = TOTAL_COLS;
  ws.mergeCells(4, remarksCol, 5, remarksCol);
  ws.getCell(4, remarksCol).value = TRAIL_COLUMN.label;
  ws.getColumn(remarksCol).width = TRAIL_COLUMN.width;

  for (const rowNo of [4, 5]) {
    for (let col = 1; col <= TOTAL_COLS; col++) {
      const cell = ws.getCell(rowNo, col);
      cell.font = { bold: true, size: 8, color: { argb: 'FFFFFFFF' } };
      cell.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: HEADER_BG } };
      cell.alignment = { horizontal: 'center', vertical: 'middle', wrapText: true };
      cell.border = {
        top: { style: 'thin', color: { argb: HEADER_BG } },
        left: { style: 'thin', color: { argb: 'FF344054' } },
        bottom: { style: 'thin', color: { argb: HEADER_BG } },
        right: { style: 'thin', color: { argb: 'FF344054' } },
      };
    }
  }

  /* ── Data rows ───────────────────────────────────────────────────────── */
  const border = {
    top: { style: 'hair' as const, color: { argb: GRID } },
    left: { style: 'hair' as const, color: { argb: GRID } },
    bottom: { style: 'hair' as const, color: { argb: GRID } },
    right: { style: 'hair' as const, color: { argb: GRID } },
  };

  const groupNames = Object.keys(grouped);
  const showGroups = !(groupNames.length === 1 && groupNames[0] === 'All Projects');

  for (const [groupName, projects] of Object.entries(grouped)) {
    if (showGroups) {
      const gr = ws.addRow([]);
      ws.mergeCells(gr.number, 1, gr.number, TOTAL_COLS);
      const gc = ws.getCell(gr.number, 1);
      const gMwp = projects.reduce((s, p) => s + p.capacity_mwp, 0);
      gc.value = `${groupName}   (${projects.length} project${projects.length !== 1 ? 's' : ''} · ${gMwp.toLocaleString('en-IN', { maximumFractionDigits: 1 })} MWp)`;
      gc.font = { bold: true, size: 9, color: { argb: INK } };
      gc.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FFEAECF0' } };
      gc.alignment = { vertical: 'middle' };
      gr.height = 16;
    }

    projects.forEach((p, idx) => {
      const row = ws.addRow([
        idx + 1,
        p.project_name || p.p6_name,
        p.p6_name || '',
        p.spv || '',
        p.plot || '',
        p.category || '',
        p.type || '',
        p.mms_type || '',
        p.epc || '',
        p.ol > 0 ? p.ol : null,
        num(p.capacity_mwac),
        num(p.capacity_mwp),
        p.connectivity_phase || '',
        p.lta || '',
        p.scod || '',
        p.aop_plan || '',
        p.ftc_date || '',
        p.tc_date || '',
        p.module_date || '',
        num(p.ordered_mwp),
        num(p.balance_ordering_mwp),
        num(p.total_receipt_mwp),
        num(p.erection_done_mwp),
        num(p.module_inventory_mwp),
        num(p.under_transit_mwp),
        num(p.balance_dispatch_mwp),
        STATUS_LABEL[p.status] ?? p.status,
        ...FORECAST_MONTHS.map(() => null),   // month-wise plan — no live source
        null,                                 // month total
        p.remarks || '',
      ]);
      row.height = 14;

      row.eachCell({ includeEmpty: true }, (cell, col) => {
        cell.font = { size: 8, color: { argb: INK } };
        cell.border = border;
        const lead = LEAD_COLUMNS[col - 1];
        cell.alignment = {
          horizontal: lead?.numeric ? 'right' : col > LEAD_COUNT && col < TOTAL_COLS ? 'right' : 'left',
          vertical: 'middle',
          wrapText: col === TOTAL_COLS,
        };
        if (typeof cell.value === 'number') cell.numFmt = '#,##0.0';
        if (col > LEAD_COUNT && col < TOTAL_COLS) {
          cell.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: EMPTY_BG } };
        }
      });

      ws.getCell(row.number, 2).font = { size: 8, bold: true, color: { argb: INK } };
      ws.getCell(row.number, 10).numFmt = '0.00';
      const st = ws.getCell(row.number, 27);
      st.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: STATUS_FILL[p.status] ?? BAND } };
      st.alignment = { horizontal: 'center', vertical: 'middle' };
    });
  }

  /* ── Totals ──────────────────────────────────────────────────────────── */
  const totalRow = ws.addRow([
    '', `Total (${Object.values(grouped).reduce((s, g) => s + g.length, 0)} projects)`,
    '', '', '', '', '', '', '', null,
    num(totals.total_mwac), num(totals.total_mwp),
    '', '', '', '', '', '', '',
    num(totals.ordered_mwp), num(totals.balance_ordering_mwp), num(totals.received_mwp),
    num(totals.erection_mwp), num(totals.inventory_mwp), num(totals.under_transit_mwp),
    num(totals.balance_dispatch_mwp),
    '', ...FORECAST_MONTHS.map(() => null), null, '',
  ]);
  totalRow.height = 18;
  totalRow.eachCell({ includeEmpty: true }, (cell, col) => {
    cell.font = { bold: true, size: 9, color: { argb: INK } };
    cell.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FFEAECF0' } };
    cell.border = { ...border, top: { style: 'medium', color: { argb: 'FF98A2B3' } } };
    cell.alignment = { horizontal: col >= 10 ? 'right' : 'left', vertical: 'middle' };
    if (typeof cell.value === 'number') cell.numFmt = '#,##0.0';
  });

  /* ── Source-type summary (the PDF's bottom block) ────────────────────── */
  ws.addRow([]);
  const sHead = ws.addRow(['Source type', 'Capacity (MWac)', 'Capacity (MWp)', 'Ordered (MWp)', 'Received (MWp)']);
  sHead.eachCell(cell => {
    cell.font = { bold: true, size: 9, color: { argb: 'FFFFFFFF' } };
    cell.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: HEADER_BG } };
    cell.alignment = { horizontal: 'center', vertical: 'middle' };
    cell.border = border;
  });
  Object.entries(summary.type_breakdowns).forEach(([type, b]) => {
    const r = ws.addRow([type, num(b.mwac), num(b.mwp), num(b.ordered), num(b.received)]);
    r.eachCell((cell, col) => {
      cell.font = { size: 9, color: { argb: INK } };
      cell.border = border;
      cell.alignment = { horizontal: col === 1 ? 'left' : 'right' };
      if (typeof cell.value === 'number') cell.numFmt = '#,##0.0';
    });
  });

  /* ── Provenance note — the empty columns are empty on purpose ────────── */
  ws.addRow([]);
  const note = ws.addRow(['Module inventory and in-transit from SAP; SCOD from P6 / trial run unless manually entered; EPC from Primavera EPS.']);
  note.getCell(1).font = { size: 8, italic: true, color: { argb: 'FF667085' } };
  const note2 = ws.addRow(['D/E and the month-wise requirement plan have no live data source and are intentionally left blank.']);
  note2.getCell(1).font = { size: 8, italic: true, color: { argb: 'FF667085' } };

  const buf = await wb.xlsx.writeBuffer();
  saveAs(new Blob([buf], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }), filename);
}
