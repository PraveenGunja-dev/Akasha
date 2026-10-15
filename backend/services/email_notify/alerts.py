"""Acknowledgement and escalation - one models.EmailAlert per thing someone
must act on, followed across every email about it.

Levels of intimation
  Every template goes out at a level (1-3, set per template in the admin
  console). An email at level N reaches each group member whose own level is
  N or lower, so L1 people hear everything and L3 people only the last step.
  Module ordering climbs with the calendar: 30 days before the ordering date
  L1, 15 days L2, 7 days L3 (catalogue.LEVEL_DEFAULT).

Acknowledgement holds the climb
  A To recipient acknowledges in Akasha (sign-in identifies them; the page
  needs a click, so a mail scanner opening the link acknowledges nothing)
  and records what is being done and the date they expect it done. While
  that expected date has not passed, the next email stays at the alert's
  current level instead of climbing ("held"). Acknowledging without a date,
  or letting the date pass, lets the next email escalate as scheduled.
  Once escalated, an alert never drops back: later emails keep the higher
  level's people informed.

Closing
  order      when the phase has nothing left to order in the Ordering
             Schedule - the PO is in SAP (checked on every run)
  condition  when the trigger no longer finds it (stock recovered, GRN
             posted, feed back up)
  one_off    when a To recipient acknowledges it
"""
from datetime import date, datetime
from typing import Iterable, List, Optional, Tuple

from sqlalchemy.orm import Session

import models
from . import catalogue, context as C


# ── Template settings ────────────────────────────────────────────────────────

def template_level(t) -> int:
    v = getattr(t, "level", None)
    if v is None:
        v = catalogue.LEVEL_DEFAULT.get(t.key, 1)
    return max(1, min(3, int(v)))


def due_stages(t) -> List[Tuple[int, int]]:
    """(level, days before the ordering date) for a module-ordering
    reminder, latest first: config {"levels": {"1": 30, "2": 15, "3": 7}}.
    An older single-stage config (days_before) is one stage at the
    template's level."""
    cfg = t.config or {}
    lv = cfg.get("levels")
    if isinstance(lv, dict):
        out = []
        for k, v in lv.items():
            try:
                L, n = int(k), int(v)
            except (TypeError, ValueError):
                continue
            if 1 <= L <= 3 and n >= 1:
                out.append((L, n))
        return sorted(out, key=lambda x: -x[1])
    return [(template_level(t), int(cfg.get("days_before", 30)))]


def overdue_steps(t) -> List[dict]:
    """The overdue reminders in day order; step 1 goes at L1, 2 at L2, 3+ at L3."""
    return sorted((t.config or {}).get("escalation") or catalogue.LEVELS, key=lambda x: int(x.get("after_days", 0)))


def ack_required(t) -> bool:
    v = getattr(t, "ack_required", None)
    return bool(v) if v is not None else t.key in catalogue.ACK_DEFAULT


def case_kind(t) -> str:
    if t.key == "approval_request":
        return "approval"         # closes when approved or returned (services/order_approvals.py)
    if t.trigger == "manual":
        return "one_off"
    return catalogue.CASE_KIND.get(t.trigger, "one_off")


def phase_id(label: Optional[str]) -> str:
    return (label or "").strip() or "main"


def case_key(t, ev) -> str:
    """Which alert an event belongs to. All module-ordering emails for a
    project phase (30 / 15 / 7 days, today, overdue) share one alert."""
    if case_kind(t) == "order":
        return f"order:{(ev.project or {}).get('project_id')}:{phase_id(ev.case_phase)}"
    return ev.case_key or ev.key


# ── Reading an alert ─────────────────────────────────────────────────────────

def find_open(db: Session, key: str, test: bool) -> Optional["models.EmailAlert"]:
    return (db.query(models.EmailAlert)
            .filter(models.EmailAlert.case_key == key, models.EmailAlert.status == "open",
                    models.EmailAlert.test.is_(test))
            .order_by(models.EmailAlert.id.desc()).first())


def late_commitment(a: "models.EmailAlert") -> bool:
    """A module order promised for after its ordering date: that is a late
    order, and must not keep the higher levels from hearing about it."""
    due = C.parse_day(a.due_date) if a.kind == "order" else None
    return bool(due and a.expected_date and a.expected_date.date() > due)


def holds(a: "models.EmailAlert", today: Optional[date] = None) -> bool:
    """Acknowledged with an expected date that has not passed (and, for a
    module order, is not after the ordering date)."""
    today = today or C.today()
    return bool(a.acknowledged_at and a.expected_date and a.expected_date.date() >= today
                and not late_commitment(a))


def _day(dt: Optional[datetime]) -> str:
    return C.fmt_day(dt.date()) if dt else ""


