"""
CPAG pack as a .pptx, built from the management-approved template itself.

`assets/cpag_reference.pptx` is the approved pack. Every output slide *is* a
template slide - positions, fonts, colours, merges and running order come from
it untouched - and only the values are replaced:

* measured values from P6 / SAP (Physical Progress, Procurement, Civil,
  Electrical, Manpower, Statutory Approvals);
* team-entered values (`manual`, from cpag_manual_entry) for the slides no
  connected system holds - Commissioning Plan, Engineering document log,
  Contractor Manpower, Critical Issues, Financial S-Curve (EAC), Supply /
  Service Ordering Status - left blank, never carried over from the old pack;
* declared facts (capacities, NFA, SPV list) as the template states them,
  overridable by manual entry.

Where the template holds a pasted picture of an Excel chart or table (the
S-curves, Civil and Electrical tables, manpower graphs, contractor grid) a
native chart/table is drawn in exactly the picture's box.
"""
import copy
import re
from calendar import monthrange
from collections import defaultdict
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from lxml import etree
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.opc.packuri import PackURI
from pptx.oxml import parse_xml
from pptx.oxml.ns import nsdecls, qn
from pptx.util import Emu, Inches, Pt

REFERENCE = Path(__file__).resolve().parent.parent / "assets" / "cpag_reference.pptx"

# Template slide numbers (1-based), per the approved pack's running order.
PSS_KEYS = ["11", "12", "10B", "09", "05B", "08B"]
S_SCURVE = dict(zip(PSS_KEYS, range(6, 12)))
S_PROC = dict(zip(PSS_KEYS, range(14, 20)))
S_CIVIL = {"11": 21, "12": 23, "10B": 25, "09": 28, "05B": 30, "08B": 32}
S_ELEC = {k: v + 1 for k, v in S_CIVIL.items()}
S_CONTRACTOR = dict(zip(PSS_KEYS, range(37, 43)))
GROUPS = [
    {"keys": ["11", "12", "10B"], "label": "PSS-11, 12 & 10(B)",
     "progress": 20, "ordering": 47, "supply": [48, 49, 50, 51],
     "service": [52, 53], "approvals_section": 61, "approvals": [62, 63]},
    {"keys": ["09", "05B", "08B"], "label": "PSS-09, 05(B) & 08(B)",
     "progress": 27, "ordering": 54, "supply": [55, 56, 57, 58],
     "service": [59, 60], "approvals_section": 64, "approvals": [65, 66]},
]
S_PHASE1 = [67, 68, 69]
S_THANK_YOU = 46

HEADER_PURPLE = RGBColor(0xA0, 0x2B, 0x93)
PEACH = RGBColor(0xFC, 0xE4, 0xD6)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
BLACK = RGBColor(0x00, 0x00, 0x00)
GREEN = RGBColor(0x00, 0xB0, 0x50)
ORANGE = RGBColor(0xFF, 0xC0, 0x00)
RED = RGBColor(0xFF, 0x00, 0x00)
SERIES_BLUE = RGBColor(0x00, 0xB0, 0xF0)
SERIES_GREEN = RGBColor(0x00, 0xB0, 0x50)
LINE_GREEN = RGBColor(0x92, 0xD0, 0x50)
PROJECT_COLOURS = {  # the template manpower graphs' series colours
    "11": RGBColor(0x15, 0x60, 0x82), "12": RGBColor(0xE9, 0x71, 0x32),
    "05B": RGBColor(0x19, 0x6B, 0x24), "08B": RGBColor(0x0F, 0x9E, 0xD5),
    "09": RGBColor(0xA0, 0x2B, 0x93), "10B": RGBColor(0x4E, 0xA7, 0x2E),
}
OVERALL_PLAN = RGBColor(0x0E, 0x28, 0x41)
OVERALL_ACTUAL = RGBColor(0x8B, 0x3A, 0x0F)


# ── Formatting ──────────────────────────────────────────────────────────────
def pss_key(pss: str) -> str:
    """"PSS-10(B)" -> "10B", "PSS-05(B)" -> "05B", "PSS-11" -> "11"."""
    return pss.replace("PSS-", "").replace("(", "").replace(")", "").strip()


def pss_label(key: str) -> str:
    """The template's slide-title spelling: "PSS 11", "PSS 10B", "PSS 9"."""
    return {"09": "PSS 9", "05B": "PSS 5B", "08B": "PSS 8B"}.get(key, f"PSS {key}")


def _d(iso: Optional[str], star: bool = False) -> str:
    if not iso:
        return "-"
    s = datetime.fromisoformat(iso[:19]).strftime("%d-%b-%y")
    return s + "*" if star else s


def _mon(ym: str) -> str:
    return datetime.strptime(ym[:7], "%Y-%m").strftime("%b-%y")


def _n(v, dp: int = 0) -> str:
    if v is None or v == "":
        return "-"
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    return f"{f:,.{dp}f}" if dp else f"{round(f):,}"


def _p(v) -> str:
    """Whole percent where the value is whole, two decimals otherwise - the
    pack prints both ("2%", "1.80%")."""
    if v is None:
        return "-"
    v = round(float(v), 2)
    return f"{v:.0f}%" if abs(v - round(v)) < 0.005 else f"{v:.2f}%"


def _ordinal_date(d: date) -> str:
    suffix = "th" if 11 <= d.day <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(d.day % 10, "th")
    return f"{d.day}{suffix} {d.strftime('%b %y')}"


def _add_months(ym: str, n: int) -> str:
    y, m = int(ym[:4]), int(ym[5:7]) - 1 + n
    return f"{y + m // 12:04d}-{m % 12 + 1:02d}"


# ── Text and table primitives ───────────────────────────────────────────────
def _first_rpr(txBody):
    rpr = None
    r = txBody.find(".//" + qn("a:r"))
    if r is not None and r.find(qn("a:rPr")) is not None:
        rpr = copy.deepcopy(r.find(qn("a:rPr")))
    else:
        end = txBody.find(".//" + qn("a:endParaRPr"))
        if end is not None:
            rpr = copy.deepcopy(end)
            rpr.tag = qn("a:rPr")
    if rpr is not None:
        # The pack strikes through superseded dates by hand; a new value
        # must never inherit that.
        for attr in ("strike", "dirty", "err"):
            rpr.attrib.pop(attr, None)
    return rpr


def set_text(obj, text, *, color: Optional[RGBColor] = None, bold: Optional[bool] = None) -> None:
    """Replace a shape's or cell's text, keeping the template's own run
    formatting (font, size, colour, alignment). Newlines become paragraphs."""
    tf = obj.text_frame
    txBody = tf._txBody
    paras = txBody.findall(qn("a:p"))
    ppr = paras[0].find(qn("a:pPr")) if paras else None
    ppr = copy.deepcopy(ppr) if ppr is not None else None
    rpr = _first_rpr(txBody)
    for p in paras:
        txBody.remove(p)
    lines = [""] if text is None else str(text).split("\n")
    for line in lines:
        p = etree.SubElement(txBody, qn("a:p"))
        if ppr is not None:
            p.append(copy.deepcopy(ppr))
        if line:
            r = etree.SubElement(p, qn("a:r"))
            if rpr is not None:
                rr = copy.deepcopy(rpr)
                r.append(rr)
            else:
                rr = etree.SubElement(r, qn("a:rPr"))
            if color is not None:
                for f in rr.findall(qn("a:solidFill")):
                    rr.remove(f)
                fill = etree.Element(qn("a:solidFill"))
                clr = etree.SubElement(fill, qn("a:srgbClr"))
                clr.set("val", str(color))
                # solidFill precedes latin/ea/cs in rPr
                rr.insert(0, fill)
            if bold is not None:
                rr.set("b", "1" if bold else "0")
            t = etree.SubElement(r, qn("a:t"))
            t.text = line
        elif rpr is not None:
            end = copy.deepcopy(rpr)
            end.tag = qn("a:endParaRPr")
            p.append(end)


def set_paragraph(shape, index: int, text: str) -> None:
    """Replace one paragraph's text in a multi-line text box."""
    paras = shape.text_frame._txBody.findall(qn("a:p"))
    if index >= len(paras):
        return
    p = paras[index]
    runs = p.findall(qn("a:r"))
    rpr = copy.deepcopy(runs[0].find(qn("a:rPr"))) if runs and runs[0].find(qn("a:rPr")) is not None else None
    for r in runs:
        p.remove(r)
    for br in p.findall(qn("a:br")):
        p.remove(br)
    r = etree.Element(qn("a:r"))
    if rpr is not None:
        r.append(rpr)
    t = etree.SubElement(r, qn("a:t"))
    t.text = text
    end = p.find(qn("a:endParaRPr"))
    if end is not None:
        end.addprevious(r)
    else:
        p.append(r)


def shape_named(slide, name: str):
    for sh in slide.shapes:
        if sh.name == name:
            return sh
    return None


def tables(slide) -> List[Any]:
    return [sh for sh in slide.shapes if getattr(sh, "has_table", False) and sh.has_table]


def pictures(slide) -> List[Any]:
    return [sh for sh in slide.shapes if sh.shape_type == 13 and sh.width > Emu(914400)]


def _strip_merge(tr) -> None:
    for tc in tr.findall(qn("a:tc")):
        for attr in ("rowSpan", "gridSpan", "hMerge", "vMerge"):
            if attr in tc.attrib:
                del tc.attrib[attr]


def set_body(table_shape, first_body: int, rows: Sequence[Sequence[Any]],
             proto: Optional[int] = None, row_height: Optional[int] = None) -> None:
    """Replace a template table's body rows (from `first_body` down) with
    `rows`, each cloned from a template body row so it keeps the row's own
    height, fills, borders and fonts."""
    tbl = table_shape.table._tbl
    trs = tbl.findall(qn("a:tr"))
    proto_tr = copy.deepcopy(trs[proto if proto is not None else min(first_body, len(trs) - 1)])
    _strip_merge(proto_tr)
    # A cloned row takes the template's shortest body-row height - its
    # tallest rows are tall only because of the old pack's text.
    heights = [int(tr.get("h")) for tr in trs[first_body:] if tr.get("h")]
    if row_height:
        proto_tr.set("h", str(row_height))
    elif heights:
        proto_tr.set("h", str(min(heights)))
    for tr in trs[first_body:]:
        tbl.remove(tr)
    table = table_shape.table
    for r_i, values in enumerate(rows):
        tbl.append(copy.deepcopy(proto_tr))
        for c_i, v in enumerate(values):
            if c_i >= len(table.columns):
                break
            cell = table.cell(first_body + r_i, c_i)
            if isinstance(v, tuple):
                set_text(cell, v[0], color=v[1])
            else:
                set_text(cell, v)


