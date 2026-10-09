"""Audit the Ariba ZIBDSESREP load and its mapping to projects.

Run after every Ariba load. Exits non-zero if any HARD check fails, so a bad
load cannot reach the Module Deliveries page unnoticed.

    cd backend && ./venv/Scripts/python.exe scripts/check_ariba.py [--no-file]

HARD (must hold):
  1. The table matches the extract: every material IBD line loaded, once.
  2. No duplicate rows, no total rows, no service rows, no 'nan' / '1234.0' text.
  3. Every mapped row's WBS shares sum to exactly 1.
  4. No Ariba quantity is counted twice across projects: per PO, the sum over
     every project row on the Module page never exceeds what Ariba holds.
  5. Within a project, every delivery event (PO, dispatch date, receipt date)
     appears once.
REPORTED (data quality, not failures):
  - Ariba GRN vs SAP CO actual GR quantity, per PO line.
  - Ariba GRN vs SAP Total Receipt, per project (the proof coverage).
  - Unmapped lines (PO not in the SAP CO extract) and module POs with no
    Ariba record at all.
"""
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd  # noqa: E402
from sqlalchemy import text  # noqa: E402

from database import SessionLocal  # noqa: E402
from services.ariba_service import (  # noqa: E402
    COLUMNS, find_ariba_file, load_ariba_allocations)

failures: list[str] = []


def check(ok: bool, label: str, detail: str = "") -> None:
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}{(' - ' + detail) if detail else ''}")
    if not ok:
        failures.append(label)


