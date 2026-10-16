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
from urllib.parse import quote
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

import models
from . import alerts, catalogue, context as C, render, sender, snapshot
from .config import settings

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 3


# ── Templates ────────────────────────────────────────────────────────────────

_OLD_OVERDUE_STEPS = [
    {"after_days": 0, "label": "Level 1 - overdue", "add_to": [], "add_cc": []},
    {"after_days": 7, "label": "Level 2 - 7 days overdue", "add_to": ["tc_head"], "add_cc": ["pmag"]},
    {"after_days": 14, "label": "Level 3 - 14 days overdue", "add_to": [], "add_cc": ["executive"]},
]
_DEFAULT_UPGRADES = [
    ("ordering_due_30", {"days_before": 30, "days_until": 8}, {"days_before": 30, "days_until": 16},
     "The 15-day reminder takes over at 15 days: the 30-day window now ends at 16"),
    ("ordering_overdue", {"escalation": _OLD_OVERDUE_STEPS}, {"escalation": catalogue.LEVELS},
     "Overdue steps renamed - levels of intimation are now set per template"),
]


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
    # Shipped settings that changed: a template still holding the exact old
    # default gets the new one (as a new version, with a note); anything an
    # administrator changed is left alone.
    for key, old, new, note in _DEFAULT_UPGRADES:
        t = db.get(models.EmailTemplate, key)
        if t and (t.config or {}) == old:
            t.config, t.version = new, (t.version or 1) + 1
            t.updated_by, t.updated_at = "system", datetime.utcnow()
            db.add(version_row(t, "system", note))
            added += 1
    # Module ordering reminders became one template with L1 / L2 / L3 days.
    # The 30-day template takes the three stages; the separate 15- and 7-day
    # templates go, but only while nobody has edited them and they have never
    # sent anything (otherwise they stay for an administrator to retire).
    due = db.get(models.EmailTemplate, "ordering_due_30")
    if due and "levels" not in (due.config or {}):
        src = next(x for x in catalogue.TEMPLATES if x["key"] == "ordering_due_30")
        due.config = dict(src["config"])
        due.name, due.description = src["name"], src["description"]
        due.version, due.updated_by, due.updated_at = (due.version or 1) + 1, "system", datetime.utcnow()
        db.add(version_row(due, "system", "One reminder with L1 / L2 / L3 days (30 / 15 / 7 days before the ordering date)"))
        added += 1
    for key in ("ordering_due_15", "ordering_due_7"):
        t = db.get(models.EmailTemplate, key)
        if t and (t.updated_by or "system") == "system" and not t.enabled and not db.query(models.EmailLog).filter(
                models.EmailLog.template_key == key).first():
            db.query(models.EmailTemplateVersion).filter(models.EmailTemplateVersion.template_key == key).delete()
            db.delete(t)
            added += 1
    ov = db.get(models.EmailTemplate, "ordering_overdue")
    if ov and ov.level == 3 and ov.updated_by == "system" and ov.version <= 2:
        ov.level = 1      # its steps set the level: L1 when missed, L2 at 7 days, L3 at 14
        added += 1
    # Shipped text that changed, for templates nobody has edited.
    for key, note in (("approval_request", "Approval requests now come from the Ordering Schedule"),
                      ("date_change", "Says who changed the date and the reason given")):
        t = db.get(models.EmailTemplate, key)
        src = next((x for x in catalogue.TEMPLATES if x["key"] == key), None)
        if t and src and (t.updated_by or "system") == "system" and (t.body != src["body"] or t.subject != src["subject"]):
            t.subject, t.body, t.description = src["subject"], src["body"], src["description"]
            t.version, t.updated_at = (t.version or 1) + 1, datetime.utcnow()
            db.add(version_row(t, "system", note))
            added += 1
    # days_until is no longer used (each phase gets the nearest reminder it
    # has reached), so it is dropped rather than left to mislead.
    for t in db.query(models.EmailTemplate).filter(models.EmailTemplate.trigger == "ordering_due").all():
        if "days_until" in (t.config or {}):
            t.config = {k: v for k, v in t.config.items() if k != "days_until"}
            t.version, t.updated_by, t.updated_at = (t.version or 1) + 1, "system", datetime.utcnow()
            db.add(version_row(t, "system", "Removed days_until - each phase now gets the nearest reminder it has reached"))
            added += 1
    # Level / acknowledgement arrived after the first templates were saved:
    # fill them from the catalogue once, never over an administrator's choice.
    for t in db.query(models.EmailTemplate).filter(
            (models.EmailTemplate.level.is_(None)) | (models.EmailTemplate.ack_required.is_(None))).all():
        if t.level is None:
            t.level = catalogue.LEVEL_DEFAULT.get(t.key, 1)
        if t.ack_required is None:
            t.ack_required = t.key in catalogue.ACK_DEFAULT
        added += 1
    if added:
        db.commit()
    return added


