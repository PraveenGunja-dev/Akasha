"""
CPAG Khavda Wind PPTX Builder.

Takes the split Khavda Wind reference deck and injects live data from P6 + SAP + project_mapping
into table cells and charts, replacing all template placeholder data while strictly preserving
the original visual styling, slide format, and structure.
"""
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional
from collections import defaultdict

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from sqlalchemy import text
from sqlalchemy.orm import Session

from services.cpag_pptx import replace_chart_data
from services.cpag_khavda_scrub import TableSpec, scrub_deck
from services.cpag_khavda_wind_progress import fetch_wind_progress, khavda_wind_projects
from services.cpag_khavda_solar_pptx import _relabel_months

BACKEND = Path(__file__).resolve().parent.parent
REFERENCE = BACKEND / "assets" / "cpag_khavda_wind_reference.pptx"

# What is format on each page of the Khavda Wind deck (1-based slide numbers);
# every other table cell and every chart point is blanked before the fill.
_SPECS = {
    3: TableSpec(2),
    4: TableSpec(1, keep_cols=(0, 1)),
    6: TableSpec(1, keep_rows=(6, 9), keep_cols=(0,)),
    7: TableSpec(2, keep_cols=(0,)),
    8: TableSpec(2, keep_cols=(0, 1, 2)),
    9: TableSpec(2, keep_cols=(0, 1, 2)),
    10: TableSpec(2, keep_cols=(0, 1, 2)),
}
_BLANK_CHARTS = (4, 7, 11)
_BLANK_TEXT = {10: ("TextBox 1",)}


def _ordinal_date(d: date) -> str:
    suffix = "th" if 11 <= d.day <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(d.day % 10, "th")
    return f"{d.day}{suffix} {d.strftime('%b %y')}"


def _replace_text_preserve_format(shape, old_text: str, new_text: str):
    if not shape.has_text_frame:
        return
    for paragraph in shape.text_frame.paragraphs:
        for run in paragraph.runs:
            if old_text in run.text:
                run.text = run.text.replace(old_text, new_text)


def _set_cell_text(table, row: int, col: int, value: str):
    if row >= len(table.rows) or col >= len(table.columns):
        return
    cell = table.cell(row, col)
    for p in cell.text_frame.paragraphs:
        if p.runs:
            p.runs[0].text = str(value)
            for r in p.runs[1:]:
                r.text = ""
            return
    if cell.text_frame.paragraphs:
        cell.text_frame.paragraphs[0].text = str(value)


def _clear_table_data(table, start_row: int = 1, start_col: int = 0):
    for r in range(start_row, len(table.rows)):
        for c in range(start_col, len(table.columns)):
            cell = table.cell(r, c)
            for paragraph in cell.text_frame.paragraphs:
                for run in paragraph.runs:
                    run.text = ""


def _fmt(val, zero: str = "0", pct: bool = False, decimals: int = 0) -> str:
    if val is None or val == "":
        return "-"
    try:
        f = float(val)
        if abs(f) < 1e-6:
            return zero
        if pct:
            return f"{f:.{decimals}f}%" if decimals > 0 else f"{round(f)}%"
        return f"{f:,.{decimals}f}" if decimals > 0 else f"{round(f):,}"
    except (ValueError, TypeError):
        return str(val)


# ── Live Data Extractors for Wind Khavda ────────────────────────────────────

