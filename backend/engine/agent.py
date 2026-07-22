"""
Akasha Engine — ReAct Agent Loop (Deep Analysis Mode)

This module implements a true ReAct (Reasoning and Acting) agent loop.
Instead of gathering all data upfront, it provides the LLM with a set of tools
and lets the LLM dynamically decide which tools to call, read the results, and
reason through complex multi-step queries.
"""

import json
import logging
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, ValidationError, validator
from engine.contracts import UserScope
from engine.project_resolver import resolve_project
from engine.security import (
    public_dev_scope,
    scope_allows_domain,
    scope_allows_portfolio,
    scope_allows_project,
    unauthorized_tool_envelope,
)

from engine.tools.p6_tools import (
    p6_get_project_summary, p6_list_all_projects,
    p6_get_critical_activities, p6_get_delayed_activities,
    p6_get_activity_status_breakdown, p6_get_pending_activities,
    p6_get_block_status, p6_get_wbs_tree
)
from engine.tools.sap_tools import (
    sap_get_po_summary, sap_get_material_gaps,
    sap_get_vendor_performance, sap_get_inventory,
    sap_get_consumption
)
from engine.tools.tc_tools import tc_get_project_lines, tc_get_at_risk_lines, tc_get_network_summary
from engine.tools.portfolio_tools import portfolio_resolve_project_id, portfolio_get_riskiest_projects, portfolio_get_notifications
from engine.tools.simulation_tools import (
    sim_get_activity_productivity, sim_project_duration_what_if,
    sim_monsoon_impact, sim_material_bottlenecks
)

logger = logging.getLogger(__name__)


def _is_current_project_status_question(message: str) -> bool:
    text = message.lower()
    return (
        "status" in text
        and "project" in text
        and any(term in text for term in ("current", "give me", "show me", "what is", "what's"))
    )


def _current_project_status_response(
    db: Session,
    message: str,
    user_scope: UserScope,
) -> tuple[str, list[str], list[dict]] | None:
    if not _is_current_project_status_question(message):
        return None

    resolution = resolve_project(db, None, message=message)
    if resolution.status != "resolved" or not resolution.project_ids:
        return None

    project_id = resolution.project_ids[0]
    tool_results: list[dict] = []
    tools_used: list[str] = []

    for tool_name, args in (
        ("portfolio_resolve_project_id", {"name": message}),
        ("p6_get_project_summary", {"project_id": project_id}),
        ("sap_get_po_summary", {"project_id": project_id}),
        ("tc_get_project_lines", {"project_id": project_id}),
    ):
        result = parse_tool_result(execute_tool(db, tool_name, args, user_scope=user_scope))
        tool_results.append({"tool_name": tool_name, "arguments": args, **result})
        tools_used.append(tool_name)
        if result.get("status") == "unauthorized":
            return result.get("error") or "You are not authorized to access this project.", tools_used, tool_results

    p6 = _tool_data(tool_results, "p6_get_project_summary")
    if not p6:
        return None

    sap = _tool_data(tool_results, "sap_get_po_summary") or {}
    tc = _tool_data(tool_results, "tc_get_project_lines") or {}
    return _format_project_status_answer(p6, sap, tc), tools_used, tool_results


def _tool_data(tool_results: list[dict], tool_name: str) -> dict | None:
    for result in tool_results:
        if result.get("tool_name") == tool_name and isinstance(result.get("data"), dict):
            return result["data"]
    return None


def _fmt_date(value: str | None) -> str:
    if not value:
        return "not available"
    try:
        from datetime import datetime
        return datetime.fromisoformat(str(value)).strftime("%d %b %Y")
    except Exception:
        return str(value)


def _fmt_num(value, suffix: str = "") -> str:
    if value is None:
        return "not available"
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return f"{value}{suffix}"


