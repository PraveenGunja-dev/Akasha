"""
CPAG Khavda Solar PPTX Builder.

Takes the split Khavda Solar reference deck and injects live data from P6 + SAP + project_mapping
into table cells and charts, replacing all template placeholder data while strictly preserving
the original visual styling, slide format, and structure.
"""
import copy
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional
from collections import defaultdict
import re

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.util import Emu, Pt
from sqlalchemy import text
from sqlalchemy.orm import Session

from services.cpag_pptx import replace_chart_data
from services.cpag_khavda_scrub import TableSpec, scrub_deck
from services.cpag_khavda_progress import fetch_khavda_solar_progress

BACKEND = Path(__file__).resolve().parent.parent
REFERENCE = BACKEND / "assets" / "cpag_khavda_solar_reference.pptx"

# What is format on each page of the Khavda Solar deck (1-based slide numbers);
# every other table cell and every chart point is blanked before the fill.
_SPECS = {
    3: TableSpec(2),
    4: TableSpec(1, keep_cols=(0, 1)),
    6: TableSpec(1, keep_rows=(7, 10), keep_cols=(0,)),
    7: TableSpec(1),
    8: TableSpec(2, keep_cols=(0,)),
    9: TableSpec(1, keep_cols=(0, 1)),
    10: TableSpec(2, keep_cols=(0, 1, 2)),
    11: TableSpec(2, keep_cols=(0, 1, 2)),
    12: TableSpec(2, keep_cols=(0, 1, 2)),
    13: TableSpec(2),
    14: TableSpec(3),
    15: TableSpec(1, keep_cols=(0,)),
    **{n: TableSpec(2, keep_cols=(2,)) for n in range(16, 22)},
    **{n: TableSpec(1, keep_cols=(0,)) for n in range(22, 28)},
    28: TableSpec(2),
}
_BLANK_CHARTS = (4, 8)
_BLANK_TEXT = {7: ("TextBox 33",)}


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


# ── Live Data Extractors for Solar Khavda ───────────────────────────────────

