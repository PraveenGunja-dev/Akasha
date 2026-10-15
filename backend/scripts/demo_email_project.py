"""Demo project for testing the email workflow end to end (VM or local).

Two ways to get one:

  --use <project>   take a project that already exists (e.g. the Solar demo
                    project). Its current portfolio, dates and flags are saved
                    first; it is then moved into its own portfolio,
                    "Akasha Demo", so only the testers you add hear about it.
                    --remove puts every saved value back.
  (no --use)        create a new throw-away project, "DEMO - Akasha Email
                    Test", with no P6 or SAP records.

Either way the testers are added to every distribution group for the demo
portfolio only - nobody set to "all portfolios" ever receives demo emails
(services/email_notify/engine.DEMO_PORTFOLIO) - and --remove deletes what the
testing caused (alerts, logged emails, approvals, date changes) since the demo
was set up, nothing older.

What it lets you test: the L1 / L2 / L3 ordering reminders and acknowledging,
Request approval -> Approve / Return -> the freeze, editing LTA / SCOD (asks
for the reason, emails the change).

Usage (from backend/, with the venv):
  python scripts/demo_email_project.py --find
  python scripts/demo_email_project.py --use "<project id or mapping id>" --recipient you@adani.com
  python scripts/demo_email_project.py --recipient you@adani.com            # create a new demo instead
  python scripts/demo_email_project.py --days 15     # move the ordering date (when dates are Akasha's, not P6's)
  python scripts/demo_email_project.py --status
  python scripts/demo_email_project.py --remove

Then: Admin > Email notifications - keep EMAIL_TEST_MODE=true in backend/.env,
switch on the templates to test, "Preview next run", "Send now".
"""
import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)
from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(BACKEND, ".env"))

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
STATE = os.path.join(BACKEND, "scripts", ".demo_email_state.json")   # what --use changed, to put back
SAVED = ("cluster", "subcluster", "manual_scod", "lta_date", "manual_scod_is_lta", "is_commissioned", "is_tracked")


def today_ist() -> date:
    return (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).date()


def dates_for(days: int, source: str = SOURCE):
    """SCOD such that the planner's ordering date is `days` from today:
    ordering = SCOD - 45 days (install) - lead time (services/module_planner.py)."""
    order = today_ist() + timedelta(days=days)
    scod = order + timedelta(days=TC_OFFSET_DAYS + LEAD_TIMES.get(source, 98))
    lta = scod + timedelta(days=60)
    return order, datetime(scod.year, scod.month, scod.day), datetime(lta.year, lta.month, lta.day)


def _state():
    try:
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _save_state(st):
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(st, f, indent=2, default=str)


def mapping(db):
    """The created demo project (not a --use one)."""
    return db.query(models.ProjectMapping).filter(models.ProjectMapping.project_id == PROJECT_ID).first()


def _rows(db, ident: str):
    q = db.query(models.ProjectMapping)
    rows = q.filter(models.ProjectMapping.project_id == ident).all()
    if not rows and ident.isdigit():
        rows = q.filter(models.ProjectMapping.id == int(ident)).all()
    return rows


def _summary_row(db, mapping_id: int):
    from routers.module_deliveries import get_module_deliveries_summary
    s = get_module_deliveries_summary(scenario="baseline", priorities=None, portfolio=None, phase="all", db=db)
    return next((x for x in s.get("projects") or [] if x.get("id") == mapping_id), None)


def _add_recipients(db, recipients, mark, portfolio=PORTFOLIO):
    have = {(r.group_key, r.email.lower()) for r in db.query(models.EmailRecipient).all()}
    added = 0
    for email in recipients:
        for g in GROUPS:
            if (g, email.lower()) in have:
                continue
            db.add(models.EmailRecipient(group_key=g, name=f"Demo tester ({email.split('@')[0]})", email=email,
                                         portfolios=[portfolio], level=1, active=True, created_by=mark))
            added += 1
    return added


