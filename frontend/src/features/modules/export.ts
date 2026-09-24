/* Module Deliveries — export.
   Mirrors the CEO's PDF tracker layout: title block, a merged two-row header
   with the month group spanning its sub-columns, grouped project rows, a
   totals line and the source-type summary. Built from the rows the user is
   looking at (current filter and grouping), via exceljs, which the project
   already ships for other reports.

   Columns with no live source (D/E, the month-wise plan) are written empty
   rather than filled with a derived guess — same as the screen. */
import { saveAs } from 'file-saver';
import type { PaperSize } from 'exceljs';
import type { ModuleDeliveriesSummary, ModuleProject, ModuleTotals } from './types';

// exceljs's PaperSize enum omits code 8 (A3), which this wide landscape
// table needs — the numeric OOXML code is still valid at runtime.
import { PLANNING_RULES } from './planningRules';

const A3: PaperSize = 8 as PaperSize;

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
  { label: 'Priority', width: 9 },
  { label: 'OL', width: 7, numeric: true },
  { label: 'Capacity\n(MWac)', width: 10, numeric: true },
  { label: 'Capacity\n(MWp)', width: 10, numeric: true },
  { label: 'Connectivity\nPhase', width: 13 },
  { label: 'LTA', width: 11 },
  { label: 'SCOD', width: 11 },
  { label: 'AOP\n(Plan)', width: 10 },
  { label: 'Ordered\n(MWp)', width: 10, numeric: true },
  { label: 'Balance\nOrdering\n(MWp)', width: 11, numeric: true },
  { label: 'Total\nReceipt\n(MWp)', width: 10, numeric: true },
  { label: 'Erection\ndone\n(MWp)', width: 10, numeric: true },
  { label: 'Module\nInventory\n(MWp)', width: 11, numeric: true },
  { label: 'Under\nTransit\n(MWp)', width: 10, numeric: true },
  { label: 'Balance\nDispatch\n(MWp)', width: 11, numeric: true },
  { label: 'Status', width: 12 },
];

const monthGroupLabel = (unit: 'both' | 'mwp' | 'mwac') =>
  `Month wise Module Requirement at Site (${unit === 'both' ? 'MWp / MWac' : unit === 'mwp' ? 'MWp' : 'MWac'})`;
// FTC/TC/Module sit after the month-wise plan, right before Remarks (user
// decision 2026-09-20) — they used to follow AOP, ahead of the SAP columns.
// Widened from the original 11/46: at that width a 5-6 phase project (or the
// AI's now much longer remarks, since the delay/exclusion explanations were
// added) wrapped to 8-10 lines inside a fixed 14pt row and visibly bled into
// the row below — this exact garbling is what prompted the redesign
// (user report 2026-09-21).
const DATE_COLUMNS: { label: string; width: number }[] = [
  { label: 'FTC\nDate', width: 24 },
  { label: 'TC\nDate', width: 24 },
  { label: 'Module\nDate', width: 24 },
];
const TRAIL_COLUMN = { label: 'Remarks', width: 70 };

const LEAD_COUNT = LEAD_COLUMNS.length;                       // 24
const MONTH_COUNT = FORECAST_MONTHS.length + 1;               // 13 + Total
const DATE_COUNT = DATE_COLUMNS.length;                       // FTC, TC, Module
const TOTAL_COLS = LEAD_COUNT + MONTH_COUNT + DATE_COUNT + 1; // + Remarks

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


type RichRun = { text: string; font?: { color?: { argb: string }; bold?: boolean; name?: string } };

/** A multi-phase date string is joined with " · " on screen, where it reads as
 *  one line; forced into a much narrower Excel column that became several
 *  unreadable wrapped fragments per phase. One phase per line is exact and
 *  legible instead of an arbitrary character-wrap. */
function splitPhases(value: string): string[] {
  return value ? value.split(' · ') : [];
}

/** Rich-text runs for an FTC/TC/Module Date cell, one phase per line, colouring
 *  a phase red once its own date has passed — the same distinction the
 *  on-screen DatedPhases component draws. */
