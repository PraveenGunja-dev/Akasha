import requests
import json
import logging
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from database import SessionLocal
from models import TcProjectEntry, TcNetworkEdge, TcNetworkNode, ProjectMapping
from datetime import datetime

import urllib3
from urllib.parse import quote

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)


def find_mapping_id(db: Session, project_names):
    """Resolve a local ProjectMapping.id from one or more TC project names.

    Used by the offline TC loader (scripts/load_tc_data_from_json.py): a dumped
    edge/entry carries a mapping_id from the *source* DB that is invalid locally,
    so we recompute it here by matching the TC project name(s) against
    ProjectMapping.project (stored comma-separated). Returns None if unmatched —
    the FK is nullable, so unmapped edges still load and get resolved at read time
    via the `projects` ILIKE fallback in tc_tools.tc_get_project_lines.

    NOTE: the live API sync below does NOT use this — it maps via direct
    per-project API resolution. This helper exists only for the offline loader.
    """
    if not project_names:
        return None

    names = project_names if isinstance(project_names, list) else [project_names]
    all_maps = db.query(ProjectMapping).all()

    for name in names:
        if not name:
            continue
        for m in all_maps:
            if m.project:
                tc_names = [t.strip() for t in m.project.split(',')]
                if name in tc_names:
                    return m.id
    return None


# ── Transmission Portal connection ───────────────────────────────────────────
# The portal (Unada) backend, per its route document of 14 Oct 2026. Signing in
# with email + password is two-step there - it emails a one-time code and
# returns a challenge ID, never a token - so an unattended sync cannot use it.
# The sync signs in with the portal's login link instead: POST
# /api/v1/user/login-link with the #lt= token of an Akasha portal link, which
# returns the session token directly. Nothing secret lives in the code; all of
# it comes from backend/.env:
#
#   TC_BASE_URL            portal backend, e.g. https://transmission-backend-testing.unada.in
#   TC_LOGIN_LINK_TOKEN    the #lt= value of the Akasha portal link
#   TC_AUTH_TOKEN          optional: a session token pasted by hand, used as-is
#                          (overrides the login link; expires)
TC_BASE_URL = (os.getenv("TC_BASE_URL") or "").strip().rstrip("/")
BASE_URL = TC_BASE_URL          # name kept for the code below
TIMEOUT_S = 60


class TcAuthError(RuntimeError):
    """Why the portal sign-in failed, in words a person can act on."""


def _token_from(body):
    if not isinstance(body, dict):
        return None
    data = body.get("data") if isinstance(body.get("data"), dict) else {}
    return body.get("token") or body.get("access_token") or data.get("token") or data.get("access_token")


def login() -> str:
    """A session token for the portal, or TcAuthError saying why not."""
    if not TC_BASE_URL:
        raise TcAuthError("TC_BASE_URL is not set in backend/.env - add the transmission portal's backend address.")
    pasted = (os.getenv("TC_AUTH_TOKEN") or "").strip()
    if pasted:
        return pasted
    lt = (os.getenv("TC_LOGIN_LINK_TOKEN") or "").strip()
    if not lt:
        raise TcAuthError("TC_LOGIN_LINK_TOKEN is not set in backend/.env - add the #lt= value of the "
                          "Akasha portal link (password sign-in needs an emailed code and cannot be automated).")
    try:
        r = requests.post(f"{TC_BASE_URL}/api/v1/user/login-link", json={"token": lt},
                          verify=False, timeout=TIMEOUT_S)
    except requests.RequestException as e:
        raise TcAuthError(f"Transmission portal not reachable at {TC_BASE_URL} ({type(e).__name__}).") from e
    try:
        body = r.json()
    except ValueError:
        body = {}
    if r.status_code in (401, 403):
        raise TcAuthError(f"Portal refused the login link ({r.status_code}: {body.get('message') or 'no message'}) - "
                          "the #lt= token may have expired or been revoked; ask the portal team for a new link.")
    if not r.ok:
        raise TcAuthError(f"Portal login-link sign-in failed ({r.status_code}: {body.get('message') or r.text[:120]}).")
    token = _token_from(body)
    if not token:
        data = body.get("data") or {}
        if isinstance(data, dict) and (data.get("challengeId") or data.get("challenge_id")):
            raise TcAuthError("Portal answered the login link with a one-time-code challenge "
                              "(LOGIN_LINK_REQUIRES_OTP is on) - an unattended sync cannot complete it.")
        raise TcAuthError(f"Portal login-link sign-in returned no token: {str(body)[:160]}")
    return token


