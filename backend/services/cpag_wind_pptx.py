"""
CPAG Wind PPTX builder.

Takes the approved template deck and injects live data from P6 + SAP into
the correct table cells while preserving all formatting.
"""
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List
from pptx import Presentation
from datetime import datetime

REFERENCE = Path(__file__).resolve().parent.parent / "assets" / "cpag_wind_reference.pptx"


# ── Helpers ─────────────────────────────────────────────────────────────────

def _replace_text_preserve_format(shape, old_text: str, new_text: str):
    """Replace text in a shape's text frame while keeping run-level formatting."""
    if not shape.has_text_frame:
        return
    for paragraph in shape.text_frame.paragraphs:
        for run in paragraph.runs:
            if old_text in run.text:
                run.text = run.text.replace(old_text, new_text)


def _set_cell_text(table, row: int, col: int, value: str):
    """Set the text of the first run in a table cell, preserving formatting."""
    cell = table.cell(row, col)
    for p in cell.text_frame.paragraphs:
        if p.runs:
            p.runs[0].text = str(value)
            # Clear remaining runs in same paragraph
            for r in p.runs[1:]:
                r.text = ""
            return
    # Fallback: set text directly if no runs exist
    cell.text_frame.paragraphs[0].text = str(value)


def _clear_table_data(table, start_row: int = 1):
    """Clear all data rows in a table (preserve header rows)."""
    for row in range(start_row, len(table.rows)):
        for cell in table.rows[row].cells:
            for paragraph in cell.text_frame.paragraphs:
                for run in paragraph.runs:
                    run.text = ""


def _remove_shape(shape):
    """Remove a shape from its slide."""
    sp = shape._element
    sp.getparent().remove(sp)


# ── Slide builders ──────────────────────────────────────────────────────────

def _fill_slide_1(prs, data: Dict[str, Any]):
    """Slide 1: CPAG – Energy Cluster cover. Replace date."""
    slide = prs.slides[0]
    current_date = datetime.now().strftime("%d-%b-%Y") # Always use today's date
    for shape in slide.shapes:
        _replace_text_preserve_format(shape, "Aug-26", current_date)


def _fill_slide_3(prs, data: Dict[str, Any]):
    """Slide 3 (Index 2): Executive Summary."""
    if len(prs.slides) <= 2:
        return
    proj = data.get("project", {})
    s_curve = data.get("s_curve", {})
    gap_data = s_curve.get("gap_analysis", [])
    total_gap = next((g for g in gap_data if g.get("parameter") == "Total"), {})
    
    slide = prs.slides[2]
    for sh in slide.shapes:
        if not getattr(sh, "has_table", False):
            continue
        tbl = sh.table
        _clear_table_data(tbl, start_row=2)
        if len(tbl.rows) > 2:
            r = 2
            # Col 0: Location (not in DB)
            _set_cell_text(tbl, r, 0, "-")
            # Col 1: Project Name
            name = proj.get("project_name", "")
            cap = proj.get("capacity_mw", "")
            if cap:
                _set_cell_text(tbl, r, 1, f"{name} (Project capacity: {cap} MW)")
            else:
                _set_cell_text(tbl, r, 1, name)
            # Col 2, 3, 4: FY MW and AOP Plan (not in DB)
            _set_cell_text(tbl, r, 2, "-")
            _set_cell_text(tbl, r, 3, "-")
            _set_cell_text(tbl, r, 4, "-")
            # Col 5: COD (Achieved/Expected)
            _set_cell_text(tbl, r, 5, proj.get("cod_expected", "-"))
            # Col 6: Plan Progress
            _set_cell_text(tbl, r, 6, total_gap.get("plan", "-"))
            # Col 7: Actual Progress
            _set_cell_text(tbl, r, 7, total_gap.get("actual", "-"))
            # Col 8: Remarks
            _set_cell_text(tbl, r, 8, "-")
        break


def _fill_slide_5(prs, data: Dict[str, Any]):
    """Slide 5 (Index 4): Salient Features — inject project info."""
    if len(prs.slides) <= 4:
        return
    proj = data.get("project", {})
    slide = prs.slides[4]
    for sh in slide.shapes:
        if not getattr(sh, "has_table", False):
            continue
        tbl = sh.table
        # Row 0: Project name
        _set_cell_text(tbl, 0, 1, proj.get("project_name", ""))
        # Row 1: Capacity
        cap = proj.get('capacity_mw')
        _set_cell_text(tbl, 1, 1, f"{cap} MW" if cap else "")
        # Row 2: SPV/Developer
        _set_cell_text(tbl, 2, 1, proj.get("spv", ""))
        # Row 3: Location
        _set_cell_text(tbl, 3, 1, proj.get("location", ""))
        # Row 7: WTG type
        wtg = proj.get('wtg_mw')
        _set_cell_text(tbl, 7, 1, f"ANIL {wtg}MW" if wtg else "")
        
        # Clear out the hardcoded commissioning values at the bottom of the template table
        if len(tbl.rows) > 11 and len(tbl.columns) > 5:
            from pptx.enum.text import PP_ALIGN
            try:
                from pptx.enum.text import MSO_ANCHOR
            except ImportError:
                MSO_ANCHOR = None
                
            for r_idx in (10, 11):
                for c_idx in range(1, 6):
                    _set_cell_text(tbl, r_idx, c_idx, "-")
                    cell = tbl.cell(r_idx, c_idx)
                    if MSO_ANCHOR:
                        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
                    for p in cell.text_frame.paragraphs:
                        p.alignment = PP_ALIGN.CENTER
        break


