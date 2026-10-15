"""The email engine: finds what has happened, decides who should hear about
it, and sends each alert exactly once.

    run()          the scheduled pass - every enabled template's trigger
    preview()      one template rendered for a real project (admin screen)
    send_test()    one template to the administrator's own address
    send_manual()  one template for a chosen project to its groups
    resend()       a logged email again

Rules that keep it trustworthy:
  - Nothing goes out unless EMAIL_ENABLED is true; with EMAIL_TEST_MODE on,
    everything goes only to EMAIL_TEST_RECIPIENTS, marked [TEST].
  - Only addresses in EMAIL_ALLOWED_DOMAINS leave Akasha.
  - Each alert has an event key (template + project + phase + the date it is
    about). It is sent once; if the date moves, the key changes and the
    reminder is due again. A failure is retried on the next run (3 tries).
  - Watched values (dates, POs) are only RECORDED the first time they are
    seen - no mail about a value Akasha has just met.
  - Every email is logged with its rendered text, recipients and outcome.
"""
import html as html_mod
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

import models
from . import catalogue, context as C, render, sender, snapshot
from .config import settings

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 3


# ── Templates ────────────────────────────────────────────────────────────────

def seed_templates(db: Session) -> int:
    """Add catalogue templates that are not in the database yet. Never
    overwrites an administrator's edits. Returns how many were added."""
    have = {k for (k,) in db.query(models.EmailTemplate.key).all()}
    added = 0
    for t in catalogue.TEMPLATES:
        if t["key"] in have:
            continue
        row = models.EmailTemplate(**t, enabled=False, version=1, updated_by="system", updated_at=datetime.utcnow())
        db.add(row)
        db.add(version_row(row, "system", "Initial template"))
        added += 1
    if added:
        db.commit()
    return added


def version_row(t, who: str, note: str = "") -> "models.EmailTemplateVersion":
    return models.EmailTemplateVersion(
        template_key=t.key, version=t.version, name=t.name, subject=t.subject, body=t.body,
        to_groups=list(t.to_groups or []), cc_groups=list(t.cc_groups or []), config=dict(t.config or {}),
        attach_snapshot=bool(t.attach_snapshot), enabled=bool(t.enabled), note=note or None,
        changed_by=who, changed_at=datetime.utcnow())


# ── Recipients ───────────────────────────────────────────────────────────────

def members(db: Session, groups: List[str], portfolio: Optional[str] = None) -> List[str]:
    """Active addresses of the groups, limited to people who cover the
    project's portfolio (a member with no portfolios covers every one)."""
    if not groups:
        return []
    out = []
    for r in (db.query(models.EmailRecipient)
              .filter(models.EmailRecipient.group_key.in_(groups), models.EmailRecipient.active.is_(True)).all()):
        ports = [x.lower() for x in (r.portfolios or [])]
        if portfolio and ports and portfolio.lower() not in ports:
            continue
        out.append(r.email)
    return out


# ── Data ─────────────────────────────────────────────────────────────────────

class Data:
    """The Ordering Schedule as the alerts read it, loaded once per run."""

    def __init__(self, db: Session):
        from routers.module_deliveries import get_module_deliveries_summary
        self.db = db
        self.cfg = settings()
        summary = get_module_deliveries_summary(scenario="baseline", priorities=None, portfolio=None,
                                                phase="ongoing", db=db)
        pid_of = {mid: pid for mid, pid in db.execute(
            text("select id, project_id from project_mapping where project_id is not null"))}
        self.projects = [{**p, "project_id": pid_of.get(p["id"])} for p in summary.get("projects") or []]
        self.projects = [p for p in self.projects if p.get("project_id")]
        self.dates = C.data_dates(db)
        self._plans: Optional[Dict[str, dict]] = None

    def plans(self) -> Dict[str, dict]:
        """Advanced-planning block stages per project (P6) - built only when
        an email needs construction progress or the snapshot (~10 s)."""
        if self._plans is None:
            self._plans = {}
            try:
                from services import advanced_planning
                built = advanced_planning.build(self.db, self.projects)
                for pl in built.get("projects") or []:
                    for pid in [pl.get("project_id")] + list(pl.get("ids") or []):
                        if pid:
                            self._plans[str(pid)] = pl
            except Exception as e:  # noqa: BLE001 - progress is optional
                logger.warning(f"Email: construction progress unavailable ({e})")
        return self._plans

    def project(self, project_id: str) -> Optional[dict]:
        return next((p for p in self.projects if str(p.get("project_id")) == str(project_id)), None)

    def context(self, p: dict, with_progress: bool = False) -> Dict:
        plan = self.plans().get(str(p.get("project_id"))) if with_progress else None
        return C.project_context(p, self.cfg, plan, self.dates)


