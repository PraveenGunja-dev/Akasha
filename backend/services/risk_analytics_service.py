from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import date, datetime
import math
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from sqlalchemy.orm import Session

import models
from services.project_catalog_service import has_portfolio_filter, list_project_mappings
from services.sap_project_data_service import get_sap_project_data, get_sap_projects_data
from services.schedule_metrics_service import ScheduleMetricsService, calculate_schedule_metrics


PMAG_SCHEDULE_RAG = "pmag.schedule_rag"
COMMAND_CENTER_SCHEDULE_COUNT = "command_center.schedule_risk_count"
COMMAND_CENTER_FINANCIAL_COUNT = "command_center.financial_risk_count"
COMMAND_CENTER_OVERALL_SCORE = "command_center.overall_risk_score"
COMMAND_CENTER_HEATMAP = "command_center.risk_heatmap"
PROJECT360_RISK_FLAGS = "project360.risk_flags"
PROJECT360_COD_RISK = "project360.cod_risk"
PROJECT360_STATUS_TIER = "project360.status_tier"
PROJECT360_STATUS_TIER_COUNTS = "project360.status_tier_counts"
PREDICTIVE_PORTFOLIO_SLIPPAGE = "predictive.portfolio_slippage"
KPI_PROJECT_EXPOSURE = "kpi.project_exposure"
KPI_PORTFOLIO_PROJECT_EXPOSURE = "kpi.portfolio_project_exposure"


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set):
        return frozenset(_freeze(item) for item in value)
    return value


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, frozenset)):
        return [_plain(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class RiskMetric:
    """Immutable, provenance-carrying result for one named risk formula."""

    metric_id: str
    name: str
    formula_version: str
    scope: str
    value: Any
    unit: str
    classification: str | None
    components: Mapping[str, Any]
    formula: str
    availability: bool
    heuristic: bool
    evidence: tuple[Any, ...]
    warnings: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _freeze(self.value))
        object.__setattr__(self, "components", _freeze(self.components))
        object.__setattr__(self, "evidence", tuple(_freeze(item) for item in self.evidence))
        object.__setattr__(self, "warnings", tuple(self.warnings))

    def to_dict(self) -> dict[str, Any]:
        return {field.name: _plain(getattr(self, field.name)) for field in fields(self)}


def _get(record: object, *names: str, default: Any = None) -> Any:
    for name in names:
        if isinstance(record, Mapping) and name in record:
            return record[name]
        if hasattr(record, name):
            return getattr(record, name)
    return default


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


class RiskAnalyticsService:
    """Named risk calculations. Metrics remain separate unless a source formula combines them."""

    @staticmethod
    def project360_inputs(
        p6: object | None,
        schedule,
        sap: Mapping[str, Any],
        *,
        today: date | None = None,
    ) -> dict[str, float | None]:
        """Build the one authoritative input snapshot for Project360 risk formulas."""
        po = sap["totals"]["purchase_orders"]
        inventory = sap["totals"]["inventory"]
        consumption = sap["totals"]["consumption"]
        ordered = float(po["ordered_quantity"])
        transit = float(po["pending_quantity"])
        inventory_qty = float(inventory["quantity"])
        material_pct = (
            min(100, round(((inventory_qty + transit) / ordered) * 100))
            if ordered > 0
            else 100 if inventory_qty > 0 else 0
        )
        progress_fraction = (
            float(schedule.progress_pct) / 100
            if schedule.p6_available and schedule.progress_pct is not None
            else None
        )
        budget = float(po["order_value"] or 0) or float(getattr(p6, "planned_cost", 0) or 0)
        actual_cost = float(consumption["net_value"] or 0) or float(
            getattr(p6, "actual_total_cost", 0) or 0
        )
        planned_fraction = progress_fraction
        start = getattr(p6, "baseline_start_date", None) or getattr(p6, "start_date", None)
        finish = (
            getattr(p6, "baseline_finish_date", None)
            or getattr(p6, "scheduled_finish_date", None)
            or getattr(p6, "finish_date", None)
        )
        if start and finish:
            start_date = start.date() if isinstance(start, datetime) else start
            finish_date = finish.date() if isinstance(finish, datetime) else finish
            if finish_date > start_date:
                elapsed = ((today or datetime.now().date()) - start_date).days
                planned_fraction = min(1.0, max(0.0, elapsed / (finish_date - start_date).days))
        earned_value = progress_fraction * budget if progress_fraction is not None else None
        planned_value = planned_fraction * budget if planned_fraction is not None else None
        spi = None
        if earned_value is not None and planned_value is not None:
            spi = (
                earned_value / planned_value
                if planned_value > 0
                else progress_fraction / planned_fraction if planned_fraction and planned_fraction > 0 else 1.0
            )
        cpi = (
            earned_value / actual_cost
            if earned_value is not None and actual_cost > 0
            else 1.0 if progress_fraction is not None else None
        )
        variance = schedule.finish_date_variance if schedule.p6_available else None
        if variance is None and getattr(p6, "baseline_finish_date", None):
            compare = getattr(p6, "scheduled_finish_date", None) or getattr(p6, "finish_date", None)
            if compare:
                variance = (p6.baseline_finish_date - compare).days
        return {
            "ordered_quantity": ordered,
            "in_transit_quantity": transit,
            "inventory_quantity": inventory_qty,
            "material_availability_pct": material_pct,
            "progress_pct": progress_fraction * 100 if progress_fraction is not None else None,
            "schedule_variance_days": float(variance) if variance is not None else None,
            "spi": spi,
            "cpi": cpi,
            "cost_variance_inr": (
                float(p6.total_cost_variance)
                if p6 is not None and p6.total_cost_variance is not None
                else None
            ),
        }

    @staticmethod
    def pmag_schedule_rag(finish_date_variance: Any, *, scope: str = "project") -> RiskMetric:
        variance = _number(finish_date_variance)
        classification = (
            "grey" if variance is None else
            "green" if variance >= 0 else
            "amber" if variance >= -7 else
            "red"
        )
        return RiskMetric(
            metric_id=PMAG_SCHEDULE_RAG,
            name="PMAG schedule RAG",
            formula_version="pmag-schedule-rag-v1",
            scope=scope,
            value=classification if variance is not None else None,
            unit="RAG category",
            classification=classification,
            components={"finish_date_variance": variance, "variance_unit": "days"},
            formula="grey if variance is null; green if variance >= 0; amber if -7 <= variance < 0; red if variance < -7",
            availability=variance is not None,
            heuristic=False,
            evidence=({"finish_date_variance": variance, "unit": "days"},) if variance is not None else (),
            warnings=() if variance is not None else ("Finish-date variance is unavailable; PMAG displays grey.",),
        )

    @staticmethod
    def command_center_schedule_count(projects: Iterable[object]) -> RiskMetric:
        risks = []
        supplied = list(projects or ())
        for project in supplied:
            variance = _number(_get(project, "finish_date_variance", "finishDateVariance"))
            if variance is not None and variance < -30:
                risks.append({
                    "project_id": _get(project, "project_id", "projectId"),
                    "name": _get(project, "name"),
                    "finish_date_variance": variance,
                    "unit": "days",
                })
        risks.sort(key=lambda item: item["finish_date_variance"], reverse=True)
        return RiskMetric(
            metric_id=COMMAND_CENTER_SCHEDULE_COUNT,
            name="Portfolio Command Center schedule risk count",
            formula_version="command-center-schedule-count-v1",
            scope="portfolio",
            value=len(risks),
            unit="projects",
            classification=None,
            components={"threshold_days": -30, "projects_evaluated": len(supplied)},
            formula="count(project where finish_date_variance < -30 days)",
            availability=True,
            heuristic=False,
            evidence=tuple(risks),
            warnings=(),
        )

    @staticmethod
    def command_center_financial_count(purchase_orders: Iterable[object]) -> RiskMetric:
        risks = []
        supplied = list(purchase_orders or ())
        for po in supplied:
            quantity = _number(_get(po, "po_quantities_mw"))
            if quantity is not None and quantity > 500:
                risks.append({
                    "purchasing_document": _get(po, "purchasing_document"),
                    "vendor_name": _get(po, "vendor_name"),
                    "po_quantities_mw": quantity,
                    "unit": "MW",
                })
        risks.sort(key=lambda item: item["po_quantities_mw"], reverse=True)
        return RiskMetric(
            metric_id=COMMAND_CENTER_FINANCIAL_COUNT,
            name="Portfolio Command Center high-volume PO count",
            formula_version="command-center-financial-count-v1",
            scope="portfolio",
            value=len(risks),
            unit="purchase orders",
            classification=None,
            components={"threshold_mw": 500, "purchase_orders_evaluated": len(supplied)},
            formula="count(purchase order where po_quantities_mw > 500 MW)",
            availability=True,
            heuristic=False,
            evidence=tuple(risks),
            warnings=("This is a PO-volume threshold, not a monetary financial-risk calculation.",),
        )

    @staticmethod
    def command_center_overall_score(schedule_count: int, financial_count: int) -> RiskMetric:
        schedule_count = max(0, int(schedule_count))
        financial_count = max(0, int(financial_count))
        raw = 5 * schedule_count + 2 * financial_count
        score = min(100, raw)
        return RiskMetric(
            metric_id=COMMAND_CENTER_OVERALL_SCORE,
            name="Portfolio Command Center overall risk score",
            formula_version="command-center-overall-v1",
            scope="portfolio",
            value=score,
            unit="score (0-100)",
            classification=None,
            components={"schedule_risk_count": schedule_count, "financial_risk_count": financial_count, "uncapped_score": raw},
            formula="min(100, 5 * schedule_risk_count + 2 * financial_risk_count)",
            availability=True,
            heuristic=False,
            evidence=(),
            warnings=("This score combines only the two Command Center counts; it is not a probability or KPI exposure score.",),
        )

    @staticmethod
    def command_center_heatmap(schedule_evidence: Iterable[object]) -> RiskMetric:
        points = []
        for index, item in enumerate(schedule_evidence or ()):
            variance = _number(_get(item, "finish_date_variance", "finishDateVariance"))
            # Preserve the current visual formula, including its signed-variance impact input.
            impact = min(5, max(3, math.ceil((variance or 0) / 100)))
            points.append({
                "probability": index % 3 + 3,
                "impact": impact,
                "name": _get(item, "name"),
                "finish_date_variance": variance,
            })
        return RiskMetric(
            metric_id=COMMAND_CENTER_HEATMAP,
            name="Portfolio Command Center risk heatmap",
            formula_version="command-center-heatmap-v1",
            scope="portfolio",
            value=points,
            unit="ordinal 1-5 coordinates",
            classification="heuristic",
            components={"point_count": len(points)},
            formula="probability = (display_index mod 3) + 3; impact = min(5, max(3, ceil(finish_date_variance / 100)))",
            availability=bool(points),
            heuristic=True,
            evidence=tuple(points),
            warnings=("Heatmap probability and impact coordinates are display heuristics, not calibrated risk estimates.",),
        )

    @staticmethod
    def project360_risk_flags(
        *, material_availability_pct: Any, po_volume: Any, schedule_variance_days: Any,
        spi: Any, in_transit_volume: Any, cost_variance_inr: Any, progress_pct: Any,
    ) -> RiskMetric:
        mat = _number(material_availability_pct)
        po = _number(po_volume)
        variance = _number(schedule_variance_days)
        spi_value = _number(spi)
        transit = _number(in_transit_volume)
        cost = _number(cost_variance_inr)
        progress = _number(progress_pct)
        flags = {
            "material_risk": bool(mat is not None and po is not None and mat < 80 and po > 0),
            "schedule_risk": bool((variance is not None and variance < -10) or (spi_value is not None and spi_value < 0.95)),
            "vendor_risk": bool(transit is not None and po is not None and transit == 0 and po > 0),
            "financial_risk": bool(cost is not None and cost < -1_000_000),
            "procurement_risk": bool(po is not None and progress is not None and po == 0 and progress < 50),
        }
        available = any(value is not None for value in (mat, po, variance, spi_value, transit, cost, progress))
        return RiskMetric(
            metric_id=PROJECT360_RISK_FLAGS,
            name="Project360 risk flags",
            formula_version="project360-risk-flags-v1",
            scope="project",
            value=flags,
            unit="boolean flags",
            classification=None,
            components={"material_availability_pct": mat, "po_volume": po, "schedule_variance_days": variance, "spi": spi_value, "in_transit_volume": transit, "cost_variance_inr": cost, "progress_pct": progress},
            formula="material: availability < 80% and PO > 0; schedule: variance < -10 days or SPI < 0.95; vendor: transit = 0 and PO > 0; financial: cost variance < -1,000,000 INR; procurement: PO = 0 and progress < 50%",
            availability=available,
            heuristic=False,
            evidence=(),
            warnings=() if available else ("No Project360 risk inputs are available.",),
        )

    @staticmethod
    def project360_cod_risk(*, schedule_variance_days: Any, material_risk: bool, material_availability_pct: Any, vendor_risk: bool) -> RiskMetric:
        variance = _number(schedule_variance_days)
        mat = _number(material_availability_pct)
        delay_days = abs(round(variance)) if variance is not None and variance < 0 else 0
        at_risk = delay_days > 14 or (material_risk and mat is not None and mat < 50) or vendor_risk
        available = variance is not None or mat is not None or material_risk or vendor_risk
        return RiskMetric(
            metric_id=PROJECT360_COD_RISK,
            name="Project360 COD risk",
            formula_version="project360-cod-risk-v1",
            scope="project",
            value=at_risk if available else None,
            unit="boolean",
            classification=("at risk" if at_risk else "not at risk") if available else None,
            components={"delay_days": delay_days, "material_risk": bool(material_risk), "material_availability_pct": mat, "vendor_risk": bool(vendor_risk)},
            formula="rounded delay > 14 days OR (material risk AND availability < 50%) OR vendor risk",
            availability=available,
            heuristic=False,
            evidence=(),
            warnings=() if available else ("No Project360 COD risk inputs are available.",),
        )

    @staticmethod
    def project360_status_tier(*, progress_pct: Any, schedule_variance_days: Any, spi: Any, material_availability_pct: Any, ordered_quantity: Any, vendor_risk: bool) -> RiskMetric:
        progress = _number(progress_pct)
        variance = _number(schedule_variance_days)
        spi_value = _number(spi)
        mat = _number(material_availability_pct)
        ordered = _number(ordered_quantity)
        has_order = ordered is not None and ordered > 0
        if progress is not None and progress >= 99:
            tier = "Completed"
        elif ((variance is not None and spi_value is not None and variance < -30 and spi_value < 0.8) or (mat is not None and mat < 30 and has_order)):
            tier = "Critical"
        elif (variance is not None and variance < -20) or (mat is not None and mat < 50 and has_order) or vendor_risk:
            tier = "High Risk"
        elif (variance is not None and variance < -10) or (mat is not None and mat < 80 and has_order):
            tier = "Watchlist"
        else:
            tier = "Healthy"
        available = any(value is not None for value in (progress, variance, spi_value, mat, ordered)) or vendor_risk
        return RiskMetric(
            metric_id=PROJECT360_STATUS_TIER,
            name="Project360 status tier",
            formula_version="project360-status-tier-v2",
            scope="project",
            value=tier if available else None,
            unit="status tier",
            classification=tier if available else None,
            components={"progress_pct": progress, "schedule_variance_days": variance, "spi": spi_value, "material_availability_pct": mat, "ordered_quantity": ordered, "vendor_risk": bool(vendor_risk)},
            formula="Completed at progress >= 99%; else Critical/High Risk/Watchlist/Healthy using the Project360 ordered thresholds",
            availability=available,
            heuristic=False,
            evidence=(),
            warnings=() if available else ("No Project360 status inputs are available.",),
        )

    @staticmethod
    def project360_status_tier_counts(projects: Iterable[object]) -> RiskMetric:
        """Aggregate the exact status tiers already assigned by Project 360."""
        supplied = list(projects or ())
        tiers = ("Critical", "High Risk", "Watchlist", "Healthy", "Completed")
        counts = {tier: 0 for tier in tiers}
        evidence = []
        for project in supplied:
            tier = _get(project, "statusTier", "status_tier")
            if tier not in counts:
                continue
            counts[tier] += 1
            evidence.append({
                "project_id": _get(project, "projectId", "project_id"),
                "project_name": _get(project, "projectName", "project_name"),
                "status_tier": tier,
            })
        return RiskMetric(
            metric_id=PROJECT360_STATUS_TIER_COUNTS,
            name="Project 360 portfolio status-tier counts",
            formula_version="project360-status-tier-counts-v1",
            scope="portfolio",
            value=counts,
            unit="projects by status tier",
            classification=None,
            components={
                "projects_evaluated": len(supplied),
                "projects_classified": sum(counts.values()),
                "tiers": tiers,
            },
            formula="count the statusTier values produced by the Project 360 portfolio dataset",
            availability=bool(supplied),
            heuristic=False,
            evidence=tuple(evidence),
            warnings=() if supplied else ("No Project 360 projects are available.",),
        )

    @staticmethod
    def predictive_portfolio_slippage(projects: Iterable[object]) -> RiskMetric:
        supplied = list(projects or ())
        total_delay = sum(
            abs(variance) for variance in (
                _number(_get(project, "finish_date_variance", "finishDateVariance"))
                for project in supplied
            ) if variance is not None and variance < 0
        )
        active_count = sum(_get(project, "status") == "Active" for project in supplied)
        denominator = active_count or 1
        average = total_delay / denominator
        forecasts = {"current": average, "30_days": average * 1.2, "60_days": average * 1.5, "90_days": average * 1.9}
        return RiskMetric(
            metric_id=PREDICTIVE_PORTFOLIO_SLIPPAGE,
            name="Predictive portfolio schedule slippage",
            formula_version="predictive-slippage-v1",
            scope="portfolio",
            value=forecasts,
            unit="days of average delay",
            classification="heuristic forecast",
            components={"negative_variance_total_days": total_delay, "active_project_count": active_count, "denominator": denominator, "multipliers": {"30_days": 1.2, "60_days": 1.5, "90_days": 1.9}, "confidence_pct": 87},
            formula="average = sum(abs(negative variance)) / max(active project count, 1); forecasts = average * [1.2, 1.5, 1.9]",
            availability=bool(supplied),
            heuristic=True,
            evidence=(),
            warnings=("The 87% confidence label is fixed presentation text and is not statistically calibrated.",),
        )

    @staticmethod
    def kpi_project_exposure(db: Session, project_id: str) -> RiskMetric:
        from engine.kpi_engine import compute_project_kpis

        exposure = compute_project_kpis(db, project_id, calculate_health=False)
        available = "error" not in exposure
        return RiskMetric(
            metric_id=KPI_PROJECT_EXPOSURE,
            name="KPI engine project exposure",
            formula_version="kpi-project-exposure-adapter-v1",
            scope=project_id,
            value=exposure if available else None,
            unit="KPI exposure bundle",
            classification=None,
            components={},
            formula="adapter: compute_project_kpis(db, project_id, calculate_health=False)",
            availability=available,
            heuristic=False,
            evidence=(exposure,) if available else (),
            warnings=() if available else (str(exposure.get("error", "KPI exposure unavailable")),),
        )

    @staticmethod
    def portfolio_project_exposures(db: Session) -> tuple[RiskMetric, ...]:
        """Expose the KPI portfolio ranking as explicit, independently named metrics."""
        from engine.kpi_engine import compute_portfolio_kpis

        return tuple(
            RiskMetric(
                metric_id=KPI_PORTFOLIO_PROJECT_EXPOSURE,
                name="KPI portfolio project exposure",
                formula_version="kpi-portfolio-project-exposure-adapter-v1",
                scope=str(exposure["project_id"]),
                value=exposure,
                unit="KPI exposure bundle",
                classification=None,
                components={},
                formula="adapter: compute_portfolio_kpis(db), one envelope per ranked project",
                availability=True,
                heuristic=False,
                evidence=(exposure,),
                warnings=(),
            )
            for exposure in compute_portfolio_kpis(db)
        )

    @classmethod
    def _portfolio_projects(
        cls,
        db: Session,
        portfolio: str | None = None,
        project_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Match /api/summary's project population and legacy variance fallback."""
        project_ids = list(dict.fromkeys(
            mapping.project_id
            for mapping in list_project_mappings(db, portfolio)
            if mapping.project_id
        ))
        if project_id:
            project_ids = [candidate for candidate in project_ids if candidate == project_id]
        if not project_ids:
            return []

        projects = db.query(models.P6Project).filter(models.P6Project.project_id.in_(project_ids)).all()
        result = []
        for project in projects:
            schedule = calculate_schedule_metrics(project)
            variance = schedule.finish_date_variance
            if variance is None and schedule.baseline_finish:
                compare_date = schedule.scheduled_finish or schedule.finish_date
                if compare_date:
                    variance = (schedule.baseline_finish - compare_date).days
            result.append({
                "project_id": schedule.project_id,
                "name": project.name,
                "status": schedule.status,
                "finish_date_variance": variance,
            })
        return result

    @classmethod
    def command_center(
        cls,
        db: Session,
        portfolio: str | None = None,
        project_id: str | None = None,
    ) -> tuple[RiskMetric, ...]:
        projects = cls._portfolio_projects(db, portfolio, project_id)
        schedule = cls.command_center_schedule_count(projects)
        if project_id:
            purchase_orders = sorted(
                get_sap_project_data(db, project_id)["purchase_orders"],
                key=lambda row: row.net_order_value_inr or 0,
                reverse=True,
            )[:100]
        elif has_portfolio_filter(portfolio):
            records = {}
            for result in get_sap_projects_data(
                db,
                list(dict.fromkeys(
                    mapping.project_id
                    for mapping in list_project_mappings(db, portfolio)
                    if mapping.project_id
                )),
            ).values():
                for record in result["purchase_orders"]:
                    records[record.id] = record
            purchase_orders = sorted(
                records.values(),
                key=lambda row: row.net_order_value_inr or 0,
                reverse=True,
            )[:100]
        else:
            purchase_orders = db.query(models.MTPOAmount).order_by(
                models.MTPOAmount.net_order_value_inr.desc()
            ).limit(100).all()
        financial = cls.command_center_financial_count(purchase_orders)
        overall = cls.command_center_overall_score(schedule.value, financial.value)
        heatmap = cls.command_center_heatmap(schedule.evidence)
        return schedule, financial, overall, heatmap

    @classmethod
    def predictive(
        cls,
        db: Session,
        portfolio: str | None = None,
        project_id: str | None = None,
    ) -> RiskMetric:
        return cls.predictive_portfolio_slippage(
            cls._portfolio_projects(db, portfolio, project_id)
        )

    @classmethod
    def project360(cls, db: Session, project_id: str) -> tuple[RiskMetric, ...]:
        schedule = ScheduleMetricsService.get_by_project_id(db, project_id)
        sap = get_sap_project_data(db, project_id)
        p6 = db.query(models.P6Project).filter(
            models.P6Project.project_id == project_id
        ).first()
        if not schedule.p6_available and not sap["has_data"]:
            unavailable = (None, None, None, None, None, None, None)
            flags = cls.project360_risk_flags(
                material_availability_pct=unavailable[0], po_volume=unavailable[1],
                schedule_variance_days=unavailable[2], spi=unavailable[3],
                in_transit_volume=unavailable[4], cost_variance_inr=unavailable[5],
                progress_pct=unavailable[6],
            )
            cod = cls.project360_cod_risk(schedule_variance_days=None, material_risk=False, material_availability_pct=None, vendor_risk=False)
            status = cls.project360_status_tier(progress_pct=None, schedule_variance_days=None, spi=None, material_availability_pct=None, ordered_quantity=None, vendor_risk=False)
            return flags, cod, status

        inputs = cls.project360_inputs(p6, schedule, sap)
        flags = cls.project360_risk_flags(
            material_availability_pct=inputs["material_availability_pct"],
            po_volume=inputs["ordered_quantity"],
            schedule_variance_days=inputs["schedule_variance_days"],
            spi=inputs["spi"],
            in_transit_volume=inputs["in_transit_quantity"],
            cost_variance_inr=inputs["cost_variance_inr"],
            progress_pct=inputs["progress_pct"],
        )
        cod = cls.project360_cod_risk(
            schedule_variance_days=inputs["schedule_variance_days"],
            material_risk=flags.value["material_risk"],
            material_availability_pct=inputs["material_availability_pct"],
            vendor_risk=flags.value["vendor_risk"],
        )
        status = cls.project360_status_tier(
            progress_pct=inputs["progress_pct"],
            schedule_variance_days=inputs["schedule_variance_days"],
            spi=inputs["spi"],
            material_availability_pct=inputs["material_availability_pct"],
            ordered_quantity=inputs["ordered_quantity"],
            vendor_risk=flags.value["vendor_risk"],
        )
        return flags, cod, status