def set_row(table_shape, r: int, values: Sequence[Any], start_col: int = 0) -> None:
    table = table_shape.table
    for i, v in enumerate(values):
        c = start_col + i
        if c >= len(table.columns):
            break
        if isinstance(v, tuple):
            set_text(table.cell(r, c), v[0], color=v[1])
        else:
            set_text(table.cell(r, c), v)


def _rule(cell, color: RGBColor = BLACK, w: int = 6350) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    for edge in ("L", "R", "T", "B"):
        tag = qn(f"a:ln{edge}")
        for old in tc_pr.findall(tag):
            tc_pr.remove(old)
        ln = etree.SubElement(tc_pr, tag, {"w": str(w), "cap": "flat", "cmpd": "sng", "algn": "ctr"})
        fill = etree.SubElement(ln, qn("a:solidFill"))
        etree.SubElement(fill, qn("a:srgbClr"), {"val": str(color)})
    # borders precede the cell fill in tcPr
    fill = tc_pr.find(qn("a:solidFill"))
    if fill is not None:
        tc_pr.remove(fill)
        tc_pr.append(fill)


def new_table(slide, left, top, width, height, rows: Sequence[Sequence[Any]],
              col_w: Sequence[float], *, size: float = 10, font: str = "Arial",
              header_rows: Sequence[int] = (0,), header_fill: Optional[RGBColor] = None,
              header_color: RGBColor = BLACK, row_fills: Optional[Dict[int, RGBColor]] = None,
              bold_cols: Sequence[int] = (), center: bool = True,
              row_h: Optional[Sequence[float]] = None):
    """A plain bordered table drawn in a picture's box, styled like the pasted
    Excel ranges it replaces. Cell values may be (text, colour) pairs."""
    n_r, n_c = len(rows), len(rows[0])
    gf = slide.shapes.add_table(n_r, n_c, left, top, width, height)
    tbl = gf.table
    tbl.first_row = False
    tbl.horz_banding = False
    style = tbl._tbl.tblPr.find(qn("a:tableStyleId"))
    if style is not None:
        style.text = "{5940675A-B579-460E-94D1-54222C63F5DA}"  # No Style, Table Grid
    total = sum(col_w)
    for i, w in enumerate(col_w):
        tbl.columns[i].width = Emu(int(width * w / total))
    for i in range(n_r):
        tbl.rows[i].height = Emu(int(height * row_h[i] / sum(row_h))) if row_h else Emu(int(height / n_r))
    for r, row in enumerate(rows):
        for c, v in enumerate(row):
            cell = tbl.cell(r, c)
            text, colour = (v if isinstance(v, tuple) else (v, None))
            cell.text = "" if text is None else str(text)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.margin_left = cell.margin_right = Emu(27000)
            cell.margin_top = cell.margin_bottom = Emu(0)
            is_head = r in header_rows
            fill = header_fill if (is_head and header_fill) else (row_fills or {}).get(r)
            cell.fill.solid()
            cell.fill.fore_color.rgb = fill or WHITE
            _rule(cell)
            for para in cell.text_frame.paragraphs:
                para.alignment = PP_ALIGN.CENTER if (center and c > 0) or is_head else PP_ALIGN.LEFT
                for run in para.runs:
                    run.font.size = Pt(size)
                    run.font.name = font
                    run.font.bold = is_head or c in bold_cols
                    run.font.color.rgb = colour or (header_color if is_head else BLACK)
    return gf


# ── Slide operations ────────────────────────────────────────────────────────
def delete_slide(prs, slide) -> None:
    lst = prs.slides._sldIdLst
    for sld_id in list(lst):
        if prs.part.related_part(sld_id.rId) is slide.part:
            prs.part.drop_rel(sld_id.rId)
            lst.remove(sld_id)
            return


def move_slide_to_end(prs, slide) -> None:
    lst = prs.slides._sldIdLst
    for sld_id in list(lst):
        if prs.part.related_part(sld_id.rId) is slide.part:
            lst.remove(sld_id)
            lst.append(sld_id)
            return


def duplicate_slide(prs, src):
    """Copy a table-only template slide in place, directly after `src` (used
    to continue a table the template gives one slide for)."""
    new = prs.slides.add_slide(src.slide_layout)
    # add_slide names the part from the slide count, which collides with an
    # existing part once any slide has been removed.
    taken = {str(p.partname) for p in prs.part.package.iter_parts()}
    n = len(taken)
    while f"/ppt/slides/slide{n}.xml" in taken:
        n += 1
    new.part.partname = PackURI(f"/ppt/slides/slide{n}.xml")
    for shp in list(new.shapes):
        shp._element.getparent().remove(shp._element)
    rid_map = {}
    for rid, rel in list(src.part.rels.items()):
        if rel.reltype.endswith("/slideLayout") or rel.reltype.endswith("/notesSlide"):
            continue
        if rel.is_external:
            rid_map[rid] = new.part.rels.get_or_add_ext_rel(rel.reltype, rel.target_ref)
        else:
            rid_map[rid] = new.part.relate_to(rel.target_part, rel.reltype)
    r_attrs = {qn("r:embed"), qn("r:id"), qn("r:link")}
    for el in src.shapes._spTree:
        if el.tag in (qn("p:nvGrpSpPr"), qn("p:grpSpPr")):
            continue
        new_el = copy.deepcopy(el)
        for node in new_el.iter():
            for attr in list(node.attrib):
                if attr in r_attrs and node.get(attr) in rid_map:
                    node.set(attr, rid_map[node.get(attr)])
        new.shapes._spTree.append(new_el)
    bg = src._element.cSld.find(qn("p:bg"))
    if bg is not None:
        new._element.cSld.insert(0, copy.deepcopy(bg))
    lst = prs.slides._sldIdLst
    ids = list(lst)
    new_id = ids[-1]
    src_idx = next(i for i, s in enumerate(ids) if prs.part.related_part(s.rId) is src.part)
    lst.remove(new_id)
    lst.insert(src_idx + 1, new_id)
    return new


def remove_shape(shape) -> None:
    el = shape._element
    el.getparent().remove(el)


# ── Chart primitives ────────────────────────────────────────────────────────
def _plot_area(chart):
    return chart._chartSpace.find(qn("c:chart")).find(qn("c:plotArea"))


def _add_data_table(chart) -> None:
    pa = _plot_area(chart)
    dt = parse_xml(
        f'<c:dTable {nsdecls("c")}><c:showHorzBorder val="1"/><c:showVertBorder val="1"/>'
        f'<c:showOutline val="1"/><c:showKeys val="1"/></c:dTable>')
    tail = pa.find(qn("c:spPr"))
    if tail is not None:
        tail.addprevious(dt)
    else:
        pa.append(dt)


def _as_line_series(ser) -> None:
    """Make a bar-chart <c:ser> valid as a line series."""
    inv = ser.find(qn("c:invertIfNegative"))
    if inv is not None:
        ser.remove(inv)
    anchor = ser.find(qn("c:spPr"))
    marker = parse_xml(f'<c:marker {nsdecls("c")}><c:symbol val="none"/></c:marker>')
    if anchor is not None:
        anchor.addnext(marker)
    else:
        ser.find(qn("c:tx")).addnext(marker)
    ser.append(parse_xml(f'<c:smooth {nsdecls("c")} val="0"/>'))


def _move_to_line(chart, n_line: int, secondary: bool) -> None:
    """Move the last `n_line` series of a bar chart onto a line chart - on
    new secondary axes when `secondary`, else on the bar chart's own axes."""
    pa = _plot_area(chart)
    bar = pa.find(qn("c:barChart"))
    sers = bar.findall(qn("c:ser"))
    ax_ids = [a.get("val") for a in bar.findall(qn("c:axId"))]
    if secondary:
        cat_id, val_id = "90000001", "90000002"
    else:
        cat_id, val_id = ax_ids[0], ax_ids[1]
    line = parse_xml(
        f'<c:lineChart {nsdecls("c")}><c:grouping val="standard"/><c:varyColors val="0"/>'
        f'<c:marker val="1"/><c:axId val="{cat_id}"/><c:axId val="{val_id}"/></c:lineChart>')
    first_ax = line.find(qn("c:marker"))
    for s in sers[-n_line:]:
        bar.remove(s)
        _as_line_series(s)
        first_ax.addprevious(s)
    bar.addnext(line)
    if secondary:
        last_ax = pa.findall(qn("c:valAx"))[-1]
        cat = parse_xml(
            f'<c:catAx {nsdecls("c")}><c:axId val="{cat_id}"/><c:scaling><c:orientation val="minMax"/>'
            f'</c:scaling><c:delete val="1"/><c:axPos val="b"/><c:majorTickMark val="none"/>'
            f'<c:minorTickMark val="none"/><c:tickLblPos val="nextTo"/><c:crossAx val="{val_id}"/>'
            f'<c:crosses val="autoZero"/><c:auto val="1"/><c:lblAlgn val="ctr"/>'
            f'<c:lblOffset val="100"/><c:noMultiLvlLbl val="0"/></c:catAx>')
        val = parse_xml(
            f'<c:valAx {nsdecls("c")}><c:axId val="{val_id}"/><c:scaling><c:orientation val="minMax"/>'
            f'</c:scaling><c:delete val="0"/><c:axPos val="l"/><c:numFmt formatCode="0.00%" sourceLinked="0"/>'
            f'<c:majorTickMark val="out"/><c:minorTickMark val="none"/><c:tickLblPos val="nextTo"/>'
            f'<c:crossAx val="{cat_id}"/><c:crosses val="autoZero"/><c:crossBetween val="between"/></c:valAx>')
        last_ax.addnext(cat)
        cat.addnext(val)
        # The bar (monthly) axis moves to the right, as in the pack.
        bar_val = [v for v in pa.findall(qn("c:valAx")) if v.find(qn("c:axId")).get("val") == ax_ids[1]][0]
        bar_val.find(qn("c:axPos")).set("val", "r")
        crosses = bar_val.find(qn("c:crosses"))
        if crosses is not None:
            crosses.set("val", "max")


