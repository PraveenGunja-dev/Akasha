"""
CPAG Solar PPTX builder.

Takes the approved template deck and injects live data from P6 + SAP into
the correct table cells while preserving all formatting.
"""
from collections import defaultdict
from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from pptx.util import Pt
from sqlalchemy import text
from sqlalchemy.orm import Session

from services.cpag_pptx import (
    _add_months, _light_gridlines, _mon, _move_to_line, _span_blanks,
    _p, _series_fill, LINE_GREEN, SERIES_BLUE, SERIES_GREEN, set_row,
)

REFERENCE = Path(__file__).resolve().parent.parent / "assets" / "cpag_solar_reference.pptx"

# The four phases on the template's "Overall S Curve" gap-analysis table
# (row order + weightage are the template's own pre-approved values - there
# is no other source of truth for how a solar CPAG pack should weight these
# phases, so we keep them rather than inventing a split, 2026-10-06).
SCURVE_ROW_ORDER = ["Land & Statutory", "Engineering+ System Study", "Procurement", "Construction"]
SCURVE_WEIGHTS = {"Land & Statutory": 7, "Engineering+ System Study": 13, "Procurement": 30, "Construction": 50}

# WBS names that mean "Land" outright (never a bare substring match - P6 wbs
# names like "CABLE ACCESSORIES - GLAND..." contain "LAND" as a substring of
# "GLAND" and would false-positive, 2026-10-06).
_LAND_EXACT_WBS = {"LAND", "GOVT LAND", "PVT LAND", "GOVERNMENT LAND"}
_CONSTRUCTION_EXACT_WBS = {
    "CIVIL WORKS", "CIVIL", "ELECTRICAL WORKS", "ELECTRIC WORKS",
    "TESTING AND COMMISSIONING", "TESTING & COMMISSIONIONG", "COMMISSIONING", "TESTING",
}


def _classify_wbs(wbs_name: Optional[str]) -> Optional[str]:
    up = (wbs_name or "").upper().strip()
    if up in _LAND_EXACT_WBS or "STATUTORY" in up:
        return "Land & Statutory"
    if "ENGINEERING" in up or "SYSTEM STUDY" in up:
        return "Engineering+ System Study"
    if "CONSTRUCTION" in up or up in _CONSTRUCTION_EXACT_WBS:
        return "Construction"
    if "PROCUREMENT" in up or "SUPPLY" in up or "LOGISTICS" in up or up in (
        "MODULE", "INVERTER", "LT PANEL", "HT PANEL", "HT PANEL INDOOR", 
        "POWER TRANSFORMER", "STATIC VAR GENRATOR", "EARTHING FLAT"
    ) or "CABLE" in up or "FASTNER" in up:
        return "Procurement"
    return None


def _solar_project_object_id(db: Session, p6_name: str) -> Optional[int]:
    """P6 keeps duplicate project rows per name from repeat imports; some are
    stale snapshots with zero activities. Picks the one that actually has
    activity data (2026-10-06)."""
    row = db.execute(text("""
        SELECT p6.p6_object_id
        FROM p6_project p6
        LEFT JOIN p6_activity a ON a.project_object_id = p6.p6_object_id
        WHERE p6.name = :name
        GROUP BY p6.p6_object_id
        ORDER BY count(a.id) DESC
        LIMIT 1
    """), {"name": p6_name}).fetchone()
    return row[0] if row else None


