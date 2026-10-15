"""Self-test of the whole email workflow, on a throw-away demo project.

Runs every path through the real code and checks the result:
  1. Module ordering ladder - L1 at 30 days, L2 at 15, L3 at 7 / the ordering
     date; acknowledgement with an expected date holds the level
  2. Approval request -> approve (not by the requester) -> freeze in the plan
  3. Approval returned (remarks required) -> email with the remarks
  4. LTA edit needs a reason -> schedule-change email with who and why
  5. A sync change -> email straight away, never twice
  6. Each email: no unfilled {{variables}}, the right buttons, the Adani
     banner travelling inside the message
  7. Project-delay and AOP triggers on the real projects (read only)

Safe on a live server:
  - NOTHING is emailed: sending is replaced for the run, and template on/off
    switches in the database are never touched
  - the engine sees only the demo project; real projects are only read (7)
  - everything it creates (demo project, alerts, logged emails, test users,
    demo recipients) is removed at the end, pass or fail
  - refuses while email is live (EMAIL_ENABLED=true, EMAIL_TEST_MODE=false)
    unless --force, so the scheduler cannot email the demo's test addresses

Usage, from backend/ with the venv:
    python scripts/email_selftest.py
Exit code 0 when every check passes.
"""
import argparse
import os
import sys
from datetime import datetime, timedelta

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)
from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(BACKEND, ".env"))

from fastapi import BackgroundTasks, HTTPException  # noqa: E402
from starlette.requests import Request  # noqa: E402

import models  # noqa: E402
from services import demo_scope  # noqa: E402

demo_scope.show_all()   # these scripts work on the demo projects
from database import SessionLocal  # noqa: E402
from routers import alerts as AR, mappings as MR  # noqa: E402
from services import date_history, order_approvals as OA  # noqa: E402
from services.email_notify import alerts as A, config, context as C, engine, render, sender  # noqa: E402

sys.path.insert(0, os.path.join(BACKEND, "scripts"))
import demo_email_project as demo  # noqa: E402

DEMO = demo.PROJECT_ID
TESTER, HEAD = "selftest_orderer", "selftest_head"
# Its own portfolio and marker: it never sees, nor removes, a demo set up for manual testing.
PORTFOLIO, MARK = "Akasha Demo Selftest", "email-selftest"
fails = []


def check(name, ok, info=""):
    print(("  PASS  " if ok else "  FAIL  ") + name + (f"   [{info}]" if info and not ok else ""))
    if not ok:
        fails.append(name + (f" - got: {info}" if info else ""))