def version_row(t, who: str, note: str = "") -> "models.EmailTemplateVersion":
    return models.EmailTemplateVersion(
        template_key=t.key, version=t.version, name=t.name, subject=t.subject, body=t.body,
        to_groups=list(t.to_groups or []), cc_groups=list(t.cc_groups or []), config=dict(t.config or {}),
        attach_snapshot=bool(t.attach_snapshot), enabled=bool(t.enabled), level=t.level,
        ack_required=t.ack_required, note=note or None,
        changed_by=who, changed_at=datetime.utcnow())


# ── Recipients ───────────────────────────────────────────────────────────────

# The demo projects' portfolio (scripts/demo_email_project.py; the self-test
# uses "Akasha Demo Selftest"). Only people who list it explicitly hear about
# it - "all portfolios" never includes a demo.
DEMO_PORTFOLIO = "Akasha Demo"


def members(db: Session, groups: List[str], portfolio: Optional[str] = None, level: int = 1) -> List[str]:
    """Active addresses of the groups, limited to people who cover the
    project's portfolio (a member with no portfolios covers every one) and
    whose level of intimation the alert has reached: an L2 member hears of
    an alert only once it has escalated to level 2."""
    if not groups:
        return []
    out = []
    for r in (db.query(models.EmailRecipient)
              .filter(models.EmailRecipient.group_key.in_(groups), models.EmailRecipient.active.is_(True)).all()):
        ports = [x.lower() for x in (r.portfolios or [])]
        if portfolio and ports and portfolio.lower() not in ports:
            continue
        if portfolio and portfolio.lower().startswith(DEMO_PORTFOLIO.lower()) and not ports:
            continue
        if (r.level or 1) > level:
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
        self._cod: Optional[Dict[str, dict]] = None

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

    def cod(self) -> Dict[str, dict]:
        """Per P6 project: the AOP (baseline finish of the COD milestones),
        the P6 forecast COD (current finish), whether COD is achieved (every
        COD milestone has an actual finish) and progress as completed /
        total activities - all from the latest P6 snapshot, never estimated.
        A multi-phase project takes its latest phase, as the AOP column does."""
        if self._cod is None:
            from routers.module_deliveries import LATEST_P6
            self._cod = {}
            for pid, aop, fc, done in self.db.execute(text(f"""
                WITH latest_p6 AS ({LATEST_P6})
                SELECT p.project_id, MAX(a.baseline_finish_date), MAX(a.finish_date),
                       BOOL_AND(a.actual_finish_date IS NOT NULL)
                FROM p6_activity a JOIN latest_p6 p ON p.p6_object_id = a.project_object_id
                WHERE a.name ILIKE 'COD%' AND a.type = 'Finish Milestone'
                GROUP BY p.project_id""")):
                self._cod[str(pid)] = {"aop": aop.date() if aop else None, "forecast": fc.date() if fc else None,
                                       "achieved": bool(done)}
            for pid, total, completed in self.db.execute(text(f"""
                WITH latest_p6 AS ({LATEST_P6})
                SELECT p.project_id, COUNT(*), COUNT(*) FILTER (WHERE a.status = 'Completed')
                FROM p6_activity a JOIN latest_p6 p ON p.p6_object_id = a.project_object_id
                GROUP BY p.project_id""")):
                self._cod.setdefault(str(pid), {})["activities"] = (int(total or 0), int(completed or 0))
        return self._cod