def fetch_solar_khavda_data(db: Session) -> Dict[str, Any]:
    """Extract all dynamic metrics and project data for Khavda Solar from DB."""
    # 1. Plot-wise and project summaries from project_mapping
    plots_query = text("""
        SELECT 
            COALESCE(category, 'FY27 Project') as category,
            COALESCE(NULLIF(spv_name, ''), '-') as spv,
            COALESCE(NULLIF(plot_no, ''), '-') as plot,
            COALESCE(capacity_mwac, 0) as capacity,
            CASE WHEN is_commissioned = true OR project_name_from_p6 ILIKE '%commissioned%' 
                 THEN COALESCE(capacity_mwac, 0) ELSE 0 END as comm_mw,
            project_name_from_p6
        FROM project_mapping
        WHERE cluster = 'Solar Khavda'
        ORDER BY 
            CASE WHEN is_commissioned = true OR project_name_from_p6 ILIKE '%commissioned%' THEN 0 ELSE 1 END,
            plot_no, project_name_from_p6
    """)
    plots_raw = db.execute(plots_query).fetchall()

    plots = []
    tot_cap = 0.0
    tot_comm = 0.0
    for r in plots_raw:
        cat = r[0] or "FY27 Project"
        spv = r[1]
        plot_no = r[2]
        cap = float(r[3] or 0)
        comm = float(r[4] or 0)
        tot_cap += cap
        tot_comm += comm
        plots.append({
            "category": cat,
            "spv": spv,
            "plot": plot_no,
            "capacity": cap,
            "commissioned": comm,
            "project_name": r[5] or ""
        })

    # 2. Connected P6 projects
    p6_projects = db.execute(text("""
        SELECT DISTINCT p6.p6_object_id, p6.name, p6.scheduled_finish_date, p6.baseline_finish_date, p6.duration_percent_complete
        FROM p6_project p6
        JOIN project_mapping pm ON p6.name = pm.project_name_from_p6
        WHERE pm.cluster = 'Solar Khavda'
          AND EXISTS (SELECT 1 FROM p6_activity a WHERE a.project_object_id = p6.p6_object_id LIMIT 1)
    """)).fetchall()

    solar_obj_ids = [p[0] for p in p6_projects]

    # Progress calculations
    avg_act_progress = 0.0
    if p6_projects:
        valid_progs = [float(p[4]) for p in p6_projects if p[4] is not None]
        if valid_progs:
            avg_act_progress = sum(valid_progs) / len(valid_progs)

    # 3. Activities across solar projects
    gap_analysis = []
    scurve_monthly = []
    procurement_packages = []
    construction_activities = []
    manpower_data = []

    if solar_obj_ids:
        # Fetch activity summary
        acts = db.execute(text(f"""
            SELECT a.wbs_name, a.status, a.start_date, a.finish_date, a.actual_start_date, a.actual_finish_date, a.name
            FROM p6_activity a
            WHERE a.project_object_id IN ({','.join(map(str, solar_obj_ids))})
        """)).fetchall()

        data_dates = [p[2] for p in p6_projects if getattr(p, "data_date", None)]
        as_of = max(data_dates) if data_dates else datetime.now()

        def _classify(wbs, name):
            w = (wbs or "").upper().strip()
            n = (name or "").upper().strip()
            if any(k in w for k in ('CONSTRUCTION', 'CIVIL WORKS', 'EQUIPMENT ERECTION', 'CABLE LAYING', 'COMMISSIONING', 'PRE COMMISSIONING', 'ELECTRO-MECHANICAL')) or \
               any(k in n for k in ('LAYING', 'ERECTION', 'INSTALLATION', 'CASTING', 'TESTING', 'COMMISSIONING', 'PILING', 'PULL OUT')):
                return 'Construction'
            if any(k in w for k in ('LAYOUT', 'SCHEDULE', 'DIAGRAM', 'DRAWING', 'ENGINEERING', 'STUDY', 'SYSTEM STUDY')) or \
               any(k in n for k in ('DRAWING', 'LAYOUT', 'STUDY', 'SLD', 'APPROVAL', 'DESIGN', 'MDR', 'ENGINEERING')):
                return 'Engineering'
            if any(k in w for k in ('PROCUREMENT', 'SUPPLY', 'MODULE', 'INVERTER', 'PANEL', 'TRANSFORMER', 'MMS', 'ROBOT', 'CONNECTOR', 'FASTENER', 'STRUCTURE', 'HT CABLE', 'LT CABLE')) or \
               any(k in n for k in ('SUPPLY', 'RECEIPT', 'DELIVERY', 'MANUFACTURING', 'MDCC', 'DISPATCH', 'PO RELEASE', 'ORDER')):
                return 'Procurement'
            return 'Construction'

        buckets = {'Engineering': [], 'Procurement': [], 'Construction': []}
        for a in acts:
            cat = _classify(a[0], a[6])
            buckets[cat].append(a)

        weights = {'Engineering': 0.15, 'Procurement': 0.30, 'Construction': 0.55}

        # Gap Analysis Table (Parameters from Image 2)
        tot_w_pln = 0.0
        tot_w_act = 0.0
        for cat in ('Engineering', 'Procurement', 'Construction'):
            w = weights[cat]
            c_acts = buckets[cat]
            tot = len(c_acts) or 1
            pln = (sum(1 for a in c_acts if (a[3] or a[2]) and (a[3] or a[2]) <= as_of) / tot) * 100
            act = (sum(1 for a in c_acts if a[1] == 'Completed') / tot) * 100
            var = max(0, pln - act)
            gap_analysis.append({
                "parameter": cat,
                "weight": f"{int(w * 100)}%",
                "plan": f"{round(pln)}%",
                "actual": f"{round(act)}%",
                "variance": f"{round(var)}%",
                "remark": ""
            })
            tot_w_pln += w * pln
            tot_w_act += w * act

        gap_analysis.append({
            "parameter": "Total",
            "weight": "100%",
            "plan": f"{round(tot_w_pln)}%",
            "actual": f"{round(tot_w_act)}%",
            "variance": f"{round(max(0, tot_w_pln - tot_w_act))}%",
            "remark": ""
        })

        # Month definitions across FY26-27 (Apr-26 to Mar-27)
        month_defs = [
            ("Apr-26", datetime(2026, 4, 30, 23, 59, 59)),
            ("May-26", datetime(2026, 5, 31, 23, 59, 59)),
            ("Jun-26", datetime(2026, 6, 30, 23, 59, 59)),
            ("Jul-26", datetime(2026, 7, 31, 23, 59, 59)),
            ("Aug-26", datetime(2026, 8, 31, 23, 59, 59)),
            ("Sep-26", datetime(2026, 9, 30, 23, 59, 59)),
            ("Oct-26", datetime(2026, 10, 31, 23, 59, 59)),
            ("Nov-26", datetime(2026, 11, 30, 23, 59, 59)),
            ("Dec-26", datetime(2026, 12, 31, 23, 59, 59)),
            ("Jan-27", datetime(2027, 1, 31, 23, 59, 59)),
            ("Feb-27", datetime(2027, 2, 28, 23, 59, 59)),
            ("Mar-27", datetime(2027, 3, 31, 23, 59, 59)),
        ]
        pre_apr_date = datetime(2026, 3, 31, 23, 59, 59)

        cat_cum_plan = {}
        cat_cum_act = {}
        for cat in ('Engineering', 'Procurement', 'Construction'):
            c_acts = buckets[cat]
            tot = len(c_acts) or 1
            cat_cum_plan[cat] = {}
            cat_cum_act[cat] = {}
            cat_cum_plan[cat]["Base"] = (sum(1 for a in c_acts if (a[3] or a[2]) and (a[3] or a[2]) <= pre_apr_date) / tot) * 100
            cat_cum_act[cat]["Base"] = (sum(1 for a in c_acts if a[1] == 'Completed' and a[5] and a[5] <= pre_apr_date) / tot) * 100
            for m_label, m_date in month_defs:
                pln_c = sum(1 for a in c_acts if (a[3] or a[2]) and (a[3] or a[2]) <= m_date)
                cat_cum_plan[cat][m_label] = (pln_c / tot) * 100
                if m_date <= as_of or (m_date.year == as_of.year and m_date.month == as_of.month):
                    act_c = sum(1 for a in c_acts if a[1] == 'Completed' and (not a[5] or a[5] <= m_date))
                    in_prog = sum(0.5 for a in c_acts if a[1] == 'In Progress' and a[4] and a[4] <= m_date)
                    cat_cum_act[cat][m_label] = ((act_c + in_prog) / tot) * 100
                else:
                    cat_cum_act[cat][m_label] = None

        prev_cum_p = sum(weights[c] * cat_cum_plan[c]["Base"] for c in weights)
        prev_cum_a = sum(weights[c] * cat_cum_act[c]["Base"] for c in weights)

        for m_label, m_date in month_defs:
            cum_p = sum(weights[c] * cat_cum_plan[c][m_label] for c in weights)
            month_p = max(0.0, cum_p - prev_cum_p)
            prev_cum_p = cum_p

            act_vals = [cat_cum_act[c][m_label] for c in weights]
            if all(v is not None for v in act_vals):
                cum_a = sum(weights[c] * v for c, v in zip(weights.keys(), act_vals))
                month_a = max(0.0, cum_a - prev_cum_a) if prev_cum_a is not None else 0.0
                prev_cum_a = cum_a
            else:
                cum_a = None
                month_a = None

            scurve_monthly.append({
                "month": m_label,
                "monthly_plan": round(month_p, 2),
                "monthly_actual": round(month_a, 2) if month_a is not None else None,
                "cum_plan": round(cum_p, 2),
                "cum_actual": round(cum_a, 2) if cum_a is not None else None,
            })

    progress = fetch_khavda_solar_progress(db)

    def _latest(idx):
        ds = [p[idx] for p in p6_projects if p[idx]]
        return max(ds).strftime("%d-%b-%y") if ds else "-"

    return {
        "as_of": date.today().isoformat(),
        "progress": progress,
        "page_notes": {**_progress_notes(progress), **_commissioning_notes(progress)},
        "cod_plan": _latest(3),
        "cod_expected": _latest(2),
        "total_capacity_mw": tot_cap,
        "commissioned_mw": tot_comm,
        "plots": plots,
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


def _fit_plot_rows(slide, tbl_shape, n_plots: int):
    """Grow or trim the table to one row per plot (plus heading and total), and
    size the rows and text so the whole table stays on the page. The template
    holds fewer rows than the register has plots; dropping the rest would leave
    a Total that does not match the rows shown."""
    tbl = tbl_shape.table
    trs = tbl._tbl.tr_lst
    want = n_plots + 2                      # heading + plots + total
    while len(trs) > want:                  # trim data rows, keeping heading and total
        tbl._tbl.remove(trs[-2])
        trs = tbl._tbl.tr_lst
    while len(trs) < want:                  # clone a body row ahead of the total
        trs[-1].addprevious(copy.deepcopy(trs[1]))
        trs = tbl._tbl.tr_lst
    prs_h = slide.part.package.presentation_part.presentation.slide_height
    avail = prs_h - tbl_shape.top - Emu(230_000)
    row_h = int(min(avail / want, 280_000))
    for row in tbl.rows:
        row.height = Emu(row_h)
    return Pt(max(6, min(10, row_h / 12700 * 0.62)))


def _size_plot_rows(tbl, size) -> None:
    """Uniform small text: empty cells keep their end-of-paragraph size, which
    otherwise sets a minimum row height."""
    last = len(tbl.rows) - 1
    for r in range(len(tbl.rows)):
        for c in range(len(tbl.columns)):
            cell = tbl.cell(r, c)
            cell.margin_top = cell.margin_bottom = Emu(0)
            for para in cell.text_frame.paragraphs:
                for run in para.runs:
                    run.font.size = size
                    if r > 0:
                        run.font.bold = (r == last)
                para._p.get_or_add_endParaRPr().set("sz", str(int(size.pt * 100)))


def _fill_slide_7(slide, data: Dict[str, Any]):
    """Slide 7: Solar Plot wise Development."""
    tbl_shape = next((sh for sh in slide.shapes if getattr(sh, "has_table", False)), None)
    if not tbl_shape:
        return
    tbl = tbl_shape.table
    plots = data.get("plots", [])
    size = _fit_plot_rows(slide, tbl_shape, len(plots))
    _clear_table_data(tbl, start_row=1, start_col=0)

    tot_row_idx = len(tbl.rows) - 1
    for idx, p in enumerate(plots):
        r = idx + 1
        _set_cell_text(tbl, r, 0, p["category"])
        _set_cell_text(tbl, r, 1, p["spv"])
        _set_cell_text(tbl, r, 2, p["plot"])
        _set_cell_text(tbl, r, 3, _fmt(p["capacity"]))
        _set_cell_text(tbl, r, 4, _fmt(p["commissioned"]) if p["commissioned"] > 0 else "-")

    _set_cell_text(tbl, tot_row_idx, 0, "Total")
    _set_cell_text(tbl, tot_row_idx, 1, "")
    _set_cell_text(tbl, tot_row_idx, 2, "")
    _set_cell_text(tbl, tot_row_idx, 3, _fmt(data.get("total_capacity_mw", 0)))
    _set_cell_text(tbl, tot_row_idx, 4, _fmt(data.get("commissioned_mw", 0)))
    _size_plot_rows(tbl, size)


def _fill_slide_8(slide, data: Dict[str, Any]):
    """Slide 8: Physical Progress S-Curve & Gap Analysis."""
    tbl_shape = next((sh for sh in slide.shapes if getattr(sh, "has_table", False)), None)
    gap_rows = data.get("gap_analysis", [])
    if tbl_shape and gap_rows:
        tbl = tbl_shape.table
        for idx, g in enumerate(gap_rows):
            r = idx + 2  # Gap analysis data rows start at row 2
            if r < len(tbl.rows):
                _set_cell_text(tbl, r, 0, g["parameter"])
                _set_cell_text(tbl, r, 1, g["weight"])
                _set_cell_text(tbl, r, 2, g["plan"])
                _set_cell_text(tbl, r, 3, g["actual"])
                _set_cell_text(tbl, r, 4, g["variance"])
                _set_cell_text(tbl, r, 5, g.get("remark", ""))

    # Update chart if present
    chart_shape = next((sh for sh in slide.shapes if getattr(sh, "has_chart", False)), None)
    monthly = data.get("scurve_monthly", [])
    if chart_shape and monthly:
        try:
            cd = CategoryChartData(number_format="0.00%")
            cd.categories = [m["month"] for m in monthly]
            cd.add_series("Monthly Plan", [m["monthly_plan"] / 100 for m in monthly])
            cd.add_series("Monthly Actual", [None if m["monthly_actual"] is None else m["monthly_actual"] / 100 for m in monthly])
            cd.add_series("Cumm. Plan", [m["cum_plan"] / 100 for m in monthly])
            cd.add_series("Cumm. Actual", [None if m["cum_actual"] is None else m["cum_actual"] / 100 for m in monthly])
            replace_chart_data(chart_shape.chart, cd)
            try:
                chart_shape.chart.has_legend = False
            except Exception:
                pass
        except Exception:
            pass


# ── Procurement, Construction Progress, Manpower (P6, summed over the projects) ──
_MONTH_LABEL = re.compile(r"\b(Aug|Sep|Oct|Nov)([\u2019'\-])26\b")


def _relabel_months(tbl, header_rows: int = 2) -> None:
    """The template's headings are Aug-26 (data month) then Sep / Oct / Nov;
    follow today's date, as the Rajasthan pack does."""
    today = date.today()

    def month(k: int):
        y, m = divmod(today.year * 12 + today.month - 1 + k, 12)
        return date(y, m + 1, 1)

    names = {"Aug": month(0), "Sep": month(1), "Oct": month(2), "Nov": month(3)}

    def sub(m):
        d = names[m.group(1)]
        return f"{d.strftime('%b')}{m.group(2)}{d.strftime('%y')}"

    for r in range(min(header_rows, len(tbl.rows))):
        for c in range(len(tbl.columns)):
            for p in tbl.cell(r, c).text_frame.paragraphs:
                full = "".join(run.text for run in p.runs)
                if p.runs and _MONTH_LABEL.search(full):
                    p.runs[0].text = _MONTH_LABEL.sub(sub, full)
                    for run in p.runs[1:]:
                        run.text = ""


_FRACTIONAL = {"km", "mwdc", "mwac", "mw"}


def _q(v, uom: str, zero: str = "-") -> str:
    """The Khavda template groups digits in thousands (1,574,829); one decimal
    only where the unit is fractional and the quantity is not whole."""
    if v is None:
        return "-"
    if abs(v) < 0.05:
        return zero
    if uom.strip().lower() in _FRACTIONAL and abs(v - round(v)) >= 0.05:
        return f"{v:,.1f}"
    return f"{round(v):,}"


def _table(slide):
    sh = next((s for s in slide.shapes if getattr(s, "has_table", False)), None)
    return sh.table if sh else None


def _fill_slide_10(slide, data: Dict[str, Any]):
    """Procurement & Supply Status. Cols: 2 UOM, 3 Scope, 4 Ordered, 5 Balance,
    6 Delivered, 7-9 forecast months."""
    tbl = _table(slide)
    if tbl is None:
        return
    _relabel_months(tbl)
    for i, r in enumerate(data["progress"]["procurement"]["rows"]):
        row = 2 + i
        if r is None or row >= len(tbl.rows):
            continue
        u = r["uom"]
        _set_cell_text(tbl, row, 2, u)
        _set_cell_text(tbl, row, 3, _q(r["scope"], u))
        _set_cell_text(tbl, row, 4, _q(r["ordered"], u, "0"))
        _set_cell_text(tbl, row, 5, _q(r["balance"], u, "0"))
        _set_cell_text(tbl, row, 6, _q(r["delivered"], u, "0"))
        for k, v in enumerate(r["forecast"]):
            _set_cell_text(tbl, row, 7 + k, _q(v, u))


def _fill_slide_11(slide, data: Dict[str, Any]):
    """Construction Progress. Cols: 2 UOM, 3 Scope, 4 Completed, 5 Balance,
    6 Month Plan, 7 Month Actual, 8-10 forecast months, 11 Completion Target."""
    tbl = _table(slide)
    if tbl is None:
        return
    _relabel_months(tbl)
    for i, r in enumerate(data["progress"]["construction"]["rows"]):
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


def _fill_slide_12(slide, data: Dict[str, Any]):
    """Construction Manpower. Cols: 2 UOM, 3 Scope, 4 Completed, 5 Balance,
    6-8 next three months' manpower; the last row totals them."""
    tbl = _table(slide)
    if tbl is None:
        return
    _relabel_months(tbl)
    man = data["progress"]["manpower"]
    shown = [r for r in man["rows"] if r]
    for i, r in enumerate(shown):
        row = 2 + i
        if row >= len(tbl.rows) - 1:
            break
        u = r["uom"]
        _set_cell_text(tbl, row, 2, u)
        _set_cell_text(tbl, row, 3, _q(r["scope"], u))
        _set_cell_text(tbl, row, 4, _q(r["completed"], u, "0"))
        _set_cell_text(tbl, row, 5, _q(r["balance"], u, "0"))
        for k, v in enumerate(r["forecast"]):
            _set_cell_text(tbl, row, 6 + k, f"{v:,}" if v else "-")
    last = len(tbl.rows) - 1
    for k, v in enumerate(man["total"]):
        _set_cell_text(tbl, last, 6 + k, f"{v:,}" if v else "-")


def _coverage(rows) -> str:
    return ", ".join(f"{r['label']} {r['n']}" for r in rows if r)


def _progress_notes(progress: Dict[str, Any]) -> Dict[int, List[str]]:
    n = progress["n_projects"]
    proc, cons = progress["procurement"], progress["construction"]
    return {
        10: [
            f"P6 Material resources '<item> - Supply', summed over the {n} Solar Khavda projects. Units are P6's (Module in MWdc, MMS in tables, cables in km).",
            "Scope = planned units; Delivered = actual units as of each project's P6 data date; forecast months = units still due on lots not yet received, by P6 forecast finish. Work due this month or overdue sits in the first forecast month.",
            "A project counts in a row only when P6's supply quantity agrees with its own construction quantity for the item (within 10%). Projects counted: " + _coverage(proc["rows"]) + f" (of {n}).",
            "Ordering Completed / Balance Ordering are shown only when P6 states the 'LOI / PO Release' milestone for every project in the row: a released package counts as fully ordered, an unreleased one as not yet ordered. '-' otherwise.",
        ],
        11: [
            f"P6 Material resources '<item> - Construction' (installed units), summed over the {n} Solar Khavda projects. Scope = P6's planned quantity; Balance = Scope - Completed.",
            "Transformer / IDT foundation, slab, shed and foundation-completion rows count block activities weighted by each block's IDT count; MC4 & VOC counts a block only when both steps are done, in that block's module MWdc.",
            "Month Plan = units with a baseline finish this month. Month Actual shows '-' unless every project's P6 data date reaches this month (no actuals reported yet, not zero). Next 3 months = units still open by P6 forecast finish; work due this month or overdue sits in the first month. Completion Target = latest forecast finish of open work.",
            "Inference: Piling = 'Piling Stub - MMS' units (one stub per pile); Tracker rows = MMS Rafter and Bracing table quantities; Transformer foundation completion = 'IDT Foundation - Grade Slab Casting & Dyke Wall'.",
        ],
        12: [
            "Quantities as on the Construction Progress page. Manpower = P6 Labor remaining hours / 8 = mandays, spread evenly over each activity's remaining window (later of its start and the P6 data date, to its forecast finish), divided by the days in the month.",
            "Inference, not a headcount plan: P6 loads labour on activities, not on named crews. Work finishing before the first month shown is not included, and rows with no Labor in P6 are left empty.",
        ],
    }


def _mw(v) -> str:
    return "-" if not v or abs(v) < 0.5 else f"{round(v):,}"


def _fill_slide_3(slide, data: Dict[str, Any]):
    """Executive Summary (Solar row). MW columns are P6 block COD, FY month window."""
    tbl = _table(slide)
    if tbl is None or len(tbl.rows) < 3:
        return
    _relabel_months(tbl)
    c = data["progress"]["commissioning"]
    r = 2
    _set_cell_text(tbl, r, 0, "1")
    _set_cell_text(tbl, r, 1, "GJ")
    _set_cell_text(tbl, r, 2, "Khavda-Solar")
    _set_cell_text(tbl, r, 3, _mw(sum(c["budget"])))
    _set_cell_text(tbl, r, 4, _mw(c["planned_to_date"]))
    _set_cell_text(tbl, r, 5, _mw(c["commissioned"]))
    _set_cell_text(tbl, r, 6, data.get("cod_plan", "-"))
    _set_cell_text(tbl, r, 7, data.get("cod_expected", "-"))
    _set_cell_text(tbl, r, 8, data.get("overall_plan_pct", "-"))
    _set_cell_text(tbl, r, 9, data.get("overall_act_pct", "-"))
    _set_cell_text(tbl, r, 10, "-")


def _fill_slide_4(slide, data: Dict[str, Any]):
    """Commissioning: Plan vs Forecast. BUDGET = block COD at its baseline finish;
    ACTUAL / FCST = COD at its actual finish, or P6 forecast finish if still open."""
    tbl = _table(slide)
    if tbl is None:
        return
    c = data["progress"]["commissioning"]
    b_row, a_row = 2, (3 if len(tbl.rows) == 4 else 4)
    for row, vals in ((b_row, c["budget"]), (a_row, c["actual"])):
        for k, v in enumerate(vals):
            _set_cell_text(tbl, row, 2 + k, _mw(v))
        _set_cell_text(tbl, row, 14, _mw(sum(vals)))

    chart_shape = next((sh for sh in slide.shapes if getattr(sh, "has_chart", False)), None)
    if chart_shape:
        try:
            cd = CategoryChartData(number_format="#,##0")
            cd.categories = list(chart_shape.chart.plots[0].categories)
            cd.add_series("Budget", [v or None for v in c["budget"]])
            cd.add_series("Actual / Fcst", [v or None for v in c["actual"]])
            replace_chart_data(chart_shape.chart, cd)
        except Exception:
            pass


def _fill_slide_6(slide, data: Dict[str, Any]):
    """Salient Features: capacity from the register; commissioning by quarter and
    the end date from P6 block COD."""
    tbl = _table(slide)
    if tbl is None:
        return
    c = data["progress"]["commissioning"]
    _set_cell_text(tbl, 1, 1, f"{data.get('total_capacity_mw', 0):,.0f} MW")
    if c["last_cod"]:
        _set_cell_text(tbl, 5, 1, f"Progressively up to {c['last_cod']}")
    for row, vals in ((11, c["budget"]), (12, c["actual"])):
        if row >= len(tbl.rows):
            continue
        q = [sum(vals[i:i + 3]) for i in (0, 3, 6, 9)]
        for k, v in enumerate(q):
            _set_cell_text(tbl, row, 1 + k, _mw(v))
        _set_cell_text(tbl, row, 5, _mw(sum(q)))


def _fill_slide_14(slide, data: Dict[str, Any]):
    """Major Milestone - Next 3 months: plots whose First Time Charging is due in
    each month (P6 forecast finish, MW from the block split)."""
    tbl = _table(slide)
    if tbl is None:
        return
    _relabel_months(tbl, header_rows=1)
    charging = data["progress"]["commissioning"]["charging"]
    first, last = 3, len(tbl.rows) - 3          # body rows; the row after them is Total
    room = last - first + 1
    ref = next((r.font.size for p in tbl.cell(first, 0).text_frame.paragraphs for r in p.runs if r.font.size), Pt(12))
    for k, plots in enumerate(charging):
        shown = plots
        if len(plots) > room:
            rest = plots[room - 1:]
            shown = plots[: room - 1] + [(f"Others ({len(rest)} plots)", sum(mw for _, mw in rest))]
        for i, (plot, mw) in enumerate(shown):
            _set_cell_text(tbl, first + i, 2 * k, plot)
            _set_cell_text(tbl, first + i, 2 * k + 1, _mw(mw))
        _set_cell_text(tbl, last + 1, 2 * k + 1, _mw(sum(mw for _, mw in plots)))
    # The template's lower body rows carry a larger font; use the first row's throughout.
    for row in range(first, last + 1):
        for col in range(len(tbl.columns)):
            for para in tbl.cell(row, col).text_frame.paragraphs:
                for run in para.runs:
                    run.font.size = ref
                para._p.get_or_add_endParaRPr().set("sz", str(int(ref.pt * 100)))


def _fill_slide_15(slide, data: Dict[str, Any]):
    """Khavda PSS Status from the PSS charging milestones in the solar projects' P6."""
    tbl = _table(slide)
    if tbl is None:
        return
    for i, r in enumerate(data["progress"]["pss"]):
        row = 1 + i
        if r is None or row >= len(tbl.rows):
            continue
        _set_cell_text(tbl, row, 1, r["baseline"])
        for k, d in enumerate(r["charging"]):
            _set_cell_text(tbl, row, 2 + k, d)


def _fill_slide_28(slide, data: Dict[str, Any]):
    """Tracker & Robot Installation Status: only the robot count P6 holds."""
    tbl = _table(slide)
    rob = data["progress"].get("robots")
    if tbl is None or not rob:
        return
    row = next((r for r in range(len(tbl.rows)) if tbl.cell(r, 0).text_frame.text.strip().lower() == "grand total"), None)
    if row is None or row + 1 >= len(tbl.rows):
        return
    _set_cell_text(tbl, row, 4, f"{rob['total']:,.0f}")
    _set_cell_text(tbl, row, 5, f"{rob['installed']:,.0f}")
    _set_cell_text(tbl, row + 1, 4, "100%")
    _set_cell_text(tbl, row + 1, 5, f"{round(100 * rob['installed'] / rob['total'])}%")


def _commissioning_notes(progress: Dict[str, Any]) -> Dict[int, List[str]]:
    c = progress["commissioning"]
    n = progress["n_projects"]
    block = (f"P6 block COD / First Time Charging milestones of the {n} Solar Khavda projects. P6 holds no block capacity, so each project's "
             "registered MWac is split over its blocks in proportion to P6's module MWdc per block (the blocks add back to the register).")
    cover = (f"Covers {c['capacity']:,.0f} MW of the register's solar capacity (the plots with a P6 schedule). "
             f"{c['outside_budget']:,.0f} MW (budget) and {c['outside_actual']:,.0f} MW (actual / forecast) fall outside this financial year and are not shown.")
    return {
        3: [block, "FY27 Plan = budget COD in this financial year; Planned till = all budget COD due by today (carry-forward included); Actual till = all completed COD. "
            "Plan / Actual % are activity counts (completed / total); COD dates are the latest P6 baseline / forecast finish.", cover],
        4: [block, "BUDGET = COD at its P6 baseline finish month; ACTUAL / FCST = COD at its actual finish, or P6 forecast finish while open.", cover],
        6: [block, "Capacity is the register's. Commissioning by quarter and 'Progressively up to' (latest forecast COD of open blocks) are from P6.",
            "Owner, location, land area and configuration are not held in P6 or the register, so they are left empty."],
        14: [block, "Plots with First Time Charging due in each month, by P6 forecast finish; work due this month or overdue sits in the first month. "
             "Plot is read from the P6 project name (the register's plot is blank or differs for a few)."],
        15: ["PSS charging milestones held in the solar projects' P6 ('PSS-xx Charging ...'), one per connecting project. Base Line Date = earliest baseline; "
             "Charging Date P1-P3 = distinct actual / forecast dates in order (first three). Inference: P1-P3 are date order, not named phases. "
             "Rows with no such milestone (PSS-18) are empty."],
        28: ["Only the robot count is held in P6: Total = 'Robots - Construction' planned units, Installation = actual units, summed over the projects. "
             "Tracker, online, RFI and auto-run figures are not in P6 or the register and are left empty."],
    }


def build_solar_deck(data: Dict[str, Any]) -> bytes:
    """Build the dynamic Khavda Solar deck bytes."""
    prs = Presentation(str(REFERENCE))
    scrub_deck(prs, _SPECS, _BLANK_CHARTS, _BLANK_TEXT)
    _fill_slide_1(prs.slides[0], _ordinal_date(date.today()))
    fills = {3: _fill_slide_3, 4: _fill_slide_4, 6: _fill_slide_6, 7: _fill_slide_7, 8: _fill_slide_8,
             10: _fill_slide_10, 11: _fill_slide_11, 12: _fill_slide_12, 14: _fill_slide_14,
             15: _fill_slide_15, 28: _fill_slide_28}
    for n, fill in fills.items():
        if len(prs.slides) >= n:
            fill(prs.slides[n - 1], data)

    bio = BytesIO()
    prs.save(bio)
    return bio.getvalue()
