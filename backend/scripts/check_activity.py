"""End-to-end check of the activity trail: who is online, data changes,
refused calls, security alerts, departments and the CSV exports.

Creates temporary zz_test_* accounts, drives the real app in-process with
FastAPI's TestClient, and removes the accounts, sessions and every audit row
the run produced. Changes nothing else: the one data write it makes targets a
mapping id that does not exist. Exits non-zero on any failure.

    cd backend && ./venv/Scripts/python.exe scripts/check_activity.py
"""
import csv
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from database import SessionLocal  # noqa: E402
from models import AkashaAuditLog  # noqa: E402
from scripts.check_access import PREFIX, check, cleanup as cleanup_users, client_for, failures, make_user  # noqa: E402

TEST_IP = "203.0.113.77"          # TEST-NET-3: never a real client
BAD_KEY = "ak_zztest_not_a_real_key"
API = "/akasha/api"


def cleanup(db) -> None:
    db.query(AkashaAuditLog).filter(
        (AkashaAuditLog.ip == TEST_IP) | (AkashaAuditLog.target == BAD_KEY[:10])
    ).delete(synchronize_session=False)
    db.commit()
    cleanup_users(db)


def actions(db, **f) -> list:
    return db.query(AkashaAuditLog).filter_by(**f).order_by(AkashaAuditLog.id).all()


