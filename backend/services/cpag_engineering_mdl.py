"""
Engineering Progress, from the Master Document List the team uploads.

P6 holds the engineering *deliverable* activities (drawings, specs - 29 per
project on PSS-11, all eventually "Completed"), not a document register with
approval categories. The CPAG pack's Engineering Progress table is a document
register - Cat I-IV* counts, cumulative received/approved - which only the
MDL Excel has (its own "Summary" sheet already has exactly the pack's own
column layout, confirmed against the 3-Sep-26 file: Description / Overall
Completion / Total / Docs. Cum. Received / Cat I-IV* / Documents Under
Review / Cum. Total approved / Approved % / Remarks).

No copy of this file is kept as static data - whatever was most recently
uploaded is what the pack shows. Re-uploading a newer MDL is how the team
refreshes this page.
"""
import re
from datetime import datetime
from io import BytesIO
from typing import Any, Dict, Optional

import openpyxl

SHEET_NAME = "Summary"
# Column letters, fixed by the sheet's own layout (row 4 spells them out as
# A..K, confirmed against the file): Description, Overall Completion, Total,
# Docs Cum Received, Cat I-IV*, Docs Under Review, Cum Total approved,
# Approved %, Remarks.
COLS = {"label": 1, "dates": 2, "total": 3, "received": 4,
        "cat": [5, 6, 7, 8, 9], "review": 10, "remarks": 13}


def _clean(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v).replace("\xa0", "").strip()
    return s if s and s != "-" else None


def _num(v: Any) -> Optional[int]:
    s = _clean(v)
    if s is None:
        return None
    try:
        return int(round(float(s)))
    except ValueError:
        return None


def parse_engineering_mdl(blob: bytes, filename: str) -> Dict[str, Any]:
    """Raises ValueError with a plain-language reason if the file isn't this
    MDL's own "Summary" sheet shape - never guesses at a different layout."""
    try:
        wb = openpyxl.load_workbook(BytesIO(blob), data_only=True, read_only=True)
    except Exception as e:
        raise ValueError(f"Could not open '{filename}' as an Excel file: {e}")

    if SHEET_NAME not in wb.sheetnames:
        raise ValueError(
            f"'{filename}' has no '{SHEET_NAME}' sheet (found: {', '.join(wb.sheetnames)}). "
            f"This needs to be the Phase-II Master Document Log workbook.")
    ws = wb[SHEET_NAME]

    header = ws.cell(1, COLS["label"]).value
    if not header or "description" not in str(header).lower():
        raise ValueError(
            f"'{filename}' > {SHEET_NAME} doesn't look like the Master Document Log "
            f"(cell A1 is '{header}', expected 'Description').")

    as_of_label = None
    status_header = ws.cell(1, 4).value
    if status_header:
        m = re.search(r"up to\s+(.+)$", str(status_header).strip())
        if m:
            as_of_label = m.group(1).strip()

    rows: Dict[str, Dict[str, Any]] = {}
    for r in range(6, ws.max_row + 1):
        label = _clean(ws.cell(r, COLS["label"]).value)
        if not label:
            continue
        if not label.upper().startswith("PSS"):
            break
        rows[label] = {
            "dates": _clean(ws.cell(r, COLS["dates"]).value) or "",
            "total": _num(ws.cell(r, COLS["total"]).value),
            "received": _num(ws.cell(r, COLS["received"]).value),
            "cat": [_num(ws.cell(r, c).value) for c in COLS["cat"]],
            "review": _num(ws.cell(r, COLS["review"]).value),
            "remarks": _clean(ws.cell(r, COLS["remarks"]).value) or "",
        }

    if not rows:
        raise ValueError(
            f"'{filename}' > {SHEET_NAME}: no PSS rows found from row 6 down. "
            f"Check the sheet still has its Summary layout.")

    return {
        "rows": rows, "asOfLabel": as_of_label,
        "sourceFile": filename, "uploadedAt": datetime.utcnow().isoformat(),
    }
