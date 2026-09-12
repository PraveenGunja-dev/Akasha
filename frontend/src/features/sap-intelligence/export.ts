/* SAP Intelligence — export. CSV built from the rows the user is looking at
   (current filters, sort, and selection), fetched from the server in pages
   so an export of 20k lines does not require them all in the DOM. Excel via
   exceljs, which the project already ships for other reports. */
import { saveAs } from 'file-saver';
import { sapApi } from './api';
import { STATUS_LABEL } from './format';
import type { LedgerColumn, POLine, SAPFilters } from './types';

export const COLUMN_LABEL: Record<LedgerColumn, string> = {
  po: 'PO number', buyer: 'Buyer', vendor: 'Vendor', material_code: 'Material code', material: 'Material',
  date: 'PO date', status: 'Status', ordered_cr: 'PO value (₹ Cr)', delivered_cr: 'Delivered (₹ Cr)', outstanding_cr: 'Still to deliver (₹ Cr)', wbs: 'WBS',
};

const cell = (r: POLine, c: LedgerColumn): string | number => {
  switch (c) {
    case 'status': return STATUS_LABEL[r.status];
    case 'date': return r.date ?? '';
    default: { const v = r[c]; return v == null ? '' : v; }
  }
};

const csvEscape = (v: string | number) => { const s = String(v); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };

export async function fetchAllLines(f: SAPFilters, sort: string, order: 'asc' | 'desc', max = 20_000, onProgress?: (n: number) => void): Promise<POLine[]> {
  const out: POLine[] = [];
  let page = 1;
  for (;;) {
    const r = await sapApi.pos(f, page, 200, sort, order);
    out.push(...r.rows); onProgress?.(out.length);
    if (out.length >= r.total || out.length >= max || r.rows.length === 0) break;
    page += 1;
  }
  return out.slice(0, max);
}

export function exportCSV(rows: POLine[], columns: LedgerColumn[], filename: string) {
  const head = columns.map(c => COLUMN_LABEL[c]).join(',');
  const body = rows.map(r => columns.map(c => csvEscape(cell(r, c))).join(',')).join('\n');
  saveAs(new Blob(['﻿' + head + '\n' + body], { type: 'text/csv;charset=utf-8' }), filename);
}

export async function exportXLSX(rows: POLine[], columns: LedgerColumn[], filename: string, meta: Record<string, string>) {
  const ExcelJS = await import('exceljs');
  const wb = new ExcelJS.Workbook();
  const ws = wb.addWorksheet('Procurement ledger');
  ws.addRow(['AKASHA — SAP Intelligence export']).font = { bold: true };
  Object.entries(meta).forEach(([k, v]) => ws.addRow([k, v]));
  ws.addRow([]);
  const hdr = ws.addRow(columns.map(c => COLUMN_LABEL[c])); hdr.font = { bold: true };
  rows.forEach(r => ws.addRow(columns.map(c => cell(r, c))));
  ws.columns.forEach(col => { col.width = 18; });
  const buf = await wb.xlsx.writeBuffer();
  saveAs(new Blob([buf], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }), filename);
}

export const exportName = (suffix: string, ext: 'csv' | 'xlsx') => `SAP_Intelligence_${suffix}_${new Date().toISOString().slice(0, 10)}.${ext}`;