def _format_project_status_answer(p6: dict, sap: dict, tc: dict) -> str:
    name = p6.get("project_name") or p6.get("name") or "This project"
    status = p6.get("schedule_status") or p6.get("status") or "Unknown"
    reason = p6.get("schedule_status_reason") or "No schedule reason was available."

    lines = [
        f"**{name} is {status}.** {reason}",
        "",
        "**Schedule Snapshot**",
        f"- Project state: **{p6.get('status') or 'not available'}**",
        f"- Progress: **{_fmt_num(p6.get('progress_percent'), '%')}**",
        f"- Baseline finish: **{_fmt_date(p6.get('baseline_finish'))}**",
        f"- Projected finish: **{_fmt_date(p6.get('projected_finish') or p6.get('scheduled_finish') or p6.get('finish_date'))}**",
        f"- Baseline variance: **{_fmt_num(p6.get('baseline_variance_days'), ' days')}**",
        "",
        "**Execution Position**",
        f"- Activities: **{_fmt_num(p6.get('activity_count'))}** total, **{_fmt_num(p6.get('completed_activities'))}** completed, **{_fmt_num(p6.get('in_progress_activities'))}** in progress, **{_fmt_num(p6.get('not_started_activities'))}** not started, **{_fmt_num(p6.get('pending_activities'))}** pending",
        f"- Delayed activities vs baseline: **{_fmt_num(p6.get('delayed_activity_count'))}** total, including **{_fmt_num(p6.get('delayed_pending_activity_count'))}** pending and **{_fmt_num(p6.get('delayed_completed_activity_count'))}** completed; maximum activity drift: **{_fmt_num(p6.get('max_activity_drift_days'), ' days')}**",
        f"- Critical activities: **{_fmt_num(p6.get('critical_activity_count'))}**",
    ]

    sap_has_data = sap.get("has_data") is True
    tc_has_data = tc.get("has_data") is True
    if sap_has_data or tc_has_data:
        lines.extend(["", "**Cross-Domain Signals**"])
    if sap_has_data:
        summary = sap.get("summary") or {}
        lines.append(
            f"- Procurement: **{_fmt_num(summary.get('fulfillment_pct'), '%')}** fulfilled; "
            f"pending quantity **{_fmt_num(summary.get('total_pending_qty'))}**"
        )
    if tc_has_data:
        lines.append(
            f"- Transmission: **{_fmt_num(tc.get('total_lines'))}** lines, "
            f"**{_fmt_num(tc.get('delayed'))}** delayed"
        )

    data_gaps = []
    if not sap_has_data:
        data_gaps.append("SAP procurement is not mapped or has no records for this project")
    if not tc_has_data:
        data_gaps.append("TC transmission data is not mapped or has no lines for this project")
    if data_gaps:
        lines.extend(["", "**Data Gaps**"])
        lines.extend(f"- {gap}." for gap in data_gaps)

    lines.extend([
        "",
        "**Management Review**",
        f"- Review the recovery plan for the **{_fmt_num(p6.get('delayed_pending_activity_count'))} delayed pending activities**, starting with the **{_fmt_num(p6.get('critical_activity_count'))} critical activities**.",
        f"- Validate the drivers behind the **{_fmt_num(p6.get('baseline_variance_days'), '-day')} baseline slip** and assign owners by block/WBS.",
    ])
    if data_gaps:
        lines.append("- Confirm whether the SAP/TC gaps are true absence of data or missing project mappings before treating those areas as healthy.")

    return "\n".join(lines)