def decide(db: Session, t, ev, test: bool) -> Tuple[int, Optional["models.EmailAlert"], str, str]:
    """(level, open alert or None, what happens, why) for an email about
    to go out. What happens: sent / escalated / held."""
    base = max(template_level(t), int(ev.level or 1))
    if not ack_required(t):
        return base, None, "sent", ""
    a = find_open(db, case_key(t, ev), test)
    if not a:
        return base, None, "sent", ""
    current = a.level or 1
    if base <= current:
        return current, a, "sent", ""
    if holds(a):
        return current, a, "held", (
            f"Held at level {current}: {a.acknowledged_by} acknowledged on {_day(a.acknowledged_at)} and expects it done "
            f"by {_day(a.expected_date)}. It escalates if that date passes with the work still open.")
    if not a.acknowledged_at:
        why = f"Escalated to level {base}: not acknowledged at level {current} since {_day(a.opened_at)}."
    elif not a.expected_date:
        why = (f"Escalated to level {base}: acknowledged by {a.acknowledged_by} on {_day(a.acknowledged_at)} "
               f"with no expected date recorded.")
    elif late_commitment(a):
        why = (f"Escalated to level {base}: {a.acknowledged_by} expects the order on {_day(a.expected_date)}, "
               f"after the ordering date {a.due_date}.")
    else:
        why = (f"Escalated to level {base}: the expected date {_day(a.expected_date)} given by "
               f"{a.acknowledged_by} has passed with the work still open.")
    return base, a, "escalated", why


def ask_text(t) -> str:
    if case_kind(t) == "approval":
        return "Approvers (To): approve the order, or return it with remarks, in Akasha."
    if case_kind(t) == "one_off":
        return "To recipients: acknowledge this in Akasha so the team knows it has been seen."
    return ("To recipients: acknowledge in Akasha and record what is being done and the date you expect it done. "
            "Without an expected date, the next reminder goes to the next level.")


# ── Recording ────────────────────────────────────────────────────────────────

def ensure(db: Session, t, ev, level: int, test: bool) -> "models.EmailAlert":
    """The open alert for this event, created (and flushed, for its id) when
    this is the first email about it."""
    key = case_key(t, ev)
    a = find_open(db, key, test)
    if a:
        return a
    p = ev.project or {}
    a = models.EmailAlert(case_key=key, kind=case_kind(t), template_key=t.key, project_id=p.get("project_id"),
                          project_name=p.get("project_name") or ev.ctx.get("source_name"), phase=ev.phase or None,
                          due_date=ev.ctx.get("module_ordering_date") or None, level=level, status="open",
                          test=test, opened_at=datetime.utcnow(), emails=0)
    db.add(a)
    db.flush()
    return a


def discard_if_unsent(db: Session, a: "models.EmailAlert") -> None:
    """A brand-new alert whose first email did not go out is not an alert."""
    if a.emails == 0:
        db.query(models.EmailAlertEvent).filter(models.EmailAlertEvent.alert_id == a.id).delete()
        db.query(models.EmailAlertRecipient).filter(models.EmailAlertRecipient.alert_id == a.id).delete()
        db.delete(a)


def note_sent(db: Session, a: "models.EmailAlert", t, ev, level: int, what: str, why: str,
              to: Iterable[str], log_id: int, actor: str) -> None:
    now = datetime.utcnow()
    first = a.emails == 0
    a.template_key, a.level = t.key, max(a.level or 1, level)
    a.last_sent_at, a.emails = now, (a.emails or 0) + 1
    if ev.ctx.get("module_ordering_date"):
        a.due_date = ev.ctx["module_ordering_date"]
    have = {r.email.lower(): r for r in db.query(models.EmailAlertRecipient)
            .filter(models.EmailAlertRecipient.alert_id == a.id).all()}
    for addr in to:
        r = have.get(addr.lower())
        if r:
            r.last_sent_at = now
        else:
            db.add(models.EmailAlertRecipient(alert_id=a.id, email=addr, level=level, first_sent_at=now, last_sent_at=now))
    if first:
        db.add(models.EmailAlertEvent(alert_id=a.id, at=now, kind="opened", level=level, actor=actor,
                                      detail=f"First email: {t.name}"))
    db.add(models.EmailAlertEvent(alert_id=a.id, at=now, kind=what if not first else "sent", level=level,
                                  actor=actor, detail=why or t.name, log_id=log_id))


def resolve(db: Session, a: "models.EmailAlert", reason: str, actor: str = "Akasha") -> None:
    now = datetime.utcnow()
    a.status, a.resolved_at, a.resolved_reason = "resolved", now, reason
    db.add(models.EmailAlertEvent(alert_id=a.id, at=now, kind="resolved", level=a.level, actor=actor, detail=reason))


