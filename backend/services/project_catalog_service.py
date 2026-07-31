from __future__ import annotations

from dataclasses import dataclass
import difflib
import re
from typing import Literal

from sqlalchemy import func
from sqlalchemy.orm import Session

import models


ResolutionStatus = Literal["resolved", "ambiguous", "not_found"]


class AmbiguousProjectError(ValueError):
    def __init__(self, query: str, candidates: tuple["CatalogProject", ...]):
        self.query = query
        self.candidates = candidates
        super().__init__(f"Multiple projects match '{query}'.")


def _normalize(value: str | None) -> str:
    return " ".join(str(value or "").strip().casefold().split())


_GENERIC_ALIAS_TOKENS = {
    "project",
    "projects",
    "solar",
    "wind",
    "site",
    "plant",
    "phase",
    "final",
}


def _alias_tokens(value: str | None) -> frozenset[str]:
    """Return meaningful identifier/name tokens suitable for exact alias matching."""
    tokens = re.findall(r"[a-z0-9]+", str(value or "").casefold())
    return frozenset(
        token
        for token in tokens
        if token not in _GENERIC_ALIAS_TOKENS
        and len(token) >= 4
        and not re.fullmatch(r"\d+(?:mw|mwp|mwac|mwdc)?", token)
    )


def _preferred_name(mapping: models.ProjectMapping) -> str:
    return mapping.project_name_from_p6 or mapping.project or ""


def _is_demo(mapping: models.ProjectMapping) -> bool:
    return "demo" in _preferred_name(mapping).casefold()


def has_portfolio_filter(portfolio: str | None) -> bool:
    return bool(portfolio) and str(portfolio).lower() != "all portfolios"


@dataclass(frozen=True, slots=True)
class CatalogProject:
    mapping_id: int
    project_id: str | None
    project_name: str | None
    p6_mapping_name: str | None
    display_name: str
    spv_name: str | None
    category: str | None
    cluster: str | None
    subcluster: str | None
    capacity_mwac: float | None
    capacity_mwdc: float | None
    spv_plant_code: str | None
    agel_code: str | None
    module_wbs: str | None
    plot_no: str | None
    priority: str | None

    @classmethod
    def from_mapping(cls, mapping: models.ProjectMapping) -> "CatalogProject":
        return cls(
            mapping_id=mapping.id,
            project_id=mapping.project_id,
            project_name=mapping.project,
            p6_mapping_name=mapping.project_name_from_p6,
            display_name=_preferred_name(mapping) or "Unknown project",
            spv_name=mapping.spv_name,
            category=mapping.category,
            cluster=mapping.cluster,
            subcluster=mapping.subcluster,
            capacity_mwac=mapping.capacity_mwac,
            capacity_mwdc=mapping.capacity_mwdc,
            spv_plant_code=mapping.spv_plant_code,
            agel_code=mapping.agel,
            module_wbs=mapping.module_wbs,
            plot_no=mapping.plot_no,
            priority=mapping.priority,
        )


@dataclass(frozen=True, slots=True)
class ProjectResolution:
    status: ResolutionStatus
    query: str
    match_kind: str | None = None
    project: CatalogProject | None = None
    candidates: tuple[CatalogProject, ...] = ()