@dataclass
class Event:
    key: str
    ctx: Dict
    project: Optional[dict] = None
    phase: str = ""
    add_to: List[str] = field(default_factory=list)
    add_cc: List[str] = field(default_factory=list)
    to_override: Optional[List[str]] = None       # digest: one recipient
    orders: List[dict] = field(default_factory=list)
    watch: Optional[tuple] = None                 # (project_id, field, value) to record after sending


# ── Watched values ───────────────────────────────────────────────────────────

def _watch_get(db, pid, fld):
    w = db.get(models.EmailWatch, (str(pid), fld))
    return (True, w.value) if w else (False, None)


def _watch_set(db, pid, fld, value):
    w = db.get(models.EmailWatch, (str(pid), fld))
    if w:
        w.value, w.updated_at = value, datetime.utcnow()
    else:
        db.add(models.EmailWatch(project_id=str(pid), field=fld, value=value, updated_at=datetime.utcnow()))


# ── Triggers ─────────────────────────────────────────────────────────────────

def _orders(p):
    return [o for o in C.phases(p) if (o.get("mwp") or 0) > 0]


def _phase_key(o):
    return f"{o.get('phase_label') or 'main'}:{o.get('order_date') or ''}"


def ev_ordering_due(d: Data, t, dry: bool) -> List[Event]:
    before = int((t.config or {}).get("days_before", 30))
    until = int((t.config or {}).get("days_until", 1))
    today, out = C.today(), []
    for p in d.projects:
        if (p.get("balance_ordering_mwp") or 0) <= 0:
            continue
        orders = _orders(p)
        for o in orders:
            od = C.parse_day(o.get("order_date"))
            if not od or o.get("overdue"):
                continue
            days = (od - today).days
            if until <= days <= before:
                ctx = C.phase_context(d.context(p, t.attach_snapshot or "construction_progress" in t.body), p, o)
                out.append(Event(f"{t.key}:{p['project_id']}:{_phase_key(o)}", ctx, p, ctx["phase"], orders=orders))
    return out


def ev_ordering_today(d: Data, t, dry: bool) -> List[Event]:
    today, out = C.today(), []
    for p in d.projects:
        if (p.get("balance_ordering_mwp") or 0) <= 0:
            continue
        for o in _orders(p):
            if C.parse_day(o.get("order_date")) == today:
                ctx = C.phase_context(d.context(p), p, o)
                out.append(Event(f"{t.key}:{p['project_id']}:{_phase_key(o)}", ctx, p, ctx["phase"]))
    return out


def ev_ordering_overdue(d: Data, t, dry: bool) -> List[Event]:
    levels = sorted((t.config or {}).get("escalation") or catalogue.LEVELS, key=lambda x: x.get("after_days", 0))
    today, out = C.today(), []
    for p in d.projects:
        if (p.get("balance_ordering_mwp") or 0) <= 0:
            continue
        orders = _orders(p)
        for o in orders:
            od = C.parse_day(o.get("order_date"))
            if not o.get("overdue") or not od:
                continue
            days = (today - od).days
            reached = [lv for lv in levels if days >= int(lv.get("after_days", 0))]
            if not reached:
                continue
            idx = len(reached)
            add_to = [g for lv in reached for g in lv.get("add_to") or []]
            add_cc = [g for lv in reached for g in lv.get("add_cc") or []]
            ctx = C.phase_context(d.context(p, t.attach_snapshot), p, o)
            ctx["escalation_level"] = reached[-1].get("label") or f"Level {idx}"
            out.append(Event(f"{t.key}:{p['project_id']}:{_phase_key(o)}:L{idx}", ctx, p, ctx["phase"],
                             add_to, add_cc, orders=orders))
    return out


FIELD_LABEL = {"ftc_date": "FTC date", "lta": "LTA date", "scod": "SCOD", "aop_plan": "AOP date",
               "module_date": "Module ordering date"}