@dataclass
class Event:
    key: str
    ctx: Dict
    project: Optional[dict] = None
    phase: str = ""
    add_to: List[str] = field(default_factory=list)
    add_cc: List[str] = field(default_factory=list)
    to_override: Optional[List[str]] = None       # digest: one recipient
    level: int = 1                                 # overdue step reached (1 = first notice)
    orders: List[dict] = field(default_factory=list)
    watch: Optional[tuple] = None                 # (project_id, field, value) to record after sending
    case_key: Optional[str] = None                # the alert it belongs to (alerts.case_key)
    case_phase: Optional[str] = None              # module ordering: the phase label
    extra_to: List[str] = field(default_factory=list)   # addresses, not groups (an approval's requester)
    extra_cc: List[str] = field(default_factory=list)


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
    """The template's L1 / L2 / L3 reminders (config levels, e.g. 30 / 15 /
    7 days before the ordering date). An order gets the nearest stage it has
    reached - a project first seen 12 days out gets the L2 email, not the L1
    one as well - and each stage once."""
    mine = alerts.due_stages(t)
    if not mine:
        return []
    every = {n for _, n in mine} | {n for x in d.db.query(models.EmailTemplate)
                                    .filter(models.EmailTemplate.trigger == "ordering_due", models.EmailTemplate.enabled.is_(True),
                                            models.EmailTemplate.key != t.key).all() for _, n in alerts.due_stages(x)}
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
            reached = [s for s in mine if s[1] >= days >= 1]
            if not reached:
                continue
            lv, n = min(reached, key=lambda s: s[1])
            if min(x for x in every if x >= days) != n:
                continue            # another reminder's nearer stage applies
            ctx = C.phase_context(d.context(p, t.attach_snapshot or "construction_progress" in t.body), p, o)
            # The L1 key keeps its original form, so a go-live baseline still matches.
            key = f"{t.key}:{p['project_id']}:{_phase_key(o)}" + (f":L{lv}" if lv > 1 else "")
            out.append(Event(key, ctx, p, ctx["phase"], orders=orders, level=lv, case_phase=o.get("phase_label")))
    return out


def ev_ordering_today(d: Data, t, dry: bool) -> List[Event]:
    today, out = C.today(), []
    for p in d.projects:
        if (p.get("balance_ordering_mwp") or 0) <= 0:
            continue
        for o in _orders(p):
            if C.parse_day(o.get("order_date")) == today:
                ctx = C.phase_context(d.context(p), p, o)
                out.append(Event(f"{t.key}:{p['project_id']}:{_phase_key(o)}", ctx, p, ctx["phase"],
                                 case_phase=o.get("phase_label")))
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
                             add_to, add_cc, orders=orders, level=min(idx, 3), case_phase=o.get("phase_label")))
    return out


FIELD_LABEL = {"ftc_date": "FTC date", "lta": "LTA date", "scod": "SCOD", "aop_plan": "AOP date",
               "module_date": "Module ordering date"}


FIELD_ORIGIN = {"ftc_date": "Primavera P6 sync", "aop_plan": "Primavera P6 sync (baseline COD)",
                "module_date": "Recalculated from the P6 dates"}


def _change_origin(db, p: dict, f: str, new_day) -> tuple:
    """(who / what changed it, the reason given) - from the LTA / SCOD
    history for those two; the sync that feeds the others."""
    if f in ("lta", "scod") and p.get("id"):
        q = (db.query(models.ProjectDateChange)
             .filter(models.ProjectDateChange.mapping_id == p["id"], models.ProjectDateChange.field == f)
             .order_by(models.ProjectDateChange.changed_at.desc(), models.ProjectDateChange.id.desc()))
        for r in q.limit(5).all():
            if (r.new_value.date() if r.new_value else None) == new_day:
                from services.date_history import SOURCE_LABEL
                label = SOURCE_LABEL.get(r.source, r.source)
                who = f"{label} by {r.changed_by}" if r.source == "manual" and r.changed_by else label
                return who, (r.remarks or ("Automatic update - no reason recorded" if r.source != "manual" else ""))
        return "Transmission portal / project mapping", "Automatic update - no reason recorded"
    return FIELD_ORIGIN.get(f, "Data sync"), "Automatic update - no reason recorded"


def _gap(days: int, what: str) -> str:
    return f"{days} days after {what}" if days > 0 else f"{-days} days before {what}" if days < 0 else f"on {what}"


