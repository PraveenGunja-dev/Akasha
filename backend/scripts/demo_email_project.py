"""Demo project for testing the email workflow end to end (VM or local).

Creates one solar project in its own portfolio, "Akasha Demo", whose module
ordering date is a chosen number of days from today, so every email can be
exercised against it without touching a real project:

  - the 30 / 15 / 7-day ordering reminders (L1 / L2 / L3) and acknowledgement
  - Request approval from its month cell, Approve / Return, the freeze
  - editing its LTA / SCOD (asks for the reason; emails the change)

Recipients are added to every distribution group but limited to the demo
portfolio, so real projects never email them and they never see real alerts.
Nothing here is real data: the project is named DEMO, has no P6 or SAP
records, and --remove deletes everything it created or caused.

Usage (from backend/, with the venv):
  python scripts/demo_email_project.py --recipient you@adani.com
  python scripts/demo_email_project.py --recipient a@adani.com --recipient b@adani.com --days 30
  python scripts/demo_email_project.py --days 15        # move the ordering date (re-run any time)
  python scripts/demo_email_project.py --status
  python scripts/demo_email_project.py --remove

Then in Akasha: Admin > Email notifications - switch on the templates to test
(keep EMAIL_TEST_MODE=true in backend/.env until you are sure), and use
"Send now", or wait for the daily run.
"""
import argparse
import os
import sys
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

import models  # noqa: E402
from database import SessionLocal  # noqa: E402
from services.module_planner import LEAD_TIMES, TC_OFFSET_DAYS  # noqa: E402

PROJECT_ID = "DEMO-AKASHA-EMAIL"
NAME = "DEMO - Akasha Email Test"
PORTFOLIO = "Akasha Demo"
SOURCE = "DCR"                      # 98-day lead time
CAPACITY_MWAC = 100.0
OL = 1.35
MARK = "demo-script"                # created_by on the recipients it adds
GROUPS = ["tc_ordering", "tc_head", "projects", "pmag", "executive", "tc_stores", "finance", "admin"]


def today_ist() -> date:
    return (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).date()


def dates_for(days: int):
    """SCOD such that the planner's ordering date is `days` from today:
    ordering = SCOD - 45 days (install) - lead time (services/module_planner.py)."""
    order = today_ist() + timedelta(days=days)
    scod = order + timedelta(days=TC_OFFSET_DAYS + LEAD_TIMES[SOURCE])
    lta = scod + timedelta(days=60)
    return order, datetime(scod.year, scod.month, scod.day), datetime(lta.year, lta.month, lta.day)


def mapping(db):
    return db.query(models.ProjectMapping).filter(models.ProjectMapping.project_id == PROJECT_ID).first()


def create(db, days: int, recipients: list) -> None:
    order, scod, lta = dates_for(days)
    m = mapping(db)
    fresh = m is None
    if fresh:
        m = models.ProjectMapping(project_id=PROJECT_ID)
        db.add(m)
    m.project, m.project_name_from_p6, m.spv_name, m.plot_no = NAME, NAME, "DEMO SPV", "DEMO-1"
    m.category, m.mms_type, m.cluster, m.subcluster = "Merchant", "Fixed Tilt", PORTFOLIO, PORTFOLIO
    m.capacity_mwac, m.ol, m.capacity_mwdc = CAPACITY_MWAC, str(OL), round(CAPACITY_MWAC * OL, 1)
    m.source_of_origin, m.is_commissioned, m.is_tracked = SOURCE, False, True
    m.manual_scod, m.lta_date, m.manual_scod_is_lta = scod, lta, False
    db.flush()
    if not fresh:
        # The date watches would treat a re-dated demo as a schedule change -
        # forget them so moving the demo does not email "date changed".
        db.query(models.EmailWatch).filter(models.EmailWatch.project_id == PROJECT_ID).delete()

    have = {(r.group_key, r.email.lower()) for r in db.query(models.EmailRecipient).all()}
    added = 0
    for email in recipients:
        for g in GROUPS:
            if (g, email.lower()) in have:
                continue
            db.add(models.EmailRecipient(group_key=g, name=f"Demo tester ({email.split('@')[0]})", email=email,
                                         portfolios=[PORTFOLIO], level=1, active=True, created_by=MARK))
            added += 1
    db.commit()
    print(f"{'Created' if fresh else 'Updated'} {NAME} (mapping #{m.id}, portfolio '{PORTFOLIO}')")
    print(f"  {CAPACITY_MWAC:.0f} MWac x OL {OL} = {CAPACITY_MWAC * OL:.1f} MWp to order, nothing ordered (no SAP POs)")
    print(f"  Ordering date {order:%d-%b-%y} ({days} days from today) - SCOD {scod:%d-%b-%y}, LTA {lta:%d-%b-%y}")
    if added:
        print(f"  Added {added} demo recipient rows (L1, every group, portfolio '{PORTFOLIO}' only)")
    verify(db, days)


