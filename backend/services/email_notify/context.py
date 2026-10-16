"""Template values, built from the Ordering Schedule's own figures
(routers/module_deliveries.get_module_deliveries_summary - the live plan) so
an email can never say something the screen does not. Nothing is estimated:
a value Akasha does not have stays empty and reads "Not available".
Calculated dates (forecast TC / FTC) are labelled as calculations in the
variable catalogue and the templates.
"""
from collections import OrderedDict
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional
from urllib.parse import quote

from sqlalchemy.orm import Session

IST = timedelta(hours=5, minutes=30)
MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
UNPHASED = {"", "main", "project balance", "single phase"}


def parse_day(s) -> Optional[date]:
    """'17-Jun-26' (or 'Ph-I (75MW): 17-Jun-26 · ...' - the first date) -> date."""
    import re
    m = re.search(r"(\d{1,2})-([A-Za-z]{3})-(\d{2,4})", str(s or ""))
    if not m or m.group(2).title() not in MON:
        return None
    y = int(m.group(3))
    try:
        return date(2000 + y if y < 100 else y, MON.index(m.group(2).title()) + 1, int(m.group(1)))
    except ValueError:
        return None


def fmt_day(d: Optional[date]) -> str:
    return f"{d.day:02d}-{MON[d.month - 1]}-{str(d.year)[-2:]}" if d else ""


def mw(v) -> str:
    try:
        return f"{float(v):,.1f}"
    except (TypeError, ValueError):
        return ""


def now_ist() -> datetime:
    return datetime.utcnow() + IST


def today() -> date:
    return now_ist().date()


def data_dates(db: Session) -> Dict[str, str]:
    """When the P6 and SAP data behind an email were last refreshed."""
    from models import SyncLog
    out = {}
    p6 = (db.query(SyncLog).filter(SyncLog.source == "p6", SyncLog.status == "success")
          .order_by(SyncLog.finished_at.desc()).first())
    if p6 and p6.finished_at:
        out["p6_as_of"] = (p6.finished_at + IST).strftime("%d-%b-%y %H:%M IST")
    sap = (db.query(SyncLog).filter(SyncLog.source == "sharepoint", SyncLog.status == "success")
           .order_by(SyncLog.finished_at.desc()).first())
    if sap and (sap.data_as_on or sap.finished_at):
        out["sap_as_of"] = ((sap.data_as_on or sap.finished_at) + IST).strftime("%d-%b-%y")
    return out


def stage_summary(plan: Optional[dict]) -> str:
    """'Piling 100% · Capping 100% · Structure 80% · Module 45%' from the
    Advanced planning block stages (P6), when there are any."""
    stages = (plan or {}).get("stages") or []
    return " · ".join(f"{s.get('label')} {round(s.get('pct') or 0)}%" for s in stages if s.get("label"))


def ordering_status(p: dict) -> str:
    cap, ordered, bal = p.get("capacity_mwp") or 0, p.get("ordered_mwp") or 0, p.get("balance_ordering_mwp") or 0
    if ordered <= 0:
        return f"Not ordered - {mw(bal)} MWp to order"
    if bal <= 0:
        return f"Fully ordered ({mw(ordered)} MWp)"
    return f"Ordered {mw(ordered)} of {mw(cap)} MWp - {mw(bal)} MWp to order"


def risk_reason(p: dict, ph: Optional[dict] = None) -> str:
    """Why the schedule is at risk, from the Ordering Schedule's own checks."""
    out = []
    if ph:
        if ph.get("overdue"):
            out.append(f"ordering window passed on {ph.get('order_date')}")
        if ph.get("shifted"):
            out.append("moved out of its target month by the vendor allocation")
        if not ph.get("ftc_reachable", True):
            out.append(f"the P6 FTC {ph.get('ftc_date')} cannot be met from {ph.get('order_month')} "
                       f"({ph.get('ftc_short_days')} days short)")
    flags = set(p.get("planning_flags") or [])
    lta = parse_day(p.get("lta"))
    if "ftc_past_lta" in flags and lta:
        out.append(f"FTC lands after the LTA ({p.get('lta')})")
    if not out:
        return "On plan - the order can still meet the P6 FTC"
    s = "; ".join(out)
    return s[0].upper() + s[1:]