def fetch_wind_khavda_data(db: Session) -> Dict[str, Any]:
    """Extract all dynamic metrics and project data for Khavda Wind from DB."""
    # The Khavda wind projects in P6; capacity in MW is not held anywhere (see
    # services/cpag_khavda_wind_progress.py), so the MW totals stay empty.
    wind_list = khavda_wind_projects(db)
    p6_wind_projects = [(w["obj"], w["name"], w["finish"], w["baseline"], w["pct"]) for w in wind_list]
    tot_cap = 0.0
    tot_comm = 0.0

    wind_obj_ids = [p[0] for p in p6_wind_projects]

    avg_progress = 0.0
    if p6_wind_projects:
        valid_p = [float(p[4]) for p in p6_wind_projects if p[4] is not None]
        if valid_p:
            avg_progress = sum(valid_p) / len(valid_p)

    gap_analysis = []
    scurve_monthly = []

    if wind_obj_ids:
        acts = db.execute(text(f"""
            SELECT name, wbs_name, status, start_date, finish_date, actual_start_date, actual_finish_date
            FROM p6_activity
            WHERE project_object_id IN ({','.join(map(str, wind_obj_ids))})
        """)).fetchall()

        now = datetime.now()
        eng_acts = [a for a in acts if 'ENGINEERING' in (a[1] or '').upper()]
        proc_acts = [a for a in acts if (a[0] or '').upper().startswith('ORDERING & SUPPLY')]
        proc_ids = {id(a) for a in proc_acts}
        con_acts = [a for a in acts if id(a) not in proc_ids and any(k in (a[1] or '').upper() for k in ('CIVIL', 'ERECTION', 'ELECTRIC', 'COMMISSION', 'TESTING', 'FOUNDATION'))]

        def _cat_stat(lst, weight):
            scope = len(lst)
            if not scope:
                return {"weight": f"{weight}%", "plan": "0%", "actual": "0%", "variance": "0%"}
            pln = sum(1 for a in lst if a[4] and a[4] <= now)
            act = sum(1 for a in lst if a[2] == 'Completed')
            pln_pct = round(100 * pln / scope)
            act_pct = round(100 * act / scope)
            return {
                "weight": f"{weight}%",
                "plan": f"{pln_pct}%",
                "actual": f"{act_pct}%",
                "variance": f"{max(0, pln_pct - act_pct)}%"
            }

        eng_stat = _cat_stat(eng_acts, 5)
        proc_stat = _cat_stat(proc_acts, 35)
        con_stat = _cat_stat(con_acts, 60)

        tot_pln = round(0.05 * int(eng_stat["plan"][:-1]) + 0.35 * int(proc_stat["plan"][:-1]) + 0.60 * int(con_stat["plan"][:-1]))
        tot_act = round(0.05 * int(eng_stat["actual"][:-1]) + 0.35 * int(proc_stat["actual"][:-1]) + 0.60 * int(con_stat["actual"][:-1]))

        gap_analysis = [
            {"parameter": "Engineering", **eng_stat, "remark": ""},
            {"parameter": "Procurement", **proc_stat, "remark": ""},
            {"parameter": "Construction", **con_stat, "remark": ""},
            {"parameter": "Total", "weight": "100%", "plan": f"{tot_pln}%", "actual": f"{tot_act}%", "variance": f"{max(0, tot_pln - tot_act)}%", "remark": ""},
        ]

        # Monthly S-curve
        months_label = ["Apr-26", "May-26", "Jun-26", "Jul-26", "Aug-26", "Sep-26", "Oct-26", "Nov-26", "Dec-26", "Jan-27", "Feb-27", "Mar-27"]
        plan_m = defaultdict(int)
        act_m = defaultdict(int)
        for a in acts:
            if a[3]:
                plan_m[a[3].strftime("%b-%y")] += 1
            if a[2] == "Completed" and a[6]:
                act_m[a[6].strftime("%b-%y")] += 1
            elif a[2] == "In Progress" and a[5]:
                act_m[a[5].strftime("%b-%y")] += 0.5

        total_a = len(acts) or 1
        cum_p = 0.0
        cum_a = 0.0
        for m in months_label:
            p = (plan_m[m] / total_a) * 100
            a = (act_m[m] / total_a) * 100 if m in act_m else 0
            cum_p = min(100, cum_p + p)
            cum_a = min(100, cum_a + a)
            scurve_monthly.append({
                "month": m,
                "monthly_plan": round(p, 2),
                "monthly_actual": round(a, 2),
                "cum_plan": round(cum_p, 2),
                "cum_actual": round(cum_a, 2),
            })

    progress = fetch_wind_progress(db)

    def _latest(idx):
        ds = [p[idx] for p in p6_wind_projects if p[idx]]
        return max(ds).strftime("%d-%b-%y") if ds else "-"

    return {
        "as_of": date.today().isoformat(),
        "progress": progress,
        "page_notes": _progress_notes(progress),
        "cod_plan": _latest(3),
        "cod_expected": _latest(2),
        "total_capacity_mw": tot_cap,
        "commissioned_mw": tot_comm,
        "overall_plan_pct": gap_analysis[-1]["plan"] if gap_analysis else "-",
        "overall_act_pct": gap_analysis[-1]["actual"] if gap_analysis else "-",
        "gap_analysis": gap_analysis,
        "scurve_monthly": scurve_monthly,
    }