def ev_date_change(d: Data, t, dry: bool) -> List[Event]:
    fields = (t.config or {}).get("fields") or list(FIELD_LABEL)
    out = []
    for p in d.projects:
        pid = p["project_id"]
        for f in fields:
            now_v = str(p.get(f) or "").strip()
            known, before = _watch_get(d.db, pid, f"date:{f}")
            if not known:
                if not dry:
                    _watch_set(d.db, pid, f"date:{f}", now_v)     # first sighting: record only
                continue
            if (before or "") == now_v:
                continue
            b, a = C.parse_day(before), C.parse_day(now_v)
            ctx = d.context(p)
            ctx.update({"changed_date_field": FIELD_LABEL.get(f, f), "previous_date": before or "Not set",
                        "revised_date": now_v or "Removed",
                        "date_variance_days": (f"{(a - b).days:+d}" if a and b else "")})
            out.append(Event(f"{t.key}:{pid}:{f}:{now_v}", ctx, p, watch=(pid, f"date:{f}", now_v)))
    return out


def ev_ftc_unreachable(d: Data, t, dry: bool) -> List[Event]:
    out = []
    for p in d.projects:
        for o in _orders(p):
            # An overdue order already gets the overdue alert, which states the
            # FTC shortfall - one problem, one email.
            if o.get("ftc_reachable", True) or o.get("overdue"):
                continue
            ctx = C.phase_context(d.context(p), p, o)
            out.append(Event(f"{t.key}:{p['project_id']}:{_phase_key(o)}:{o.get('ftc_date')}:{ctx['revised_ordering_month']}",
                             ctx, p, ctx["phase"]))
    return out


def ev_vendor_shift(d: Data, t, dry: bool) -> List[Event]:
    out = []
    for p in d.projects:
        for o in _orders(p):
            if not o.get("shifted") or o.get("overdue"):
                continue
            ctx = C.phase_context(d.context(p), p, o)
            ctx["shift_reason"] = (f"{p.get('type') or 'Vendor'} monthly allocation full in the target month; "
                                   f"order placed in {', '.join(o.get('months') or [])}")
            out.append(Event(f"{t.key}:{p['project_id']}:{_phase_key(o)}:{'+'.join(o.get('months') or [])}",
                             ctx, p, ctx["phase"]))
    return out


def ev_awaiting_grn(d: Data, t, dry: bool) -> List[Event]:
    min_days = int((t.config or {}).get("min_days", 30))
    every = max(1, int((t.config or {}).get("remind_every_days", 7)))
    out = []
    for p in d.projects:
        pr = p.get("procurement") or {}
        days = pr.get("oldest_awaiting_days") or 0
        if (pr.get("awaiting_grn_mwp") or 0) > 0 and days >= min_days:
            out.append(Event(f"{t.key}:{p['project_id']}:{(days - min_days) // every}", d.context(p), p))
    return out


def ev_checklist_missing(d: Data, t, dry: bool) -> List[Event]:
    out = []
    for p in d.projects:
        pr = p.get("procurement") or {}
        due, made = pr.get("checklist_due") or 0, pr.get("checklist_created") or 0
        if due > made:
            out.append(Event(f"{t.key}:{p['project_id']}:{due}:{made}", d.context(p), p))
    return out


def ev_site_stock_low(d: Data, t, dry: bool) -> List[Event]:
    floor = float((t.config or {}).get("min_stock_mwp", 5))
    week = C.today().isocalendar()
    out = []
    for p in d.projects:
        cap, erected = p.get("capacity_mwp") or 0, p.get("erection_done_mwp") or 0
        stock = p.get("module_inventory_mwp") or 0
        if (p.get("ordered_mwp") or 0) > 0 and cap - erected > 1 and stock <= floor:
            out.append(Event(f"{t.key}:{p['project_id']}:{week[0]}-W{week[1]}",
                             d.context(p, True), p, orders=_orders(p)))
    return out


