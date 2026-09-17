"""Compare two ZPSPS007 extracts and report what the newer one lost.

The daily bot's ZPSPS007 on SharePoint dropped the BESS scope on 16 Sep 2026:
307 POs / Rs 11,850 Cr present on 20 Aug were gone. This script makes that
check repeatable so a narrowed extract is caught before it is trusted.

Usage (from backend/):
    python scripts/check_sap_extract_scope.py                 # newest vs previous in Data/NEW31
    python scripts/check_sap_extract_scope.py OLD.xlsx NEW.xlsx

Reads the two files and project_mapping. Writes nothing.
"""
import os
import re
import sys

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(backend_dir)

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from scripts.ingest_sap_data import SAP_DATA_DIR, SAP_FILE_PATTERNS

CR = 1e7


def zsps_files():
    hits = [f for f in os.listdir(SAP_DATA_DIR) if SAP_FILE_PATTERNS["zsps"].match(f)]
    hits = sorted((os.path.join(SAP_DATA_DIR, f) for f in hits), key=os.path.getmtime)
    if len(hits) < 2:
        sys.exit(f"Need two ZPSPS007 files in {SAP_DATA_DIR} to compare; found {len(hits)}")
    return hits[-2], hits[-1]


def prefix(wbs) -> str:
    s = str(wbs or "").upper().replace("-", "")
    return s[1:5] if s.startswith("H") else s[:4]


def load_po_docs(path: str) -> pd.DataFrame:
    """One row per PO document: value, and the WBS prefix it books to."""
    print(f"Reading {os.path.basename(path)} ...", flush=True)
    df = pd.read_excel(path, usecols=["C.Document", "Type", "WBS Element", "Description",
                                      "Commitment Amt", "Actual Amount", "Summary"])
    df = df[df["C.Document"].notna() & (df["Type"].astype(str).str.strip() == "POrd")]
    df = df[df["Summary"].isna() | (df["Summary"].astype(str).str.strip() == "")]
    df["doc"] = df["C.Document"].astype(str).str.replace(r"\.0$", "", regex=True).str.strip()
    df["pfx"] = df["WBS Element"].map(prefix)
    df["val"] = (pd.to_numeric(df["Commitment Amt"], errors="coerce").fillna(0)
                 + pd.to_numeric(df["Actual Amount"], errors="coerce").fillna(0))
    df["act"] = pd.to_numeric(df["Actual Amount"], errors="coerce").fillna(0)
    return df.groupby("doc").agg(val=("val", "sum"), act=("act", "sum"),
                                 pfx=("pfx", "first"), desc=("Description", "first"))


def project_index():
    """prefix → (project name, cluster) from project_mapping."""
    load_dotenv(os.path.join(backend_dir, ".env"))
    e = create_engine(os.environ["DATABASE_URL"])
    idx = {}
    with e.connect() as c:
        for name, cluster, *codes in c.execute(text(
                "select coalesce(project_name_from_p6, project), cluster, spv_plant_code, agel, age6l from project_mapping")):
            for val in codes:
                for code in re.findall(r"H-?\s*([A-Za-z0-9]+)", str(val or "")):
                    idx.setdefault(code.upper()[:4], (name, cluster))
    return idx


def main():
    old_path, new_path = (sys.argv[1], sys.argv[2]) if len(sys.argv) == 3 else zsps_files()
    old, new = load_po_docs(old_path), load_po_docs(new_path)
    idx = project_index()

    gone = old[~old.index.isin(new.index)]
    added = new[~new.index.isin(old.index)]

    print()
    print(f"OLD  {os.path.basename(old_path):28s} {len(old):6d} POs   Rs {old.val.sum() / CR:10,.0f} Cr")
    print(f"NEW  {os.path.basename(new_path):28s} {len(new):6d} POs   Rs {new.val.sum() / CR:10,.0f} Cr")
    print(f"     POs only in OLD (dropped):        {len(gone):6d}       Rs {gone.val.sum() / CR:10,.0f} Cr"
          f"   (Rs {gone.act.sum() / CR:,.0f} Cr of it already delivered)")
    print(f"     POs only in NEW (added):          {len(added):6d}       Rs {added.val.sum() / CR:10,.0f} Cr")

    if gone.empty:
        print("\nNo POs dropped. The new extract covers everything the old one did.")
        return

    g = gone.assign(project=gone.pfx.map(lambda p: idx.get(p, ("<unmapped>", None))[0]),
                    cluster=gone.pfx.map(lambda p: idx.get(p, (None, "<unmapped>"))[1]))

    print("\nDROPPED VALUE BY CLUSTER")
    for cl, grp in g.groupby("cluster", dropna=False):
        print(f"  {str(cl):18s} {len(grp):5d} POs   Rs {grp.val.sum() / CR:9,.0f} Cr")

    print("\nDROPPED VALUE BY PROJECT (top 15)")
    byp = g.groupby(["project", "pfx"]).agg(pos=("val", "size"), cr=("val", "sum")).sort_values("cr", ascending=False)
    for (proj, p), r in byp.head(15).iterrows():
        print(f"  {proj:32s} {p:5s} {int(r.pos):4d} POs   Rs {r.cr / CR:9,.0f} Cr")

    print("\nLARGEST DROPPED POs")
    for doc, r in g.sort_values("val", ascending=False).head(10).iterrows():
        print(f"  {doc}  {r.pfx:5s} Rs {r.val / CR:8,.0f} Cr  {str(r.desc)[:40]:40s}  {r.project}")

    print("\nThese POs exist in SAP (they were in the earlier extract) but the newer")
    print("ZPSPS007 export does not include them. Check the report's project / WBS /")
    print("company-code selection on the bot before trusting the newer numbers.")


if __name__ == "__main__":
    main()
