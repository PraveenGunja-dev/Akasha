from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from routers import dashboard


DASHBOARD_TABLES = [
    models.ProjectMapping.__table__,
    models.P6Project.__table__,
    models.P6Activity.__table__,
    models.MTInventory.__table__,
    models.MTRequirement.__table__,
    models.MTPOAmount.__table__,
    models.MTMaterialDocument.__table__,
    models.TcProjectEntry.__table__,
    models.TcNetworkEdge.__table__,
    models.PulseNC.__table__,
    models.PulseRFI.__table__,
    models.SourceSyncState.__table__,
]

CATALOG_BASELINE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "dashboard_alignment"
    / "catalog_baseline.v1.json"
)


def load_catalog_baseline() -> dict:
    return json.loads(CATALOG_BASELINE_PATH.read_text(encoding="utf-8"))


def create_dashboard_session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.Base.metadata.create_all(engine, tables=DASHBOARD_TABLES)
    return engine, sessionmaker(bind=engine, autoflush=False, autocommit=False)


def clear_dashboard_tables(db) -> None:
    for table in reversed(DASHBOARD_TABLES):
        db.execute(table.delete())
    db.commit()


def mapping(
    *,
    mapping_id: int,
    project_id: str | None,
    name: str,
    cluster: str,
    category: str,
    capacity: float = 100.0,
    p6_name: str | None = None,
    spv_name: str | None = None,
):
    return models.ProjectMapping(
        id=mapping_id,
        project_id=project_id,
        project=name,
        project_name_from_p6=p6_name if p6_name is not None else name,
        cluster=cluster,
        category=category,
        capacity_mwac=capacity,
        spv_name=spv_name or f"SPV-{mapping_id}",
        spv_plant_code=f"PLANT-{mapping_id}",
        module_wbs=f"WBS-{mapping_id}",
    )


def p6_project(*, object_id: int, project_id: str, name: str, progress: float = 0.25):
    return models.P6Project(
        p6_object_id=object_id,
        project_id=project_id,
        name=name,
        status="Active",
        duration_percent_complete=progress,
        last_synced_at=datetime(2026, 7, 15, 12),
    )


def seed_catalog_scenario(db) -> None:
    baseline = load_catalog_baseline()
    db.add_all(mapping(**row) for row in baseline["mappings"])
    db.add_all(p6_project(**row) for row in baseline["p6_projects"])
    db.commit()


def dashboard_summary(db, portfolio: str | None = None):
    empty_capacity = {
        "totals": {},
        "projects": [],
        "financial_years": [],
        "monthly_trends": [],
        "recent_milestones": [],
    }
    dashboard.clear_dashboard_caches()
    with patch("routers.dashboard.get_capacity_overview", return_value=empty_capacity):
        result = dashboard.get_dashboard_summary(
            portfolio=portfolio,
            nocache=True,
            db=db,
        )
    dashboard.clear_dashboard_caches()
    return result
