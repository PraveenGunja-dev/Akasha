"""
SAP CO line-item extracts -> sap_co_line.

The Commitment.xlsx and Actual.xlsx CO line-item extracts are the planned
replacement for ZPSPS007 as the PO / SLR source (decided 2026-09-29). They
carry what ZPSPS lacks - real units of measure, goods-receipt actuals, material
and PR-vs-PO per line - but until a full-scope export reconciles against ZPSPS
this table is built alongside mt_poamount / mt_slr_data and nothing on screen
reads it. `reconcile()` reports how far the two sources are apart.

Rules (see slr_rules.co_po_lines_only) are stored as per-line flags, never
applied by deleting lines, so every figure can be audited.

    cd backend && ./venv/Scripts/python.exe scripts/ingest_sap_co.py [--reconcile]
"""
import glob
import os
import re
import sys
from datetime import datetime
from typing import Optional

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.ingest_sap_data import SAP_DATA_DIR  # noqa: E402
from scripts.ingest_slr_data import build_wbs_mapping  # noqa: E402

REPO_DATA = os.path.join(os.path.dirname(SAP_DATA_DIR))
# Only files named Actual* / Commitment*. The SharePoint folder also holds a
# CJI3.xlsx, which is NOT this Actual extract (user, 2026-09-29) - it must never
# be picked up in its place.
CO_FILE_PATTERNS = {
    "commitment": re.compile(r"^Commitment.*\.xlsx?$", re.I),
    "actual": re.compile(r"^Actual.*\.xlsx?$", re.I),
}
# Where to look, newest first wins: the SAP download folder (SharePoint lands
# files there), then Data/SLR where the first extracts were dropped by hand.
SEARCH_DIRS = [SAP_DATA_DIR, os.path.join(REPO_DATA, "SLR")]
MASTER_NAME = "AKASHA SAP MASTER FILE (1) 1.xlsx"   # the file the SLR ingest maps with

# Consolidated EPC contract lines excluded by the SLR rule. The CO extracts
# spell the SPGS contracts both "SPGS Supply" and "SPG Supply" / "SPG Service";
# matching only "SPGS" let Rs 10,116 Cr of "SPG ..." lines through (2026-09-29).
# Whole word, so an unrelated description starting with these letters is kept.
OVERHEAD = re.compile(r"^\s*(SPGS?|PMC|ISA)\b", re.I)
# A PV panel: "MODULE,SOLAR,590WP,..." / "MODULE,615W,LR8-66HGD-615M,LONGI".
# Not "MODULE,PN:100002099,ARCTECH" (tracker electronics) or module cleaning robots.
PANEL = re.compile(r"^MODULE,(SOLAR|\d{3}\s?W)|MODULE,.*\b\d{3}\s?WP?\b", re.I)
MODULE_WBS = {"MODULES SUPPLY (FOB)", "PV MODULES", "PV MODULE"}

COLUMNS = {
    "commitment": {
        "company_code": "Company Code", "ref_category": "Reference document category",
        "po_document": "Ref Document Number", "po_item": "Reference item",
        "document_date": "Document Date", "wbs_element": "WBS Element", "wbs_fallback": "Object",
        "wbs_description": "CO object name", "project_definition": "Project Definition",
        "material": "Material", "material_description": "Material Description",
        "cost_element": "Cost element", "cost_element_descr": "Cost element descr.",
        "quantity": "Total Quantity", "uom": "Unit of Measure", "value_inr": "Val/COArea Crcy",
        "supplier_code": "Supplier",
    },
    "actual": {
        "company_code": "Company Code", "po_document": "Purchasing Document", "po_item": "Item",
        "document_number": "Document Number", "document_type": "Document type",
        "document_date": "Document Date", "posting_date": "Posting Date",
        "wbs_element": "WBS Element", "wbs_description": "CO object name",
        "project_definition": "Project Definition", "material": "Material",
        "material_description": "Material Description", "cost_element": "Cost Element",
        "cost_element_descr": "Cost element descr.", "quantity": "Total quantity",
        "uom": "Posted unit of meas.", "value_inr": "Val/COArea Crcy",
    },
}


def find_co_file(kind: str) -> Optional[str]:
    hits = [f for d in SEARCH_DIRS for f in glob.glob(os.path.join(d, "*"))
            if CO_FILE_PATTERNS[kind].match(os.path.basename(f))]
    return max(hits, key=os.path.getmtime) if hits else None