def _change_impact(d: "Data", p: dict, f: str, old, new) -> str:
    """What the changed date means now, worked out from the current plan
    and P6 - stated only where Akasha has the figures, never guessed."""
    today, out = C.today(), []
    info = d.cod().get(str(p.get("project_id"))) or {}
    fc = info.get("forecast")
    lta, scod, aop = C.parse_day(p.get("lta")), C.parse_day(p.get("scod")), C.parse_day(p.get("aop_plan"))
    if f == "aop_plan":
        if info.get("achieved"):
            out.append("COD is already achieved")
        elif fc and new:
            exp = today if fc < today else fc
            line = f"P6 forecast COD {C.fmt_day(fc)} is {_gap((exp - new).days, 'the new AOP')}"
            if old:
                line += f" (it was {_gap((exp - old).days, 'the old AOP')})"
            out.append(line + (" - the P6 forecast date has already passed without COD" if fc < today else ""))
        total, done = info.get("activities", (0, 0))
        if total:
            out.append(f"progress {round(done / total * 100)}% ({done:,} of {total:,} P6 activities completed)")
    elif f == "lta":
        if new:
            ftcs = [x for x in (C.parse_day(s) for s in str(p.get("ftc_date") or "").split("·")) if x]
            late = [x for x in ftcs if x > new]
            if ftcs:
                out.append(f"{len(late)} of {len(ftcs)} phase FTC date(s) fall after the new LTA" if late
                           else "every phase FTC is on or before the new LTA")
            if scod:
                out.append(f"SCOD {C.fmt_day(scod)} is {_gap((scod - new).days, 'the LTA')}")
        else:
            out.append("the project now has no LTA - transmission readiness cannot be checked")
    elif f == "scod":
        parts = ([f"{_gap((new - lta).days, 'the LTA')} ({C.fmt_day(lta)})"] if new and lta else []) +                 ([f"{_gap((new - aop).days, 'the AOP')} ({C.fmt_day(aop)})"] if new and aop else [])
        if parts:
            out.append("the new SCOD is " + " and ".join(parts))
    elif f in ("ftc_date", "module_date"):
        nxt = sorted((C.parse_day(o.get("order_date")), o) for o in _orders(p) if C.parse_day(o.get("order_date")))
        if nxt:
            od, o = nxt[0]
            days = (od - today).days
            out.append(f"next order {C.mw(o.get('mwp'))} MWp by {C.fmt_day(od)} "
                       + (f"({days} days from today)" if days >= 0 else f"({-days} days overdue)"))
        if (p.get("ftc_at_risk_mwp") or 0) > 0:
            out.append(f"{C.mw(p['ftc_at_risk_mwp'])} MWp can no longer reach its P6 FTC from the planned order month")
        elif (p.get("balance_ordering_mwp") or 0) <= 0:
            out.append("fully ordered - no module order is affected")
    if not out:
        return "No impact Akasha can measure from the data it holds"
    s = "; ".join(out)
    return s[0].upper() + s[1:]


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
            src, why = _change_origin(d.db, p, f, a)
            w = d.db.get(models.EmailWatch, (str(pid), f"date:{f}"))
            since = w.updated_at.strftime("%Y%m%d%H%M%S") if w and w.updated_at else ""
            ctx.update({"changed_date_field": FIELD_LABEL.get(f, f), "previous_date": before or "Not set",
                        "revised_date": now_v or "Removed",
                        "date_variance_days": (f"{(a - b).days:+d}" if a and b else ""),
                        "change_source": src, "change_remarks": why,
                        "change_impact": _change_impact(d, p, f, b, a)})
            # One email per transition: the key carries the value it moved
            # from and when that value was recorded, so A -> B -> A is two.
            out.append(Event(f"{t.key}:{pid}:{f}:{before}>{now_v}:{since}", ctx, p, watch=(pid, f"date:{f}", now_v)))
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
                             ctx, p, ctx["phase"],
                             case_key=f"{t.key}:{p['project_id']}:{alerts.phase_id(o.get('phase_label'))}"))
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
            out.append(Event(f"{t.key}:{p['project_id']}:{(days - min_days) // every}", d.context(p), p,
                             case_key=f"{t.key}:{p['project_id']}"))
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
        # Negative stock = P6 erected more than SAP received: a data conflict, not a low site stock.
        if (p.get("ordered_mwp") or 0) > 0 and cap - erected > 1 and 0 <= stock <= floor:
            out.append(Event(f"{t.key}:{p['project_id']}:{week[0]}-W{week[1]}",
                             d.context(p, True), p, orders=_orders(p), case_key=f"{t.key}:{p['project_id']}"))
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
        out.append(Event(f"{t.key}:{src}:{day}", ctx, case_key=f"{t.key}:{src}"))
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
        projects = [p for p in d.projects if (not ports and not (p.get("cluster") or "").lower().startswith(DEMO_PORTFOLIO.lower()))
                    or (p.get("cluster") or "").lower() in ports]
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
            name = f'<a href="{e(base)}/project/{e(quote(str(p["project_id"]), safe=""))}" style="color:#0b74b1;">{name}</a>'
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