def _report(db, mapping_id: int):
    """Read the demo back from the Ordering Schedule exactly as the emails will."""
    p = _summary_row(db, mapping_id)
    if not p:
        print("  ! Not in the Ordering Schedule - only solar projects with a capacity are (Wind is not)")
        return
    cells = {m: v for m, v in (p.get("month_mwp") or {}).items() if v}
    phases = [ph for rows in (p.get("month_phases") or {}).values() for ph in rows]
    print(f"  Ordering Schedule: balance {p.get('balance_ordering_mwp')} MWp, planned {cells or 'nothing'}")
    if not phases:
        print("  ! No order is planned (nothing left to order, or no dates) - ordering emails will not fire")
        return
    first = min(phases, key=lambda x: datetime.strptime(x["order_date"], "%d-%b-%y"))
    od = datetime.strptime(first["order_date"], "%d-%b-%y").date()
    days = (od - today_ist()).days
    print(f"  Next order: '{first['phase_label']}' {first['mwp']} MWp, order by {first['order_date']} ({days} days), "
          f"at site {first['tc_date']}, FTC {first['ftc_date']}")
    t = db.get(models.EmailTemplate, "ordering_due_30")
    from services.email_notify import alerts
    st = sorted(alerts.due_stages(t), key=lambda x: x[1]) if t else [(1, 30), (2, 15), (3, 7)]
    hit = [lv for lv, n in st if n >= days >= 1]
    msg = (f"L{hit[0]} reminder" if hit else "the due-today email" if days == 0 else "the overdue email" if days < 0
           else f"nothing yet (first reminder at {max(n for _, n in st)} days)")
    print(f"  The next run sends: {msg}  (reminders at " + ", ".join(f"L{lv} {n} d" for lv, n in sorted(st)) + ")")


# ── Create a new demo project ────────────────────────────────────────────────

def create(db, days: int, recipients: list, mark: str = MARK, portfolio: str = PORTFOLIO) -> None:
    order, scod, lta = dates_for(days)
    m = mapping(db)
    fresh = m is None
    if fresh:
        m = models.ProjectMapping(project_id=PROJECT_ID)
        db.add(m)
    m.project, m.project_name_from_p6, m.spv_name, m.plot_no = NAME, NAME, "DEMO SPV", "DEMO-1"
    m.category, m.mms_type, m.cluster, m.subcluster = "Merchant", "Fixed Tilt", portfolio, portfolio
    m.capacity_mwac, m.ol, m.capacity_mwdc = CAPACITY_MWAC, str(OL), round(CAPACITY_MWAC * OL, 1)
    m.source_of_origin, m.is_commissioned, m.is_tracked = SOURCE, False, True
    m.manual_scod, m.lta_date, m.manual_scod_is_lta = scod, lta, False
    db.flush()
    if not fresh:
        # Moving the demo must not read as a schedule change.
        db.query(models.EmailWatch).filter(models.EmailWatch.project_id == PROJECT_ID).delete()
    added = _add_recipients(db, recipients, mark, portfolio)
    db.commit()
    print(f"{'Created' if fresh else 'Updated'} {NAME} (mapping #{m.id}, portfolio '{portfolio}')")
    print(f"  {CAPACITY_MWAC:.0f} MWac x OL {OL} = {CAPACITY_MWAC * OL:.1f} MWp to order, nothing ordered (no SAP POs)")
    print(f"  Ordering date {order:%d-%b-%y} ({days} days from today) - SCOD {scod:%d-%b-%y}, LTA {lta:%d-%b-%y}")
    if added:
        print(f"  Added {added} demo recipient rows (L1, every group, portfolio '{portfolio}' only)")
    _report(db, m.id)


# ── Use an existing project ──────────────────────────────────────────────────

def find(db) -> None:
    from sqlalchemy import or_
    rows = (db.query(models.ProjectMapping)
            .filter(or_(*[getattr(models.ProjectMapping, c).ilike(f"%{w}%") for c in ("project", "project_id", "project_name_from_p6")
                          for w in ("demo", "test", "dummy", "sample", "dpr")])).order_by(models.ProjectMapping.id).all())
    if not rows:
        print("No project with demo / test / dummy / sample / dpr in its name.")
        return
    seen = set()
    for m in rows:
        key = (m.project_id, m.project)
        dup = key in seen
        seen.add(key)
        wind = "wind" in f"{m.category} {m.mms_type}".lower()
        why = ("Wind - not in the Ordering Schedule" if wind else "no capacity" if not m.capacity_mwac
               else "commissioned (will be set ongoing)" if m.is_commissioned else "usable")
        print(f"  {m.project_id or '-':20} mapping #{m.id:<5} {m.project[:60]:60} {m.cluster or '-':16} {why}"
              + ("  (duplicate row)" if dup else ""))
    print("\nUse one with:  python scripts/demo_email_project.py --use \"<project id>\" --recipient you@adani.com")


