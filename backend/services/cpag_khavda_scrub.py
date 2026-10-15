"""
Strip the Khavda report's own figures from a split reference deck, keeping its
format: titles, column headings, row labels, layout, colours and chart styling.

The reference decks are the issued monthly report cut by technology, so every
table cell and chart point in them is that report's figure, not data from a
connected system. Each pack scrubs the deck first and then fills only what its
queries can support; anything it cannot fill stays empty, never a stale number.
"""
import re
from typing import Dict, Iterable, Optional

from pptx.oxml.ns import qn

KEEP_TEXT = {"total", "grand total", "summary"}   # row labels that are format, not data


class TableSpec:
    """Which cells of a table are format. Everything else is blanked.

    header_rows - leading rows kept whole (column headings)
    keep_rows   - further rows kept whole (sub-headings inside the body)
    keep_cols   - columns kept for every body row (row labels, UOM)
    """
    def __init__(self, header_rows: int = 1, keep_rows: Iterable[int] = (), keep_cols: Iterable[int] = ()):
        self.header_rows = header_rows
        self.keep_rows = set(keep_rows)
        self.keep_cols = set(keep_cols)


def _blank_cell(cell) -> None:
    for p in cell.text_frame.paragraphs:
        for r in p.runs:
            r.text = ""


def blank_table(tbl, spec: TableSpec) -> None:
    for r in range(len(tbl.rows)):
        if r < spec.header_rows or r in spec.keep_rows:
            continue
        for c in range(len(tbl.columns)):
            if c in spec.keep_cols:
                continue
            cell = tbl.cell(r, c)
            if cell.text_frame.text.strip().lower() in KEEP_TEXT:
                continue
            _blank_cell(cell)


def blank_chart(chart) -> None:
    """Drop every plotted value, keeping categories, series styling and axes."""
    for val in chart._chartSpace.iter(qn("c:val")):
        for cache in val.iter(qn("c:numCache")):
            for pt in cache.findall(qn("c:pt")):
                cache.remove(pt)


_FIGURE_IN_TITLE = re.compile(r"\s*\(\s*[\d,.]+\s*MW\w*\s*\)")


def _walk(shapes):
    for sh in shapes:
        if sh.shape_type == 6:
            yield from _walk(sh.shapes)
        else:
            yield sh


def scrub_deck(prs, tables: Dict[int, TableSpec], blank_charts: Iterable[int] = (),
               blank_text: Optional[Dict[int, Iterable[str]]] = None) -> None:
    """tables / blank_charts are keyed by 1-based slide number.

    blank_text names text boxes (by shape name) whose whole text is a figure or
    a remark rather than a label. A capacity in a title, e.g. "(4,639 MW)", is
    dropped everywhere."""
    blank_text = blank_text or {}
    charts = set(blank_charts)
    for n, slide in enumerate(prs.slides, start=1):
        for sh in _walk(slide.shapes):
            if getattr(sh, "has_table", False) and sh.has_table and n in tables:
                blank_table(sh.table, tables[n])
            elif getattr(sh, "has_chart", False) and sh.has_chart and n in charts:
                blank_chart(sh.chart)
            elif sh.has_text_frame:
                if sh.name in blank_text.get(n, ()):
                    for p in sh.text_frame.paragraphs:
                        for r in p.runs:
                            r.text = ""
                else:
                    for p in sh.text_frame.paragraphs:
                        full = "".join(r.text for r in p.runs)   # the figure can span runs
                        if p.runs and _FIGURE_IN_TITLE.search(full):
                            p.runs[0].text = _FIGURE_IN_TITLE.sub("", full)
                            for r in p.runs[1:]:
                                r.text = ""