def main_() -> int:
    db = SessionLocal()
    cleanup(db)
    try:
        pws = {"super": make_user(db, "super", "superadmin"), "tcs": make_user(db, "tcs", "tc_stores"),
               "raj": make_user(db, "raj", "projects", portfolios=["Solar Rajasthan"])}
        sup = client_for("super", pws["super"])
        raj = client_for("raj", pws["raj"])
        tcs = client_for("tcs", pws["tcs"])
        users = {u["username"]: u for u in sup.get(f"{API}/admin/users").json()["users"]}

        print("\n1. Departments")
        r = sup.patch(f"{API}/admin/users/{users[PREFIX + 'raj']['id']}", json={"department": "  Projects   Solar "})
        check(r.status_code == 200 and r.json()["user"]["department"] == "Projects Solar", "department saved, spacing tidied")
        sup.patch(f"{API}/admin/users/{users[PREFIX + 'tcs']['id']}", json={"department": "TC Stores"})
        depts = sup.get(f"{API}/admin/departments").json()["departments"]
        check({"Projects Solar", "TC Stores"} <= set(depts), "department list offers both")
        check(sup.patch(f"{API}/admin/users/{users[PREFIX + 'tcs']['id']}", json={"department": "x" * 61}).status_code == 400,
              "over-long department refused")

        print("\n2. Who is online, and on which screen")
        raj.get(f"{API}/auth/me", headers={"x-akasha-view": "/projects/overview"})
        act = sup.get(f"{API}/admin/activity").json()
        mine = [s for s in act["sessions"] if s["username"] == PREFIX + "raj"]
        check(len(mine) == 1 and mine[0]["online"] and mine[0]["view"] == "/projects/overview",
              "online now, with the screen they have open", str(mine[:1]))
        check(mine and mine[0]["department"] == "Projects Solar", "session carries the department")
        dept = next((d for d in act["departments"] if d["department"] == "Projects Solar"), None)
        check(dept is not None and dept["users"] == 1 and dept["online"] == 1 and dept["sign_ins"] >= 1,
              "department roll-up: 1 user, online, signed in", str(dept))
        check(act["summary"]["online_now"] >= 3, "summary counts online people")
        check(tcs.get(f"{API}/admin/activity").status_code == 403, "activity needs audit.view")

        print("\n3. Data changes are recorded")
        r = sup.put(f"{API}/mappings/987654321", json={"project": "x"}, headers={"x-forwarded-for": TEST_IP})
        rows = actions(db, action="data.change", actor_username=PREFIX + "super")
        check(len(rows) == 1 and rows[0].target == "/api/mappings/987654321" and rows[0].detail["status"] == r.status_code
              and rows[0].detail["ok"] is False and rows[0].ip == TEST_IP,
              "edit recorded with who, what, result and address", str([(a.target, a.detail) for a in rows]))
        r = tcs.put(f"{API}/mappings/987654321", json={"project": "x"})
        check(r.status_code == 403, "user without data.edit refused")
        check(len(actions(db, action="access.denied", actor_username=PREFIX + "tcs")) == 1,
              "the refusal is recorded as access.denied")
        check(not actions(db, action="data.change", actor_username=PREFIX + "tcs"), "a refused write is not logged as a change")
        n = db.query(AkashaAuditLog).filter(AkashaAuditLog.actor_username == PREFIX + "raj").count()
        raj.get(f"{API}/auth/me")
        check(db.query(AkashaAuditLog).filter(AkashaAuditLog.actor_username == PREFIX + "raj").count() == n,
              "plain reads are not logged")

        print("\n4. Refused calls -> alerts")
        for _ in range(3):
            raj.get(f"{API}/dashboard/summary?portfolio=Wind")
        denied = actions(db, action="access.denied", actor_username=PREFIX + "raj")
        check(len(denied) == 1 and denied[0].severity == "warning", "repeat of the same refused call logged once",
              f"{len(denied)} rows")
        for p in ["BESS", "Solar Khavda", "Wind,BESS"]:
            raj.get(f"{API}/dashboard/summary?portfolio={p}")
        raj.get(f"{API}/bess/projects")
        burst = actions(db, action="access.denied_repeated", actor_username=PREFIX + "raj")
        check(len(burst) == 1 and burst[0].severity == "critical", "5 refusals in 10 min -> one critical alert")

        TestClient(main.app, base_url="https://testserver").get(f"{API}/v1/projects", headers={"x-api-key": BAD_KEY})
        check(len(actions(db, action="api_key.invalid", target=BAD_KEY[:10])) == 1, "a bad API key is recorded")

        anon = TestClient(main.app, base_url="https://testserver")
        for i in range(10):
            anon.post(f"{API}/auth/login", json={"username": f"{PREFIX}nobody{i}", "password": "wrong-password-1"},
                      headers={"x-forwarded-for": TEST_IP})
        burst = actions(db, action="login.burst", ip=TEST_IP)
        check(len(burst) == 1 and burst[0].severity == "critical" and burst[0].detail["usernames_tried"] == 10,
              "10 failed sign-ins from one address -> critical alert", str([b.detail for b in burst]))

        r = sup.patch(f"{API}/admin/users/{users[PREFIX + 'tcs']['id']}", json={"role": "superadmin"})
        check(r.status_code == 200 and len(actions(db, action="user.privileged_change", target=PREFIX + "tcs")) == 1,
              "granting superadmin raises an alert")

        print("\n5. Alert badge and acknowledgement")
        summ = sup.get(f"{API}/admin/alerts/summary").json()
        check(summ["open"] >= 4 and summ["critical"] >= 2 and summ["latest"] is not None, "badge counts open alerts", str(summ))
        mine = sup.get(f"{API}/admin/audit", params={"open_alerts": "true", "user": PREFIX + "raj"}).json()["entries"]
        ids = [e["id"] for e in mine]
        r = sup.post(f"{API}/admin/alerts/acknowledge", json={"ids": ids})
        check(r.status_code == 200 and r.json()["acknowledged"] == len(ids) > 0, "acknowledge selected alerts")
        after = sup.get(f"{API}/admin/alerts/summary").json()
        check(after["open"] == summ["open"] - len(ids), "badge drops by what was acknowledged")
        row = db.query(AkashaAuditLog).filter(AkashaAuditLog.id == ids[0]).first()
        db.refresh(row)
        check(row.acknowledged_by == PREFIX + "super", "who acknowledged is kept")

        print("\n6. Filters and exports")
        r = sup.get(f"{API}/admin/audit", params={"department": "Projects Solar", "category": "access"}).json()
        check(r["total"] >= 2 and all(e["department"] == "Projects Solar" for e in r["entries"]),
              "filter by department + category", f"{r['total']} rows")
        r = sup.get(f"{API}/admin/audit/export", params={"department": "Projects Solar"})
        rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
        check(r.status_code == 200 and rows[0][:4] == ["time_ist", "time_utc", "severity", "event"] and len(rows) > 3,
              "activity CSV with the same filters", f"{len(rows) - 1} rows")
        check(len(actions(db, action="audit.exported", actor_username=PREFIX + "super")) == 1, "the export itself is recorded")
        r = sup.get(f"{API}/admin/users/export")
        rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
        check(r.status_code == 200 and any(x[0] == PREFIX + "raj" and x[3] == "Projects Solar" for x in rows),
              "user list CSV includes department")
        check(raj.get(f"{API}/admin/audit/export").status_code == 403, "export needs audit.view")

        print("\n7. End one session")
        ref = next(s["ref"] for s in sup.get(f"{API}/admin/activity").json()["sessions"] if s["username"] == PREFIX + "raj")
        check(sup.post(f"{API}/admin/sessions/{ref}/end").status_code == 200, "session ended")
        check(raj.get(f"{API}/auth/me").status_code == 401, "that browser is signed out")
        check(len(actions(db, action="session.ended", target=PREFIX + "raj")) == 1, "ending it is recorded")
        check(sup.post(f"{API}/admin/sessions/{ref}/end").status_code == 404, "ending it twice -> 404")
    finally:
        db.rollback()
        cleanup(db)
        left = db.query(AkashaAuditLog).filter(
            AkashaAuditLog.actor_username.like(PREFIX + "%") | AkashaAuditLog.target.like(PREFIX + "%")
            | (AkashaAuditLog.ip == TEST_IP)).count()
        print(f"\ncleanup: {left} test audit rows left")
        db.close()

    print(f"\n{'ALL ACTIVITY CHECKS PASSED' if not failures else 'FAILED: ' + '; '.join(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main_())
