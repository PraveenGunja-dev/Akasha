"""
CPAG deck primitives — template access, text, tables and native charts.

Builds the downloadable deck from the same payload the screen renders, so the
file and the screen can never disagree.  Charts are native PowerPoint charts,
not pictures, so the numbers stay inspectable and the deck stays editable.

The template in assets/cpag_template.pptx is the circulated CPAG pack with its
slides stripped out - masters, layouts, theme, fonts and brand furniture kept.
Slides are built on its own layouts, so the output opens looking like the pack
the reviewers already read rather than a lookalike.

Every caveat the screen shows is carried into the file - the declared-capacity
source, the derived manday basis, the missing PSS-12 supply extract and the
unavailable contractor headcount.  A deck that quietly dropped them would be
more confident than the data supports.
"""
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR

TEMPLATE = Path(__file__).resolve().parent.parent / "assets" / "cpag_template.pptx"
FRONTEND_ASSETS = Path(__file__).resolve().parent.parent.parent / "frontend" / "public" / "cpag"
COVER_PHOTO = FRONTEND_ASSETS / "cover-photo.jpg"
SECTION_IMG = FRONTEND_ASSETS / "section-a.png"
LOGO_IMG = FRONTEND_ASSETS / "logo.png"

# Layout names as they exist in the pack's own master.
LAYOUT_COVER = "Title Slide"
LAYOUT_SECTION = "4_Section Header"
LAYOUT_CONTENT = "2_Title Slide"

# Brand ramp from frontend/src/index.css, for the few marks the template does
# not already style (table headers, chart series, variance tints).
BRAND_BLUE = RGBColor(0x0B, 0x74, 0xB1)
BRAND_PURPLE = RGBColor(0x76, 0x48, 0x9D)
INK = RGBColor(0x10, 0x18, 0x28)
MUTED = RGBColor(0x66, 0x70, 0x85)
RULE = RGBColor(0xE4, 0xE7, 0xEC)
# Verified against the circulated deck's own table fills (slide XML dump,
# 2026-09-24): header purple 7030A0 is the deck's mode (176/312 header cells
# across every slide; 912A82 and 782170 are the runner-ups). Body rows are
# plain white almost everywhere - there is no alternating row band in the
# native tables. The one exception is the Procurement table, which tints by
# COLUMN (grey for ordering columns, peach for delivery-tracking columns),
# not by row - reproduced as GREY_COL/PEACH_COL for that table specifically.
HEADER = RGBColor(0x70, 0x30, 0xA0)
GREY_COL = RGBColor(0xF2, 0xF2, 0xF2)
PEACH_COL = RGBColor(0xFB, 0xE2, 0xD5)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
BAND = WHITE
CELL_RULE = RGBColor(0xC9, 0xCC, 0xD2)
CRITICAL = RGBColor(0xD9, 0x2D, 0x20)
RISK = RGBColor(0xF7, 0x90, 0x09)
HEALTHY = RGBColor(0x12, 0xB7, 0x6A)

SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)

# The template's own content box, measured from its "2_Title Slide" layout.
# Staying inside it is what keeps the header rule, footer rule, logo and slide
# number clear of anything this module draws.
MARGIN = Inches(0.52)
BODY_W = Inches(12.29)
CONTENT_TOP = Inches(1.25)
CONTENT_BOTTOM = Inches(6.80)
FOOTNOTE_TOP = Inches(6.38)

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _month(m: Optional[str]) -> str:
    if not m or "-" not in m:
        return "-"
    y, mm = m.split("-")[:2]
    try:
        return f"{MONTHS[int(mm) - 1]}-{y[2:]}"
    except (ValueError, IndexError):
        return m


def _date(s: Optional[str]) -> str:
    if not s:
        return "-"
    try:
        y, m, d = s[:10].split("-")
        return f"{d}-{MONTHS[int(m) - 1]}-{y[2:]}"
    except (ValueError, IndexError):
        return s[:10]


def _num(v: Any, dp: int = 0) -> str:
    if v is None:
        return "-"
    try:
        return f"{float(v):,.{dp}f}"
    except (TypeError, ValueError):
        return str(v)


def _pct(v: Any, dp: int = 1) -> str:
    return "-" if v is None else f"{float(v):.{dp}f}%"


def _deck() -> Presentation:
    """The pack's own template, slides already stripped, or fallback presentation."""
    if TEMPLATE.exists():
        try:
            return Presentation(str(TEMPLATE))
        except Exception:
            pass
    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H
    return prs


def _layout(prs: Presentation, name: str):
    if prs.slide_masters:
        for lay in prs.slide_masters[0].slide_layouts:
            if lay.name == name:
                return lay
    if len(prs.slide_layouts) > 6:
        return prs.slide_layouts[6]
    return prs.slide_layouts[0]


