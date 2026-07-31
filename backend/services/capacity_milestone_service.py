from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
import math
import re
from typing import Iterable

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

import models


WIND_MW_PER_WTG = {
    "3074": 5.2,
    "4707": 5.0,
    "3075": 5.2,
    "3076": 5.2,
    "3072": 5.2,
    "3073": 5.2,
    "6733": 5.2,
    "3105": 3.3,
}
DEFAULT_WIND_MW = 3.3
SOLAR_NOMINAL_BLOCK_MW = 12.5
FORMULA_VERSION = "dashboard-capacity-overview-v1"

_CAPACITY_RE = re.compile(r"(\d+(?:\.\d+)?)[\s_]*MW", re.IGNORECASE)
_BLOCK_RE = re.compile(r"(?<![A-Z0-9])BLOCK[\s_-]*(\d+)(?!\d)", re.IGNORECASE)
_WTG_RE = re.compile(r"(?<![A-Z0-9])WTG[\s_-]*(\d+)(?!\d)", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class MappingFact:
    mapping_id: int
    project_id: str | None
    project_name: str | None
    p6_name: str | None
    cluster: str | None
    category: str | None
    capacity_mwac: float | None


@dataclass(frozen=True, slots=True)
class P6ProjectFact:
    object_id: str
    project_id: str | None
    name: str | None
    data_date: datetime | date | None
    last_synced_at: datetime | date | None


@dataclass(frozen=True, slots=True)
class ActivityFact:
    object_id: int
    project_object_id: str
    name: str | None
    status: str | None
    activity_type: str | None
    wbs_name: str | None
    start_date: datetime | date | None
    planned_finish_date: datetime | date | None
    actual_start_date: datetime | date | None
    actual_finish_date: datetime | date | None
    last_synced_at: datetime | date | None


@dataclass(frozen=True, slots=True)
class SourceSnapshot:
    mappings: tuple[MappingFact, ...]
    projects: tuple[P6ProjectFact, ...]
    activities: tuple[ActivityFact, ...]


@dataclass(frozen=True, slots=True)
class BlockMilestone:
    project_object_id: str
    project_name: str
    block: str
    project_type: str
    capacity: float = 0.0
    has_trial_run: bool = False
    has_cod: bool = False
    trial_run_start: datetime | date | None = None
    trial_run_finish: datetime | date | None = None
    cod_start: datetime | date | None = None
    cod_finish: datetime | date | None = None
    cod_forecast_date: datetime | date | None = None
    latest_date: datetime | date | None = None


@dataclass(frozen=True, slots=True)
class ProjectCapacity:
    mapping: MappingFact
    p6: P6ProjectFact | None
    project_name: str
    project_type: str
    mapped_capacity: float
    name_capacity: float | None
    wind_mw_per_wtg: float | None
    blocks: tuple[BlockMilestone, ...]
    eligible_activity_count: int | None


def _clean(value: object | None) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def financial_year(value: datetime | date | None) -> str | None:
    """Return the dashboard FY label, whose boundary is April 1."""
    if value is None:
        return None
    year = value.year if value.month >= 4 else value.year - 1
    return f"FY{str(year)[-2:]}"


def normalize_block_name(activity_name: str | None) -> str | None:
    """Normalize supported Block/WTG punctuation variants to one identity."""
    text = str(activity_name or "")
    block = _BLOCK_RE.search(text)
    if block:
        return f"BLOCK-{block.group(1)}"
    wtg = _WTG_RE.search(text)
    if wtg:
        return f"WTG{wtg.group(1)}"
    return None


def project_type(cluster: str | None) -> str:
    return "Wind" if "wind" in _clean(cluster) else "Solar"


def capacity_from_name(*names: str | None) -> float | None:
    for name in names:
        match = _CAPACITY_RE.search(str(name or ""))
        if match:
            return float(match.group(1))
    return None


def activity_kind(activity: ActivityFact, capacity_type: str) -> str | None:
    """Apply the Capacity Overview milestone and project-type WBS rules."""
    name = _clean(activity.name)
    is_cod = "cod" in name
    is_trial_run = "trial run certificate" in name or "trail run certificate" in name
    if not (is_cod or is_trial_run):
        return None
    if "milestone" in _clean(activity.activity_type):
        return None
    wbs = _clean(activity.wbs_name)
    if capacity_type == "Wind" and "testing" not in wbs:
        return None
    if capacity_type == "Solar" and "construction" not in wbs:
        return None
    return "cod" if is_cod else "trial_run"


def _activity_date(activity: ActivityFact) -> datetime | date | None:
    return activity.actual_finish_date or activity.actual_start_date or activity.start_date


def _later(
    current: datetime | date | None, candidate: datetime | date | None
) -> datetime | date | None:
    if candidate is None:
        return current
    if current is None or candidate > current:
        return candidate
    return current


def _iso(value: datetime | date | None) -> str | None:
    return value.isoformat() if value else None


def _day_delta(
    finish: datetime | date | None, start: datetime | date | None
) -> int | None:
    return (finish - start).days if finish is not None and start is not None else None


def _source_snapshot(
    db: Session,
    portfolio: str | None = None,
    project_query: str | None = None,
) -> SourceSnapshot:
    """Detach the complete capacity source snapshot from ORM rows in one bulk query."""
    id_match = and_(
        models.ProjectMapping.project_id.isnot(None),
        models.P6Project.project_id.isnot(None),
        func.trim(models.ProjectMapping.project_id) != "",
        func.trim(models.ProjectMapping.project_id) == func.trim(models.P6Project.project_id),
    )
    preferred_mapping_name = func.coalesce(
        models.ProjectMapping.project_name_from_p6, models.ProjectMapping.project
    )
    name_match = and_(
        preferred_mapping_name.isnot(None),
        models.P6Project.name.isnot(None),
        func.lower(func.trim(preferred_mapping_name))
        == func.lower(func.trim(models.P6Project.name)),
    )
    query = (
        db.query(models.ProjectMapping, models.P6Project, models.P6Activity)
        .outerjoin(models.P6Project, or_(id_match, name_match))
        .outerjoin(
            models.P6Activity,
            models.P6Activity.project_object_id == models.P6Project.p6_object_id,
        )
    )
    if portfolio and str(portfolio).casefold() != "all portfolios":
        for token in str(portfolio).replace("+", " ").strip().casefold().split():
            query = query.filter(
                func.lower(models.ProjectMapping.cluster).contains(token)
                | func.lower(models.ProjectMapping.category).contains(token)
                | func.lower(models.ProjectMapping.project).contains(token)
            )
    if project_query:
        normalized = _clean(project_query)
        query = query.filter(or_(
            func.lower(func.trim(models.ProjectMapping.project_id)) == normalized,
            func.lower(func.trim(models.ProjectMapping.project)) == normalized,
            func.lower(func.trim(models.ProjectMapping.project_name_from_p6)) == normalized,
        ))
    rows = query.order_by(
        models.ProjectMapping.id.asc(),
        models.P6Project.id.asc(),
        models.P6Activity.id.asc(),
    ).all()

    mappings: dict[int, MappingFact] = {}
    projects: dict[str, P6ProjectFact] = {}
    activities: dict[int, ActivityFact] = {}
    for mapping, p6, activity in rows:
        preferred_name = mapping.project_name_from_p6 or mapping.project or ""
        if "demo" in preferred_name.casefold():
            continue
        mappings.setdefault(
            mapping.id,
            MappingFact(
                mapping_id=mapping.id,
                project_id=mapping.project_id,
                project_name=mapping.project,
                p6_name=mapping.project_name_from_p6,
                cluster=mapping.cluster,
                category=mapping.category,
                capacity_mwac=float(mapping.capacity_mwac) if mapping.capacity_mwac is not None else None,
            ),
        )
        if p6 is None:
            continue
        object_id = str(p6.p6_object_id)
        projects.setdefault(
            object_id,
            P6ProjectFact(
                object_id=object_id,
                project_id=p6.project_id,
                name=p6.name,
                data_date=p6.data_date,
                last_synced_at=p6.last_synced_at,
            ),
        )
        if activity is not None:
            activities.setdefault(
                activity.id,
                ActivityFact(
                    object_id=activity.id,
                    project_object_id=str(activity.project_object_id),
                    name=activity.name,
                    status=activity.status,
                    activity_type=activity.type,
                    wbs_name=activity.wbs_name,
                    start_date=activity.start_date,
                    planned_finish_date=activity.planned_finish_date,
                    actual_start_date=activity.actual_start_date,
                    actual_finish_date=activity.actual_finish_date,
                    last_synced_at=activity.last_synced_at,
                ),
            )
    return SourceSnapshot(tuple(mappings.values()), tuple(projects.values()), tuple(activities.values()))


def _matching_p6(mapping: MappingFact, projects: Iterable[P6ProjectFact]) -> P6ProjectFact | None:
    candidates = tuple(projects)
    project_id = _clean(mapping.project_id)
    if project_id:
        for p6 in candidates:
            if _clean(p6.project_id) == project_id:
                return p6
    name = _clean(mapping.p6_name or mapping.project_name)
    if name:
        for p6 in candidates:
            if _clean(p6.name) == name:
                return p6
    return None


def _build_project(
    mapping: MappingFact,
    projects: tuple[P6ProjectFact, ...],
    activities: tuple[ActivityFact, ...],
) -> ProjectCapacity:
    p6 = _matching_p6(mapping, projects)
    kind = project_type(mapping.cluster)
    name_capacity = capacity_from_name(mapping.p6_name, mapping.project_name)
    mapped_capacity = float(mapping.capacity_mwac or 0)
    total_capacity = mapped_capacity if mapped_capacity > 0 else float(name_capacity or 0)
    display_name = (p6.name if p6 else None) or mapping.p6_name or mapping.project_name or "Unknown project"
    wind_mw = WIND_MW_PER_WTG.get(p6.object_id, DEFAULT_WIND_MW) if p6 and kind == "Wind" else None

    if p6 is None:
        return ProjectCapacity(
            mapping, None, display_name, kind, total_capacity, name_capacity,
            None, (), None,
        )

    blocks: dict[str, BlockMilestone] = {}
    eligible_count = 0
    for activity in activities:
        if activity.project_object_id != p6.object_id:
            continue
        milestone_kind = activity_kind(activity, kind)
        if milestone_kind is None:
            continue
        eligible_count += 1
        block_name = normalize_block_name(activity.name)
        if block_name is None:
            continue
        actual = _activity_date(activity)
        block = blocks.get(block_name) or BlockMilestone(
            project_object_id=p6.object_id,
            project_name=display_name,
            block=block_name,
            project_type=kind,
            latest_date=actual,
        )
        is_achieved = _clean(activity.status) == "completed" and actual is not None
        if milestone_kind == "cod" and is_achieved:
            start = activity.actual_start_date or actual
            finish = activity.actual_finish_date or actual
            if block.cod_finish is None or (finish is not None and finish >= block.cod_finish):
                block = replace(block, has_cod=True, cod_start=start, cod_finish=finish)
        if milestone_kind == "cod":
            block = replace(
                block,
                cod_forecast_date=block.cod_forecast_date or activity.planned_finish_date,
            )
        elif milestone_kind == "trial_run" and is_achieved:
            start = activity.actual_start_date or actual
            finish = activity.actual_finish_date or actual
            if block.trial_run_finish is None or (finish is not None and finish >= block.trial_run_finish):
                block = replace(
                    block, has_trial_run=True,
                    trial_run_start=start, trial_run_finish=finish,
                )
        blocks[block_name] = replace(block, latest_date=_later(block.latest_date, actual))

    ordered = tuple(sorted(blocks.values(), key=lambda block: block.block))
    if kind == "Solar":
        expected = math.ceil(total_capacity / SOLAR_NOMINAL_BLOCK_MW) if total_capacity > 0 else 0
        capacity = total_capacity / expected if expected else 0
    else:
        capacity = float(wind_mw or DEFAULT_WIND_MW)
    allocated = tuple(replace(block, capacity=capacity) for block in ordered)
    return ProjectCapacity(
        mapping, p6, display_name, kind, total_capacity, name_capacity,
        wind_mw, allocated, eligible_count,
    )


def _project_dict(project: ProjectCapacity) -> dict:
    blocks = project.blocks
    if project.project_type == "Wind" and blocks:
        total_capacity = round(len(blocks) * float(project.wind_mw_per_wtg or DEFAULT_WIND_MW), 2)
        total_blocks = len(blocks)
    elif project.project_type == "Solar":
        total_capacity = project.mapped_capacity
        total_blocks = math.ceil(total_capacity / SOLAR_NOMINAL_BLOCK_MW) if total_capacity > 0 else 0
    else:
        total_capacity = project.mapped_capacity
        total_blocks = 0
    cod = tuple(block for block in blocks if block.has_cod)
    trial_run = tuple(block for block in blocks if not block.has_cod and block.has_trial_run)
    cod_mw = sum(block.capacity for block in cod)
    trial_run_mw = sum(block.capacity for block in trial_run)
    warnings = []
    if project.p6 is None:
        warnings.append("No matching P6 project; milestone source facts are unavailable.")
    return {
        "project_id": project.mapping.project_id or "-",
        "project_name": project.project_name,
        "type": project.project_type,
        "total_capacity": total_capacity,
        "total_blocks": total_blocks,
        "tr_blocks": len(trial_run),
        "tr_mw": trial_run_mw,
        "cod_blocks": len(cod),
        "cod_mw": cod_mw,
        "remaining_capacity": max(0, round(total_capacity - cod_mw - trial_run_mw, 2)),
        "remaining_blocks": total_blocks - len(cod) - len(trial_run),
        "blocks": [
            {
                "block": block.block,
                "capacity": block.capacity,
                "cod_status": "Completed" if block.has_cod else "Not Started",
                "trial_run_status": "Completed" if block.has_trial_run else "Not Started",
                "cod_forecast_date": _iso(block.cod_forecast_date),
                "cod_actual_date": _iso(block.cod_finish or block.cod_start),
                "trial_run_actual_date": _iso(block.trial_run_finish or block.trial_run_start),
            }
            for block in blocks
        ],
        "p6_available": project.p6 is not None,
        "source_facts": {
            "mapping_id": project.mapping.mapping_id,
            "mapped_capacity_mwac": project.mapping.capacity_mwac,
            "name_capacity_fallback_mw": project.name_capacity,
            "p6_object_id": project.p6.object_id if project.p6 else None,
            "wind_mw_per_wtg": project.wind_mw_per_wtg,
            "eligible_activity_count": project.eligible_activity_count,
            "parsed_block_count": len(blocks) if project.p6 else None,
        },
        "freshness": {
            "data_as_of": _iso(project.p6.data_date) if project.p6 else None,
            "last_synced_at": _iso(project.p6.last_synced_at) if project.p6 else None,
        },
        "warnings": warnings,
    }


def _calculate(snapshot: SourceSnapshot, project_query: str | None = None) -> dict:
    mappings = snapshot.mappings
    if project_query:
        query = _clean(project_query)
        mappings = tuple(
            mapping for mapping in mappings
            if query in {
                _clean(mapping.project_id), _clean(mapping.project_name), _clean(mapping.p6_name)
            }
        )
    projects = tuple(
        _build_project(mapping, snapshot.projects, snapshot.activities) for mapping in mappings
    )
    project_rows = [_project_dict(project) for project in projects]

    fy_data: dict[str, dict] = {}
    recent: list[dict] = []
    monthly: dict[str, dict[str, float]] = {}
    for project in projects:
        for block in project.blocks:
            if block.has_cod:
                selected_kind = "cod"
                selected_date = block.cod_finish or block.cod_start
            elif block.has_trial_run:
                selected_kind = "tr"
                selected_date = block.trial_run_finish or block.trial_run_start
            else:
                selected_kind = None
                selected_date = None
            fy = financial_year(selected_date)
            if fy and selected_kind:
                row = fy_data.setdefault(
                    fy,
                    {"name": fy, "solar_cod": 0, "solar_tr": 0, "wind_cod": 0, "wind_tr": 0},
                )
                row[f"{project.project_type.casefold()}_{selected_kind}"] += block.capacity

            if block.has_trial_run:
                value = block.trial_run_finish or block.trial_run_start
                if value:
                    month = value.strftime("%Y-%m")
                    month_row = monthly.setdefault(month, _empty_month())
                    month_row[f"{project.project_type} Trial Run"] += block.capacity
            if block.has_cod:
                value = block.cod_finish or block.cod_start
                if value:
                    month = value.strftime("%Y-%m")
                    month_row = monthly.setdefault(month, _empty_month())
                    month_row[f"{project.project_type} COD"] += block.capacity

            recent.append({
                "project": block.project_name,
                "block": block.block,
                "type": block.project_type,
                "capacity": block.capacity,
                "status": "COD" if block.has_cod else "Trial Run" if block.has_trial_run else "Pending",
                "tr_start": block.trial_run_start.strftime("%Y-%m-%d") if block.trial_run_start else None,
                "tr_finish": block.trial_run_finish.strftime("%Y-%m-%d") if block.trial_run_finish else None,
                "cod_start": block.cod_start.strftime("%Y-%m-%d") if block.cod_start else None,
                "cod_finish": block.cod_finish.strftime("%Y-%m-%d") if block.cod_finish else None,
                "tr_duration": _day_delta(block.trial_run_finish, block.trial_run_start),
                "cod_duration": _day_delta(block.cod_finish, block.cod_start),
                "gap_days": _day_delta(block.cod_start, block.trial_run_finish),
                "_latest_date": block.latest_date,
            })

    financial_years = sorted(fy_data.values(), key=lambda row: row["name"])
    cumulative = _empty_month()
    monthly_trends = []
    for month in sorted(monthly):
        for key, value in monthly[month].items():
            cumulative[key] += value
        monthly_trends.append({"name": month, **{key: round(value, 2) for key, value in cumulative.items()}})
    recent.sort(key=lambda row: _iso(row["_latest_date"]) or "", reverse=True)
    for row in recent:
        del row["_latest_date"]

    totals = {
        "solar_cod": sum(row["solar_cod"] for row in financial_years),
        "solar_tr": sum(row["solar_tr"] for row in financial_years),
        "wind_cod": sum(row["wind_cod"] for row in financial_years),
        "wind_tr": sum(row["wind_tr"] for row in financial_years),
    }
    project_rows.sort(key=lambda row: row["total_capacity"], reverse=True)
    sync_values = [
        value for value in (
            *(project.last_synced_at for project in snapshot.projects),
            *(activity.last_synced_at for activity in snapshot.activities),
        ) if value is not None
    ]
    data_dates = [project.data_date for project in snapshot.projects if project.data_date is not None]
    missing = sum(project.p6 is None for project in projects)
    warnings = []
    if missing:
        warnings.append(f"{missing} mapped project(s) have no matching P6 project.")
    return {
        "financial_years": financial_years,
        "monthly_trends": monthly_trends,
        "recent_milestones": recent[:50],
        "totals": totals,
        "projects": project_rows,
        "metadata": {
            "formula": {
                "version": FORMULA_VERSION,
                "capacity_units": "MW",
                "solar_allocation": "capacity / ceil(capacity / 12.5)",
                "wind_allocation": "parsed WTG count * project MW per WTG",
                "current_totals_precedence": "COD over Trial Run per block",
                "monthly_trends": "independent cumulative COD and Trial Run events",
                "financial_year_boundary": "April 1",
            },
            "evidence": {
                "mapping_count": len(mappings),
                "p6_project_count": sum(project.p6 is not None for project in projects),
                "eligible_activity_count": sum(project.eligible_activity_count or 0 for project in projects),
                "parsed_block_count": sum(len(project.blocks) for project in projects),
            },
            "freshness": {
                "data_as_of": _iso(max(data_dates)) if data_dates else None,
                "last_synced_at": _iso(max(sync_values)) if sync_values else None,
            },
            "warnings": warnings,
        },
    }


def _empty_month() -> dict[str, float]:
    return {
        "Solar COD": 0,
        "Solar Trial Run": 0,
        "Wind COD": 0,
        "Wind Trial Run": 0,
    }


class CapacityMilestoneService:
    """Canonical capacity overview calculations with detached source facts."""

    @staticmethod
    def get_portfolio_overview(db: Session, portfolio: str | None = None) -> dict:
        return _calculate(_source_snapshot(db, portfolio))

    @staticmethod
    def get_project_status(
        db: Session,
        project_id_or_name: str,
        portfolio: str | None = None,
    ) -> dict:
        return _calculate(
            _source_snapshot(db, portfolio, project_id_or_name),
            project_id_or_name,
        )


def get_capacity_overview(db: Session, portfolio: str | None = None) -> dict:
    return CapacityMilestoneService.get_portfolio_overview(db, portfolio)


def get_project_capacity_status(
    db: Session, project_id_or_name: str, portfolio: str | None = None
) -> dict:
    return CapacityMilestoneService.get_project_status(db, project_id_or_name, portfolio)


get_portfolio_capacity_overview = get_capacity_overview