def project_context(p: dict, cfg, plan: Optional[dict] = None, dates: Optional[dict] = None) -> Dict:
    cap = p.get("capacity_mwp") or 0
    erected = p.get("erection_done_mwp") or 0
    pid = p.get("project_id") or p.get("p6_project_id") or ""
    base = cfg.public_url
    procurement = p.get("procurement") or {}
    pos = procurement.get("pos") or []
    vendors = list(OrderedDict.fromkeys(po.get("vendor") for po in pos if po.get("vendor")))
    ctx = {
        "project_name": p.get("project_name") or p.get("p6_name") or "",
        "project_id": pid,
        "portfolio": p.get("cluster") or "",
        "vendor_type": p.get("type") or "",
        "priority": (p.get("priority") or "standard").upper().replace("STANDARD", "Standard"),
        "capacity_mwp": mw(cap),
        "balance_ordering_mwp": mw(p.get("balance_ordering_mwp")),
        "ordered_mwp": mw(p.get("ordered_mwp")),
        "received_mwp": mw(p.get("total_receipt_mwp")),
        "in_transit_mwp": mw(p.get("under_transit_mwp")),
        # Received (SAP) minus erected (P6). Below zero the two systems
        # disagree - more erected than received - and there is no stock
        # figure to state, so it reads "Not available" rather than a negative.
        "on_site_stock_mwp": mw(p.get("module_inventory_mwp")) if (p.get("module_inventory_mwp") or 0) >= 0 else "",
        "erected_mwp": mw(erected),
        "erection_pct": f"{round(erected / cap * 100)}%" if cap else "",
        "construction_progress": stage_summary(plan),
        "module_ordering_date": (p.get("module_date") or ""),
        "tc_delivery_date": p.get("tc_date") or "",
        "ftc_date": p.get("ftc_date") or "",
        "lta_date": p.get("lta") or "",
        "scod_date": p.get("scod") or "",
        "ordering_status": ordering_status(p),
        "risk_reason": risk_reason(p),
        "vendor_name": ", ".join(vendors),
        "po_numbers": ", ".join(str(po.get("po")) for po in pos if po.get("po")),
        "awaiting_grn_mwp": mw(procurement.get("awaiting_grn_mwp")),
        "oldest_awaiting_days": procurement.get("oldest_awaiting_days") or "",
        "checklist_pending": max(0, (procurement.get("checklist_due") or 0) - (procurement.get("checklist_created") or 0)) or "",
        "akasha_link": base,
        "akasha_project_link": f"{base}/project/{quote(str(pid), safe='')}" if base and pid else "",
        "support_contact": cfg.support_contact,
        "generated_at": now_ist().strftime("%d-%b-%y %H:%M IST"),
    }
    ctx.update(dates or {})
    return ctx


def phases(p: dict) -> List[dict]:
    """The project's orders, one per (phase, planned order date), merging the
    months a vendor allocation split it across. Each carries the phase record
    fields plus the months it lands in."""
    groups: "OrderedDict[tuple, dict]" = OrderedDict()
    for mo, rows in (p.get("month_phases") or {}).items():
        for r in rows or []:
            key = (r.get("phase_label") or "", r.get("order_date") or "")
            g = groups.get(key)
            if not g:
                g = dict(r)
                g["months"] = [mo]
                groups[key] = g
            else:
                g["mwp"] = round((g.get("mwp") or 0) + (r.get("mwp") or 0), 1)
                g["months"].append(mo)
                g["overdue"] = g.get("overdue") or r.get("overdue")
                g["shifted"] = g.get("shifted") or r.get("shifted")
                g["ftc_reachable"] = g.get("ftc_reachable", True) and r.get("ftc_reachable", True)
                if (r.get("delay_months") or 0) > (g.get("delay_months") or 0):
                    for k in ("delay_months", "next_tc_date", "next_ftc_date", "order_month"):
                        g[k] = r.get(k)
                g["ftc_short_days"] = max(g.get("ftc_short_days") or 0, r.get("ftc_short_days") or 0)
    return list(groups.values())