def main():
    ap = argparse.ArgumentParser(description="Email workflow self-test on a throw-away demo project")
    ap.add_argument("--force", action="store_true", help="run even while email is live")
    args = ap.parse_args()

    real = config.settings()
    if real.enabled and not real.test_mode and not args.force:
        print("Email is LIVE here (EMAIL_ENABLED=true, EMAIL_TEST_MODE=false). The self-test sends nothing itself,\n"
              "but while it runs the scheduler could email the demo's test addresses. Run it with EMAIL_TEST_MODE=true,\n"
              "or pass --force.")
        return 2

    db = SessionLocal()
    if demo.mapping(db):
        print("The created demo project (DEMO - Akasha Email Test) exists - the self-test needs it for itself.\n"
              "Remove it first: python scripts/demo_email_project.py --remove")
        return 2

    # ── Stubs: capture instead of send; the engine sees only the demo ──────
    mails = []
    sender_send = sender.send

    def capture(cfg, to, cc, subject, html, text, attachments=None, tag=""):
        mails.append({"to": list(to), "cc": list(cc), "subject": subject, "html": html,
                      "att": [a[0] for a in (attachments or [])]})
        return "selftest"
    sender.send = capture
    cfg = config.settings()
    cfg.enabled, cfg.test_mode, cfg.server = True, False, cfg.server or "selftest"
    cfg.from_addr = cfg.from_addr or "akasha@adani.com"
    cfg.public_url = cfg.public_url or "https://akasha.example/akasha"
    config.settings = lambda: cfg
    engine.settings = lambda: cfg
    Data = engine.Data

    class DemoData(Data):
        def __init__(self, db_):
            super().__init__(db_)
            self.cfg = cfg
            self.projects = [p for p in self.projects if p.get("project_id") == DEMO]
    engine.Data = DemoData
    real_today = C.today

    def at(day):
        C.today = lambda: day
        A.C.today = C.today
        AR.C.today = C.today

    req = Request({"type": "http", "headers": [], "client": ("127.0.0.1", 0)})
    print("Akasha email self-test\n")
    try:
        demo.create(db, 30, ["selftest.l1@adani.com"], mark=MARK, portfolio=PORTFOLIO)
        for email, lv in (("selftest.l2@adani.com", 2), ("selftest.l3@adani.com", 3)):
            db.add(models.EmailRecipient(group_key="tc_ordering", name=f"Self-test L{lv}", email=email, level=lv,
                                         portfolios=[PORTFOLIO], active=True, created_by=MARK))
        orderer = models.AkashaUser(username=TESTER, password_hash="x", display_name="Self-test Orderer", role="tc_ordering",
                                    email="selftest.l1@adani.com", is_active=True, portfolios=[PORTFOLIO])
        head = models.AkashaUser(username=HEAD, password_hash="x", display_name="Self-test Head", role="tc_head",
                                 email="selftest.head@adani.com", is_active=True, portfolios=[PORTFOLIO])
        db.add_all([orderer, head])
        db.commit()
        engine.seed_templates(db)
        keys = ["ordering_due_30", "ordering_due_today", "ordering_overdue"]
        m = demo.mapping(db)
        p = engine.Data(db).projects[0]
        due = C.parse_day(next(ph for rows in p["month_phases"].values() for ph in rows)["order_date"])
        month = next(k for k, v in p["month_mwp"].items() if v)
        # The days this server's template really uses (editable per template).
        stage = {lv: n for lv, n in A.due_stages(db.get(models.EmailTemplate, "ordering_due_30"))}
        d1, d2, d3 = stage.get(1), stage.get(2), stage.get(3)
        print(f"\n  Demo project: ordering date {C.fmt_day(due)}, {p['month_mwp'][month]} MWp in {month}")
        print(f"  'Module ordering - due' sends L1 at {d1}, L2 at {d2}, L3 at {d3} days before\n")
        if not (d1 and d2 and d3 and 30 >= d1 > d2 > d3 >= 1):
            check("The template has L1 > L2 > L3 days with L1 at most 30 (the self-test project is 30 days out)", False, stage)
            return 1

        print("1. Module ordering ladder")
        at(due - timedelta(days=d1)); mails.clear(); engine.run(db, "selftest", only=keys)
        e1 = [x for x in mails if "DEMO" in x["subject"]]
        check(f"{d1} days before: one L1 email", len(e1) == 1, [x["subject"] for x in mails])
        check(f"{d1} days before: only L1 people", e1 and set(e1[0]["to"]) == {"selftest.l1@adani.com"}, e1 and e1[0]["to"])
        check("Acknowledge button links to the alert", e1 and "/alerts/" in e1[0]["html"])
        check("No unfilled {{variables}}", e1 and "{{" not in e1[0]["html"] + e1[0]["subject"])
        check("Adani banner in the email", e1 and f"cid:{render.BANNER_CID}" in e1[0]["html"])
        check("Project snapshot PDF attached", e1 and any(a.endswith(".pdf") for a in e1[0]["att"]), e1 and e1[0]["att"])
        al = A.find_open(db, f"order:{DEMO}:{A.phase_id('Project Balance')}", False)
        check("Alert opened at L1", al is not None and al.level == 1)
        if d1 - d2 > 1:
            at(due - timedelta(days=d1 - 1)); mails.clear(); engine.run(db, "selftest", only=keys)
            check("The next day: nothing sent twice", not [x for x in mails if "DEMO" in x["subject"]], [x["subject"] for x in mails])
        at(due - timedelta(days=d2)); mails.clear(); engine.run(db, "selftest", only=keys)
        e2 = [x for x in mails if "DEMO" in x["subject"]]
        check(f"{d2} days, not acknowledged: escalates to L2",
              bool(e2) and set(e2[0]["to"]) == {"selftest.l1@adani.com", "selftest.l2@adani.com"},
              e2[0]["to"] if e2 else f"no email; sent: {[x['subject'] for x in mails] or 'nothing'}")
        check("L2 email says why and is tagged in the subject", e2 and "not acknowledged at level 1" in e2[0]["html"] and "[L2" in e2[0]["subject"])
        det = AR.acknowledge(al.id, AR.AckIn(note="PR raised", expected_date=due - timedelta(days=2)), req, db, orderer)
        check("A To recipient acknowledges with an expected date", det["acknowledged_by"] == "Self-test Orderer" and det["holds"])
        at(due - timedelta(days=d3)); mails.clear(); engine.run(db, "selftest", only=keys)
        e3 = [x for x in mails if "DEMO" in x["subject"]]
        check(f"{d3} days, acknowledged: held at L2 (L3 not told)", bool(e3) and "selftest.l3@adani.com" not in e3[0]["to"],
              e3[0]["to"] if e3 else "no email")
        at(due); mails.clear(); engine.run(db, "selftest", only=keys)
        e4 = [x for x in mails if "DEMO" in x["subject"]]
        check("Ordering date, expected date passed: escalates to L3", e4 and "selftest.l3@adani.com" in e4[0]["to"], e4 and e4[0]["to"])
        at(real_today())

        print("\n2. Approval request, approve, freeze")
        mails.clear()
        a = OA.request(db, orderer, m.id, month, 100.0, "Vendor slot confirmed")
        rq = [x for x in mails if "Approval Required" in x["subject"]]
        check("Request email to the TC Head role, requester on Cc", rq and "selftest.head@adani.com" in rq[0]["to"], rq and (rq[0]["to"], rq[0]["cc"]))
        check("Request email shows quantity, month, requester, note",
              rq and all(s in rq[0]["html"] for s in ("100.0", month, "Self-test Orderer", "Vendor slot confirmed")))
        check("Request email: Review and approve button", rq and "Review and approve in Akasha" in rq[0]["html"])
        check("Decision basis recorded", bool(a.basis) and "lta" in a.basis)
        try:
            OA.decide(db, orderer, a, "approve", None)
            check("The requester cannot approve their own request", False)
        except OA.ApprovalError:
            check("The requester cannot approve their own request", True)
        mails.clear()
        OA.decide(db, head, a, "approve", "Go ahead")
        dc = [x for x in mails if "Approval Approved" in x["subject"]]
        check("Approved email to TC Ordering and the requester", dc and "selftest.l1@adani.com" in dc[0]["to"], dc and dc[0]["to"])
        check("Approval alert closed", db.get(models.EmailAlert, a.alert_id).status == "resolved")
        check("100 MWp frozen in its month", engine.Data(db).projects[0]["month_frozen_mwp"].get(month) == 100.0)

        print("\n3. Approval returned")
        a2 = models.ModuleOrderApproval(mapping_id=m.id, project_id=DEMO, project_name=a.project_name, month=month, mwp=5,
                                        phases=[], ordered_at_request=0, status="pending", requested_by=TESTER,
                                        requested_by_name="Self-test Orderer", requested_by_email="selftest.l1@adani.com",
                                        requested_at=datetime.utcnow())
        db.add(a2); db.commit()
        try:
            OA.decide(db, head, a2, "return", "")
            check("Returning needs remarks", False)
        except OA.ApprovalError:
            check("Returning needs remarks", True)
        mails.clear(); OA.decide(db, head, a2, "return", "Wait for the revised SCOD")
        rt = [x for x in mails if "Approval Returned" in x["subject"]]
        check("Returned email carries the remarks", rt and "Wait for the revised SCOD" in rt[0]["html"])

        print("\n4. LTA edit in Akasha")
        engine.run(db, "selftest", only=["date_change"])          # first sighting: record only
        try:
            MR.update_mapping(m.id, MR.ProjectMappingUpdate(lta_date=m.lta_date + timedelta(days=20)), BackgroundTasks(), db, orderer)
            check("An LTA change without a reason is refused", False)
        except HTTPException as e:
            check("An LTA change without a reason is refused", e.status_code == 400)
        mails.clear()
        MR.update_mapping(m.id, MR.ProjectMappingUpdate(lta_date=m.lta_date + timedelta(days=20), remarks="CTUIL revised the date"),
                          BackgroundTasks(), db, orderer)
        engine.run(db, "edit by selftest", only=["date_change"])
        ch = [x for x in mails if "LTA date Revised" in x["subject"]]
        check("Schedule-change email sent", len(ch) == 1, [x["subject"] for x in mails])
        check("It names who changed it and the reason", ch and "Self-test Orderer" in ch[0]["html"] and "CTUIL revised the date" in ch[0]["html"])
        check("It states the impact", ch and "Impact" in ch[0]["html"])

        print("\n5. Change from a sync")
        mails.clear()
        old = m.lta_date
        date_history.record(db, m, "lta", old, old - timedelta(days=20), "portal", "sync")
        m.lta_date = old - timedelta(days=20); db.commit()
        engine.run(db, "tc sync", only=["date_change"])
        sy = [x for x in mails if "LTA date Revised" in x["subject"]]
        check("Emailed after the sync, from the portal", len(sy) == 1 and "Transmission portal sync" in sy[0]["html"])
        mails.clear(); engine.run(db, "tc sync", only=["date_change"])
        check("The same change is not emailed twice", not [x for x in mails if "LTA date Revised" in x["subject"]])

        print("\n6. The message itself")
        sender.send = sender_send
        sent = {}

        class NoSMTP:
            def __init__(self, *a, **k): pass
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def ehlo(self): pass
            def has_extn(self, x): return False
            def login(self, *a): pass
            def send_message(self, msg, **k): sent["msg"] = msg; return {}
        smtp = sender.smtplib.SMTP
        sender.smtplib.SMTP = NoSMTP
        try:
            sender.send(cfg, ["x@adani.com"], [], "Self-test", e1[0]["html"], "text")
        finally:
            sender.smtplib.SMTP = smtp
        parts = [q.get_content_type() for q in sent["msg"].walk()]
        check("The banner travels inside the message (inline image)", "image/jpeg" in parts and "multipart/related" in parts, parts)

        print("\n7. Project delay / AOP on the real projects (read only)")
        engine.Data = Data
        d = Data(db)
        for key in ("project_delay", "aop_due"):
            t = db.get(models.EmailTemplate, key)
            evs = engine.TRIGGERS[t.trigger](d, t, True)
            bad = [e for e in evs if "{{" in render.render(t, e.ctx)[1]]
            check(f"{t.name}: {len(evs)} project(s) qualify today, every email fills", not bad)
    finally:
        sender.send = sender_send
        engine.Data = Data
        C.today = real_today
        A.C.today = real_today
        AR.C.today = real_today
        db.rollback()
        db.query(models.AkashaUser).filter(models.AkashaUser.username.in_([TESTER, HEAD])).delete(synchronize_session=False)
        db.commit()
        demo.remove_created(db, MARK)
        db.close()

    if fails:
        print(f"\n{len(fails)} CHECK(S) FAILED:")
        for f in fails:
            print("  - " + f)
    else:
        print("\nALL CHECKS PASSED")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