def _drop_empty_placeholders(slide) -> None:
    """Remove placeholders left unfilled so the deck carries no prompt text."""
    for shape in list(slide.placeholders):
        if shape.placeholder_format.idx == 12:      # slide number - template's
            continue
        if not shape.text_frame.text.strip():
            shape._element.getparent().remove(shape._element)


def _content_slide(prs: Presentation, title: str, subtitle: str = ""):
    """A branded content slide with the pack's title treatment."""
    slide = prs.slides.add_slide(_layout(prs, LAYOUT_CONTENT))
    has_title = False
    for shape in slide.placeholders:
        idx = shape.placeholder_format.idx
        if idx == 0:
            shape.text_frame.text = title
            has_title = True
        elif idx == 1 and subtitle:
            shape.text_frame.text = subtitle
    _drop_empty_placeholders(slide)

    if not has_title:
        top = Inches(0.4)
        _text(slide, MARGIN, top, BODY_W, Inches(0.45), title, size=22, bold=True)
        if subtitle:
            _text(slide, MARGIN, top + Inches(0.42), BODY_W, Inches(0.25), subtitle,
                  size=12, color=MUTED)

    return slide


def _section_slide(prs: Presentation, title: str):
    """Full-bleed divider, same as the pack's section breaks and web presentation."""
    if SECTION_IMG.exists():
        slide = prs.slides.add_slide(_layout(prs, "Blank"))
        slide.shapes.add_picture(
            str(SECTION_IMG), left=0, top=0, width=SLIDE_W, height=SLIDE_H
        )
        top = SLIDE_H * 0.575
        height = SLIDE_H * 0.19
        box = slide.shapes.add_textbox(Inches(0.83), top, SLIDE_W - Inches(1.66), height)
        tf = box.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        tf.margin_left = tf.margin_top = tf.margin_right = tf.margin_bottom = 0
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.LEFT
        run = p.add_run()
        run.text = title
        run.font.size = Pt(32)
        run.font.bold = True
        run.font.color.rgb = WHITE
        run.font.name = "Calibri"
        return slide
    slide = prs.slides.add_slide(_layout(prs, LAYOUT_SECTION))
    for shape in slide.placeholders:
        if shape.placeholder_format.idx == 0:
            shape.text_frame.text = title
    _drop_empty_placeholders(slide)
    return slide


def _text(slide, left, top, width, height, text, *, size=12, bold=False,
          color=INK, align=PP_ALIGN.LEFT, italic=False):
    box = slide.shapes.add_textbox(left, top, width, height)
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = 0
    tf.margin_top = tf.margin_bottom = 0
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = color
    run.font.name = "Calibri"
    return box


def _heading(slide, title: str, eyebrow: Optional[str] = None):
    top = Inches(0.4)
    if eyebrow:
        _text(slide, MARGIN, top, BODY_W, Inches(0.22), eyebrow.upper(),
              size=10, bold=True, color=BRAND_BLUE)
        top = top + Inches(0.26)
    _text(slide, MARGIN, top, BODY_W, Inches(0.45), title, size=24, bold=True)
    return top + Inches(0.62)


def _footnote(slide, text: str):
    _text(slide, MARGIN, SLIDE_H - Inches(0.68), BODY_W - Inches(3.2),
          Inches(0.42), text, size=9, color=MUTED, italic=True)
    _generated_by(slide)


def _generated_by(slide) -> None:
    """Name what produced the deck, on every content slide."""
    _text(slide, SLIDE_W - Inches(3.75), SLIDE_H - Inches(0.44), Inches(3.2),
          Inches(0.22), "Generated by Akasha from P6, SAP and Pulse",
          size=8, color=MUTED, align=PP_ALIGN.RIGHT)


