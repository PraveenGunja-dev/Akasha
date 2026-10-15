"""Check the integration API (/api/v1) as an external system uses it: with an
API key. Covers key handling and each fix made for the API issues list.

Creates a temporary superadmin and keys, removes them afterwards.

    cd backend && ./venv/Scripts/python.exe scripts/check_api_v1.py
"""
import os
import secrets
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from database import SessionLocal  # noqa: E402
from models import AkashaApiKey, AkashaAuditLog, AkashaSession, AkashaUser, ProjectMapping  # noqa: E402
from services import portfolio, security  # noqa: E402

PREFIX = "zz_v1_"
failures: list[str] = []


def check(ok, label, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}{(' - ' + str(detail)) if detail != '' else ''}")
    if not ok:
        failures.append(label)


def cleanup(db):
    ids = [u.id for u in db.query(AkashaUser).filter(AkashaUser.username.like(PREFIX + "%"))]
    if ids:
        db.query(AkashaSession).filter(AkashaSession.user_id.in_(ids)).delete(synchronize_session=False)
    db.query(AkashaApiKey).filter(AkashaApiKey.name.like(PREFIX + "%")).delete(synchronize_session=False)
    db.query(AkashaAuditLog).filter(AkashaAuditLog.target.like(PREFIX + "%")
                                    | AkashaAuditLog.actor_username.like(PREFIX + "%")).delete(synchronize_session=False)
    db.query(AkashaUser).filter(AkashaUser.username.like(PREFIX + "%")).delete(synchronize_session=False)
    db.commit()


def all_rows(c, path, key, **params):
    rows, page = [], 1
    while True:
        r = c.get(path, params={**params, "page": page, "page_size": 200}, headers={"X-API-Key": key})
        if r.status_code != 200:
            return None, r.status_code
        body = r.json()
        rows += body["data"]
        if len(rows) >= body["meta"]["total"] or not body["data"]:
            return rows, 200
        page += 1