def _light_gridlines(chart) -> None:
    for grid in _plot_area(chart).iter(qn("c:majorGridlines")):
        for old in grid.findall(qn("c:spPr")):
            grid.remove(old)
        grid.append(parse_xml(
            f'<c:spPr {nsdecls("c", "a")}><a:ln w="6350"><a:solidFill>'
            f'<a:srgbClr val="D9D9D9"/></a:solidFill></a:ln></c:spPr>'))


def _span_blanks(chart) -> None:
    c = chart._chartSpace.find(qn("c:chart"))
    d = c.find(qn("c:dispBlanksAs"))
    if d is None:
        d = etree.SubElement(c, qn("c:dispBlanksAs"))
        pvo = c.find(qn("c:plotVisOnly"))
        if pvo is not None:
            pvo.addnext(d)
    d.set("val", "span")


def _series_fill(chart, colours: Sequence[RGBColor], line_from: Optional[int] = None) -> None:
    i = 0
    for plot in chart.plots:
        for s in plot.series:
            col = colours[i] if i < len(colours) else None
            if col is not None:
                if line_from is not None and i >= line_from:
                    s.format.line.color.rgb = col
                    s.format.line.width = Pt(2.25)
                else:
                    s.format.fill.solid()
                    s.format.fill.fore_color.rgb = col
            i += 1


def _label_last(series, idx: int, text: str, colour: RGBColor,
                position: Optional[XL_LABEL_POSITION] = None) -> None:
    dl = series.points[idx].data_label
    dl.has_text_frame = True
    dl.text_frame.text = text
    if position is not None:
        dl.position = position
    for r in dl.text_frame.paragraphs[0].runs:
        r.font.bold = True
        r.font.size = Pt(9)
        r.font.color.rgb = colour


def replace_chart_data(chart, cd) -> None:
    """Swap a template chart's data, keeping its formatting. The pack's charts
    link to an external Excel file; that link is dropped so the new data is
    embedded in the deck instead of pointing at a workbook reviewers lack."""
    cs = chart._chartSpace
    ext = cs.find(qn("c:externalData"))
    if ext is not None:
        rid = ext.get(qn("r:id"))
        cs.remove(ext)
        part = chart.part
        if rid in part.rels:
            part.rels.pop(rid)
    chart.replace_data(cd)


def _chart_in_box(slide, box, chart_type, cd):
    x, y, cx, cy = box.left, box.top, box.width, box.height
    remove_shape(box)
    return slide.shapes.add_chart(chart_type, x, y, cx, cy, cd).chart


# ── Payload helpers ─────────────────────────────────────────────────────────
def _manual(d: Dict[str, Any], key: str) -> Any:
    e = (d.get("manual") or {}).get(key)
    return e.get("payload") if e else None


def _receipts(pkg) -> List[Dict[str, Any]]:
    return sorted((m for m in pkg["milestones"] if "receipt at site" in m["name"].lower()),
                  key=lambda m: m.get("baselineFinish") or m.get("forecastFinish") or "")


def _mdcc(pkg) -> List[Dict[str, Any]]:
    return sorted((m for m in pkg["milestones"] if m["name"].lower().strip().startswith("mdcc")),
                  key=lambda m: m.get("baselineFinish") or "")


def _placement(pkg):
    return next((m for m in pkg["milestones"] if "placement of the order" in m["name"].lower()), None)


def _af(m, which: str = "Finish") -> str:
    """Actual where it happened, P6's forecast (starred) where it has not."""
    if not m:
        return "-"
    if m.get(f"actual{which}"):
        return _d(m[f"actual{which}"])
    if m.get(f"forecast{which}"):
        return _d(m[f"forecast{which}"], star=True)
    return "-"


_QTY = re.compile(r"(\d[\d,.]*)\s*(nos|no\.|set|sets|kms|km)\b", re.I)


def _lot_qty(name: str) -> Optional[float]:
    m = _QTY.search(name)
    return float(m.group(1).replace(",", "")) if m else None


# ── Slide fillers ───────────────────────────────────────────────────────────
TEMPLATE_PACKAGES = [  # the pack's package sequence; P6 package names matched
    ("Battery Container", ["battery container"], "Nos."),
    ("PCS", ["pcs"], "Nos."),
    ("EMS", ["ems"], "Set"),
    ("Converter Transformer", ["converter transformer"], "Nos."),
    ("CSS", ["css"], "Nos."),
    ("MV Switchgear", ["mv switchgear"], "Nos."),
    ("HT Cable", ["ht cable"], "Kms"),
    ("DC & LT Cables", ["dc cable", "lt 1c", "lt cable"], "Kms"),
    ("Control Cable", ["control & comm", "control cable"], "Kms"),
    ("SCADA Cable", ["scada"], "Kms"),
    ("FO Cable", ["optic fibre", "fo cable", "ofc"], "Kms"),
]

APPROVAL_OWNERS = {  # Responsible / Approval Authority - organisational facts
    "clra": ("Site IR Team", "Govt. of Gujrat(Dept of Labor)"),
    "fire safety plan": ("Project Team", "Regional Fire Officer"),
    "project import": ("TC Team", "Commissioner of Customs, Kandla"),
    "grid connectivity": ("Asset Commissioning + BD HO Team and Delhi Office", "CTU"),
    "metering scheme": ("Engineering + Asset Commissioning Team", "RLDC"),
    "connectivity agreement": ("Asset Commissioning, Engineering and Delhi Office", "CTU & WRLDC"),
    "ptcc": ("Asset Commissioning & Projects",
             "CEA, Department of Telecommunications & Indian Railways & Defense"),
    "intimation to labor inspector": ("Site IR Team", "Govt. of Gujrat(Dept of Labor)"),
    "implementation support agreement": ("BD Team", "Internal"),
}


_SPELLINGS = [  # one package, spelt differently across the six schedules
    (r"^control\s*&\s*comm", "Control & Communication Cables"),
    (r"^structur(e|al)\s+material", "Structural Material"),
    (r"^balance supply", "Balance Supply Items"),
]


def _package_label(pk) -> str:
    """The pack's name for a P6 package - the template's own label where it
    has one, else the P6 name with known spelling variants merged."""
    base = (pk.get("packageBase") or pk["package"]).strip()
    low = base.lower()
    for label, needles, _uom in TEMPLATE_PACKAGES:
        if any(low.startswith(n) for n in needles):
            return label
    for pattern, label in _SPELLINGS:
        if re.match(pattern, low):
            return label
    return base


def _vendor(name: Optional[str]) -> str:
    if not name:
        return "-"
    s = re.sub(r"\b(PVT|PRIVATE|LTD|LIMITED|LLP|INDIA|CO)\b\.?", "", name, flags=re.I)
    s = re.sub(r"[()]", "", s)
    return re.sub(r"\s+", " ", s).strip(" .,").title() or name


def fill_cover(slide, single: Optional[Dict[str, Any]]) -> None:
    tb = shape_named(slide, "TextBox 1")
    if tb is None:
        return
    if single:
        set_paragraph(tb, 1, f"{single['pss']} : FY 2026 \u2013 27")
    set_paragraph(tb, 3, _ordinal_date(date.today()))


def fill_capacity(slide, projects) -> None:
    t = tables(slide)[0]
    by = {pss_key(p["pss"]): p for p in projects}
    tot = [0, 0, 0]
    for r, key in enumerate(PSS_KEYS, start=1):
        p = by.get(key)
        if not p:
            set_row(t, r, ["-", "-", "-"], 1)
            continue
        vals = [p["powerMw"], p["energyMwh"], p["dispatchableMwh"]]
        tot = [a + b for a, b in zip(tot, vals)]
        set_row(t, r, [f"{vals[0]} MW", f"{vals[1]} MWh", f"{vals[2]} MWh"], 1)
    set_row(t, len(t.table.rows) - 1, [f"{tot[0]} MW", f"{tot[1]} MWh", f"{tot[2]} MWh"], 1)


def fill_salient(slide, projects, d) -> None:
    tb = shape_named(slide, "TextBox 4")
    P = sum(p["powerMw"] for p in projects)
    E = sum(p["energyMwh"] for p in projects)
    D = sum(p["dispatchableMwh"] for p in projects)
    if tb is not None:
        set_paragraph(tb, 0, f"Project Capacity\t:\xa0{P} MW / {E} MWh (Dispatchable Power : {D} MWh)")
    man = _manual(d, "salient") or {}
    t_nfa, t_spv = tables(slide)[0], tables(slide)[1]
    if man.get("nfa"):
        set_body(t_nfa, 1, man["nfa"])
    by = {pss_key(p["pss"]): p for p in projects}
    set_row(t_spv, 0, [by[k]["spv"] if k in by else "-" for k in PSS_KEYS], 1)
    for r, key in ((2, "connectivity"), (3, "landLease"), (4, "contractors")):
        if man.get(key):
            set_row(t_spv, r, man[key], 1)