function dateCellRichText(value: string): { richText: RichRun[] } | string {
  const phases = splitPhases(value);
  if (phases.length === 0) return '';
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const runs: RichRun[] = [];
  phases.forEach((seg, i) => {
    if (i > 0) runs.push({ text: '\n' });
    const m = seg.match(/(\d{1,2})-([A-Za-z]{3})-(\d{2})/);
    let overdue = false;
    if (m) {
      const months = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'];
      const monIdx = months.indexOf(m[2].toLowerCase());
      if (monIdx !== -1) {
        const dt = new Date(2000 + parseInt(m[3], 10), monIdx, parseInt(m[1], 10));
        overdue = dt < today;
      }
    }
    runs.push(overdue ? { text: seg, font: { color: { argb: 'FFD92D20' }, name: 'Adani' } } : { text: seg, font: { name: 'Adani' } });
  });
  return { richText: runs };
}

type ChipData = { label: string; phase: string | null; type: 'tc' | 'module' | 'ftc' };

function getChipsForMonth(p: ModuleProject, mo: string, cellVal: number, milestoneFilter: string, unitToggle: 'both' | 'mwp' | 'mwac'): ChipData[] {
  const chips: ChipData[] = [];
  if (!p.balance_ordering_mwp || p.balance_ordering_mwp <= 0) return chips;

  if (cellVal > 0) {
      const ac = Math.round(p.ol > 0 ? cellVal / p.ol : cellVal / 1.35);
      const labelStr = unitToggle === 'mwp' ? `${Math.round(cellVal)}` : unitToggle === 'mwac' ? `${ac}` : `${Math.round(cellVal)} / ${ac}`;
      chips.push({ label: labelStr, phase: null, type: 'tc' });
  }

  const now = new Date();
  const parseSegments = (val: string, type: 'tc' | 'module' | 'ftc') => {
    if (!val) return;
    val.split(' · ').forEach(seg => {
      if (seg.includes(mo)) {
        const dateMatch = seg.match(/(\d{1,2})-([A-Za-z]{3})-(\d{2,4})/);
        if (dateMatch) {
          const parsed = new Date(`${dateMatch[2]} ${dateMatch[1]}, 20${dateMatch[3].length === 2 ? dateMatch[3] : dateMatch[3].slice(-2)}`);
          if (!isNaN(parsed.getTime()) && parsed < now) return; 
        }

        const parts = seg.split(': ');
        if (parts.length > 1) {
          const mwMatch = parts[0].match(/\((.*?MW)\)/i);
          if (mwMatch) {
            const acMatch = mwMatch[1].match(/([\d\.]+)/);
            if (acMatch) {
              const ac = parseFloat(acMatch[1]);
              const dc = Math.round(ac * (p.ol > 0 ? p.ol : 1.35));
              const labelStr = unitToggle === 'mwp' ? `${dc}` : unitToggle === 'mwac' ? `${ac}` : `${dc} / ${ac}`;
              chips.push({ label: labelStr, phase: parts[0], type });
            } else {
              chips.push({ label: mwMatch[1], phase: parts[0], type });
            }
          } else {
            chips.push({ label: '-', phase: parts[0], type });
          }
        } else {
          const phasesCount = val.split(' · ').length;
          const dc = p.balance_ordering_mwp / (phasesCount || 1);
          const ac = Math.round(p.ol > 0 ? dc / p.ol : dc / 1.35);
          const labelStr = unitToggle === 'mwp' ? `${Math.round(dc)}` : unitToggle === 'mwac' ? `${ac}` : `${Math.round(dc)} / ${ac}`;
          chips.push({ label: labelStr, phase: null, type });
        }
      }
    });
  };
  
  parseSegments(p.tc_date || '', 'module');
  parseSegments(p.ftc_date || '', 'ftc');
  return chips.filter(c => milestoneFilter === 'all' || c.type === milestoneFilter);
}

function monthCellRichText(p: ModuleProject, mo: string, val: number, milestoneFilter: string, unitToggle: 'both' | 'mwp' | 'mwac'): { richText: RichRun[] } | string {
  const chips = getChipsForMonth(p, mo, val, milestoneFilter, unitToggle);
  if (chips.length === 0) {
    return '-';
  }

  const runs: RichRun[] = [];
  chips.forEach((c, i) => {
    if (i > 0) runs.push({ text: '\n' });
    let color = 'FF2563EB'; // Blue (tc)
    if (c.type === 'module') color = 'FFD97706'; // Amber (module)
    if (c.type === 'ftc') color = 'FF059669'; // Emerald (ftc)
    
    runs.push({ text: `[ ${c.label} ]`, font: { color: { argb: color }, bold: true, name: 'Adani' } });
  });
  return { richText: runs };
}