# ── Slide Fillers ───────────────────────────────────────────────────────────

def _fill_slide_1(slide, current_date_str: str):
    """Slide 1: Cover."""
    for sh in slide.shapes:
        _replace_text_preserve_format(sh, "Aug-26", current_date_str)


def _fill_slide_3(slide, data: Dict[str, Any]):
    """Slide 3: Executive Summary (Wind row)."""
    tbl_shape = next((sh for sh in slide.shapes if getattr(sh, "has_table", False)), None)
    if not tbl_shape:
        return
    tbl = tbl_shape.table
    r = 2  # The Wind row (after cut)
    if r < len(tbl.rows):
        _relabel_months(tbl)
        _set_cell_text(tbl, r, 0, "1")
        _set_cell_text(tbl, r, 1, "GJ")
        _set_cell_text(tbl, r, 2, "Khavda-Wind")
        for c in (3, 4, 5):      # wind MW is held in neither P6 nor the register
            _set_cell_text(tbl, r, c, "-")
        _set_cell_text(tbl, r, 6, data.get("cod_plan", "-"))
        _set_cell_text(tbl, r, 7, data.get("cod_expected", "-"))
        _set_cell_text(tbl, r, 8, data.get("overall_plan_pct", "-"))
        _set_cell_text(tbl, r, 9, data.get("overall_act_pct", "-"))
        _set_cell_text(tbl, r, 10, "-")


def _fill_slide_4(slide, data: Dict[str, Any]):
    """Slide 4: Commissioning Plan vs Forecast (Wind row + Chart)."""
    tbl_shape = next((sh for sh in slide.shapes if getattr(sh, "has_table", False)), None)
    if tbl_shape:
        tbl = tbl_shape.table
        # The month-wise budget and forecast have no connected source, so the
        # Total column stays empty too: capacity / commissioned MW are not the
        # FY budget and forecast the row names.

    chart_shape = next((sh for sh in slide.shapes if getattr(sh, "has_chart", False)), None)
    if chart_shape and tbl_shape:
        tbl = tbl_shape.table
        try:
            cd = CategoryChartData(number_format="#,##0")
            cd.categories = list(chart_shape.chart.plots[0].categories)
            b_row = 2
            a_row = 3 if len(tbl.rows) == 4 else 4
            b_vals = []
            a_vals = []
            for c in range(2, 14):
                if c < len(tbl.columns):
                    bv = tbl.cell(b_row, c).text_frame.text.replace(",", "").strip()
                    av = tbl.cell(a_row, c).text_frame.text.replace(",", "").strip()
                    b_vals.append(float(bv) if bv and bv != "-" else None)
                    a_vals.append(float(av) if av and av != "-" else None)
            cd.add_series("Budget", b_vals)
            cd.add_series("Actual / Fcst", a_vals)
            replace_chart_data(chart_shape.chart, cd)
        except Exception:
            pass


def _fill_slide_6(slide, data: Dict[str, Any]):
    """Slide 6: Salient Features."""
    tbl_shape = next((sh for sh in slide.shapes if getattr(sh, "has_table", False)), None)
    if not tbl_shape:
        return
    tbl = tbl_shape.table
    locations = data["progress"]["locations"]
    if locations and len(tbl.rows) > 1 and len(tbl.columns) > 1:
        _set_cell_text(tbl, 1, 1, f"{locations:,} WTG locations")