def fill_commissioning(slide, projects, d, as_of: str) -> None:
    t = tables(slide)[0]
    table = t.table
    by = {pss_key(p["pss"]): p for p in projects}
    for i, key in enumerate(PSS_KEYS):
        p = by.get(key)
        if p:
            set_text(table.cell(0, 1 + 2 * i), f"{p['pss']} in MWh")
            set_text(table.cell(1, 1 + 2 * i), f"({p['batteryOem']})")
    man = _manual(d, "commissioning") or {}
    body_rows = len(table.rows) - 4
    months = man.get("months") or [_add_months(as_of, i - 3) for i in range(body_rows)]
    values = man.get("values") or []
    col_tot = [0.0] * 14
    for r in range(body_rows):
        row_vals = values[r] if r < len(values) else []
        cells = [_mon(months[r]) if r < len(months) else ""]
        mwh = cont = 0.0
        for c in range(12):
            v = row_vals[c] if c < len(row_vals) else None
            cells.append("" if v in (None, "") else _n(v))
            if v not in (None, ""):
                col_tot[c] += float(v)
                if c % 2 == 0:
                    mwh += float(v)
                else:
                    cont += float(v)
        cells += ["" if not row_vals else _n(mwh), "" if not row_vals else _n(cont)]
        col_tot[12] += mwh
        col_tot[13] += cont
        set_row(t, 3 + r, cells)
    set_row(t, len(table.rows) - 1,
            ["Total"] + (["" for _ in range(14)] if not values else [_n(v) for v in col_tot]))
    note = shape_named(slide, "TextBox 1")
    if note is not None:
        set_text(note, man.get("note") or "Note :")


def fill_scurve(slide, p, d) -> None:
    t = tables(slide)[0]
    buckets = p.get("buckets") or []
    man = _manual(d, f"scurve.{pss_key(p['pss'])}") or {}
    # Remarks are the reviewer's own commentary on the variance - manual
    # entry only, blank until someone writes one.
    remarks = man.get("remarks") or []
    for i, b in enumerate(buckets[:4]):
        w, pp, aa = b.get("weightPct") or 0, b.get("planToDatePct") or 0, b.get("earnedPct") or 0
        rem = remarks[i] if i < len(remarks) and remarks[i] else ""
        set_row(t, 2 + i, [_p(w), _p(pp), _p(aa), _p(pp - aa), rem], 1)
    # The Total row is the graph's own FTM point, so the table and the curve
    # above it cannot disagree by a rounding step.
    series = p.get("sCurve") or []
    ftm = next((s for s in series if s["month"] == p.get("lastActualMonth")), None)
    pl = (ftm or {}).get("planCumPct") or sum(b.get("planToDatePct") or 0 for b in buckets)
    ac = (ftm or {}).get("actualCumPct") or sum(b.get("earnedPct") or 0 for b in buckets)
    rem = remarks[4] if len(remarks) > 4 and remarks[4] else ""
    set_row(t, 6, [_p(100), _p(pl), _p(ac), _p(pl - ac), rem], 1)

    pics = pictures(slide)
    if not series or not pics:
        return
    months = [s["month"] for s in series]
    cats = [_mon(_add_months(months[0], -1))] + [_mon(m) for m in months]

    def col(key):
        return [0.0] + [None if s.get(key) is None else s[key] / 100 for s in series]

    cd = CategoryChartData(number_format="0.00%")
    cd.categories = cats
    cd.add_series("Monthly Plan", col("planMonthPct"))
    cd.add_series("Monthly Actual", col("actualMonthPct"))
    cd.add_series("Planned", col("planCumPct"))
    cd.add_series("Actual", col("actualCumPct"))
    chart = _chart_in_box(slide, pics[0], XL_CHART_TYPE.COLUMN_CLUSTERED, cd)
    chart.has_legend = False
    chart.font.size = Pt(9)
    _move_to_line(chart, 2, secondary=True)
    _light_gridlines(chart)
    _add_data_table(chart)
    _series_fill(chart, [SERIES_BLUE, SERIES_GREEN, SERIES_BLUE, LINE_GREEN], line_from=2)
    line = chart.plots[1]
    # Plan and Actual sit above/below each other, not side by side - fixed
    # opposite label positions so the two percentages never sit on top of
    # each other when the values are close (2026-09-26).
    label_positions = (XL_LABEL_POSITION.ABOVE, XL_LABEL_POSITION.BELOW)
    for s_i, (key, colour, pos) in enumerate(
            (("planCumPct", SERIES_BLUE, label_positions[0]),
             ("actualCumPct", SERIES_GREEN, label_positions[1]))):
        vals = col(key)
        last = max((i for i, v in enumerate(vals) if v is not None), default=None)
        if last is not None:
            _label_last(line.series[s_i], last, f"{vals[last] * 100:.2f}%", colour, pos)


def _cdd(sap_rows) -> str:
    """The SAP PO delivery date; a range where the PO lines differ."""
    firsts = [r["cddFirst"] for r in sap_rows if r.get("cddFirst")]
    lasts = [r["cddLast"] for r in sap_rows if r.get("cddLast")]
    if not firsts:
        return "-"
    a, b = _d(min(firsts)), _d(max(lasts))
    return a if a == b else f"{a}\n{b}"


def _schedule_cols(members, sap, fc_months: List[str]) -> Dict[str, Any]:
    """Expected Delivery / MDCC / Delivered / Forecast - always P6 (plus the
    SAP delivered-quantity fallback for containers/PCS), unmoved by where a
    row's Packages-through-PO-Date columns come from: the BESS PMAG mapping
    (2026-09-26) scopes SAP-as-source to those columns only."""
    receipts = sorted((m for pk in members for m in _receipts(pk)),
                      key=lambda m: m.get("baselineFinish") or m.get("forecastFinish") or "")
    mdcc = sorted((m for pk in members for m in _mdcc(pk)), key=lambda m: m.get("baselineFinish") or "")
    sap_rows = [sap[pk["sapMaterial"]] for pk in members if pk.get("sapMaterial") in sap]
    # A combined/split row (e.g. DC + LT + Control cable folded into one line)
    # has scope spread across every matched P6 package - summed, not just the
    # first one found, or the row under-reports (BESS PMAG, 2026-09-26).
    scope_vals = [pk["scopeQty"] for pk in members if pk.get("scopeQty")]
    scope = sum(scope_vals) if scope_vals else None
    lot_q = [_lot_qty(m["name"]) for m in receipts]
    if scope is None and receipts and all(q is not None for q in lot_q):
        scope = sum(lot_q)
    delivered = None
    if receipts and all(q is not None for q in lot_q):
        delivered = sum(q for q, m in zip(lot_q, receipts) if m.get("actualFinish"))
    elif sap_rows and sap_rows[0]["material"] in ("BESS Containers", "PCS Supply"):
        delivered = sap_rows[0].get("deliveredQtyRaw")
    elif receipts and scope and all(m.get("actualFinish") for m in receipts):
        delivered = scope
    all_in = bool(receipts) and all(m.get("actualFinish") for m in receipts)
    if scope and delivered is not None and delivered >= scope:
        all_in = True
    fc = []
    for ym in fc_months:
        q, hit = 0.0, False
        for qty, m in zip(lot_q, receipts):
            if not m.get("actualFinish") and (m.get("forecastFinish") or "")[:7] == ym:
                hit = True
                q += qty or 0
        fc.append(_n(q) if hit and q else ("Lot" if hit else "-"))
    # Start/finish collapse to a single actual range across every lot of this
    # package (BESS PMAG, 2026-09-26): earliest actual start, latest actual-or-
    # forecast finish. A lot still pending contributes its forecast finish -
    # shown in blue - rather than leaving the row incomplete.
    starts = [m["actualStart"] for m in receipts if m.get("actualStart")]
    start = _d(min(starts)) if starts else "-"
    finish_pairs = [(m["actualFinish"], False) for m in receipts if m.get("actualFinish")]
    finish_pairs += [(m["forecastFinish"], True) for m in receipts
                     if not m.get("actualFinish") and m.get("forecastFinish")]
    if finish_pairs:
        finish_iso, finish_forecast = max(finish_pairs, key=lambda t: t[0])
        finish = (_d(finish_iso) + "*", PLAN_BLUE) if finish_forecast else _d(finish_iso)
    else:
        finish = "-"
    return {
        "scope": scope,
        "start": start,
        "finish": finish,
        "mdcc": _af(mdcc[-1]) if mdcc else "-",
        "delivered": delivered, "completed": all_in, "forecast": fc,
    }


# WBS-baseline package label -> the TEMPLATE_PACKAGES label(s) covering the
# same scope in P6, so an uploaded row can still carry P6's Expected
# Delivery / MDCC / Delivered / Forecast. Two P6 packages fold into one
# uploaded WBS package where SAP books them as a single PO (DC/LT/Control
# cable; SCADA/FO cable) - confirmed against the WBS mapping file, 2026-09-26.
WBS_TO_TEMPLATE_LABELS = {
    "BESS Containers": ["Battery Container"], "PCS Supply": ["PCS"], "EMS Supply": ["EMS"],
    "Converter Transformer": ["Converter Transformer"],
    "HT Panel Supply (MV Switchgear)": ["MV Switchgear"],
    "DC Cable, LT Cable & Control Cable Supply": ["DC & LT Cables", "Control Cable"],
    "HT Cable Supply": ["HT Cable"],
    "SCADA & FO Cable Supply": ["SCADA Cable", "FO Cable"],
}