def ev_po_detected(d: Data, t, dry: bool) -> List[Event]:
    out = []
    for p in d.projects:
        pid = p["project_id"]
        pos = (p.get("procurement") or {}).get("pos") or []
        current = sorted({str(po.get("po")) for po in pos if po.get("po")})
        known, before = _watch_get(d.db, pid, "pos")
        if not known:
            if not dry:
                _watch_set(d.db, pid, "pos", ",".join(current))
            continue
        seen = set((before or "").split(",")) - {""}
        for po in pos:
            num = str(po.get("po") or "")
            if not num or num in seen:
                continue
            ctx = d.context(p)
            ctx.update({"po_numbers": num, "vendor_name": po.get("vendor") or "",
                        "po_date": C.fmt_day(C.parse_day(_iso_to_day(po.get("po_date")))) or (po.get("po_date") or ""),
                        "po_quantity_mwp": C.mw(po.get("ordered_mwp"))})
            out.append(Event(f"{t.key}:{pid}:{num}", ctx, p, watch=(pid, "pos", ",".join(current))))
    return out


def _iso_to_day(v):
    """'2026-10-14' -> '14-Oct-26' for parse_day."""
    try:
        dt = datetime.strptime(str(v)[:10], "%Y-%m-%d")
        return f"{dt.day:02d}-{C.MON[dt.month - 1]}-{str(dt.year)[-2:]}"
    except (TypeError, ValueError):
        return v


SOURCE_LABEL = {"sharepoint": "SAP (SharePoint)", "p6": "Primavera P6", "pulse": "Pulse (Quality)",
                "einvoice": "E-Invoice", "tc": "Transmission", "capacity": "Capacity Milestones",
                "mapping": "Project Mapping"}


def ev_sync_failed(d: Data, t, dry: bool) -> List[Event]:
    stale_h = int((t.config or {}).get("stale_hours", 26))
    now, out = datetime.utcnow(), []
    enabled = {s.source for s in d.db.query(models.SyncSchedule).filter(models.SyncSchedule.enabled.is_(True)).all()}
    for src, label in SOURCE_LABEL.items():
        if enabled and src not in enabled:
            continue
        last = (d.db.query(models.SyncLog).filter(models.SyncLog.source == src)
                .order_by(models.SyncLog.started_at.desc()).first())
        ok = (d.db.query(models.SyncLog).filter(models.SyncLog.source == src, models.SyncLog.status == "success")
              .order_by(models.SyncLog.finished_at.desc()).first())
        if not last:
            continue
        failed = last.status == "failed"
        stale = not ok or not ok.finished_at or now - ok.finished_at > timedelta(hours=stale_h)
        if not (failed or stale):
            continue
        ctx = {k: v for k, v in d.context({"project_name": ""}).items() if k not in ("project_name",)}
        ctx.update({"source_name": label,
                    "sync_error": (last.message or "")[:300] if failed else f"No successful run for over {stale_h} hours",
                    "last_success": (ok.finished_at + C.IST).strftime("%d-%b-%y %H:%M IST") if ok and ok.finished_at else "Never"})
        day = (now + C.IST).strftime("%Y-%m-%d")
        out.append(Event(f"{t.key}:{src}:{day}", ctx))
    return out


def ev_weekly_digest(d: Data, t, dry: bool, force: bool = False) -> List[Event]:
    weekday = int((t.config or {}).get("weekday", 0))
    today = C.today()
    if today.weekday() != weekday and not force:
        return []
    monday = today - timedelta(days=today.weekday())
    period = f"{C.fmt_day(monday)} to {C.fmt_day(monday + timedelta(days=6))}"
    week = today.isocalendar()
    out, seen = [], set()
    recips = (d.db.query(models.EmailRecipient)
              .filter(models.EmailRecipient.group_key.in_(t.to_groups or []), models.EmailRecipient.active.is_(True)).all())
    for r in recips:
        if r.email.lower() in seen:
            continue
        seen.add(r.email.lower())
        ports = {x.lower() for x in (r.portfolios or [])}
        projects = [p for p in d.projects if not ports or (p.get("cluster") or "").lower() in ports]
        ctx = d.context({"project_name": ""})
        ctx.update({"digest_period": period, "digest_table": digest_table(projects, d.cfg.public_url)})
        out.append(Event(f"{t.key}:{r.email.lower()}:{week[0]}-W{week[1]}", ctx, to_override=[r.email]))
    return out