def order_lines(p: dict, skip: Optional[dict] = None) -> str:
    """The project's orders still to place, soonest first - quantity and
    ordering date - leaving out `skip` (the order the email is about)."""
    rows = []
    for o in phases(p):
        if not (o.get("mwp") or 0) > 0:
            continue
        if skip is not None and (o.get("phase_label"), o.get("order_date")) == (skip.get("phase_label"), skip.get("order_date")):
            continue
        label = (o.get("phase_label") or "").strip()
        label = "" if label.lower() in UNPHASED else label
        rows.append((parse_day(o.get("order_date")) or date.max,
                     f"{label + ': ' if label else ''}{mw(o.get('mwp'))} MWp by {o.get('order_date') or 'a date not yet set'}"))
    rows.sort(key=lambda r: r[0])
    # Orders the LTA moved past the months on screen are still to place, later.
    for m in p.get("lta_moves") or []:
        if not m.get("to_in_view"):
            lab = (m.get("phase_label") or "").strip()
            lab = "" if lab.lower() in UNPHASED else lab
            rows.append((date.max, f"{lab + ': ' if lab else ''}{mw(m.get('mwp'))} MWp moved to {m.get('to_month')} for the LTA"))
    return "; ".join(text for _, text in rows) or "None - no further order is planned"


def lta_vs_basis(p: dict) -> Dict:
    """The LTA against the AOP, in words. Empty where either date is missing
    - no date is no signal. (Named for the basis the Ordering Schedule's own
    LTA flag uses, which is the SCOD for PPA contracts; the emails and the
    plan's LTA move use the AOP only.)"""
    lta, aop = parse_day(p.get("lta")), parse_day(p.get("aop_plan"))
    if not lta or not aop:
        return {}
    days = (lta - aop).days
    basis, when = "AOP", fmt_day(aop)
    n = abs(days)
    unit = "day" if n == 1 else "days"
    text = (f"{n} {unit} after the {basis} ({when})" if days > 0
            else f"{n} {unit} before the {basis} ({when})" if days < 0 else f"on the {basis} ({when})")
    return {"lta_basis": basis, "lta_basis_date": when, "lta_days_late": days, "lta_vs_basis": text,
            # for a table row: shown as a danger when the LTA is later than the AOP, with why
            "lta_vs_basis_flag": (f"!! {text} || Connectivity comes after the AOP: construction can finish, "
                                  f"but no power can flow before the LTA, so the AOP cannot be met unless the LTA comes forward."
                                  if days > 0 else text)}


def lta_order_note(p: dict) -> str:
    """What the LTA delay means for ordering: how much is not yet placed."""
    bal, ordered = p.get("balance_ordering_mwp") or 0, p.get("ordered_mwp") or 0
    if bal <= 0:
        return "Fully ordered - there is no order left to move"
    if ordered <= 0:
        return f"Nothing ordered yet - all {mw(bal)} MWp is still to be placed and need not be ordered for the earlier date"
    return f"{mw(ordered)} MWp already ordered; the remaining {mw(bal)} MWp is still to be placed and need not be ordered for the earlier date"


def phase_context(base: Dict, p: dict, ph: dict) -> Dict:
    label = (ph.get("phase_label") or "").strip()
    order = parse_day(ph.get("order_date"))
    t = today()
    delayed = (ph.get("delay_months") or 0) > 0
    ctx = dict(base)
    ctx.update({
        "phase": "" if label.lower() in UNPHASED else label,
        "module_quantity_mwp": mw(ph.get("mwp")),
        "module_ordering_date": ph.get("order_date") or "",
        "tc_delivery_date": ph.get("tc_date") or "",
        "ftc_date": ph.get("ftc_date") or base.get("ftc_date", ""),
        "revised_ordering_month": ph.get("order_month") or (ph.get("months") or [""])[-1],
        "forecast_tc_date": ph.get("next_tc_date") if delayed else ph.get("tc_date"),
        "forecast_ftc_date": ph.get("next_ftc_date") if delayed else ph.get("ftc_date"),
        "ftc_shortfall_days": ph.get("ftc_short_days") or 0,
        "days_to_ordering": (order - t).days if order and order >= t else "",
        "days_overdue": (t - order).days if order and order < t else "",
        "risk_reason": risk_reason(p, ph),
        # What is left once this order is placed, and what is still to come.
        "balance_after_order_mwp": (mw(max(0.0, float(p["balance_ordering_mwp"]) - float(ph.get("mwp") or 0)))
                                    if p.get("balance_ordering_mwp") is not None else ""),
        "remaining_orders": order_lines(p, ph),
    })
    return ctx