def _fill_slide_8(prs, data: Dict[str, Any]):
    """Slide 8 (Index 7): Procurement & Supply Status — inject SAP PO data."""
    if len(prs.slides) <= 7:
        return
    procurement = data.get("procurement", [])
    slide = prs.slides[7]
    for sh in slide.shapes:
        if not getattr(sh, "has_table", False):
            continue
        tbl = sh.table
        
        import datetime
        from dateutil.relativedelta import relativedelta
        current_date = datetime.datetime.now()
        
        # Update headers dynamically
        if len(tbl.rows) > 1 and len(tbl.columns) > 9:
            preceding = current_date - relativedelta(months=1)
            _set_cell_text(tbl, 0, 5, f"Delivered at Site up to {preceding.strftime('%b')}'{preceding.strftime('%y')}")
            for i in range(1, 4):
                next_m = current_date + relativedelta(months=i)
                _set_cell_text(tbl, 1, 6 + i, next_m.strftime("%b-%y"))
                
        num_cols = len(tbl.columns)
        # We don't clear the table here because we want to keep the package names and UOMs
        # from the template, just update the numbers.
        max_rows = min(len(procurement), len(tbl.rows) - 2)
        for i in range(max_rows):
            row_idx = i + 2  # Skip 2 header rows
            p = procurement[i]
            # Col 0: Sr No (Keep from template)
            # Col 1: Packages (Keep from template)
            # Col 2: UOM (Keep from template)
            _set_cell_text(tbl, row_idx, 3, str(p.get("scope", "")))
            _set_cell_text(tbl, row_idx, 4, str(p.get("ordered", "")))
            _set_cell_text(tbl, row_idx, 5, str(p.get("delivered", "")))
            _set_cell_text(tbl, row_idx, 6, str(p.get("balance", "")))
            # Clear the rolling plan columns for now as they require complex P6 mapping
            for c in range(7, 10):
                if num_cols > c:
                    _set_cell_text(tbl, row_idx, c, "-")
        break


def _fill_slide_9(prs, data: Dict[str, Any]):
    """Slide 9 (Index 8): Construction Progress Update — inject P6 activity counts."""
    if len(prs.slides) <= 8:
        return
    construction = data.get("construction_progress", [])
    slide = prs.slides[8]
    for sh in slide.shapes:
        if not getattr(sh, "has_table", False):
            continue
        tbl = sh.table
        import datetime
        from dateutil.relativedelta import relativedelta
        current_date = datetime.datetime.now()
        
        # Update headers
        if len(tbl.rows) > 1 and len(tbl.columns) > 9:
            preceding = current_date - relativedelta(months=1)
            _set_cell_text(tbl, 0, 5, f"Preceding Month {preceding.strftime('%b')}'{preceding.strftime('%y')}")
            for i in range(1, 4):
                next_m = current_date + relativedelta(months=i)
                _set_cell_text(tbl, 1, 6 + i, next_m.strftime("%b-%y"))

        # Data rows start at row 2
        max_rows = min(len(construction), len(tbl.rows) - 2)
        for i in range(max_rows):
            row_idx = i + 2
            c = construction[i]
            # Col 0: Activity (Keep from template)
            # Col 1: UOM (Keep from template, but fix alignment)
            from pptx.enum.text import PP_ALIGN
            try:
                from pptx.enum.text import MSO_ANCHOR
                tbl.cell(row_idx, 1).vertical_anchor = MSO_ANCHOR.MIDDLE
            except ImportError:
                pass
            for p in tbl.cell(row_idx, 1).text_frame.paragraphs:
                p.alignment = PP_ALIGN.CENTER
            
            # Col 2: Scope
            _set_cell_text(tbl, row_idx, 2, str(c.get("scope", "")))
            # Col 3: Completed
            _set_cell_text(tbl, row_idx, 3, str(c.get("completed", "")))
            # Col 4: Balance
            balance = max(0, c.get("scope", 0) - c.get("completed", 0))
            _set_cell_text(tbl, row_idx, 4, str(balance))
            # Col 5: Preceding Month Plan (raw number, not %)
            _set_cell_text(tbl, row_idx, 5, "-") 
            # Col 6: Preceding Month Actual
            _set_cell_text(tbl, row_idx, 6, "-")
            # Col 7-9: Next 3 Months
            for c_idx in range(7, 10):
                if len(tbl.columns) > c_idx:
                    _set_cell_text(tbl, row_idx, c_idx, "-")
            # Col 10: Completion Target
            if len(tbl.columns) > 10:
                _set_cell_text(tbl, row_idx, 10, c.get("target_date", "-"))
        break


