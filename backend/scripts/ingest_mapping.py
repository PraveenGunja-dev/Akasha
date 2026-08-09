import os
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.append(str(BACKEND_DIR))

from database import SessionLocal
from services.sap_master_mapping_service import sync_sap_master


def ingest_mapping(db=None, *, dry_run: bool = False) -> dict:
    owns_session = db is None
    db = db or SessionLocal()
    try:
        report = sync_sap_master(
            db,
            REPO_DIR / "Data" / "AKASHA SAP MASTER FILE.xlsx",
            REPO_DIR / "Data" / "Project_Name_Master.xlsx",
            dry_run=dry_run,
        )
        if owns_session and not dry_run:
            db.commit()
        return report.to_dict()
    except Exception:
        db.rollback()
        raise
    finally:
        if owns_session:
            db.close()


if __name__ == "__main__":
    print(ingest_mapping(dry_run="--dry-run" in sys.argv))