def run() -> int:
    db = SessionLocal()
    cleanup(db)
    try:
        pw = secrets.token_urlsafe(12) + "aA1!"
        db.add(AkashaUser(username=PREFIX + "admin", display_name="v1 check", role="superadmin", is_active=True,
                          password_hash=security.hash_password(pw), must_change_password=False))
        db.commit()
        admin = TestClient(main.app, base_url="https://t")
        assert admin.post("/akasha/api/auth/login", json={"username": PREFIX + "admin", "password": pw}).status_code == 200

        print("\n1. API keys")
        r = admin.post("/akasha/api/admin/api-keys", json={"name": PREFIX + "all", "expires_in_days": 30})
        check(r.status_code == 200 and r.json()["key"].startswith("ak_"), "superadmin issues a key, shown once")
        key = r.json()["key"]
        stored = db.query(AkashaApiKey).filter(AkashaApiKey.name == PREFIX + "all").first()
        check(stored and stored.key_hash != key and key not in (stored.key_hash or ""), "only the key's hash is stored")
        c = TestClient(main.app, base_url="https://t")
        check(c.get("/akasha/api/v1/projects").status_code == 401, "no key -> 401")
        check(c.get("/akasha/api/v1/projects", headers={"X-API-Key": "ak_wrong"}).status_code == 401, "wrong key -> 401")
        check(c.get("/akasha/api/v1/projects", headers={"X-API-Key": key}).status_code == 200, "valid key reads /api/v1 (X-API-Key)")
        check(c.get("/akasha/api/v1/projects", headers={"Authorization": f"Bearer {key}"}).status_code == 200, "valid key reads /api/v1 (Bearer)")
        check(c.get("/akasha/api/dashboard/summary", headers={"X-API-Key": key}).status_code == 403, "key cannot read outside /api/v1")
        check(c.post("/akasha/api/sharepoint/sync", headers={"X-API-Key": key}).status_code == 403, "key cannot write")
        r = admin.post("/akasha/api/admin/api-keys", json={"name": PREFIX + "wind", "portfolios": ["Wind"]})
        wkey = r.json()["key"]
        projs, st = all_rows(c, "/akasha/api/v1/projects", wkey)
        check(st == 200 and projs and all(p["portfolio"] == "Wind" for p in projs), "Wind-only key sees only Wind projects", f"{len(projs or [])} projects")
        solar = db.query(ProjectMapping).filter(ProjectMapping.cluster == "Solar Khavda", ProjectMapping.project_id.isnot(None)).first()
        check(c.get(f"/akasha/api/v1/projects/{solar.project_id}", headers={"X-API-Key": wkey}).status_code == 403, "Wind key refused a Solar project")
        check(c.get("/akasha/api/v1/sap", params={"project_id": solar.project_id}, headers={"X-API-Key": wkey}).status_code == 403,
              "Wind key refused ?project_id= of a Solar project")
        check(c.get("/akasha/api/v1/transmission-network", headers={"X-API-Key": wkey}).status_code == 403,
              "Wind key refused the all-portfolio network")
        kid = db.query(AkashaApiKey.id).filter(AkashaApiKey.name == PREFIX + "wind").scalar()
        admin.post(f"/akasha/api/admin/api-keys/{kid}/revoke")
        check(c.get("/akasha/api/v1/projects", headers={"X-API-Key": wkey}).status_code == 401, "revoked key -> 401")

        print("\n2. Fixes for the issues list")
        projs, _ = all_rows(c, "/akasha/api/v1/projects", key)
        check(all(p["portfolio"] for p in projs), "every project has a portfolio", f"{sum(1 for p in projs if not p['portfolio'])} without")
        tc, _ = all_rows(c, "/akasha/api/v1/transmission", key)
        sigs = [(t["region"], t["tc_project_name"], t["phase"], t["kps"], t["pss"], t["block"], t["breakup"], t["mw"], t["mapping_id"]) for t in tc]
        check(all(isinstance(t["tc_project_name"], (str, type(None))) for t in tc) and all(isinstance(t["project"], (dict, type(None))) for t in tc),
              "transmission keeps its own project name beside the project block")
        check(len(sigs) == len(set(sigs)), "transmission has no duplicate rows",
              f"{len(tc)} rows, {sum(len(t['duplicate_ids']) for t in tc)} duplicates folded")
        r = c.get("/akasha/api/v1/material-documents", params={"page_size": 200}, headers={"X-API-Key": key}).json()["data"]
        check(r and all(x.get("block_plot_name") is None for x in r), "material documents: 'nan' text returned as null")
        p6 = c.get("/akasha/api/v1/p6", params={"page_size": 200}, headers={"X-API-Key": key}).json()["data"]
        bandha = next((x for x in p6 if "BANDHA" in (x.get("name") or "")), None)
        check(bandha and bandha["finish_variance_days_derived"] == -133 and bandha["duration_unit"] == "hours",
              "P6 derived variance in calendar days (Bandha -133) and duration unit", bandha and bandha["finish_variance_days_derived"])
        tr = c.get("/akasha/api/v1/trial-run", params={"page_size": 200}, headers={"X-API-Key": key}).json()
        filled = sum(1 for x in tr["data"] if x.get("spv_plant_code"))
        check(all("spv_plant_code_source" in x for x in tr["data"]), "trial run marks where the SPV plant code came from",
              f"{filled} of {len(tr['data'])} on page 1 have a code")
        sap = c.get("/akasha/api/v1/sap", params={"page_size": 200}, headers={"X-API-Key": key}).json()["data"]
        pct = lambda f: round(100 * sum(1 for x in sap if x.get(f)) / max(len(sap), 1))
        check(pct("plant_code") > 80 and pct("vendor_code") > 50, "SAP rows carry plant and vendor code",
              f"plant {pct('plant_code')}%, vendor code {pct('vendor_code')}%, storage {pct('storage_location')}%")
        inv = c.get("/akasha/api/v1/inventory", params={"page_size": 200}, headers={"X-API-Key": key}).json()["data"]
        check(inv and all(x.get("material_type") and x.get("plant_name") for x in inv), "inventory carries material type and plant name")

        print("\n3. New endpoints")
        for path, label in [("/akasha/api/v1/p6-baselines", "P6 baselines"), ("/akasha/api/v1/wbs", "WBS tree"),
                            ("/akasha/api/v1/notifications", "notifications")]:
            r = c.get(path, params={"page_size": 5}, headers={"X-API-Key": key})
            body = r.json() if r.status_code == 200 else {}
            check(r.status_code == 200 and body["meta"]["total"] > 0 and all(x.get("project_id") for x in body["data"]),
                  f"{label} returned and linked to projects", body.get("meta", {}).get("total"))
        r = c.get("/akasha/api/v1/transmission-network", headers={"X-API-Key": key}).json()["data"]
        check(len(r["nodes"]) > 0 and len(r["edges"]) > 0 and "stringing" in r["edges"][0], "transmission network with progress fields",
              f"{len(r['nodes'])} nodes, {len(r['edges'])} edges")
        d = c.get("/akasha/api/v1/dictionary", headers={"X-API-Key": key})
        check(d.status_code == 200 and d.json()["data"]["values"]["pulse_nc.status (status_label)"], "dictionary returns units and live value lists")
    finally:
        cleanup(db)
        db.close()
    print(f"\n{'ALL V1 CHECKS PASSED' if not failures else 'FAILED: ' + '; '.join(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(run())