def verify(db, days: int) -> None:
    """Read the demo back from the Ordering Schedule exactly as the emails will."""
    from routers.module_deliveries import get_module_deliveries_summary
    s = get_module_deliveries_summary(scenario="baseline", priorities=None, portfolio=PORTFOLIO, phase="all", db=db)
    p = next((x for x in s.get("projects") or [] if x.get("project_name") == NAME), None)
    if not p:
        print("  ! The demo is not in the Ordering Schedule - check the mapping")
        return
    cells = {m: v for m, v in (p.get("month_mwp") or {}).items() if v}
    first = next((ph for rows in (p.get("month_phases") or {}).values() for ph in rows), None)
    print(f"  Ordering Schedule: balance {p.get('balance_ordering_mwp')} MWp in {cells}")
    if first:
        print(f"  Phase '{first['phase_label']}': order by {first['order_date']}, at site {first['tc_date']}, FTC {first['ftc_date']}")
    stage = "L1 (30-day)" if 16 <= days <= 30 else "L2 (15-day)" if 8 <= days <= 15 else "L3 (7-day)" if 1 <= days <= 7 \
        else "ordering date - due today" if days == 0 else "overdue" if days < 0 else "none yet (more than 30 days away)"
    print(f"  With the default reminder days, the next run sends: {stage}")


def status(db) -> None:
    m = mapping(db)
    if not m:
        print("No demo project. Create it with --recipient you@adani.com")
        return
    print(f"{NAME}: mapping #{m.id}, SCOD {m.manual_scod:%d-%b-%y}, LTA {m.lta_date:%d-%b-%y}")
    for a in db.query(models.ModuleOrderApproval).filter(models.ModuleOrderApproval.mapping_id == m.id).all():
        print(f"  approval #{a.id}: {a.status} {a.mwp} MWp in {a.month}")
    for a in db.query(models.EmailAlert).filter(models.EmailAlert.project_id == PROJECT_ID).all():
        print(f"  alert #{a.id}: {a.status} {a.template_key} L{a.level} ack={a.acknowledged_by or '-'}")
    n = db.query(models.EmailLog).filter(models.EmailLog.project_id == PROJECT_ID).count()
    print(f"  {n} email(s) logged; recipients: "
          f"{', '.join(sorted({r.email for r in db.query(models.EmailRecipient).filter(models.EmailRecipient.created_by == MARK).all()})) or 'none'}")


def remove(db) -> None:
    m = mapping(db)
    ids = [a.id for a in db.query(models.EmailAlert).filter(models.EmailAlert.project_id == PROJECT_ID).all()]
    if m:
        appr = [a.id for a in db.query(models.ModuleOrderApproval).filter(models.ModuleOrderApproval.mapping_id == m.id).all()]
        ids += [a.alert_id for a in db.query(models.ModuleOrderApproval).filter(models.ModuleOrderApproval.id.in_(appr or [0])).all() if a.alert_id]
        db.query(models.ModuleOrderApprovalEvent).filter(models.ModuleOrderApprovalEvent.approval_id.in_(appr or [0])).delete(synchronize_session=False)
        db.query(models.ModuleOrderApproval).filter(models.ModuleOrderApproval.mapping_id == m.id).delete(synchronize_session=False)
        db.query(models.ProjectDateChange).filter(models.ProjectDateChange.mapping_id == m.id).delete(synchronize_session=False)
    ids = list(set(ids))
    if ids:
        db.query(models.EmailAlertEvent).filter(models.EmailAlertEvent.alert_id.in_(ids)).delete(synchronize_session=False)
        db.query(models.EmailAlertRecipient).filter(models.EmailAlertRecipient.alert_id.in_(ids)).delete(synchronize_session=False)
        db.query(models.EmailAlert).filter(models.EmailAlert.id.in_(ids)).delete(synchronize_session=False)
    logs = db.query(models.EmailLog).filter(models.EmailLog.project_id == PROJECT_ID).delete(synchronize_session=False)
    db.query(models.EmailWatch).filter(models.EmailWatch.project_id == PROJECT_ID).delete(synchronize_session=False)
    recips = db.query(models.EmailRecipient).filter(models.EmailRecipient.created_by == MARK).delete(synchronize_session=False)
    if m:
        db.delete(m)
    db.commit()
    print(f"Removed the demo project, {len(ids)} alert(s), {logs} logged email(s) and {recips} demo recipient row(s).")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--recipient", action="append", default=[], help="email to receive the demo's emails (repeatable)")
    ap.add_argument("--days", type=int, default=30, help="ordering date this many days from today (default 30)")
    ap.add_argument("--status", action="store_true", help="show the demo's approvals, alerts and emails")
    ap.add_argument("--remove", action="store_true", help="delete the demo and everything it caused")
    a = ap.parse_args()
    db = SessionLocal()
    try:
        if a.remove:
            remove(db)
        elif a.status:
            status(db)
        else:
            for e in a.recipient:
                if "@" not in e:
                    ap.error(f"Not an email address: {e}")
            if not mapping(db) and not a.recipient:
                print("Note: no --recipient given - the demo's emails will have nobody to go to (except EMAIL_TEST_RECIPIENTS in test mode).")
            create(db, a.days, a.recipient)
    finally:
        db.close()


if __name__ == "__main__":
    main()