def digest_table(projects: List[dict], base: str) -> str:
    """Overdue, due within 30 days and FTC-at-risk orders, most urgent first."""
    today, rows = C.today(), []
    for p in projects:
        for o in _orders(p):
            od = C.parse_day(o.get("order_date"))
            if not od:
                continue
            days = (od - today).days
            if o.get("overdue"):
                status, rank = f"Overdue {-days} d", 0
            elif not o.get("ftc_reachable", True):
                status, rank = f"FTC at risk ({o.get('ftc_short_days')} d short)", 1
            elif days <= 30:
                status, rank = f"Due in {days} d", 2
            else:
                continue
            rows.append((rank, days, p, o, status))
    if not rows:
        return '<p style="margin:0 0 14px;color:#15803d;">Nothing overdue, due in the next 30 days, or at risk. 👍</p>'
    rows.sort(key=lambda r: (r[0], r[1]))
    colour = {0: "#b42318", 1: "#b42318", 2: "#b45309"}
    e = html_mod.escape
    trs = []
    for rank, _, p, o, status in rows[:60]:
        name = e(p.get("project_name") or "")
        if base and p.get("project_id"):
            name = f'<a href="{e(base)}/ceo-dashboard/project/{e(str(p["project_id"]))}" style="color:#0b74b1;">{name}</a>'
        phase = "" if (o.get("phase_label") or "").strip().lower() in C.UNPHASED else e(o.get("phase_label") or "")
        trs.append(
            f'<tr><td style="padding:6px 8px;border-bottom:1px solid #eef0f3;">{name}<br>'
            f'<span style="color:#6b7280;font-size:11px;">{phase}</span></td>'
            f'<td style="padding:6px 8px;border-bottom:1px solid #eef0f3;text-align:right;">{C.mw(o.get("mwp"))}</td>'
            f'<td style="padding:6px 8px;border-bottom:1px solid #eef0f3;">{e(o.get("order_date") or "")}</td>'
            f'<td style="padding:6px 8px;border-bottom:1px solid #eef0f3;">{e(o.get("ftc_date") or "")}</td>'
            f'<td style="padding:6px 8px;border-bottom:1px solid #eef0f3;color:{colour[rank]};font-weight:600;">{e(status)}</td></tr>')
    more = f'<p style="color:#6b7280;font-size:12px;">…and {len(rows) - 60} more in Akasha.</p>' if len(rows) > 60 else ""
    head = "".join(f'<th style="padding:6px 8px;text-align:{a};font-size:11px;color:#6b7280;border-bottom:1px solid #e5e7eb;">{h}</th>'
                   for h, a in [("Project", "left"), ("MWp", "right"), ("Order by", "left"), ("FTC (P6)", "left"), ("Status", "left")])
    return (f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="font-size:12.5px;'
            f'border:1px solid #e5e7eb;border-radius:8px;margin:0 0 16px;"><tr>{head}</tr>{"".join(trs)}</table>{more}')


TRIGGERS = {
    "ordering_due": ev_ordering_due, "ordering_today": ev_ordering_today, "ordering_overdue": ev_ordering_overdue,
    "date_change": ev_date_change, "ftc_unreachable": ev_ftc_unreachable, "vendor_shift": ev_vendor_shift,
    "awaiting_grn": ev_awaiting_grn, "checklist_missing": ev_checklist_missing, "site_stock_low": ev_site_stock_low,
    "po_detected": ev_po_detected, "sync_failed": ev_sync_failed, "weekly_digest": ev_weekly_digest,
}


# ── Delivery ─────────────────────────────────────────────────────────────────

def _blocked(db: Session, key: str, test_mode: bool) -> Optional["models.EmailLog"]:
    """The log row that means this event is already handled, if any."""
    rows = db.query(models.EmailLog).filter(models.EmailLog.event_key == key).order_by(models.EmailLog.id.desc()).all()
    done = {"sent", "baseline"} | ({"test"} if test_mode else set())
    for r in rows:
        if r.status in done:
            return r
        if r.status == "no_recipients" and r.created_at and r.created_at.date() == datetime.utcnow().date():
            return r     # retried tomorrow, so adding recipients picks it up
        if r.status == "failed" and (r.attempts or 1) >= MAX_ATTEMPTS:
            return r
    return None