def main(read_file: bool = True) -> int:
    db = SessionLocal()
    q = lambda sql, **p: db.execute(text(sql), p).fetchall()  # noqa: E731

    print("\n1. Table vs extract")
    n_rows = q("select count(*) from ariba_inbound_delivery")[0][0]
    if read_file and (path := find_ariba_file()):
        df = pd.read_excel(path)
        df = df.rename(columns={c: COLUMNS[k] for c in df.columns
                                if (k := " ".join(str(c).split()).lower()) in COLUMNS})
        expected = len(df[df["po_number"].notna() & df["ibd_creation_date"].notna()].drop_duplicates())
        check(n_rows == expected, "every material IBD line loaded once",
              f"{os.path.basename(path)}: {expected:,} expected, {n_rows:,} in table")
    else:
        print(f"  [SKIP] extract comparison ({n_rows:,} rows in table)")

    print("\n2. Row hygiene")
    dup = q("""select count(*) from (
                 select 1 from ariba_inbound_delivery
                 group by po_number, item, material_number, material_description, po_quantity, uom,
                          company_code, vendor_code, vendor_name, inbound_delivery_quantity,
                          rejected_quantity, ibd_creation_date, plant, gr_posting_date, grn_quantity,
                          currency, ariba_invoice_date, checklist_number, checklist_status, checklist_date
                 having count(*) > 1) d""")[0][0]
    check(dup == 0, "no duplicate rows", f"{dup} duplicated row groups")
    bad = q("""select
                 sum(case when po_number is null or po_number = '' then 1 else 0 end),
                 sum(case when ibd_creation_date is null then 1 else 0 end),
                 sum(case when 'nan' in (lower(coalesce(po_number,'')), lower(coalesce(item,'')),
                                         lower(coalesce(checklist_status,'')), lower(coalesce(checklist_number,'')),
                                         lower(coalesce(material_number,''))) then 1 else 0 end),
                 sum(case when po_number like '%.0' or item like '%.0' or vendor_code like '%.0'
                           or checklist_number like '%.0' then 1 else 0 end),
                 sum(case when (checklist_number is null) <> (checklist_status is null) then 1 else 0 end)
               from ariba_inbound_delivery""")[0]
    check(not bad[0], "no total rows (blank PO)", str(bad[0] or 0))
    check(not bad[1], "no service-entry rows (no IBD date)", str(bad[1] or 0))
    check(not bad[2], "no 'nan' text values", str(bad[2] or 0))
    check(not bad[3], "no float-formatted codes ('1234.0')", str(bad[3] or 0))
    check(not bad[4], "checklist number and status filled together", str(bad[4] or 0))

    print("\n3. Mapping to WBS")
    alloc = load_ariba_allocations(db)
    rows = alloc["rows"]
    bad_share = [r for r in rows if r["allocations"] and abs(sum(s for _, s in r["allocations"]) - 1) > 1e-6]
    check(not bad_share, "WBS shares of every mapped row sum to 1", f"{len(bad_share)} rows off")
    by = Counter(r["mapped_by"] for r in rows)
    print(f"  rows by PO line: {by['po_item']:,} | by single-WBS PO: {by['po']:,} | "
          f"unmapped: {by[None]:,} ({alloc['unmapped_lines']:,} lines, PO not in SAP CO extract)")

    grn = defaultdict(float)
    for r in rows:
        grn[(r["po_number"], str(r["item"]).lstrip("0"))] += r["grn_quantity"] or 0
    co = {(str(po), str(it).lstrip("0")): float(qty or 0) for po, it, qty in q("""
            select po_document, po_item, sum(quantity) from sap_co_line
            where kind = 'actual' and po_item is not null and po_document = any(:pos)
            group by 1, 2""", pos=list({r["po_number"] for r in rows}))}
    both = [(k, grn[k], co[k]) for k in grn if k in co]
    agree = sum(1 for _, a, s in both if abs(a - s) <= 0.01 * max(abs(s), 1))
    print(f"  Ariba GRN = SAP CO actual GR qty on {agree:,} of {len(both):,} PO lines "
          f"({agree / max(len(both), 1):.1%})")

    print("\n4-5. Module Deliveries page: no double counting")
    from routers.module_deliveries import get_module_deliveries_summary
    res = get_module_deliveries_summary(scenario="baseline", priorities=None, portfolio=None, phase=None, db=db)
    projects = res["projects"]

    ariba_po_qty = defaultdict(float)
    for r in rows:
        if r["is_module"] and r["allocations"]:
            ariba_po_qty[r["po_number"]] += (r["grn_quantity"] if r["gr_posting_date"] else r["inbound_delivery_quantity"]) or 0
    page_po_qty = defaultdict(float)
    dup_events = 0
    for p in projects:
        ev = (p.get("procurement") or {}).get("events", [])
        keys = Counter((e["po"], e["dispatch_date"], e["receipt_date"]) for e in ev)
        dup_events += sum(c - 1 for c in keys.values() if c > 1)
        for e in ev:
            page_po_qty[e["po"]] += e["qty"]
    over = {po: (page_po_qty[po], ariba_po_qty[po]) for po in page_po_qty
            if page_po_qty[po] > ariba_po_qty[po] * 1.0001 + 0.5}
    check(not over, "no PO counted more than once across projects",
          ", ".join(f"{po}: page {a:,.0f} > Ariba {b:,.0f}" for po, (a, b) in list(over.items())[:5]))
    check(dup_events == 0, "each delivery event appears once per project", f"{dup_events} duplicates")
    short = {po: (page_po_qty.get(po, 0), q_) for po, q_ in ariba_po_qty.items()
             if page_po_qty.get(po, 0) < q_ * 0.999 - 0.5}
    if short:
        print(f"  note: {len(short)} module PO(s) only partly shown - their WBS carries no project on the "
              f"mapping sheet: " + ", ".join(f"{po} ({a:,.0f} of {b:,.0f})" for po, (a, b) in list(short.items())[:5]))

    print("\nProof coverage: Ariba GRN vs SAP Total Receipt (MWp)")
    print(f"  {'Project':34} {'SAP rcv':>9} {'Ariba GRN':>10} {'cover':>6} {'await':>6} {'ckl':>9}")
    for p in sorted(projects, key=lambda p: -p["total_receipt_mwp"]):
        c = p.get("procurement") or {}
        if p["total_receipt_mwp"] <= 0 and not c.get("lots"):
            continue
        cov = f"{c['received_mwp'] / p['total_receipt_mwp']:.0%}" if p["total_receipt_mwp"] > 0 else "-"
        label = "no Ariba record" if not c.get("lots") else cov
        print(f"  {(p['project_name'] or '')[:34]:34} {p['total_receipt_mwp']:9.1f} {c.get('received_mwp', 0):10.1f} "
              f"{label:>6} {c.get('awaiting_grn_mwp', 0):6.1f} {c.get('checklist_created', 0):>4}/{c.get('checklist_due', 0):<4}")
    tot_sap = sum(p["total_receipt_mwp"] for p in projects)
    tot_ar = sum((p.get("procurement") or {}).get("received_mwp", 0) for p in projects)
    print(f"  {'TOTAL':34} {tot_sap:9.1f} {tot_ar:10.1f} {tot_ar / max(tot_sap, 1e-9):6.0%}")

    print(f"\n{'ALL HARD CHECKS PASSED' if not failures else 'FAILED: ' + '; '.join(failures)}")
    db.close()
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(read_file="--no-file" not in sys.argv))
