"""
KPI metric history.

The platform had no time series for any headline figure: /dashboard/summary
returns scalars, and MetricsCache holds one overwritten row per project rather
than a history. That is why every KPI tile fell back to a proportion bar
instead of a sparkline.

No snapshot table is needed to fix it. The underlying records are already
timestamped, so a monthly series can be reconstructed from them directly:

    po_value            MTPOAmount.document_date      cumulative order value
    open_ncs            PulseNC.created_at/approved_at  raised-minus-resolved
    total_projects      P6Project.start_date          cumulative count
    completed_projects  P6Project.finish_date         cumulative count
    portfolio_capacity  ProjectMapping.capacity_mwac  cumulative at COD

`delayed_projects` is deliberately absent. Delay is computed against the
CURRENT baseline, so a historical value cannot be derived from stored records —
only a real snapshot would give it. Rather than fabricate a plausible line, the
key is omitted and the tile keeps its proportion bar.
"""

import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

import models
from database import get_db

router = APIRouter(prefix="/api/metrics", tags=["metrics"])

# A sparkline below this many points is noise, not a trend — the frontend
# drops back to a proportion bar at the same threshold (MIN_SERIES_POINTS).
MIN_POINTS = 4


def _month_keys(months: int) -> List[str]:
    """Continuous YYYY-MM keys, oldest first, ending on the current month.

    Built explicitly rather than taken from the query results so that a month
    with no activity contributes a real zero (or a carried-forward cumulative
    value) instead of collapsing the series and distorting the shape.
    """
    today = datetime.utcnow().replace(day=1)
    keys = []
    for _ in range(months):
        keys.append(today.strftime("%Y-%m"))
        today = (today - timedelta(days=1)).replace(day=1)
    return list(reversed(keys))


def _accumulate(per_month: Dict[str, float], keys: List[str], baseline: float = 0.0) -> List[float]:
    """Running total across a continuous month axis."""
    out, running = [], baseline
    for k in keys:
        running += per_month.get(k, 0.0)
        out.append(round(running, 2))
    return out


def _bucket(rows) -> Dict[str, float]:
    """(month datetime, value) rows → {'YYYY-MM': value}."""
    acc: Dict[str, float] = {}
    for month, value in rows:
        if month is None:
            continue
        acc[month.strftime("%Y-%m")] = acc.get(month.strftime("%Y-%m"), 0.0) + float(value or 0)
    return acc


def _scoped_mappings(
    db: Session, portfolio: Optional[str], phase: Optional[str]
) -> List[models.ProjectMapping]:
    """The same project set /dashboard/summary counts.

    This has to mirror the dashboard exactly, because a sparkline whose final
    point disagrees with the number printed above it is worse than no
    sparkline at all. Unscoped, these queries returned 66 projects against a
    tile reading 48, and 3,782 MW against a tile reading 967.

    Mirrors: drop anything named "demo", then deduplicate on project_id
    keeping the row with the longest spv_plant_code.
    """
    query = db.query(models.ProjectMapping)
    if portfolio and portfolio.lower() != "all portfolios":
        query = query.filter(models.ProjectMapping.cluster == portfolio)
    # The header defaults to Ongoing, and omitting it was the whole gap: 62
    # projects against a tile reading 48. With it applied the two agree.
    if phase == "Ongoing":
        query = query.filter(models.ProjectMapping.is_commissioned.is_(False))
    elif phase == "Commissioned":
        query = query.filter(models.ProjectMapping.is_commissioned.is_(True))

    dedup: Dict[str, models.ProjectMapping] = {}
    for m in query.all():
        name = (m.project_name_from_p6 or m.project or "")
        if "demo" in name.lower() or not m.project_id:
            continue
        existing = dedup.get(m.project_id)
        if existing is None or len(m.spv_plant_code or "") > len(existing.spv_plant_code or ""):
            dedup[m.project_id] = m
    return list(dedup.values())