def _package_rows(p, fc_months: List[str], wbs_rows: Optional[List[Dict[str, Any]]] = None
                  ) -> List[Dict[str, Any]]:
    pkgs = list(p.get("packages") or [])
    sap = {r["material"]: r for r in (p.get("sap") or [])}
    used, rows = set(), []

    def match_p6(template_labels: List[str]):
        needles = [n for lab in template_labels for l2, ns, _u in TEMPLATE_PACKAGES if l2 == lab for n in ns]
        members = [pk for pk in pkgs if id(pk) not in used and any(
            (pk.get("packageBase") or pk["package"]).lower().startswith(n) for n in needles)]
        used.update(id(pk) for pk in members)
        return members

    def build(label, members, uom):
        order = next((_placement(pk) for pk in members if _placement(pk)), None)
        sap_rows = [sap[pk["sapMaterial"]] for pk in members if pk.get("sapMaterial") in sap]
        sched = _schedule_cols(members, sap, fc_months)
        return {
            **sched,
            "label": label,
            "vendor": _vendor(sap_rows[0]["vendor"]) if sap_rows else "-",
            "uom": uom,
            "placed": None if order is None else bool(order.get("actualFinish")),
            "po": ", ".join(r["poNumbers"] for r in sap_rows) if sap_rows else "-",
            "poDate": _af(order), "cdd": _cdd(sap_rows),
        }

    wbs_by_pkg: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in wbs_rows or []:
        wbs_by_pkg[r["package"]].append(r)
    # Template label -> the uploaded WBS label covering it, so row order can
    # follow the approved pack's own package sequence (TEMPLATE_PACKAGES),
    # never the upload's or any other ordering (user, 2026-09-26).
    label_to_wbs = {lab: wbs_label for wbs_label, labs in WBS_TO_TEMPLATE_LABELS.items() for lab in labs}
    emitted_wbs: set = set()

    for label, needles, uom in TEMPLATE_PACKAGES:
        wbs_label = label_to_wbs.get(label)
        if wbs_label and wbs_rows:
            if wbs_label in emitted_wbs:
                continue
            emitted_wbs.add(wbs_label)
            po_rows = wbs_by_pkg.get(wbs_label)
            if not po_rows:
                continue
            members = match_p6(WBS_TO_TEMPLATE_LABELS[wbs_label])
            sched = _schedule_cols(members, sap, fc_months)
            for po in po_rows:
                rows.append({
                    **sched,
                    "label": wbs_label,
                    "vendor": _vendor(po["vendor"]) if po["vendor"] else "-",
                    "uom": po["uom"] or "-", "scope": po["qty"], "placed": True,
                    "po": po["poNumber"] or "-",
                    "poDate": _d(po["poDate"]) if po["poDate"] else "-",
                    "cdd": "-",
                })
            continue
        # Not covered by the upload (CSS today - "keep under manual
        # provision", BESS PMAG mail 2026-09-22) - or no upload yet - keeps
        # coming straight from P6, in the template's own package slot.
        members = [pk for pk in pkgs if id(pk) not in used and any(
            (pk.get("packageBase") or pk["package"]).lower().startswith(n) for n in needles)]
        if not members:
            continue
        used.update(id(pk) for pk in members)
        rows.append(build(label, members, uom))

    # Anything genuinely outside the approved pack's package list - an
    # uploaded label with no template slot, or a leftover P6 package - has
    # nowhere else to sit, so it prints last.
    for wbs_label, po_rows in wbs_by_pkg.items():
        if wbs_label in emitted_wbs or not po_rows:
            continue
        members = match_p6(WBS_TO_TEMPLATE_LABELS.get(wbs_label, []))
        sched = _schedule_cols(members, sap, fc_months)
        for po in po_rows:
            rows.append({
                **sched,
                "label": wbs_label,
                "vendor": _vendor(po["vendor"]) if po["vendor"] else "-",
                "uom": po["uom"] or "-", "scope": po["qty"], "placed": True,
                "po": po["poNumber"] or "-",
                "poDate": _d(po["poDate"]) if po["poDate"] else "-",
                "cdd": "-",
            })
    for pk in pkgs:
        if id(pk) in used:
            continue
        uom = "Nos." if re.search(r"\bnos\b", pk["package"], re.I) else "-"
        rows.append(build(pk.get("packageBase") or pk["package"], [pk], uom))
    return rows


# The template's own table runs from 0.71in to 7.21in on a 7.5in slide; at
# the compact row height fill_procurement uses (274320 EMU), that fits ~20
# body rows before overflowing - verified geometrically, 2026-09-26. The old
# 11-row cap paginated projects (e.g. 19 rows) onto a mostly-empty second
# slide well before the real limit.
PROC_CAPACITY = 19
PROC_LINE_BUDGET = 38


def _cdd_after_po_date(t) -> None:
    """Review mail 2026-09-25: CDD (Commercial Delivery Date, from the SAP PO)
    is its own column straight after PO Date, and Manufacturing Status covers
    MDCC Date only. The template's "QAP Acceptance Date" column is moved into
    that slot, so the column count and widths stay the template's."""
    tbl = t.table._tbl
    table = t.table
    head1 = [re.sub(r"\s+", " ", table.cell(1, c).text).strip() for c in range(len(table.columns))]
    if "QAP Acceptance Date" not in head1:
        return
    head0 = [re.sub(r"\s+", " ", table.cell(0, c).text).strip() for c in range(len(table.columns))]
    src = head1.index("QAP Acceptance Date")
    dst = head0.index("PO Date") + 1
    trs = tbl.findall(qn("a:tr"))
    po_head0 = copy.deepcopy(trs[0].findall(qn("a:tc"))[dst - 1])  # "PO Date", rowSpan=2
    po_head1 = copy.deepcopy(trs[1].findall(qn("a:tc"))[dst - 1])  # its vMerge half
    mfg_head = copy.deepcopy(trs[0].findall(qn("a:tc"))[src])      # "Manufacturing Status"
    mfg_head.attrib.pop("gridSpan", None)

    grid = tbl.find(qn("a:tblGrid"))
    col = grid.findall(qn("a:gridCol"))[src]
    grid.remove(col)
    grid.findall(qn("a:gridCol"))[dst].addprevious(col)
    for tr in trs:
        tcs = tr.findall(qn("a:tc"))
        cell = tcs[src]
        tr.remove(cell)
        tr.findall(qn("a:tc"))[dst].addprevious(cell)

    def swap(tr, idx, new):
        old = tr.findall(qn("a:tc"))[idx]
        old.addprevious(new)
        tr.remove(old)

    # Header: CDD spans both header rows like PO Date; the Manufacturing
    # Status group now sits over MDCC Date alone.
    # After the move the old "MC Date" column sits at src + 1; the columns
    # between dst and src each shifted right by one.
    mdcc = src + 1
    swap(trs[0], dst, po_head0)
    swap(trs[1], dst, po_head1)
    swap(trs[0], mdcc, mfg_head)
    set_text(table.cell(0, dst), "CDD")
    set_text(table.cell(1, mdcc), "MDCC Date")


PROC_FORECAST_MONTHS = 3  # present + next 2 - BESS PMAG, 2026-09-26


def _normalize_forecast_columns(t, target: int = PROC_FORECAST_MONTHS) -> None:
    """Every project's Forecast Delivery Schedule shows the same `target`
    month columns. The reference template was authored per project and is
    inconsistent - 1 to 4 month columns depending on the slide - so this
    clones or drops columns until every slide has exactly the same count
    before the months get relabelled to the live rolling window."""
    tbl = t.table._tbl
    table = t.table
    head1 = [re.sub(r"\s+", " ", table.cell(1, c).text).strip() for c in range(len(table.columns))]
    fc = [c for c, h in enumerate(head1) if re.fullmatch(r"[A-Z][a-z]{2}-\d{2}", h)]
    if not fc or len(fc) == target:
        return
    grid = tbl.find(qn("a:tblGrid"))
    cols = grid.findall(qn("a:gridCol"))
    trs = tbl.findall(qn("a:tr"))
    span_cell = trs[0].findall(qn("a:tc"))[fc[0]]
    span = int(span_cell.get("gridSpan") or "1")

    if len(fc) < target:
        last = fc[-1]
        for _ in range(target - len(fc)):
            cols[last].addnext(copy.deepcopy(cols[last]))
            for tr in trs:
                tcs = tr.findall(qn("a:tc"))
                tcs[last].addnext(copy.deepcopy(tcs[last]))
        span_cell.set("gridSpan", str(span + (target - len(fc))))
    else:
        for idx in sorted(fc[target:], reverse=True):
            grid.remove(cols[idx])
            for tr in trs:
                tr.remove(tr.findall(qn("a:tc"))[idx])
        span_cell.set("gridSpan", str(span - (len(fc) - target)))