def find_master() -> Optional[str]:
    exact = os.path.join(SAP_DATA_DIR, MASTER_NAME)
    if os.path.exists(exact):
        return exact
    hits = glob.glob(os.path.join(REPO_DATA, "**", "AKASHA SAP MASTER FILE*.xlsx"), recursive=True)
    return max(hits, key=os.path.getmtime) if hits else None


def _master_prefix(wbs, wmap) -> Optional[str]:
    """Longest SAP Master code the WBS starts with - the SLR ingest's rule."""
    if not isinstance(wbs, str) or not wbs.strip():
        return None
    s = wbs.strip().upper().replace("-", "")
    s = s[1:] if s.startswith("H") else s
    for n in range(min(len(s), 10), 2, -1):
        if s[:n] in wmap:
            return s[:n]
    return None


def _txt(s: pd.Series) -> pd.Series:
    return s.fillna("").astype(str).str.strip()


def prepare(commitment_path: str, actual_path: str, master_path: str) -> pd.DataFrame:
    """Both extracts -> one frame of sap_co_line rows with every rule flag.
    Pure: reads files, writes nothing."""
    wmap = build_wbs_mapping(master_path)
    frames = []
    for kind, path in (("commitment", commitment_path), ("actual", actual_path)):
        raw = pd.read_excel(path, dtype=str)
        cols = COLUMNS[kind]
        df = pd.DataFrame({k: raw[v] for k, v in cols.items() if v in raw.columns and k != "wbs_fallback"})
        if kind == "commitment" and cols["wbs_fallback"] in raw.columns:
            df["wbs_element"] = df["wbs_element"].where(_txt(df["wbs_element"]) != "", raw[cols["wbs_fallback"]])
        # The export's own subtotal / grand-total rows: no company, no WBS, no document.
        doc = _txt(df.get("po_document", pd.Series(index=df.index, dtype=str)))
        subtotal = (_txt(df["company_code"]) == "") & (_txt(df["wbs_element"]) == "") & (doc == "")
        df = df[~subtotal].copy()
        df["kind"] = kind
        df["source_file"] = os.path.basename(path)
        frames.append(df)
    df = pd.concat(frames, ignore_index=True)

    for c in ("po_document", "ref_category", "document_type", "wbs_description", "material_description", "uom"):
        if c not in df.columns:
            df[c] = ""
        df[c] = _txt(df[c])
    df["value_inr"] = pd.to_numeric(df["value_inr"], errors="coerce").fillna(0.0)
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce")
    for c in ("document_date", "posting_date"):
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce")

    df["master_prefix"] = df["wbs_element"].map(lambda w: _master_prefix(w, wmap))
    df["is_goods_receipt"] = (df["kind"] == "actual") & (df["document_type"].str.upper() == "WE")
    df["is_module"] = (df["material_description"].str.match(PANEL)
                       | df["wbs_description"].str.upper().isin(MODULE_WBS))
    overhead_pos = set(df.loc[df["wbs_description"].str.match(OVERHEAD) & (df["po_document"] != ""), "po_document"])
    df["is_overhead_po"] = df["po_document"].isin(overhead_pos)

    is_order = ((df["kind"] == "commitment") & (df["ref_category"] == "POrd")) | \
               ((df["kind"] == "actual") & (df["po_document"] != ""))
    df["counts_as_po"] = (is_order & ~df["is_overhead_po"] & df["master_prefix"].notna()
                          & (df["value_inr"] != 0))
    return df