def _cod_context(d: "Data", p: dict, info: dict) -> Dict:
    """Context for the project-delay and AOP emails: dates, how late, and
    progress with the counts behind the percentage."""
    ctx = d.context(p, True)
    today = C.today()
    aop, fc = info.get("aop"), info.get("forecast")
    total, done = info.get("activities", (0, 0))
    stale = bool(fc and fc < today)
    expected = today if (stale or not fc) else fc
    ctx.update({
        "aop_date": C.fmt_day(aop), "forecast_cod_date": C.fmt_day(fc) if fc else "",
        "cod_delay_days": max(0, (expected - aop).days) if aop else "",
        "days_to_aop": (aop - today).days if aop and aop >= today else "",
        "progress_pct": (f"{round(done / total * 100)}% ({done:,} of {total:,} activities completed)" if total else ""),
        "activities_remaining": f"{total - done:,}" if total else "",
        "forecast_note": (f"P6 still forecasts COD on {C.fmt_day(fc)}, a date that has passed without COD - the P6 schedule needs updating"
                          if stale else f"P6 forecasts COD on {C.fmt_day(fc)}" if fc else "P6 has no COD forecast"),
    })
    return ctx


def _level_for(stages, value, before: bool):
    """The highest level whose threshold `value` has reached. `before`: days
    before a date (smaller is later); otherwise days late (larger is later)."""
    hit = [(lv, n) for lv, n in stages if (value <= n if before else value >= n)]
    return max(hit, key=lambda x: x[0]) if hit else None


def ev_project_delay(d: Data, t, dry: bool) -> List[Event]:
    """COD later than the AOP: L1 / L2 / L3 at the configured days late
    (config levels, e.g. 15 / 30 / 60). Late = the P6 forecast COD after the
    AOP, or - where that forecast has passed without COD - today."""
    stages = alerts.config_stages(t, {"1": 15, "2": 30, "3": 60})
    cod, today, out = d.cod(), C.today(), []
    for p in d.projects:
        info = cod.get(str(p.get("project_id")))
        if not info or info.get("achieved") or not info.get("aop"):
            continue
        fc = info.get("forecast")
        expected = today if (not fc or fc < today) else fc
        late = (expected - info["aop"]).days
        hit = _level_for(stages, late, before=False)
        if not hit:
            continue
        lv, n = hit
        ctx = _cod_context(d, p, info)
        ctx["escalation_level"] = f"{late} days late against the AOP (level {lv} from {n} days)"
        out.append(Event(f"{t.key}:{p['project_id']}:L{lv}", ctx, p, level=lv, case_key=f"{t.key}:{p['project_id']}"))
    return out


def ev_aop_due(d: Data, t, dry: bool) -> List[Event]:
    """The AOP is near and COD is not achieved: L1 / L2 / L3 at the
    configured days before the AOP (config levels, e.g. 60 / 30 / 15). Once
    the AOP passes, the project-delay email takes over."""
    stages = alerts.config_stages(t, {"1": 60, "2": 30, "3": 15})
    cod, today, out = d.cod(), C.today(), []
    for p in d.projects:
        info = cod.get(str(p.get("project_id")))
        if not info or info.get("achieved") or not info.get("aop") or info["aop"] < today:
            continue
        days = (info["aop"] - today).days
        hit = _level_for(stages, days, before=True)
        if not hit:
            continue
        lv, n = hit
        out.append(Event(f"{t.key}:{p['project_id']}:{info['aop']}:L{lv}", _cod_context(d, p, info), p, level=lv,
                         case_key=f"{t.key}:{p['project_id']}"))
    return out