/** How many lines a cell will actually occupy once wrapped at colWidthChars,
 *  used to size the row instead of leaving it at a fixed height regardless of
 *  content — a fixed 14pt row is what let long remarks and multi-phase dates
 *  overflow into the row below. */
function estimateWrappedLines(text: string, colWidthChars: number): number {
  if (!text) return 1;
  const perLine = Math.max(6, colWidthChars);
  return text.split('\n').reduce((sum, line) => sum + Math.max(1, Math.ceil(line.length / perLine)), 0);
}

// Rounded to whole MWp, matching the on-screen table (user decision
// 2026-09-21) — a decimal place read as false precision on figures that are
// mostly derived/apportioned anyway.
const num = (v: number) => (v > 0 ? Math.round(v) : null);

export function moduleExportName(ext: 'xlsx') {
  return `Khavda_Module_Deliveries_${new Date().toISOString().slice(0, 10)}.${ext}`;
}

export async function exportModuleDeliveriesXLSX(
  grouped: Record<string, ModuleProject[]>,
  totals: ModuleTotals,
  summary: ModuleDeliveriesSummary,
  filename: string,
  milestoneFilter: 'all' | 'tc' | 'module' | 'ftc' = 'all',
  unitToggle: 'both' | 'mwp' | 'mwac' = 'both'
) {
  const ExcelJS = await import('exceljs');
  const wb = new ExcelJS.Workbook();
  wb.creator = 'AKASHA';
  wb.created = new Date();

  const ws = wb.addWorksheet('Module Deliveries', {
    views: [{ state: 'frozen', xSplit: 2, ySplit: 5 }],
    pageSetup: {
      orientation: 'landscape', fitToPage: true, fitToWidth: 1, fitToHeight: 0,
      paperSize: A3, margins: { left: 0.2, right: 0.2, top: 0.3, bottom: 0.3, header: 0.1, footer: 0.1 },
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
  ws.getCell(4, monthStart).value = monthGroupLabel(unitToggle);
  [...FORECAST_MONTHS, 'Total'].forEach((mo, i) => {
    const col = monthStart + i;
    ws.getCell(5, col).value = mo;
    ws.getColumn(col).width = 14;
  });

  const dateStart = monthEnd + 1;
  DATE_COLUMNS.forEach((c, i) => {
    const col = dateStart + i;
    ws.mergeCells(4, col, 5, col);
    ws.getCell(4, col).value = c.label;
    ws.getColumn(col).width = c.width;
  });

  const remarksCol = TOTAL_COLS;
  ws.mergeCells(4, remarksCol, 5, remarksCol);
  ws.getCell(4, remarksCol).value = TRAIL_COLUMN.label;
  ws.getColumn(remarksCol).width = TRAIL_COLUMN.width;

  for (const rowNo of [4, 5]) {
    for (let col = 1; col <= TOTAL_COLS; col++) {
      const cell = ws.getCell(rowNo, col);
      cell.font = { bold: true, size: 8, color: { argb: 'FFFFFFFF' }, name: 'Adani' };
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
      gc.font = { bold: true, size: 9, color: { argb: INK }, name: 'Adani' };
      gc.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FFEAECF0' } };
      gc.alignment = { vertical: 'middle' };
      gr.height = 16;
    }

    projects.forEach((p, idx) => {
      const ftcText = p.ftc_date || (p.ftc_all_charged ? 'No pending FTC' : '');
      const tcText = p.tc_date || '';
      const modText = p.module_date || '';
      const remarksText = p.remarks ? (p.ai_suggestion ? `${p.remarks} | AI Suggestion: ${p.ai_suggestion}` : p.remarks) : '';

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
        (p.priority || 'std').toUpperCase(),
        p.ol > 0 ? p.ol : null,
        num(p.capacity_mwac),
        num(p.capacity_mwp),
        p.connectivity_phase || '',
        p.lta || '',
        p.scod || '',
        p.aop_plan || '',
        num(p.ordered_mwp),
        num(p.balance_ordering_mwp),
        num(p.total_receipt_mwp),
        num(p.erection_done_mwp),
        num(p.module_inventory_mwp),
        num(p.under_transit_mwp),
        num(p.balance_dispatch_mwp),
        STATUS_LABEL[p.status] ?? p.status,
        ...FORECAST_MONTHS.map(mo => monthCellRichText(p, mo, p.month_mwp?.[mo] || 0, milestoneFilter, unitToggle)),
        num(p.balance_ordering_mwp || 0),
        dateCellRichText(ftcText),
        dateCellRichText(tcText),
        dateCellRichText(modText),
        remarksText,
      ]);

      // Sized to the tallest wrapped cell instead of a fixed 14pt — that
      // fixed height is what let a 5-6 phase date cell or a long AI remark
      // overflow past its row and visually bleed into the one below
      // (user report 2026-09-21). One phase = one line for the date columns
      // (exact, since splitPhases drives the rich-text line breaks too);
      // remarks is prose, so it's a character-wrap estimate instead.
      const linesNeeded = Math.max(
        1,
        splitPhases(ftcText).length,
        splitPhases(tcText).length,
        splitPhases(modText).length,
        estimateWrappedLines(remarksText, TRAIL_COLUMN.width),
        ...FORECAST_MONTHS.map(mo => Math.max(1, getChipsForMonth(p, mo, p.month_mwp?.[mo] || 0, milestoneFilter, unitToggle).length))
      );
      row.height = Math.max(14, linesNeeded * 11 + 3);

      // same tier for every populated month cell in this row removed

      row.eachCell({ includeEmpty: true }, (cell, col) => {
        cell.font = { size: 8, color: { argb: INK }, name: 'Adani' };
        cell.border = border;
        const lead = LEAD_COLUMNS[col - 1];
        const inMonthBlock = col > LEAD_COUNT && col <= monthEnd;
        const inDateBlock = col >= dateStart && col < dateStart + DATE_COUNT;
        cell.alignment = {
          horizontal: lead?.numeric ? 'right' : inMonthBlock ? 'right' : 'left',
          vertical: 'middle',
          wrapText: col === TOTAL_COLS || inDateBlock || inMonthBlock,
        };
        if (typeof cell.value === 'number') cell.numFmt = '#,##0';
        if (inMonthBlock) {
          
          cell.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: EMPTY_BG } };
        }
      });

      ws.getCell(row.number, 2).font = { size: 8, bold: true, color: { argb: INK }, name: 'Adani' };
      ws.getCell(row.number, 11).numFmt = '0.00';
      const st = ws.getCell(row.number, LEAD_COUNT);
      st.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: STATUS_FILL[p.status] ?? BAND } };
      st.alignment = { horizontal: 'center', vertical: 'middle' };
    });
  }

  /* ── Totals ──────────────────────────────────────────────────────────── */
  const totalRow = ws.addRow([
    '', `Total (${Object.values(grouped).reduce((s, g) => s + g.length, 0)} projects)`,
    '', '', '', '', '', '', '', '', null,
    num(totals.total_mwac), num(totals.total_mwp),
    '', '', '', '',
    num(totals.ordered_mwp), num(totals.balance_ordering_mwp), num(totals.received_mwp),
    num(totals.erection_mwp), num(totals.inventory_mwp), num(totals.under_transit_mwp),
    num(totals.balance_dispatch_mwp),
    '',
    ...FORECAST_MONTHS.map(mo => {
      const allRows = Object.values(grouped).flat();
      const mTot = allRows.reduce((s, p) => s + (p.month_mwp?.[mo] || 0), 0);
      return num(mTot);
    }),
    num(Object.values(grouped).flat().reduce((s, p) => s + (p.balance_ordering_mwp || 0), 0)),
    '', '', '',
    '',
  ]);
  totalRow.height = 18;
  totalRow.eachCell({ includeEmpty: true }, (cell, col) => {
    cell.font = { bold: true, size: 9, color: { argb: INK }, name: 'Adani' };
    cell.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FFEAECF0' } };
    cell.border = { ...border, top: { style: 'medium', color: { argb: 'FF98A2B3' } } };
    cell.alignment = { horizontal: col >= 10 ? 'right' : 'left', vertical: 'middle' };
    if (typeof cell.value === 'number') cell.numFmt = '#,##0';
  });

  /* ── Source-type summary (the PDF's bottom block) ────────────────────── */
  ws.addRow([]);
  const sHead = ws.addRow(['Source type', 'Capacity (MWac)', 'Capacity (MWp)', 'Ordered (MWp)', 'Received (MWp)']);
  sHead.eachCell(cell => {
    cell.font = { bold: true, size: 9, color: { argb: 'FFFFFFFF' }, name: 'Adani' };
    cell.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: HEADER_BG } };
    cell.alignment = { horizontal: 'center', vertical: 'middle' };
    cell.border = border;
  });
  Object.entries(summary.type_breakdowns).forEach(([type, b]) => {
    const r = ws.addRow([type, num(b.mwac), num(b.mwp), num(b.ordered), num(b.received)]);
    r.eachCell((cell, col) => {
      cell.font = { size: 9, color: { argb: INK }, name: 'Adani' };
      cell.border = border;
      cell.alignment = { horizontal: col === 1 ? 'left' : 'right' };
      if (typeof cell.value === 'number') cell.numFmt = '#,##0';
    });
  });

  /* ── Provenance note ─────────────────────────────────────────────────── */
  ws.addRow([]);
  const note = ws.addRow(['Module inventory and in-transit from SAP; SCOD from P6 / trial run unless manually entered; EPC from Primavera EPS.']);
  note.getCell(1).font = { size: 8, italic: true, color: { argb: 'FF667085' }, name: 'Adani' };
  const note2 = ws.addRow(['Month-wise module requirement at site is generated by the Akasha AI Planning Engine: backward-scheduled from P6 FTC milestones (-45d TC, -lead time) and leveled against source supplier monthly limits.']);
  note2.getCell(1).font = { size: 8, italic: true, color: { argb: 'FF667085' }, name: 'Adani' };

  /* ── Sheet 2: the order, phase by phase ──────────────────────────────
     The grid gives one MWp figure per month. A planner placing the order
     needs to know which phases that figure is made of and when each must
     actually be raised, so the breakdown gets a sheet of its own rather
     than being trapped in a tooltip. */
  const ps = wb.addWorksheet('Phase Orders', {
    views: [{ state: 'frozen', ySplit: 2 }],
    pageSetup: { orientation: 'landscape', fitToPage: true, fitToWidth: 1, fitToHeight: 0, paperSize: A3 },
  });
  ps.mergeCells('A1:M1');
  const pTitle = ps.getCell('A1');
  pTitle.value = 'Order breakdown by phase — each phase is ordered in full before the next begins. Dates are as they now fall: a moved order moves its TC and FTC with it.';
  pTitle.font = { bold: true, size: 11, color: { argb: 'FFFFFFFF' }, name: 'Adani' };
  pTitle.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: HEADER_BG } };
  pTitle.alignment = { horizontal: 'left', vertical: 'middle' };
  ps.getRow(1).height = 20;

  const pCols = [
    { h: 'Project', w: 30 }, { h: 'Plot', w: 8 }, { h: 'Order month', w: 12 },
    { h: 'Phase', w: 10 }, { h: 'Order qty (MWp)', w: 15 }, { h: 'Phase (MWac)', w: 13 },
    { h: 'Place order by', w: 14 }, { h: 'TC date', w: 12 }, { h: 'FTC date', w: 12 },
    { h: 'Slip vs plan', w: 12 }, { h: 'Planned order', w: 14 },
    { h: 'Status', w: 16 }, { h: 'LTA', w: 12 },
  ];
  const pHead = ps.addRow(pCols.map(c => c.h));
  pHead.eachCell(cell => {
    cell.font = { bold: true, size: 9, color: { argb: 'FFFFFFFF' }, name: 'Adani' };
    cell.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: HEADER_BG } };
    cell.alignment = { horizontal: 'center', vertical: 'middle', wrapText: true };
    cell.border = border;
  });
  pCols.forEach((c, i) => { ps.getColumn(i + 1).width = c.w; });

  let pBand = false;
  Object.values(grouped).flat().forEach(proj => {
    const byMonth = proj.month_phases || {};
    const rowsFor = FORECAST_MONTHS.flatMap(mo => (byMonth[mo] || []).map(ph => ({ mo, ph })));
    if (rowsFor.length === 0) return;
    pBand = !pBand;
    rowsFor.forEach(({ mo, ph }) => {
      const status = ph.overdue ? 'Overdue' : ph.shifted ? 'Moved by quota' : 'On schedule';
      /* The placed dates are the ones that now apply: when quota moves an
         order later, its TC and FTC move with it. The original plan is kept
         in its own column so the slip can be seen rather than inferred. */
      const r = ps.addRow([
        proj.project_name || proj.p6_name, proj.plot || '', mo, ph.phase_label,
        Math.round(ph.mwp), ph.mw_ac || null,
        ph.placed_order_date, ph.placed_tc_date, ph.placed_ftc_date,
        ph.revised ? `${ph.slip_months > 0 ? '+' : ''}${ph.slip_months} mo` : '-',
        ph.revised ? ph.order_date : '-',
        status, proj.lta || '',
      ]);
      r.eachCell((cell, col) => {
        const isStatus = col === 12;
        const isSlip = col === 10;
        cell.font = {
          size: 9, name: 'Adani',
          color: { argb: (isStatus && ph.overdue) || (isSlip && ph.revised) ? 'FFB42318' : INK },
          bold: (isStatus && ph.overdue) || (isSlip && ph.revised),
          italic: col === 11,
        };
        cell.border = border;
        cell.alignment = { horizontal: col === 1 ? 'left' : col === 5 || col === 6 ? 'right' : 'center' };
        if (typeof cell.value === 'number') cell.numFmt = '#,##0';
        if (pBand) cell.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: BAND } };
        if (isStatus && ph.overdue) {
          cell.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FFFEE4E2' } };
        }
      });
    });
  });

  /* ── Sheet 3: every rule behind the numbers ──────────────────────────
     So a figure questioned in a meeting can be traced to the rule that
     produced it, and to the file that enforces it. */
  const rs = wb.addWorksheet('Planning Rules', {
    views: [{ state: 'frozen', ySplit: 2 }],
    pageSetup: { orientation: 'portrait', fitToPage: true, fitToWidth: 1, fitToHeight: 0 },
  });
  rs.mergeCells('A1:D1');
  const rTitle = rs.getCell('A1');
  rTitle.value = 'How this plan is built — every rule applied, and where it is enforced';
  rTitle.font = { bold: true, size: 11, color: { argb: 'FFFFFFFF' }, name: 'Adani' };
  rTitle.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: HEADER_BG } };
  rTitle.alignment = { horizontal: 'left', vertical: 'middle' };
  rs.getRow(1).height = 20;

  const rHead = rs.addRow(['Area', 'Rule', 'What it does', 'Enforced in']);
  rHead.eachCell(cell => {
    cell.font = { bold: true, size: 9, color: { argb: 'FFFFFFFF' }, name: 'Adani' };
    cell.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: HEADER_BG } };
    cell.alignment = { horizontal: 'center', vertical: 'middle' };
    cell.border = border;
  });
  rs.getColumn(1).width = 24;
  rs.getColumn(2).width = 28;
  rs.getColumn(3).width = 95;
  rs.getColumn(4).width = 24;

  PLANNING_RULES.forEach(group => {
    const gr = rs.addRow([group.title, '', '', '']);
    rs.mergeCells(`A${gr.number}:D${gr.number}`);
    gr.getCell(1).font = { bold: true, size: 9, color: { argb: INK }, name: 'Adani' };
    gr.getCell(1).fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FFEAECF0' } };
    gr.getCell(1).border = border;
    group.rules.forEach(rule => {
      const r = rs.addRow(['', rule.name, rule.detail, rule.source || '']);
      r.eachCell((cell, col) => {
        cell.font = {
          size: 9, name: 'Adani', bold: col === 2,
          color: { argb: col === 4 ? 'FF667085' : INK },
          italic: col === 4,
        };
        cell.border = border;
        cell.alignment = { vertical: 'top', wrapText: col === 3, horizontal: 'left' };
      });
      r.height = Math.max(14, Math.ceil(rule.detail.length / 95) * 12);
    });
  });

  const buf = await wb.xlsx.writeBuffer();
  saveAs(new Blob([buf], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }), filename);
}