def ingest_co(commitment_path: str = None, actual_path: str = None, master_path: str = None) -> dict:
    """Replace sap_co_line from the newest Commitment + Actual extracts.
    Returns a summary; raises FileNotFoundError when either extract is absent."""
    from database import SessionLocal, engine
    import models
    from sqlalchemy import text

    commitment_path = commitment_path or find_co_file("commitment")
    actual_path = actual_path or find_co_file("actual")
    master_path = master_path or find_master()
    for label, p in (("Commitment", commitment_path), ("Actual", actual_path), ("SAP Master", master_path)):
        if not p or not os.path.exists(p):
            raise FileNotFoundError(f"{label} extract not found")

    df = prepare(commitment_path, actual_path, master_path)
    models.Base.metadata.create_all(bind=engine, tables=[models.SAPCOLine.__table__])
    db = SessionLocal()
    try:
        pos = [p for p in df["po_document"].unique() if p]
        vendors = {}
        for i in range(0, len(pos), 2000):
            for po, name in db.execute(text("select purchasing_document, vendor_name from mt_me2j_po "
                                            "where purchasing_document = any(:p)"), {"p": pos[i:i + 2000]}):
                vendors[po] = name
        df["vendor_name"] = df["po_document"].map(vendors)

        now = datetime.utcnow()
        keep = [c.name for c in models.SAPCOLine.__table__.columns if c.name not in ("id", "upload_time")]
        rows = []
        for rec in df.reindex(columns=keep).to_dict("records"):
            rec = {k: (None if (v is None or (isinstance(v, float) and pd.isna(v)) or v is pd.NaT or v == "") else v)
                   for k, v in rec.items()}
            for k in ("document_date", "posting_date"):
                if rec.get(k) is not None:
                    rec[k] = rec[k].to_pydatetime()
            rec["upload_time"] = now
            rows.append(rec)
        db.query(models.SAPCOLine).delete()
        for i in range(0, len(rows), 5000):
            db.bulk_insert_mappings(models.SAPCOLine, rows[i:i + 5000])
        db.commit()
    finally:
        db.close()

    counted = df[df["counts_as_po"]]
    cr = lambda x: round(float(x) / 1e7, 1)
    summary = {
        "files": {"commitment": os.path.basename(commitment_path), "actual": os.path.basename(actual_path),
                  "master": os.path.basename(master_path)},
        "lines": int(len(df)),
        "po_count": int(counted["po_document"].nunique()),
        "commitment_cr": cr(counted.loc[counted["kind"] == "commitment", "value_inr"].sum()),
        "actual_cr": cr(counted.loc[counted["kind"] == "actual", "value_inr"].sum()),
        "delivered_cr": cr(counted.loc[counted["is_goods_receipt"], "value_inr"].sum()),
        "module_cr": cr(counted.loc[counted["is_module"], "value_inr"].sum()),
        "preq_cr": cr(df.loc[(df["kind"] == "commitment") & (df["ref_category"] == "PReq")
                             & df["master_prefix"].notna() & (df["value_inr"] != 0), "value_inr"].sum()),
        "overhead_pos_excluded": int(df.loc[df["is_overhead_po"], "po_document"].nunique()),
        "unmatched_wbs_lines": int(df["master_prefix"].isna().sum()),
        "vendor_named_pos": int(sum(1 for p in counted["po_document"].unique() if vendors.get(p))),
    }
    summary["po_value_cr"] = round(summary["commitment_cr"] + summary["actual_cr"], 1)
    return summary


def po_source() -> str:
    """Which extract the app's PO tables are built from: "co" (default since
    2026-09-29 - the CO Commitment + Actual extracts) or "zsps" (ZPSPS007, the
    previous source). Set AKASHA_PO_SOURCE=zsps to go back without a deploy."""
    return (os.getenv("AKASHA_PO_SOURCE") or "co").strip().lower()


def zsps_kept_prefixes(db) -> set:
    """WBS prefixes (first 6 chars, e.g. "H-5XA1") that stay on ZPSPS.

    The CO extracts delivered so far cover solar and wind only; BESS extracts
    are to follow (user, 2026-09-29). So BESS WBS - the CPAG register's supply
    and civil WBS plus every prefix of a project the master puts in the BESS
    cluster - keep their ZPSPS rows. A prefix drops off this list by itself as
    soon as the Commitment extract carries PO lines for it, so loading the BESS
    CO files switches BESS over with no code change. Commitment, not just any
    CO line: PO value is Actual + Commitment, and the 2026-10-05 Actual already
    carries BESS (Rs 6,027 Cr) while Commitment does not - switching on Actual
    alone would drop every open order from the BESS PO value."""
    from sqlalchemy import text
    from routers.bess import BESS_PROJECTS
    from services import project_identity
    bess = {w for c in BESS_PROJECTS.values() for w in (c.get("supply_wbs"), c.get("civil_wbs")) if w}
    for ident in project_identity.resolve_all(db, phase="all"):
        if (ident.cluster or ident.portfolio or "").strip().upper() == "BESS":
            bess.update(ident.sap_wbs_prefixes)
    in_co = {r[0] for r in db.execute(text(
        "select distinct left(wbs_element, 6) from sap_co_line "
        "where counts_as_po and kind = 'commitment'"))}
    return {p for p in bess if p not in in_co}