def get_auth_token():
    """The session token, or None (the reason is logged). Kept for callers that
    test for None; new code should call login() for the reason."""
    try:
        return login()
    except TcAuthError as e:
        logger.error(f"Transmission portal sign-in: {e}")
        return None


class FetchFailed(Exception):
    """The portal did not answer (timeout, 5xx, ...). Unlike a 404, this says
    nothing about whether the project still exists there."""


def fetch_json(endpoint: str, token: str, retries: int = 1):
    """The endpoint's JSON; None when the portal answers 404 (no such
    project); FetchFailed when it could not be read at all. One retry, for the
    occasional connect timeout."""
    headers = {"Authorization": f"Bearer {token}"}
    for attempt in range(retries + 1):
        try:
            res = requests.get(f"{BASE_URL}{endpoint}", headers=headers, verify=False, timeout=TIMEOUT_S)
            if res.status_code == 404:
                return None   # expected for unmapped or non-existent projects
            res.raise_for_status()
            return res.json()
        except (requests.RequestException, ValueError) as e:
            if attempt == retries:
                raise FetchFailed(f"{endpoint}: {e}") from e


def fetch_data(endpoint: str, token: str):
    """fetch_json, with a failure logged and read as None."""
    try:
        return fetch_json(endpoint, token)
    except FetchFailed as e:
        logger.error(f"Failed to fetch {e}")
        return None

def get_global_topology(token: str, region: str):
    """Fetches the global snapshot to get accurate node coordinates and edge from/to links"""
    proj_data = fetch_data(f"/api/{region}/projects", token)
    if not proj_data or "projects" not in proj_data:
        logger.error(f"No {region} global projects found")
        return None
        
    current_proj = next((p for p in proj_data["projects"] if p.get("is_current")), None)
    if not current_proj:
        # The portal doesn't always keep an `is_current` snapshot flagged (seen
        # empty for Khavda in practice) - fall back to the most recently
        # modified snapshot instead of refusing to sync.
        candidates = [p for p in proj_data["projects"] if p.get("last_modified") or p.get("upload_date")]
        if candidates:
            current_proj = max(candidates, key=lambda p: p.get("last_modified") or p.get("upload_date"))
            logger.warning(
                f"No snapshot flagged is_current for {region}; falling back to most recently "
                f"modified snapshot '{current_proj.get('name')}' ({current_proj.get('id')})"
            )
        elif proj_data["projects"]:
            current_proj = proj_data["projects"][0]
            logger.warning(f"No snapshot flagged is_current for {region}; falling back to first available snapshot")

    if not current_proj:
        logger.error(f"No {region} global project found to sync")
        return None
        
    data = fetch_data(f"/api/{region}/projects/{current_proj['id']}", token)
    if not data or "data" not in data or "network" not in data["data"]:
        logger.error(f"Invalid {region} global network data")
        return None
        
    network = data["data"]["network"]
    
    # Map edges by ID to retrieve their topology later
    global_edges = {}
    for e in network.get("edges", []):
        global_edges[e.get("id")] = e
        
    return {
        "nodes": network.get("nodes", []),
        "edges": global_edges
    }

def _as_datetime(v):
    """pandas Timestamp / datetime -> a plain midnight datetime, else None."""
    if v is None:
        return None
    try:
        v = v.to_pydatetime()
    except AttributeError:
        pass
    return datetime(v.year, v.month, v.day) if isinstance(v, datetime) else None


def apply_connectivity_dates(pm, rows, db=None) -> dict:
    """LTA and SCOD from the portal's Project Blocks rows (the connectivity
    sheet, one row per block / phase of the project):

        LTA  = the latest ECOD across the project's rows
        SCOD = the latest SCOD across them (a date, or "LTA +/- N days",
               read against that LTA)

    The latest phase governs, the same rule the connectivity export import
    used. A project the portal has no date for keeps the date it had - this
    never clears one. Returns what changed."""
    from scripts.update_lta_from_123 import _parse_date, _parse_scod
    changed = {}
    ecods = [d for d in (_as_datetime(_parse_date(r.get("ecod"))) for r in rows or []) if d]
    lta = max(ecods) if ecods else None
    scod, scod_is_lta = None, False
    for r in rows or []:
        val, is_lta = _parse_scod(r.get("scod"), lta)
        val = _as_datetime(val)
        if val and (scod is None or val > scod):
            scod, scod_is_lta = val, is_lta
    from services import date_history
    if lta and pm.lta_date != lta:
        changed["lta"] = (pm.lta_date, lta)
        if db is not None:
            date_history.record(db, pm, "lta", pm.lta_date, lta, "portal", "sync")
        pm.lta_date = lta
    if scod and (pm.manual_scod != scod or bool(pm.manual_scod_is_lta) != scod_is_lta):
        changed["scod"] = (pm.manual_scod, scod)
        if db is not None:
            date_history.record(db, pm, "scod", pm.manual_scod, scod, "portal", "sync")
        pm.manual_scod, pm.manual_scod_is_lta = scod, scod_is_lta
    return changed