def _fill_slide_7(slide, data: Dict[str, Any]):
    """Slide 7: Physical Progress S-Curve & Gap Analysis."""
    tbl_shape = next((sh for sh in slide.shapes if getattr(sh, "has_table", False)), None)
    gap_rows = data.get("gap_analysis", [])
    if tbl_shape and gap_rows:
        tbl = tbl_shape.table
        for idx, g in enumerate(gap_rows):
            r = idx + 2
            if r < len(tbl.rows):
                _set_cell_text(tbl, r, 0, g["parameter"])
                _set_cell_text(tbl, r, 1, g["weight"])
                _set_cell_text(tbl, r, 2, g["plan"])
                _set_cell_text(tbl, r, 3, g["actual"])
                _set_cell_text(tbl, r, 4, g["variance"])
                _set_cell_text(tbl, r, 5, g.get("remark", ""))

    # One chart, two plots in the template: monthly bars (Plan, Actual, Forecast
    # Plan) then cumulative lines (same three). There is no forecast, so those
    # two series stay empty.
    chart_shape = next((sh for sh in slide.shapes if getattr(sh, "has_chart", False)), None)
    monthly = data.get("scurve_monthly", [])
    if chart_shape and monthly:
        try:
            none = [None] * len(monthly)
            cd = CategoryChartData(number_format="0.00%")
            # The template's axis is a date axis: text labels would plot nothing.
            cd.categories = [datetime.strptime(m["month"], "%b-%y").date() for m in monthly]
            cd.categories.number_format = "mmm\-yy"
            cd.add_series("Monthly Plan", [m["monthly_plan"] / 100 for m in monthly])
            cd.add_series("Monthly Actual", [m["monthly_actual"] / 100 for m in monthly])
            cd.add_series("Monthly Forecast Plan", none)
            cd.add_series("Cummulative Plan", [m["cum_plan"] / 100 for m in monthly])
            cd.add_series("Cummulative Actual", [m["cum_actual"] / 100 for m in monthly])
            cd.add_series("Cummulative Forecast Plan", none)
            replace_chart_data(chart_shape.chart, cd)
        except Exception:
            pass


def _mw(v) -> str:
    return "-" if not v or abs(v) < 0.5 else f"{round(v):,}"


def _q(v, uom: str, zero: str = "-") -> str:
    """Thousands grouping as the template prints it; one decimal only for a fractional unit."""
    if v is None:
        return "-"
    if abs(v) < 0.05:
        return zero
    if uom.strip().lower() == "km" and abs(v - round(v)) >= 0.05:
        return f"{v:,.1f}"
    return f"{round(v):,}"


def _table(slide):
    sh = next((s for s in slide.shapes if getattr(s, "has_table", False)), None)
    return sh.table if sh else None


def _fill_slide_8(slide, data: Dict[str, Any]):
    """Procurement. Cols: 2 UOM, 3 Scope, 4 Ordering Completed (not held in P6 - left
    empty), 5 Delivered at site, 6 Balance to deliver, 7-9 forecast months."""
    tbl = _table(slide)
    if tbl is None:
        return
    _relabel_months(tbl)
    for i, r in enumerate(data["progress"]["procurement"]):
        row = 2 + i
        if r is None or row >= len(tbl.rows):
            continue
        u = r["uom"]
        _set_cell_text(tbl, row, 2, u)
        _set_cell_text(tbl, row, 3, _q(r["scope"], u))
        _set_cell_text(tbl, row, 5, _q(r["delivered"], u, "0"))
        _set_cell_text(tbl, row, 6, _q(r["balance"], u, "0"))
        for k, v in enumerate(r["forecast"]):
            _set_cell_text(tbl, row, 7 + k, _q(v, u))