class ProjectCatalogService:
    """Authoritative non-demo project population and identity resolution."""

    @staticmethod
    def list_mappings(db: Session, portfolio: str | None = None) -> list[models.ProjectMapping]:
        query = db.query(models.ProjectMapping)
        if has_portfolio_filter(portfolio):
            cleaned = str(portfolio).replace("+", " ").strip().lower()
            for part in cleaned.split():
                query = query.filter(
                    func.lower(models.ProjectMapping.cluster).contains(part)
                    | func.lower(models.ProjectMapping.category).contains(part)
                    | func.lower(models.ProjectMapping.project).contains(part)
                )

        mappings = query.order_by(models.ProjectMapping.id.asc()).all()
        return [mapping for mapping in mappings if not _is_demo(mapping)]

    @classmethod
    def list_projects(cls, db: Session, portfolio: str | None = None) -> tuple[CatalogProject, ...]:
        return tuple(CatalogProject.from_mapping(mapping) for mapping in cls.list_mappings(db, portfolio))

    @classmethod
    def get_by_project_id(cls, db: Session, project_id: str) -> CatalogProject | None:
        normalized = _normalize(project_id)
        matches = [
            project
            for project in cls.list_projects(db)
            if _normalize(project.project_id) == normalized
        ]
        return cls._representative(matches)

    @classmethod
    def get_display_name(
        cls,
        db: Session,
        project_id: str,
        *,
        fallback: str | None = None,
    ) -> str:
        project = cls.get_by_project_id(db, project_id)
        if project:
            return project.display_name
        if fallback:
            return fallback
        p6_name = db.query(models.P6Project.name).filter(
            models.P6Project.project_id == project_id
        ).scalar()
        return p6_name or project_id

    @classmethod
    def list_scoped_mappings(
        cls,
        db: Session,
        *,
        portfolio: str | None = None,
        project_name: str | None = None,
    ) -> list[models.ProjectMapping]:
        mappings = cls.list_mappings(db, portfolio)
        if not project_name or project_name == "All":
            return mappings

        resolution = cls.resolve(db, project_name, portfolio=portfolio)
        if resolution.status == "resolved" and resolution.project:
            project_ids = {resolution.project.project_id}
        elif resolution.status == "ambiguous":
            raise AmbiguousProjectError(project_name, resolution.candidates)
        else:
            return []
        return [mapping for mapping in mappings if mapping.project_id in project_ids]

    @staticmethod
    def is_known_project_id(
        db: Session,
        project_id: str,
        *,
        include_unmapped_p6: bool = False,
    ) -> bool:
        mapping_exists = db.query(models.ProjectMapping.id).filter(
            models.ProjectMapping.project_id == project_id
        ).first()
        if mapping_exists:
            return True
        if not include_unmapped_p6:
            return False
        return db.query(models.P6Project.id).filter(
            models.P6Project.project_id == project_id
        ).first() is not None

    @classmethod
    def resolve(
        cls,
        db: Session,
        value: str,
        *,
        portfolio: str | None = None,
    ) -> ProjectResolution:
        query = str(value or "").strip()
        normalized = _normalize(query)
        if not normalized:
            return ProjectResolution("not_found", query)

        projects = [project for project in cls.list_projects(db, portfolio) if project.project_id]
        project_ids = {project.project_id for project in projects if project.project_id}
        p6_names: dict[str, list[str]] = {}
        if project_ids:
            p6_rows = db.query(models.P6Project.project_id, models.P6Project.name).filter(
                models.P6Project.project_id.in_(project_ids)
            ).all()
            for project_id, name in p6_rows:
                if project_id and name:
                    p6_names.setdefault(project_id, []).append(name)

        tiers = (
            ("project_id", lambda project: [project.project_id]),
            ("project_name_from_p6", lambda project: [project.p6_mapping_name]),
            ("project", lambda project: [project.project_name]),
            ("p6_name", lambda project: p6_names.get(project.project_id or "", [])),
            ("spv_name", lambda project: [project.spv_name]),
        )
        for match_kind, values in tiers:
            matches = [
                project
                for project in projects
                if any(_normalize(candidate) == normalized for candidate in values(project) if candidate)
            ]
            resolution = cls._resolve_matches(query, match_kind, matches)
            if resolution:
                return resolution

        # Short site/location aliases such as "BAIYA" are often embedded inside a
        # longer P6 name or project ID. Match exact meaningful tokens, then retain
        # the existing identity grouping so one alias can resolve or explicitly
        # return every distinct canonical project when ambiguous.
        query_aliases = _alias_tokens(query)
        if query_aliases:
            alias_matches = []
            for project in projects:
                candidates = [
                    project.project_id,
                    project.project_name,
                    project.p6_mapping_name,
                    project.spv_name,
                    project.category,
                    project.cluster,
                    project.subcluster,
                    project.plot_no,
                    *p6_names.get(project.project_id or "", []),
                ]
                if any(
                    query_aliases.issubset(_alias_tokens(candidate))
                    for candidate in candidates
                    if candidate
                ):
                    alias_matches.append(project)
            resolution = cls._resolve_matches(query, "token_alias", alias_matches)
            if resolution:
                return resolution
        else:
            # Exact-name tiers above may legitimately resolve short identifiers,
            # but generic or capacity-only input must not fall through to fuzzy
            # matching and silently select a project (for example, "100MW").
            return ProjectResolution("not_found", query)

        scores: dict[str, tuple[float, CatalogProject]] = {}
        for project in projects:
            candidates = [
                project.project_name,
                project.p6_mapping_name,
                project.spv_name,
                *p6_names.get(project.project_id or "", []),
            ]
            for candidate in candidates:
                candidate_normalized = _normalize(candidate)
                if not candidate_normalized:
                    continue
                if normalized not in candidate_normalized and candidate_normalized not in normalized:
                    continue
                score = difflib.SequenceMatcher(None, normalized, candidate_normalized).ratio()
                identity = project.project_id or f"mapping:{project.mapping_id}"
                current = scores.get(identity)
                if current is None or score > current[0]:
                    scores[identity] = (score, project)

        eligible = [entry for entry in scores.values() if entry[0] >= 0.4]
        if not eligible:
            return ProjectResolution("not_found", query)
        best_score = max(score for score, _ in eligible)
        best = [project for score, project in eligible if score == best_score]
        return cls._resolve_matches(query, "fuzzy", best) or ProjectResolution("not_found", query)

    @classmethod
    def _resolve_matches(
        cls,
        query: str,
        match_kind: str,
        matches: list[CatalogProject],
    ) -> ProjectResolution | None:
        if not matches:
            return None
        grouped: dict[str, list[CatalogProject]] = {}
        for project in matches:
            identity = project.project_id or f"mapping:{project.mapping_id}"
            grouped.setdefault(identity, []).append(project)

        representatives = tuple(
            sorted(
                (cls._representative(group) for group in grouped.values()),
                key=lambda project: (
                    _normalize(project.display_name),
                    _normalize(project.project_id),
                    project.mapping_id,
                ),
            )
        )
        if len(representatives) == 1:
            return ProjectResolution(
                "resolved",
                query,
                match_kind=match_kind,
                project=representatives[0],
                candidates=representatives,
            )
        return ProjectResolution(
            "ambiguous",
            query,
            match_kind=match_kind,
            candidates=representatives,
        )

    @staticmethod
    def _representative(projects: list[CatalogProject]) -> CatalogProject | None:
        if not projects:
            return None
        return min(projects, key=lambda project: project.mapping_id)


def list_project_mappings(db: Session, portfolio: str | None = None) -> list[models.ProjectMapping]:
    return ProjectCatalogService.list_mappings(db, portfolio)