def _me2j_enrichment() -> dict:
    """PO-line facts the CO extracts lack, from the newest ME2J: company code,
    plant, storage location, buyer, vendor code and the deletion indicator.

    Keyed three ways, most specific first: (PO, WBS, material), (PO, WBS), PO.
    A value is offered only when every ME2J line under that key agrees, so a PO
    that delivers to two plants never gets one of them guessed. ME2J repeats
    two header names; the PO line is the first `Item`, and the deletion flag
    (L = deleted, S = blocked) is in whichever `Deletion Indicator` is filled."""
    from scripts.ingest_sap_data import find_sap_file
    path = find_sap_file("me2j", SAP_DATA_DIR)
    if not path:
        return {}
    head = list(pd.read_excel(path, nrows=0).columns)
    wanted = {"Purchasing Document", "WBS Element", "Material", "Company Code", "Plant",
              "Storage Location", "Buyer Name", "Vendor/supplying plant"}
    idx = [i for i, c in enumerate(head) if str(c).split(".")[0] in wanted | {"Deletion Indicator"}]
    df = pd.read_excel(path, usecols=idx, dtype=str)
    dels = [c for c in df.columns if c.startswith("Deletion Indicator")]
    df["_del"] = df[dels].bfill(axis=1).iloc[:, 0] if dels else None
    # Plain identifiers, so itertuples keeps the names (it renames any column
    # with a space or "/" to a positional _N).
    df = df.rename(columns={c: str(c).split(".")[0].replace(" ", "_").replace("/", "_")
                            for c in df.columns if not str(c).startswith("Deletion Indicator")})
    df = df.loc[:, ~df.columns.duplicated()]
    clean = lambda v: (str(v).strip() if v is not None and str(v).strip().lower() not in ("", "nan", "none") else None)
    def code(v):
        v = clean(v)
        return v[:-2] if v and v.endswith(".0") else v
    fields = {}
    for r in df.itertuples(index=False):
        row = r._asdict()
        po = code(row.get("Purchasing_Document"))
        if not po:
            continue
        vendor = clean(row.get("Vendor_supplying_plant"))
        facts = {
            "company_code": code(row.get("Company_Code")),
            "plant_code": code(row.get("Plant")),
            "storage_location": clean(row.get("Storage_Location")),
            "buyer_name": clean(row.get("Buyer_Name")),
            "vendor_code": (vendor.split()[0] if vendor and vendor.split()[0].isdigit() else None),
            "deletion_indicator": clean(row.get("_del")),
        }
        wbs, mat = clean(row.get("WBS_Element")), code(row.get("Material"))
        for key in ((po, wbs, mat), (po, wbs), (po,)):
            bucket = fields.setdefault(key, {})
            for f, v in facts.items():
                bucket.setdefault(f, set()).add(v)
    out = {}
    for key, bucket in fields.items():
        out[key] = {f: next(iter(vs)) for f, vs in bucket.items() if len(vs) == 1 and None not in vs}
        # Deleted only when every line under the key is deleted.
        if bucket.get("deletion_indicator") and bucket["deletion_indicator"] != {"L"}:
            out[key].pop("deletion_indicator", None)
    return out