def _fill_slide_10(prs, data: Dict[str, Any]):
    """Slide 10 (Index 9): Major Milestones — inject P6 milestone data."""
    if len(prs.slides) <= 9:
        return
    milestones = data.get("milestones", [])
    slide = prs.slides[9]
    for sh in slide.shapes:
        if not getattr(sh, "has_table", False):
            continue
        tbl = sh.table
        _clear_table_data(tbl, start_row=1)
        
        import datetime
        from dateutil.relativedelta import relativedelta
        
        current_date = datetime.datetime.now()
            
        months = []
        for i in range(1, 4):
            months.append(current_date + relativedelta(months=i))
            
        if len(tbl.columns) >= 3:
            for c in range(3):
                _set_cell_text(tbl, 0, c, months[c].strftime("%b-%y"))
                
        col_data = {0: [], 1: [], 2: []}
        for m in milestones:
            plan_str = m.get("plan_date", "-")
            try:
                plan_d = datetime.datetime.strptime(plan_str, "%Y-%m-%d")
                for c in range(3):
                    if plan_d.year == months[c].year and plan_d.month == months[c].month:
                        col_data[c].append(m.get("milestone", ""))
            except Exception:
                pass
                
        max_items = max((len(col_data[c]) for c in range(3)), default=0)
        max_rows = len(tbl.rows) - 1
        
        for row_i in range(min(max_items, max_rows)):
            row_idx = row_i + 1
            for c in range(3):
                val = col_data[c][row_i] if row_i < len(col_data[c]) else ""
                if len(tbl.columns) > c:
                    _set_cell_text(tbl, row_idx, c, val)
def _remove_shape(shape):
    """Remove a shape from a slide."""
    sp = shape._element
    sp.getparent().remove(sp)

def _fill_slide_7(prs, data: Dict[str, Any]):
    """Slide 7 (Index 6): Overall S Curve — inject chart image and gap analysis table."""
    if len(prs.slides) <= 6:
        return
    s_curve = data.get("s_curve", {})
    gap_analysis = s_curve.get("gap_analysis", [])
    chart_data = s_curve.get("chart", {})
    
    slide = prs.slides[6]
    chart_shape = None
    chart_box = None
    
    for sh in list(slide.shapes):
        if getattr(sh, "has_table", False):
            tbl = sh.table
            max_rows = min(len(gap_analysis), len(tbl.rows) - 2)
            for i in range(max_rows):
                row_idx = i + 2
                g = gap_analysis[i]
                _set_cell_text(tbl, row_idx, 0, g.get("parameter", ""))
                _set_cell_text(tbl, row_idx, 1, g.get("weight", ""))
                _set_cell_text(tbl, row_idx, 2, g.get("plan", ""))
                _set_cell_text(tbl, row_idx, 3, g.get("actual", ""))
                _set_cell_text(tbl, row_idx, 4, g.get("variance", ""))
                if len(tbl.columns) > 5:
                    _set_cell_text(tbl, row_idx, 5, "")
        elif getattr(sh, "has_chart", False):
            chart_shape = sh
            # Save position
            chart_box = (sh.left, sh.top, sh.width, sh.height)
            
    if chart_shape and chart_data and chart_data.get("categories"):
        from services.cpag_pptx import (
            _chart_in_box, _move_to_line, _light_gridlines, 
            _add_data_table, _series_fill, _label_last,
            SERIES_BLUE, SERIES_GREEN, LINE_GREEN
        )
        from pptx.chart.data import CategoryChartData
        from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION
        from pptx.util import Pt
        
        cats = chart_data.get("categories", [])
        cd = CategoryChartData(number_format="0.00%")
        cd.categories = cats
        cd.add_series("Monthly Plan", [v for v in chart_data.get("monthly_plan", [])])
        cd.add_series("Monthly Actual", [v for v in chart_data.get("monthly_actual", [])])
        cd.add_series("Planned", [v for v in chart_data.get("cum_plan", [])])
        cd.add_series("Actual", [v for v in chart_data.get("cum_actual", [])])
        
        chart = _chart_in_box(slide, chart_shape, XL_CHART_TYPE.COLUMN_CLUSTERED, cd)
        chart.has_legend = False
        chart.font.size = Pt(9)
        _move_to_line(chart, 2, secondary=True)
        _light_gridlines(chart)
        _add_data_table(chart)
        _series_fill(chart, [SERIES_BLUE, SERIES_GREEN, SERIES_BLUE, LINE_GREEN], line_from=2)
        
        line = chart.plots[1]
        label_positions = (XL_LABEL_POSITION.ABOVE, XL_LABEL_POSITION.BELOW)
        
        for s_i, (key, colour, pos) in enumerate(
                (("cum_plan", SERIES_BLUE, label_positions[0]),
                 ("cum_actual", SERIES_GREEN, label_positions[1]))):
            vals = chart_data.get(key, [])
            last = max((i for i, v in enumerate(vals) if v is not None and v > 0), default=None)
            if last is not None:
                _label_last(line.series[s_i], last, f"{vals[last] * 100:.2f}%", colour, pos)


