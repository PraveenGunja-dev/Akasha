"""
The CPAG pack as page images - the on-screen pack is the downloadable file.

The deck is built once per distinct input (data + manual entries + builder),
saved, and rendered page by page through PowerPoint. The viewer shows those
pages and its Download serves that same saved file, so what is reviewed on
screen and what is sent to management cannot differ.
"""
import hashlib
import json
import subprocess
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List

from pptx import Presentation

BACKEND = Path(__file__).resolve().parent.parent
CACHE = BACKEND / "cache" / "cpag"
SCRIPT = BACKEND / "scripts" / "render_pptx.ps1"
_BUILDER_FILES = [BACKEND / "services" / "cpag_pptx.py", BACKEND / "services" / "cpag_render.py",
                  BACKEND / "assets" / "cpag_reference.pptx"]
_lock = threading.Lock()


def deck_key(data: Dict[str, Any]) -> str:
    h = hashlib.sha1()
    h.update(json.dumps(data, sort_keys=True, default=str).encode())
    for f in _BUILDER_FILES:
        h.update(str(f.stat().st_mtime_ns).encode())
    return h.hexdigest()[:16]


def _outline(pptx_path: Path) -> List[Dict[str, Any]]:
    """Title and section for each page, for the viewer's jump list. A
    section-divider page starts a new section, as it does in the pack."""
    prs = Presentation(str(pptx_path))
    out, section = [], "Overview"
    for i, s in enumerate(prs.slides, start=1):
        heads = sorted((sh for sh in s.shapes
                        if sh.has_text_frame and sh.text_frame.text.strip()
                        and not sh.name.startswith("Slide Number")
                        and (sh.top or 0) < 914400 * 1.2),
                       key=lambda sh: sh.top or 0)
        if "Section Header" in s.slide_layout.name:
            heads = [sh for sh in s.shapes if sh.has_text_frame and sh.text_frame.text.strip()
                     and not sh.name.startswith("Slide Number")]
        title = (heads[0].text_frame.text.strip().split("\n")[0] if heads
                 else ("Cover" if i == 1 else "Project Capacity" if i == 2 else f"Page {i}"))
        title = title.replace("\n", " ")
        if "Section Header" in s.slide_layout.name:
            section = title
        out.append({"n": i, "title": title[:120], "section": section})
    return out


def render(data: Dict[str, Any], build: Callable[[Dict[str, Any]], bytes]) -> Dict[str, Any]:
    key = deck_key(data)
    folder = CACHE / key
    meta_file = folder / "outline.json"
    with _lock:
        if not meta_file.exists():
            folder.mkdir(parents=True, exist_ok=True)
            deck = folder / "deck.pptx"
            deck.write_bytes(build(data))
            subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                 "-File", str(SCRIPT), "-Deck", str(deck), "-OutDir", str(folder)],
                check=True, capture_output=True, timeout=900)
            meta_file.write_text(json.dumps(_outline(deck)))
    return {"key": key, "slides": json.loads(meta_file.read_text())}


def page_path(key: str, n: int) -> Path:
    return CACHE / key / f"s{n:03d}.png"


def deck_path(key: str) -> Path:
    return CACHE / key / "deck.pptx"
