"""
SAP Intelligence Router — one filter model, every panel.

Every endpoint below takes the same SAPFilters and applies them the same way,
so the KPI row, trend chart, vendor bars, map, ledger and insights all answer
the same question at the same time. The screen used to assemble these from
five endpoints with five different notions of scope — one of which was a
1,000-row sample of an 88k-row table.

Book of record is ZSPS (mt_poamount): value columns reconcile exactly
(ordered = delivered + still-to-deliver). Quantity columns mix units and do
not reconcile; nothing here sums them across materials.

Attribution to project / cluster / state uses the WBS prefix (positions 3-6
of wbs_element, e.g. H-51ZQ-03-01 → 51ZQ) matched against every code column
on project_mapping — the same rule dashboard.py uses. Exact module_wbs match
covers 12% of PO value; the prefix rule covers 99.6%.

Known gaps, surfaced rather than papered over:
  · delivery_date is null on every row → no lateness, no lead time.
  · document_date is null on 42% of lines → period-over-period figures carry
    a `dated_share` so the reader knows what population they describe.
  · MB52 has no history → inventory is a snapshot; "cover" is derived from
    MB51 movement and labelled as such.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import requests
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, case, func, or_
from sqlalchemy.orm import Session

import models
from database import get_db

router = APIRouter(prefix="/api/sap")
logger = logging.getLogger(__name__)

CR = 10_000_000.0
PO = models.MTPOAmount
MB51 = models.MTMaterialDocument
MB52 = models.MTInventory
MAP = models.ProjectMapping

# Clusters resolve to states. Khavda, the wind sites (Mandvi, Mundra, Khavda
# WTG) and the BESS substations are all in Kutch, Gujarat; Bandha, Baiya and
# Ludbay are in Rajasthan. Two states is the truth of this portfolio.
CLUSTER_STATE = {
    "Solar Khavda": "Gujarat",
    "Wind": "Gujarat",
    "BESS": "Gujarat",
    "Solar Rajasthan": "Rajasthan",
}

# Where each cluster physically is, for the map. Khavda RE park and the
# Bhadla/Bandha belt come from the substation table the transmission map
# already uses (SUBSTATION_COORDS); Mandvi/Mundra is the wind belt on the
# Kutch coast. BESS units sit inside the Khavda park and are offset a few
# km so the two bubbles do not sit on top of each other. Cluster-level, not
# plot-level: ZSPS has no plot coordinates.
CLUSTER_COORDS = {
    "Solar Khavda": {"lat": 24.024, "lng": 69.337, "site": "Khavda RE Park, Kutch"},
    "BESS": {"lat": 23.80, "lng": 69.62, "site": "Khavda PSS (BESS), Kutch"},
    "Wind": {"lat": 22.83, "lng": 69.35, "site": "Mandvi / Mundra, Kutch"},
    "Solar Rajasthan": {"lat": 27.0, "lng": 74.2, "site": "Bandha / Baiya, Rajasthan"},
}

_CACHE: Dict[str, Tuple[float, object]] = {}
_TTL = 300


def _cached(key: str, build):
    hit = _CACHE.get(key)
    if hit and time.time() - hit[0] < _TTL:
        return hit[1]
    val = build()
    _CACHE[key] = (time.time(), val)
    return val


# ─────────────────────────────────────────────────────────────────────────────
# Attribution: WBS prefix → mapping row
# ─────────────────────────────────────────────────────────────────────────────

def _prefix_index(db: Session) -> Dict[str, List[dict]]:
    """prefix (4 chars) → [ {cluster, state, project, project_id} ]"""
    def build():
        idx: Dict[str, List[dict]] = {}
        for m in db.query(MAP).all():
            info = {
                "cluster": m.cluster or None,
                "state": CLUSTER_STATE.get(m.cluster or "", None),
                "project": m.project_name_from_p6,
                "project_id": m.project_id,
                "category": m.category,
            }
            for val in (m.spv_plant_code, m.agel, m.age6l, m.module_wbs):
                if not val:
                    continue
                for code in re.findall(r"H-?\s*([A-Za-z0-9]+)", str(val)):
                    idx.setdefault(code.upper()[:4], []).append(info)
        return idx
    return _cached("prefix_index", build)


def _prefixes_where(index: Dict[str, List[dict]], pred) -> List[str]:
    return [p for p, rows in index.items() if any(pred(r) for r in rows)]


WBS_PREFIX = func.substr(func.upper(PO.wbs_element), 3, 4)


# ─────────────────────────────────────────────────────────────────────────────
# Filters
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SAPFilters:
    portfolio: Optional[str] = None
    project: Optional[str] = None
    state: Optional[str] = None
    cluster: Optional[str] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    vendor: Optional[str] = None
    material: Optional[str] = None
    status: Optional[str] = None
    q: Optional[str] = None
    codes: List[str] = field(default_factory=list)

    @property
    def scoped(self) -> bool:
        return any([self.portfolio, self.project, self.state, self.cluster, self.vendor,
                    self.material, self.status, self.q, self.codes, self.date_from, self.date_to])


def parse_filters(
    portfolio: Optional[str] = None,
    project: Optional[str] = None,
    state: Optional[str] = None,
    cluster: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    vendor: Optional[str] = None,
    material: Optional[str] = None,
    status: Optional[str] = None,
    q: Optional[str] = None,
    codes: Optional[str] = None,
) -> SAPFilters:
    def d(s):
        if not s:
            return None
        try:
            return datetime.fromisoformat(s[:10])
        except ValueError:
            raise HTTPException(400, f"bad date {s!r}; expected YYYY-MM-DD")

    norm = lambda v: None if not v or v.lower() in ("all", "all portfolios", "all projects", "all vendors", "all materials") else v
    return SAPFilters(
        portfolio=norm(portfolio), project=norm(project), state=norm(state), cluster=norm(cluster),
        date_from=d(date_from), date_to=d(date_to),
        vendor=norm(vendor), material=norm(material), status=norm(status), q=(q or "").strip() or None,
        codes=[c.strip() for c in (codes or "").split(",") if c.strip()],
    )


LINE_STATUS = case(
    (PO.deletion_indicator.isnot(None), "cancelled"),
    (PO.delivery_completed_flag == "X", "delivered"),
    (func.coalesce(PO.delivered_qty, 0) > 0, "partial"),
    else_="pending",
)


def apply_filters(query, f: SAPFilters, db: Session, *, dates: bool = True):
    idx = _prefix_index(db)

    if f.portfolio:
        pf = f.portfolio.lower()
        prefixes = _prefixes_where(idx, lambda r: (r["cluster"] or "").lower().find(pf) >= 0 or (r["category"] or "").lower().find(pf) >= 0)
        query = query.filter(WBS_PREFIX.in_(prefixes or ["__none__"]))
    if f.project:
        prefixes = _prefixes_where(idx, lambda r: r["project"] == f.project or r["project_id"] == f.project)
        query = query.filter(WBS_PREFIX.in_(prefixes or ["__none__"]))
    if f.state:
        prefixes = _prefixes_where(idx, lambda r: r["state"] == f.state)
        query = query.filter(WBS_PREFIX.in_(prefixes or ["__none__"]))
    if f.cluster:
        prefixes = _prefixes_where(idx, lambda r: r["cluster"] == f.cluster)
        query = query.filter(WBS_PREFIX.in_(prefixes or ["__none__"]))
    if f.codes:
        conds = []
        for c in f.codes:
            for v in {c, c[2:] if c.upper().startswith("H-") else c}:
                conds.append(PO.plant_code.ilike(f"%{v}%"))
                conds.append(PO.wbs_element.ilike(f"%{v}%"))
        query = query.filter(or_(*conds))
    if f.vendor:
        query = query.filter(func.coalesce(PO.vendor_name, "") == ("" if f.vendor == "(no vendor recorded)" else f.vendor))
    if f.material:
        query = query.filter(PO.material_code == f.material)
    if f.status:
        query = query.filter(LINE_STATUS == f.status)
    if f.q:
        like = f"%{f.q}%"
        query = query.filter(or_(
            PO.purchasing_document.ilike(like), PO.vendor_name.ilike(like), PO.material_code.ilike(like),
            PO.material_name.ilike(like), PO.short_text.ilike(like), PO.buyer_name.ilike(like), PO.wbs_element.ilike(like),
        ))
    if dates and f.date_from:
        query = query.filter(PO.document_date >= f.date_from)
    if dates and f.date_to:
        query = query.filter(PO.document_date < f.date_to + timedelta(days=1))
    return query


def _filter_dep(
    portfolio: Optional[str] = None, project: Optional[str] = None, state: Optional[str] = None,
    cluster: Optional[str] = None, date_from: Optional[str] = None, date_to: Optional[str] = None,
    vendor: Optional[str] = None, material: Optional[str] = None, status: Optional[str] = None,
    q: Optional[str] = None, codes: Optional[str] = None,
) -> SAPFilters:
    return parse_filters(portfolio, project, state, cluster, date_from, date_to, vendor, material, status, q, codes)


def _cr(v) -> float:
    return round(float(v or 0) / CR, 2)


def _pct(num, den) -> float:
    return round(float(num) * 100.0 / float(den), 1) if den else 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Overview
# ─────────────────────────────────────────────────────────────────────────────

def _totals(db: Session, f: SAPFilters, *, dates=True) -> dict:
    q = apply_filters(db.query(
        func.count(func.distinct(PO.purchasing_document)),
        func.count(func.distinct(func.nullif(PO.vendor_name, ""))),
        func.count(func.distinct(PO.material_code)),
        func.sum(PO.net_order_value_inr),
        func.sum(PO.delivered_value_inr_cr),
        func.count(PO.id),
        func.count(PO.document_date),
    ), f, db, dates=dates)
    pos, vendors, materials, ordered, delivered_cr, lines, dated = q.first()
    ordered_cr = _cr(ordered)
    delivered_cr = round(float(delivered_cr or 0), 2)
    return {
        "pos": pos or 0, "vendors": vendors or 0, "materials": materials or 0,
        "ordered_cr": ordered_cr, "delivered_cr": delivered_cr,
        "outstanding_cr": round(max(ordered_cr - delivered_cr, 0), 2),
        "delivered_pct": _pct(delivered_cr, ordered_cr),
        "lines": lines or 0, "dated_lines": dated or 0,
    }


@router.get("/overview")
def sap_overview(f: SAPFilters = Depends(_filter_dep), db: Session = Depends(get_db)):
    now = _totals(db, f)

    # Previous period on document_date only. If the caller gave no range, the
    # comparison is trailing-12-months vs the 12 before — and it says so.
    if f.date_from and f.date_to:
        span = (f.date_to - f.date_from) + timedelta(days=1)
        cur_from, cur_to = f.date_from, f.date_to
    else:
        cur_to = db.query(func.max(PO.document_date)).scalar() or datetime.utcnow()
        span = timedelta(days=365)
        cur_from = cur_to - span + timedelta(days=1)
    prev_f = SAPFilters(**{**f.__dict__, "date_from": cur_from - span, "date_to": cur_from - timedelta(days=1)})
    cur_f = SAPFilters(**{**f.__dict__, "date_from": cur_from, "date_to": cur_to})
    cur = _totals(db, cur_f)
    prev = _totals(db, prev_f)

    def delta(k):
        a, b = cur[k], prev[k]
        return {"current": a, "previous": b, "pct": round((a - b) * 100.0 / b, 1) if b else None}

    # Status mix by line
    status_rows = apply_filters(db.query(LINE_STATUS, func.count(PO.id)), f, db).group_by(LINE_STATUS).all()

    # Inventory: MB52 snapshot, scoped by the same WBS prefixes when a scope is set
    inv_q = db.query(func.sum(MB52.quantity_inv), func.sum(MB52.value_unrestricted))
    if f.portfolio or f.project or f.state or f.cluster:
        idx = _prefix_index(db)
        pred = (lambda r: True)
        if f.state:
            pred = lambda r, s=f.state: r["state"] == s
        elif f.cluster:
            pred = lambda r, c=f.cluster: r["cluster"] == c
        elif f.project:
            pred = lambda r, p=f.project: r["project"] == p or r["project_id"] == p
        elif f.portfolio:
            pf = f.portfolio.lower(); pred = lambda r, pf=pf: (r["cluster"] or "").lower().find(pf) >= 0
        prefixes = _prefixes_where(idx, pred) or ["__none__"]
        inv_q = inv_q.filter(func.substr(func.upper(MB52.wbs_element), 3, 4).in_(prefixes))
    inv_qty, inv_val = inv_q.first()

    # Consumption (MB51 issues, negative quantities) inside the date range
    con_q = db.query(func.sum(MB51.amount_in_lc), func.sum(MB51.quantity)).filter(MB51.quantity < 0)
    if f.date_from:
        con_q = con_q.filter(MB51.posting_date >= f.date_from)
    if f.date_to:
        con_q = con_q.filter(MB51.posting_date < f.date_to + timedelta(days=1))
    con_val, con_qty = con_q.first()

    synced = db.query(func.max(PO.upload_time)).scalar()

    return {
        "kpis": {
            **now,
            "volume_qty": None,  # quantities mix units; not shown as a total
            "inventory_qty": float(inv_qty or 0),
            "inventory_value_cr": _cr(inv_val),
            "consumed_value_cr": round(abs(float(con_val or 0)) / CR, 2),
        },
        "period": {
            "current": [cur_from.date().isoformat(), cur_to.date().isoformat()],
            "previous": [prev_f.date_from.date().isoformat(), prev_f.date_to.date().isoformat()],
            "basis": "document_date",
            "dated_share": _pct(now["dated_lines"], now["lines"]),
            "pos": delta("pos"), "ordered_cr": delta("ordered_cr"), "vendors": delta("vendors"),
        },
        "status_mix": {s: n for s, n in status_rows},
        "synced_at": synced.isoformat() if synced else None,
        "source": {"pos": "ZSPS (mt_poamount)", "inventory": "MB52 (mt_inventory)", "consumption": "MB51 (mt_materialdocument)"},
    }


# ─────────────────────────────────────────────────────────────────────────────
# Trends
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/trends")
def sap_trends(
    granularity: str = Query("month", pattern="^(month|quarter|year)$"),
    f: SAPFilters = Depends(_filter_dep), db: Session = Depends(get_db),
):
    trunc = {"month": "month", "quarter": "quarter", "year": "year"}[granularity]
    key = lambda d: d.strftime("%Y-%m") if granularity == "month" else (f"{d.year}-Q{(d.month - 1) // 3 + 1}" if granularity == "quarter" else str(d.year))

    po_q = apply_filters(db.query(
        func.date_trunc(trunc, PO.document_date).label("b"),
        func.sum(PO.net_order_value_inr), func.count(func.distinct(PO.purchasing_document)),
        func.sum(PO.delivered_value_inr_cr),
    ).filter(PO.document_date.isnot(None)), f, db).group_by("b").all()

    mb_q = db.query(
        func.date_trunc(trunc, MB51.posting_date).label("b"),
        func.sum(case((MB51.quantity < 0, MB51.amount_in_lc), else_=0)),
        func.sum(case((MB51.quantity < 0, MB51.quantity), else_=0)),
        func.sum(case((MB51.quantity > 0, MB51.quantity), else_=0)),
    ).filter(MB51.posting_date.isnot(None))
    if f.date_from:
        mb_q = mb_q.filter(MB51.posting_date >= f.date_from)
    if f.date_to:
        mb_q = mb_q.filter(MB51.posting_date < f.date_to + timedelta(days=1))
    mb_rows = mb_q.group_by("b").all()

    buckets: Dict[str, dict] = {}
    def get(b):
        k = key(b)
        return buckets.setdefault(k, {"bucket": k, "ordered_cr": 0.0, "pos": 0, "delivered_cr": 0.0,
                                      "consumed_cr": 0.0, "consumed_qty": 0.0, "reversal_qty": 0.0})
    for b, val, n, deliv in po_q:
        if b is None: continue
        r = get(b); r["ordered_cr"] += _cr(val); r["pos"] += n or 0; r["delivered_cr"] += round(float(deliv or 0), 2)
    for b, cval, cqty, rqty in mb_rows:
        if b is None: continue
        r = get(b); r["consumed_cr"] += round(abs(float(cval or 0)) / CR, 2)
        r["consumed_qty"] += abs(float(cqty or 0)); r["reversal_qty"] += float(rqty or 0)

    series = [buckets[k] for k in sorted(buckets) if k >= "2022"]
    # Inventory position reconstructed backwards from the MB52 snapshot (no dates in MB52).
    inv_total = float(db.query(func.sum(MB52.quantity_inv)).scalar() or 0)
    running = inv_total
    for r in reversed(series):
        r["inventory_qty"] = round(running, 2)
        running -= (r["reversal_qty"] - r["consumed_qty"])
    for i, r in enumerate(series):
        r["utilisation_pct"] = _pct(r["delivered_cr"], r["ordered_cr"])
        prev = series[i - 1] if i else None
        r["ordered_change_pct"] = round((r["ordered_cr"] - prev["ordered_cr"]) * 100.0 / prev["ordered_cr"], 1) if prev and prev["ordered_cr"] else None
        for k in ("ordered_cr", "delivered_cr", "consumed_cr", "consumed_qty", "reversal_qty"):
            r[k] = round(r[k], 2)

    return {"granularity": granularity, "series": series, "events": _detect_events(series), "inventory_total_qty": inv_total}


def _detect_events(series: List[dict]) -> List[dict]:
    """Rule-based: a bucket whose change from the trailing-6 mean exceeds 2σ
    and a floor. Labelled 'rules' so the UI never calls this AI."""
    out = []
    specs = [
        ("ordered_cr", "PO surge", "PO drop", 50.0),
        ("consumed_cr", "Consumption spike", "Consumption drop", 20.0),
        ("reversal_qty", "Reversal spike", None, 1000.0),
    ]
    for k, up, down, floor in specs:
        vals = [r[k] for r in series]
        for i in range(6, len(vals)):
            window = vals[i - 6:i]
            mean = sum(window) / 6
            sd = (sum((v - mean) ** 2 for v in window) / 6) ** 0.5
            v = vals[i]
            if sd == 0 or abs(v) < floor:
                continue
            z = (v - mean) / sd
            if z > 2 and up:
                out.append({"bucket": series[i]["bucket"], "series": k, "kind": "up", "label": up, "value": v, "baseline": round(mean, 2), "z": round(z, 1), "source": "rules"})
            elif z < -2 and down:
                out.append({"bucket": series[i]["bucket"], "series": k, "kind": "down", "label": down, "value": v, "baseline": round(mean, 2), "z": round(z, 1), "source": "rules"})
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Vendors
# ─────────────────────────────────────────────────────────────────────────────

VENDOR_NAME = func.coalesce(func.nullif(func.trim(PO.vendor_name), ""), "(no vendor recorded)")


def _vendor_rows(db, f, limit=None):
    q = apply_filters(db.query(
        VENDOR_NAME, func.sum(PO.net_order_value_inr), func.sum(PO.delivered_value_inr_cr),
        func.count(func.distinct(PO.purchasing_document)), func.count(func.distinct(PO.material_code)),
        func.max(PO.document_date),
    ), f, db).group_by(VENDOR_NAME)
    rows = []
    for name, ordered, deliv, pos, mats, last in q.all():
        o = _cr(ordered); d = round(float(deliv or 0), 2)
        if o <= 0: continue
        rows.append({"name": name, "ordered_cr": o, "delivered_cr": d, "outstanding_cr": round(max(o - d, 0), 2),
                     "delivered_pct": _pct(d, o), "pos": pos, "materials": mats, "last_po": last.date().isoformat() if last else None})
    rows.sort(key=lambda r: -r["ordered_cr"])
    total = sum(r["ordered_cr"] for r in rows) or 1
    out_total = sum(r["outstanding_cr"] for r in rows) or 1
    for r in rows:
        r["share_pct"] = _pct(r["ordered_cr"], total)
        r["outstanding_share_pct"] = _pct(r["outstanding_cr"], out_total)
    return rows[:limit] if limit else rows, len(rows)


@router.get("/vendors")
def sap_vendors(limit: int = 10, f: SAPFilters = Depends(_filter_dep), db: Session = Depends(get_db)):
    rows, n = _vendor_rows(db, f, limit if limit > 0 else None)
    return {"vendors": rows, "vendor_count": n}


@router.get("/vendors/{name}")
def sap_vendor_detail(name: str, f: SAPFilters = Depends(_filter_dep), db: Session = Depends(get_db)):
    vf = SAPFilters(**{**f.__dict__, "vendor": name})
    tot = _totals(db, vf)
    mats = apply_filters(db.query(PO.material_code, func.max(PO.material_name), func.sum(PO.net_order_value_inr), func.sum(PO.delivered_value_inr_cr)), vf, db) \
        .group_by(PO.material_code).order_by(func.sum(PO.net_order_value_inr).desc()).limit(8).all()
    projects = apply_filters(db.query(WBS_PREFIX, func.sum(PO.net_order_value_inr)), vf, db).group_by(WBS_PREFIX).all()
    idx = _prefix_index(db)
    proj_map: Dict[str, float] = {}
    for pre, val in projects:
        rows = idx.get(pre or "", [])
        label = rows[0]["project"] if rows and rows[0]["project"] else "(unattributed)"
        proj_map[label] = proj_map.get(label, 0) + _cr(val)
    recent = apply_filters(db.query(PO.purchasing_document, func.max(PO.document_date), func.sum(PO.net_order_value_inr), func.sum(PO.delivered_value_inr_cr), func.count(PO.id)), vf, db) \
        .group_by(PO.purchasing_document).order_by(func.max(PO.document_date).desc().nullslast()).limit(8).all()
    trend = sap_trends("quarter", vf, db)["series"][-8:]
    return {
        "name": name, **tot,
        "top_materials": [{"code": c, "name": n, "ordered_cr": _cr(o), "delivered_cr": round(float(d or 0), 2)} for c, n, o, d in mats],
        "projects": sorted([{"project": k, "ordered_cr": round(v, 2)} for k, v in proj_map.items()], key=lambda r: -r["ordered_cr"]),
        "recent_pos": [{"po": p, "date": d.date().isoformat() if d else None, "ordered_cr": _cr(o), "delivered_cr": round(float(dv or 0), 2), "lines": n} for p, d, o, dv, n in recent],
        "trend": trend,
        "not_available": ["average_delivery_time", "delayed_pos"],  # delivery_date is null on every row
    }


# ─────────────────────────────────────────────────────────────────────────────
# Materials
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/materials")
def sap_materials(by: str = Query("value", pattern="^(value|outstanding|consumption|inventory)$"), limit: int = 10,
                  f: SAPFilters = Depends(_filter_dep), db: Session = Depends(get_db)):
    # Blank material codes carry 46% of PO value (₹30.7k Cr over ~5k POs).
    # They are grouped as one bucket and named for what they are, rather than
    # inheriting whichever material_name max() happened to pick.
    MAT_CODE = func.coalesce(func.nullif(func.trim(PO.material_code), ""), "(no material code)")
    q = apply_filters(db.query(
        MAT_CODE, func.max(func.coalesce(PO.material_name, PO.short_text)),
        func.sum(PO.net_order_value_inr), func.sum(PO.delivered_value_inr_cr),
        func.count(func.distinct(PO.purchasing_document)), func.count(func.distinct(func.nullif(PO.vendor_name, ""))),
    ), f, db).group_by(MAT_CODE)
    rows = {}
    for code, name, ordered, deliv, pos, vendors in q.all():
        o = _cr(ordered); d = round(float(deliv or 0), 2)
        if code == "(no material code)":
            name = "(no material code)"
        rows[code] = {"code": code, "name": name or code, "ordered_cr": o, "delivered_cr": d, "outstanding_cr": round(max(o - d, 0), 2),
                      "delivered_pct": _pct(d, o), "pos": pos, "vendors": vendors, "consumed_cr": 0.0, "inventory_qty": 0.0, "inventory_value_cr": 0.0}
    if rows:
        codes = list(rows)
        for code, val in db.query(MB51.material_code, func.sum(MB51.amount_in_lc)).filter(MB51.material_code.in_(codes), MB51.quantity < 0).group_by(MB51.material_code).all():
            rows[code]["consumed_cr"] = round(abs(float(val or 0)) / CR, 2)
        for code, qty, val in db.query(MB52.material_code, func.sum(MB52.quantity_inv), func.sum(MB52.value_unrestricted)).filter(MB52.material_code.in_(codes)).group_by(MB52.material_code).all():
            rows[code]["inventory_qty"] = float(qty or 0); rows[code]["inventory_value_cr"] = _cr(val)
    keyf = {"value": "ordered_cr", "outstanding": "outstanding_cr", "consumption": "consumed_cr", "inventory": "inventory_value_cr"}[by]
    blank = rows.pop("(no material code)", None)
    out = sorted(rows.values(), key=lambda r: -r[keyf])
    return {"by": by, "materials": out[:limit], "material_count": len(out), "no_material_code": blank}


@router.get("/materials/{code}")
def sap_material_detail(code: str, f: SAPFilters = Depends(_filter_dep), db: Session = Depends(get_db)):
    mf = SAPFilters(**{**f.__dict__, "material": code})
    tot = _totals(db, mf)
    name = db.query(func.max(func.coalesce(PO.material_name, PO.short_text))).filter(PO.material_code == code).scalar()
    suppliers = apply_filters(db.query(VENDOR_NAME, func.sum(PO.net_order_value_inr), func.sum(PO.delivered_value_inr_cr), func.count(func.distinct(PO.purchasing_document))), mf, db) \
        .group_by(VENDOR_NAME).order_by(func.sum(PO.net_order_value_inr).desc()).limit(8).all()
    cons = db.query(func.date_trunc("month", MB51.posting_date), func.sum(MB51.amount_in_lc), func.sum(MB51.quantity)) \
        .filter(MB51.material_code == code, MB51.quantity < 0, MB51.posting_date.isnot(None)).group_by(func.date_trunc("month", MB51.posting_date)).order_by(func.date_trunc("month", MB51.posting_date)).all()
    inv = db.query(func.sum(MB52.quantity_inv), func.sum(MB52.value_unrestricted), func.max(MB52.base_unit)).filter(MB52.material_code == code).first()
    projects = apply_filters(db.query(WBS_PREFIX, func.sum(PO.net_order_value_inr)), mf, db).group_by(WBS_PREFIX).all()
    idx = _prefix_index(db); proj_map: Dict[str, float] = {}
    for pre, val in projects:
        rows = idx.get(pre or "", []); label = rows[0]["project"] if rows and rows[0]["project"] else "(unattributed)"
        proj_map[label] = proj_map.get(label, 0) + _cr(val)
    # Unit price per PO line (value / qty) — spread, not a "price trend": no dates on 42% of lines
    prices = apply_filters(db.query(PO.net_order_value_inr, PO.order_quantity, PO.document_date), mf, db).filter(PO.order_quantity > 0).order_by(PO.document_date.asc().nullsfirst()).all()
    unit = [{"date": d.date().isoformat() if d else None, "unit_price": round(float(v or 0) / float(q), 2)} for v, q, d in prices if q]
    return {
        "code": code, "name": name or code, **tot,
        "suppliers": [{"name": n, "ordered_cr": _cr(o), "delivered_cr": round(float(d or 0), 2), "pos": p} for n, o, d, p in suppliers],
        "consumption": [{"month": m.strftime("%Y-%m"), "value_cr": round(abs(float(v or 0)) / CR, 2), "qty": abs(float(q or 0))} for m, v, q in cons if m],
        "inventory": {"qty": float(inv[0] or 0), "value_cr": _cr(inv[1]), "unit": inv[2]},
        "projects": sorted([{"project": k, "ordered_cr": round(v, 2)} for k, v in proj_map.items()], key=lambda r: -r["ordered_cr"]),
        "unit_prices": unit[-60:],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Geography
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/geography")
def sap_geography(f: SAPFilters = Depends(_filter_dep), db: Session = Depends(get_db)):
    idx = _prefix_index(db)
    rows = apply_filters(db.query(WBS_PREFIX, func.sum(PO.net_order_value_inr), func.sum(PO.delivered_value_inr_cr), func.count(func.distinct(PO.purchasing_document))), f, db).group_by(WBS_PREFIX).all()
    states: Dict[str, dict] = {}
    clusters: Dict[str, dict] = {}
    unattributed = {"ordered_cr": 0.0, "pos": 0, "reason": {}}
    for pre, val, deliv, pos in rows:
        cands = idx.get(pre or "", [])
        cl_set = {r["cluster"] for r in cands if r["cluster"]}
        o = _cr(val); d = round(float(deliv or 0), 2)
        if not cands:
            unattributed["ordered_cr"] += o; unattributed["pos"] += pos; unattributed["reason"]["no mapping row"] = unattributed["reason"].get("no mapping row", 0) + o; continue
        if len(cl_set) != 1:
            k = "prefix shared by clusters" if len(cl_set) > 1 else "mapping row has no cluster"
            unattributed["ordered_cr"] += o; unattributed["pos"] += pos; unattributed["reason"][k] = unattributed["reason"].get(k, 0) + o; continue
        cl = next(iter(cl_set)); st = CLUSTER_STATE.get(cl)
        c = clusters.setdefault(cl, {"cluster": cl, "state": st, "ordered_cr": 0.0, "delivered_cr": 0.0, "pos": 0})
        c["ordered_cr"] += o; c["delivered_cr"] += d; c["pos"] += pos
        if st:
            s = states.setdefault(st, {"state": st, "ordered_cr": 0.0, "delivered_cr": 0.0, "pos": 0})
            s["ordered_cr"] += o; s["delivered_cr"] += d; s["pos"] += pos
    for coll in (states, clusters):
        for r in coll.values():
            r["ordered_cr"] = round(r["ordered_cr"], 2); r["delivered_cr"] = round(r["delivered_cr"], 2)
            r["outstanding_cr"] = round(max(r["ordered_cr"] - r["delivered_cr"], 0), 2); r["delivered_pct"] = _pct(r["delivered_cr"], r["ordered_cr"])

    # Coordinates and trailing-12-month change per cluster (document_date
    # only, so labelled as such on the client).
    end = db.query(func.max(PO.document_date)).scalar() or datetime.utcnow()
    span = timedelta(days=365)
    for cl, r in clusters.items():
        r.update(CLUSTER_COORDS.get(cl, {"lat": None, "lng": None, "site": None}))
        cf = SAPFilters(**{**f.__dict__, "cluster": cl, "date_from": end - span + timedelta(days=1), "date_to": end})
        pf = SAPFilters(**{**f.__dict__, "cluster": cl, "date_from": end - 2 * span + timedelta(days=1), "date_to": end - span})
        cur = _totals(db, cf)["ordered_cr"]; prev = _totals(db, pf)["ordered_cr"]
        r["change_pct"] = round((cur - prev) * 100.0 / prev, 1) if prev else None
        r["change_basis"] = "PO value, trailing 12 months vs prior 12, dated lines only"
    unattributed["ordered_cr"] = round(unattributed["ordered_cr"], 2)
    unattributed["reason"] = {k: round(v, 2) for k, v in unattributed["reason"].items()}
    return {"states": sorted(states.values(), key=lambda r: -r["ordered_cr"]),
            "clusters": sorted(clusters.values(), key=lambda r: -r["ordered_cr"]),
            "unattributed": unattributed,
            "basis": "WBS prefix → project_mapping → cluster → state"}


# ─────────────────────────────────────────────────────────────────────────────
# Ledger
# ─────────────────────────────────────────────────────────────────────────────

SORTABLE = {
    "po": PO.purchasing_document, "buyer": PO.buyer_name, "vendor": PO.vendor_name, "material": PO.material_code,
    "date": PO.document_date, "value": PO.net_order_value_inr, "delivered": PO.delivered_value_inr_cr, "status": LINE_STATUS,
}


def _line(r) -> dict:
    o = _cr(r.net_order_value_inr); d = round(float(r.delivered_value_inr_cr or 0), 2)
    st = "cancelled" if r.deletion_indicator else "delivered" if r.delivery_completed_flag == "X" else "partial" if (r.delivered_qty or 0) > 0 else "pending"
    return {
        "id": r.id, "po": r.purchasing_document, "buyer": r.buyer_name, "vendor": (r.vendor_name or "").strip() or None,
        "material_code": r.material_code, "material": r.material_name or r.short_text, "short_text": r.short_text,
        "date": r.document_date.date().isoformat() if r.document_date else None,
        "delivery_date": None,  # null on every ZSPS row
        "status": st, "ordered_cr": o, "delivered_cr": d, "outstanding_cr": round(max(o - d, 0), 2),
        "qty": r.order_quantity, "delivered_qty": r.delivered_qty, "wbs": r.wbs_element, "plant": r.plant_code, "storage": r.storage_location,
    }


@router.get("/pos")
def sap_pos(page: int = 1, size: int = Query(25, le=200), sort: str = "value", order: str = Query("desc", pattern="^(asc|desc)$"),
            f: SAPFilters = Depends(_filter_dep), db: Session = Depends(get_db)):
    base = apply_filters(db.query(PO), f, db)
    total = base.with_entities(func.count(PO.id)).scalar()
    col = SORTABLE.get(sort, PO.net_order_value_inr)
    ob = col.desc().nullslast() if order == "desc" else col.asc().nullsfirst()
    rows = base.order_by(ob, PO.id).offset((page - 1) * size).limit(size).all()
    return {"rows": [_line(r) for r in rows], "total": total, "page": page, "size": size}


@router.get("/pos/{po}")
def sap_po_detail(po: str, db: Session = Depends(get_db)):
    lines = db.query(PO).filter(PO.purchasing_document == po).order_by(PO.id).all()
    if not lines:
        raise HTTPException(404, f"PO {po} not found")
    items = [_line(r) for r in lines]
    o = round(sum(i["ordered_cr"] for i in items), 2); d = round(sum(i["delivered_cr"] for i in items), 2)
    sts = {i["status"] for i in items}
    status = "cancelled" if sts == {"cancelled"} else "delivered" if sts <= {"delivered", "cancelled"} else "partial" if ("delivered" in sts or "partial" in sts) else "pending"
    idx = _prefix_index(db)
    pres = {(l.wbs_element or "").upper()[2:6] for l in lines}
    projects = sorted({r["project"] for p in pres for r in idx.get(p, []) if r["project"]})
    consumed = db.query(func.sum(MB51.amount_in_lc)).filter(MB51.purchase_order == po, MB51.quantity < 0).scalar()
    dates = [l.document_date for l in lines if l.document_date]
    return {
        "po": po, "buyer": next((l.buyer_name for l in lines if l.buyer_name), None), "vendor": next(((l.vendor_name or "").strip() for l in lines if l.vendor_name), None),
        "date": min(dates).date().isoformat() if dates else None, "status": status,
        "ordered_cr": o, "delivered_cr": d, "outstanding_cr": round(max(o - d, 0), 2), "delivered_pct": _pct(d, o),
        "consumed_cr": round(abs(float(consumed or 0)) / CR, 2), "projects": projects, "lines": items,
        "materials": sorted({i["material_code"] for i in items if i["material_code"]}),
        "not_available": ["expected_delivery"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Search, filter options
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/search")
def sap_search(q: str = Query(..., min_length=2), limit: int = 8, db: Session = Depends(get_db)):
    like = f"%{q}%"
    out = []
    for po, in db.query(PO.purchasing_document).filter(PO.purchasing_document.ilike(like)).distinct().limit(limit):
        out.append({"type": "po", "id": po, "label": po})
    for v, in db.query(PO.vendor_name).filter(PO.vendor_name.ilike(like)).distinct().limit(limit):
        out.append({"type": "vendor", "id": v, "label": v})
    for c, n in db.query(PO.material_code, func.max(func.coalesce(PO.material_name, PO.short_text))).filter(or_(PO.material_code.ilike(like), PO.material_name.ilike(like), PO.short_text.ilike(like))).group_by(PO.material_code).limit(limit):
        out.append({"type": "material", "id": c, "label": f"{c} · {n}" if n else c})
    for b, in db.query(PO.buyer_name).filter(PO.buyer_name.ilike(like)).distinct().limit(limit):
        out.append({"type": "buyer", "id": b, "label": b})
    for p, in db.query(MAP.project_name_from_p6).filter(MAP.project_name_from_p6.ilike(like)).distinct().limit(limit):
        out.append({"type": "project", "id": p, "label": p})
    return {"q": q, "results": out}


@router.get("/filters")
def sap_filter_options(db: Session = Depends(get_db)):
    def build():
        clusters = [c for c, in db.query(MAP.cluster).filter(MAP.cluster.isnot(None), MAP.cluster != "").distinct().order_by(MAP.cluster)]
        projects = [{"id": pid, "name": n} for pid, n in db.query(MAP.project_id, MAP.project_name_from_p6).filter(MAP.project_name_from_p6.isnot(None)).order_by(MAP.project_name_from_p6)]
        vendors = [v for v, in db.query(VENDOR_NAME).group_by(VENDOR_NAME).order_by(func.sum(PO.net_order_value_inr).desc()).limit(200)]
        dmin, dmax = db.query(func.min(PO.document_date), func.max(PO.document_date)).first()
        return {"portfolios": clusters, "states": sorted({s for s in CLUSTER_STATE.values()}), "projects": projects, "vendors": vendors,
                "statuses": ["pending", "partial", "delivered", "cancelled"],
                "date_min": dmin.date().isoformat() if dmin else None, "date_max": dmax.date().isoformat() if dmax else None}
    return _cached("filters", build)


# ─────────────────────────────────────────────────────────────────────────────
# Insights — rule-based, with optional AI enrichment that is labelled as such
# ─────────────────────────────────────────────────────────────────────────────

def _insight(id, category, severity, title, summary, *, metric=None, current=None, previous=None, impact=None,
             vendors=None, materials=None, pos=None, recommendation=None, evidence=None):
    return {"id": id, "category": category, "severity": severity, "title": title, "summary": summary, "metric": metric,
            "currentValue": current, "previousValue": previous, "impact": impact, "affectedVendors": vendors or [],
            "affectedMaterials": materials or [], "affectedPOs": pos or [], "recommendation": recommendation,
            "evidence": evidence or {}, "createdAt": datetime.utcnow().isoformat(), "source": "rules"}


def build_insights(db: Session, f: SAPFilters) -> List[dict]:
    ov = sap_overview(f, db)
    k, p = ov["kpis"], ov["period"]
    vendors, _ = _vendor_rows(db, f)
    out: List[dict] = []

    # 1. PO creation vs previous period (dated lines only)
    d = p["ordered_cr"]
    if d["pct"] is not None and d["previous"] > 0 and abs(d["pct"]) >= 10:
        up = d["pct"] > 0
        out.append(_insight("po-period", "procurement", "warning" if abs(d["pct"]) >= 40 else "info",
            f"PO value {'up' if up else 'down'} {abs(d['pct']):.0f}% vs previous period",
            f"₹{d['current']:,.0f} Cr ordered {p['current'][0]} → {p['current'][1]}, against ₹{d['previous']:,.0f} Cr in the preceding period. Based on document_date, present on {p['dated_share']:.0f}% of lines.",
            metric="ordered_cr", current=d["current"], previous=d["previous"],
            recommendation="Confirm the change is planned procurement, not timing of PO entry." if up else "Check whether procurement slowed or PO entry is lagging.",
            evidence={"period": p}))

    # 2. Vendor concentration
    if vendors:
        top5 = sum(v["share_pct"] for v in vendors[:5])
        if top5 >= 50:
            out.append(_insight("vendor-conc", "vendor", "warning" if top5 >= 70 else "info",
                f"Top 5 vendors hold {top5:.0f}% of PO value",
                f"{', '.join(v['name'] for v in vendors[:3])} lead. Concentration this high makes delivery on the portfolio hostage to a handful of counterparties.",
                metric="share_pct", current=top5, vendors=[v["name"] for v in vendors[:5]],
                recommendation="Review alternates for the largest outstanding lines with these vendors.",
                evidence={"top5": vendors[:5]}))

    # 3. Outstanding exposure concentration
    outstanding = sorted(vendors, key=lambda v: -v["outstanding_cr"])
    if outstanding and k["outstanding_cr"] > 0:
        o1 = outstanding[0]
        if o1["outstanding_share_pct"] >= 25:
            out.append(_insight("outstanding-conc", "risk", "warning",
                f"₹{o1['outstanding_cr']:,.0f} Cr still to deliver from {o1['name']}",
                f"{o1['outstanding_share_pct']:.0f}% of all outstanding PO value (₹{k['outstanding_cr']:,.0f} Cr) sits with one vendor at {o1['delivered_pct']:.0f}% delivered.",
                metric="outstanding_cr", current=o1["outstanding_cr"], vendors=[o1["name"]],
                recommendation="Get a delivery schedule for the open lines and track it weekly.",
                evidence={"vendor": o1}))

    # 4. Large vendors with nothing delivered
    zero = [v for v in vendors if v["delivered_pct"] == 0 and v["ordered_cr"] >= 500 and v["name"] != "(no vendor recorded)"]
    if zero:
        out.append(_insight("zero-delivery", "risk", "critical" if zero[0]["ordered_cr"] >= 2000 else "warning",
            f"{len(zero)} vendor{'s' if len(zero) > 1 else ''} above ₹500 Cr with 0% delivered",
            f"{zero[0]['name']} has ₹{zero[0]['ordered_cr']:,.0f} Cr on order and nothing recorded as delivered" + (f"; {len(zero) - 1} more in the same position." if len(zero) > 1 else "."),
            metric="delivered_pct", current=0, vendors=[v["name"] for v in zero],
            recommendation="Confirm whether these are new POs or delivery postings are missing in ZSPS.",
            evidence={"vendors": zero[:5]}))

    # 5. No vendor recorded
    nov = next((v for v in vendors if v["name"] == "(no vendor recorded)"), None)
    if nov and nov["ordered_cr"] >= 100:
        out.append(_insight("no-vendor", "data-quality", "warning",
            f"₹{nov['ordered_cr']:,.0f} Cr across {nov['pos']:,} POs has no vendor recorded",
            f"These lines cannot be attributed to a counterparty, so vendor exposure and concentration are understated by this amount.",
            metric="ordered_cr", current=nov["ordered_cr"], pos=[],
            recommendation="Fix vendor master on these POs at source; until then treat vendor figures as a floor.",
            evidence={"vendor": nov}))

    # 6. Consumption trend, last 3 months vs prior 3 (MB51)
    tr = sap_trends("month", SAPFilters(**{**f.__dict__, "date_from": None, "date_to": None}), db)["series"]
    if len(tr) >= 6:
        last3 = sum(r["consumed_cr"] for r in tr[-3:]); prev3 = sum(r["consumed_cr"] for r in tr[-6:-3])
        if prev3 > 0:
            chg = (last3 - prev3) * 100.0 / prev3
            if abs(chg) >= 25:
                out.append(_insight("consumption", "inventory", "warning" if chg < 0 else "info",
                    f"Site consumption {'down' if chg < 0 else 'up'} {abs(chg):.0f}% over the last three months",
                    f"₹{last3:,.0f} Cr issued to site in {tr[-3]['bucket']}–{tr[-1]['bucket']} vs ₹{prev3:,.0f} Cr in the three months before (MB51).",
                    metric="consumed_cr", current=round(last3, 1), previous=round(prev3, 1),
                    recommendation="A consumption drop with steady deliveries means stock is accumulating at site." if chg < 0 else "Check inventory cover keeps pace with the higher burn.",
                    evidence={"last3": tr[-3:], "prev3": tr[-6:-3]}))
        # 7. Inventory cover
        avg_burn = sum(r["consumed_qty"] for r in tr[-6:]) / 6
        if avg_burn > 0 and k["inventory_qty"] > 0:
            months = k["inventory_qty"] / avg_burn
            out.append(_insight("inv-cover", "inventory", "warning" if months > 12 else "info",
                f"Inventory on hand ≈ {months:.1f} months of consumption",
                f"MB52 holds {k['inventory_qty']:,.0f} units (₹{k['inventory_value_cr']:,.0f} Cr) against an average {avg_burn:,.0f} units/month issued over the last six months. Quantity-based; units differ across materials, so read as an order of magnitude.",
                metric="inventory_months", current=round(months, 1),
                recommendation="Slow further receipts on materials with the longest cover." if months > 12 else None,
                evidence={"inventory_qty": k["inventory_qty"], "avg_burn": avg_burn}))
        # 8. Reversal spike in the last bucket
        ev = [e for e in _detect_events(tr) if e["series"] == "reversal_qty"][-1:]
        if ev and ev[0]["bucket"] == tr[-1]["bucket"]:
            out.append(_insight("reversals", "inventory", "warning", f"Reversal spike in {ev[0]['bucket']}",
                f"{ev[0]['value']:,.0f} units reversed against a trailing baseline of {ev[0]['baseline']:,.0f}.",
                metric="reversal_qty", current=ev[0]["value"], previous=ev[0]["baseline"],
                recommendation="Reversals at this scale usually mean wrong postings or returns; check the material documents.", evidence=ev[0]))

    # 9. Materials carrying the outstanding
    mres = sap_materials("outstanding", 5, f, db)
    mats = mres["materials"]
    nomat = mres.get("no_material_code")
    if nomat and nomat["ordered_cr"] >= 1000:
        out.append(_insight("no-material-code", "data-quality", "warning",
            f"₹{nomat['ordered_cr']:,.0f} Cr across {nomat['pos']:,} POs has no material code",
            f"{_pct(nomat['ordered_cr'], k['ordered_cr']):.0f}% of PO value cannot be analysed by material. Material-level exposure below describes only the coded lines.",
            metric="ordered_cr", current=nomat["ordered_cr"],
            recommendation="Service and expense POs are expected here; anything that is physical supply should carry a code.", evidence={"bucket": nomat}))
    if mats and k["outstanding_cr"] > 0:
        share = sum(m["outstanding_cr"] for m in mats) * 100.0 / k["outstanding_cr"]
        if share >= 40:
            out.append(_insight("material-outstanding", "material", "info",
                f"Five materials account for {share:.0f}% of outstanding value",
                f"{mats[0]['name']} alone is ₹{mats[0]['outstanding_cr']:,.0f} Cr still to deliver.",
                metric="outstanding_cr", current=round(share, 1), materials=[m["code"] for m in mats],
                recommendation="These are the lines whose slippage moves the portfolio; track them by name.", evidence={"materials": mats}))

    # 10. Undated lines
    if p["dated_share"] < 80:
        out.append(_insight("undated", "data-quality", "info",
            f"{100 - p['dated_share']:.0f}% of PO lines carry no document date",
            "Period-over-period comparisons and the trend chart describe only the dated lines.",
            metric="dated_share", current=p["dated_share"], recommendation=None, evidence={"lines": k["lines"], "dated": k["dated_lines"]}))

    sev_rank = {"critical": 0, "warning": 1, "info": 2, "success": 3}
    out.sort(key=lambda i: sev_rank[i["severity"]])
    return out


def _ollama() -> Tuple[str, Optional[str]]:
    """(base_url, model). Follows the project's .env (OLLAMA_ENDPOINT is the
    OpenAI-style /v1 URL; OLLAMA_MODEL the preferred model). If the preferred
    model is not pulled — .env says llama3.1, the box has qwen2.5:3b — use
    the first model Ollama actually reports, so the feature works with what
    is installed rather than failing on a name."""
    import os
    def build():
        base = (os.getenv("OLLAMA_BASE_URL") or os.getenv("OLLAMA_ENDPOINT") or "http://localhost:11434").rstrip("/")
        if base.endswith("/v1"):
            base = base[:-3]
        want = os.getenv("OLLAMA_MODEL", "")
        try:
            names = [m.get("name", "") for m in requests.get(f"{base}/api/tags", timeout=3).json().get("models", [])]
        except Exception:  # noqa: BLE001
            return base, None
        if not names:
            return base, None
        pick = next((n for n in names if want and (n == want or n.split(":")[0] == want.split(":")[0])), names[0])
        if want and pick != want:
            logger.warning(f"OLLAMA_MODEL={want!r} is not pulled; using {pick!r}")
        return base, pick
    hit = _CACHE.get("ollama")
    if hit and time.time() - hit[0] < 60:
        return hit[1]  # type: ignore[return-value]
    val = build(); _CACHE["ollama"] = (time.time(), val)
    return val


def _enrich_with_ai(insights: List[dict]) -> List[dict]:
    """Ask the local model for a one-line 'why this matters'. Only the field
    it writes is marked as AI; the numbers stay rule-derived. Any failure
    leaves the insight untouched."""
    base, model = _ollama()
    if not model:
        return insights
    for ins in insights[:5]:
        prompt = (f"You are an infrastructure procurement analyst. In one sentence (max 30 words), say why this matters to a CEO. "
                  f"Do not repeat the numbers.\nInsight: {ins['title']}\nDetail: {ins['summary']}")
        try:
            r = requests.post(f"{base}/api/generate", json={"model": model, "prompt": prompt, "stream": False, "options": {"num_predict": 60}}, timeout=40)
            txt = (r.json().get("response") or "").strip()
            if txt:
                ins["aiNote"] = txt; ins["aiSource"] = model
        except Exception as e:  # noqa: BLE001
            logger.info(f"insight enrichment skipped: {e}")
            break
    return insights


@router.get("/insights")
def sap_insights(enrich: bool = False, f: SAPFilters = Depends(_filter_dep), db: Session = Depends(get_db)):
    key = f"insights:{enrich}:{sorted(f.__dict__.items())!r}"
    def build():
        ins = build_insights(db, f)
        return _enrich_with_ai(ins) if enrich else ins
    return {"insights": _cached(key, build), "generatedAt": datetime.utcnow().isoformat()}


# ─────────────────────────────────────────────────────────────────────────────
# Ask Akasha (SAP-scoped)
# ─────────────────────────────────────────────────────────────────────────────

from pydantic import BaseModel  # noqa: E402


class AskRequest(BaseModel):
    question: str
    context: dict = {}
    history: List[dict] = []


@router.post("/ask")
def sap_ask(req: AskRequest):
    """Grounded Q&A over the dashboard context the client sends (filters, KPIs,
    top vendors/materials, insights) — never the whole table. Uses the local
    model directly; the general /api/chat orchestrator streams and is not
    scoped to SAP."""
    import json
    base, model = _ollama()
    if not model:
        raise HTTPException(503, "AI backend unavailable: Ollama is not reachable or has no models")
    ctx = json.dumps(req.context, default=str)[:6000]
    hist = "\n".join(f"{m.get('role','user')}: {m.get('content','')}" for m in req.history[-6:])
    prompt = (
        "You are Akasha, an analyst for Adani Green's SAP procurement data. Answer ONLY from the context JSON. "
        "Quote figures with units (₹ Cr). If the context cannot answer, say what data would be needed. Be concise.\n\n"
        f"CONTEXT:\n{ctx}\n\nCONVERSATION:\n{hist}\nuser: {req.question}\nassistant:"
    )
    try:
        r = requests.post(f"{base}/api/generate", json={"model": model, "prompt": prompt, "stream": False, "options": {"num_predict": 300}}, timeout=150)
        r.raise_for_status()
        return {"answer": (r.json().get("response") or "").strip(), "model": model}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(503, f"AI backend unavailable: {e}")