def _fill_slide_11(prs, data: Dict[str, Any]):
    """Slide 11 (Index 10): Manpower — inject chart data."""
    if len(prs.slides) <= 10:
        return
    manpower = data.get("manpower", [])
    if not manpower:
        return
        
    slide = prs.slides[10]
    chart_shape = next((sh for sh in slide.shapes if getattr(sh, "has_chart", False)), None)
    if not chart_shape:
        return
        
    from pptx.chart.data import CategoryChartData
    from pptx.enum.chart import XL_CHART_TYPE
    from pptx.util import Pt
    from services.cpag_pptx import (
        _chart_in_box, _move_to_line, _light_gridlines, 
        _add_data_table, _series_fill,
        SERIES_BLUE, SERIES_GREEN, LINE_GREEN
    )
    
    cd = CategoryChartData(number_format="#,##0")
    cats = []
    plan_vals = []
    actual_vals = []
    
    for m in manpower:
        cats.append(m.get("month", ""))
        plan_vals.append(m.get("planManpower", 0))
        # If it's a future month with no earned data, use None so the line stops
        actual = m.get("earnedManpower")
        if actual == 0 and m.get("earnedMonth") == 0:
            actual_vals.append(None)
        else:
            actual_vals.append(actual)
            
    cd.categories = cats
    cd.add_series("Plan Manpower", plan_vals)
    cd.add_series("Actual Manpower", actual_vals)
    cd.add_series("Plan", plan_vals)
    cd.add_series("Actual", actual_vals)
    
    chart = _chart_in_box(slide, chart_shape, XL_CHART_TYPE.COLUMN_CLUSTERED, cd)
    chart.has_legend = False
    chart.font.size = Pt(9)
    _move_to_line(chart, 2, secondary=False)
    _light_gridlines(chart)
    _add_data_table(chart)
    _series_fill(chart, [SERIES_BLUE, SERIES_GREEN, SERIES_BLUE, LINE_GREEN], line_from=2)


# ── Main builder ────────────────────────────────────────────────────────────

def build_portfolio_pptx(data: Dict[str, Any]) -> bytes:
    """Build the CPAG Wind pack by injecting live data into the template."""
    prs = Presentation(REFERENCE)

    # ── Slide 1: Cover with dynamic date ──
    _fill_slide_1(prs, data)

    # ── Slide 3 (Index 2): Executive Summary — inject data ──
    _fill_slide_3(prs, data)

    # ── Slide 4 (Index 3): Commissioning — clear for now ──
    if len(prs.slides) > 3:
        for sh in prs.slides[3].shapes:
            if getattr(sh, "has_table", False):
                _clear_table_data(sh.table, start_row=2)

    # ── Slide 5 (Index 4): Salient Features — inject project info ──
    _fill_slide_5(prs, data)

    # ── Slide 7 (Index 6): S Curve — inject chart data and gap analysis ──
    _fill_slide_7(prs, data)

    # ── Slide 8 (Index 7): Procurement — inject SAP PO data ──
    _fill_slide_8(prs, data)

    # ── Slide 9 (Index 8): Construction Progress — inject P6 data ──
    _fill_slide_9(prs, data)

    # ── Slide 10 (Index 9): Major Milestones — inject P6 data ──
    _fill_slide_10(prs, data)

    # ── Slide 11 (Index 10): Manpower — inject chart data ──
    _fill_slide_11(prs, data)

    # ── Slide 12 (Index 11): Issues — clear for now ──
    if len(prs.slides) > 11:
        for sh in prs.slides[11].shapes:
            if getattr(sh, "has_table", False):
                _clear_table_data(sh.table, start_row=1)

    out = BytesIO()
    prs.save(out)
    return out.getvalue()
