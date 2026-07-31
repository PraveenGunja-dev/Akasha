"""Thin, unregistered adapters for named risk analytics metrics."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from services.risk_analytics_service import (
    COMMAND_CENTER_FINANCIAL_COUNT,
    COMMAND_CENTER_HEATMAP,
    COMMAND_CENTER_OVERALL_SCORE,
    COMMAND_CENTER_SCHEDULE_COUNT,
    KPI_PROJECT_EXPOSURE,
    PMAG_SCHEDULE_RAG,
    PREDICTIVE_PORTFOLIO_SLIPPAGE,
    PROJECT360_COD_RISK,
    PROJECT360_RISK_FLAGS,
    PROJECT360_STATUS_TIER,
    PROJECT360_STATUS_TIER_COUNTS,
    RiskAnalyticsService,
)
from services.schedule_metrics_service import ScheduleMetricsService


def risk_get_metric(
    db: Session,
    metric_id: str,
    *,
    project_id: str | None = None,
    portfolio: str | None = None,
) -> dict[str, Any]:
    """Return exactly one named metric; callers must choose its metric_id."""
    if not metric_id:
        raise ValueError("metric_id is required")

    if metric_id == PMAG_SCHEDULE_RAG:
        if not project_id:
            raise ValueError("project_id is required for PMAG schedule RAG")
        schedule = ScheduleMetricsService.get_by_project_id(db, project_id)
        return RiskAnalyticsService.pmag_schedule_rag(
            schedule.finish_date_variance,
            scope=project_id,
        ).to_dict()

    if metric_id in {
        COMMAND_CENTER_SCHEDULE_COUNT,
        COMMAND_CENTER_FINANCIAL_COUNT,
        COMMAND_CENTER_OVERALL_SCORE,
        COMMAND_CENTER_HEATMAP,
    }:
        metrics = {
            metric.metric_id: metric
            for metric in RiskAnalyticsService.command_center(db, portfolio, project_id)
        }
        return metrics[metric_id].to_dict()

    if metric_id in {PROJECT360_RISK_FLAGS, PROJECT360_COD_RISK, PROJECT360_STATUS_TIER}:
        if not project_id:
            raise ValueError("project_id is required for Project360 risk metrics")
        metrics = {metric.metric_id: metric for metric in RiskAnalyticsService.project360(db, project_id)}
        return metrics[metric_id].to_dict()

    if metric_id == PROJECT360_STATUS_TIER_COUNTS:
        from services.project_service import calculate_project_360_metrics

        projects = calculate_project_360_metrics(db, portfolio)
        return RiskAnalyticsService.project360_status_tier_counts(projects).to_dict()

    if metric_id == PREDICTIVE_PORTFOLIO_SLIPPAGE:
        return RiskAnalyticsService.predictive(db, portfolio, project_id).to_dict()

    if metric_id == KPI_PROJECT_EXPOSURE:
        if not project_id:
            raise ValueError("project_id is required for KPI project exposure")
        return RiskAnalyticsService.kpi_project_exposure(db, project_id).to_dict()

    raise ValueError(f"Unknown risk metric_id: {metric_id}")


def risk_get_command_center(db: Session) -> list[dict[str, Any]]:
    """Convenience bundle; each result retains its independent metric identity."""
    return [metric.to_dict() for metric in RiskAnalyticsService.command_center(db)]


def risk_get_project360(db: Session, project_id: str) -> list[dict[str, Any]]:
    """Convenience bundle for the three existing Project360 formulas."""
    if not project_id:
        raise ValueError("project_id is required")
    return [metric.to_dict() for metric in RiskAnalyticsService.project360(db, project_id)]