def _sap_procurement_pct(db: Session, module_wbs: Optional[str]) -> Optional[tuple]:
    """Point-in-time value delivered / value ordered from SAP PO data,
    joined via project_mapping.module_wbs (the codebase's established SAP
    link, per engine/variance.py compute_sap_variance). Not a time-phased
    figure: delivery_date is null on every mt_poamount row platform-wide, so
    no monthly procurement curve is possible. Despite the name, module_wbs
    resolves to the Modules package specifically (verified: Bandha's 3 PO
    lines are all "Modules Supply", while other wbs_element codes in the
    table carry 200-2,200 lines covering the full BOM) - so this is Module
    procurement, not whole-project procurement, and may only be a handful of
    POs. Returns (pct, po_count) so the caller can disclose coverage."""
    if not module_wbs:
        return None
    row = db.execute(text("""
        SELECT SUM(net_order_value_inr), SUM(delivered_value_inr_cr), COUNT(*)
        FROM mt_poamount WHERE wbs_element = :w
    """), {"w": module_wbs}).fetchone()
    if not row or not row[0]:
        return None
    ordered_cr = float(row[0]) / 1e7
    if ordered_cr <= 0:
        return None
    delivered_cr = float(row[1] or 0)
    return round(100 * delivered_cr / ordered_cr), int(row[2])


def _category_progress(acts: list, as_of: datetime):
    """Completed-activities/total, not mean(percent_complete) - the latter
    credits part-done work and reads ~23pts high (verified platform-wide)."""
    scope = len(acts)
    if not scope:
        return None
    completed = sum(1 for a in acts if a.status == "Completed")
    plan_count = sum(1 for a in acts if a.start_date and a.start_date <= as_of)
    return round(100 * plan_count / scope), round(100 * completed / scope)


def _gap_analysis(db: Session, acts: list, module_wbs: Optional[str], as_of: datetime) -> List[Dict[str, Any]]:
    buckets: Dict[str, list] = {k: [] for k in SCURVE_ROW_ORDER}
    for a in acts:
        cat = _classify_wbs(a.wbs_name)
        if cat:
            buckets[cat].append(a)

    rows = []
    plan_sum = plan_wt = act_sum = act_wt = 0.0
    for label in SCURVE_ROW_ORDER:
        weight = SCURVE_WEIGHTS[label]

        prog = _category_progress(buckets[label], as_of)
        if prog is None:
            rows.append({"label": label, "weight": weight, "plan": None, "actual": None,
                         "variance": None, "remark": ""})
            continue
        plan_pct, act_pct = prog
        plan_sum += plan_pct * weight
        plan_wt += weight
        act_sum += act_pct * weight
        act_wt += weight
        rows.append({"label": label, "weight": weight, "plan": plan_pct, "actual": act_pct,
                     "variance": plan_pct - act_pct, "remark": ""})

    overall_plan = round(plan_sum / plan_wt) if plan_wt else None
    overall_act = round(act_sum / act_wt) if act_wt else None
    overall_var = (overall_plan - overall_act) if (overall_plan is not None and overall_act is not None) else None
    # Remarks is reviewer/manual-entry territory (matches the template's own
    # convention) - left blank here, not auto-filled, per 2026-10-06 request.
    rows.append({"label": "Overall", "weight": 100, "plan": overall_plan, "actual": overall_act,
                 "variance": overall_var, "remark": ""})
    return rows