def deliver(db: Session, t, ev: Event, d: Data, triggered_by: str, dry_run: bool = False,
            force_to: Optional[List[str]] = None, test_banner: str = "") -> dict:
    """Render, address, send and log one email. Returns a summary row."""
    cfg = d.cfg
    portfolio = (ev.project or {}).get("cluster")
    if force_to is not None:
        to, cc = list(force_to), []
    elif ev.to_override is not None:
        to, cc = list(ev.to_override), []
    else:
        to = members(db, list(t.to_groups or []) + ev.add_to, portfolio)
        cc = members(db, list(t.cc_groups or []) + ev.add_cc, portfolio)
    to, dropped_to = sender.allowed(to, cfg.allowed_domains)
    cc, dropped_cc = sender.allowed([a for a in cc if a.lower() not in {x.lower() for x in to}], cfg.allowed_domains)

    real_to, real_cc = to, cc
    banner = test_banner
    if cfg.test_mode and force_to is None:
        banner = banner or f"TEST MODE - would have gone to: {', '.join(to + cc) or 'nobody (no recipients)'}"
        to, cc = sender.allowed(cfg.test_recipients, cfg.allowed_domains)[0], []

    subject, html_body, text_body = render.render(t, ev.ctx, banner)
    if cfg.test_mode or test_banner:
        subject = f"[TEST] {subject}"

    row = {"template": t.key, "event_key": ev.key, "project_id": (ev.project or {}).get("project_id"),
           "project_name": (ev.project or {}).get("project_name") or ev.ctx.get("source_name"),
           "phase": ev.phase, "to": real_to, "cc": real_cc, "subject": subject}
    if dry_run:
        return {**row, "status": "would_send" if real_to else "no_recipients"}

    attachments = []
    if t.attach_snapshot and ev.project is not None:
        try:
            plan = d.plans().get(str(ev.project.get("project_id")))
            pdf = snapshot.build(ev.project, {**d.context(ev.project), **ev.ctx}, plan, ev.orders or _orders(ev.project))
            safe = "".join(ch for ch in (ev.project.get("project_name") or "project") if ch.isalnum() or ch in " -_").strip()
            attachments.append((f"Akasha snapshot - {safe[:60]}.pdf", pdf, "application/pdf"))
        except Exception as e:  # noqa: BLE001 - an email without the snapshot beats no email
            logger.warning(f"Email snapshot failed for {ev.key}: {e}")

    status, detail = "sent", None
    dropped = dropped_to + dropped_cc
    if dropped:
        detail = f"Not sent to addresses outside {', '.join(cfg.allowed_domains)}: {', '.join(dropped)}"
    if not to:
        status, detail = "no_recipients", ("No recipients in the template's groups for this portfolio"
                                           if not cfg.test_mode else "EMAIL_TEST_RECIPIENTS is empty")
    else:
        try:
            sender.send(cfg, to, cc, subject, html_body, text_body, attachments, tag=t.key)
            status = "test" if (cfg.test_mode or test_banner) else "sent"
        except sender.SendError as e:
            status, detail = "failed", str(e)

    prev = (db.query(models.EmailLog).filter(models.EmailLog.event_key == ev.key, models.EmailLog.status == "failed")
            .order_by(models.EmailLog.id.desc()).first()) if status != "test" else None
    log = models.EmailLog(
        template_key=t.key, template_version=t.version, event_key=ev.key, severity=t.severity,
        project_id=row["project_id"], project_name=row["project_name"], phase=ev.phase or None,
        to_addrs=real_to if cfg.test_mode else to, cc_addrs=real_cc if cfg.test_mode else cc,
        subject=subject, body_html=html_body, attachments=[a[0] for a in attachments] or None,
        status=status, detail=detail, attempts=((prev.attempts or 1) + 1) if prev else 1,
        triggered_by=triggered_by, created_at=datetime.utcnow())
    db.add(log)
    if ev.watch and status in ("sent", "test", "no_recipients"):
        _watch_set(db, *ev.watch)
    db.commit()
    return {**row, "status": status, "detail": detail, "log_id": log.id}