# --- Tool Schemas for the LLM ---
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "portfolio_resolve_project_id",
            "description": "Resolve a fuzzy project name, SPV name, or P6 name to the canonical project_id AND project_name. ALWAYS use this first if you only have a name. Returns project_id, project_name, p6_name, spv_name, category, and capacity.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "The name of the project to search for."
                    }
                },
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "portfolio_get_riskiest_projects",
            "description": "Get a list of the riskiest projects in the entire portfolio. Returns a dictionary containing the total number of projects in the portfolio and the requested top N riskiest projects.",
            "parameters": {
                "type": "object",
                "properties": {
                    "top_n": {
                        "type": "integer",
                        "description": "Number of projects to return (e.g., 5)."
                    }
                },
                "required": ["top_n"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "p6_get_project_summary",
            "description": "Get Primavera P6 schedule data for a specific project_id (SPI, CPI, variances, float).",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "The canonical project_id (NOT the name)."
                    }
                },
                "required": ["project_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "sap_get_po_summary",
            "description": "Get SAP R/3 procurement data (materials, vendors, fulfillment %) for a specific project_id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "The canonical project_id."
                    }
                },
                "required": ["project_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "tc_get_project_lines",
            "description": "Get Transmission Connectivity (TC) data (network edges, readiness) for a specific project_id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "The canonical project_id."
                    }
                },
                "required": ["project_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "portfolio_get_notifications",
            "description": "Get the user's latest system notifications and alerts, including AI suggestions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Number of notifications to return (default 10)."
                    },
                    "category": {
                        "type": "string",
                        "description": "Filter by category (e.g. 'All', 'Schedule', 'Procurement', 'Transmission'). Default is 'All'."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "tc_get_at_risk_lines",
            "description": "Get all transmission lines at risk or delayed across the entire portfolio.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days_threshold": {
                        "type": "integer",
                        "description": "Days delayed threshold. Default is 60."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "tc_get_network_summary",
            "description": "Get overall transmission network summary — total nodes and edges across the portfolio.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "p6_list_all_projects",
            "description": "Get the total count of all active projects in the portfolio and their core metrics. Returns a dictionary with 'total_projects' and 'projects' list.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "p6_get_critical_activities",
            "description": "Get activities on the critical path (total_float <= 0) for a project. Returns activity names, drift days from baseline, and completion %.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "The canonical project_id."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max activities to return (default 20)."
                    }
                },
                "required": ["project_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "p6_get_delayed_activities",
            "description": "Get activities behind schedule — finish date drifted from baseline. Returns drift_days, activity name, forecast finish vs baseline.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "The canonical project_id."
                    },
                    "min_drift_days": {
                        "type": "integer",
                        "description": "Minimum days of drift to include (default 7)."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max activities to return (default 20)."
                    }
                },
                "required": ["project_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "p6_get_activity_status_breakdown",
            "description": "Get activity count breakdown by status (Completed, In Progress, Not Started) for a project.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "The canonical project_id."
                    }
                },
                "required": ["project_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "p6_get_pending_activities",
            "description": "Get unfinished P6 activities for a project. Pending means status is Not Started or In Progress; this is not the same as delayed-vs-baseline.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "The canonical project_id."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max activities to return (default 50)."
                    }
                },
                "required": ["project_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "p6_get_block_status",
            "description": "Get Block/WTG COD and Trial Run status for a project. Pending blocks are Blocks/WTGs where COD is not completed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "The canonical project_id."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max blocks to return (default 50)."
                    }
                },
                "required": ["project_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "sap_get_material_gaps",
            "description": "Get materials with pending deliveries sorted by gap severity. Shows material name, ordered qty, delivered qty, pending qty, and gap percentage.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "The canonical project_id."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max materials to return (default 15)."
                    }
                },
                "required": ["project_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "sap_get_vendor_performance",
            "description": "Get vendor delivery performance — ordered vs delivered vs pending per vendor. Use for vendor risk and payment queries.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "The canonical project_id."
                    }
                },
                "required": ["project_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "sap_get_inventory",
            "description": "Get current material inventory (stock on hand) for a project — total items, quantities, and value.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "The canonical project_id."
                    }
                },
                "required": ["project_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "sap_get_consumption",
            "description": "Get material consumption data (MB51) — issued qty, returned qty, net consumed for a project.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "The canonical project_id."
                    }
                },
                "required": ["project_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "sim_get_activity_productivity",
            "description": "Derives real-world productivity metrics (avg days, avg manpower per block) for a specific activity type based on COMPLETED blocks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "The canonical project_id."
                    },
                    "activity_keyword": {
                        "type": "string",
                        "description": "Keyword like 'Module Installation', 'MMS', 'Piling', 'WTG'."
                    }
                },
                "required": ["project_id", "activity_keyword"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "sim_project_duration_what_if",
            "description": "Simulates future duration for remaining blocks of an activity, optionally applying a manpower multiplier (e.g., 1.2 for +20%).",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "The canonical project_id."
                    },
                    "activity_keyword": {
                        "type": "string",
                        "description": "Keyword like 'Module Installation', 'MMS', 'Piling'."
                    },
                    "manpower_multiplier": {
                        "type": "number",
                        "description": "Multiplier for manpower (e.g., 1.1 for 10% increase, 0.8 for 20% decrease). Default is 1.0."
                    }
                },
                "required": ["project_id", "activity_keyword"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "sim_monsoon_impact",
            "description": "Calculates historical slowdown factors for an activity executed during monsoon months (Jul-Sep).",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "The canonical project_id."
                    },
                    "activity_keyword": {
                        "type": "string",
                        "description": "Keyword like 'Foundation', 'Trenching'."
                    }
                },
                "required": ["project_id", "activity_keyword"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "sim_material_bottlenecks",
            "description": "Identifies potential material bottlenecks by cross-referencing remaining activity scope with inventory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "The canonical project_id."
                    },
                    "activity_keyword": {
                        "type": "string",
                        "description": "Keyword for the activity to check."
                    }
                },
                "required": ["project_id", "activity_keyword"]
            }
        }
    }
]


class _ToolArgs(BaseModel):
    class Config:
        extra = "forbid"


class _ProjectToolArgs(_ToolArgs):
    project_id: str

    @validator("project_id")
    def project_id_must_not_be_blank(cls, value: str) -> str:
        value = str(value).strip()
        if not value:
            raise ValueError("project_id is required")
        return value


class _ProjectLimitToolArgs(_ProjectToolArgs):
    limit: int = Field(default=20, ge=1, le=50)


