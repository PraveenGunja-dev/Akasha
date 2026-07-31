"""Canonical quality analytics, project association, and immutable DTOs."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Mapping

from sqlalchemy.orm import Session

import models
from services.project_catalog_service import CatalogProject, ProjectCatalogService


QUALITY_FORMULA_VERSIONS = (
    ("overview", "dashboard-quality-overview-v1"),
    ("project_score", "dashboard-quality-project-score-v1"),
    ("contractor_score", "dashboard-quality-contractor-score-v1"),
    ("aging", "dashboard-quality-aging-v1"),
    ("trend", "dashboard-quality-trend-v1"),
)
SOURCE_TABLES = ("pulse_nc", "pulse_rfi")


def _key(value: object | None) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def _status(value: object | None) -> str:
    return _key(value) or "unknown"


def _category(value: object | None) -> str:
    normalized = _key(value).replace("-", " ").replace("_", " ")
    return " ".join(part.capitalize() for part in normalized.split()) or "Unknown"


def _label(value: object | None, fallback: str = "Unknown") -> str:
    return " ".join(str(value or "").strip().split()) or fallback


def _is_completed(row: object) -> bool:
    return _status(getattr(row, "status", None)) == "completed"


def _is_critical(row: object) -> bool:
    return _category(getattr(row, "category", None)).casefold() == "critical"


def _iso(value: object | None) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else None


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _now(value: datetime | None) -> datetime:
    return _naive_utc(value or datetime.now(timezone.utc))


def _age_days(created_at: datetime | None, now: datetime) -> int:
    if not created_at:
        return 0
    return max(0, (_naive_utc(now) - _naive_utc(created_at)).days)


def _elapsed_days(start: datetime, end: datetime) -> float:
    return (_naive_utc(end) - _naive_utc(start)).total_seconds() / 86400


def _pairs(values: Mapping[str, int]) -> tuple[tuple[str, int], ...]:
    return tuple(values.items())


def _pair_dict(values: tuple[tuple[str, object], ...]) -> dict:
    return dict(values)


@dataclass(frozen=True, slots=True)
class MatchWarning:
    source: str
    source_id: str
    reason: str
    candidates: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class QualityNC:
    id: str
    nc_label: str | None
    status: str
    status_label: str | None
    category: str
    defect_type: str | None
    description: str | None
    current_handler: str | None
    contractor_name: str | None
    vendor_name: str | None
    engineer_name: str | None
    quality_name: str | None
    project_name: str | None
    cluster_name: str | None
    worklocation_name: str | None
    workarea_name: str | None
    package_name: str | None
    subactivity_name: str | None
    debit: float | None
    debit_reason: str | None
    age_days: int
    created_at: str | None
    approved_at: str | None


@dataclass(frozen=True, slots=True)
class QualityProvenance:
    source_tables: tuple[str, ...] = SOURCE_TABLES
    nc_source_ids: tuple[str, ...] = ()
    rfi_source_ids: tuple[str, ...] = ()
    nc_last_synced_at: str | None = None
    rfi_last_synced_at: str | None = None
    data_as_of: str | None = None
    formula_versions: tuple[tuple[str, str], ...] = QUALITY_FORMULA_VERSIONS


@dataclass(frozen=True, slots=True)
class QualityOverview:
    available: bool
    nc_available: bool
    rfi_available: bool
    total_ncs: int
    open_ncs: int
    completed_ncs: int
    critical_open: int
    closure_rate: float
    avg_resolution_days: float
    total_debit: float
    debit_count: int
    total_rfis: int
    open_rfis: int
    rfis_completed: int
    by_status: tuple[tuple[str, int], ...] = ()
    by_category: tuple[tuple[str, int], ...] = ()
    by_cluster: tuple[tuple[str, int], ...] = ()
    by_handler: tuple[tuple[str, int], ...] = ()
    by_package: tuple[tuple[str, int], ...] = ()
    aging: tuple[tuple[str, int], ...] = ()
    trend: tuple[tuple[str, int], ...] = ()
    trends: tuple[tuple[str, int, int], ...] = ()
    top_defects: tuple[tuple[str, int], ...] = ()
    warnings: tuple[MatchWarning, ...] = ()
    provenance: QualityProvenance = field(default_factory=QualityProvenance)

    def to_dict(self) -> dict:
        result = asdict(self)
        for name in ("by_status", "by_category", "by_cluster", "by_handler", "by_package", "aging"):
            result[name] = _pair_dict(getattr(self, name))
        result["trend"] = [{"month": month, "count": count} for month, count in self.trend]
        result["trends"] = [
            {"month": month, "created": created, "closed": closed}
            for month, created, closed in self.trends
        ]
        result["top_defects"] = [{"type": name, "count": count} for name, count in self.top_defects]
        result["warnings"] = [asdict(warning) for warning in self.warnings]
        result["provenance"]["formula_versions"] = _pair_dict(self.provenance.formula_versions)
        result["availability"] = {
            "quality": self.available,
            "ncs": self.nc_available,
            "rfis": self.rfi_available,
        }
        result["_sources_used"] = list(self.provenance.source_tables)
        return result


@dataclass(frozen=True, slots=True)
class ProjectQualitySnapshot:
    resolution_status: str
    query: str
    project_id: str | None
    project_name: str | None
    match_kind: str | None
    available: bool
    nc_available: bool
    rfi_available: bool
    total_ncs: int
    open_ncs: int
    completed_ncs: int
    critical_open: int
    total_rfis: int
    open_rfis: int
    rfis_completed: int
    quality_score: int | None
    closure_rate: float | None
    by_status: tuple[tuple[str, int], ...] = ()
    by_handler: tuple[tuple[str, int], ...] = ()
    blocks: tuple[tuple[str, int, int, int], ...] = ()
    ncs: tuple[QualityNC, ...] = ()
    warnings: tuple[MatchWarning, ...] = ()
    candidates: tuple[tuple[str | None, str], ...] = ()
    provenance: QualityProvenance = field(default_factory=QualityProvenance)

    def to_dict(self) -> dict:
        result = asdict(self)
        result["by_status"] = _pair_dict(self.by_status)
        result["by_handler"] = _pair_dict(self.by_handler)
        result["blocks"] = [
            {"name": name, "total": total, "critical_open": critical, "open": opened}
            for name, total, critical, opened in self.blocks
        ]
        result["ncs"] = [asdict(nc) for nc in self.ncs]
        result["warnings"] = [asdict(warning) for warning in self.warnings]
        result["candidates"] = [
            {"project_id": project_id, "project_name": name}
            for project_id, name in self.candidates
        ]
        result["provenance"]["formula_versions"] = _pair_dict(self.provenance.formula_versions)
        result["availability"] = {
            "quality": self.available,
            "ncs": self.nc_available,
            "rfis": self.rfi_available,
        }
        result["_sources_used"] = list(self.provenance.source_tables)
        return result


@dataclass(frozen=True, slots=True)
class ContractorScore:
    name: str
    code: str | None
    total_ncs: int
    critical: int
    open: int
    rejected: int
    completed: int
    closure_rate: float
    debit_total: float
    debit_count: int
    avg_resolution_days: float | None
    quality_score: int


@dataclass(frozen=True, slots=True)
class ContractorScorecard:
    available: bool
    contractors: tuple[ContractorScore, ...]
    warnings: tuple[MatchWarning, ...] = ()
    provenance: QualityProvenance = field(default_factory=QualityProvenance)

    def to_dict(self) -> dict:
        return {
            "available": self.available,
            "contractors": [asdict(contractor) for contractor in self.contractors],
            "warnings": [asdict(warning) for warning in self.warnings],
            "provenance": {
                **asdict(self.provenance),
                "formula_versions": _pair_dict(self.provenance.formula_versions),
            },
            "_sources_used": list(self.provenance.source_tables),
        }


@dataclass(frozen=True, slots=True)
class QualityNCPage:
    available: bool
    items: tuple[QualityNC, ...]
    total: int
    page: int
    page_size: int
    warnings: tuple[MatchWarning, ...] = ()
    provenance: QualityProvenance = field(default_factory=QualityProvenance)

    def to_dict(self) -> dict:
        return {
            "available": self.available,
            "items": [asdict(item) for item in self.items],
            "total": self.total,
            "page": self.page,
            "page_size": self.page_size,
            "warnings": [asdict(warning) for warning in self.warnings],
            "provenance": {
                **asdict(self.provenance),
                "formula_versions": _pair_dict(self.provenance.formula_versions),
            },
            "_sources_used": ["pulse_nc"],
        }


class _ProjectMatcher:
    def __init__(self, projects: Iterable[CatalogProject], p6_names: Mapping[str, tuple[str, ...]]):
        projects = tuple(projects)
        unique: dict[str, CatalogProject] = {}
        for project in projects:
            identity = project.project_id or f"mapping:{project.mapping_id}"
            current = unique.get(identity)
            if current is None or project.mapping_id < current.mapping_id:
                unique[identity] = project
        self.projects = tuple(sorted(unique.values(), key=lambda p: (_key(p.display_name), p.mapping_id)))
        self.aliases: dict[str, tuple[str, ...]] = {}
        for project in self.projects:
            identity = self.identity(project)
            equivalent = [candidate for candidate in projects if self.identity(candidate) == identity]
            values = []
            for candidate in equivalent:
                values.extend((
                    candidate.project_id,
                    candidate.project_name,
                    candidate.p6_mapping_name,
                    candidate.spv_name,
                ))
            values.extend(p6_names.get(project.project_id or "", ()))
            self.aliases[identity] = tuple(dict.fromkeys(_key(value) for value in values if _key(value)))

    @staticmethod
    def identity(project: CatalogProject) -> str:
        return project.project_id or f"mapping:{project.mapping_id}"

    def partial_candidates(self, value: str) -> tuple[CatalogProject, ...]:
        normalized = _key(value)
        if len(normalized) < 4:
            return ()
        matches = []
        for project in self.projects:
            aliases = self.aliases[self.identity(project)]
            if any(normalized in alias or alias in normalized for alias in aliases if len(alias) >= 4):
                matches.append(project)
        return tuple(matches)

    def match_row(self, row: object) -> tuple[CatalogProject | None, tuple[CatalogProject, ...]]:
        values = (
            getattr(row, "project_id", None),
            getattr(row, "project_name", None),
            getattr(row, "spv_name", None),
        )
        for value in values:
            normalized = _key(value)
            if not normalized:
                continue
            exact = tuple(
                project for project in self.projects
                if normalized in self.aliases[self.identity(project)]
            )
            if len(exact) == 1:
                return exact[0], ()
            if len(exact) > 1:
                return None, exact

        partial: dict[str, CatalogProject] = {}
        for value in values:
            for project in self.partial_candidates(str(value or "")):
                partial[self.identity(project)] = project
        candidates = tuple(sorted(partial.values(), key=lambda p: (_key(p.display_name), p.mapping_id)))
        return (candidates[0], ()) if len(candidates) == 1 else (None, candidates)


class QualityAnalyticsService:
    """Canonical Pulse quality calculations and deterministic catalog association."""

    @staticmethod
    def _load_context(db: Session, portfolio: str | None = None):
        projects = ProjectCatalogService.list_projects(db, portfolio)
        ids = {project.project_id for project in projects if project.project_id}
        p6_names: dict[str, list[str]] = {}
        if ids:
            rows = db.query(models.P6Project.project_id, models.P6Project.name).filter(
                models.P6Project.project_id.in_(ids)
            ).all()
            for project_id, name in rows:
                if project_id and name:
                    p6_names.setdefault(project_id, []).append(name)
        matcher = _ProjectMatcher(projects, {key: tuple(value) for key, value in p6_names.items()})
        return projects, matcher

    @staticmethod
    def _provenance(ncs: Iterable[object], rfis: Iterable[object]) -> QualityProvenance:
        ncs = tuple(ncs)
        rfis = tuple(rfis)
        nc_sync = max((row.last_synced_at for row in ncs if row.last_synced_at), default=None)
        rfi_sync = max((row.last_synced_at for row in rfis if row.last_synced_at), default=None)
        available_sync = [value for value in (nc_sync, rfi_sync) if value]
        data_as_of = min(available_sync) if available_sync else None
        return QualityProvenance(
            nc_source_ids=tuple(str(row.pulse_id) for row in ncs),
            rfi_source_ids=tuple(str(row.pulse_id) for row in rfis),
            nc_last_synced_at=_iso(nc_sync),
            rfi_last_synced_at=_iso(rfi_sync),
            data_as_of=_iso(data_as_of),
        )

    @staticmethod
    def _warning(source: str, row: object, candidates: Iterable[CatalogProject]) -> MatchWarning:
        candidate_ids = tuple(project.project_id or project.display_name for project in candidates)
        return MatchWarning(
            source=source,
            source_id=str(getattr(row, "pulse_id", "")),
            reason="ambiguous_project" if candidate_ids else "unmatched_project",
            candidates=candidate_ids,
        )

    @classmethod
    def _scope_rows(cls, rows, matcher: _ProjectMatcher, source: str, *, require_match: bool):
        selected = []
        warnings = []
        assigned: dict[str, list] = {matcher.identity(project): [] for project in matcher.projects}
        for row in rows:
            project, candidates = matcher.match_row(row)
            if project:
                assigned[matcher.identity(project)].append(row)
                selected.append(row)
            else:
                warnings.append(cls._warning(source, row, candidates))
                if not require_match:
                    selected.append(row)
        return selected, assigned, warnings

    @classmethod
    def portfolio_overview(
        cls,
        db: Session,
        portfolio: str | None = None,
        *,
        cluster: str | None = None,
        now: datetime | None = None,
    ) -> QualityOverview:
        all_ncs = db.query(models.PulseNC).order_by(models.PulseNC.id.asc()).all()
        all_rfis = db.query(models.PulseRFI).order_by(models.PulseRFI.id.asc()).all()
        if cluster:
            all_ncs = [row for row in all_ncs if _key(row.cluster_name) == _key(cluster)]
            all_rfis = [row for row in all_rfis if _key(row.cluster_name) == _key(cluster)]
        _, matcher = cls._load_context(db, portfolio)
        scoped = bool(portfolio and _key(portfolio) != "all portfolios")
        ncs, _, nc_warnings = cls._scope_rows(all_ncs, matcher, "pulse_nc", require_match=scoped)
        rfis, _, rfi_warnings = cls._scope_rows(all_rfis, matcher, "pulse_rfi", require_match=scoped)
        return cls._overview(ncs, rfis, now=_now(now), warnings=(*nc_warnings, *rfi_warnings))

    @classmethod
    def _overview(cls, ncs, rfis, *, now: datetime, warnings=()) -> QualityOverview:
        by_status: dict[str, int] = {}
        by_category: dict[str, int] = {}
        by_cluster: dict[str, int] = {}
        by_handler: dict[str, int] = {}
        by_package: dict[str, int] = {}
        aging = {"0-3": 0, "3-7": 0, "7-14": 0, "14-30": 0, "30+": 0}
        created: dict[str, int] = {}
        closed: dict[str, int] = {}
        defects: dict[str, int] = {}
        resolution_days = []
        debit_rows = []

        for nc in ncs:
            status = _status(nc.status)
            category = _category(nc.category)
            by_status[status] = by_status.get(status, 0) + 1
            by_category[category] = by_category.get(category, 0) + 1
            cluster = _label(nc.cluster_name)
            package = _label(nc.package_name)
            by_cluster[cluster] = by_cluster.get(cluster, 0) + 1
            by_package[package] = by_package.get(package, 0) + 1
            if not _is_completed(nc):
                handler = _key(nc.current_handler) or "unknown"
                by_handler[handler] = by_handler.get(handler, 0) + 1
                days = _age_days(nc.created_at, now)
                if nc.created_at:
                    bucket = "0-3" if days <= 3 else "3-7" if days <= 7 else "7-14" if days <= 14 else "14-30" if days <= 30 else "30+"
                    aging[bucket] += 1
            if nc.created_at:
                month = nc.created_at.strftime("%Y-%m")
                created[month] = created.get(month, 0) + 1
            if _is_completed(nc) and nc.approved_at:
                month = nc.approved_at.strftime("%Y-%m")
                closed[month] = closed.get(month, 0) + 1
                if nc.created_at:
                    delta = _elapsed_days(nc.created_at, nc.approved_at)
                    if delta >= 0:
                        resolution_days.append(delta)
            if nc.debit is not None and nc.debit > 0:
                debit_rows.append(nc)
            if nc.defect_type:
                defect = _label(nc.defect_type)
                defects[defect] = defects.get(defect, 0) + 1

        total = len(ncs)
        completed = sum(_is_completed(row) for row in ncs)
        rfi_completed = sum(_is_completed(row) for row in rfis)
        months = sorted(set(created) | set(closed))
        top_defects = tuple(sorted(defects.items(), key=lambda item: (-item[1], _key(item[0])))[:10])
        return QualityOverview(
            available=bool(ncs or rfis),
            nc_available=bool(ncs),
            rfi_available=bool(rfis),
            total_ncs=total,
            open_ncs=total - completed,
            completed_ncs=completed,
            critical_open=sum(_is_critical(row) and not _is_completed(row) for row in ncs),
            closure_rate=round(completed / total * 100, 1) if total else 0,
            avg_resolution_days=round(sum(resolution_days) / len(resolution_days), 1) if resolution_days else 0,
            total_debit=sum(float(row.debit) for row in debit_rows),
            debit_count=len(debit_rows),
            total_rfis=len(rfis),
            open_rfis=len(rfis) - rfi_completed,
            rfis_completed=rfi_completed,
            by_status=_pairs(by_status),
            by_category=_pairs(by_category),
            by_cluster=_pairs(by_cluster),
            by_handler=_pairs(by_handler),
            by_package=_pairs(by_package),
            aging=_pairs(aging),
            trend=tuple((month, created[month]) for month in sorted(created)),
            trends=tuple((month, created.get(month, 0), closed.get(month, 0)) for month in months),
            top_defects=top_defects,
            warnings=tuple(warnings),
            provenance=cls._provenance(ncs, rfis),
        )

    @classmethod
    def project_snapshots(
        cls, db: Session, portfolio: str | None = None, *, now: datetime | None = None
    ) -> tuple[ProjectQualitySnapshot, ...]:
        projects, matcher = cls._load_context(db, portfolio)
        ncs = db.query(models.PulseNC).order_by(models.PulseNC.id.asc()).all()
        rfis = db.query(models.PulseRFI).order_by(models.PulseRFI.id.asc()).all()
        _, nc_assigned, nc_warnings = cls._scope_rows(ncs, matcher, "pulse_nc", require_match=True)
        _, rfi_assigned, rfi_warnings = cls._scope_rows(rfis, matcher, "pulse_rfi", require_match=True)
        warnings = tuple((*nc_warnings, *rfi_warnings))
        unique: dict[str, CatalogProject] = {}
        for project in projects:
            unique.setdefault(matcher.identity(project), project)
        return tuple(
            cls._project_snapshot(
                project,
                nc_assigned.get(identity, ()),
                rfi_assigned.get(identity, ()),
                now=_now(now),
                warnings=warnings,
                query=project.project_id or project.display_name,
                match_kind="portfolio",
            )
            for identity, project in sorted(unique.items(), key=lambda item: (_key(item[1].display_name), item[1].mapping_id))
        )

    @classmethod
    def project_status(
        cls,
        db: Session,
        project: str,
        portfolio: str | None = None,
        *,
        now: datetime | None = None,
    ) -> ProjectQualitySnapshot:
        resolution = ProjectCatalogService.resolve(db, project, portfolio=portfolio)
        projects, matcher = cls._load_context(db, portfolio)
        candidates = resolution.candidates
        if resolution.status == "resolved" and resolution.match_kind == "fuzzy":
            partial = matcher.partial_candidates(project)
            if len(partial) > 1:
                resolution_status = "ambiguous"
                resolved = None
                candidates = partial
            else:
                resolution_status = resolution.status
                resolved = resolution.project
        else:
            resolution_status = resolution.status
            resolved = resolution.project

        if resolution_status != "resolved" or resolved is None:
            warning = MatchWarning(
                source="project_catalog",
                source_id=str(project),
                reason="ambiguous_project" if resolution_status == "ambiguous" else "unmatched_project",
                candidates=tuple(candidate.project_id or candidate.display_name for candidate in candidates),
            )
            return ProjectQualitySnapshot(
                resolution_status=resolution_status,
                query=str(project),
                project_id=None,
                project_name=None,
                match_kind=resolution.match_kind,
                available=False,
                nc_available=False,
                rfi_available=False,
                total_ncs=0,
                open_ncs=0,
                completed_ncs=0,
                critical_open=0,
                total_rfis=0,
                open_rfis=0,
                rfis_completed=0,
                quality_score=None,
                closure_rate=None,
                warnings=(warning,),
                candidates=tuple((candidate.project_id, candidate.display_name) for candidate in candidates),
            )

        all_ncs = db.query(models.PulseNC).order_by(models.PulseNC.id.asc()).all()
        all_rfis = db.query(models.PulseRFI).order_by(models.PulseRFI.id.asc()).all()
        _, nc_assigned, _ = cls._scope_rows(all_ncs, matcher, "pulse_nc", require_match=True)
        _, rfi_assigned, _ = cls._scope_rows(all_rfis, matcher, "pulse_rfi", require_match=True)
        identity = matcher.identity(resolved)
        return cls._project_snapshot(
            resolved,
            nc_assigned.get(identity, ()),
            rfi_assigned.get(identity, ()),
            now=_now(now),
            # Project-scoped responses must not disclose unrelated catalog candidates.
            warnings=(),
            query=str(project),
            match_kind=resolution.match_kind,
        )

    @classmethod
    def _project_snapshot(cls, project, ncs, rfis, *, now, warnings, query, match_kind):
        by_status: dict[str, int] = {}
        by_handler: dict[str, int] = {}
        blocks: dict[str, list[int]] = {}
        for nc in ncs:
            status = _status(nc.status)
            by_status[status] = by_status.get(status, 0) + 1
            block = _label(nc.workarea_name)
            values = blocks.setdefault(block, [0, 0, 0])
            values[0] += 1
            if not _is_completed(nc):
                handler = _key(nc.current_handler) or "unknown"
                by_handler[handler] = by_handler.get(handler, 0) + 1
                values[2] += 1
                if _is_critical(nc):
                    values[1] += 1
        total = len(ncs)
        completed = sum(_is_completed(row) for row in ncs)
        rejected = sum(_status(row.status) == "rejected" for row in ncs)
        critical_open = sum(_is_critical(row) and not _is_completed(row) for row in ncs)
        closure_rate = round(completed / total * 100, 1) if total else 100
        score = 100
        score -= (1 - closure_rate / 100) * 30
        score -= critical_open / max(total, 1) * 25
        score -= rejected / max(total, 1) * 15
        rfi_completed = sum(_is_completed(row) for row in rfis)
        nc_items = tuple(cls._nc(row, now) for row in sorted(ncs, key=lambda row: row.created_at or now, reverse=True))
        return ProjectQualitySnapshot(
            resolution_status="resolved",
            query=query,
            project_id=project.project_id,
            project_name=project.display_name,
            match_kind=match_kind,
            available=bool(ncs or rfis),
            nc_available=bool(ncs),
            rfi_available=bool(rfis),
            total_ncs=total,
            open_ncs=total - completed,
            completed_ncs=completed,
            critical_open=critical_open,
            total_rfis=len(rfis),
            open_rfis=len(rfis) - rfi_completed,
            rfis_completed=rfi_completed,
            quality_score=max(0, round(score)),
            closure_rate=closure_rate,
            by_status=_pairs(by_status),
            by_handler=_pairs(by_handler),
            blocks=tuple((name, values[0], values[1], values[2]) for name, values in blocks.items()),
            ncs=nc_items,
            warnings=tuple(warnings),
            provenance=cls._provenance(ncs, rfis),
        )

    @classmethod
    def contractor_scorecard(cls, db: Session, portfolio: str | None = None) -> ContractorScorecard:
        all_ncs = db.query(models.PulseNC).order_by(models.PulseNC.id.asc()).all()
        _, matcher = cls._load_context(db, portfolio)
        scoped = bool(portfolio and _key(portfolio) != "all portfolios")
        ncs, _, warnings = cls._scope_rows(all_ncs, matcher, "pulse_nc", require_match=scoped)
        groups: dict[str, dict] = {}
        for nc in ncs:
            name = _label(nc.vendor_name)
            group = groups.setdefault(_key(name), {
                "name": name, "code": nc.vendor_code, "rows": [], "resolution": []
            })
            group["rows"].append(nc)
            if not group["code"] and nc.vendor_code:
                group["code"] = nc.vendor_code
            if _is_completed(nc) and nc.approved_at and nc.created_at:
                days = _elapsed_days(nc.created_at, nc.approved_at)
                if days >= 0:
                    group["resolution"].append(days)
        contractors = []
        for group in groups.values():
            rows = group["rows"]
            total = len(rows)
            completed = sum(_is_completed(row) for row in rows)
            opened = total - completed
            critical = sum(_is_critical(row) for row in rows)
            rejected = sum(_status(row.status) == "rejected" for row in rows)
            avg = round(sum(group["resolution"]) / len(group["resolution"]), 1) if group["resolution"] else None
            score = 100 - critical / total * 30 - rejected / total * 20 - min(opened / total * 25, 25)
            if avg and avg > 7:
                score -= min((avg - 7) * 2, 20)
            debit_rows = [row for row in rows if row.debit is not None and row.debit > 0]
            contractors.append(ContractorScore(
                name=group["name"], code=group["code"], total_ncs=total,
                critical=critical, open=opened, rejected=rejected, completed=completed,
                closure_rate=round(completed / total * 100, 1),
                debit_total=sum(float(row.debit) for row in debit_rows), debit_count=len(debit_rows),
                avg_resolution_days=avg, quality_score=max(0, round(score)),
            ))
        contractors.sort(key=lambda item: (-item.total_ncs, _key(item.name)))
        return ContractorScorecard(
            available=bool(ncs), contractors=tuple(contractors), warnings=tuple(warnings),
            provenance=cls._provenance(ncs, ()),
        )

    @classmethod
    def list_ncs(
        cls, db: Session, *, status: str | None = None, category: str | None = None,
        cluster: str | None = None, project: str | None = None, package: str | None = None,
        portfolio: str | None = None, page: int = 1, page_size: int = 50,
        now: datetime | None = None,
    ) -> QualityNCPage:
        page = max(1, int(page))
        page_size = max(1, min(200, int(page_size)))
        rows = db.query(models.PulseNC).order_by(models.PulseNC.created_at.desc(), models.PulseNC.id.desc()).all()
        _, matcher = cls._load_context(db, portfolio)
        warnings = []
        if project:
            resolution = cls.project_status(db, project, portfolio=portfolio, now=now)
            if resolution.resolution_status != "resolved":
                return QualityNCPage(False, (), 0, page, page_size, resolution.warnings)
            selected = []
            for row in rows:
                matched, candidates = matcher.match_row(row)
                if matched and matched.project_id == resolution.project_id:
                    selected.append(row)
                elif not matched:
                    warnings.append(cls._warning("pulse_nc", row, candidates))
            rows = selected
        elif portfolio and _key(portfolio) != "all portfolios":
            rows, _, warnings = cls._scope_rows(rows, matcher, "pulse_nc", require_match=True)
        if status:
            rows = [row for row in rows if _status(row.status) == _status(status)]
        if category:
            rows = [row for row in rows if _category(row.category).casefold() == _category(category).casefold()]
        if cluster:
            rows = [row for row in rows if _key(row.cluster_name) == _key(cluster)]
        if package:
            rows = [row for row in rows if _key(row.package_name) == _key(package)]
        total = len(rows)
        start = (page - 1) * page_size
        shown = rows[start:start + page_size]
        return QualityNCPage(
            available=bool(rows), items=tuple(cls._nc(row, _now(now)) for row in shown),
            total=total, page=page, page_size=page_size, warnings=tuple(warnings),
            provenance=cls._provenance(rows, ()),
        )

    @staticmethod
    def _nc(nc, now: datetime) -> QualityNC:
        return QualityNC(
            id=str(nc.pulse_id), nc_label=nc.nc_label, status=_status(nc.status),
            status_label=nc.status_label, category=_category(nc.category), defect_type=nc.defect_type,
            description=nc.description, current_handler=nc.current_handler,
            contractor_name=nc.contractor_name, vendor_name=nc.vendor_name,
            engineer_name=nc.engineer_name, quality_name=nc.quality_name,
            project_name=nc.project_name, cluster_name=nc.cluster_name,
            worklocation_name=nc.worklocation_name, workarea_name=nc.workarea_name,
            package_name=nc.package_name, subactivity_name=nc.subactivity_name,
            debit=nc.debit, debit_reason=nc.debit_reason, age_days=_age_days(nc.created_at, now),
            created_at=_iso(nc.created_at), approved_at=_iso(nc.approved_at),
        )

    # Explicit get_* names make the service API parallel to existing canonical services.
    get_portfolio_overview = portfolio_overview
    get_project_status = project_status
    get_project_snapshots = project_snapshots
    get_contractor_scorecard = contractor_scorecard


# Plain-dict adapters for routes/tools and gradual compatibility migration.
def get_quality_overview(db: Session, portfolio: str | None = None) -> dict:
    return QualityAnalyticsService.portfolio_overview(db, portfolio).to_dict()


def get_project_quality(db: Session, project: str, portfolio: str | None = None) -> dict:
    return QualityAnalyticsService.project_status(db, project, portfolio).to_dict()


def get_contractor_scorecard(db: Session, portfolio: str | None = None) -> list[dict]:
    return QualityAnalyticsService.contractor_scorecard(db, portfolio).to_dict()["contractors"]


def get_nc_list(db: Session, **filters) -> dict:
    return QualityAnalyticsService.list_ncs(db, **filters).to_dict()
