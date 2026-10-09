"""End-to-end check of sign-in, roles, permissions and portfolio scope.

Creates temporary zz_test_* accounts, drives the real app in-process with
FastAPI's TestClient (cookies and all), and removes the accounts, their
sessions and their audit rows afterwards. Exits non-zero on any failure.

    cd backend && ./venv/Scripts/python.exe scripts/check_access.py
"""
import os
import secrets
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import func  # noqa: E402

import main  # noqa: E402  (runs schema upgrade and role seeding)
from database import SessionLocal  # noqa: E402
from models import AkashaAuditLog, AkashaRole, AkashaSession, AkashaUser, ProjectMapping  # noqa: E402
from services import access, portfolio, security  # noqa: E402

PREFIX = "zz_test_"
failures: list[str] = []


def check(ok: bool, label: str, detail: str = "") -> None:
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}{(' - ' + detail) if detail else ''}")
    if not ok:
        failures.append(label)


def make_user(db, name: str, role: str, must_change=False, portfolios=None) -> str:
    pw = secrets.token_urlsafe(12) + "aA1!"
    db.add(AkashaUser(username=PREFIX + name, display_name=f"Test {name}", role=role, is_active=True,
                      password_hash=security.hash_password(pw), must_change_password=must_change,
                      portfolios=portfolios))
    db.commit()
    return pw


def client_for(name: str, pw: str) -> TestClient:
    c = TestClient(main.app, base_url="https://testserver")
    r = c.post("/akasha/api/auth/login", json={"username": PREFIX + name, "password": pw})
    assert r.status_code == 200, (name, r.status_code, r.text)
    return c


def cleanup(db) -> None:
    ids = [u.id for u in db.query(AkashaUser).filter(AkashaUser.username.like(PREFIX + "%"))]
    if ids:
        db.query(AkashaSession).filter(AkashaSession.user_id.in_(ids)).delete(synchronize_session=False)
    db.query(AkashaAuditLog).filter(
        AkashaAuditLog.target.like(PREFIX + "%") | AkashaAuditLog.actor_username.like(PREFIX + "%")
    ).delete(synchronize_session=False)
    db.query(AkashaUser).filter(AkashaUser.username.like(PREFIX + "%")).delete(synchronize_session=False)
    db.query(AkashaRole).filter(AkashaRole.key.like(PREFIX + "%")).delete(synchronize_session=False)
    db.commit()