TRIGGERS = {
    "ordering_due": ev_ordering_due, "ordering_today": ev_ordering_today, "ordering_overdue": ev_ordering_overdue,
    "date_change": ev_date_change, "ftc_unreachable": ev_ftc_unreachable, "vendor_shift": ev_vendor_shift,
    "awaiting_grn": ev_awaiting_grn, "checklist_missing": ev_checklist_missing, "site_stock_low": ev_site_stock_low,
    "po_detected": ev_po_detected, "sync_failed": ev_sync_failed, "weekly_digest": ev_weekly_digest,
    "project_delay": ev_project_delay, "aop_due": ev_aop_due,
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
    """Decide the level, render, address, send and log one email, and record
    it on its alert. Returns a summary row."""
    cfg = d.cfg
    portfolio = (ev.project or {}).get("cluster")
    tracked = force_to is None and ev.to_override is None and alerts.ack_required(t)
    test = bool(cfg.test_mode or test_banner)
    level, alert, what, why = alerts.decide(db, t, ev, test) if force_to is None else (alerts.template_level(t), None, "sent", "")
    add_to, add_cc = (ev.add_to, ev.add_cc) if what != "held" else ([], [])   # a held alert keeps its audience
    if force_to is not None:
        to, cc = list(force_to), []
    elif ev.to_override is not None:
        to, cc = list(ev.to_override), []
    else:
        to = members(db, list(t.to_groups or []) + add_to, portfolio, level) + list(ev.extra_to)
        cc = members(db, list(t.cc_groups or []) + add_cc, portfolio, level) + list(ev.extra_cc)
    to, dropped_to = sender.allowed(to, cfg.allowed_domains)
    cc, dropped_cc = sender.allowed([a for a in cc if a.lower() not in {x.lower() for x in to}], cfg.allowed_domains)

    real_to, real_cc = to, cc
    banner = test_banner
    if cfg.test_mode and force_to is None:
        banner = banner or f"TEST MODE - would have gone to: {', '.join(to + cc) or 'nobody (no recipients)'}"
        to, cc = sender.allowed(cfg.test_recipients, cfg.allowed_domains)[0], []

    row = {"template": t.key, "event_key": ev.key, "project_id": (ev.project or {}).get("project_id"),
           "project_name": (ev.project or {}).get("project_name") or ev.ctx.get("source_name"),
           "phase": ev.phase, "to": real_to, "cc": real_cc, "level": level, "escalation": what, "why": why}
    if dry_run:
        subject, _, _ = render.render(t, ev.ctx, banner)
        return {**row, "subject": f"[TEST] {subject}" if test else subject,
                "status": "would_send" if real_to else "no_recipients"}

    ack = None
    if tracked and real_to:
        alert = alert or alerts.ensure(db, t, ev, level, test)
        ack = {"level": level, "why": why, "ask": alerts.ask_text(t),
               "url": f"{cfg.public_url}/alerts/{alert.id}" if cfg.public_url else ""}
        if alert.kind == "approval":
            ack.update(title="approval required", button="Review and approve in Akasha")
            ev.ctx["akasha_approval_link"] = ack["url"]
    elif force_to is not None and alerts.ack_required(t):
        ack = {"level": level, "why": "", "ask": alerts.ask_text(t) + " (Test copy - the real email links to its alert.)",
               "url": f"{cfg.public_url}/alerts" if cfg.public_url else ""}
    subject, html_body, text_body = render.render(t, ev.ctx, banner, ack)
    # The level shows in the subject too, so an escalation reads as one in the inbox.
    if ack and level >= 2:
        subject = f"[L{level} {'Senior escalation' if level >= 3 else 'Escalation'}] {subject}"
    if test:
        subject = f"[TEST] {subject}"
    row["subject"] = subject

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
            status = "test" if test else "sent"
        except sender.SendError as e:
            status, detail = "failed", str(e)
    if why:
        detail = f"{why} {detail}" if detail else why

    prev = (db.query(models.EmailLog).filter(models.EmailLog.event_key == ev.key, models.EmailLog.status == "failed")
            .order_by(models.EmailLog.id.desc()).first()) if status != "test" else None
    log = models.EmailLog(
        template_key=t.key, template_version=t.version, event_key=ev.key, severity=t.severity,
        project_id=row["project_id"], project_name=row["project_name"], phase=ev.phase or None,
        to_addrs=real_to if cfg.test_mode else to, cc_addrs=real_cc if cfg.test_mode else cc,
        subject=subject, body_html=html_body, attachments=[a[0] for a in attachments] or None,
        status=status, detail=detail, attempts=((prev.attempts or 1) + 1) if prev else 1,
        triggered_by=triggered_by, created_at=datetime.utcnow(), level=level,
        alert_id=alert.id if (alert is not None and ack is not None and status in ("sent", "test")) else None)
    db.add(log)
    db.flush()
    if alert is not None and ack is not None:
        if status in ("sent", "test"):
            alerts.note_sent(db, alert, t, ev, level, what, why, real_to, log.id, triggered_by)
        else:
            alerts.discard_if_unsent(db, alert)
    if ev.watch and status in ("sent", "test", "no_recipients"):
        _watch_set(db, *ev.watch)
    db.commit()
    return {**row, "status": status, "detail": detail, "log_id": log.id,
            "alert_id": log.alert_id}


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
    ran, found = {}, set()     # triggers that ran cleanly, and every alert they still find
    for t in templates:
        fn = TRIGGERS.get(t.trigger)
        if not fn:
            continue
        try:
            events = fn(d, t, dry_run)
        except Exception as e:  # noqa: BLE001 - one bad trigger must not stop the others
            logger.exception(f"Email trigger {t.key} failed")
            items.append({"template": t.key, "status": "error", "detail": str(e)})
            ran[t.trigger] = False
            continue
        ran.setdefault(t.trigger, True)
        for ev in events:
            found.add(alerts.case_key(t, ev))
            if _blocked(db, ev.key, cfg.test_mode):
                continue
            r = deliver(db, t, ev, d, triggered_by, dry_run)
            items.append(r)
            counts[r["status"]] = counts.get(r["status"], 0) + 1
    closed = 0
    if not dry_run:
        closed = alerts.close_finished(db, d, ran, found, cfg.test_mode)
        from services import order_approvals
        order_approvals.refresh_ordered(db, d.projects)     # POs in SAP release approved freezes
        db.commit()     # first-sighting records from the date / PO watches, closed alerts
    msg = ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in sorted(counts.items())) or "Nothing new to send"
    if closed:
        msg += f"; {closed} alert(s) closed - the work is done"
    return {"message": msg, "counts": counts, "items": items, "dry_run": dry_run, "closed": closed,
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
    return {"message": f"{n} existing alert(s) marked as handled; only new events will be emailed", "by_template": per,
            "items": [], "counts": {"baseline": n}}


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
              "po_quantity_mwp", "vendor_name", "digest_period", "order_month", "requested_by", "request_note",
              "approval_status", "approval_decision", "approved_by", "approval_date", "decision_note",
              "approval_next_step", "change_source", "change_remarks", "akasha_approval_link",
              "change_impact", "aop_date", "forecast_cod_date", "cod_delay_days", "days_to_aop", "forecast_note"}