class _DelayedActivitiesToolArgs(_ProjectToolArgs):
    min_drift_days: int = Field(default=7, ge=0, le=3650)
    limit: int = Field(default=20, ge=1, le=50)


class _ProjectActivityKeywordToolArgs(_ProjectToolArgs):
    activity_keyword: str

    @validator("activity_keyword")
    def activity_keyword_must_not_be_blank(cls, value: str) -> str:
        value = str(value).strip()
        if not value:
            raise ValueError("activity_keyword is required")
        return value


class _ProjectDurationWhatIfToolArgs(_ProjectActivityKeywordToolArgs):
    manpower_multiplier: float = Field(default=1.0, gt=0, le=3)


class _ResolveProjectToolArgs(_ToolArgs):
    name: str

    @validator("name")
    def name_must_not_be_blank(cls, value: str) -> str:
        value = str(value).strip()
        if not value:
            raise ValueError("name is required")
        return value


class _RiskiestProjectsToolArgs(_ToolArgs):
    top_n: int = Field(default=5, ge=1, le=20)


class _NotificationsToolArgs(_ToolArgs):
    limit: int = Field(default=10, ge=1, le=50)
    category: str = "All"


class _AtRiskLinesToolArgs(_ToolArgs):
    days_threshold: int = Field(default=60, ge=0, le=3650)
    limit: int = Field(default=15, ge=1, le=50)


class _NoArgs(_ToolArgs):
    pass


_TOOL_INPUT_MODELS: dict[str, type[BaseModel]] = {
    "portfolio_resolve_project_id": _ResolveProjectToolArgs,
    "portfolio_get_riskiest_projects": _RiskiestProjectsToolArgs,
    "p6_get_project_summary": _ProjectToolArgs,
    "sap_get_po_summary": _ProjectToolArgs,
    "tc_get_project_lines": _ProjectToolArgs,
    "portfolio_get_notifications": _NotificationsToolArgs,
    "tc_get_at_risk_lines": _AtRiskLinesToolArgs,
    "tc_get_network_summary": _NoArgs,
    "p6_list_all_projects": _NoArgs,
    "p6_get_critical_activities": _ProjectLimitToolArgs,
    "p6_get_delayed_activities": _DelayedActivitiesToolArgs,
    "p6_get_activity_status_breakdown": _ProjectToolArgs,
    "p6_get_pending_activities": _ProjectLimitToolArgs,
    "p6_get_block_status": _ProjectLimitToolArgs,
    "sap_get_material_gaps": _ProjectLimitToolArgs,
    "sap_get_vendor_performance": _ProjectToolArgs,
    "sap_get_inventory": _ProjectToolArgs,
    "sap_get_consumption": _ProjectToolArgs,
    "sim_get_activity_productivity": _ProjectActivityKeywordToolArgs,
    "sim_project_duration_what_if": _ProjectDurationWhatIfToolArgs,
    "sim_monsoon_impact": _ProjectActivityKeywordToolArgs,
    "sim_material_bottlenecks": _ProjectActivityKeywordToolArgs,
}