def main_() -> int:
    db = SessionLocal()
    cleanup(db)
    try:
        pws = {n: make_user(db, n, r) for n, r in [
            ("super", "superadmin"), ("exec", "executive"), ("tcs", "tc_stores")]}
        pws["solar"] = make_user(db, "solar", "pmag", portfolios=["Solar Khavda", "Solar Rajasthan"])
        pws["wind"] = make_user(db, "wind", "pmag", portfolios=["Wind"])
        pws["raj"] = make_user(db, "raj", "projects", portfolios=["Solar Rajasthan"])
        pws["mix"] = make_user(db, "mix", "projects", portfolios=["Solar Khavda", "Wind"])
        pws["fresh"] = make_user(db, "fresh", "executive", must_change=True)

        print("\n1. Sign-in")
        anon = TestClient(main.app, base_url="https://testserver")
        check(anon.get("/akasha/api/dashboard/summary").status_code == 401, "API refuses a caller with no session")
        r = anon.post("/akasha/api/auth/login", json={"username": PREFIX + "exec", "password": "wrong-password"})
        check(r.status_code == 401 and r.json()["detail"] == "Incorrect username or password",
              "wrong password -> generic message")
        r = anon.post("/akasha/api/auth/login", json={"username": PREFIX + "nobody", "password": "whatever-123"})
        check(r.status_code == 401 and r.json()["detail"] == "Incorrect username or password",
              "unknown user -> same generic message")
        c = TestClient(main.app, base_url="https://testserver")
        r = c.post("/akasha/api/auth/login", json={"username": (PREFIX + "exec").upper(), "password": pws["exec"]})
        check(r.status_code == 200, "username is case-insensitive")
        sc = r.headers.get("set-cookie", "")
        check("httponly" in sc.lower() and "samesite=lax" in sc.lower() and "secure" in sc.lower(),
              "session cookie is HttpOnly, SameSite=Lax, Secure over https", sc.split(";")[0][:24] + "...")
        raw = c.cookies.get(security.SESSION_COOKIE)
        stored = db.query(AkashaSession).filter(AkashaSession.token == raw).first()
        check(stored is None, "raw session token is not stored in the database")
        me = c.get("/akasha/api/auth/me").json()["user"]
        check(len(me["dashboards"]) == 5, "executive opens all 5 dashboards", ", ".join(d["key"] for d in me["dashboards"]))
        check(me["portfolio_access"]["all"], "executive sees every portfolio")
        check(c.get("/akasha/api/dashboard/summary").status_code == 200, "signed-in executive reads data")
        c.post("/akasha/api/auth/logout")
        check(c.get("/akasha/api/dashboard/summary").status_code == 401, "after sign-out the session is dead")

        print("\n2. Lockout")
        for _ in range(security.LOCKOUT_ATTEMPTS):
            anon.post("/akasha/api/auth/login", json={"username": PREFIX + "tcs", "password": "bad-password-x"})
        r = anon.post("/akasha/api/auth/login", json={"username": PREFIX + "tcs", "password": pws["tcs"]})
        check(r.status_code == 423, f"{security.LOCKOUT_ATTEMPTS} failures lock the account, even the right password is refused")
        sup = client_for("super", pws["super"])
        uid = db.query(AkashaUser.id).filter(AkashaUser.username == PREFIX + "tcs").scalar()
        check(sup.post(f"/akasha/api/admin/users/{uid}/unlock").status_code == 200, "superadmin unlocks it")
        check(anon.post("/akasha/api/auth/login", json={"username": PREFIX + "tcs", "password": pws["tcs"]}).status_code == 200,
              "unlocked account signs in")

        print("\n3. Forced password change")
        f = client_for("fresh", pws["fresh"])
        r = f.get("/akasha/api/dashboard/summary")
        check(r.status_code == 403 and r.json()["code"] == "password_change_required", "data blocked until password changed")
        check(f.post("/akasha/api/auth/password", json={"current_password": pws["fresh"], "new_password": "short"}).status_code == 400,
              "weak new password refused")
        new_pw = "Kh@vda-" + secrets.token_hex(6)
        r = f.post("/akasha/api/auth/password", json={"current_password": pws["fresh"], "new_password": new_pw})
        check(r.status_code == 200 and not r.json()["user"]["must_change_password"], "strong new password accepted")
        check(f.get("/akasha/api/dashboard/summary").status_code == 200, "data opens after the change")

        print("\n4. Permissions")
        tcs = client_for("tcs", pws["tcs"])
        check(tcs.post("/akasha/api/sharepoint/sync").status_code == 403, "tc_stores cannot trigger a data sync")
        check(tcs.put("/akasha/api/mappings/0", json={}).status_code == 403, "tc_stores cannot edit mappings")
        check(tcs.get("/akasha/api/admin/users").status_code == 403, "tc_stores cannot open user admin")
        ex = client_for("exec", pws["exec"])
        check(ex.get("/akasha/api/admin/users").status_code == 403, "executive cannot open user admin")
        check(ex.post("/akasha/api/sharepoint/sync").status_code == 403, "executive cannot trigger a sync (data.sync)")
        check(sup.get("/akasha/api/admin/users").status_code == 200, "superadmin opens user admin")
        check(sup.get("/akasha/api/admin/audit").status_code == 200, "superadmin reads the audit log")
        me_s = sup.get("/akasha/api/auth/me").json()["user"]
        check(set(me_s["permissions"]) == access.PERMISSION_KEYS, "superadmin holds every permission")

        print("\n5. Admin guard rails")
        r = sup.post("/akasha/api/admin/users", json={"username": PREFIX + "made", "display_name": "Made", "role": "pmag",
                                                      "portfolios": ["BESS"]})
        check(r.status_code == 200 and r.json()["temporary_password"], "create user returns a one-time temporary password")
        check(r.status_code == 200 and r.json()["user"]["portfolios"] == ["BESS"], "new user carries the portfolios chosen")
        check(sup.post("/akasha/api/admin/users", json={"username": PREFIX + "bad", "display_name": "x", "role": "pmag",
                                                        "portfolios": ["Mars"]}).status_code == 400, "unknown portfolio refused")
        made_pw = r.json()["temporary_password"]
        check(sup.post("/akasha/api/admin/users", json={"username": PREFIX + "made", "display_name": "x", "role": "pmag"}).status_code == 409,
              "duplicate username refused")
        mc = TestClient(main.app, base_url="https://testserver")
        r = mc.post("/akasha/api/auth/login", json={"username": PREFIX + "made", "password": made_pw})
        check(r.status_code == 200 and r.json()["user"]["must_change_password"], "new user must change the temporary password")
        sid = db.query(AkashaUser.id).filter(AkashaUser.username == PREFIX + "super").scalar()
        check(sup.patch(f"/akasha/api/admin/users/{sid}", json={"is_active": False}).status_code == 400,
              "superadmin cannot deactivate themself")
        check(sup.patch(f"/akasha/api/admin/users/{sid}", json={"role": "executive"}).status_code == 400,
              "superadmin cannot demote themself")
        check(sup.patch("/akasha/api/admin/roles/superadmin", json={"permissions": []}).status_code == 400,
              "Super Admin role cannot be edited")
        check(sup.delete("/akasha/api/admin/roles/executive").status_code == 400, "built-in roles cannot be deleted")
        # A user manager who is not superadmin cannot escalate.
        db.add(AkashaRole(key=PREFIX + "usermgr", name="Test user manager", permissions=["users.manage"], is_system=False))
        db.commit()
        access.invalidate()
        pws["mgr"] = make_user(db, "mgr", PREFIX + "usermgr")
        mgr = client_for("mgr", pws["mgr"])
        check(mgr.post("/akasha/api/admin/users", json={"username": PREFIX + "evil", "display_name": "x", "role": "superadmin"}).status_code == 403,
              "user manager cannot create a superadmin")
        check(mgr.patch(f"/akasha/api/admin/users/{sid}", json={"display_name": "hacked"}).status_code == 403,
              "user manager cannot edit a superadmin account")
        check(mgr.patch(f"/akasha/api/admin/roles/{PREFIX}usermgr", json={"permissions": ["users.manage", "roles.manage"]}).status_code == 403,
              "user manager cannot grant themselves more")
        wid = db.query(AkashaUser.id).filter(AkashaUser.username == PREFIX + "wind").scalar()
        r = sup.patch(f"/akasha/api/admin/users/{wid}", json={"is_active": False})
        check(r.status_code == 200, "superadmin deactivates a user")
        check(anon.post("/akasha/api/auth/login", json={"username": PREFIX + "wind", "password": pws["wind"]}).status_code == 401,
              "deactivated user cannot sign in")
        sup.patch(f"/akasha/api/admin/users/{wid}", json={"is_active": True})

        print("\n6. Portfolio scope (PMAG user with Solar Khavda + Solar Rajasthan)")
        so = client_for("solar", pws["solar"])
        me = so.get("/akasha/api/auth/me").json()["user"]
        check([d["key"] for d in me["dashboards"]] == ["pmag"], "PMAG Solar opens only the PMAG dashboard")
        check(not me["portfolio_access"]["all"] and me["portfolio_access"]["clusters"] == ["Solar Khavda", "Solar Rajasthan"],
              "scoped to Solar Khavda + Solar Rajasthan", ", ".join(me["portfolio_access"]["clusters"]))
        check(so.get("/akasha/api/pmag/dashboard", params={"portfolio": "Wind"}).status_code == 403, "asking for Wind is refused")
        check(so.get("/akasha/api/dashboard/summary", params={"portfolio": "BESS"}).status_code == 403, "asking for BESS is refused")
        r = so.get("/akasha/api/pmag/dashboard")
        check(r.status_code == 200, "no portfolio given -> narrowed to the user's own portfolios")
        check(so.get("/akasha/api/dashboard/summary", params={"portfolio": "Solar Khavda,Wind"}).status_code == 403,
              "a list that includes a foreign portfolio is refused")
        r = so.get("/akasha/api/dashboard/summary")
        names = [p.get("project_name") or p.get("name") for p in (r.json().get("projects") or [])] if r.status_code == 200 else []
        solar = {(m.project or "").lower() for m in db.query(ProjectMapping).filter(ProjectMapping.cluster.ilike("Solar%"))} | \
                {(m.project_name_from_p6 or "").lower() for m in db.query(ProjectMapping).filter(ProjectMapping.cluster.ilike("Solar%"))}
        leaked = [n for n in names if n and n.lower() not in solar]
        check(r.status_code == 200 and not leaked and len(names) > 45, "summary returns Khavda + Rajasthan projects only",
              f"{len(names)} projects" + (f", leaked: {leaked[:3]}" if leaked else ""))
        for cluster in me["portfolio_access"]["clusters"]:
            check(so.get("/akasha/api/financials", params={"portfolio": cluster}).status_code == 200, f"own cluster '{cluster}' opens")
        wind_p = db.query(ProjectMapping).filter(ProjectMapping.cluster.ilike("Wind%"), ProjectMapping.project_id.isnot(None)).first()
        solar_p = db.query(ProjectMapping).filter(ProjectMapping.cluster.ilike("Solar%"), ProjectMapping.project_id.isnot(None)).first()
        if wind_p:
            check(so.get(f"/akasha/api/project-360/{wind_p.project_id}/detail").status_code == 403, "a Wind project's detail is refused")
            check(so.get("/akasha/api/financials", params={"portfolio": "Solar Khavda", "project_name": wind_p.project}).status_code == 403,
                  "a Wind project named inside a Solar query is refused")
        if solar_p:
            check(so.get(f"/akasha/api/project-360/{solar_p.project_id}/detail").status_code != 403, "a Solar project's detail opens")
        check(so.get("/akasha/api/bess/projects").status_code == 403, "BESS namespace is refused")
        check(so.get("/akasha/api/solar/portfolio/cpag").status_code != 403, "Solar CPAG (Rajasthan) open to a Khavda+Rajasthan user")
        check(so.get("/akasha/api/dashboard/search", params={"q": "khavda"}).status_code == 403,
              "non-portfolio-aware endpoint (search) is refused")
        r = so.get("/akasha/api/module-deliveries/summary")
        md = (r.json().get("projects") or []) if r.status_code == 200 else []
        bad = [p["project_name"] for p in md if (p.get("cluster") or "") not in ("Solar Khavda", "Solar Rajasthan")]
        check(r.status_code == 200 and md and not bad, "module deliveries narrowed to Solar", f"{len(md)} projects" + (f", leaked {bad[:3]}" if bad else ""))
        from sqlalchemy import func as _f
        from models import PulseNC
        solar_ncs = db.query(_f.count(PulseNC.id)).filter(PulseNC.project_type == "solar").scalar()
        r = so.get("/akasha/api/quality/overview").json()
        check(r.get("total_ncs", r.get("total")) == solar_ncs, "quality overview counts Solar NCs only", f"{r.get('total_ncs', r.get('total'))} of {solar_ncs} solar")
        r = so.get("/akasha/api/quality/by-project").json()
        unmatched = r.get("unmatched_projects") or []
        check(all("solar" in (u.get("project_type") or "solar").lower() for u in unmatched), "quality by-project shows no other portfolio's NCs")
        r = so.get("/akasha/api/quality/ncs", params={"page_size": 200}).json()
        check(r.get("total") == solar_ncs, "quality NC list holds Solar NCs only", f"{r.get('total')} of {solar_ncs} solar")
        check(so.get("/akasha/api/dashboard/search", params={"q": "wind"}).status_code == 403, "search still refused (not portfolio-aware)")

        print("\n6b. Single cluster and mixed portfolios")
        rj = client_for("raj", pws["raj"])
        me = rj.get("/akasha/api/auth/me").json()["user"]
        check(me["portfolio_access"]["clusters"] == ["Solar Rajasthan"], "Rajasthan-only user sees one cluster")
        check(rj.get("/akasha/api/summary", params={"portfolio": "Solar Khavda"}).status_code == 403, "Rajasthan user refused Khavda")
        check(rj.get("/akasha/api/solar/portfolio/cpag").status_code != 403, "Rajasthan user opens the Solar (Rajasthan) pack")
        raj_p = db.query(ProjectMapping).filter(ProjectMapping.cluster == "Solar Rajasthan", ProjectMapping.project_id.isnot(None)).first()
        if raj_p:
            check(rj.get(f"/akasha/api/project-360/{raj_p.project_id}/detail").status_code != 403, "own Rajasthan project opens")
        if solar_p and solar_p.cluster == "Solar Khavda":
            check(rj.get(f"/akasha/api/project-360/{solar_p.project_id}/detail").status_code == 403, "a Khavda project is refused")
        mx = client_for("mix", pws["mix"])
        check(mx.get("/akasha/api/dashboard/summary", params={"portfolio": "Solar Khavda,Wind"}).status_code == 200,
              "Khavda + Wind user may ask for both at once")
        check(mx.get("/akasha/api/wind/portfolio/cpag").status_code != 403 and mx.get("/akasha/api/bess/projects").status_code == 403,
              "Khavda + Wind user: wind API open, BESS API refused")
        check(mx.get("/akasha/api/solar/portfolio/cpag").status_code == 403,
              "Khavda user refused the Solar pack (it covers Rajasthan projects)")
        r = mx.get("/akasha/api/dashboard/summary")
        projs = (r.json().get("projects") or []) if r.status_code == 200 else []
        names = [p.get("project_name") for p in projs]
        clusters = {portfolio.mapping_cluster(m) for m in db.query(ProjectMapping).filter(ProjectMapping.project.in_(names))}
        check(r.status_code == 200 and bool(clusters) and clusters <= {"Solar Khavda", "Wind"},
              "no portfolio given -> both of the user's portfolios, nothing else", ", ".join(sorted(c or "-" for c in clusters)))

        print("\n7. Role change takes effect")
        so_id = db.query(AkashaUser.id).filter(AkashaUser.username == PREFIX + "solar").scalar()
        sup.patch(f"/akasha/api/admin/users/{so_id}", json={"portfolios": ["Wind"]})
        check(so.get("/akasha/api/auth/me").status_code == 401, "portfolio change ends the user's sessions")
    finally:
        cleanup(db)
        access.invalidate()
        left = db.query(func.count(AkashaUser.id)).filter(AkashaUser.username.like(PREFIX + "%")).scalar()
        print(f"\ncleanup: {left} test accounts left")
        db.close()

    print(f"\n{'ALL ACCESS CHECKS PASSED' if not failures else 'FAILED: ' + '; '.join(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main_())