def preview(db: Session, t, project_id: Optional[str] = None) -> dict:
    d = Data(db)
    ev = sample_event(d, t, project_id)
    for v in render.used_variables(t.subject, t.body):
        if v in EVENT_ONLY and not str(ev.ctx.get(v) or "").strip() and catalogue.VARIABLES[v][2]:
            ev.ctx[v] = f"{catalogue.VARIABLES[v][2]} (example)"
    ack = None
    if alerts.ack_required(t):
        ack = {"level": alerts.template_level(t), "why": "", "ask": alerts.ask_text(t),
               "url": f"{d.cfg.public_url}/alerts" if d.cfg.public_url else ""}
    subj, html_body, _ = render.render(t, ev.ctx, "", ack)
    used = render.used_variables(t.subject, t.body)
    return {"subject": subj, "html": render.for_browser(html_body), "problems": render.validate(t.subject, t.body),
            "project_id": (ev.project or {}).get("project_id"), "project_name": (ev.project or {}).get("project_name"),
            "empty": [v for v in used if not str(ev.ctx.get(v) or "").strip()],
            "level": alerts.template_level(t),
            "to": members(db, list(t.to_groups or []), (ev.project or {}).get("cluster"), alerts.template_level(t)),
            "cc": members(db, list(t.cc_groups or []), (ev.project or {}).get("cluster"), alerts.template_level(t))}


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
    if (row.template_key or "").startswith("account_"):
        # Its logged copy has the password masked: reset the password instead.
        raise ValueError("Sign-in emails cannot be resent - reset the user's password to send a new one")
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
                          triggered_by=f"{who} (resend)", created_at=datetime.utcnow(), level=row.level,
                          alert_id=row.alert_id if status in ("sent", "test") else None)
    db.add(log)
    db.commit()
    return {"status": status, "detail": detail, "log_id": log.id}