def fill_procurement(prs, slide, p, d, as_of: str) -> None:
    t = tables(slide)[0]
    _cdd_after_po_date(t)
    _normalize_forecast_columns(t)
    table = t.table
    head = [re.sub(r"\s+", " ", table.cell(1, c).text).strip() for c in range(len(table.columns))]
    fc_cols = [c for c, h in enumerate(head) if re.fullmatch(r"[A-Z][a-z]{2}-\d{2}", h)]
    fc_months = [_add_months(as_of, i) for i in range(len(fc_cols))]
    for c, ym in zip(fc_cols, fc_months):
        set_text(table.cell(1, c), _mon(ym))

    remarks = (_manual(d, f"procurement.{pss_key(p['pss'])}") or {}).get("remarks") or {}
    wbs_rows = ((_manual(d, "procurement_wbs") or {}).get("projects") or {}).get(pss_key(p["pss"]))
    rows, completed = [], []
    for i, r in enumerate(_package_rows(p, fc_months, wbs_rows), start=1):
        scope = r["scope"]
        ordered = (None if scope is None or r["placed"] is None
                   else scope if r["placed"] else 0)
        balance = (scope - ordered) if (scope is not None and ordered is not None) else None
        row = [str(i), r["label"], r["vendor"], r["uom"] if scope is not None else "-",
               _n(scope), _n(ordered), _n(balance), r["po"], r["poDate"], r["cdd"],
               r["start"], r["finish"], r["mdcc"], _n(r["delivered"])]
        row += ([("Completed", GREEN)] + [""] * (len(fc_cols) - 1)) if r["completed"] else r["forecast"]
        row.append(remarks.get(r["label"]) or "")
        rows.append(row)
        completed.append(r["completed"])

    chunks, flags, cur, cur_f, used = [], [], [], [], 0
    for row, done in zip(rows, completed):
        lines = max(max(str(v).count("\n") + 1 for v in row), len(row[-1]) // 14 + 1, 2)
        if cur and (used + lines > PROC_LINE_BUDGET or len(cur) >= PROC_CAPACITY):
            chunks.append(cur)
            flags.append(cur_f)
            cur, cur_f, used = [], [], 0
        cur.append(row)
        cur_f.append(done)
        used += lines
    chunks.append(cur)
    flags.append(cur_f)
    targets = [slide]
    for _ in chunks[1:]:
        targets.append(duplicate_slide(prs, targets[-1]))
    for sl, chunk, done in zip(targets, chunks, flags):
        tt = tables(sl)[0]
        set_body(tt, 2, chunk, proto=2, row_height=Emu(274320))
        if len(fc_cols) > 1:
            for r_i, is_done in enumerate(done):
                if is_done:
                    tt.table.cell(2 + r_i, fc_cols[0]).merge(tt.table.cell(2 + r_i, fc_cols[-1]))
    if len(targets) > 1:
        for k, sl in enumerate(targets, start=1):
            ttl = _title_shape(sl, "Procurement")
            if ttl is not None:
                set_text(ttl, f"{ttl.text_frame.text.split(' (')[0]} ({k}/{len(targets)})")


PLAN_BLUE = RGBColor(0x00, 0x70, 0xC0)
LEGEND_YELLOW = RGBColor(0xFF, 0xFF, 0x00)


def _legend_colour(actual, plan) -> RGBColor:
    """The pack's chart legend: green at 80%+ of plan achieved, yellow at
    40-80%, red below 40%."""
    r = (actual / plan) if plan else 1.0
    return GREEN if r >= 0.8 else LEGEND_YELLOW if r >= 0.4 else RED


def _colour_points(series, colours) -> None:
    for i, c in enumerate(colours):
        fmt = series.points[i].format
        fmt.fill.solid()
        fmt.fill.fore_color.rgb = c


def _achievement(actual, plan) -> RGBColor:
    if not plan:
        return GREEN
    r = actual / plan
    return GREEN if r >= 0.8 else ORANGE if r >= 0.4 else RED


def _civil_rows(elements):
    out = []
    for e in elements:
        plan = [("-" if v is None else _n(v)) for v in e["plan"]]
        act = [("-" if v is None else (_n(v), _achievement(v, pv)))
               for v, pv in zip(e["actual"], e["plan"])]
        out.append([e["element"], "Plan", _n(e["scope"]), *plan, _p(e["planPct"])])
        act_pct = (_p(e["actualPct"]) if e["actualPct"] is None
                   else (_p(e["actualPct"]), _achievement(e["actualPct"], e["planPct"] or 0)))
        out.append(["", "Actual", _n(e["scope"]), *act, act_pct])
    return out


def fill_civil(slide, p) -> None:
    groups = (p.get("civil") or {}).get("groups") or []
    pics = sorted(pictures(slide), key=lambda s: -s.height)
    main_pic, bcf_pic = (pics + [None, None])[:2]

    if main_pic is not None and len(groups) >= 2:
        rows, heads, fills, spans = [], [], {}, []
        for g in groups[:2]:
            heads.append(len(rows))
            rows.append(["", "", "Total Scope", *g["stages"], "Progress"])
            for e in g["elements"]:
                fills[len(rows)] = PEACH
                spans.append(len(rows))
                rows.extend(_civil_rows([e]))
        x, y, cx, cy = main_pic.left, main_pic.top, main_pic.width, main_pic.height
        remove_shape(main_pic)
        gf = new_table(slide, x, y, cx, cy, rows, [0.6, 0.65, 0.7, 0.95, 1.1, 0.95, 0.95, 0.95, 0.8],
                       size=8, header_rows=heads, row_fills=fills, bold_cols=(0,),
                       row_h=[2.0 if r in heads else 1.0 for r in range(len(rows))])
        tb = gf.table
        for r in spans:
            tb.cell(r, 0).merge(tb.cell(r + 1, 0))
        for r in heads:
            tb.cell(r, 0).merge(tb.cell(r, 1))

    if bcf_pic is not None and len(groups) >= 3 and groups[2]["elements"]:
        g = groups[2]
        rows = [[p["pss"], "", "Total Scope", *g["stages"], "Progress"]] + _civil_rows(g["elements"])
        x, y, cx, cy = bcf_pic.left, bcf_pic.top, bcf_pic.width, bcf_pic.height
        remove_shape(bcf_pic)
        gf = new_table(slide, x, y, cx, cy, rows, [0.9, 0.9, 0.9, 1.1, 1.6, 1.1, 1.1, 0.9],
                       size=10, row_fills={1: PEACH}, bold_cols=(0,))
        tb = gf.table
        tb.cell(0, 0).merge(tb.cell(0, 1))
        tb.cell(1, 0).merge(tb.cell(2, 0))

    charts = sorted((sh for sh in slide.shapes if getattr(sh, "has_chart", False) and sh.has_chart),
                    key=lambda s: -s.height)
    for chart_shape, g_list in zip(charts, (groups[:2], groups[2:3])):
        elements = [e for g in g_list for e in g["elements"]]
        if not elements:
            continue
        cd = CategoryChartData(number_format="0%")
        vals = []
        for e in elements:
            cat = cd.add_category(e["element"])
            cat.add_sub_category("Plan")
            cat.add_sub_category("Actual")
            vals += [(e["planPct"] or 0) / 100, (e["actualPct"] or 0) / 100]
        cd.add_series("Progress", vals)
        chart = chart_shape.chart
        replace_chart_data(chart, cd)
        colours = []
        for e in elements:
            colours += [PLAN_BLUE, _legend_colour(e["actualPct"] or 0, e["planPct"] or 0)]
        _colour_points(chart.plots[0].series[0], colours)
        chart.value_axis.minimum_scale = 0
        chart.value_axis.maximum_scale = 1

    _polish_civil_legend(slide)


def fill_electrical(slide, p) -> None:
    items = (p.get("electrical") or {}).get("items") or []
    pics = pictures(slide)
    if pics and items:
        rows = [["", "UoM", "Scope", "Plan", "Actual", "Plan %", "Actual %"]]
        for it in items:
            rows.append([it["element"], it["uom"], _n(it["scope"]), _n(it["plan"]),
                         _n(it["actual"]), _p(it["planPct"]), _p(it["actualPct"])])
        pic = pics[0]
        x, y, cx, cy = pic.left, pic.top, pic.width, pic.height
        remove_shape(pic)
        new_table(slide, x, y, cx, cy, rows, [1.45, 0.9, 1.0, 1.0, 1.1, 1.0, 1.0],
                  size=11, header_fill=HEADER_PURPLE, header_color=WHITE)
    chart_shape = next((sh for sh in slide.shapes if getattr(sh, "has_chart", False) and sh.has_chart), None)
    if chart_shape is not None and items:
        cd = CategoryChartData(number_format="0%")
        cd.categories = [it["element"] for it in items]
        cd.add_series("Plan %", [(it["planPct"] or 0) / 100 for it in items])
        cd.add_series("Actual %", [(it["actualPct"] or 0) / 100 for it in items])
        chart = chart_shape.chart
        replace_chart_data(chart, cd)
        _colour_points(chart.plots[0].series[0], [PLAN_BLUE] * len(items))
        _colour_points(chart.plots[0].series[1],
                       [_legend_colour(it["actualPct"] or 0, it["planPct"] or 0) for it in items])


MANPOWER_STACK = ["11", "12", "05B", "08B", "09", "10B"]


def fill_manpower(slide, projects, d, key_plan: str, key_act: str, label_suffix: str) -> None:
    pics = pictures(slide)
    by = {pss_key(p["pss"]): p for p in projects}
    months = sorted({s["month"] for p in projects for s in (p.get("manpower") or [])
                     if s.get(key_plan) or s.get(key_act)})
    if not pics or not months:
        return
    cd = CategoryChartData(number_format="0")
    for m in months:
        c = cd.add_category(_mon(m))
        c.add_sub_category("Plan")
        c.add_sub_category("Act")
    order = [k for k in MANPOWER_STACK if k in by]
    plan_tot = [0.0] * len(months)
    act_tot = [0.0] * len(months)
    for k in order:
        s_by = {s["month"]: s for s in by[k].get("manpower") or []}
        vals = []
        for i, m in enumerate(months):
            s = s_by.get(m) or {}
            pv, av = s.get(key_plan), s.get(key_act)
            plan_tot[i] += pv or 0
            act_tot[i] += av or 0
            vals += [pv or None, av or None]
        cd.add_series(by[k]["pss"].replace("(", "").replace(")", ""), vals)
    cd.add_series("Overall Plan", [v for i in range(len(months)) for v in (round(plan_tot[i]), None)])
    cd.add_series("Overall Actual", [v for i in range(len(months)) for v in (None, round(act_tot[i]))])
    chart = _chart_in_box(slide, pics[0], XL_CHART_TYPE.COLUMN_STACKED, cd)
    chart.has_legend = False
    chart.font.size = Pt(9)
    _move_to_line(chart, 2, secondary=False)
    _light_gridlines(chart)
    _span_blanks(chart)
    _add_data_table(chart)
    _series_fill(chart, [PROJECT_COLOURS[k] for k in order] + [OVERALL_PLAN, OVERALL_ACTUAL],
                 line_from=len(order))
    line = chart.plots[1]
    line.has_data_labels = True
    line.data_labels.show_value = True
    line.data_labels.font.size = Pt(9)
    line.data_labels.font.bold = True
    note = _title_shape(slide, "Note:")
    if note is not None:
        set_text(note, (_manual(d, "manpower") or {}).get("note") or "")
    title = _title_shape(slide, "Deployment")
    if title is not None and label_suffix:
        base = title.text_frame.text.split("- PSS")[0].rstrip()
        set_text(title, f"{base}- {label_suffix}")


def _weeks(ym: str) -> int:
    """Weeks in a month as the pack counts them - one per Monday."""
    y, m = int(ym[:4]), int(ym[5:7])
    return sum(1 for day in range(1, monthrange(y, m)[1] + 1) if date(y, m, day).weekday() == 0)


def fill_contractor(slide, p, d, as_of: str) -> None:
    pics = pictures(slide)
    man = _manual(d, f"contractor.{pss_key(p['pss'])}") or {}
    if not pics or not man:
        # No one has entered this project's contractor manpower yet - the
        # template's own picture stays rather than swapping in an empty
        # table (BESS PMAG, 2026-09-26): a blank table looks broken, and
        # nothing here is measured data to show instead.
        return
    months = man.get("months") or [_add_months(as_of, i - 8) for i in range(9)]
    n_weeks = sum(_weeks(m) for m in months)
    contractors = man.get("rows") or [{"description": "", "contractor": ""} for _ in range(3)]
    head0 = ["SN", "Description", "Contractor", "Forecast & Actual"]
    head1 = ["", "", "", ""]
    for m in months:
        for w in range(1, _weeks(m) + 1):
            head0.append(_mon(m) if w == 1 else "")
            head1.append(f"W{w}")
    head0.append("Past Month Average")
    head1.append("")
    rows = [head0, head1]
    prev = months[-2] if len(months) > 1 else months[-1]
    start = sum(_weeks(m) for m in months[:months.index(prev)])
    prev_idx = list(range(start, start + _weeks(prev)))

    def cells(vals, colour=None):
        out = []
        for j in range(n_weeks):
            v = vals[j] if j < len(vals) else None
            out.append("" if v is None else ((_n(v), colour) if colour else _n(v)))
        xs = [vals[j] for j in prev_idx if j < len(vals) and vals[j] is not None]
        a = _n(sum(xs) / len(xs)) if xs else ""
        out.append((a, colour) if (colour and a) else a)
        return out

    tot_f, tot_a, have = [None] * n_weeks, [None] * n_weeks, False
    for i, c in enumerate(contractors, start=1):
        f = list(c.get("forecast") or [])
        a = list(c.get("actual") or [])
        sf = [(f[j] - a[j]) if j < len(f) and j < len(a) and f[j] is not None and a[j] is not None
              else None for j in range(n_weeks)]
        for j in range(n_weeks):
            if j < len(f) and f[j] is not None:
                tot_f[j] = (tot_f[j] or 0) + f[j]
                have = True
            if j < len(a) and a[j] is not None:
                tot_a[j] = (tot_a[j] or 0) + a[j]
        rows.append([str(i), c.get("description", ""), c.get("contractor", ""), "Forecast", *cells(f)])
        rows.append(["", "", "", ("Actual", GREEN), *cells(a, GREEN)])
        rows.append(["", "", "", ("Shortfall", RED), *cells(sf, RED)])
    sf_t = [(x - y) if x is not None and y is not None else None for x, y in zip(tot_f, tot_a)]
    rows.append(["Total", "", "", "Forecast", *cells(tot_f if have else [])])
    rows.append(["", "", "", ("Actual", GREEN), *cells(tot_a if have else [], GREEN)])
    rows.append(["", "", "", ("Shortfall", RED), *cells(sf_t if have else [], RED)])

    pic = pics[0]
    x, y, cx, cy = pic.left, pic.top, pic.width, pic.height
    remove_shape(pic)
    gf = new_table(slide, x, y, cx, cy, rows, [0.35, 1.2, 1.1, 1.0] + [0.42] * n_weeks + [0.8],
                   size=7, header_rows=(0, 1), header_fill=HEADER_PURPLE, header_color=WHITE)
    tb = gf.table
    col = 4
    for m in months:
        w = _weeks(m)
        if w > 1:
            tb.cell(0, col).merge(tb.cell(0, col + w - 1))
        col += w
    for c in (0, 1, 2, 3, len(rows[0]) - 1):
        tb.cell(0, c).merge(tb.cell(1, c))
    r = 2
    for _ in contractors:
        for c in (0, 1, 2):
            tb.cell(r, c).merge(tb.cell(r + 2, c))
        r += 3
    tb.cell(r, 0).merge(tb.cell(r + 2, 2))


def fill_critical(slide, d) -> None:
    t = tables(slide)[0]
    rows = (_manual(d, "critical") or {}).get("rows") or [[""] * 7 for _ in range(3)]
    set_body(t, 2, [[str(i), *r] for i, r in enumerate(rows, start=1)], proto=2)


def fill_financial(slide, d) -> None:
    man = _manual(d, "financial") or {}
    if not man:
        # No spend/EAC figures entered yet - leave the template's own table
        # and chart untouched rather than blanking every row (2026-09-26).
        return
    t = tables(slide)[0]
    table = t.table
    months = man.get("months") or [table.cell(0, c).text for c in range(1, len(table.columns))]
    set_row(t, 0, months, 1)
    keys = ["budgetedCum", "budgetedMonth", "actualCum", "actualMonth"]
    series = {k: (man.get(k) or [None] * len(months)) for k in keys}
    for r, k in enumerate(keys, start=1):
        set_row(t, r, ["" if v in (None, "") else _n(v) for v in series[k]], 1)
    chart_shape = next((sh for sh in slide.shapes if getattr(sh, "has_chart", False) and sh.has_chart), None)
    if chart_shape is not None:
        def num(vs):
            return [None if v in (None, "") else float(v) for v in vs]
        cd = CategoryChartData(number_format="#,##0")
        cd.categories = months
        cd.add_series("Monthly Budgeted", num(series["budgetedMonth"]))
        cd.add_series("Monthly Actual", num(series["actualMonth"]))
        cd.add_series("Budgeted- cumulative", num(series["budgetedCum"]))
        cd.add_series("Actual Cumulative", num(series["actualCum"]))
        replace_chart_data(chart_shape.chart, cd)


def fill_engineering(slide, d, as_of: str) -> None:
    t = tables(slide)[0]
    table = t.table
    mdl = _manual(d, "engineering") or {}
    # The MDL's own "as of" label where one was uploaded - the P6 data date
    # otherwise, so the header is never left as the template's stale month.
    set_text(table.cell(0, 3), f"Overall Status up to {mdl.get('asOfLabel') or _mon(as_of)}")
    mdl_link = _title_shape(slide, "MDL Link")
    if mdl_link is not None:
        set_text(mdl_link, f"MDL: {mdl['sourceFile']}, uploaded {_d(mdl['uploadedAt'])}"
                 if mdl.get("sourceFile") else "MDL: not yet uploaded")
    man = mdl.get("rows") or {}
    for r in range(4, len(table.rows)):
        m = man.get(table.cell(r, 0).text.strip()) or {}
        cats = list(m.get("cat") or []) + [None] * 5
        cats = cats[:5]
        total = m.get("total")
        filled = [float(c) for c in cats if c not in (None, "")]
        j = sum(filled) if filled else None
        k = f"{j / float(total) * 100:.0f}%" if j is not None and total else ""
        set_row(t, r, [m.get("dates", ""), "" if total is None else _n(total),
                       "" if m.get("received") is None else _n(m["received"]),
                       *["" if c in (None, "") else _n(c) for c in cats],
                       "" if m.get("review") is None else _n(m["review"]),
                       "" if j is None else _n(j), k, m.get("remarks", "")], 1)


def _title_shape(slide, needle: str):
    return next((sh for sh in slide.shapes if sh.has_text_frame
                 and needle.lower() in sh.text_frame.text.lower()), None)


def _pool_fill(prs, pool: List[Any], rows: List[List[Any]], per_slide: int, title_fn) -> None:
    """Spread rows over template slides sharing one table layout - copying
    the last when there are more rows than the template has slides, dropping
    the ones not needed."""
    chunks = [rows[i:i + per_slide] for i in range(0, len(rows), per_slide)] or [[]]
    slides = list(pool)
    while len(slides) < len(chunks):
        slides.append(duplicate_slide(prs, slides[-1]))
    for sl in slides[len(chunks):]:
        delete_slide(prs, sl)
    for k, (sl, chunk) in enumerate(zip(slides, chunks), start=1):
        set_body(tables(sl)[0], 1, chunk, proto=1, row_height=Emu(457200))
        title_fn(sl, k, len(chunks))


def fill_ordering(prs, pool, projects, d, kind: str, label: str, group_idx: int) -> None:
    key = "packages" if kind == "Supply" else "servicePackages"
    overrides = (_manual(d, f"ordering.{group_idx}.{kind.lower()}") or {}).get("overrides") or {}
    order: List[str] = []
    by_label: Dict[str, List[Any]] = {}
    known = [lab for lab, _n, _u in TEMPLATE_PACKAGES]
    for p in projects:
        for pk in p.get(key) or []:
            norm = _package_label(pk)
            if norm not in by_label:
                order.append(norm)
                by_label[norm] = []
            by_label[norm].append((p, pk))
    # The pack's own package sequence first, anything else after it.
    first_seen = {n: i for i, n in enumerate(order)}
    order.sort(key=lambda n: (known.index(n) if n in known else len(known), first_seen[n]))
    rows, all_placed = [], True
    for i, norm in enumerate(order, start=1):
        # One line per project, even where the pack's package spans two P6
        # packages (DC and LT cable).
        seen, entries = set(), []
        for p, pk in by_label[norm]:
            if p["pss"] not in seen:
                seen.add(p["pss"])
                entries.append((p, pk))
        label_txt = norm
        qty, release, update = [], [], []
        for p, pk in entries:
            q = pk.get("scopeQty")
            unit = "NOS" if re.search(r"\bnos\b", pk["package"], re.I) else (
                "SET" if re.search(r"\bsets?\b", pk["package"], re.I) else "LOT")
            qty.append(f"{q} {unit}" if q else "1 LOT")
            m = _placement(pk)
            release.append(_af(m))
            if m and m.get("actualFinish"):
                update.append(f"Order placed for {p['pss']} on {_d(m['actualFinish'])}.")
            else:
                all_placed = False
        ov = overrides.get(label_txt) or {}
        colour = GREEN if len(update) == len(entries) else BLACK
        rows.append([(v, colour) for v in (
            str(i), label_txt, "\n".join(qty),
            ov.get("specIssue", ""), ov.get("verified", "NA"), ov.get("tber", ""),
            ov.get("vendors", ""), ov.get("offer", ""), ov.get("nfa", ""),
            "\n".join(release), ov.get("update") or "\n".join(update))])

    def title(sl, k, total):
        sh = _title_shape(sl, "ordering Status")
        if sh is not None:
            set_text(sh, f"{kind} ordering Status ({label})" + (" - Completed" if all_placed else ""))

    _pool_fill(prs, pool, rows, 9, title)


def fill_approvals(prs, pool, projects, d, label: str) -> None:
    meta = _manual(d, "approvals") or {}
    by_name: Dict[str, List[Any]] = {}
    order: List[str] = []
    for p in projects:
        for a in p.get("approvals") or []:
            norm = re.sub(r"\s+", " ", a["name"].lower()).strip()
            if norm not in by_name:
                order.append(norm)
                by_name[norm] = []
            by_name[norm].append((p, a))
    rows = []
    for i, norm in enumerate(order, start=1):
        # A group's approval is only through when its last project is.
        _p_, a = max(by_name[norm], key=lambda e: e[1].get("actualFinish") or e[1].get("forecastFinish") or "")
        owner = next((v for k, v in APPROVAL_OWNERS.items() if k in norm), ("", ""))
        ov = meta.get(a["name"]) or {}
        colour = GREEN if a["status"] == "Completed" else BLACK
        rows.append([(v, colour) for v in (
            str(i), a["name"], ov.get("responsible", owner[0]), ov.get("authority", owner[1]),
            _d(a.get("baselineStart")), _d(a.get("baselineFinish")),
            _d(a["actualStart"]) if a.get("actualStart") else _d(a.get("forecastStart"), star=True),
            _af(a), ov.get("remarks") or "")])

    def title(sl, k, total):
        sh = _title_shape(sl, "Approvals (")
        if sh is not None:
            set_text(sh, f"Statutory and Other Approvals ({label})")
        for extra in [s for s in sl.shapes if s.has_text_frame and s.text_frame.text.startswith("*")]:
            set_text(extra, "")

    _pool_fill(prs, pool, rows, 9, title)


def _relabel(slide, text: str, paragraph: Optional[int] = None) -> None:
    sh = next((s for s in slide.shapes if s.has_text_frame and s.text_frame.text.strip()
               and not s.name.startswith("Slide Number")), None)
    if sh is None:
        return
    if paragraph is None:
        set_text(sh, text)
    else:
        set_paragraph(sh, paragraph, text)


# ── Composition ─────────────────────────────────────────────────────────────
def _compose(projects: List[Dict[str, Any]], d: Dict[str, Any], single: bool) -> bytes:
    prs = Presentation(str(REFERENCE))
    T = {i: s for i, s in enumerate(prs.slides, start=1)}
    by = {pss_key(p["pss"]): p for p in projects}
    as_of = max((p.get("lastActualMonth") for p in projects if p.get("lastActualMonth")),
                default=date.today().strftime("%Y-%m"))
    # Major Milestones is curated commentary, not a system feed - it keeps the
    # reference template's own text untouched, the same as Contractor
    # Manpower/Financial S-Curve when nothing has been entered (2026-09-26).
    drop: set = set()
    one = projects[0] if single else None
    scope_label = one["pss"] if single else None

    fill_cover(T[1], one)
    fill_capacity(T[2], projects)
    fill_salient(T[3], projects, d)
    fill_commissioning(T[5], projects, d, as_of)
    fill_engineering(T[12], d, as_of)
    fill_critical(T[44], d)
    fill_financial(T[45], d)
    fill_manpower(T[35], projects, d, "planMonth", "earnedMonth", scope_label or "")
    fill_manpower(T[36], projects, d, "planManpower", "earnedManpower", scope_label or "")

    for key in PSS_KEYS:
        p = by.get(key)
        own = [S_SCURVE[key], S_PROC[key], S_CIVIL[key], S_ELEC[key], S_CONTRACTOR[key]]
        if not p:
            drop.update(own)
            continue
        fill_scurve(T[S_SCURVE[key]], p, d)
        fill_civil(T[S_CIVIL[key]], p)
        fill_electrical(T[S_ELEC[key]], p)
        fill_contractor(T[S_CONTRACTOR[key]], p, d, as_of)
        fill_procurement(prs, T[S_PROC[key]], p, d, as_of)

    for gi, g in enumerate(GROUPS):
        members = [by[k] for k in g["keys"] if k in by]
        if not members:
            drop.update([g["progress"], g["ordering"], *g["supply"], *g["service"],
                         g["approvals_section"], *g["approvals"]])
            continue
        label = scope_label or g["label"]
        fill_ordering(prs, [T[i] for i in g["supply"]], members, d, "Supply", label, gi)
        fill_ordering(prs, [T[i] for i in g["service"]], members, d, "Service", label, gi)
        fill_approvals(prs, [T[i] for i in g["approvals"]], members, d, label)
        if single:
            _relabel(T[g["progress"]], f"{scope_label} Progress")
            _relabel(T[g["ordering"]], f"Ordering Status {scope_label}")
            _relabel(T[g["approvals_section"]], scope_label, paragraph=1)

    if single:
        _relabel(T[13], f"Procurement Status: {scope_label}")
        _relabel(T[34], f"Manpower & Mandays Status: {scope_label}")
    # Physical Progress : PSS 10A/5A/8A S-Curve - a leftover phase-1 naming
    # that predates the current six projects (10B/05B/08B), manual-entry-only
    # and never populated. Dropped unconditionally (2026-09-26).
    drop.update(S_PHASE1)

    for i in sorted(drop):
        delete_slide(prs, T[i])
    _strip_link_boxes(prs)
    _strip_comments(prs)
    _strip_title_highlights(prs)
    _add_missing_page_numbers(prs)
    if S_THANK_YOU not in drop:
        move_slide_to_end(prs, T[S_THANK_YOU])
    buf = BytesIO()
    prs.save(buf)
    return buf.getvalue()


def _strip_link_boxes(prs) -> None:
    """The template's "Link" text boxes (Civil/Electrical pages) point at the
    old SharePoint workbooks those pages were pasted from - meaningless now
    that the numbers are live. Dropped everywhere, not just those pages, so
    a copy that turns up elsewhere is caught too."""
    for slide in prs.slides:
        for sh in list(slide.shapes):
            if sh.has_text_frame and sh.text_frame.text.strip().lower() == "link":
                remove_shape(sh)


def _strip_title_highlights(prs) -> None:
    """The template marks most of its own titles with a text highlight (green
    on 53 slides, yellow on 2 more inconsistently) - a review-draft artefact,
    not something the approved pack's own titles should carry. Dropped
    everywhere, not just where it was first noticed."""
    for slide in prs.slides:
        for sh in slide.shapes:
            if not sh.has_text_frame:
                continue
            for hl in list(sh._element.iter(qn("a:highlight"))):
                hl.getparent().remove(hl)


def _polish_civil_legend(slide) -> None:
    """The Civil slide's own Plan/Actual colour key, shrunk and tidied: the
    template's own 9pt, top-anchored, 0.51in-tall table reads as an
    afterthought pinned under the charts above it."""
    for sh in slide.shapes:
        if not (getattr(sh, "has_table", False) and sh.has_table):
            continue
        tbl = sh.table
        if len(tbl.rows) != 2 or tbl.cell(0, 1).text.strip() != "Plan":
            continue
        row_h = Inches(0.15)
        sh.height = row_h * 2
        for r in range(2):
            tbl.rows[r].height = row_h
        for r in range(2):
            for c in range(5):
                cell = tbl.cell(r, c)
                cell.vertical_anchor = MSO_ANCHOR.MIDDLE
                cell.margin_top = cell.margin_bottom = Emu(0)
                cell.margin_left = cell.margin_right = Emu(45720)
                for para in cell.text_frame.paragraphs:
                    for run in para.runs:
                        run.font.size = Pt(8)
        break


def _strip_comments(prs) -> None:
    """The template carries its own reviewers' comments (13 in the reference
    deck) as modern-comment parts linked from individual slides. Those are
    internal review notes on the approved template, not on this run's
    numbers, and must not travel into a deck someone downloads. Dropping the
    relationship is enough - a part no slide points to is never written."""
    reltype = "http://schemas.microsoft.com/office/2018/10/relationships/comments"
    for slide in prs.slides:
        for rid in [rid for rid, rel in slide.part.rels.items() if rel.reltype == reltype]:
            slide.part.drop_rel(rid)


def _add_missing_page_numbers(prs) -> None:
    """A page number on every slide. The template leaves it off about a
    third of its own slides (inconsistently - some pairs of project pages
    have it, some don't), which reads as broken once reviewers cite a page
    by number. The stamp is cloned from the template's own placeholder, so
    an added number looks native and stays correct via the same auto-paging
    field every other slide already uses."""
    def has_page_field(sh):
        return sh.has_text_frame and sh._element.find(".//" + qn("a:fld")) is not None

    donor = None
    for slide in prs.slides:
        # The real PLACEHOLDER (not the couple of slides where the template
        # itself used a plain text box) is the most common shape, so it is
        # the one every added stamp should look like.
        found = next((sh for sh in slide.shapes if sh.is_placeholder and has_page_field(sh)), None)
        if found is not None:
            donor = found._element
            break
    if donor is None:
        return
    for slide in prs.slides:
        if any(has_page_field(sh) for sh in slide.shapes):
            continue
        stamp = copy.deepcopy(donor)
        # A cloned shape id must be unique on its new slide, not just valid
        # on the donor's.
        used = {sh.shape_id for sh in slide.shapes}
        cNvPr = stamp.find(".//" + qn("p:cNvPr"))
        cNvPr.set("id", str(max(used, default=0) + 1))
        slide.shapes._spTree.append(stamp)


def _project_from_single(d: Dict[str, Any]) -> Dict[str, Any]:
    meta, decl = d["meta"], d["meta"]["declared"]
    return {
        "pss": meta["pss"], "spv": meta["spv"], "plot": meta["plot"],
        "powerMw": decl["powerMw"], "energyMwh": decl["energyMwh"],
        "dispatchableMwh": decl["dispatchableMwh"], "containers": decl["containers"],
        "batteryOem": decl["batteryOem"],
        "buckets": d["progress"]["buckets"], "sCurve": d["sCurve"]["series"],
        "lastActualMonth": d["sCurve"].get("lastActualMonth"),
        "packages": d["procurement"]["packages"],
        "servicePackages": d["procurement"].get("servicePackages") or [],
        "sap": d["procurement"]["sap"],
        "approvals": d["approvals"]["items"],
        "approvalsDone": d["approvals"]["completed"], "approvalsTotal": d["approvals"]["total"],
        "civil": d.get("civil") or {}, "electrical": d.get("electrical") or {},
        "manpower": (d.get("manpower") or {}).get("series") or [],
    }


def build_project_pptx(d: Dict[str, Any]) -> bytes:
    return _compose([_project_from_single(d)], d, single=True)


def build_portfolio_pptx(d: Dict[str, Any]) -> bytes:
    return _compose(d["projects"], d, single=False)