def _monthly_scurve(acts: list, as_of: datetime) -> List[Dict[str, Any]]:
    """Blended cumulative plan-vs-actual across every activity (all phases),
    counted by activity not mean(percent_complete), same convention as
    _category_progress. No per-phase monthly curve: Engineering and Land &
    Statutory have too few dated activities to plot a meaningful monthly
    series, and Procurement has none at all."""
    total = len(acts)
    starts = [a.start_date for a in acts if a.start_date]
    if not total or not starts:
        return []
    finishes = [a.actual_finish_date or a.finish_date for a in acts if (a.actual_finish_date or a.finish_date)]
    lo, hi = min(starts), (max(finishes) if finishes else max(starts))
    if hi < lo:
        hi = lo

    def mk(d):
        return (d.year, d.month)

    months = []
    y, m = lo.year, lo.month
    hy, hm = mk(hi)
    while (y, m) <= (hy, hm):
        months.append((y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1

    plan_m: Dict[tuple, int] = defaultdict(int)
    act_m: Dict[tuple, float] = defaultdict(float)
    for a in acts:
        if a.start_date:
            plan_m[mk(a.start_date)] += 1
        if a.status == "Completed" and a.actual_finish_date:
            act_m[mk(a.actual_finish_date)] += 1
        elif a.status == "In Progress" and a.actual_start_date:
            act_m[mk(a.actual_start_date)] += 0.5

    as_of_key = mk(as_of)
    series, cum_p, cum_a = [], 0.0, 0.0
    for key in months:
        p = plan_m.get(key, 0) / total * 100
        cum_p += p
        is_future = key > as_of_key
        a_val = None
        if not is_future:
            cum_a += act_m.get(key, 0) / total * 100
            a_val = round(act_m.get(key, 0) / total * 100, 2)
        series.append({
            "month": f"{key[0]:04d}-{key[1]:02d}",
            "planMonthPct": round(p, 2),
            "actualMonthPct": a_val,
            "planCumPct": round(min(cum_p, 100), 2),
            "actualCumPct": None if is_future else round(min(cum_a, 100), 2),
        })
    return series


def fetch_scurve_data(db: Session, p6_name: str) -> Dict[str, Any]:
    """Real P6 + SAP data for one project's "Overall S Curve" slide: the
    4-phase gap-analysis table and the blended monthly S-curve chart."""
    obj_id = _solar_project_object_id(db, p6_name)
    if not obj_id:
        return {"gap_analysis": [], "monthly": []}

    proj_row = db.execute(
        text("SELECT data_date FROM p6_project WHERE p6_object_id = :o"), {"o": obj_id}
    ).fetchone()
    as_of = proj_row[0] if proj_row and proj_row[0] else datetime.now()

    acts = db.execute(text("""
        SELECT wbs_name, status, start_date, actual_start_date, actual_finish_date, finish_date
        FROM p6_activity WHERE project_object_id = :o
    """), {"o": obj_id}).fetchall()

    module_wbs = db.execute(
        text("SELECT module_wbs FROM project_mapping WHERE project_name_from_p6 = :n LIMIT 1"),
        {"n": p6_name},
    ).scalar()

    return {
        "gap_analysis": _gap_analysis(db, acts, module_wbs, as_of),
        "monthly": _monthly_scurve(acts, as_of),
    }


# P6 resource Units are stored in hours, not days - verified platform-wide
# (CLAUDE.md), flat-divided to mandays.
HOURS_PER_DAY = 8.0

# P6 Labor resource_name values map directly to site-construction disciplines
# (verified identical naming across Bandha and Baiya, 2026-10-06) - unlike
# wbs_name, which lumps most labor under broad "CONSTRUCTION-PV AREA-*"
# nodes that don't decompose into these buckets. Resource pools not listed
# here ("Procurement Resource", "Engineering Resource", "Land Resource",
# "HOTO Resource", "Statutory Resource", "Preliminary Study Resource",
# "Contract Closure Resource", "Site Demobilation Resource", "Closeout &
# Report Resource", "Transmission Line Manpower") are office/milestone-loaded
# or out of plant scope, not site manpower - excluded, the same way the BESS
# pack excludes its own "LAB - GENERAL" pool.
MANPOWER_ROW_ORDER = ["Piling", "MMS+Robot", "Module", "IDT Area", "AC DC"]
MANPOWER_BUCKET_COLOURS = [
    RGBColor(0xED, 0x7D, 0x31),  # Piling - orange
    RGBColor(0xA5, 0xA5, 0xA5),  # MMS+Robot - grey
    RGBColor(0xFF, 0xC0, 0x00),  # Module - gold
    RGBColor(0x70, 0xAD, 0x47),  # IDT Area - green
    RGBColor(0x5B, 0x9B, 0xD5),  # AC DC - blue
]
_MANPOWER_BUCKETS = {
    "Piling": {"PILING MANPOWER"},
    "MMS+Robot": {"FT MANPOWER", "ROBOT INSTALLATION MANPOWER"},
    "Module": {"MODULE MANPOWER"},
    "IDT Area": {"IDT CIVIL MANPOWER", "IDT FILTRATION & TESTING"},
    "AC DC": {
        "ACDC MANPOWER", "CIVIL MANPOWER - CONSTRUCTION", "ELECTRICAL MANPOWER - CONSTRUCTION",
        "ELECTRICAL PT MANPOWER - CONSTRUCTION", "ELECTRICAL HARMONIC FILTER MANPOWER - CONSTRUCTION",
        "ELECTRICAL SVG MANPOWER - CONSTRUCTION", "PEB ERECTION MANPOWER - CONSTRUCTION",
        "LT PANEL TESTING", "HT PANEL TESTING",
    },
}


def _classify_manpower_resource(resource_name: Optional[str]) -> Optional[str]:
    up = (resource_name or "").upper().strip()
    for bucket, names in _MANPOWER_BUCKETS.items():
        if up in names:
            return bucket
    return None


def _spread_monthly(acc: Dict[str, float], start, finish, units: float) -> None:
    """Pro rata by days spent in each month - how a labour loading is
    phased, rather than landing the whole activity's units in one month."""
    if not units:
        return
    if start is None or finish is None or finish <= start:
        d = finish or start
        if d is not None:
            acc[d.strftime("%Y-%m")] += units
        return
    span = (finish - start).total_seconds()
    cur = start
    while cur < finish:
        nxt = (cur.replace(day=1) + timedelta(days=32)).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0)
        end = min(nxt, finish)
        acc[cur.strftime("%Y-%m")] += units * (end - cur).total_seconds() / span
        cur = end


def _days_in_month(m: str) -> int:
    y, mo = int(m[:4]), int(m[5:7])
    nxt = date(y + (mo == 12), mo % 12 + 1 if mo < 12 else 1, 1)
    return (nxt - date(y, mo, 1)).days


def fetch_manpower_data(db: Session, p6_name: str) -> Dict[str, Any]:
    """Site labor manpower (mandays/day) by discipline, Plan (baseline dates)
    vs Actual (posted hours over actual dates; planned x percent-complete
    only where nothing is posted yet, same fallback the BESS pack uses)."""
    obj_id = _solar_project_object_id(db, p6_name)
    empty = {"months": [], "plan_by_bucket": {}, "act_by_bucket": {}, "plan_total": [], "act_total": []}
    if not obj_id:
        return empty

    data_date = db.execute(
        text("SELECT data_date FROM p6_project WHERE p6_object_id = :o"), {"o": obj_id}
    ).scalar()

    rows = db.execute(text("""
        SELECT r.resource_name, a.baseline_start_date, a.baseline_finish_date,
               a.actual_start_date, a.actual_finish_date, a.finish_date,
               COALESCE(a.percent_complete, 0) AS pct,
               SUM(r.planned_units) AS planned, SUM(r.actual_units) AS actual
        FROM p6_resource_assignment r
        JOIN p6_activity a ON a.p6_object_id = r.activity_object_id
        WHERE r.project_object_id = :o AND r.resource_type = 'Labor'
        GROUP BY r.resource_name, a.baseline_start_date, a.baseline_finish_date,
                 a.actual_start_date, a.actual_finish_date, a.finish_date, a.percent_complete
    """), {"o": obj_id}).fetchall()
    if not rows:
        return empty

    plan_by_bucket: Dict[str, Dict[str, float]] = {b: defaultdict(float) for b in MANPOWER_ROW_ORDER}
    act_by_bucket: Dict[str, Dict[str, float]] = {b: defaultdict(float) for b in MANPOWER_ROW_ORDER}
    as_of = data_date.strftime("%Y-%m") if data_date else None

    for resource_name, bs, bf, as_, af, finish, pct, planned, actual in rows:
        bucket = _classify_manpower_resource(resource_name)
        if bucket is None:
            continue
        planned_md = float(planned or 0) / HOURS_PER_DAY
        _spread_monthly(plan_by_bucket[bucket], bs, bf, planned_md)

        actual_md = float(actual or 0) / HOURS_PER_DAY
        earned = actual_md if actual_md > 0 else planned_md * float(pct)
        if not earned:
            continue
        a_start, a_end = as_ or bs, af or finish or data_date
        # Don't let the percent-complete fallback leak mandays into months
        # beyond the P6 data date - there is no "actual" there yet.
        if as_of and a_end and a_end.strftime("%Y-%m") > as_of:
            a_end = data_date
        if as_of and a_start and a_start.strftime("%Y-%m") > as_of:
            continue
        _spread_monthly(act_by_bucket[bucket], a_start, a_end, earned)

    months = sorted({m for b in MANPOWER_ROW_ORDER
                      for m in set(plan_by_bucket[b]) | set(act_by_bucket[b])})
    if not months:
        return empty

    plan_by = {b: [round(plan_by_bucket[b].get(m, 0) / _days_in_month(m), 1) for m in months]
               for b in MANPOWER_ROW_ORDER}
    act_by = {b: ([round(act_by_bucket[b].get(m, 0) / _days_in_month(m), 1) if (not as_of or m <= as_of) else None
                   for m in months])
              for b in MANPOWER_ROW_ORDER}
    plan_total = [round(sum(plan_by[b][i] for b in MANPOWER_ROW_ORDER)) for i in range(len(months))]
    act_total = [
        round(sum(act_by[b][i] for b in MANPOWER_ROW_ORDER if act_by[b][i] is not None))
        if not as_of or m <= as_of else None
        for i, m in enumerate(months)
    ]
    return {"months": months, "plan_by_bucket": plan_by, "act_by_bucket": act_by,
            "plan_total": plan_total, "act_total": act_total}


def _replace_text_preserve_format(shape, old_text: str, new_text: str):
    """Replace text in a shape's text frame while keeping run-level formatting."""
    if not getattr(shape, "has_text_frame", False):
        return
    for paragraph in shape.text_frame.paragraphs:
        full_text = "".join(r.text for r in paragraph.runs)
        if old_text in full_text:
            paragraph.runs[0].text = full_text.replace(old_text, new_text)
            for r in paragraph.runs[1:]:
                r.text = ""

def _replace_text_in_table(table, old_text: str, new_text: str):
    """Replace text across all cells in a table."""
    for row in table.rows:
        for cell in row.cells:
            for p in cell.text_frame.paragraphs:
                full_text = "".join(r.text for r in p.runs)
                if old_text in full_text:
                    p.runs[0].text = full_text.replace(old_text, new_text)
                    for r in p.runs[1:]:
                        r.text = ""

def _set_cell_text(table, row: int, col: int, value: str):
    """Set the text of the first run in a table cell, preserving formatting."""
    cell = table.cell(row, col)
    from pptx.enum.text import PP_ALIGN
    try:
        from pptx.enum.text import MSO_ANCHOR
    except ImportError:
        MSO_ANCHOR = None
        
    first_run_set = False
    for p in cell.text_frame.paragraphs:
        for r in p.runs:
            if not first_run_set:
                r.text = str(value)
                first_run_set = True
            else:
                r.text = ""
    if not first_run_set:
        cell.text_frame.paragraphs[0].text = str(value)

def _clear_table_data(table, start_row: int = 1, start_col: int = 0):
    """Clear all data rows in a table (preserve header rows)."""
    for row in range(start_row, len(table.rows)):
        for col in range(start_col, len(table.columns)):
            _set_cell_text(table, row, col, "-")

def _remove_shape(shape):
    """Remove a shape from its slide."""
    sp = shape._element
    sp.getparent().remove(sp)

def _populate_project_slides(prs, start_idx: int, proj: dict):
    """Populate a single project's slide sequence with live data."""
    # 1. Salient Features (start_idx + 1)
    if len(prs.slides) > start_idx + 1:
        for sh in prs.slides[start_idx + 1].shapes:
            if getattr(sh, "has_table", False):
                tbl = sh.table
                # Clear by default
                _clear_table_data(tbl, start_row=0, start_col=1)
                
                # Populate specific rows
                _set_cell_text(tbl, 0, 1, proj.get("name", ""))
                _set_cell_text(tbl, 1, 1, proj.get("capacity", ""))
                _set_cell_text(tbl, 2, 1, proj.get("spv", ""))
                _set_cell_text(tbl, 9, 1, proj.get("start_date", ""))
                _set_cell_text(tbl, 10, 1, proj.get("cod_plan", ""))
                _set_cell_text(tbl, 12, 1, proj.get("cod_actual", ""))
                
    # 2. Plot Plan (start_idx + 2)
    if len(prs.slides) > start_idx + 2:
        for sh in prs.slides[start_idx + 2].shapes:
            if getattr(sh, "has_table", False):
                _clear_table_data(sh.table, start_row=1, start_col=1)

    # 3. Overall S Curve (start_idx + 3)
    if len(prs.slides) > start_idx + 3:
        slide = prs.slides[start_idx + 3]
        scurve = proj.get("scurve") or {}
        gap_rows = scurve.get("gap_analysis") or []
        monthly = scurve.get("monthly") or []

        chart_box = None
        for sh in slide.shapes:
            if getattr(sh, "has_table", False):
                if gap_rows:
                    for i, row in enumerate(gap_rows):
                        set_row(sh, 2 + i, [
                            f"{row['weight']}%",
                            _p(row["plan"]),
                            _p(row["actual"]),
                            _p(row["variance"]),
                            row["remark"],
                        ], 1)
                        # The template's own placeholder in the Overall row's
                        # remark cell is 18pt (vs 10pt on every data row) -
                        # set_text preserves whatever it finds, so without
                        # this the disclosure text renders oversized.
                        remark_cell = sh.table.cell(2 + i, 5)
                        for para in remark_cell.text_frame.paragraphs:
                            for run in para.runs:
                                run.font.size = Pt(10)
                else:
                    _clear_table_data(sh.table, start_row=2, start_col=2)
            elif getattr(sh, "has_chart", False):
                # The chart shape's own position/size *is* the box - this
                # template has no separate placeholder picture for it.
                chart_box = (sh.left, sh.top, sh.width, sh.height)
                _remove_shape(sh)

        if monthly and chart_box:
            cats = [_mon(_add_months(monthly[0]["month"], -1))] + [_mon(m["month"]) for m in monthly]

            def col(key):
                return [0.0] + [None if m[key] is None else m[key] / 100 for m in monthly]

            cd = CategoryChartData(number_format="0.00%")
            cd.categories = cats
            cd.add_series("Monthly Plan", col("planMonthPct"))
            cd.add_series("Monthly Actual", col("actualMonthPct"))
            cd.add_series("Cumm. Plan", col("planCumPct"))
            cd.add_series("Cumm. Actual", col("actualCumPct"))
            x, y, cx, cy = chart_box
            chart = slide.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, x, y, cx, cy, cd).chart
            chart.font.size = Pt(9)
            _move_to_line(chart, 2, secondary=True)
            _light_gridlines(chart)
            _series_fill(chart, [SERIES_BLUE, SERIES_GREEN, SERIES_BLUE, LINE_GREEN], line_from=2)
            chart.has_legend = True
            chart.legend.position = XL_LEGEND_POSITION.TOP
            chart.legend.include_in_layout = False
            chart.legend.font.size = Pt(9)

    # 4. Engineering (start_idx + 4)
    if len(prs.slides) > start_idx + 4:
        for sh in prs.slides[start_idx + 4].shapes:
            if getattr(sh, "has_table", False):
                _clear_table_data(sh.table, start_row=1, start_col=2)

    # 5. Procurement (start_idx + 5)
    if len(prs.slides) > start_idx + 5:
        from dateutil.relativedelta import relativedelta
        from datetime import datetime
        now = datetime.now()
        m0 = now.strftime("%b-%y")
        m0_apos = now.strftime("%b'%y")
        m1 = (now + relativedelta(months=1)).strftime("%b-%y")
        m2 = (now + relativedelta(months=2)).strftime("%b-%y")
        m3 = (now + relativedelta(months=3)).strftime("%b-%y")
        
        for sh in prs.slides[start_idx + 5].shapes:
            if getattr(sh, "has_table", False):
                tbl = sh.table
                _clear_table_data(tbl, start_row=2, start_col=3)
                # Update headers in reverse order to prevent cascading overwrites
                _replace_text_in_table(tbl, "Nov-26", m3)
                _replace_text_in_table(tbl, "Oct-26", m2)
                _replace_text_in_table(tbl, "Sep-26", m1)
                _replace_text_in_table(tbl, "Aug-26", m0)
                _replace_text_in_table(tbl, "Aug'26", m0_apos)
                _replace_text_in_table(tbl, "Aug’26", m0_apos)

    # 6. Construction Progress (start_idx + 6)
    if len(prs.slides) > start_idx + 6:
        from dateutil.relativedelta import relativedelta
        from datetime import datetime
        now = datetime.now()
        m0 = now.strftime("%b-%y")
        m0_apos = now.strftime("%b'%y")
        m1 = (now + relativedelta(months=1)).strftime("%b-%y")
        m2 = (now + relativedelta(months=2)).strftime("%b-%y")
        m3 = (now + relativedelta(months=3)).strftime("%b-%y")
        
        for sh in prs.slides[start_idx + 6].shapes:
            if getattr(sh, "has_table", False):
                tbl = sh.table
                _clear_table_data(tbl, start_row=2, start_col=3)
                # Update headers in reverse order to prevent cascading overwrites
                _replace_text_in_table(tbl, "Nov-26", m3)
                _replace_text_in_table(tbl, "Oct-26", m2)
                _replace_text_in_table(tbl, "Sep-26", m1)
                _replace_text_in_table(tbl, "Aug-26", m0)
                _replace_text_in_table(tbl, "Aug'26", m0_apos)
                _replace_text_in_table(tbl, "Aug’26", m0_apos)

    # 7. Milestones (start_idx + 7)
    if len(prs.slides) > start_idx + 7:
        for sh in prs.slides[start_idx + 7].shapes:
            if getattr(sh, "has_table", False):
                _clear_table_data(sh.table, start_row=1, start_col=0)

    # 8. Manpower Chart (start_idx + 8)
    if len(prs.slides) > start_idx + 8:
        slide = prs.slides[start_idx + 8]
        mp = proj.get("manpower") or {}
        months = mp.get("months") or []

        chart_box = None
        for sh in list(slide.shapes):
            if getattr(sh, "has_chart", False):
                chart_box = (sh.left, sh.top, sh.width, sh.height)
                _remove_shape(sh)

        if months and chart_box:
            cd = CategoryChartData(number_format="0")
            for m in months:
                c = cd.add_category(_mon(m))
                c.add_sub_category("Plan")
                c.add_sub_category("Act")

            plan_by = mp["plan_by_bucket"]
            act_by = mp["act_by_bucket"]
            for bucket in MANPOWER_ROW_ORDER:
                vals = []
                for i in range(len(months)):
                    vals += [plan_by[bucket][i], act_by[bucket][i]]
                cd.add_series(bucket, vals)
            plan_total, act_total = mp["plan_total"], mp["act_total"]
            cd.add_series("Total Planned", [v for i in range(len(months)) for v in (plan_total[i], None)])
            cd.add_series("Total Actual", [v for i in range(len(months)) for v in (None, act_total[i])])

            x, y, cx, cy = chart_box
            chart = slide.shapes.add_chart(XL_CHART_TYPE.COLUMN_STACKED, x, y, cx, cy, cd).chart
            chart.font.size = Pt(9)
            _move_to_line(chart, 2, secondary=False)
            _light_gridlines(chart)
            _series_fill(chart, MANPOWER_BUCKET_COLOURS + [SERIES_BLUE, SERIES_GREEN], line_from=5)
            _span_blanks(chart)
            chart.has_legend = True
            chart.legend.position = XL_LEGEND_POSITION.TOP
            chart.legend.include_in_layout = False
            chart.legend.font.size = Pt(9)