def build_po_tables() -> dict:
    """Rebuild mt_poamount and mt_slr_data - the two tables every PO / SLR
    figure in the app reads (dashboards, financials, CPAG, /api/v1/sap, /slr)
    - from sap_co_line, so the whole app switches source at once.

    Same meaning as the ZPSPS rows they replace:
      net_order_value_inr  = commitment + actual   (PO value)
      still_to_deliver_inr = commitment            (open)
      delivered_value_inr_cr = actual / 1e7        (booked against the PO)
    One mt_poamount row per (PO, WBS, material, unit) so quantities never mix
    units - the reason ZPSPS quantities could not be charted. SLR rows are one
    per (PO, SAP-Master prefix, type), as the ZPSPS SLR ingest aggregates.
    Refuses to run on an empty CO load, leaving the live tables untouched."""
    from database import SessionLocal
    import models
    from sqlalchemy import text
    from scripts.ingest_sap_data import _extract_wattage_from_text

    db = SessionLocal()
    try:
        keep = sorted(zsps_kept_prefixes(db))
        po_lines = db.execute(text("""
            select po_document, wbs_element, coalesce(material, ''), coalesce(uom, ''),
                   max(company_code), max(wbs_description), max(material_description),
                   max(vendor_name), max(supplier_code), min(document_date),
                   min(po_item) filter (where kind = 'commitment'),
                   sum(value_inr) filter (where kind = 'commitment'),
                   sum(value_inr) filter (where kind = 'actual'),
                   sum(quantity) filter (where kind = 'commitment'),
                   sum(quantity) filter (where kind = 'actual'),
                   bool_or(is_module)
            from sap_co_line where counts_as_po and not (left(wbs_element, 6) = any(:keep))
            group by 1, 2, 3, 4"""), {"keep": keep}).fetchall()
        if not po_lines:
            raise RuntimeError("sap_co_line has no PO lines - refusing to replace the PO tables")

        now = datetime.utcnow()
        po_rows = []
        for (po, wbs, mat, uom, cc, wdesc, mdesc, vendor, vcode, ddate, item,
             c_val, a_val, c_qty, a_qty, is_mod) in po_lines:
            c_val, a_val = float(c_val or 0), float(a_val or 0)
            c_qty, a_qty = float(c_qty or 0), float(a_qty or 0)
            mw = _extract_wattage_from_text(mdesc or "") if is_mod else None
            qty = c_qty + a_qty
            po_rows.append(dict(
                company_code=cc, purchasing_document=po, wbs_element=wbs,
                material_code=mat or None, material_name=wdesc, short_text=mdesc,
                vendor_name=vendor, vendor_code=vcode, document_date=ddate, document_line=item,
                order_quantity=qty, po_quantities=qty,
                still_to_deliver_qty=c_qty, still_to_be_delivered_qty=c_qty,
                delivered_qty=a_qty, quantity_received=a_qty,
                net_order_value=c_val + a_val, net_order_value_inr=c_val + a_val,
                still_to_deliver_inr=c_val, delivered_value_inr_cr=a_val / 1e7,
                unit_of_measure=uom or None, currency="INR", doc_type="POrd", source="co",
                mw_multiplication_factor=mw, po_quantities_mw=(qty * mw) if mw else None,
                upload_time=now,
            ))

        # Fill what the CO lines lack from ME2J; never overwrite a CO value.
        enrich = _me2j_enrichment()
        filled = 0
        for r in po_rows:
            po, wbs, mat = r["purchasing_document"], r["wbs_element"], r["material_code"]
            for key in ((po, wbs, mat), (po, wbs), (po,)):
                for f, v in enrich.get(key, {}).items():
                    if not r.get(f):
                        r[f] = v
                        filled += 1

        slr = db.execute(text("""
            select po_document, master_prefix,
                   case when kind = 'commitment' and ref_category = 'PReq' then 'PReq' else 'POrd' end t,
                   max(wbs_description), max(wbs_element), max(vendor_name),
                   sum(value_inr) filter (where kind = 'actual'),
                   sum(value_inr) filter (where kind = 'commitment')
            from sap_co_line
            where not (left(wbs_element, 6) = any(:keep))
              and (counts_as_po
                   or (kind = 'commitment' and ref_category = 'PReq' and master_prefix is not null
                       and value_inr <> 0 and not is_overhead_po))
            group by 1, 2, 3"""), {"keep": keep}).fetchall()
        slr_rows = [dict(po_document=po, plant_code=pfx, type=t, description=desc, wbs_element=wbs,
                         vendor_name=vendor or "", actual_amount=float(a or 0),
                         commitment_amount=float(c or 0), upload_time=now)
                    for po, pfx, t, desc, wbs, vendor, a, c in slr]

        # One transaction: a failure leaves the previous tables in place.
        # Everything is replaced except the ZPSPS rows of the kept (BESS) WBS.
        db.execute(text("""delete from mt_poamount
                           where source = 'co' or not (left(coalesce(wbs_element, ''), 6) = any(:keep))"""),
                   {"keep": keep})
        db.execute(text("delete from mt_slr_data where not (left(coalesce(wbs_element, ''), 6) = any(:keep))"),
                   {"keep": keep})
        kept_pos = db.execute(text("select count(distinct purchasing_document), "
                                   "coalesce(sum(net_order_value_inr), 0) from mt_poamount")).fetchone()
        for i in range(0, len(po_rows), 5000):
            db.bulk_insert_mappings(models.MTPOAmount, po_rows[i:i + 5000])
        for i in range(0, len(slr_rows), 5000):
            db.bulk_insert_mappings(models.MTSLRData, slr_rows[i:i + 5000])
        # The rows kept from ZPSPS (BESS WBS) get the same ME2J facts, also
        # only where empty - descriptive fields only, never quantities/values.
        for row in db.query(models.MTPOAmount).filter(
                (models.MTPOAmount.source.is_(None)) | (models.MTPOAmount.source != "co")).all():
            po = (row.purchasing_document or "").strip()
            for key in ((po, row.wbs_element, row.material_code), (po, row.wbs_element), (po,)):
                for f, v in enrich.get(key, {}).items():
                    if not getattr(row, f, None):
                        setattr(row, f, v)
        # E-invoice PO -> WBS lookup: add the CO POs it does not know yet
        # (ME2J already filled it; existing entries are left as they are).
        known = {r[0] for r in db.execute(text("select purchasing_document from mt_einvoice_po_lookup"))}
        new_lookup = {}
        for r in po_rows:
            if r["purchasing_document"] not in known and r["wbs_element"]:
                new_lookup.setdefault(r["purchasing_document"], r["wbs_element"])
        if new_lookup:
            db.bulk_insert_mappings(models.MTEInvoicePOLookup,
                                    [{"purchasing_document": p, "wbs_element": w} for p, w in new_lookup.items()])
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    try:  # the SAP router caches prefix indexes / facets built on the old rows
        from routers.sap import _CACHE as sap_cache
        sap_cache.clear()
    except Exception:
        pass
    co_value = sum(r["net_order_value_inr"] for r in po_rows)
    return {"po_rows": len(po_rows), "po_count": len({r["purchasing_document"] for r in po_rows}),
            "po_value_cr": round(co_value / 1e7, 1),
            "zsps_kept_prefixes": keep, "zsps_kept_pos": int(kept_pos[0]),
            "zsps_kept_cr": round(float(kept_pos[1]) / 1e7, 1),
            "total_po_value_cr": round((co_value + float(kept_pos[1])) / 1e7, 1),
            "slr_rows": len(slr_rows), "einvoice_lookup_added": len(new_lookup)}


