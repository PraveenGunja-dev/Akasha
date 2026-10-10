"""
Step 1 - extract raw data from the Akasha database (read-only) into CSV.

Runs with the BACKEND's Python, because it reuses the backend's database
connection and the exact project <-> SAP/Ariba mapping the Module Deliveries
page uses (so a figure here reconciles with the screen):

    backend\\venv\\Scripts\\python.exe training_model\\pipelines\\extract.py

Writes training_model/data/raw/*.csv.gz. Nothing is written to the database.
"""
import os
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
os.chdir(ROOT / "backend")          # database.py loads backend/.env

import pandas as pd                 # noqa: E402
from sqlalchemy import text         # noqa: E402

from database import SessionLocal   # noqa: E402

OUT = ROOT / "training_model" / "data" / "raw"

# Block identity is in the activity name (CLAUDE.md: p6_wbs_node.is_block is
# unusable). Solar blocks are written "Block-07", "Block 7", "Block-07 -".
BLOCK_RE = re.compile(r"(?i)\bblock[\s\-_:]*0*(\d{1,3})\b")
# A baseline's own date is in its name ("... - B1 20.01.2025", "- 24-May-25");
# planned_start_date is the project's start, not when the baseline was taken.
DATE_PATTERNS = [
    (re.compile(r"(?<!\d)(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})(?!\d)"), "dmy4"),
    (re.compile(r"(?<!\d)(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{2})(?!\d)"), "dmy2"),
    (re.compile(r"(?<!\d)(\d{1,2})[\s\-]([A-Za-z]{3})[a-z]*[\s\-](\d{2,4})(?!\d)"), "dmony"),
]


def baseline_taken(name):
    """Date a P6 baseline was taken, parsed from its name, or None."""
    if not isinstance(name, str) or not name:
        return None
    for rx, kind in DATE_PATTERNS:
        for m in rx.finditer(name):
            try:
                if kind == "dmy4":
                    return datetime(int(m[3]), int(m[2]), int(m[1])).date()
                if kind == "dmy2":
                    return datetime(2000 + int(m[3]), int(m[2]), int(m[1])).date()
                y = int(m[3]) if len(m[3]) == 4 else 2000 + int(m[3])
                return datetime.strptime(f"{m[1]} {m[2][:3].title()} {y}", "%d %b %Y").date()
            except ValueError:
                continue
    return None


