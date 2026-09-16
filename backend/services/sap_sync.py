"""The one SAP refresh path: SharePoint → Data/NEW31 → PO/inventory/consumption
ingest → SLR rebuild → sync_log. Used by the /api/sharepoint/sync route and
by `python scripts/ingest_sap_data.py`, so both do exactly the same thing."""
import logging
import os
from datetime import datetime

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def sync_sap_from_sharepoint(db: Session) -> dict:
    import models
    from services.sharepoint_service import SharePointService
    from scripts.ingest_sap_data import SAP_DATA_DIR, SAP_FILE_PATTERNS, ingest_data
    from scripts.ingest_slr_data import ingest_slr

    log = models.SyncLog(source="sharepoint", status="running")
    db.add(log); db.commit()

    def finish(status, message, **fields):
        for k, v in fields.items():
            setattr(log, k, v)
        log.status, log.message, log.finished_at = status, message, datetime.utcnow()
        db.commit()

    try:
        sp = SharePointService()
        files = sp.list_files_in_target_folder()
        # Only the extracts the ingest consumes; the folder also carries CJI3/ZPS021 etc.
        wanted = [f for f in files if f.get("download_url")
                  and any(p.match(f["name"]) for p in SAP_FILE_PATTERNS.values())]
        if not any(SAP_FILE_PATTERNS["zsps"].match(f["name"]) for f in wanted):
            raise RuntimeError(f"ZPSPS007 (PO book of record) not found in {sp.target_folder}")

        downloaded = []
        for f in wanted:
            print(f"Downloading {f['name']} ({(f.get('size') or 0) / 1e6:.1f} MB, modified {str(f.get('modified'))[:16]})...")
            sp.download_file(f["download_url"], os.path.join(SAP_DATA_DIR, f["name"]))
            downloaded.append({"name": f["name"], "modified": f.get("modified"), "size_mb": round((f.get("size") or 0) / 1e6, 1)})

        ingest_data()
        # SLR is the same ZPSPS007 extract through its own filters, so it refreshes with it.
        slr_rows = ingest_slr()
        # Prefix index, filter facets and insights were built on the old tables.
        from routers.sap import _CACHE as sap_cache
        sap_cache.clear()

        # The data date is the newest extract's own modified time, not our clock.
        as_on = max(datetime.fromisoformat(f["modified"].replace("Z", "+00:00")).replace(tzinfo=None)
                    for f in downloaded if f.get("modified"))
        msg = f"Ingested {len(downloaded)} SAP extracts from SharePoint; SLR rebuilt ({slr_rows} rows)"
        finish("success", msg, files=downloaded, data_as_on=as_on)
        return {"status": "success", "message": msg, "folder": sp.target_folder,
                "files": downloaded, "data_as_on": as_on.isoformat(), "ingested": True, "slr_rows": slr_rows}
    except Exception as e:
        logger.error(f"SharePoint sync failed: {e}")
        finish("failed", str(e)[:1000])
        raise
