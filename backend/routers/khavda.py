"""
Khavda CPAG packs: /api/solar-khavda and /api/wind-khavda.

Separate namespaces from /api/solar (Rajasthan) and /api/wind, so each is gated
on its own portfolio cluster (services/access.py NAMESPACE_CLUSTERS): Khavda
solar needs "Solar Khavda", never "Solar Rajasthan". Same route shape as the
other packs, so the viewer needs no special case beyond the base URL.
"""
import re
from importlib import import_module

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from database import get_db

from services.cpag_khavda import DECK_NAMES, TECHNOLOGIES, khavda_pack

_PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


def _cache_key(key: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{16}", key):
        raise HTTPException(404, "Unknown pack")
    return key


def _router(tech: str) -> APIRouter:
    router = APIRouter(prefix=f"/api/{tech}-khavda", tags=[f"{tech}-khavda"])
    render = lambda: import_module(f"services.cpag_{tech}_render")  # noqa: E731 - loaded on first use

    @router.get("/portfolio/cpag/preview")
    def preview(db: Session = Depends(get_db)):
        """The Khavda pack as page images of the downloadable deck itself."""
        return khavda_pack(tech, db)

    @router.get("/cpag/preview/{key}/{n}.png")
    def preview_page(key: str, n: int):
        path = render().page_path(_cache_key(key), n)
        if not path.exists():
            raise HTTPException(404, "No such page")
        return FileResponse(path, media_type="image/png",
                            headers={"Cache-Control": "public, max-age=86400"})

    @router.get("/cpag/preview/{key}/deck.pptx")
    def preview_deck(key: str):
        path = render().deck_path(_cache_key(key))
        if not path.exists():
            raise HTTPException(404, "No such file")
        return FileResponse(path, media_type=_PPTX, filename=DECK_NAMES[tech],
                            headers={"Cache-Control": "no-store"})

    return router


solar_router, wind_router = (_router(t) for t in TECHNOLOGIES)