def activity_kind(name):
    n = (name or "").lower()
    if "first time charg" in n:
        if "application" in n:
            return "ftc_application"
        if "approval" in n:
            return "ftc_approval"
        return "ftc"
    if "module installation" in n:
        return "module_installation"
    return "other"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    db = SessionLocal()
    q = lambda sql, **p: pd.read_sql(text(sql), db.bind, params=p)  # noqa: E731

    # -- Register: the solar projects the planner tracks ---------------------
    register = q("""
        select project_id, project, spv_name, category, cluster, subcluster, mms_type,
               capacity_mwac, capacity_mwdc, ol, module_wbs, age6l, spv_plant_code,
               source_of_origin, priority, is_commissioned, is_tracked, lta_date, manual_scod
        from project_mapping where project_id is not null and project_id <> ''""")
    register.to_csv(OUT / "register.csv.gz", index=False)

    # Pooling station per project, from the transmission portal data - the
    # project's location for weather (reference/substations_dms.tsv).
    q("""select m.project_id, m.cluster, string_agg(distinct e.kps, ',') as kps
         from project_mapping m left join tc_project_entry e on e.mapping_id = m.id
         where m.project_id <> '' group by 1, 2""").to_csv(OUT / "project_kps.csv.gz", index=False)

    # -- P6 projects + when their assigned baseline was taken ----------------
    projects = q("""
        select p.p6_object_id as project_object_id, p.project_id, p.name, p.data_date,
               b.name as baseline_name, b.planned_start_date as baseline_planned_start
        from p6_project p
        left join p6_baseline_project b on b.p6_object_id = p.current_baseline_project_object_id
        where p.project_id = any(:ids)""", ids=list(register.project_id.unique()))
    projects["baseline_taken"] = projects.baseline_name.map(baseline_taken)
    projects.to_csv(OUT / "p6_projects.csv.gz", index=False)

    # -- P6 activities of those projects (all - project-level progress needs
    #    them; block-level features use the ones with a block in the name) ---
    acts = q("""
        select project_object_id, activity_id, name, status, type,
               baseline_start_date, baseline_finish_date, planned_start_date, planned_finish_date,
               actual_start_date, actual_finish_date, percent_complete, wbs_name
        from p6_activity where project_object_id = any(:o)""",
             o=[int(x) for x in projects.project_object_id])
    acts["block"] = acts.name.str.extract(BLOCK_RE, expand=False).astype("float")
    acts["kind"] = acts.name.map(activity_kind)
    acts.to_csv(OUT / "p6_activities.csv.gz", index=False)

    # Module MWp per block: the Material resource on P6 "Module Installation"
    # activities is MWp (verified in routers/module_deliveries: per project it
    # lands within 10% of capacity on 47 of 49 projects).
    mwp = q("""
        select a.project_object_id, a.activity_id, sum(r.planned_units) as planned_mwp,
               sum(r.actual_units) as installed_mwp
        from p6_resource_assignment r join p6_activity a on a.p6_object_id = r.activity_object_id
        where a.project_object_id = any(:o) and a.name ilike '%module installation%'
          and r.resource_type = 'Material'
        group by 1, 2""", o=[int(x) for x in projects.project_object_id])
    mwp.to_csv(OUT / "module_install_mwp.csv.gz", index=False)

    # -- SAP module PO lines (POrd only - the SLR rule) ----------------------
    from routers.module_deliveries import _wbs_key
    po = q("""
        select a.purchasing_document as po, a.document_line, a.wbs_element, a.vendor_name,
               a.document_date, a.po_quantities_mw as ordered_mw,
               a.delivered_qty * a.mw_multiplication_factor as delivered_mw_now,
               m.pr_first_release, m.po_first_release
        from mt_poamount a
        left join mt_me2j_po m on m.purchasing_document = a.purchasing_document
        where (a.material_name ilike '%module%' or a.short_text ilike '%module%')
          and a.mw_multiplication_factor > 0 and a.doc_type = 'POrd'""")
    po["wbs_key"] = po.wbs_element.map(_wbs_key)
    # 531x = import (foreign vendor), 451x = domestic - the PO number series.
    po["origin"] = po.po.astype(str).str[:3].map({"531": "import", "451": "domestic"}).fillna("other")
    po.to_csv(OUT / "module_po_lines.csv.gz", index=False)

    # -- Ariba receipts on module lines, allocated to WBS exactly as the
    #    Module Deliveries page does (services.ariba_service) -----------------
    from services.ariba_service import load_ariba_allocations
    rows = []
    for r in load_ariba_allocations(db)["rows"]:
        if not r["is_module"]:
            continue
        for wbs, share in r["allocations"]:
            qty = float(r["grn_quantity"] or 0) if r["gr_posting_date"] else float(r["inbound_delivery_quantity"] or 0)
            rows.append({
                "po": r["po_number"], "item": r["item"], "vendor_name": r["vendor_name"],
                "wbs_key": _wbs_key(wbs), "share": share,
                "dispatch_date": r["ibd_creation_date"], "receipt_date": r["gr_posting_date"],
                "qty": qty * share, "mw_per_unit": r["mw_per_unit"],
                "mwp": qty * share * (r["mw_per_unit"] or 0),
            })
    pd.DataFrame(rows).to_csv(OUT / "module_receipts.csv.gz", index=False)

    # -- P6 project <-> SAP WBS, shared WBS split by capacity (as the page) --
    from routers.module_deliveries import _project_wbs_keys
    from models import ProjectMapping
    cap_by_key = {}
    links = []
    for m in db.query(ProjectMapping).all():
        if not m.project_id:
            continue
        cap = m.capacity_mwdc or (m.capacity_mwac or 0) * float(m.ol or 1.35)
        for key in _project_wbs_keys(m):
            links.append({"project_id": m.project_id, "wbs_key": key, "capacity": cap})
            cap_by_key[key] = cap_by_key.get(key, 0) + cap
    links = pd.DataFrame(links)
    links["share"] = links.apply(lambda r: r.capacity / cap_by_key[r.wbs_key] if cap_by_key[r.wbs_key] else 0, axis=1)
    links.to_csv(OUT / "project_wbs.csv.gz", index=False)

    meta = {"extracted_at": datetime.now().isoformat(timespec="seconds"),
            "register": len(register), "p6_projects": len(projects),
            "activities": len(acts), "block_activities": int(acts.block.notna().sum()),
            "module_po_lines": len(po), "module_receipt_rows": len(rows),
            "project_wbs_links": len(links)}
    pd.Series(meta).to_json(OUT / "extract_meta.json", indent=2)
    for k, v in meta.items():
        print(f"{k:22s} {v}")


if __name__ == "__main__":
    main()
