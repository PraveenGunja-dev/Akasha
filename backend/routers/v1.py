"""
/api/v1 — the standardised surface.

Mounted alongside the existing routes, which keep working unchanged. Everything
here follows one contract so a client can predict a URL and a payload without
reading the docs:

  * one canonical identifier          `project_id`, resolved from any alias
  * one filter vocabulary             portfolio / phase / project / page
  * one envelope                      { data, meta }
  * filters are never silently dropped — meta.filters_applied says what the
    server actually scoped by

That last point exists because of a real bug: the UI sends `phase` to six
endpoints and only one of them declares it, so FastAPI discards it and the
dashboard shows Ongoing KPIs beside unfiltered financials.
"""

from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from services import project_identity

router = APIRouter(prefix="/api/v1", tags=["v1"])

PHASES = ("ongoing", "commissioned", "all")
MAX_PAGE_SIZE = 200


def envelope(
    data: Any,
    *,
    filters: dict | None = None,
    sources: list[str] | None = None,
    page: int | None = None,
    page_size: int | None = None,
    total: int | None = None,
) -> dict:
    """The single response shape.

    `filters_applied` is the contract that makes a silently-ignored filter
    impossible: whatever the server scoped by is stated back to the caller.
    """
    meta: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "filters_applied": filters or {},
        "sources": sources or [],
    }
    if page is not None:
        meta.update({"page": page, "page_size": page_size, "total": total})
    return {"data": data, "meta": meta}


def normalise_phase(phase: Optional[str]) -> str:
    """Default is `all` — a client-facing API must not filter silently.

    The UI treats Ongoing as its default and passes `phase=ongoing` explicitly.
    Defaulting to that here would mean an integrator calling /api/v1/projects
    silently receives 48 of 63 projects with nothing in the response to say so,
    which is the single most common cause of "why is our data missing" reports.
    Whatever is applied is always echoed back in meta.filters_applied.
    """
    # Tolerates being handed an unresolved Query() default, which happens when
    # backend code calls these handlers directly rather than over HTTP.
    if not isinstance(phase, str):
        phase = None
    value = (phase or "all").strip().lower()
    if value not in PHASES:
        raise HTTPException(
            status_code=422,
            detail=f"phase must be one of {', '.join(PHASES)} (got {phase!r})",
        )
    return value


@router.get("/projects")
def list_projects(
    portfolio: Optional[str] = None,
    phase: Optional[str] = Query(None, description="ongoing | commissioned | all (default: all)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
):
    """Every project, one canonical id each, with its source-system linkage."""
    normalised = normalise_phase(phase)
    identities = project_identity.resolve_all(db, portfolio=portfolio, phase=normalised)
    identities.sort(key=lambda i: i.name.lower())

    start = (page - 1) * page_size
    window = identities[start : start + page_size]

    return envelope(
        [i.to_dict() for i in window],
        filters={"portfolio": portfolio, "phase": normalised},
        sources=["P6", "SAP", "TC", "Pulse"],
        page=page,
        page_size=page_size,
        total=len(identities),
    )


@router.get("/projects/{project_id}")
def get_project(project_id: str, db: Session = Depends(get_db)):
    """One project by canonical id.

    `project_id` is tolerant: the canonical ProjectMapping.project_id, the
    numeric mapping id, a P6 object id, or the project name all resolve here.
    The response always answers with the canonical id.
    """
    identity = project_identity.resolve(db, project_id)
    if identity is None:
        raise HTTPException(status_code=404, detail=f"No project matching {project_id!r}")
    return envelope(identity.to_dict(), sources=["P6", "SAP", "TC", "Pulse"])


@router.get("/projects/{project_id}/identity")
def get_project_identity(project_id: str, db: Session = Depends(get_db)):
    """The key map for one project — what to call it in each source system.

    Useful to an integrator building their own joins, and the honest answer to
    "why is quality empty for this project": it will be listed under `unlinked`.
    """
    identity = project_identity.resolve(db, project_id)
    if identity is None:
        raise HTTPException(status_code=404, detail=f"No project matching {project_id!r}")

    data = identity.to_dict()
    data["keys"] = {
        "canonical": identity.project_id,
        "p6": {"project_id": identity.p6_project_id, "object_id": identity.p6_object_id},
        "sap": {"plant_code": identity.sap_plant_code, "wbs_prefixes": identity.sap_wbs_prefixes},
        "tc": {"mapping_id": identity.tc_mapping_id},
        "pulse": {"project_name": identity.pulse_project_name},
    }
    return envelope(data, sources=["P6", "SAP", "TC", "Pulse"])


@router.get("/coverage")
def get_coverage(
    portfolio: Optional[str] = None,
    phase: Optional[str] = Query(None, description="ongoing | commissioned | all (default: all)"),
    db: Session = Depends(get_db),
):
    """How much of the portfolio actually links to each source system.

    Worth calling before trusting an aggregate. Pulse in particular resolves for
    roughly a third of projects, because it stores a free-text project name
    rather than a key — so an empty quality response usually means "not linked",
    not "no non-conformances".
    """
    normalised = normalise_phase(phase)
    identities = project_identity.resolve_all(db, portfolio=portfolio, phase=normalised)
    total = len(identities)

    breakdown = {}
    for system in project_identity.SOURCE_SYSTEMS:
        linked = sum(1 for i in identities if system in i.linked)
        breakdown[system] = {
            "linked": linked,
            "total": total,
            "pct": round((linked / total) * 100) if total else 0,
            "unlinked_project_ids": [
                i.project_id for i in identities if system not in i.linked
            ][:50],
        }

    return envelope(
        {"total_projects": total, "systems": breakdown},
        filters={"portfolio": portfolio, "phase": normalised},
        sources=["P6", "SAP", "TC", "Pulse"],
    )
