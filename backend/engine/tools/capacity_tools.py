"""Thin tool adapters for canonical capacity milestone facts."""

from sqlalchemy.orm import Session

from services.capacity_milestone_service import CapacityMilestoneService


def capacity_get_portfolio_overview(
    db: Session, portfolio: str | None = None
) -> dict:
    """Return portfolio capacity, COD, trial-run, and milestone facts."""
    return CapacityMilestoneService.get_portfolio_overview(db, portfolio)


def capacity_get_project_status(
    db: Session, project_id_or_name: str, portfolio: str | None = None
) -> dict:
    """Return canonical capacity milestone facts for one project."""
    return CapacityMilestoneService.get_project_status(
        db, project_id_or_name, portfolio
    )