def use(db, ident: str, days, recipients: list) -> None:
    st = _state()
    if st and st.get("ident") != ident:
        print(f"Already using '{st.get('ident')}' as the demo - run --remove first.")
        return
    rows = _rows(db, ident)
    if not rows:
        print(f"No project '{ident}'. List candidates with --find.")
        return
    if any("wind" in f"{m.category} {m.mms_type}".lower() for m in rows):
        print("That is a Wind project - the Ordering Schedule (and so ordering emails and approvals) is solar only.")
        return
    if not st:
        st = {"ident": ident, "since": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(), "project_ids": sorted({m.project_id for m in rows if m.project_id}),
              "mappings": {str(m.id): {k: getattr(m, k) for k in SAVED} for m in rows}}
        _save_state(st)
    for m in rows:
        m.cluster = m.subcluster = PORTFOLIO
        m.is_commissioned, m.is_tracked = False, True
    p = _summary_row(db, rows[0].id) if rows else None
    from_p6 = bool(p and (p.get("module_date") or p.get("ftc_date")))
    if days is not None and not from_p6:
        _, scod, lta = dates_for(days, rows[0].source_of_origin or SOURCE)
        for m in rows:
            m.manual_scod, m.lta_date, m.manual_scod_is_lta = scod, lta, False
        for pid in st["project_ids"]:
            db.query(models.EmailWatch).filter(models.EmailWatch.project_id == pid).delete()
    added = _add_recipients(db, recipients, MARK)
    db.commit()
    print(f"Using '{rows[0].project}' ({ident}, mapping #{', #'.join(str(m.id) for m in rows)}) as the demo project")
    print(f"  Moved into portfolio '{PORTFOLIO}' - only the demo testers receive its emails; --remove puts it back")
    if from_p6:
        print("  Its ordering dates come from P6, so --days cannot move them; the dates below are the real plan.")
    elif days is not None:
        print(f"  SCOD / LTA set so the ordering date is {days} days from today")
    if added:
        print(f"  Added {added} demo recipient rows (L1, every group, portfolio '{PORTFOLIO}' only)")
    _report(db, rows[0].id)


# ── Status and removal ───────────────────────────────────────────────────────

def _project_ids(db):
    st = _state()
    if st:
        return st["project_ids"], [int(k) for k in st["mappings"]], datetime.fromisoformat(st["since"])
    m = mapping(db)
    return ([PROJECT_ID], [m.id] if m else [], None)


def status(db) -> None:
    pids, mids, since = _project_ids(db)
    st = _state()
    if not mids:
        print("No demo project. Use one with --use, or create one with --recipient you@adani.com")
        return
    print(f"Demo: {'existing project ' + st['ident'] if st else NAME}  (mappings #{', #'.join(map(str, mids))})")
    _report(db, mids[0])
    for a in db.query(models.ModuleOrderApproval).filter(models.ModuleOrderApproval.mapping_id.in_(mids)).all():
        if not since or a.requested_at >= since:
            print(f"  approval #{a.id}: {a.status} {a.mwp} MWp in {a.month}")
    for a in db.query(models.EmailAlert).filter(models.EmailAlert.project_id.in_(pids)).all():
        if not since or a.opened_at >= since:
            print(f"  alert #{a.id}: {a.status} {a.template_key} L{a.level} acknowledged by {a.acknowledged_by or '-'}")
    q = db.query(models.EmailLog).filter(models.EmailLog.project_id.in_(pids))
    if since:
        q = q.filter(models.EmailLog.created_at >= since)
    print(f"  {q.count()} email(s) logged; testers: "
          f"{', '.join(sorted({r.email for r in db.query(models.EmailRecipient).filter(models.EmailRecipient.created_by == MARK)})) or 'none'}")