def reconcile() -> dict:
    """PO-by-PO comparison of sap_co_line (rules applied) against today's SLR
    (mt_slr_data, POrd): which POs each side has, and where values differ.
    The switch-over gate: a full-scope export should leave `missing_in_co`
    near zero."""
    from database import SessionLocal
    from sqlalchemy import text
    db = SessionLocal()
    try:
        co = {r[0]: float(r[1] or 0) for r in db.execute(text(
            "select po_document, sum(value_inr) from sap_co_line where counts_as_po group by 1"))}
        slr = {r[0]: (float(r[1] or 0), r[2]) for r in db.execute(text(
            "select po_document, sum(coalesce(actual_amount,0)+coalesce(commitment_amount,0)), "
            "min(left(wbs_element,6)) from mt_slr_data where type = 'POrd' group by 1"))}
    finally:
        db.close()
    cr = lambda x: round(x / 1e7, 1)
    both = co.keys() & slr.keys()
    missing = {p: slr[p] for p in slr.keys() - co.keys()}
    by_prefix = {}
    for _po, (v, pfx) in missing.items():
        agg = by_prefix.setdefault(pfx or "?", [0, 0.0])
        agg[0] += 1
        agg[1] += v
    diffs = sorted(((p, co[p], slr[p][0]) for p in both), key=lambda t: -abs(t[1] - t[2]))
    return {
        "slr_pos": len(slr), "co_pos": len(co), "in_both": len(both),
        "missing_in_co": len(missing), "missing_in_co_cr": cr(sum(v for v, _ in missing.values())),
        "only_in_co": len(co.keys() - slr.keys()),
        "slr_total_cr": cr(sum(v for v, _ in slr.values())), "co_total_cr": cr(sum(co.values())),
        "missing_by_wbs_prefix": {k: {"pos": n, "cr": cr(v)} for k, (n, v) in
                                  sorted(by_prefix.items(), key=lambda kv: -kv[1][1])[:20]},
        "largest_value_differences": [{"po": p, "co_cr": cr(a), "slr_cr": cr(b)} for p, a, b in diffs[:15]],
    }


if __name__ == "__main__":
    import json
    from auto_migrate import auto_upgrade_schema
    auto_upgrade_schema()
    if "--reconcile" in sys.argv:          # compare against ZPSPS before building
        print(json.dumps(ingest_co(), indent=2, default=str))
        print(json.dumps(reconcile(), indent=2, default=str))
    else:
        print(json.dumps(ingest_co(), indent=2, default=str))
        if po_source() == "co":
            print(json.dumps(build_po_tables(), indent=2, default=str))
