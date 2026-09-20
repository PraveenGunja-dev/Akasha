"""The one SAP refresh path: SharePoint → Data/NEW31 → PO/inventory/consumption
ingest → SLR rebuild → sync_log. Used by the /api/sharepoint/sync route and
by `python scripts/ingest_sap_data.py`, so both do exactly the same thing."""
import logging
import os
from datetime import datetime

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def sync_sap_from_local(db: Session, zsps_path: str | None = None,
                         max_drop_pct: float = 15.0, allow_drop: bool = False) -> dict:
    """Ingest from files already in Data/NEW31 — the newest of each, or a
    specific ZPSPS007 via zsps_path. Logged as source='local' so the SAP
    header shows the real file date and never claims a SharePoint pull.

    max_drop_pct / allow_drop: see services/sync_guard.py. A collapsed
    extract raises here and is logged as a failed run, never partially
    applied."""
    from auto_migrate import auto_upgrade_schema
    auto_upgrade_schema()

    import models
    from scripts.ingest_sap_data import SAP_DATA_DIR, find_sap_file, ingest_data
    from scripts.ingest_slr_data import ingest_slr

    SAP_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "Data", "NEW31")
    if zsps_path and not os.path.exists(zsps_path):
        raise FileNotFoundError(zsps_path)
    paths = {k: (zsps_path if k == "zsps" and zsps_path else find_sap_file(k, SAP_DATA_DIR)) for k in ("zsps", "me2j", "mb52", "mb51")}
    if not paths["zsps"]:
        raise FileNotFoundError(f"No ZPSPS007 extract in {SAP_DATA_DIR}")

    log = models.SyncLog(source="local", status="running")
    db.add(log); db.commit()

    def finish(status, message, **fields):
        for k, v in fields.items():
            setattr(log, k, v)
        log.status, log.message, log.finished_at = status, message, datetime.utcnow()
        db.commit()

    try:
        ingest_data(files={"zsps": paths["zsps"]}, max_drop_pct=max_drop_pct, allow_drop=allow_drop)
        slr_rows = ingest_slr(file_path=paths["zsps"], max_drop_pct=max_drop_pct, allow_drop=allow_drop)
        from routers.sap import _CACHE as sap_cache
        sap_cache.clear()

        used = [{"name": os.path.basename(p), "modified": datetime.utcfromtimestamp(os.path.getmtime(p)).isoformat(),
                 "size_mb": round(os.path.getsize(p) / 1e6, 1)} for p in paths.values() if p]
        as_on = datetime.utcfromtimestamp(os.path.getmtime(paths["zsps"]))
        msg = f"Ingested local files (ZSPS: {os.path.basename(paths['zsps'])}); SLR rebuilt ({slr_rows} rows)"
        finish("success", msg, files=used, data_as_on=as_on)
        return {"status": "success", "message": msg, "files": used, "data_as_on": as_on.isoformat(),
                "ingested": True, "slr_rows": slr_rows}
    except Exception as e:
        logger.error(f"Local SAP ingest failed: {e}")
        finish("failed", str(e)[:1000])
        raise


def sync_sap_from_sharepoint(db: Session, max_drop_pct: float = 15.0, allow_drop: bool = False) -> dict:
    """max_drop_pct / allow_drop: see services/sync_guard.py. If the bot's
    export narrows in scope again, this refuses the replace and logs a
    failed run with the before/after numbers, instead of quietly serving
    the smaller figure — the exact gap the BESS-drop incident exposed."""
    # The script path never goes through run.py, so a checkout that gained a
    # column or table (doc_type, sync_log) must upgrade its own schema first.
    from auto_migrate import auto_upgrade_schema
    auto_upgrade_schema()

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

        ingest_data(max_drop_pct=max_drop_pct, allow_drop=allow_drop)
        # SLR is the same ZPSPS007 extract through its own filters, so it refreshes with it.
        slr_rows = ingest_slr(max_drop_pct=max_drop_pct, allow_drop=allow_drop)
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