# ── Sends that something in Akasha causes ───────────────────────────────────

_notify_lock = threading.Lock()


def notify_date_changes(cause: str) -> None:
    """Send the schedule-change email now - after a sync or an edit in
    Akasha - instead of waiting for the daily run. Only when email is on and
    the template is switched on; never raises (the sync or save has already
    succeeded)."""
    from database import SessionLocal
    if not settings().enabled:
        return
    with _notify_lock:      # two quick edits must not both send the same change
        db = SessionLocal()
        try:
            t = db.get(models.EmailTemplate, "date_change")
            if t and t.enabled:
                r = run(db, triggered_by=cause, only=["date_change"])
                logger.info(f"Email after {cause}: {r.get('message')}")
        except Exception:  # noqa: BLE001
            logger.exception(f"Email after {cause} failed")
        finally:
            db.close()


def _approval_event(d: "Data", a, key: str) -> Event:
    """An approval's email context: the project's figures plus exactly what
    was asked - the month, the quantity, the phases in it."""
    p = d.project(a.project_id) or {"project_name": a.project_name, "project_id": a.project_id}
    ctx = d.context(p, True)
    phases = list(a.phases or [])
    labels = [x.get("phase_label") or "" for x in phases]
    ctx.update({
        "phase": ", ".join(l for l in labels if l.strip().lower() not in C.UNPHASED),
        "module_quantity_mwp": C.mw(a.mwp), "order_month": a.month,
        "module_ordering_date": ", ".join(x.get("order_date") or "" for x in phases if x.get("order_date")),
        "tc_delivery_date": ", ".join(x.get("tc_date") or "" for x in phases if x.get("tc_date")),
        "ftc_date": ", ".join(x.get("ftc_date") or "" for x in phases if x.get("ftc_date")) or ctx.get("ftc_date", ""),
        "requested_by": a.requested_by_name or a.requested_by, "request_note": a.request_note or "No note",
        "approval_status": a.status.title(),
    })
    return Event(key, ctx, p, ctx["phase"], case_key=f"approval:{a.id}")


def send_approval_request(db: Session, a, who: str) -> dict:
    """The approval email for a request, to the template's groups (TC Head)
    with the requester on Cc; it opens the alert approvers decide on."""
    t = db.get(models.EmailTemplate, "approval_request")
    if not t:
        seed_templates(db)
        t = db.get(models.EmailTemplate, "approval_request")
    d = Data(db)
    ev = _approval_event(d, a, f"approval:{a.id}:request")
    # Users holding the TC Head role for the portfolio are approvers too.
    from services import order_approvals
    ev.extra_to = order_approvals.role_users(db, order_approvals.APPROVER_ROLE, (ev.project or {}).get("cluster"))
    if a.requested_by_email:
        ev.extra_cc = [a.requested_by_email]
    return deliver(db, t, ev, d, f"{who} (approval request)")


def send_approval_decision(db: Session, a, who: str) -> dict:
    """Approved or returned: to TC Ordering and the requester."""
    t = db.get(models.EmailTemplate, "approval_decision")
    if not t:
        seed_templates(db)
        t = db.get(models.EmailTemplate, "approval_decision")
    d = Data(db)
    ev = _approval_event(d, a, f"approval:{a.id}:{a.status}")
    ev.case_key = None
    approved = a.status == "approved"
    ev.ctx.update({
        "approval_decision": "Approved" if approved else "Returned",
        "approved_by": a.decided_by_name or a.decided_by or "",
        "approval_date": (a.decided_at + C.IST).strftime("%d-%b-%y %H:%M IST") if a.decided_at else "",
        "decision_note": a.decision_note or "No remarks",
        "approval_next_step": (f"Required Action: TC Ordering to raise the PO. {C.mw(a.mwp)} MWp stays frozen in {a.month} "
                               f"in the Ordering Schedule until the PO is in SAP.") if approved else
                              "Required Action: Read the remarks, then raise a fresh request from the Ordering Schedule if it is still needed.",
    })
    if a.requested_by_email:
        ev.extra_to = [a.requested_by_email]
    return deliver(db, t, ev, d, f"{who} (approval {a.status})")
