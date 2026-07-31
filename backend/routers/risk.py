from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from services.risk_analytics_service import RiskAnalyticsService


router = APIRouter(prefix="/api/risk", tags=["Risk Analytics"])


def _envelope(metrics):
    return {"metrics": {metric.metric_id: metric.to_dict() for metric in metrics}}


@router.get("/command-center")
def get_command_center(
    portfolio: str | None = None,
    project_id: str | None = None,
    db: Session = Depends(get_db),
):
    return _envelope(RiskAnalyticsService.command_center(db, portfolio, project_id))


@router.get("/predictive")
def get_predictive(
    portfolio: str | None = None,
    project_id: str | None = None,
    db: Session = Depends(get_db),
):
    return _envelope((RiskAnalyticsService.predictive(db, portfolio, project_id),))


@router.get("/project/{project_id}")
def get_project_risk(
    project_id: str,
    metric_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    metrics = RiskAnalyticsService.project360(db, project_id)
    if metric_id:
        metrics = tuple(metric for metric in metrics if metric.metric_id == metric_id)
        if not metrics:
            raise HTTPException(status_code=404, detail=f"Unknown project risk metric_id: {metric_id}")
    return _envelope(metrics)