def execute_tool(db: Session, name: str, kwargs: dict, user_scope: UserScope | None = None) -> str:
    """Safely execute the requested tool and return a result envelope."""
    user_scope = user_scope or public_dev_scope()
    validation = _validate_tool_arguments(name, kwargs)
    if validation.get("error"):
        return json.dumps(validation)
    kwargs = validation["arguments"]

    authorization_error = _authorize_tool_call(name, kwargs, user_scope)
    if authorization_error:
        return json.dumps(authorization_error)

    try:
        if name == "portfolio_resolve_project_id":
            res = portfolio_resolve_project_id(db, kwargs.get("name", ""))
            if res and not scope_allows_project(user_scope, res.get("project_id")):
                return json.dumps(unauthorized_tool_envelope(
                    name,
                    reason="Project resolution result is outside the user's project scope.",
                    project_id=res.get("project_id"),
                ))
        elif name == "portfolio_get_riskiest_projects":
            res = portfolio_get_riskiest_projects(db, kwargs.get("top_n", 5))
        elif name == "p6_get_project_summary":
            res = p6_get_project_summary(db, kwargs.get("project_id"))
        elif name == "sap_get_po_summary":
            res = sap_get_po_summary(db, kwargs.get("project_id"))
        elif name == "tc_get_project_lines":
            res = tc_get_project_lines(db, kwargs.get("project_id"))
        elif name == "tc_get_at_risk_lines":
            res = tc_get_at_risk_lines(db, kwargs.get("days_threshold", 60), kwargs.get("limit", 15))
        elif name == "tc_get_network_summary":
            res = tc_get_network_summary(db)
        elif name == "p6_list_all_projects":
            res = p6_list_all_projects(db)
        elif name == "portfolio_get_notifications":
            res = portfolio_get_notifications(db, kwargs.get("limit", 10), kwargs.get("category", "All"))
        elif name == "p6_get_critical_activities":
            res = p6_get_critical_activities(db, kwargs.get("project_id"), kwargs.get("limit", 20))
        elif name == "p6_get_delayed_activities":
            res = p6_get_delayed_activities(db, kwargs.get("project_id"), kwargs.get("min_drift_days", 7), kwargs.get("limit", 20))
        elif name == "p6_get_activity_status_breakdown":
            res = p6_get_activity_status_breakdown(db, kwargs.get("project_id"))
        elif name == "p6_get_pending_activities":
            res = p6_get_pending_activities(db, kwargs.get("project_id"), kwargs.get("limit", 50))
        elif name == "p6_get_block_status":
            res = p6_get_block_status(db, kwargs.get("project_id"), kwargs.get("limit", 50))
        elif name == "sap_get_material_gaps":
            res = sap_get_material_gaps(db, kwargs.get("project_id"), kwargs.get("limit", 15))
        elif name == "sap_get_vendor_performance":
            res = sap_get_vendor_performance(db, kwargs.get("project_id"))
        elif name == "sap_get_inventory":
            res = sap_get_inventory(db, kwargs.get("project_id"))
        elif name == "sap_get_consumption":
            res = sap_get_consumption(db, kwargs.get("project_id"))
        elif name == "sim_get_activity_productivity":
            res = sim_get_activity_productivity(db, kwargs.get("project_id"), kwargs.get("activity_keyword"))
        elif name == "sim_project_duration_what_if":
            res = sim_project_duration_what_if(db, kwargs.get("project_id"), kwargs.get("activity_keyword"), kwargs.get("manpower_multiplier", 1.0))
        elif name == "sim_monsoon_impact":
            res = sim_monsoon_impact(db, kwargs.get("project_id"), kwargs.get("activity_keyword"))
        elif name == "sim_material_bottlenecks":
            res = sim_material_bottlenecks(db, kwargs.get("project_id"), kwargs.get("activity_keyword"))
        else:
            return json.dumps({
                "status": "error",
                "data": None,
                "evidence": [],
                "warnings": [],
                "error": f"Unknown tool: {name}",
            })
        return json.dumps(_tool_envelope(name, res, kwargs), default=str)
    except Exception as e:
        logger.error(f"Tool {name} failed: {e}")
        return json.dumps({
            "status": "error",
            "data": None,
            "evidence": [],
            "warnings": [],
            "error": "Tool execution failed.",
        })


def _validate_tool_arguments(tool_name: str, kwargs: dict | None) -> dict:
    model = _TOOL_INPUT_MODELS.get(tool_name)
    if model is None:
        return {
            "status": "error",
            "data": None,
            "evidence": [],
            "warnings": [],
            "error": f"Unknown tool: {tool_name}",
        }

    try:
        parsed = model(**(kwargs or {}))
    except ValidationError as exc:
        return {
            "status": "error",
            "data": None,
            "evidence": [],
            "warnings": [f"invalid_tool_arguments: {_validation_summary(exc)}"],
            "error": f"Invalid tool arguments for {tool_name}.",
        }

    return {"arguments": _model_dump(parsed)}


def _model_dump(model: BaseModel) -> dict:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def _validation_summary(exc: ValidationError) -> str:
    parts = []
    for error in exc.errors()[:3]:
        loc = ".".join(str(item) for item in error.get("loc", [])) or "arguments"
        parts.append(f"{loc}: {error.get('msg', 'invalid')}")
    return "; ".join(parts)


def parse_tool_result(result_str: str) -> dict:
    """Parse a tool envelope without leaking raw parse errors to the agent runtime."""
    try:
        parsed = json.loads(result_str)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    return {
        "status": "error",
        "data": None,
        "evidence": [],
        "warnings": [],
        "error": "Tool returned an invalid result envelope.",
    }


def _tool_envelope(tool_name: str, data, kwargs: dict) -> dict:
    project_id = kwargs.get("project_id")
    source_system, source_type = _tool_source(tool_name)
    status = "success"
    if data is None or data == []:
        status = "not_found"
    elif isinstance(data, dict) and data.get("has_data") is False:
        status = "not_found"
    return {
        "status": status,
        "data": data,
        "evidence": [{
            "source_system": source_system,
            "source_type": source_type,
            "record_ids": [str(project_id)] if project_id else [],
            "project_id": project_id,
            "as_of": data.get("_synced_at") if isinstance(data, dict) else None,
            "retrieved_at": __import__("datetime").datetime.utcnow().isoformat(),
            "calculation": None,
            "calculation_version": None,
        }],
        "warnings": [],
        "error": None,
    }


