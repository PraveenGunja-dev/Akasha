"""High-recall deterministic tool routing for the LangGraph agent."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable


RESOLVER = "portfolio_resolve_project_id"
PROJECT_HEALTH_TOOL = "get_project_kpis"

P6_TOOLS = {
    "p6_get_project_summary",
    "p6_get_block_period_progress",
    "p6_get_daily_completion_trend",
    "p6_get_portfolio_milestone_risks",
    "p6_list_all_projects",
    "p6_get_critical_activities",
    "p6_get_delayed_activities",
    "p6_get_activity_status_breakdown",
    "p6_get_activities",
    "get_project_kpis",
}
SAP_TOOLS = {
    "sap_get_po_summary",
    "sap_get_material_gaps",
    "sap_get_vendor_performance",
    "sap_get_inventory",
    "sap_get_consumption",
}
TRANSMISSION_TOOLS = {
    "tc_get_project_lines",
    "tc_get_at_risk_lines",
    "tc_get_network_summary",
    "tc_search_lines",
}
PORTFOLIO_TOOLS = {
    "portfolio_get_riskiest_projects",
    "portfolio_get_notifications",
    "p6_list_all_projects",
}
SIMULATION_TOOLS = {
    "sim_get_activity_productivity",
    "sim_project_duration_what_if",
    "sim_monsoon_impact",
    "sim_material_bottlenecks",
    "sim_forecast_completion",
    "sim_forecast_activity_finishes",
}
REPORT_TOOLS = {
    "report_preview_project_progress",
    "report_generate_project_progress",
    "report_preview_portfolio_progress",
    "report_generate_portfolio_progress",
    "report_preview_project_comparison",
    "report_generate_project_comparison",
}
CAPACITY_TOOLS = {"capacity_get_portfolio_overview", "capacity_get_project_status"}
QUALITY_TOOLS = {
    "quality_get_portfolio_overview",
    "quality_get_project_status",
    "quality_get_contractor_scorecard",
}
RISK_TOOLS = {"risk_get_metric"}


@dataclass(frozen=True, slots=True)
class ToolRoute:
    tool_names: tuple[str, ...]
    domains: tuple[str, ...]
    intent: str
    operational: bool
    uses_all_tools: bool
    required_evidence_tools: tuple[str, ...] = ()


_P6_SPECIFIC = re.compile(
    r"\b(?:p6|primavera|schedule|scheduled|baseline|milestone|activity|activities|"
    r"block|blocks|wbs|critical path|total float|float|spi|cpi|planned duration|actual duration)\b",
    re.IGNORECASE,
)
_SAP_SPECIFIC = re.compile(
    r"\b(?:sap|procurement|purchase order|purchase orders|po summary|po value|material|"
    r"materials|vendor|vendors|supplier|inventory|stock|delivery|deliveries|delivered|"
    r"consumption|consumed|ordered quantity|pending quantity)\b",
    re.IGNORECASE,
)
_TC_SPECIFIC = re.compile(
    r"\b(?:transmission|grid|substation|connectivity|voltage|stringing|charged line|"
    r"network|network edge|network edges|tower erection|evacuation|readiness|tc)\b",
    re.IGNORECASE,
)
_PORTFOLIO_SPECIFIC = re.compile(
    r"\b(?:portfolio|all projects|riskiest projects|which projects|projects are|"
    r"notification|notifications|alert|alerts)\b",
    re.IGNORECASE,
)
_CAPACITY_SPECIFIC = re.compile(
    r"\b(?:capacity|mwac|megawatt|trial run|commercial operation|cod milestone)\b",
    re.IGNORECASE,
)
_QUALITY_SPECIFIC = re.compile(
    r"\b(?:quality|non[ -]?conformance|nc|ncs|rfi|rfis|contractor scorecard|closure rate|aging)\b",
    re.IGNORECASE,
)
_RISK_SPECIFIC = re.compile(
    r"\b(?:risk|risks|exposure|schedule rag|financial risk|risk score|risk heatmap|"
    r"cod risk|risk flags|status tier|slippage|healthy|watchlist|high[ -]?risk|"
    r"critical projects?|project 360)\b",
    re.IGNORECASE,
)
_GENERIC_STATUS = re.compile(
    r"\b(?:progress|status|complete|completion|finish|start|delay|delays|delayed|late|slip|"
    r"performance|health|risk|risks|exposure|on track|behind|ahead)\b",
    re.IGNORECASE,
)
_GENERAL_CONVERSATION = re.compile(
    r"^\s*(?:hi|hello|hey|thanks|thank you|good (?:morning|afternoon|evening)|"
    r"who are you|what can you do|help)\s*[?.!]*\s*$",
    re.IGNORECASE,
)
_DEFINITIONAL = re.compile(r"^\s*(?:what is|what does|define|explain)\b", re.IGNORECASE)
_CURRENT_DATA = re.compile(
    r"\b(?:current|currently|today|latest|as of|our|project|portfolio|show|list|how many|"
    r"which|data|metric|value)\b",
    re.IGNORECASE,
)
_PROJECT_CODE = re.compile(r"\b[A-Z0-9]{4,}[_-][A-Z0-9_-]{3,}\b")
_FOLLOW_UP = re.compile(
    r"^\s*(?:and\b|also\b|what about\b|how about\b|same\b|now\b|yes\b|confirm\b)|"
    r"\b(?:it|its|that|those|them|this project|that project|same project|above)\b",
    re.IGNORECASE,
)


def _detected_domains(text: str) -> set[str]:
    domains = set()
    if _P6_SPECIFIC.search(text):
        domains.add("p6")
    if _SAP_SPECIFIC.search(text):
        domains.add("sap")
    if _TC_SPECIFIC.search(text):
        domains.add("transmission")
    if _PORTFOLIO_SPECIFIC.search(text):
        domains.add("portfolio")
    if _CAPACITY_SPECIFIC.search(text):
        domains.add("capacity")
    if _QUALITY_SPECIFIC.search(text):
        domains.add("quality")
    if _RISK_SPECIFIC.search(text):
        domains.add("risk")
    if re.search(r"\b(?:report|pdf|docx|download)\b", text, re.IGNORECASE):
        domains.add("report")
    if re.search(
        r"\b(?:forecast|predict|projection|what[ -]if|scenario|simulate|simulation|"
        r"productivity|manpower|monsoon|bottleneck|expected completion|on track|commissioning)\b|"
        r"\bwhen will\b|\bwill\b.{0,30}\b(?:finish|complete|slip|delay)\b",
        text,
        re.IGNORECASE,
    ):
        domains.add("simulation")
    if re.search(r"\b(?:charts?|graphs?|plots?|visuals?|visualizations?|donuts?|bar charts?)\b", text, re.IGNORECASE):
        domains.add("visualization")
    if re.search(
        r"\b(?:daily|day[ -]by[ -]day)\b.{0,35}\b(?:progress|completion|performance)\s+trend\b|"
        r"\b(?:compare|comparison|versus|vs\.?|distribution|breakdown|trend over time)\b|"
        r"\b(?:block|blocks|phase-wise)\b.{0,35}\b(?:progress|snapshot|ranking|comparison)\b|"
        r"\b(?:progress|snapshot|ranking|comparison)\b.{0,35}\b(?:block|blocks|phase-wise)\b",
        text,
        re.IGNORECASE,
    ):
        domains.add("visualization")
    if re.search(
        r"\b(?:daily|day[ -]by[ -]day)\b.{0,35}\b(?:progress|completion|performance)\s+trend\b|"
        r"\b(?:block|blocks|phase-wise)\b.{0,35}\b(?:progress|snapshot|ranking|comparison)\b|"
        r"\b(?:progress|snapshot|ranking|comparison)\b.{0,35}\b(?:block|blocks|phase-wise)\b|"
        r"\b(?:compare|comparison)\b.{0,40}\b(?:project|progress|schedule|completion)\b",
        text,
        re.IGNORECASE,
    ):
        domains.add("p6")
    return domains


def _ordered_names(selected: set[str], available: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(name for name in available if name in selected)


def select_tool_route(
    question: str,
    *,
    context: str = "",
    available_tool_names: Iterable[str],
) -> ToolRoute:
    """Select a high-recall subset; uncertain operational requests retain the full catalog."""
    available = tuple(dict.fromkeys(available_tool_names))
    available_set = set(available)
    non_health_tools = tuple(name for name in available if name != PROJECT_HEALTH_TOOL)
    current = (question or "").strip()
    prior = (context or "").strip()
    current_domains = _detected_domains(current)
    context_domains = _detected_domains(prior)
    has_generic_status = bool(_GENERIC_STATUS.search(current))
    is_contextual_follow_up = bool(prior and _FOLLOW_UP.search(current))

    # Short generic follow-ups inherit a clear prior domain. If history is mixed, keeping
    # the route broad is safer than guessing which earlier subject the user meant.
    if (
        not current_domains
        and has_generic_status
        and is_contextual_follow_up
        and len(context_domains) == 1
    ):
        current_domains = set(context_domains)
    elif not current_domains and is_contextual_follow_up and len(context_domains) == 1:
        current_domains = set(context_domains)

    if _GENERAL_CONVERSATION.match(current):
        return ToolRoute((), (), "conversation", False, False)

    has_live_scope = bool(_CURRENT_DATA.search(current) or _PROJECT_CODE.search(current))
    if (
        _DEFINITIONAL.search(current)
        and not has_live_scope
        and not has_generic_status
        and not _FOLLOW_UP.search(current)
    ):
        return ToolRoute((), (), "definition", False, False)

    if has_generic_status and re.search(
        r"\b(?:overall|project health|project risk|project performance|project exposure)\b",
        current,
        re.IGNORECASE,
    ):
        current_domains.update({"p6", "sap", "transmission"})
    elif not current_domains and has_generic_status:
        current_domains.add("p6")
    elif has_generic_status and "p6" not in current_domains and (
        len(current_domains & {"p6", "sap", "transmission", "portfolio"}) >= 2
        or (
            "visualization" in current_domains
            and not current_domains.intersection({"sap", "transmission", "capacity", "quality", "risk"})
            and re.search(r"\b(?:progress|schedule|activity|completion)\b", current, re.IGNORECASE)
        )
        or re.search(r"\b(?:project|overall)\s+(?:progress|status|completion)\b", current, re.IGNORECASE)
    ):
        current_domains.add("p6")

    operational = bool(
        current_domains
        or has_live_scope
        or is_contextual_follow_up
        or re.search(r"\b(?:project|portfolio|data|metric|risk|status)\b", current, re.IGNORECASE)
    )
    if not operational:
        return ToolRoute((), (), "general", False, False)

    if re.search(
        r"\b(?:resolve|find|identify|look up|lookup)\b.{0,30}\bproject\b|"
        r"\bproject\b.{0,20}\b(?:id|identifier|name)\b",
        current,
        re.IGNORECASE,
    ) and not current_domains:
        names = _ordered_names({RESOLVER}, available)
        return ToolRoute(names, ("project",), "project_resolution", True, False)

    # A live operational request with no discernible domain is genuinely ambiguous.
    if not current_domains:
        return ToolRoute(non_health_tools, ("all",), "ambiguous_operational", True, False)

    selected = {RESOLVER}
    intent_parts = []

    if "p6" in current_domains:
        intent_parts.append("schedule")
        selected.add("p6_get_project_summary")
        if re.search(r"\bblock(?:s)?\b", current, re.IGNORECASE) and re.search(
            r"\b(?:last|current|this|previous)\s+month\b|\bmonthly\b|"
            r"\b(?:last|past|previous)\s+\d+\s+days?\b|\b(?:last|past|previous)\s+week\b|"
            r"\b(?:snapshot|all blocks|block progress|phase-wise)\b",
            current,
            re.IGNORECASE,
        ):
            selected.add("p6_get_block_period_progress")
        if re.search(
            r"\b(?:daily|day[ -]by[ -]day)\b.{0,30}\b(?:progress|completion|trend)\b|"
            r"\b(?:progress|completion)\s+trend\b",
            current,
            re.IGNORECASE,
        ):
            selected.add("p6_get_daily_completion_trend")
        if re.search(r"\b(?:activity|activities)\b", current, re.IGNORECASE):
            selected.update({"p6_get_activities", "p6_get_activity_status_breakdown"})
        if re.search(r"\b(?:critical|critical path|float)\b", current, re.IGNORECASE):
            selected.add("p6_get_critical_activities")
        if re.search(r"\b(?:delay|delays|delayed|late|slip|behind)\b", current, re.IGNORECASE):
            selected.update({"p6_get_delayed_activities", "p6_get_critical_activities"})
        if re.search(r"\b(?:health|health score|project health)\b", current, re.IGNORECASE):
            selected.add("get_project_kpis")
        if re.search(r"\b(?:all projects|how many projects|portfolio)\b", current, re.IGNORECASE):
            selected.add("p6_list_all_projects")
        if re.search(
            r"\b(?:this|current|next|target) (?:month|year)\b|\b(?:monthly|yearly|annual)\b|"
            r"\bscheduled to finish\b|\bdue (?:in|this|next)\b|"
            r"\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\b|"
            r"\b20\d{2}\b",
            current,
            re.IGNORECASE,
        ) and re.search(r"\b(?:activity|activities|finish|finishes|due|completion)\b", current, re.IGNORECASE):
            selected.add("sim_forecast_activity_finishes")

    if "sap" in current_domains:
        intent_parts.append("procurement")
        selected.add("sap_get_po_summary")
        if re.search(r"\b(?:material|delivery|delivered|pending|gap|bottleneck)\b", current, re.IGNORECASE):
            selected.add("sap_get_material_gaps")
        if re.search(r"\b(?:vendor|supplier)\b", current, re.IGNORECASE):
            selected.add("sap_get_vendor_performance")
        if re.search(r"\b(?:inventory|stock)\b", current, re.IGNORECASE):
            selected.add("sap_get_inventory")
        if re.search(r"\b(?:consumption|consumed|issued|returned)\b", current, re.IGNORECASE):
            selected.add("sap_get_consumption")

    if "transmission" in current_domains:
        intent_parts.append("transmission")
        selected.update({"tc_get_project_lines", "tc_search_lines"})
        if re.search(r"\b(?:risk|delay|delays|delayed|late|slip|behind)\b", current, re.IGNORECASE):
            selected.add("tc_get_at_risk_lines")
        if re.search(r"\b(?:network|portfolio|substation|overview|summary|total|how many)\b", current, re.IGNORECASE):
            selected.add("tc_get_network_summary")

    if "portfolio" in current_domains:
        intent_parts.append("portfolio")
        if re.search(r"\b(?:portfolio|all projects|which projects|projects are)\b", current, re.IGNORECASE):
            selected.discard(RESOLVER)
        if re.search(r"\b(?:notification|notifications|alert|alerts)\b", current, re.IGNORECASE):
            selected.add("portfolio_get_notifications")
        if re.search(r"\b(?:riskiest|rank|ranking)\b", current, re.IGNORECASE) or (
            "risk" not in current_domains
            and re.search(r"\brisk\b", current, re.IGNORECASE)
        ):
            selected.add("portfolio_get_riskiest_projects")
        if not current_domains.intersection({"capacity", "quality", "risk"}) and re.search(
            r"\b(?:all projects|how many projects|status|progress|overview)\b",
            current,
            re.IGNORECASE,
        ):
            selected.add("p6_list_all_projects")
        if re.search(
            r"\b(?:milestone|milestones)\b.{0,30}\b(?:risk|miss|missing|slip|late|delay)\b|"
            r"\b(?:risk|miss|missing|slip|late|delay)\w*\b.{0,30}\b(?:milestone|milestones)\b",
            current,
            re.IGNORECASE,
        ):
            selected.add("p6_get_portfolio_milestone_risks")

    if "capacity" in current_domains:
        intent_parts.append("capacity")
        if "portfolio" in current_domains or re.search(
            r"\b(?:portfolio|all projects|overview|total)\b", current, re.IGNORECASE
        ):
            selected.add("capacity_get_portfolio_overview")
        else:
            selected.add("capacity_get_project_status")

    if "quality" in current_domains:
        intent_parts.append("quality")
        if re.search(r"\b(?:contractor|scorecard)\b", current, re.IGNORECASE):
            selected.add("quality_get_contractor_scorecard")
        elif "portfolio" in current_domains or re.search(
            r"\b(?:all projects|portfolio|overview|total|trend)\b", current, re.IGNORECASE
        ):
            selected.add("quality_get_portfolio_overview")
        else:
            selected.add("quality_get_project_status")

    if "risk" in current_domains:
        intent_parts.append("risk")
        selected.add("risk_get_metric")

    if "simulation" in current_domains:
        intent_parts.append("simulation")
        selected.add("p6_get_project_summary")
        period_activity_forecast = bool(
            re.search(r"\b(?:activity|activities)\b", current, re.IGNORECASE)
            and re.search(
                r"\b(?:month|monthly|year|yearly|annual|january|february|march|april|may|june|july|august|"
                r"september|october|november|december)\b|\b20\d{2}\b",
                current,
                re.IGNORECASE,
            )
        )
        if period_activity_forecast:
            selected.add("sim_forecast_activity_finishes")
        elif re.search(r"\b(?:forecast|predict|projection|finish|completion|on track|slip)\b", current, re.IGNORECASE):
            selected.add("sim_forecast_completion")
        if re.search(r"\b(?:productivity|production rate)\b", current, re.IGNORECASE):
            selected.add("sim_get_activity_productivity")
        if re.search(r"\b(?:what[ -]if|scenario|simulate|manpower|accelerat)\w*\b", current, re.IGNORECASE):
            selected.update({"sim_project_duration_what_if", "sim_get_activity_productivity"})
        if re.search(r"\bmonsoon\b", current, re.IGNORECASE):
            selected.update({"sim_monsoon_impact", "sim_get_activity_productivity"})
        if re.search(r"\bbottleneck\w*\b", current, re.IGNORECASE):
            selected.update({"sim_material_bottlenecks", "sap_get_material_gaps", "sap_get_inventory"})

    if "report" in current_domains:
        intent_parts.append("report")
        explicit_preview = bool(re.search(
            r"\b(?:preview|review (?:the )?(?:scope|outline|sections)|show (?:me )?(?:the )?(?:scope|outline))\b",
            current,
            re.IGNORECASE,
        ))
        comparison_report = bool(re.search(
            r"\b(?:compare|comparison|versus|vs\.?)\b", current, re.IGNORECASE
        )) or bool(is_contextual_follow_up and re.search(
            r"\b(?:project comparison|compare|comparison|versus|vs\.?)\b", prior, re.IGNORECASE
        ))
        if comparison_report:
            selected.discard("report_preview_project_progress")
            selected.discard("report_generate_project_progress")
            selected.add(
                "report_preview_project_comparison"
                if explicit_preview else "report_generate_project_comparison"
            )
        elif "portfolio" in current_domains:
            selected.discard(RESOLVER)
            selected.add(
                "report_preview_portfolio_progress"
                if explicit_preview else "report_generate_portfolio_progress"
            )
        else:
            selected.add(
                "report_preview_project_progress"
                if explicit_preview else "report_generate_project_progress"
            )

    if "visualization" in current_domains:
        intent_parts.append("visualization")
        selected.add("render_chart")

    selected &= available_set
    ordered = _ordered_names(selected, available)
    if not ordered:
        return ToolRoute(non_health_tools, ("all",), "routing_fallback", True, False)
    required_evidence = tuple(
        name
        for name in ("p6_get_block_period_progress",)
        if name in selected
    )
    return ToolRoute(
        ordered,
        tuple(sorted(current_domains)),
        "+".join(intent_parts) or "operational",
        True,
        len(ordered) == len(available),
        required_evidence,
    )