def run(db: Session, triggered_by: str = "scheduler", dry_run: bool = False, only: Optional[List[str]] = None) -> dict:
    """One pass over every enabled template (or `only`). Dry run reports
    what would go out without sending, logging or recording anything."""
    cfg = settings()
    if not dry_run and not cfg.enabled:
        return {"message": "Email sending is off (EMAIL_ENABLED=false) - nothing sent", "sent": 0, "items": []}
    seed_templates(db)
    q = db.query(models.EmailTemplate).filter(models.EmailTemplate.trigger != "manual")
    q = q.filter(models.EmailTemplate.key.in_(only)) if only else q.filter(models.EmailTemplate.enabled.is_(True))
    templates = q.all()
    if not templates:
        return {"message": "No enabled email templates", "sent": 0, "items": []}
    d = Data(db)
    items, counts = [], {}
    for t in templates:
        fn = TRIGGERS.get(t.trigger)
        if not fn:
            continue
        try:
            events = fn(d, t, dry_run)
        except Exception as e:  # noqa: BLE001 - one bad trigger must not stop the others
            logger.exception(f"Email trigger {t.key} failed")
            items.append({"template": t.key, "status": "error", "detail": str(e)})
            continue
        for ev in events:
            if _blocked(db, ev.key, cfg.test_mode):
                continue
            r = deliver(db, t, ev, d, triggered_by, dry_run)
            items.append(r)
            counts[r["status"]] = counts.get(r["status"], 0) + 1
    if not dry_run:
        db.commit()     # first-sighting records from the date / PO watches
    msg = ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in sorted(counts.items())) or "Nothing new to send"
    return {"message": msg, "counts": counts, "items": items, "dry_run": dry_run,
            "sent": counts.get("sent", 0) + counts.get("test", 0)}


def baseline(db: Session, who: str) -> dict:
    """Go-live: record every alert that is already true today as handled
    (status 'baseline'), so switching email on sends only what happens from
    now on instead of a backlog flood. The weekly digest still lists the
    backlog. Watched dates / POs are recorded too."""
    seed_templates(db)
    templates = (db.query(models.EmailTemplate)
                 .filter(models.EmailTemplate.trigger.notin_(["manual", "weekly_digest", "sync_failed"])).all())
    d = Data(db)
    n, per = 0, {}
    for t in templates:
        fn = TRIGGERS.get(t.trigger)
        if not fn:
            continue
        for ev in fn(d, t, False):
            if _blocked(db, ev.key, False):
                continue
            db.add(models.EmailLog(template_key=t.key, template_version=t.version, event_key=ev.key,
                                   severity=t.severity, project_id=(ev.project or {}).get("project_id"),
                                   project_name=(ev.project or {}).get("project_name"), phase=ev.phase or None,
                                   status="baseline", detail="Already true when email went live - not sent",
                                   triggered_by=f"{who} (go-live)", created_at=datetime.utcnow()))
            if ev.watch:
                _watch_set(db, *ev.watch)
            n += 1
            per[t.key] = per.get(t.key, 0) + 1
    db.commit()
    return {"message": f"{n} existing alert(s) marked as handled; only new events will be emailed", "by_template": per}


# ── Admin actions ────────────────────────────────────────────────────────────

def sample_event(d: Data, t, project_id: Optional[str] = None) -> Event:
    """A realistic event for previews and tests: the template's own trigger
    for the chosen (or first matching) project, else the project's first
    order as a stand-in."""
    if t.trigger in TRIGGERS and t.trigger not in ("sync_failed",):
        try:
            fn = TRIGGERS[t.trigger]
            evs = fn(d, t, True, force=True) if t.trigger == "weekly_digest" else fn(d, t, True)
            if project_id:
                evs = [e for e in evs if str((e.project or {}).get("project_id")) == str(project_id)] or evs[:0]
            if evs:
                return evs[0]
        except Exception:  # noqa: BLE001
            pass
    if t.trigger == "sync_failed":
        ctx = d.context({"project_name": ""})
        ctx.update({"source_name": "Primavera P6", "sync_error": "Example: login failed",
                    "last_success": "Example"})
        return Event("preview", ctx)
    p = d.project(project_id) if project_id else next((x for x in d.projects if _orders(x)), d.projects[0] if d.projects else None)
    if not p:
        return Event("preview", d.context({"project_name": ""}))
    orders = _orders(p)
    ctx = C.phase_context(d.context(p, True), p, orders[0]) if orders else d.context(p, True)
    ctx.setdefault("escalation_level", "Level 1 - overdue")
    pos = (p.get("procurement") or {}).get("pos") or []
    if pos:   # PO templates: show the project's latest PO
        po = sorted(pos, key=lambda x: str(x.get("po_date") or ""))[-1]
        ctx.setdefault("po_date", C.fmt_day(C.parse_day(_iso_to_day(po.get("po_date")))) or "")
        ctx.setdefault("po_quantity_mwp", C.mw(po.get("ordered_mwp")))
    if t.trigger == "weekly_digest":
        ctx.update({"digest_period": "this week", "digest_table": digest_table(d.projects, d.cfg.public_url)})
    return Event(f"{t.key}:{p['project_id']}:manual", ctx, p, ctx.get("phase", ""), orders=orders)