def _tool_source(tool_name: str) -> tuple[str, str]:
    if tool_name.startswith("p6_"):
        if tool_name == "p6_get_block_status":
            return "P6", "p6_activity,p6_wbs_node"
        return "P6", "p6_project" if "project_summary" in tool_name or "list_all" in tool_name else "p6_activity"
    if tool_name.startswith("sap_"):
        return "SAP", "mt_poamount"
    if tool_name.startswith("tc_"):
        return "TC", "tc_network_edge"
    if tool_name.startswith("sim_"):
        return "Simulation", tool_name
    return "Portfolio", tool_name


def _authorize_tool_call(tool_name: str, kwargs: dict, user_scope: UserScope) -> dict | None:
    domain = _tool_domain(tool_name)
    project_id = kwargs.get("project_id")

    if domain and not scope_allows_domain(user_scope, domain):
        return unauthorized_tool_envelope(
            tool_name,
            reason=f"Role '{user_scope.role}' cannot access the {domain} domain.",
            project_id=project_id,
        )

    if project_id and not scope_allows_project(user_scope, str(project_id)):
        return unauthorized_tool_envelope(
            tool_name,
            reason="Requested project is outside the user's project scope.",
            project_id=str(project_id),
        )

    if _is_portfolio_tool(tool_name) and not scope_allows_portfolio(user_scope):
        return unauthorized_tool_envelope(
            tool_name,
            reason="Portfolio-wide tool access is not allowed for this user.",
            project_id=project_id,
        )

    return None


def _tool_domain(tool_name: str) -> str:
    if tool_name == "portfolio_resolve_project_id":
        return ""
    if tool_name.startswith("p6_"):
        return "p6"
    if tool_name.startswith("sap_"):
        return "sap"
    if tool_name.startswith("tc_"):
        return "tc"
    if tool_name.startswith("sim_"):
        return "simulation"
    return "portfolio"


def _is_portfolio_tool(tool_name: str) -> bool:
    return tool_name in {
        "portfolio_get_riskiest_projects",
        "portfolio_get_notifications",
        "p6_list_all_projects",
        "tc_get_at_risk_lines",
        "tc_get_network_summary",
    }


def analyze_image_context(base64_image: str, prompt: str) -> str:
    """Uses a vision model to extract data/context from an image to feed into the ReAct agent."""
    try:
        from engine.model_gateway import complete_text
        
        # Determine if base64 has a data URI prefix, if not add a default jpeg one
        image_url = base64_image if base64_image.startswith("data:image") else f"data:image/jpeg;base64,{base64_image}"
        
        vision_prompt = (
            "You are a highly analytical AI assistant acting as the eyes for an enterprise ReAct agent. "
            "The user has uploaded this image and asked the following question: " + prompt + "\n\n"
            "Please describe EVERYTHING in this image that is relevant to answering the user's prompt. "
            "Extract any numbers, chart data, metrics, project names, or schedule alerts visible. "
            "Provide a highly detailed factual extraction. Do not try to answer the question directly, just extract the facts from the image."
        )
        
        return complete_text(
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": vision_prompt},
                        {"type": "image_url", "image_url": {"url": image_url}}
                    ]
                }
            ],
            temperature=0.1,
            max_tokens=1024,
            vision=True,
        )
    except Exception as e:
        logger.error(f"Vision extraction failed: {e}")
        return f"Failed to extract image context: {str(e)}"