def sync_region_data(db: Session, token: str, region: str, project_ids=None):
    """Sync one region's transmission data. If project_ids is given, only those
    projects' entries/edges are fetched and reconciled - everything else in the
    region is left untouched (used for the fast per-project sync)."""
    logger.info(f"Syncing {region} data..." + (f" (scoped to {len(project_ids)} project(s))" if project_ids else ""))

    # 1. Fetch Global Topology (Provides nodes, and from/to for edges)
    topology = get_global_topology(token, region.lower())
    if not topology:
        return

    existing_nodes = {n.node_id: n for n in db.query(TcNetworkNode).filter(TcNetworkNode.region == region).all()}
    
    # Upsert unique global nodes
    for n in topology["nodes"]:
        n_id = n.get("id")
        if n_id in existing_nodes:
            node = existing_nodes[n_id]
            node.label = n.get("label")
            node.type = n.get("type")
            node.status = n.get("status")
            node.x = n.get("x")
            node.y = n.get("y")
        else:
            node = TcNetworkNode(
                region=region,
                node_id=n_id,
                label=n.get("label"),
                type=n.get("type"),
                status=n.get("status"),
                x=n.get("x"),
                y=n.get("y")
            )
            db.add(node)
            
    # 2. Resolve which mapped projects to sync (all of them, or just the requested ones)
    mappings_query = db.query(ProjectMapping).filter(ProjectMapping.project_id.isnot(None))
    if project_ids:
        mappings_query = mappings_query.filter(ProjectMapping.project_id.in_(project_ids))
    mappings = mappings_query.all()
    scoped_pm_ids = [m.id for m in mappings]

    entries_query = db.query(TcProjectEntry).filter(TcProjectEntry.region == region)
    edges_query = db.query(TcNetworkEdge).filter(TcNetworkEdge.region == region)
    if project_ids:
        # Only reconcile rows belonging to the project(s) we're actually syncing -
        # otherwise the stale-cleanup pass below would wipe out every other
        # project's data since it would never see them as "seen" this run.
        entries_query = entries_query.filter(TcProjectEntry.mapping_id.in_(scoped_pm_ids))
        edges_query = edges_query.filter(TcNetworkEdge.mapping_id.in_(scoped_pm_ids))

    existing_entries = {(pe.mapping_id, pe.block): pe for pe in entries_query.all()}
    existing_edges = {(e.mapping_id, e.edge_id): e for e in edges_query.all()}

    seen_entry_keys = set()
    seen_edge_keys = set()
    date_changes = {}   # project_id -> {"lta"/"scod": (old, new)}

    from models import Notification

    for pm in mappings:
        pid = pm.project_id
        if not pid: continue
        
        # Targeted project API Call
        try:
            # Encode the id: several carry "&" (FY25-P18&19&20, FY27-P01&P02), which
            # unencoded split the query and the portal looked up "FY25-P18" instead.
            p_data = fetch_json(f"/api/{region.lower()}/project-details?project_id={quote(pid, safe='')}", token)
        except FetchFailed as e:
            # Could not read it this run - keep what we already hold for this
            # project rather than letting the stale-row cleanup below delete it.
            logger.error(f"Failed to fetch {e} - keeping {pid}'s existing {region} data")
            seen_entry_keys.update(k for k in existing_entries if k[0] == pm.id)
            seen_edge_keys.update(k for k in existing_edges if k[0] == pm.id)
            continue

        RAJ_EXTERNAL_MAP = {
            "FY25-BANDHA_500MW": "Siyambar"
        }

        # Fallback for Rajasthan if project-details is missing
        if not p_data and region.lower() == 'rajasthan' and pid in RAJ_EXTERNAL_MAP:
            siyambar_key = RAJ_EXTERNAL_MAP[pid]
            matched_lines = []
            for global_e in topology["edges"].values():
                proj_list = global_e.get("project", [])
                if any(siyambar_key in p for p in proj_list):
                    matched_lines.append(global_e)
            
            if matched_lines:
                p_data = {
                    "progress": {},
                    "metadata": {"rows": []},
                    "lines": matched_lines
                }

        if not p_data:
            continue
            
        # Insert precisely mapped project entries (blocks)
        metadata = p_data.get("metadata", {})
        all_entries = metadata.get("rows", [])

        # LTA (latest ECOD) and SCOD (latest SCOD) from the same rows - the
        # Ordering Schedule's LTA / SCOD columns read these fields.
        changed = apply_connectivity_dates(pm, all_entries, db)
        if changed:
            date_changes[pm.project_id] = changed
            logger.info(f"{region} {pm.project_id}: " + "; ".join(
                f"{k.upper()} {old.strftime('%d-%b-%y') if old else 'none'} -> {new.strftime('%d-%b-%y')}"
                for k, (old, new) in changed.items()))
        
        # Save rich progress metrics natively to the DB
        pm.tc_progress = p_data.get("progress", {})
        
        for entry in all_entries:
            block = entry.get("block")
            key = (pm.id, block)
            seen_entry_keys.add(key)
            if key in existing_entries:
                pe = existing_entries[key]
                pe.project = entry.get("project")
                pe.phase = entry.get("phase")
                pe.kps = entry.get("kps")
                pe.pss = entry.get("pss")
                pe.breakup = str(entry.get("breakup")) if entry.get("breakup") else ""
                mw_val = entry.get("mw")
                pe.mw = float(mw_val) if mw_val and str(mw_val).strip() else None
            else:
                pe = TcProjectEntry(
                    region=region,
                    project=entry.get("project"),
                    phase=entry.get("phase"),
                    kps=entry.get("kps"),
                    pss=entry.get("pss"),
                    block=block,
                    breakup=str(entry.get("breakup")) if entry.get("breakup") else "",
                    mw=float(entry.get("mw")) if entry.get("mw") and str(entry.get("mw")).strip() else None,
                    mapping_id=pm.id
                )
                db.add(pe)
            
        # Insert precisely mapped edges (lines), utilizing global topology for from/to
        lines = p_data.get("lines", [])
        
        for e in lines:
            edge_id = e.get("id")
            key = (pm.id, edge_id)
            seen_edge_keys.add(key)
            
            # Lookup topology from global fetch
            global_edge = topology["edges"].get(edge_id, {})
            
            new_status = e.get("status")
            new_date = e.get("expected_date")
            new_contractor = e.get("contractor")
            
            if key in existing_edges:
                edge = existing_edges[key]
                
                is_currently_delayed = e.get("is_delayed", False)
                is_in_progress = e.get("normalized_status") == 'in_progress'

                if edge.status and edge.status != new_status:
                    db.add(Notification(
                        project_name=pm.project,
                        module="Transmission",
                        change_type="Status Update",
                        message=f"Line '{e.get('from_label')} to {e.get('to_label')}' status changed from '{edge.status}' to '{new_status}'",
                        category="Dates"
                    ))
                if edge.expected_date and edge.expected_date != new_date:
                    if is_currently_delayed and is_in_progress:
                        db.add(Notification(
                            project_name=pm.project,
                            module="Transmission",
                            change_type="COD Delay",
                            message=f"Transmission Delay Warning: Line '{e.get('from_label')} to {e.get('to_label')}' ECOD slipped from '{edge.expected_date}' to '{new_date}'. SCOD is '{e.get('scd')}'.",
                            block=e.get("from_label"),
                            category="COD"
                        ))
                    else:
                        db.add(Notification(
                            project_name=pm.project,
                            module="Transmission",
                            change_type="Date Delay",
                            message=f"Line '{e.get('from_label')} to {e.get('to_label')}' expected date changed from '{edge.expected_date}' to '{new_date}'",
                            category="Dates"
                        ))
                if edge.contractor and edge.contractor != new_contractor:
                    db.add(Notification(
                        project_name=pm.project,
                        module="Transmission",
                        change_type="Contractor Change",
                        message=f"Line '{e.get('from_label')} to {e.get('to_label')}' contractor changed from '{edge.contractor}' to '{new_contractor}'",
                        category="Scope"
                    ))
                    
                edge.from_node = global_edge.get("from")
                edge.from_label = e.get("from_label")
                edge.to_node = global_edge.get("to")
                edge.to_label = e.get("to_label")
                edge.projects = json.dumps({"projects": global_edge.get("project", []), "phases": global_edge.get("phases", [])})
                edge.contractor = new_contractor
                edge.voltage = e.get("voltage")
                edge.length = str(e.get("length") or global_edge.get("length"))
                edge.status = new_status
                edge.normalized_status = e.get("normalized_status")
                edge.erection = e.get("erection")
                edge.foundation = e.get("foundation")
                edge.stringing = e.get("stringing")
                edge.expected_date = new_date
                edge.scd = e.get("scd")
                edge.charged_date = e.get("charged_date")
                edge.is_delayed = e.get("is_delayed", False)
            else:
                edge = TcNetworkEdge(
                    region=region,
                    edge_id=edge_id,
                    from_node=global_edge.get("from"),
                    from_label=e.get("from_label"),
                    to_node=global_edge.get("to"),
                    to_label=e.get("to_label"),
                    projects=json.dumps({"projects": global_edge.get("project", []), "phases": global_edge.get("phases", [])}),
                    contractor=new_contractor,
                    voltage=e.get("voltage"),
                    length=str(e.get("length") or global_edge.get("length")),
                    status=new_status,
                    normalized_status=e.get("normalized_status"),
                    erection=e.get("erection"),
                    foundation=e.get("foundation"),
                    stringing=e.get("stringing"),
                    expected_date=new_date,
                    scd=e.get("scd"),
                    charged_date=e.get("charged_date"),
                    is_delayed=e.get("is_delayed", False),
                    mapping_id=pm.id
                )
                db.add(edge)
                
                is_currently_delayed = e.get("is_delayed", False)
                is_in_progress = e.get("normalized_status") == 'in_progress'
                if is_currently_delayed and is_in_progress:
                    db.add(Notification(
                        project_name=pm.project,
                        module="Transmission",
                        change_type="COD Delay",
                        message=f"Transmission Delay Warning: Line '{e.get('from_label')} to {e.get('to_label')}' ECOD ({new_date}) is higher than SCOD ({e.get('scd')}).",
                        block=e.get("from_label")
                    ))
                
    # Delete stale edges and entries
    for key, pe in existing_entries.items():
        if key not in seen_entry_keys:
            db.delete(pe)
            
    for key, e in existing_edges.items():
        if key not in seen_edge_keys:
            db.delete(e)
            
    db.commit()
    logger.info(f"Synced {region} Data")
    return {"date_changes": date_changes}