# Values that only exist when the event happens (a date change, an
# escalation step, a failing feed). A preview without such an event shows
# the catalogue sample, marked as an example - a real email never does.
EVENT_ONLY = {"changed_date_field", "previous_date", "revised_date", "date_variance_days", "escalation_level",
              "shift_reason", "source_name", "sync_error", "last_success", "po_numbers", "po_date",
              "po_quantity_mwp", "vendor_name", "digest_period"}


def preview(db: Session, t, project_id: Optional[str] = None) -> dict:
    d = Data(db)
    ev = sample_event(d, t, project_id)
    for v in render.used_variables(t.subject, t.body):
        if v in EVENT_ONLY and not str(ev.ctx.get(v) or "").strip() and catalogue.VARIABLES[v][2]:
            ev.ctx[v] = f"{catalogue.VARIABLES[v][2]} (example)"
    subj, html_body, _ = render.render(t, ev.ctx)
    used = render.used_variables(t.subject, t.body)
    return {"subject": subj, "html": html_body, "problems": render.validate(t.subject, t.body),
            "project_id": (ev.project or {}).get("project_id"), "project_name": (ev.project or {}).get("project_name"),
            "empty": [v for v in used if not str(ev.ctx.get(v) or "").strip()],
            "to": members(db, list(t.to_groups or []), (ev.project or {}).get("cluster")),
            "cc": members(db, list(t.cc_groups or []), (ev.project or {}).get("cluster"))}


def send_test(db: Session, t, to: str, project_id: Optional[str], who: str) -> dict:
    d = Data(db)
    ev = sample_event(d, t, project_id)
    ev.key = f"test:{t.key}:{datetime.utcnow().isoformat()}"
    return deliver(db, t, ev, d, f"{who} (test)", force_to=[to],
                   test_banner=f"Test send by {who} - not sent to the template's recipients")


def send_manual(db: Session, t, project_id: str, who: str) -> dict:
    d = Data(db)
    ev = sample_event(d, t, project_id)
    if not ev.project:
        raise ValueError(f"Project {project_id} is not in the Ordering Schedule")
    ev.key = f"manual:{t.key}:{project_id}:{datetime.utcnow().isoformat()}"
    return deliver(db, t, ev, d, f"{who} (manual)")


def resend(db: Session, log_id: int, who: str) -> dict:
    """Send a logged email again, exactly as it was rendered."""
    cfg = settings()
    row = db.get(models.EmailLog, log_id)
    if not row:
        raise ValueError("No such email")
    to, cc = list(row.to_addrs or []), list(row.cc_addrs or [])
    if cfg.test_mode:
        to, cc = cfg.test_recipients, []
    status, detail = "sent", None
    try:
        sender.send(cfg, to, cc, row.subject or "", row.body_html or "",
                    "This message is best viewed in an HTML-capable mail client.", tag=row.template_key)
        status = "test" if cfg.test_mode else "sent"
    except sender.SendError as e:
        status, detail = "failed", str(e)
    log = models.EmailLog(template_key=row.template_key, template_version=row.template_version,
                          event_key=f"resend:{row.event_key}:{datetime.utcnow().isoformat()}", severity=row.severity,
                          project_id=row.project_id, project_name=row.project_name, phase=row.phase,
                          to_addrs=row.to_addrs, cc_addrs=row.cc_addrs, subject=row.subject, body_html=row.body_html,
                          attachments=None, status=status, detail=detail or f"Resend of email #{row.id}",
                          triggered_by=f"{who} (resend)", created_at=datetime.utcnow())
    db.add(log)
    db.commit()
    return {"status": status, "detail": detail, "log_id": log.id}
