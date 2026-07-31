"""REST adapters for canonical Pulse quality analytics."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from services.quality_analytics_service import QualityAnalyticsService


router = APIRouter(prefix="/api/quality")


def _redact_candidates(data: dict) -> dict:
    """Do not expose catalog candidates through routes without an auth scope."""
    data.pop("candidates", None)
    for warning in data.get("warnings", ()):
        warning.pop("candidates", None)
    return data


def _raise_for_resolution(resolution_status: str) -> None:
    if resolution_status == "ambiguous":
        raise HTTPException(status_code=409, detail="Project reference is ambiguous")
    if resolution_status != "resolved":
        raise HTTPException(status_code=404, detail="Project not found")


@router.get("/overview")
def get_quality_overview(
    cluster: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Portfolio-wide quality KPIs for the Quality Command Center."""
    result = QualityAnalyticsService.portfolio_overview(db, cluster=cluster).to_dict()
    return _redact_candidates(result)


@router.get("/contractors")
def get_contractor_scorecard(db: Session = Depends(get_db)):
    """Contractor quality scorecard with its legacy list envelope."""
    return QualityAnalyticsService.contractor_scorecard(db).to_dict()["contractors"]


@router.get("/project/{project_name}")
def get_project_quality(project_name: str, db: Session = Depends(get_db)):
    """Per-project quality details for the ProjectWorkspace Quality tab."""
    snapshot = QualityAnalyticsService.project_status(db, project_name)
    _raise_for_resolution(snapshot.resolution_status)

    result = _redact_candidates(snapshot.to_dict())
    # The legacy field echoed the path value; expose the canonical name additively.
    result["resolved_project_name"] = result["project_name"]
    result["project_name"] = project_name
    return result


@router.get("/ncs")
def get_nc_list(
    status: Optional[str] = None,
    category: Optional[str] = None,
    cluster: Optional[str] = None,
    project: Optional[str] = None,
    package: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Paginated NC list with filters."""
    result = QualityAnalyticsService.list_ncs(
        db,
        status=status,
        category=category,
        cluster=cluster,
        project=project,
        package=package,
        page=page,
        page_size=page_size,
    )
    if project and result.warnings and result.warnings[0].source == "project_catalog":
        _raise_for_resolution(
            "ambiguous" if result.warnings[0].reason == "ambiguous_project" else "not_found"
        )
    return _redact_candidates(result.to_dict())


@router.get("/trends")
def get_quality_trends(db: Session = Depends(get_db)):
    """Monthly NC creation and closure trends with the legacy list envelope."""
    return QualityAnalyticsService.portfolio_overview(db).to_dict()["trends"]