def run_sync():
    """Fired in a background thread (routers/sync.py POST /tc/sync returns
    before this finishes), so it logs its own outcome to sync_log — nothing
    else observes whether it actually succeeded."""
    import models
    from services.sync_log_util import run_logged

    logger.info("Starting Transmission Data Sync...")
    log_db = SessionLocal()

    def _do():
        token = login()   # TcAuthError carries the reason into sync_log
        db = SessionLocal()
        try:
            changes = {}
            for region in ("Khavda", "Rajasthan"):
                changes.update((sync_region_data(db, token, region) or {}).get("date_changes") or {})
            lta_n = sum(1 for c in changes.values() if "lta" in c)
            scod_n = sum(1 for c in changes.values() if "scod" in c)
            logger.info("Transmission Data Sync Complete!")
            return {"status": "success",
                    "message": f"Synced Khavda and Rajasthan transmission data. "
                               f"LTA updated for {lta_n} project(s), SCOD for {scod_n} (from the portal's Project Blocks)."}
        except Exception as e:
            logger.error(f"Error during sync: {e}")
            db.rollback()
            raise
        finally:
            db.close()

    try:
        run_logged(log_db, "tc", _do)
    except Exception:
        pass  # already logged as failed; run_sync() itself has no caller to report to
    finally:
        log_db.close()


def sync_single_project(project_id: str) -> dict:
    """Synchronously sync transmission data for one project (both regions).

    Runs fast (2 topology calls + 2 per-project API calls) since it's scoped to
    a single project_id, so callers - e.g. the per-project "Sync" button - can
    await it and know the DB actually reflects fresh data before reloading,
    unlike the portfolio-wide run_sync() which fires in a background thread.
    """
    token = login()

    db = SessionLocal()
    try:
        sync_region_data(db, token, "Khavda", project_ids=[project_id])
        sync_region_data(db, token, "Rajasthan", project_ids=[project_id])

        edges = db.query(TcNetworkEdge).join(
            ProjectMapping, TcNetworkEdge.mapping_id == ProjectMapping.id
        ).filter(ProjectMapping.project_id == project_id).count()
        entries = db.query(TcProjectEntry).join(
            ProjectMapping, TcProjectEntry.mapping_id == ProjectMapping.id
        ).filter(ProjectMapping.project_id == project_id).count()
        return {"edges": edges, "entries": entries}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_sync()
