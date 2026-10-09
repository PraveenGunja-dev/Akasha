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

    SAP_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "Data", "19_09")
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
        co_note = _ingest_co_source()
        co_note += _ingest_ariba(db)
        from routers.sap import _CACHE as sap_cache
        sap_cache.clear()

        used = [{"name": os.path.basename(p), "modified": datetime.utcfromtimestamp(os.path.getmtime(p)).isoformat(),
                 "size_mb": round(os.path.getsize(p) / 1e6, 1)} for p in paths.values() if p]
        as_on = datetime.utcfromtimestamp(os.path.getmtime(paths["zsps"]))
        msg = f"Ingested local files (ZSPS: {os.path.basename(paths['zsps'])}); SLR rebuilt ({slr_rows} rows){co_note}"
        finish("success", msg, files=used, data_as_on=as_on)
        return {"status": "success", "message": msg, "files": used, "data_as_on": as_on.isoformat(),
                "ingested": True, "slr_rows": slr_rows}
    except Exception as e:
        logger.error(f"Local SAP ingest failed: {e}")
        finish("failed", str(e)[:1000])
        raise


def _ingest_co_source() -> str:
    """Load the CO Commitment + Actual extracts and, while they are the PO
    source (AKASHA_PO_SOURCE, default "co"), rebuild mt_poamount / mt_slr_data
    from them. Runs after the ZPSPS ingest, which still loads ME2J, MB51/MB52
    and the e-invoice lookup. Returns a note for the sync log; a failure here
    leaves whatever the previous run built in place."""
    try:
        from scripts.ingest_sap_co import ingest_co, build_po_tables, po_source
        co = ingest_co()
        note = f"; CO lines {co['lines']}"
        if po_source() == "co":
            built = build_po_tables()
            note += (f"; PO tables built from CO: {built['po_count']} POs, "
                     f"Rs {built['po_value_cr']} Cr, SLR {built['slr_rows']} rows")
        return note
    except FileNotFoundError as e:
        return f"; CO extracts missing ({e}) - PO tables left from ZPSPS"
    except Exception as e:
        logger.error(f"CO ingest / PO table build failed: {e}")
        return f"; CO ingest failed ({str(e)[:120]}) - previous PO tables kept"


def _ingest_ariba(db: Session) -> str:
    """Reload the Ariba ZIBDSESREP inbound-delivery report (dispatch / GRN /
    finance checklist) when an extract is present. Never fails the SAP sync:
    a missing or bad file leaves the previous Ariba load in place."""
    try:
        from services.ariba_service import sync_ariba_inbound_deliveries
        r = sync_ariba_inbound_deliveries(db)
        return f"; Ariba IBD {r['loaded']} rows ({r['pos']} POs)"
    except FileNotFoundError:
        return "; Ariba extract not found - previous Ariba load kept"
    except Exception as e:
        db.rollback()
        logger.error(f"Ariba ingest failed: {e}")
        return f"; Ariba ingest failed ({str(e)[:120]}) - previous load kept"


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
        # Only the extracts the ingest consumes, plus the CO Commitment / Actual
        # line items (Commitment* / Actual*) the PO source is built from.
        from scripts.ingest_sap_co import CO_FILE_PATTERNS
        from services.ariba_service import ARIBA_FILE_PATTERN
        patterns = list(SAP_FILE_PATTERNS.values()) + list(CO_FILE_PATTERNS.values()) + [ARIBA_FILE_PATTERN]
        wanted = [f for f in files if f.get("download_url")
                  and any(p.match(f["name"]) for p in patterns)]
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
        # CO line items (planned replacement source): built alongside, never
        # allowed to fail the ZPSPS sync that everything on screen still reads.
        co_note = _ingest_co_source()
        co_note += _ingest_ariba(db)
        # Prefix index, filter facets and insights were built on the old tables.
        from routers.sap import _CACHE as sap_cache
        sap_cache.clear()

        # The data date is the newest extract's own modified time, not our clock.
        as_on = max(datetime.fromisoformat(f["modified"].replace("Z", "+00:00")).replace(tzinfo=None)
                    for f in downloaded if f.get("modified"))
        msg = f"Ingested {len(downloaded)} SAP extracts from SharePoint; SLR rebuilt ({slr_rows} rows){co_note}"
        finish("success", msg, files=downloaded, data_as_on=as_on)
        return {"status": "success", "message": msg, "folder": sp.target_folder,
                "files": downloaded, "data_as_on": as_on.isoformat(), "ingested": True, "slr_rows": slr_rows}
    except Exception as e:
        logger.error(f"SharePoint sync failed: {e}")
        finish("failed", str(e)[:1000])
        raise