def cleanup(db, pids, mids, since, mark) -> tuple:
    """Delete what testing caused for these projects (since `since`, if
    given) and the testers added under `mark`. Returns (alerts, emails, testers)."""
    def recent(q, col):
        return q.filter(col >= since) if since else q
    appr = recent(db.query(models.ModuleOrderApproval).filter(models.ModuleOrderApproval.mapping_id.in_(mids or [0])),
                  models.ModuleOrderApproval.requested_at).all()
    alert_ids = {a.alert_id for a in appr if a.alert_id}
    alert_ids |= {a.id for a in recent(db.query(models.EmailAlert).filter(models.EmailAlert.project_id.in_(pids or [""])),
                                       models.EmailAlert.opened_at).all()}
    ids = [a.id for a in appr]
    db.query(models.ModuleOrderApprovalEvent).filter(models.ModuleOrderApprovalEvent.approval_id.in_(ids or [0])).delete(synchronize_session=False)
    db.query(models.ModuleOrderApproval).filter(models.ModuleOrderApproval.id.in_(ids or [0])).delete(synchronize_session=False)
    recent(db.query(models.ProjectDateChange).filter(models.ProjectDateChange.mapping_id.in_(mids or [0])),
           models.ProjectDateChange.changed_at).delete(synchronize_session=False)
    if alert_ids:
        db.query(models.EmailAlertEvent).filter(models.EmailAlertEvent.alert_id.in_(alert_ids)).delete(synchronize_session=False)
        db.query(models.EmailAlertRecipient).filter(models.EmailAlertRecipient.alert_id.in_(alert_ids)).delete(synchronize_session=False)
        db.query(models.EmailAlert).filter(models.EmailAlert.id.in_(alert_ids)).delete(synchronize_session=False)
    logs = recent(db.query(models.EmailLog).filter(models.EmailLog.project_id.in_(pids or [""])),
                  models.EmailLog.created_at).delete(synchronize_session=False)
    db.query(models.EmailWatch).filter(models.EmailWatch.project_id.in_(pids or [""])).delete(synchronize_session=False)
    testers = db.query(models.EmailRecipient).filter(models.EmailRecipient.created_by == mark).delete(synchronize_session=False)
    return len(alert_ids), logs, testers


def remove_created(db, mark: str = MARK) -> None:
    """Remove the created demo project and everything it caused."""
    m = mapping(db)
    n = cleanup(db, [PROJECT_ID], [m.id] if m else [], None, mark)
    if m:
        db.delete(m)
    db.commit()
    print(f"Removed the demo project, {n[0]} alert(s), {n[1]} logged email(s) and {n[2]} demo recipient row(s).")


def remove(db) -> None:
    st = _state()
    if not st:
        remove_created(db)
        return
    pids, mids, since = _project_ids(db)
    n = cleanup(db, pids, mids, since, MARK)
    for mid, vals in st["mappings"].items():
        m = db.get(models.ProjectMapping, int(mid))
        if not m:
            continue
        for k, v in vals.items():
            if k in ("manual_scod", "lta_date") and v:
                v = datetime.fromisoformat(v)
            setattr(m, k, v)
    db.commit()
    os.remove(STATE)
    print(f"Put '{st['ident']}' back as it was; removed {n[0]} alert(s), {n[1]} logged email(s) and {n[2]} demo recipient "
          f"row(s) from the testing.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--find", action="store_true", help="list demo / test projects that can be used")
    ap.add_argument("--use", metavar="PROJECT", help="use this existing project (P6 project id or mapping id)")
    ap.add_argument("--recipient", action="append", default=[], help="email to receive the demo's emails (repeatable)")
    ap.add_argument("--days", type=int, help="ordering date this many days from today (only when dates are not from P6)")
    ap.add_argument("--status", action="store_true", help="show the demo's approvals, alerts and emails")
    ap.add_argument("--remove", action="store_true", help="undo the demo and everything the testing caused")
    a = ap.parse_args()
    for e in a.recipient:
        if "@" not in e:
            ap.error(f"Not an email address: {e}")
    db = SessionLocal()
    try:
        st = _state()
        if a.find:
            find(db)
        elif a.remove:
            remove(db)
        elif a.status:
            status(db)
        elif a.use or st:
            use(db, a.use or st["ident"], a.days, a.recipient)
        else:
            if not mapping(db) and not a.recipient:
                print("Note: no --recipient given - the demo's emails will have nobody to go to (except EMAIL_TEST_RECIPIENTS in test mode).")
            create(db, 30 if a.days is None else a.days, a.recipient)
    finally:
        db.close()


if __name__ == "__main__":
    main()