def _table(slide, rows: Sequence[Sequence[str]], left, top, width,
           *, col_w: Optional[Sequence[float]] = None, size=9,
           row_h=0.26, head_h=0.3, tints: Optional[Dict[int, RGBColor]] = None,
           tint_col: Optional[int] = None):
    """First row is the header. `tints` colours a body row's text by index."""
    n_rows, n_cols = len(rows), len(rows[0])
    height = Inches(head_h + row_h * (n_rows - 1))
    shape = slide.shapes.add_table(n_rows, n_cols, left, top, width, height)
    tbl = shape.table
    tbl.first_row = True
    tbl.horz_banding = False

    if col_w:
        total = sum(col_w)
        for i, w in enumerate(col_w):
            tbl.columns[i].width = Emu(int(width * (w / total)))

    tbl.rows[0].height = Inches(head_h)
    for r in range(1, n_rows):
        tbl.rows[r].height = Inches(row_h)

    for r, row in enumerate(rows):
        for c, val in enumerate(row):
            cell = tbl.cell(r, c)
            cell.text = "" if val is None else str(val)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.margin_left = cell.margin_right = Inches(0.055)
            cell.margin_top = cell.margin_bottom = 0
            cell.fill.solid()
            for edge in ("L", "R", "T", "B"):
                _rule(cell, edge)
            if r == 0:
                cell.fill.fore_color.rgb = HEADER
            else:
                cell.fill.fore_color.rgb = BAND if r % 2 == 0 else WHITE
            para = cell.text_frame.paragraphs[0]
            para.alignment = PP_ALIGN.RIGHT if (c and _numeric(val)) else PP_ALIGN.LEFT
            for run in para.runs:
                run.font.size = Pt(size)
                run.font.name = "Calibri"
                run.font.bold = r == 0
                if r == 0:
                    run.font.color.rgb = WHITE
                elif tints and r in tints and c == (tint_col if tint_col is not None else len(row) - 1):
                    run.font.color.rgb = tints[r]
                else:
                    run.font.color.rgb = INK
    return shape



def _rule(cell, edge: str) -> None:
    """Draw a hairline on one cell edge. python-pptx has no borders API, so the
    line element is written onto the cell properties directly."""
    from pptx.oxml.ns import qn
    tc_pr = cell._tc.get_or_add_tcPr()
    tag = "a:ln%s" % edge
    for existing in tc_pr.findall(qn(tag)):
        tc_pr.remove(existing)
    ln = tc_pr.makeelement(qn(tag), {"w": "6350", "cap": "flat",
                                     "cmpd": "sng", "algn": "ctr"})
    fill = ln.makeelement(qn("a:solidFill"), {})
    clr = fill.makeelement(qn("a:srgbClr"), {"val": "%02X%02X%02X" % (
        CELL_RULE[0], CELL_RULE[1], CELL_RULE[2])})
    fill.append(clr)
    ln.append(fill)
    tc_pr.append(ln)


def _table_grouped(slide, top_groups: Sequence[tuple], head: Sequence[str],
                   rows: Sequence[Sequence[str]], left, top, width,
                   *, col_w: Optional[Sequence[float]] = None, size=8,
                   row_h=0.26, head_h=0.26,
                   tints: Optional[Dict[int, RGBColor]] = None,
                   tint_col: Optional[int] = None,
                   col_tint: Optional[Sequence[RGBColor]] = None) -> None:
    """A table with the pack's own two-row header: `top_groups` is a list of
    (label, span) covering every column left to right. A labelled entry draws
    a horizontal merge across `span` columns on the top row, with the leaf
    labels for those columns coming from `head` on the row beneath. An entry
    with an empty label instead merges vertically - that single column's own
    header, from `head`, spans both rows, exactly as the pack's own "Sr. No.",
    "Packages" etc. columns do next to the merged "Expected Delivery at Site"
    group.
    """
    n_cols = len(head)
    n_data = len(rows)
    n_rows = 2 + n_data
    height = Inches(head_h * 2 + row_h * n_data)
    shape = slide.shapes.add_table(n_rows, n_cols, left, top, width, height)
    tbl = shape.table
    tbl.first_row = True
    tbl.horz_banding = False

    if col_w:
        total = sum(col_w)
        for i, w in enumerate(col_w):
            tbl.columns[i].width = Emu(int(width * (w / total)))
    tbl.rows[0].height = Inches(head_h)
    tbl.rows[1].height = Inches(head_h)
    for r in range(2, n_rows):
        tbl.rows[r].height = Inches(row_h)

    def _style_header_cell(cell, text_value: str, align: str = "left"):
        cell.text = text_value
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        cell.margin_left = cell.margin_right = Inches(0.04)
        cell.margin_top = cell.margin_bottom = 0
        cell.fill.solid()
        cell.fill.fore_color.rgb = HEADER
        for edge in ("L", "R", "T", "B"):
            _rule(cell, edge)
        para = cell.text_frame.paragraphs[0]
        para.alignment = PP_ALIGN.CENTER if align == "center" else PP_ALIGN.LEFT
        for run in para.runs:
            run.font.size = Pt(size)
            run.font.bold = True
            run.font.name = "Calibri"
            run.font.color.rgb = WHITE

    # Every header cell is styled before any merge call, since python-pptx
    # merges by marking the followers hMerge/vMerge - their own formatting
    # stops mattering once merged, but must exist first for the merge to see
    # a normal cell there.
    col = 0
    for label, span in top_groups:
        for i in range(span):
            _style_header_cell(tbl.cell(0, col + i), "")
            _style_header_cell(tbl.cell(1, col + i), "")
        if label:
            _style_header_cell(tbl.cell(0, col), label, align="center")
            for i in range(span):
                _style_header_cell(tbl.cell(1, col + i), head[col + i])
            if span > 1:
                tbl.cell(0, col).merge(tbl.cell(0, col + span - 1))
        else:
            _style_header_cell(tbl.cell(0, col), head[col])
            tbl.cell(0, col).merge(tbl.cell(1, col))
        col += span

    for r, row in enumerate(rows):
        rr = r + 2
        for c, val in enumerate(row):
            cell = tbl.cell(rr, c)
            cell.text = "" if val is None else str(val)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.margin_left = cell.margin_right = Inches(0.04)
            cell.margin_top = cell.margin_bottom = 0
            cell.fill.solid()
            for edge in ("L", "R", "T", "B"):
                _rule(cell, edge)
            cell.fill.fore_color.rgb = col_tint[c] if col_tint else WHITE
            para = cell.text_frame.paragraphs[0]
            para.alignment = PP_ALIGN.RIGHT if (c and _numeric(val)) else PP_ALIGN.LEFT
            for run in para.runs:
                run.font.size = Pt(size)
                run.font.name = "Calibri"
                if tints and r in tints and (tint_col is None or c == tint_col):
                    run.font.color.rgb = tints[r]
                else:
                    run.font.color.rgb = INK