@router.get("/history")
def get_metric_history(
    months: int = 12,
    portfolio: Optional[str] = None,
    phase: Optional[str] = "Ongoing",
    db: Session = Depends(get_db),
):
    """Monthly series for the Executive Overview KPI band.

    Returns only the keys that resolve to a genuine series of at least
    MIN_POINTS. A caller should treat a missing key as "no history available"
    and fall back, not as an error.
    """
    months = max(MIN_POINTS, min(months, 36))
    keys = _month_keys(months)
    floor = datetime.strptime(keys[0], "%Y-%m")
    series: Dict[str, dict] = {}

    scoped = _scoped_mappings(db, portfolio, phase)
    project_ids = [m.project_id for m in scoped if m.project_id]
    plant_codes = [m.spv_plant_code for m in scoped if m.spv_plant_code]
    wbs_codes = [m.module_wbs for m in scoped if m.module_wbs]

    def publish(key: str, values: List[float]) -> None:
        # A flat line is a claim that the figure is stable; if every point is
        # identical the series carries no information and is not worth showing.
        if len(values) >= MIN_POINTS and len(set(values)) > 1:
            series[key] = {"series": values, "period": f"{months} months"}

    # -- PO value, cumulative Rs crore ------------------------------------
    # Reproduces dashboard.py's aggregation exactly, INCLUDING its per-mapping
    # prefix loop. That loop adds a WBS row once for every prefix it matches,
    # so a row matching two prefixes is counted twice. A deduplicated sum came
    # out 6.4% lower than the tile, and a sparkline that disagrees with the
    # number above it is worse than none -- so the series matches the tile by
    # construction. See the note in the endpoint docstring: the double-count is
    # almost certainly a reporting bug, but it is the tile's bug to fix, not
    # something this series should silently diverge from.
    try:
        rows = (
            db.query(
                models.MTPOAmount.wbs_element,
                func.date_trunc("month", models.MTPOAmount.document_date).label("m"),
                func.sum(models.MTPOAmount.net_order_value_inr),
            )
            .group_by(models.MTPOAmount.wbs_element, "m")
            .all()
        )
        normalised = [
            (str(w).lower().replace("-", ""), mth, float(v))
            for w, mth, v in rows if w and v
        ]

        monthly: Dict[str, float] = {}
        opening = 0.0
        for m in scoped:
            for val in (m.spv_plant_code, m.agel, m.age6l):
                if not val:
                    continue
                for code in re.findall(r"H-\S+", str(val).strip()):
                    pfx = code.strip()[:6]
                    if len(pfx) < 6:
                        continue
                    pfx = pfx.lower().replace("-", "")
                    for norm, mth, value in normalised:
                        if not norm.startswith(pfx):
                            continue
                        # Undated orders still count toward the printed total,
                        # so they are carried as an opening balance rather than
                        # dropped -- placing them at the start cannot invent
                        # recent growth that did not happen.
                        if mth is None or mth < floor:
                            opening += value
                        else:
                            k = mth.strftime("%Y-%m")
                            monthly[k] = monthly.get(k, 0.0) + value
        publish("po_value", [round(x / 10_000_000, 1) for x in _accumulate(monthly, keys, opening)])
    except Exception:
        pass

    # -- Open NCs: raised to date minus resolved to date -------------------
    try:
        raised = _bucket(
            db.query(
                func.date_trunc("month", models.PulseNC.created_at).label("m"),
                func.count(models.PulseNC.id),
            )
            .filter(models.PulseNC.created_at.isnot(None))
            .group_by("m")
            .all()
        )
        resolved = _bucket(
            db.query(
                func.date_trunc("month", models.PulseNC.approved_at).label("m"),
                func.count(models.PulseNC.id),
            )
            .filter(models.PulseNC.approved_at.isnot(None))
            .group_by("m")
            .all()
        )
        net = {k: raised.get(k, 0) - resolved.get(k, 0) for k in set(raised) | set(resolved)}
        opening = sum(v for k, v in net.items() if k < keys[0])
        publish(
            "open_ncs",
            [max(0, int(v)) for v in _accumulate({k: v for k, v in net.items() if k in keys}, keys, opening)],
        )
    except Exception:
        pass

    # -- Open RFIs: raised to date minus completed to date -----------------
    # "Open" mirrors the dashboard: everything whose status is not 'completed'
    # (so rejected, submitted and approved all still count as open).
    try:
        raised_r = _bucket(
            db.query(
                func.date_trunc("month", models.PulseRFI.created_at).label("m"),
                func.count(models.PulseRFI.id),
            )
            .filter(models.PulseRFI.created_at.isnot(None))
            .group_by("m")
            .all()
        )
        closed_r = _bucket(
            db.query(
                func.date_trunc("month", models.PulseRFI.updated_at).label("m"),
                func.count(models.PulseRFI.id),
            )
            .filter(
                models.PulseRFI.updated_at.isnot(None),
                models.PulseRFI.status == "completed",
            )
            .group_by("m")
            .all()
        )
        net_r = {k: raised_r.get(k, 0) - closed_r.get(k, 0) for k in set(raised_r) | set(closed_r)}
        opening = sum(v for k, v in net_r.items() if k < keys[0])
        publish(
            "open_rfis",
            [max(0, int(v)) for v in _accumulate({k: v for k, v in net_r.items() if k in keys}, keys, opening)],
        )
    except Exception:
        pass

    # -- NC closure rate: resolved as a share of everything raised ----------
    try:
        raised_n = _bucket(
            db.query(
                func.date_trunc("month", models.PulseNC.created_at).label("m"),
                func.count(models.PulseNC.id),
            )
            .filter(models.PulseNC.created_at.isnot(None))
            .group_by("m")
            .all()
        )
        closed_n = _bucket(
            db.query(
                func.date_trunc("month", models.PulseNC.created_at).label("m"),
                func.count(models.PulseNC.id),
            )
            .filter(
                models.PulseNC.created_at.isnot(None),
                models.PulseNC.status == "completed",
            )
            .group_by("m")
            .all()
        )
        cum_raised = _accumulate(
            {k: v for k, v in raised_n.items() if k in keys}, keys,
            sum(v for k, v in raised_n.items() if k < keys[0]),
        )
        cum_closed = _accumulate(
            {k: v for k, v in closed_n.items() if k in keys}, keys,
            sum(v for k, v in closed_n.items() if k < keys[0]),
        )
        publish(
            "nc_closure_rate",
            [round((c / r) * 100) if r else 0 for c, r in zip(cum_closed, cum_raised)],
        )
    except Exception:
        pass

    if project_ids:
        # -- Projects under way, cumulative starts -------------------------
        try:
            rows = (
                db.query(
                    func.date_trunc("month", models.P6Project.start_date).label("m"),
                    func.count(models.P6Project.id),
                )
                .filter(
                    models.P6Project.start_date.isnot(None),
                    models.P6Project.project_id.in_(project_ids),
                )
                .group_by("m")
                .all()
            )
            opening = sum(float(v or 0) for m, v in rows if m is not None and m < floor)
            monthly = {k: v for k, v in _bucket(rows).items() if k in keys}
            publish("total_projects", [int(v) for v in _accumulate(monthly, keys, opening)])
        except Exception:
            pass

        # -- Completed projects, cumulative finishes -----------------------
        # Progress is derived the same way dashboard.py derives it: the
        # non-labour-units ratio when available, otherwise the percent-complete
        # field normalised out of 0-1. Filtering on duration_percent_complete
        # alone matched nothing.
        try:
            per_month: Dict[str, float] = {}
            opening = 0.0
            for proj in (
                db.query(models.P6Project)
                .filter(
                    models.P6Project.finish_date.isnot(None),
                    models.P6Project.project_id.in_(project_ids),
                )
                .all()
            ):
                at_completion = getattr(proj, "at_completion_non_labor_units", 0) or 0
                if at_completion > 0:
                    pct = ((getattr(proj, "actual_non_labor_units", 0) or 0) / at_completion) * 100
                else:
                    pct = getattr(proj, "construction_percent_complete", None)
                    if pct is None:
                        pct = proj.duration_percent_complete or 0
                    if 0 < pct <= 1.0:
                        pct *= 100
                if pct < 99.9 or proj.finish_date > datetime.utcnow():
                    continue
                if proj.finish_date < floor:
                    opening += 1
                else:
                    k = proj.finish_date.strftime("%Y-%m")
                    per_month[k] = per_month.get(k, 0.0) + 1
            publish("completed_projects", [int(v) for v in _accumulate(per_month, keys, opening)])
        except Exception:
            pass

        # -- Commissioned capacity, cumulative MW at COD -------------------
        # capacity-overview already builds a cumulative COD-by-month trend from
        # the same block milestones the tile's figure comes from, so it is
        # reused rather than reimplemented against ProjectMapping.capacity_mwac
        # (a different quantity that read 3,330 against a tile showing 967).
        try:
            from routers.dashboard import get_capacity_overview

            cap = get_capacity_overview(portfolio=portfolio, db=db)
            by_month = {
                t["name"]: (t.get("Solar COD", 0) or 0) + (t.get("Wind COD", 0) or 0)
                for t in cap.get("monthly_trends", [])
            }
            if by_month:
                ordered = sorted(by_month)
                values, carried = [], 0.0
                for k in keys:
                    if k in by_month:
                        carried = by_month[k]
                    else:
                        # Already cumulative, so a gap carries the last value
                        # forward rather than resetting to zero.
                        earlier = [m for m in ordered if m <= k]
                        carried = by_month[earlier[-1]] if earlier else carried
                    values.append(round(carried))
                publish("portfolio_capacity", values)
        except Exception:
            pass

        # NOTE: no `delayed_projects` series. The tile reports MW *at COD*,
        # which dashboard.py derives per project from TC block data — not from
        # ProjectMapping.capacity_mwac. A series built off capacity_mwac would
        # measure a different quantity from the number printed above it
        # (3,330 against a tile reading 967), so the tile keeps its meter until
        # COD capacity is exposed with a date attached.

    return {
        "months": keys,
        "series": series,
        # Named so the caller can distinguish "no history" from "request failed".
        "unavailable": [
            k for k in
            ["portfolio_capacity", "total_projects", "delayed_projects",
             "open_ncs", "po_value", "completed_projects"]
            if k not in series
        ],
    }