def _ordinal_date(d: date) -> str:
    suffix = "th" if 11 <= d.day <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(d.day % 10, "th")
    return f"{d.day}{suffix} {d.strftime('%b %y')}"

def build_portfolio_pptx(data: Dict[str, Any] = None) -> bytes:
    """Build the CPAG Solar pack by injecting live data into the template."""
    prs = Presentation(REFERENCE)
    
    # Update cover slide date
    slide = prs.slides[0]
    current_date = _ordinal_date(date.today())
    for shape in slide.shapes:
        if getattr(shape, "has_text_frame", False):
            for p in shape.text_frame.paragraphs:
                full_text = "".join(r.text for r in p.runs)
                if "Aug-26" in full_text:
                    p.runs[0].text = full_text.replace("Aug-26", current_date)
                    for r in p.runs[1:]:
                        r.text = ""

    # Slide 3 (Index 2): Executive Summary
    if len(prs.slides) > 2:
        for sh in prs.slides[2].shapes:
            if getattr(sh, "has_table", False):
                tbl = sh.table
                project_list = data.get("projects", [])
                # The first two rows are headers, data starts at row 2
                for i in range(2, len(tbl.rows)):
                    if tbl.cell(i, 0).text_frame.text.strip().lower() == "total":
                        # Clear totals row values
                        for c in range(3, len(tbl.columns)):
                            _set_cell_text(tbl, i, c, "")
                        continue

                    # Clear all data columns by default
                    for c in range(3, len(tbl.columns)):
                        _set_cell_text(tbl, i, c, "")
                    
                    proj_idx = i - 2
                    if proj_idx < len(project_list):
                        proj = project_list[proj_idx]
                        _set_cell_text(tbl, i, 2, proj.get("name", ""))
                        _set_cell_text(tbl, i, 3, proj.get("capacity", ""))
                        _set_cell_text(tbl, i, 6, proj.get("cod_plan", ""))
                        _set_cell_text(tbl, i, 7, proj.get("cod_actual", ""))
                        _set_cell_text(tbl, i, 8, proj.get("progress_plan", ""))
                        _set_cell_text(tbl, i, 9, proj.get("progress_actual", ""))

    # Project 1: Bandha 500 MW (Starts at Slide 4 / Index 3)
    if len(prs.slides) > 3 and len(data.get("projects", [])) > 0:
        proj = data["projects"][0]
        for sh in prs.slides[3].shapes:
            if getattr(sh, "has_text_frame", False) and "Bandha" in sh.text_frame.text:
                for p in sh.text_frame.paragraphs:
                    if p.runs:
                        p.runs[0].text = proj["name"]
                        for r in p.runs[1:]:
                            r.text = ""
        _populate_project_slides(prs, start_idx=3, proj=proj)
    
    # Project 2: Baiya 600 MW (Starts at Slide 13 / Index 12)
    if len(prs.slides) > 12 and len(data.get("projects", [])) > 1:
        proj = data["projects"][1]
        for sh in prs.slides[12].shapes:
            if getattr(sh, "has_text_frame", False) and "Baiya" in sh.text_frame.text:
                for p in sh.text_frame.paragraphs:
                    if p.runs:
                        p.runs[0].text = proj["name"]
                        for r in p.runs[1:]:
                            r.text = ""
        _populate_project_slides(prs, start_idx=12, proj=proj)

    out = BytesIO()
    prs.save(out)
    return out.getvalue()