def run_deep_analysis_agent(
    db: Session,
    message: str,
    history: list,
    user_scope: UserScope | None = None,
) -> tuple[str, list, list[dict]]:
    """
    Run the ReAct loop until the agent decides to return a final answer.
    Returns: (final_response_string, list_of_tools_used, tool_result_envelopes)
    """
    from engine.model_gateway import chat_completion
    user_scope = user_scope or public_dev_scope()
    status_response = _current_project_status_response(db, message, user_scope)
    if status_response:
        return status_response

    # Initialize messages
    messages = [
        {
            "role": "system", 
            "content": (
                "You are Akasha AI Copilot, a Deep Analysis Agent for EPC projects. "
                "You have access to tools querying P6 (Schedule), SAP (Procurement), TC (Transmission), and Notifications. "
                "If a user asks about a project by name, ALWAYS call `portfolio_resolve_project_id` first to get the canonical ID and project name. "
                "If a user asks about alerts or notifications, call `portfolio_get_notifications`. "
                "Use the tools step-by-step to gather the data you need to answer the user's question. "
                "You may use read-only tools and validated simulations only; never perform or imply a business write action. "
                "Once you have enough data, provide the EXACT answer the user asked for.\n"
                "NOTE: Quantities in SAP are absolute units, not Megawatts (MW).\n"
                "CRITICAL RULES:\n"
                "1. If the user asks a general question (like 'what can you do?', 'who are you?', or 'hi'), be conversational, interactive, and friendly. Explain your capabilities clearly.\n"
                "2. When answering data questions, NEVER use templates or boilerplate. Every metric must come from the actual data you retrieved.\n"
                "3. Answer ONLY what the user asked regarding data. If they ask 'how many delayed lines?', give the count and list them.\n"
                "4. Use **bold** for key numbers/metrics. Use markdown tables when comparing multiple items.\n"
                "5. Do NOT add disclaimers or filler like 'Based on the provided data...' or 'Let me analyze...'.\n"
                "6. Write like a senior analyst speaking to the CEO — direct, factual, and insightful.\n"
                "7. When discussing DELAYED TRANSMISSION LINES, always show 'days delayed' and 'affected projects' instead of schedule 'float'. Do not mention float unless specifically asked about P6 schedules.\n"
                "8. ALWAYS refer to projects by their project_name (human-readable name), NEVER by project_id or internal IDs in your final answer. The project_name field is always available in the tool results.\n"
                "9. All quantities (ordered, delivered, pending) are whole numbers — never show decimals like 47.0, always show 47. Durations are in integer hours.\n"
                "10. NEVER hardcode answers, guess, or hallucinate data. You MUST always use your tools to query the real database first before answering any project or data-related question.\n"
                "12. Recommendations must directly reference retrieved evidence such as delayed_activity_count, max_activity_drift_days, critical_activity_count, SAP gaps, or TC delays. If SAP/TC has no data, state that as a data coverage gap only; do not invent procurement or transmission recommendations.\n"
                "11. You are a powerful analytical engine. Do not just regurgitate data—provide analytics, summarize trends, identify risks, and calculate aggregations when the user asks for insights or analytics."
            )
        }
    ]
    messages.append({"role": "system", "content": _scope_instruction(user_scope)})
    
    # Append recent history
    for h in history[-6:]:
        r = h.get("role") or h.get("type", "user")
        if r == "bot": r = "assistant"
        messages.append({"role": r, "content": h.get("content", "")})
        
    messages.append({"role": "user", "content": message})
    
    max_loops = 8
    loop_count = 0
    tools_used = set()
    tool_results: list[dict] = []
    
    while loop_count < max_loops:
        loop_count += 1
        logger.info(f"Agent Loop {loop_count} starting...")
        
        response = chat_completion(
            messages,
            tools=TOOLS,
            tool_choice="auto",
            temperature=0.2,
            max_tokens=2048,
        )
        
        response_message = response.choices[0].message
        
        # If the LLM didn't call any tools, it means it has formulated a final answer.
        if not response_message.tool_calls:
            logger.info("Agent decided to return final answer.")
            return response_message.content, list(tools_used), tool_results
            
        # The LLM called one or more tools. We must append its message to history first.
        messages.append(response_message)
        
        for tool_call in response_message.tool_calls:
            tool_name = tool_call.function.name
            tools_used.add(tool_name)
            
            try:
                args = json.loads(tool_call.function.arguments)
                logger.info(f"Agent calling tool: {tool_name} with args: {args}")
            except Exception as e:
                logger.warning(f"Failed to parse tool args: {e}")
                args = {}
                
            # Execute the tool
            result_str = execute_tool(db, tool_name, args, user_scope=user_scope)
            tool_results.append({
                "tool_name": tool_name,
                "arguments": args,
                **parse_tool_result(result_str),
            })
            
            # Append the tool result to messages
            messages.append({
                "tool_call_id": tool_call.id,
                "role": "tool",
                "name": tool_name,
                "content": result_str,
            })
            
    logger.warning("Agent loop reached max iterations without final answer.")
    return "Deep analysis timed out. I was able to gather some data but could not synthesize a final answer in time. Try asking a more specific question.", list(tools_used), tool_results