def _fill_slide_9(slide, data: Dict[str, Any]):
    """Construction Progress. Cols: 2 UOM, 3 Scope, 4 Completed, 5 Balance, 6 Month
    Plan, 7 Month Actual, 8-10 forecast months, 11 Completion Target."""
    tbl = _table(slide)
    if tbl is None:
        return
    _relabel_months(tbl)
    for i, r in enumerate(data["progress"]["construction"]):
        row = 2 + i
        if r is None or row >= len(tbl.rows):
            continue
        u = r["uom"]
        _set_cell_text(tbl, row, 2, u)
        _set_cell_text(tbl, row, 3, _q(r["scope"], u))
        _set_cell_text(tbl, row, 4, _q(r["completed"], u, "0"))
        _set_cell_text(tbl, row, 5, _q(r["balance"], u, "0"))
        _set_cell_text(tbl, row, 6, _q(r["month_plan"], u))
        _set_cell_text(tbl, row, 7, _q(r["month_actual"], u))
        for k, v in enumerate(r["forecast"]):
            _set_cell_text(tbl, row, 8 + k, _q(v, u))
        _set_cell_text(tbl, row, 11, r["target"])


def _progress_notes(progress: Dict[str, Any]) -> Dict[int, List[str]]:
    n = progress["n_projects"]
    where = (f"the {n} Khavda wind projects in P6 (the Wind projects in the register named with a location count; "
             "Mandvi and Mundra North are other sites)")
    mw = "Wind capacity in MW is not held in P6 or the register, so every MW column is left empty."
    return {
        3: [f"Progress and COD dates from {where}. {mw}",
            "Plan / Actual % are activity counts by category (inference, weighted 5 / 35 / 60), not P6 weighted progress."],
        4: [mw],
        6: [f"{progress['locations']} WTG locations, from P6's WTG Erection quantity over {where}. " + mw],
        7: [f"Activity counts from {where}: Procurement = 'Ordering & Supply' lots, Construction = civil / erection / electrical / commissioning, "
            "Engineering = its own WBS. Weights 5 / 35 / 60 are the pack's convention. The S-curve is the share of activities due / done per month - inference, not P6 progress."],
        8: [f"P6 Material resources on the 'Ordering & Supply - Delivery at Site' lots of {where}. Each component is booked again on the activity that installs it, "
            "so supply and installation quantities are read separately.",
            "A row is shown only where the supply quantity agrees with the quantity to be installed (within 10%). Ordering Completed has no source in P6 and is left empty. "
            "Balance to deliver = Scope - Delivered; forecast months = lots not yet received, by P6 forecast finish (work due this month or overdue sits in the first month)."],
        9: [f"P6 Material resources on the civil / erection / commissioning activities of {where}. A unit is one location: a completed activity counts in full. "
            "Month Plan = baseline finish this month; Month Actual shows '-' unless every project's P6 data date reaches this month (several wind schedules were last updated months ago). "
            "Next 3 months = units still open by forecast finish. Completion Target = latest forecast finish of open work."],
        10: ["Machinery (rigs, cranes) is not held in P6 or the register; left empty."],
        11: ["Manpower by month is not built for wind yet; the chart is left empty."],
    }


def build_wind_deck(data: Dict[str, Any]) -> bytes:
    """Build the dynamic Khavda Wind deck bytes."""
    prs = Presentation(str(REFERENCE))
    scrub_deck(prs, _SPECS, _BLANK_CHARTS, _BLANK_TEXT)
    current_date_str = _ordinal_date(date.today())

    # Slide 1: Cover
    _fill_slide_1(prs.slides[0], current_date_str)

    # Slide 3: Executive Summary
    if len(prs.slides) > 2:
        _fill_slide_3(prs.slides[2], data)

    # Slide 4: Commissioning Plan vs Forecast
    if len(prs.slides) > 3:
        _fill_slide_4(prs.slides[3], data)

    # Slide 6: Salient Features
    if len(prs.slides) > 5:
        _fill_slide_6(prs.slides[5], data)

    # Slide 7: Physical Progress S-Curve
    if len(prs.slides) > 6:
        _fill_slide_7(prs.slides[6], data)

    # Slides 8-9: Procurement, Construction Progress
    if len(prs.slides) > 7:
        _fill_slide_8(prs.slides[7], data)
    if len(prs.slides) > 8:
        _fill_slide_9(prs.slides[8], data)

    bio = BytesIO()
    prs.save(bio)
    return bio.getvalue()
