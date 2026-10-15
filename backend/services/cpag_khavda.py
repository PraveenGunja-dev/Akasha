"""
The Khavda CPAG packs, one per technology.

Khavda is issued as a monthly report (uploaded as
"01. Khavda_CPAG_Energy_Monthly Report_Aug'26.pptx"); scripts/split_khavda_deck.py
splits it into assets/cpag_khavda_solar_reference.pptx and
assets/cpag_khavda_wind_reference.pptx. Each pack fills the pages it has a
source for from P6 / SAP / project_mapping (services/cpag_khavda_<tech>_pptx.py);
every other page stays as the report issued it, and the viewer says which is
which on each page. Rendering and caching reuse the Solar / Wind pack's own
machinery, so a deck's pages and its download are the same file.
"""
import hashlib
import importlib
import json
import subprocess
from datetime import date
from pathlib import Path
from typing import Any, Dict

from sqlalchemy.orm import Session

BACKEND = Path(__file__).resolve().parent.parent
TECHNOLOGIES = ("solar", "wind")

# 1-based report pages each builder fills from live data; the rest are as issued.
LIVE_PAGES = {
    "solar": {1, 3, 4, 6, 7, 8, 10, 11, 12, 14, 15, 28},
    "wind": {1, 3, 6, 7, 8, 9},
}
LIVE_NOTE = ["Filled from P6 / SAP / project register as of the P6 data date."]
ISSUED_NOTE = ["As issued in the Khavda monthly CPAG report (Aug'26) - not yet connected to live data."]
DECK_NAMES = {"solar": "CPAG_KHAVDA_SOLAR.pptx", "wind": "CPAG_KHAVDA_WIND.pptx"}


def reference_path(tech: str) -> Path:
    return BACKEND / "assets" / f"cpag_khavda_{tech}_reference.pptx"


def _builder(tech: str):
    return importlib.import_module(f"services.cpag_khavda_{tech}_pptx")


def _key(tech: str, data: Dict[str, Any]) -> str:
    h = hashlib.sha1(json.dumps(data, sort_keys=True, default=str).encode())
    h.update(date.today().isoformat().encode())   # the cover and report date follow today's date
    for f in (reference_path(tech), Path(_builder(tech).__file__), Path(__file__)):
        h.update(str(f.stat().st_mtime_ns).encode())
    return h.hexdigest()[:16]


def khavda_pack(tech: str, db: Session) -> Dict[str, Any]:
    """Page list for one technology's Khavda pack, built and rendered on first
    use and again whenever the data or the builder changes."""
    if tech not in TECHNOLOGIES:
        raise ValueError(tech)
    mod = importlib.import_module(f"services.cpag_{tech}_render")
    b = _builder(tech)
    data = getattr(b, f"fetch_{tech}_khavda_data")(db)
    key = _key(tech, data)
    folder = mod.CACHE / key
    meta = folder / "outline.json"
    with mod._lock:
        if not meta.exists():
            folder.mkdir(parents=True, exist_ok=True)
            deck = folder / "deck.pptx"
            deck.write_bytes(getattr(b, f"build_{tech}_deck")(data))
            subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                 "-File", str(mod.SCRIPT), "-Deck", str(deck), "-OutDir", str(folder)],
                check=True, capture_output=True, timeout=900)
            pages = mod._outline(deck)
            for page in pages:   # the shared outline's notes describe the other packs
                notes = (data.get("page_notes") or {}).get(str(page["n"])) or (data.get("page_notes") or {}).get(page["n"])
                page["source"] = notes or (LIVE_NOTE if page["n"] in LIVE_PAGES[tech] else ISSUED_NOTE)
            meta.write_text(json.dumps(pages))
    return {"key": key, "slides": json.loads(meta.read_text()), "asOf": {"p6": None, "sap": None}}
