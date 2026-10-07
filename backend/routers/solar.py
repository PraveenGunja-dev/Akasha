import re
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, FileResponse
from sqlalchemy import text
from sqlalchemy.orm import Session
from typing import Dict, Any, List

from datetime import date
from database import get_db
from services.cpag_solar_pptx import build_portfolio_pptx, fetch_scurve_data, fetch_manpower_data
from services.cpag_solar_render import render, page_path, deck_path

router = APIRouter(prefix="/api/solar", tags=["solar"])

def _cache_key(key: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{16}", key):
        raise HTTPException(404, "Unknown pack")
    return key


def _build_project_list(db: Session) -> List[Dict[str, Any]]:
    """The two projects currently in the Solar CPAG template (Bandha, Baiya),
    with their Salient Features fields plus the Overall S Curve data."""
    query = text("""
        SELECT p6.name,
               p6.scheduled_finish_date as cod_actual,
               p6.baseline_finish_date as cod_plan,
               p6.duration_percent_complete as progress_actual,
               p6.duration_percent_complete as progress_plan,
               p6.planned_start_date as start_date,
               pm.spv_name as spv_name
        FROM p6_project p6
        LEFT JOIN project_mapping pm ON p6.name = pm.project_name_from_p6
        WHERE (p6.name ILIKE '%bandha%' OR p6.name ILIKE '%baiya%')
          AND EXISTS (SELECT 1 FROM p6_activity a WHERE a.project_object_id = p6.p6_object_id LIMIT 1)
        ORDER BY p6.name
    """)
    projects = db.execute(query).fetchall()

    proj_list = []
    for p in projects:
        cap_match = re.search(r'(\d+)MW', p.name)
        capacity = cap_match.group(1) if cap_match else ""

        proj_list.append({
            "name": p.name,
            "capacity": f"{capacity} MW",
            "spv": p.spv_name or "-",
            "start_date": p.start_date.strftime("%b-%y") if getattr(p, 'start_date', None) else "-",
            "cod_plan": p.cod_plan.strftime("%d-%b-%y") if p.cod_plan else "-",
            "cod_actual": p.cod_actual.strftime("%d-%b-%y") if p.cod_actual else "-",
            "progress_actual": f"{p.progress_actual * 100:.0f}%" if p.progress_actual else "0%",
            "progress_plan": f"{p.progress_plan * 100:.0f}%" if p.progress_plan else "0%",
            "scurve": fetch_scurve_data(db, p.name),
            "manpower": fetch_manpower_data(db, p.name),
        })
    return proj_list


@router.get("/portfolio/cpag")
def get_portfolio_data(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Returns the raw data used for the CPAG solar pack."""
    # For now, return empty data since we're just structuring it
    return {}


@router.get("/portfolio/cpag/preview")
def preview_portfolio(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """The pack as page images of the downloadable deck itself. render()
    already caches by a hash of the data + builder files, so a plain re-call
    is cheap when nothing has changed and correct when it has."""
    proj_list = _build_project_list(db)
    data: Dict[str, Any] = {
        "project_names": [p["name"] for p in proj_list],
        "projects": proj_list,
        "generation_date": date.today().isoformat()
    }
    out = render(data, build_portfolio_pptx)
    out["asOf"] = {"p6": None, "sap": None}
    return out


@router.get("/cpag/preview/{key}/{n}.png")
def preview_page(key: str, n: int):
    path = page_path(_cache_key(key), n)
    if not path.exists():
        raise HTTPException(404, "No such page")
    return FileResponse(path, media_type="image/png",
                        headers={"Cache-Control": "public, max-age=86400"})


@router.get("/cpag/preview/{key}/deck.pptx")
def preview_deck(key: str):
    """The exact file the preview pages were rendered from. Not cached: the
    key hashes the data + builder files, not this route's own headers (e.g.
    the download filename), so a header-only change here wouldn't bust a
    cached response - a stale name/type could stick in the browser for the
    full max-age with no way to tell the user got it."""
    path = deck_path(_cache_key(key))
    if not path.exists():
        raise HTTPException(404, "No such file")
    return FileResponse(path, media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                        filename="CPAG_RAJASTHAN_SOLAR.pptx",
                        headers={"Cache-Control": "no-store"})


@router.get("/portfolio/cpag.pptx")
def download_portfolio_pptx(db: Session = Depends(get_db)):
    """The portfolio pack as a PowerPoint file."""
    proj_list = _build_project_list(db)
    data: Dict[str, Any] = {
        "project_names": [p["name"] for p in proj_list],
        "projects": proj_list,
        "generation_date": date.today().isoformat()
    }
    return Response(
        content=build_portfolio_pptx(data),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": 'attachment; filename="CPAG_RAJASTHAN_SOLAR.pptx"'},
    )