def run_deep_analysis_agent_stream(
    db: Session,
    message: str,
    history: list,
    user_scope: UserScope | None = None,
):
    """
    Run the ReAct loop until the agent decides to return a final answer, then streams it.
    """
    from engine.model_gateway import chat_completion
    user_scope = user_scope or public_dev_scope()
    status_response = _current_project_status_response(db, message, user_scope)
    if status_response:
        content, tools_used, tool_results = status_response
        yield {"type": "tool_results", "tools": tools_used, "tool_results": tool_results}
        for idx in range(0, len(content), 80):
            yield content[idx:idx + 80]
        return
    
    # Initialize messages
    messages = [
        {
            "role": "system", 
            "content": (
                "You are Akasha AI Copilot, a Deep Analysis Agent for EPC projects. "
                "You have access to tools querying P6 (Schedule), SAP (Procurement), TC (Transmission), and Notifications. "
                "If a user asks about a project by name, ALWAYS call `portfolio_resolve_project_id` first to get the canonical ID and project name. "
                "If a user asks about alerts or notifications, call `portfolio_get_notifications`. "
                "Use the tools step-by-step to gather the data you need to answer the user's question. "
                "You may use read-only tools and validated simulations only; never perform or imply a business write action. "
                "Once you have enough data, provide a comprehensive, analytical final answer to the user in markdown. "
                "NOTE: Quantities in SAP are absolute units, not Megawatts (MW).\n"
                "CRITICAL TONE INSTRUCTIONS:\n"
                "- If the user asks a general question (like 'what can you do?', 'who are you?', or 'hi'), be conversational, interactive, and friendly. Explain your capabilities clearly.\n"
                "- When discussing data, write naturally like a senior human analyst reporting to leadership. Do not sound like a robotic chatbot.\n"
                "- AVOID all AI clichés (e.g., \"It is important to note,\" \"Furthermore,\" \"Delve,\" \"In conclusion\", \"Based on the provided data\").\n"
                "- Get straight to the point. Give the exact numbers requested.\n"
                "- Use bold text to highlight key metrics or variances to make it easy for humans to read.\n"
                "- When discussing DELAYED TRANSMISSION LINES, always show 'days delayed' and 'affected projects' instead of schedule 'float'. Do not mention float unless specifically asked about P6 schedules.\n"
                "- ALWAYS refer to projects by their project_name (human-readable name), NEVER by project_id or internal IDs in your final answer. The project_name field is always available in the tool results.\n"
                "- Recommendations must directly reference retrieved evidence such as delayed_activity_count, max_activity_drift_days, critical_activity_count, SAP gaps, or TC delays. If SAP/TC has no data, state that as a data coverage gap only; do not invent procurement or transmission recommendations.\n"
                "- All quantities (ordered, delivered, pending) are whole numbers — never show decimals like 47.0, always show 47. Durations are in integer hours."
            )
        }
    ]
    messages.append({"role": "system", "content": _scope_instruction(user_scope)})
    
    for h in history[-6:]:
        r = h.get("role") or h.get("type", "user")
        if r == "bot": r = "assistant"
        messages.append({"role": r, "content": h.get("content", "")})
        
    messages.append({"role": "user", "content": message})
    
    max_loops = 8
    loop_count = 0
    tools_used = set()
    tool_results: list[dict] = []
    
    while loop_count < max_loops:
        loop_count += 1
        
        response = chat_completion(
            messages,
            tools=TOOLS,
            tool_choice="auto",
            temperature=0.2,
            max_tokens=2048,
        )
        
        response_message = response.choices[0].message
        
        # If the LLM didn't call any tools, it means it has formulated a final answer.
        if not response_message.tool_calls:
            yield {"type": "tool_results", "tools": list(tools_used), "tool_results": tool_results}
            final_content = response_message.content or ""
            for idx in range(0, len(final_content), 80):
                yield final_content[idx:idx + 80]
            return
            
        messages.append(response_message)
        
        for tool_call in response_message.tool_calls:
            tool_name = tool_call.function.name
            tools_used.add(tool_name)
            
            try:
                args = json.loads(tool_call.function.arguments)
            except Exception:
                args = {}
                
            result_str = execute_tool(db, tool_name, args, user_scope=user_scope)
            tool_results.append({
                "tool_name": tool_name,
                "arguments": args,
                **parse_tool_result(result_str),
            })
            messages.append({
                "tool_call_id": tool_call.id,
                "role": "tool",
                "name": tool_name,
                "content": result_str,
            })
            
    yield {"type": "tool_results", "tools": list(tools_used), "tool_results": tool_results}
    yield "Deep analysis timed out. I was able to gather some data but could not synthesize a final answer in time. Try asking a more specific question."


def _scope_instruction(user_scope: UserScope) -> str:
    projects = ", ".join(user_scope.project_ids) if user_scope.project_ids else "none"
    domains = ", ".join(user_scope.domains) if user_scope.domains else "none"
    portfolio = "allowed" if user_scope.can_access_portfolio else "not allowed"
    return (
        "Authorization scope for this run: "
        f"role={user_scope.role}; projects={projects}; domains={domains}; "
        f"portfolio={portfolio}. Do not request tools outside this scope."
    )