def close_finished(db: Session, d, ran_triggers: dict, found: set, test: bool) -> int:
    """Close open alerts whose work is done, from the data this run loaded.
    `ran_triggers` maps each trigger that ran cleanly to True; `found` is
    every case key the triggers produced (sent or not). Returns how many."""
    if not d.projects:
        return 0     # no Ordering Schedule loaded - never close on missing data
    from .engine import _orders
    n = 0
    templates = {t.key: t for t in db.query(models.EmailTemplate).all()}
    for a in (db.query(models.EmailAlert)
              .filter(models.EmailAlert.status == "open", models.EmailAlert.test.is_(test)).all()):
        reason = None
        if a.kind == "order":
            _, pid, ph = (a.case_key.split(":", 2) + ["", ""])[:3]
            p = d.project(pid)
            if not p:
                reason = "No longer in the Ordering Schedule's ongoing projects"
            elif (p.get("balance_ordering_mwp") or 0) <= 0:
                reason = "Fully ordered - the POs in SAP cover the project's capacity"
            elif ph not in {phase_id(o.get("phase_label")) for o in _orders(p)}:
                reason = "Nothing left to order for this phase in the Ordering Schedule - the PO is in SAP"
        elif a.kind == "condition":
            t = templates.get(a.template_key)
            if t and ran_triggers.get(t.trigger) and a.case_key not in found:
                reason = f"No longer applies - {t.name.lower()} is not found in the latest data"
        if reason:
            resolve(db, a, reason)
            n += 1
    return n


# ── What happens next ────────────────────────────────────────────────────────

def next_step(db: Session, a: "models.EmailAlert") -> Optional[str]:
    """The next thing that will happen to an open alert, in words - from the
    enabled templates' stages, so it is what the scheduler will really do."""
    if a.status != "open":
        return None
    if a.kind == "one_off":
        return "Closes when a To recipient acknowledges it"
    if a.kind == "approval":
        return "Waiting for an approver (To) to approve or return it"
    if a.kind == "condition":
        return "Closes on its own when the condition clears in the data"
    due = C.parse_day(a.due_date)
    if not due:
        return "Closes when the PO for this phase is in SAP"
    today = C.today()
    stages = []   # (date, level, name)
    for t in db.query(models.EmailTemplate).filter(models.EmailTemplate.enabled.is_(True),
                                                    models.EmailTemplate.trigger.in_(["ordering_due", "ordering_today", "ordering_overdue"])).all():
        lv = template_level(t)
        if t.trigger == "ordering_due":
            for L, n in due_stages(t):
                stages.append((due - _td(n), L, f"{t.name} ({n} days before)"))
        elif t.trigger == "ordering_today":
            stages.append((due, lv, t.name))
        else:
            for i, step in enumerate(overdue_steps(t), start=1):
                # overdue starts the day after the ordering date
                stages.append((due + _td(max(1, int(step.get("after_days", 0)))), max(lv, min(i, 3)), f"{t.name} ({step.get('label')})"))
    ahead = sorted((s for s in stages if s[0] > today), key=lambda s: (s[0], -s[1]))   # same day: the higher level
    if not ahead:
        return "No more reminders scheduled - closes when the PO for this phase is in SAP"
    when, lv, name = ahead[0]
    current = a.level or 1
    if lv <= current:
        return f"Next email {C.fmt_day(when)} at level {current}"
    if holds(a) and a.expected_date.date() >= when:
        return f"Next email {C.fmt_day(when)} stays at level {current} - held by the expected date {_day(a.expected_date)}"
    return f"Next email {C.fmt_day(when)} escalates to level {lv}"


def _td(days: int):
    from datetime import timedelta
    return timedelta(days=days)


# ── Acknowledging ────────────────────────────────────────────────────────────

def recipients(db: Session, a: "models.EmailAlert") -> List["models.EmailAlertRecipient"]:
    return (db.query(models.EmailAlertRecipient).filter(models.EmailAlertRecipient.alert_id == a.id)
            .order_by(models.EmailAlertRecipient.level, models.EmailAlertRecipient.first_sent_at).all())


def acknowledge(db: Session, a: "models.EmailAlert", recipient: "models.EmailAlertRecipient", name: str,
                note: Optional[str], expected: Optional[date], recorded_by: Optional[str] = None) -> None:
    """Record an acknowledgement (or a later update) by a To recipient,
    named `name`. With `recorded_by`, an administrator recorded it for the
    recipient (confirmed by phone, say) - the timeline says so."""
    now = datetime.utcnow()
    who = name if not recorded_by else f"{name} (recorded by {recorded_by})"
    first = not recipient.acknowledged_at
    if first:
        recipient.acknowledged_at = now
    new_level = (a.ack_level or 0) < (a.level or 1)
    if not a.acknowledged_at or new_level:
        a.acknowledged_at, a.acknowledged_by, a.ack_level = now, who, a.level
    if note is not None and note.strip():
        a.update_note = note.strip()
    if expected is not None:
        a.expected_date = datetime(expected.year, expected.month, expected.day)
    a.updated_at = now
    parts = []
    if note and note.strip():
        parts.append(note.strip())
    if expected:
        parts.append(f"expected by {C.fmt_day(expected)}")
    db.add(models.EmailAlertEvent(alert_id=a.id, at=now, kind="acknowledged" if (first or new_level) else "updated",
                                  level=a.level, actor=who, detail=" · ".join(parts) or None))
    if a.kind == "one_off" and a.status == "open":
        resolve(db, a, f"Acknowledged by {who}", actor=who)
