"""
Step 1b - P6 baseline history (read-only from the P6 API).

    backend\\venv\\Scripts\\python.exe training_model\\pipelines\\extract_p6_history.py

Every stored baseline of every register project is a snapshot of the plan on
the day it was taken (P6 DataDate). Reading each one's block activity dates
gives two things the live schedule cannot:
  - the plan that was IN FORCE on any past date - so a training example can
    be measured against the baseline a planner actually had then, instead of
    being dropped when the current baseline was set later;
  - each block's FTC REVISION history - how many times, and by how much, its
    planned date moved (AI scenario 2, "P6 not updated").

Writes data/raw/p6_baselines.csv.gz and p6_baseline_activities.csv.gz.
"""
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
os.chdir(ROOT / "backend")

import pandas as pd                                   # noqa: E402
import urllib3                                        # noqa: E402
from sqlalchemy import text                           # noqa: E402

from database import SessionLocal                     # noqa: E402
from services.cpag_baseline import _p6_get            # noqa: E402
from services.p6_service import P6Service             # noqa: E402

urllib3.disable_warnings()
OUT = ROOT / "training_model" / "data" / "raw"
BLOCK_RE = re.compile(r"(?i)\bblock[\s\-_:]*0*(\d{1,3})\b")


def main():
    db, p6 = SessionLocal(), P6Service()
    projects = db.execute(text("""
        select p.p6_object_id, p.project_id from p6_project p
        where p.project_id in (select project_id from project_mapping where project_id <> '')""")).fetchall()
    bls, acts = [], []
    for i, (poid, pid) in enumerate(projects, 1):
        try:
            found = _p6_get(p6, "baselineProject", "ObjectId,Name,DataDate", f"OriginalProjectObjectId={poid}")
        except Exception as e:                       # keep going; report at the end
            print(f"  {pid}: baseline list failed: {e}")
            continue
        for b in found:
            bls.append({"project_object_id": poid, "project_id": pid, "baseline_object_id": b["ObjectId"],
                        "baseline_name": b.get("Name"), "data_date": b.get("DataDate")})
            try:
                rows = _p6_get(p6, "activity", "Id,Name,PlannedStartDate,PlannedFinishDate",
                               f"ProjectObjectId={b['ObjectId']}")
            except Exception as e:
                print(f"  {pid} / {b.get('Name')}: activities failed: {e}")
                continue
            for a in rows:
                if BLOCK_RE.search(a.get("Name") or ""):
                    acts.append({"project_object_id": poid, "baseline_object_id": b["ObjectId"],
                                 "activity_id": a.get("Id"), "name": a.get("Name"),
                                 "planned_start": a.get("PlannedStartDate"),
                                 "planned_finish": a.get("PlannedFinishDate")})
        print(f"[{i}/{len(projects)}] {pid}: {len(found)} baselines, {len(acts)} block activity rows so far",
              flush=True)
    pd.DataFrame(bls).to_csv(OUT / "p6_baselines.csv.gz", index=False)
    pd.DataFrame(acts).to_csv(OUT / "p6_baseline_activities.csv.gz", index=False)
    print(f"done: {len(bls)} baselines, {len(acts)} block activity rows")


if __name__ == "__main__":
    main()
