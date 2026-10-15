"""Demo project for testing the email workflow end to end (VM or local).

Three ways to get one:

  --from-p6 <id>    projects that are in P6 but not yet in Akasha - the Solar
                    "Demo DPR" ("Demo 25MW") and the "(Digital)" Digital DPR
                    copies (FY26-P06 (Digital), FY26-P07 (Digital), ...): adds
                    each one's project-mapping row (Akasha syncs only mapped
                    P6 projects) and syncs its P6 data. Repeatable; several
                    demos can be active at once. --remove deletes those
                    mapping rows again; the synced P6 rows stay, unused.
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
  python scripts/demo_email_project.py --from-p6 "Demo DPR" --from-p6 "FY26-P06 (Digital)" --recipient you@adani.com
  python scripts/demo_email_project.py --use "<project id or mapping id>" --recipient you@adani.com
  python scripts/demo_email_project.py --recipient you@adani.com            # create a new demo instead
  python scripts/demo_email_project.py --days 15     # move the ordering date (when dates are Akasha's, not P6's)
  python scripts/demo_email_project.py --status
  python scripts/demo_email_project.py --remove     # every demo, everything the testing caused

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


# ── Several demo projects at once ────────────────────────────────────────────
# State: {"since": iso, "demos": {ident: {"kind": "p6" | "use", "project_ids": [...],
#         "created": [mapping ids added here], "mappings": {mapping id: saved values}}}}

DEMO_WORDS = r"demo|test|dummy|sample|digital"


def _demos() -> dict:
    st = _state()
    if not st:
        return {}
    if "demos" not in st:                       # the one-demo format of earlier versions
        st = {"since": st["since"], "demos": {st["ident"]: {"kind": "p6" if st.get("created") else "use",
                                                            "project_ids": st.get("project_ids", []),
                                                            "created": st.get("created", []),
                                                            "mappings": st.get("mappings", {})}}}
        _save_state(st)
    return st["demos"]


def _put(ident: str, entry: dict) -> None:
    st = _state() or {"since": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(), "demos": {}}
    _demos()
    st = _state() or st
    st.setdefault("demos", {})[ident] = entry
    _save_state(st)


def _p6_projects():
    import logging
    import urllib3
    urllib3.disable_warnings()
    logging.getLogger("services.p6_service").setLevel(logging.ERROR)
    from services.p6_service import P6Service
    svc = P6Service()
    return svc, svc.fetch_projects()


def from_p6(db, ids: list, recipients: list, capacity_mwac=None, source: str = "ALMM") -> None:
    """Bring P6-only projects (the Solar "Demo DPR", the "(Digital)" demo
    copies...) into Akasha as demo projects, and sync them from P6."""
    import re
    svc, projects = _p6_projects()
    by_id = {x.get("Id"): x for x in projects}
    demos = _demos()
    for p6_id in ids:
        proj = by_id.get(p6_id)
        if not proj:
            hits = [x.get("Id") for x in projects if re.search(DEMO_WORDS, f"{x.get('Id')} {x.get('Name')}", re.I)]
            print(f"P6 has no project with Id '{p6_id}'. Demo projects in P6: {', '.join(hits) or 'none'}")
            continue
        rows = _rows(db, p6_id)
        if rows and p6_id not in demos:
            print(f"'{p6_id}' is already in Akasha - use it with --use \"{p6_id}\" instead.")
            continue
        name = proj.get("Name") or p6_id
        if not rows:
            cap = capacity_mwac
            if cap is None:
                m = re.search(r"(\d+(?:\.\d+)?)\s*MW", name, re.I)
                if not m:
                    print(f"Cannot read a capacity from the P6 name '{name}' - pass --capacity <MWac>.")
                    continue
                cap = float(m.group(1))
            # Named DEMO so it reads as one everywhere; a superadmin can delete it
            # in Admin > Project mappings as well as with --remove.
            m = models.ProjectMapping(project_id=p6_id, project=f"DEMO - {name} ({p6_id})", project_name_from_p6=name, spv_name="DEMO",
                                      category="Merchant", cluster=PORTFOLIO, subcluster=PORTFOLIO, capacity_mwac=cap,
                                      ol=str(OL), capacity_mwdc=round(cap * OL, 1), source_of_origin=source,
                                      is_commissioned=False, is_tracked=True)
            db.add(m)
            db.commit()
            rows = [m]
            _put(p6_id, {"kind": "p6", "project_ids": [p6_id], "created": [m.id], "mappings": {}})
            print(f"Added '{name}' ({p6_id}) to Akasha: {cap:g} MWac solar, portfolio '{PORTFOLIO}' (mapping #{m.id})")
        print(f"Syncing '{p6_id}' from P6 (ObjectId {proj.get('ObjectId')})...")
        r = svc.individual_sync(db, int(proj["ObjectId"]))
        print(f"  {r.get('activities_synced', 0)} activities, {r.get('wbs_synced', 0)} WBS nodes, {r.get('baselines_synced', 0)} baseline(s)")
        _report(db, rows[0].id)
    added = _add_recipients(db, recipients, MARK)
    db.commit()
    if added:
        print(f"Added {added} demo recipient rows (L1, every group, portfolio '{PORTFOLIO}' only)")


def find(db) -> None:
    import re
    rows = [m for m in db.query(models.ProjectMapping).order_by(models.ProjectMapping.id).all()
            if re.search(DEMO_WORDS + "|dpr", f"{m.project} {m.project_id} {m.project_name_from_p6}", re.I)]
    demos = _demos()
    print("In Akasha:" if rows else "No demo / test project in Akasha yet.")
    seen = set()
    for m in rows:
        dup = (m.project_id, m.project) in seen
        seen.add((m.project_id, m.project))
        wind = "wind" in f"{m.category} {m.mms_type}".lower()
        why = ("demo now" if m.project_id in demos else "Wind - not in the Ordering Schedule" if wind
               else "no capacity" if not m.capacity_mwac else "usable with --use")
        print(f"  {m.project_id or '-':30} mapping #{m.id:<5} {(m.project or '')[:55]:55} {why}" + ("  (duplicate row)" if dup else ""))
    try:
        _, projects = _p6_projects()
        mapped = {m.project_id for m in db.query(models.ProjectMapping.project_id)}
        only = [x for x in projects if re.search(DEMO_WORDS, f"{x.get('Id')} {x.get('Name')}", re.I) and x.get("Id") not in mapped]
        if only:
            print("\nIn P6, not yet in Akasha (bring in with --from-p6):")
            for x in only:
                print(f"  {x.get('Id'):30} {x.get('Name')}  (EPS {x.get('ParentEPSName') or '-'})")
    except Exception as e:  # noqa: BLE001 - P6 unreachable: list only what Akasha has
        print(f"\n(P6 not reachable to list P6-only projects: {e})")
    print('\nExamples:  --from-p6 "Demo DPR" --from-p6 "FY26-P06 (Digital)" --recipient you@adani.com')
    print('           --use "<project id>" --recipient you@adani.com')


def use(db, ident: str, days, recipients: list) -> None:
    """Take an existing solar project as a demo; its values are saved and put back by --remove."""
    rows = _rows(db, ident)
    if not rows:
        print(f"No project '{ident}' in Akasha. List candidates with --find.")
        return
    if any("wind" in f"{m.category} {m.mms_type}".lower() for m in rows):
        print(f"'{ident}' is a Wind project - the Ordering Schedule (ordering emails, approvals) is solar only.")
        return
    demos = _demos()
    if ident not in demos:
        _put(ident, {"kind": "use", "project_ids": sorted({m.project_id for m in rows if m.project_id}), "created": [],
                     "mappings": {str(m.id): {k: getattr(m, k) for k in SAVED} for m in rows}})
    for m in rows:
        m.cluster = m.subcluster = PORTFOLIO
        m.is_commissioned, m.is_tracked = False, True
    p = _summary_row(db, rows[0].id)
    p6_dates = bool(p and (p.get("module_date") or p.get("ftc_date")))
    if days is not None and not p6_dates:
        _, scod, lta = dates_for(days, rows[0].source_of_origin or SOURCE)
        for m in rows:
            m.manual_scod, m.lta_date, m.manual_scod_is_lta = scod, lta, False
        db.query(models.EmailWatch).filter(models.EmailWatch.project_id.in_([m.project_id for m in rows])).delete(synchronize_session=False)
    added = _add_recipients(db, recipients, MARK)
    db.commit()
    print(f"Using '{rows[0].project}' ({ident}) as a demo project - portfolio '{PORTFOLIO}'; --remove puts it back")
    if p6_dates:
        print("  Its ordering dates come from P6, so --days cannot move them; the dates below are the real plan.")
    elif days is not None:
        print(f"  SCOD / LTA set so the ordering date is {days} days from today")
    if added:
        print(f"  Added {added} demo recipient rows (L1, every group, portfolio '{PORTFOLIO}' only)")
    _report(db, rows[0].id)


# ── Status and removal ───────────────────────────────────────────────────────

def _all(db):
    """(project ids, mapping ids, since) across every demo, or the created one."""
    demos = _demos()
    if demos:
        pids = sorted({x for d in demos.values() for x in d["project_ids"]})
        mids = sorted({int(x) for d in demos.values() for x in list(d["mappings"]) + list(d["created"])})
        return pids, mids, datetime.fromisoformat(_state()["since"])
    m = mapping(db)
    return ([PROJECT_ID], [m.id] if m else [], None)


def status(db) -> None:
    pids, mids, since = _all(db)
    if not mids:
        print("No demo project. See --find; then --from-p6 / --use, or create one with --recipient you@adani.com")
        return
    demos = _demos()
    for mid in mids:
        m = db.get(models.ProjectMapping, mid)
        print(f"\n{m.project} ({m.project_id})" + ("" if demos else "  [created demo]"))
        _report(db, mid)
    print()
    for a in db.query(models.ModuleOrderApproval).filter(models.ModuleOrderApproval.mapping_id.in_(mids)).all():
        if not since or a.requested_at >= since:
            print(f"  approval #{a.id}: {a.project_name} - {a.status} {a.mwp} MWp in {a.month}")
    for a in db.query(models.EmailAlert).filter(models.EmailAlert.project_id.in_(pids)).all():
        if not since or a.opened_at >= since:
            print(f"  alert #{a.id}: {a.project_name} - {a.status} {a.template_key} L{a.level}, acknowledged by {a.acknowledged_by or '-'}")
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
    demos = _demos()
    if not demos:
        remove_created(db)
        return
    pids, mids, since = _all(db)
    n = cleanup(db, pids, mids, since, MARK)
    for ident, d in demos.items():
        for mid in d["created"]:
            m = db.get(models.ProjectMapping, int(mid))
            if m:
                db.delete(m)
        for mid, vals in d["mappings"].items():
            m = db.get(models.ProjectMapping, int(mid))
            if not m:
                continue
            for k, v in vals.items():
                if k in ("manual_scod", "lta_date") and v:
                    v = datetime.fromisoformat(v)
                setattr(m, k, v)
        print(("Removed the mapping row added for " if d["created"] else "Put back as it was: ") + ident)
    db.commit()
    os.remove(STATE)
    print(f"Removed {n[0]} alert(s), {n[1]} logged email(s) and {n[2]} demo recipient row(s) from the testing.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--find", action="store_true", help="list demo projects in Akasha and in P6")
    ap.add_argument("--from-p6", metavar="P6_ID", action="append", default=[],
                    help="add this P6 project to Akasha as a demo and sync it (repeatable)")
    ap.add_argument("--use", metavar="PROJECT", action="append", default=[],
                    help="use this existing project as a demo (P6 project id or mapping id; repeatable)")
    ap.add_argument("--capacity", type=float, help="MWac for --from-p6 when its P6 name has none")
    ap.add_argument("--recipient", action="append", default=[], help="email to receive the demos' emails (repeatable)")
    ap.add_argument("--days", type=int, help="ordering date this many days from today (only where dates are not from P6)")
    ap.add_argument("--status", action="store_true", help="show the demos' plans, approvals, alerts and emails")
    ap.add_argument("--remove", action="store_true", help="undo every demo and everything the testing caused")
    a = ap.parse_args()
    for e in a.recipient:
        if "@" not in e:
            ap.error(f"Not an email address: {e}")
    db = SessionLocal()
    try:
        if a.find:
            find(db)
        elif a.remove:
            remove(db)
        elif a.status:
            status(db)
        elif a.from_p6 or a.use:
            if a.from_p6:
                from_p6(db, a.from_p6, a.recipient, a.capacity)
            for ident in a.use:
                use(db, ident, a.days, a.recipient)
        elif _demos():
            for ident, d in _demos().items():           # re-run: move dates / add testers on the --use demos
                if d["kind"] == "use":
                    use(db, ident, a.days, a.recipient)
            if a.recipient and not any(d["kind"] == "use" for d in _demos().values()):
                n = _add_recipients(db, a.recipient, MARK)
                db.commit()
                print(f"Added {n} demo recipient rows")
            status(db)
        else:
            if not mapping(db) and not a.recipient:
                print("Note: no --recipient given - the demo's emails will have nobody to go to (except EMAIL_TEST_RECIPIENTS in test mode).")
            create(db, 30 if a.days is None else a.days, a.recipient)
    finally:
        db.close()


if __name__ == "__main__":
    main()
