"""
Refresh everything the CPAG pack reads for the six BESS projects, in one go:
the live P6 schedule (project, WBS, activities, resource assignments - with
rows deleted in P6 removed) and each project's plan baseline (B2 for
PSS-11/12/10(B), B1 for the rest; services.cpag_baseline.PLAN_BASELINE).

    cd backend && ./venv/Scripts/python.exe scripts/sync_bess_cpag.py

Needs network access to P6. Safe to re-run; the scheduled P6 sync does the
same work, this just does it now.
"""
import logging
import os
import sys
import time
import warnings

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.WARNING)

import models  # noqa: E402
from database import SessionLocal, engine  # noqa: E402
from sqlalchemy import text  # noqa: E402
from routers.bess import BESS_PROJECTS  # noqa: E402
from services.cpag_baseline import sync_cpag_baselines  # noqa: E402
from services.p6_service import P6Service  # noqa: E402


def main() -> None:
    # New tables (cpag_baseline_activity) - the app also does this at start-up.
    models.Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    p6 = P6Service()
    rows = db.execute(
        text("select p6_object_id, project_id from p6_project where project_id = any(:p)"),
        {"p": list(BESS_PROJECTS)}).fetchall()
    failed = []
    for poid, pid in rows:
        t = time.time()
        try:
            p6.sync_projects_to_db(db, poid)
            wbs = p6.sync_wbs_to_db(db, poid)
            acts = p6.sync_activities_to_db(db, poid)
            # The fetchers log and return [] on a network/SSL error rather than
            # raising, so an empty result is the failure signal.
            n_ras = len(p6.fetch_resource_assignments(poid) or [])
            p6.sync_resource_assignments_to_db(db, poid)
            db.commit()
            dd = db.execute(text("select data_date from p6_project where p6_object_id = :o"),
                            {"o": poid}).scalar()
            ok = bool(wbs and acts and n_ras)
            print(f"{'OK  ' if ok else 'FAIL'} {pid}: P6 data date {dd:%d-%b-%Y}, "
                  f"{wbs} WBS, {acts} activities, {n_ras} assignments ({time.time() - t:.0f}s)")
            if not ok:
                failed.append(pid)
        except Exception as e:  # keep going - one project must not stop the rest
            db.rollback()
            print(f"FAIL {pid}: {e}")
            failed.append(pid)
    try:
        for poid, res in sync_cpag_baselines(db, [r[0] for r in rows], p6=p6).items():
            print(f"baseline {poid}: {res}")
    except Exception as e:
        db.rollback()
        print(f"FAIL baselines: {e}")
        failed.append("baselines")
    print("\nAll synced." if not failed else f"\nFAILED: {', '.join(failed)} - re-run once P6 is reachable.")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