def _numeric(v: Any) -> bool:
    s = str(v).replace(",", "").replace("%", "").replace("+", "") \
              .replace("-", "").replace(".", "").replace("d", "").strip()
    return bool(s) and s.isdigit()


def _line_chart(slide, categories: List[str], series: List[tuple],
                left, top, width, height, *, max_scale: Optional[float] = None,
                number_format: str = '0"%"'):
    data = CategoryChartData()
    data.categories = categories
    for name, values in series:
        data.add_series(name, values)
    frame = slide.shapes.add_chart(XL_CHART_TYPE.LINE, left, top, width, height, data)
    chart = frame.chart
    chart.has_title = False
    chart.has_legend = True
    chart.legend.position = XL_LEGEND_POSITION.TOP
    chart.legend.include_in_layout = False
    chart.font.size = Pt(9)

    value_axis = chart.value_axis
    value_axis.minimum_scale = 0
    if max_scale:
        value_axis.maximum_scale = max_scale
        value_axis.major_unit = max_scale / 4
    value_axis.tick_labels.number_format = number_format
    value_axis.tick_labels.number_format_is_linked = False
    value_axis.has_major_gridlines = True
    chart.category_axis.tick_labels.font.size = Pt(8)

    # Plan reads as a reference, actual as the subject.
    for i, plot_series in enumerate(chart.plots[0].series):
        plot_series.smooth = False
        line = plot_series.format.line
        if i == 0:
            line.color.rgb = MUTED
            line.width = Pt(1.5)
            line.dash_style = 4  # dash
        else:
            line.color.rgb = BRAND_BLUE
            line.width = Pt(2.25)
    return chart


def _bar_chart(slide, categories: List[str], series: List[tuple],
               left, top, width, height, *, number_format='#,##0'):
    data = CategoryChartData()
    data.categories = categories
    for name, values in series:
        data.add_series(name, values)
    frame = slide.shapes.add_chart(
        XL_CHART_TYPE.COLUMN_CLUSTERED, left, top, width, height, data)
    chart = frame.chart
    chart.has_title = False
    chart.has_legend = True
    chart.legend.position = XL_LEGEND_POSITION.TOP
    chart.legend.include_in_layout = False
    chart.font.size = Pt(9)
    chart.value_axis.tick_labels.number_format = number_format
    chart.value_axis.tick_labels.number_format_is_linked = False
    chart.category_axis.tick_labels.font.size = Pt(8)
    colours = [MUTED, BRAND_BLUE, BRAND_PURPLE]
    for i, plot_series in enumerate(chart.plots[0].series):
        plot_series.format.fill.solid()
        plot_series.format.fill.fore_color.rgb = colours[i % len(colours)]
    return chart


def _variance_tint(v: Optional[float]) -> RGBColor:
    if v is None:
        return INK
    if v <= -25:
        return CRITICAL
    if v <= -10:
        return RISK
    return HEALTHY


def _paginate(rows: List[List[str]], first: int, rest: int) -> List[List[List[str]]]:
    """Split body rows into slide-sized chunks, header re-applied by caller."""
    out, i, cap = [], 0, first
    while i < len(rows):
        out.append(rows[i:i + cap])
        i += cap
        cap = rest
    return out or [[]]


