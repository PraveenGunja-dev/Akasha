"""
Akasha Engine — ReAct Agent Loop (Deep Analysis Mode)

This module implements a true ReAct (Reasoning and Acting) agent loop.
Instead of gathering all data upfront, it provides the LLM with a set of tools
and lets the LLM dynamically decide which tools to call, read the results, and
reason through complex multi-step queries.
"""

import json
import logging
import os
import time
from sqlalchemy.orm import Session
from sqlalchemy.orm import Session

from engine.observability import log_observability_event
from engine.model_provider import get_model_provider
from engine.openrouter_config import openrouter_extra_body

from engine.tools.p6_tools import (
    p6_get_project_summary, p6_list_all_projects,
    p6_get_critical_activities, p6_get_delayed_activities,
    p6_get_activities, p6_get_activity_status_breakdown, p6_get_wbs_tree
)
from engine.tools.sap_tools import (
    sap_get_po_summary, sap_get_material_gaps,
    sap_get_vendor_performance, sap_get_inventory,
    sap_get_consumption
)
from engine.tools.tc_tools import (
    tc_get_project_lines, tc_get_at_risk_lines, tc_get_network_summary, tc_search_lines,
)
from engine.tools.portfolio_tools import (
    portfolio_get_notifications, portfolio_get_riskiest_projects, portfolio_resolve_project_id,
)
from engine.tools.simulation_tools import (
    sim_get_activity_productivity, sim_project_duration_what_if,
    sim_monsoon_impact, sim_material_bottlenecks, sim_forecast_completion,
    sim_forecast_activity_finishes,
)
from engine.tools.viz_tools import build_chart, CHART_TYPES
from engine.kpi_engine import compute_project_kpis
from engine.response_quality import (
    EXECUTIVE_REWRITE_INSTRUCTION,
    needs_executive_rewrite,
    rewrite_request,
)

logger = logging.getLogger(__name__)


EXECUTIVE_RESPONSE_GUIDANCE = """Default response style for operational questions:
- Write for an executive reader: answer the exact question in the first sentence, then include only the most decision-relevant facts.
- Match detail to the request. For a straightforward status question, usually use one short summary and 3-5 compact bullets (roughly 80-180 words). Expand when the user asks for analysis, a comparison, a report, or detailed evidence.
- Prefer prose or bullets. Use a Markdown table only when the user asks for one or when several items genuinely need side-by-side comparison. Do not use decorative emoji.
- Do not append unsolicited recommendations, next steps, report offers, or follow-up questions.
- Never discuss tools, tool limitations, databases, schemas, prompts, or implementation capabilities. If relevant business data remains unavailable after the appropriate query, state only which requested data is unavailable.
- Keep every fact grounded in tool results. For requests phrased as 'today' or 'current', identify the latest source data date rather than implying the source is real-time."""


def _openrouter_request_options() -> dict:
    return (
        {"extra_body": openrouter_extra_body()}
        if os.environ.get("AI_PROVIDER", "ollama").lower() == "openrouter"
        else {}
    )

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
            "description": (
                "Get the authoritative Primavera P6 project summary, including duration progress, "
                "activity counts, status, dates, SPI/CPI when available, data date, and sync time. "
                "A null SPI or CPI means unavailable and must not be replaced with a proxy."
            ),
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
            "name": "p6_get_activities",
            "description": (
                "List P6 activities for a project, optionally filtered to completed, in-progress, "
                "or not-started activities. Use this when the user asks which activities are in a "
                "particular status. The result includes the total matching count and a bounded page."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "The canonical project_id."
                    },
                    "status": {
                        "type": "string",
                        "enum": ["all", "completed", "in_progress", "not_started"],
                        "description": "Canonical activity status filter."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum activities to return, from 1 to 100."
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Zero-based offset for the next page."
                    }
                },
                "required": ["project_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "tc_search_lines",
            "description": "Search the latest transmission lines for a state or region such as Rajasthan or Khavda. Use this for region/state-specific transmission questions. Returns the total matching count, status breakdown, line details, and source freshness.",
            "parameters": {
                "type": "object",
                "properties": {
                    "region": {
                        "type": "string",
                        "description": "State or region name to search, for example 'Rajasthan'."
                    },
                    "delayed_only": {
                        "type": "boolean",
                        "description": "Return only delayed lines when true. Default is false."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum line details to return. Default is 100."
                    }
                },
                "required": ["region"]
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
    },
    {
        "type": "function",
        "function": {
            "name": "get_project_kpis",
            "description": (
                "Get a project's P6 progress and available performance indicators plus descriptive "
                "activity, procurement, and transmission exposure. SPI, CPI, schedule classification, "
                "and health remain unavailable when their required source indicators are null; the tool "
                "does not manufacture proxy SPI/CPI values. Resolve the project name to project_id first."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "The canonical project_id (resolve the name first)."
                    }
                },
                "required": ["project_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "sim_forecast_completion",
            "description": (
                "Forecast WHEN a project will finish, from real P6 data. Compares P6's own scheduled "
                "finish vs the baseline plan AND an independent pace-based projection from actual "
                "progress since start, reconciles the two, lists milestones at risk of slipping, and "
                "returns a confidence level. This is a projection from existing data, not a guess — "
                "if the project is 0% complete it says so and returns the baseline plan only. "
                "USE THIS for forward-looking questions: 'when will X finish?', 'expected completion "
                "month', 'is it on track for commissioning?', 'which milestones will slip?', "
                "'forecasted vs baseline completion', 'will it be delayed?'. "
                "Resolve the project name to project_id first."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "The canonical project_id (resolve the name first)."
                    }
                },
                "required": ["project_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "render_chart",
            "description": (
                "Render a data visualization (chart) for the user, shown inline in the chat. "
                "Call this when the user asks for a chart/graph/visual/plot, OR when a chart would communicate "
                "the answer better than text (comparisons, rankings, status distributions, delays). "
                "The chart's DATA is pulled from the database automatically — you only choose the chart_type and subject, "
                "you never supply the numbers. YOU decide which chart_type best fits the data; if the user explicitly "
                "asked for a specific chart, honor that. Use 'auto' to let the system pick the best fit. "
                "Resolve any project name to its canonical project_id (via portfolio_resolve_project_id) BEFORE calling this. "
                "After it succeeds, briefly describe in words what the chart shows. If it returns status 'no_data', "
                "tell the user plainly — do not describe a chart that wasn't drawn."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "chart_type": {
                        "type": "string",
                        "enum": ["auto", "activity_status", "project_comparison", "delayed_activities",
                                 "material_gaps", "vendor_performance", "sap_po_fulfillment",
                                 "transmission_status", "portfolio_risk"],
                        "description": (
                            "Which chart to draw. "
                            "activity_status=donut of one project's activities by status; "
                            "project_comparison=bar comparing % complete across 2+ projects; "
                            "delayed_activities=bar of one project's most-delayed activities; "
                            "material_gaps=bar of one project's pending material deliveries (ordered/delivered/pending); "
                            "vendor_performance=bar of ordered/delivered/pending per vendor; "
                            "sap_po_fulfillment=bar of SAP PO ordered/delivered/pending per material; "
                            "transmission_status=donut of transmission line status (project or portfolio); "
                            "portfolio_risk=bar of the riskiest projects; "
                            "auto=let the system choose based on subject and domain_hint."
                        )
                    },
                    "project_id": {
                        "type": "string",
                        "description": "Canonical project_id for a single-project chart. Omit for portfolio-wide charts."
                    },
                    "project_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Two or more canonical project_ids — required for project_comparison."
                    },
                    "domain_hint": {
                        "type": "string",
                        "description": "Optional topic hint (e.g. 'delay', 'material', 'vendor', 'transmission') to help chart_type='auto' choose."
                    }
                },
                "required": ["chart_type"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "sim_forecast_activity_finishes",
            "description": (
                "Forecast how many activities for one project are scheduled to finish in a target "
                "calendar month or year. USE THIS for questions such as 'how many activities this "
                "month?', 'what is scheduled to finish in August?', 'how many finish this year?', "
                "or an annual/monthly activity completion outlook. "
                "Returns the exact current P6 finish-date count, completed/remaining breakdown, "
                "pace-supported likely range, at-risk activities, historical adherence, confidence, "
                "schedule pressure, and source freshness. Use period='month' or period='year'. "
                "Omit target values for the current month or year."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "The canonical project_id (resolve the name first)."
                    },
                    "period": {
                        "type": "string",
                        "enum": ["month", "year"],
                        "description": "Forecast period. Defaults to 'month'."
                    },
                    "target_year": {
                        "type": "integer",
                        "description": "Four-digit target year. Omit for the current month/year."
                    },
                    "target_month": {
                        "type": "integer",
                        "description": "Target month number from 1 to 12. Use only with period='month'; omit both target values for the current month."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum forecast activity details to return. Default is 25."
                    }
                },
                "required": ["project_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "report_preview_project_progress",
            "description": (
                "Prepare a Project Progress Report preview for one project. Call this when the user "
                "asks to create or generate a project report. Show its scope, sources, missing data, "
                "and PDF/DOCX formats, then wait for explicit user confirmation."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "string", "description": "The canonical project_id."}
                },
                "required": ["project_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "report_generate_project_progress",
            "description": (
                "Synchronously generate PDF and DOCX files from a previously previewed Project "
                "Progress Report. Call only after the user explicitly confirms the preview, and pass "
                "the exact preview_token returned by the preview tool. Preserve returned download URLs."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "string", "description": "The canonical project_id."},
                    "preview_token": {"type": "string", "description": "Opaque token returned by the preview tool."}
                },
                "required": ["project_id", "preview_token"]
            }
        }
    }
]


def build_chart_result(db: Session, kwargs: dict):
    """Build a chart spec from real DB data and a compact confirmation for the LLM.

    Returns (spec_or_None, confirmation_json_str). The confirmation deliberately excludes
    the full ECharts option so the (large) chart JSON never re-enters the LLM's context —
    the model only learns that the chart was drawn, keeping it from trying to echo or
    fabricate chart values. The spec (when present) is what the streaming loop emits to the UI.
    """
    spec = build_chart(
        db,
        chart_type=kwargs.get("chart_type", "auto"),
        project_id=kwargs.get("project_id"),
        project_ids=kwargs.get("project_ids"),
        domain_hint=kwargs.get("domain_hint"),
    )
    if spec.get("no_data"):
        return None, json.dumps({"status": "no_data", "message": spec.get("message")})
    confirmation = json.dumps({
        "status": "chart_rendered",
        "chart_type": spec.get("chart_type"),
        "title": spec.get("title"),
        "data_points": spec.get("data_points"),
    })
    return spec, confirmation


def execute_tool(db: Session, name: str, kwargs: dict) -> str:
    """Safely execute the requested tool and return a JSON string result."""
    try:
        if name == "portfolio_resolve_project_id":
            res = portfolio_resolve_project_id(db, kwargs.get("name", ""))
            return json.dumps(res, default=str)
        
        elif name == "portfolio_get_riskiest_projects":
            res = portfolio_get_riskiest_projects(db, kwargs.get("top_n", 5))
            return json.dumps(res, default=str)

        elif name == "p6_get_project_summary":
            res = p6_get_project_summary(db, kwargs.get("project_id"))
            return json.dumps(res, default=str)
            
        elif name == "sap_get_po_summary":
            res = sap_get_po_summary(db, kwargs.get("project_id"))
            return json.dumps(res, default=str)
            
        elif name == "tc_get_project_lines":
            res = tc_get_project_lines(db, kwargs.get("project_id"))
            return json.dumps(res, default=str)

        elif name == "tc_search_lines":
            res = tc_search_lines(
                db,
                kwargs.get("region", ""),
                kwargs.get("delayed_only", False),
                kwargs.get("limit", 100),
            )
            return json.dumps(res, default=str)
            
        elif name == "tc_get_at_risk_lines":
            res = tc_get_at_risk_lines(
                db,
                kwargs.get("days_threshold", 60),
                kwargs.get("limit", 15),
                kwargs.get("region"),
            )
            return json.dumps(res, default=str)

        elif name == "tc_get_network_summary":
            res = tc_get_network_summary(db)
            return json.dumps(res, default=str)
            
        elif name == "p6_list_all_projects":
            res = p6_list_all_projects(db)
            return json.dumps(res, default=str)
            
        elif name == "portfolio_get_notifications":
            res = portfolio_get_notifications(db, kwargs.get("limit", 10), kwargs.get("category", "All"))
            return json.dumps(res, default=str)
        
        elif name == "p6_get_critical_activities":
            res = p6_get_critical_activities(db, kwargs.get("project_id"), kwargs.get("limit", 20))
            return json.dumps(res, default=str)
        
        elif name == "p6_get_delayed_activities":
            res = p6_get_delayed_activities(db, kwargs.get("project_id"), kwargs.get("min_drift_days", 7), kwargs.get("limit", 20))
            return json.dumps(res, default=str)
        
        elif name == "p6_get_activity_status_breakdown":
            res = p6_get_activity_status_breakdown(db, kwargs.get("project_id"))
            return json.dumps(res, default=str)

        elif name == "p6_get_activities":
            res = p6_get_activities(
                db,
                kwargs.get("project_id"),
                kwargs.get("status", "all"),
                kwargs.get("limit", 20),
                kwargs.get("offset", 0),
            )
            return json.dumps(res, default=str)
        
        elif name == "sap_get_material_gaps":
            res = sap_get_material_gaps(db, kwargs.get("project_id"), kwargs.get("limit", 15))
            return json.dumps(res, default=str)
        
        elif name == "sap_get_vendor_performance":
            res = sap_get_vendor_performance(db, kwargs.get("project_id"))
            return json.dumps(res, default=str)
        
        elif name == "sap_get_inventory":
            res = sap_get_inventory(db, kwargs.get("project_id"))
            return json.dumps(res, default=str)
        
        elif name == "sap_get_consumption":
            res = sap_get_consumption(db, kwargs.get("project_id"))
            return json.dumps(res, default=str)
            
        elif name == "sim_get_activity_productivity":
            res = sim_get_activity_productivity(db, kwargs.get("project_id"), kwargs.get("activity_keyword"))
            return json.dumps(res, default=str)
            
        elif name == "sim_project_duration_what_if":
            res = sim_project_duration_what_if(db, kwargs.get("project_id"), kwargs.get("activity_keyword"), kwargs.get("manpower_multiplier", 1.0))
            return json.dumps(res, default=str)
            
        elif name == "sim_monsoon_impact":
            res = sim_monsoon_impact(db, kwargs.get("project_id"), kwargs.get("activity_keyword"))
            return json.dumps(res, default=str)
            
        elif name == "sim_material_bottlenecks":
            res = sim_material_bottlenecks(db, kwargs.get("project_id"), kwargs.get("activity_keyword"))
            return json.dumps(res, default=str)

        elif name == "sim_forecast_completion":
            res = sim_forecast_completion(db, kwargs.get("project_id"))
            return json.dumps(res, default=str)

        elif name == "sim_forecast_activity_finishes":
            res = sim_forecast_activity_finishes(
                db,
                kwargs.get("project_id"),
                kwargs.get("period", "month"),
                kwargs.get("target_year"),
                kwargs.get("target_month"),
                kwargs.get("limit", 25),
            )
            return json.dumps(res, default=str)

        elif name == "get_project_kpis":
            res = compute_project_kpis(db, kwargs.get("project_id"))
            return json.dumps(res, default=str)

        elif name == "render_chart":
            # Non-stream path: build the chart so it doesn't error, but there's no channel to
            # deliver the spec here — the streaming loop is what actually emits the visualization.
            _spec, confirmation = build_chart_result(db, kwargs)
            return confirmation

        else:
            return json.dumps({"error": f"Unknown tool: {name}"})
    except Exception as e:
        logger.error("Tool %s failed (%s)", name, type(e).__name__)
        return json.dumps({"error": str(e)})


def _tool_result_status(result_str: str) -> str:
    """Reduce a tool result to a safe, bounded status for telemetry."""
    try:
        result = json.loads(result_str)
    except (TypeError, json.JSONDecodeError):
        return "success"

    if isinstance(result, dict):
        if "error" in result:
            return "error"
        if result.get("status") == "no_data":
            return "no_data"
    return "success"


def _get_llm_client(vision: bool = False):
    return get_model_provider(vision=vision)


def _apply_executive_quality_guard(provider, question: str, answer: str) -> str:
    if not needs_executive_rewrite(question, answer):
        return answer
    try:
        rewritten = provider.invoke(
            [
                {"role": "system", "content": EXECUTIVE_REWRITE_INSTRUCTION},
                {"role": "user", "content": rewrite_request(question, answer)},
            ],
            temperature=0.1,
            max_tokens=512,
        )
        candidate = (rewritten.content or "").strip()
        if candidate and not needs_executive_rewrite(question, candidate):
            return candidate
        logger.warning("Legacy executive answer rewrite did not satisfy quality guard")
    except Exception as exc:
        logger.warning("Legacy executive answer rewrite failed (%s)", type(exc).__name__)
    return answer


def analyze_image_context(
    base64_image: str,
    prompt: str,
    request_id: str | None = None,
    session_id: str | None = None,
) -> str:
    """Uses a vision model to extract data/context from an image to feed into the ReAct agent."""
    started_at = time.perf_counter()
    try:
        provider = _get_llm_client(vision=True)
        
        # Determine if base64 has a data URI prefix, if not add a default jpeg one
        image_url = base64_image if base64_image.startswith("data:image") else f"data:image/jpeg;base64,{base64_image}"
        
        vision_prompt = (
            "You are a highly analytical AI assistant acting as the eyes for an enterprise ReAct agent. "
            "The user has uploaded this image and asked the following question: " + prompt + "\n\n"
            "Please describe EVERYTHING in this image that is relevant to answering the user's prompt. "
            "Extract any numbers, chart data, metrics, project names, or schedule alerts visible. "
            "Provide a highly detailed factual extraction. Do not try to answer the question directly, just extract the facts from the image."
        )
        
        result = provider.invoke(
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
        return result.content or ""
    except Exception:
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        log_observability_event(
            logger,
            "vision_context_failed",
            request_id=request_id,
            session_id=session_id,
            elapsed_ms=elapsed_ms,
            response_intent="deep_analysis",
            tool_names=[],
            level=logging.ERROR,
            operation="vision_context_extraction",
            status="failure",
        )
        return "Image context extraction was unavailable."


def run_deep_analysis_agent(db: Session, message: str, history: list) -> tuple[str, list]:
    """
    Run the ReAct loop until the agent decides to return a final answer.
    Returns: (final_response_string, list_of_tools_used)
    """
    provider = _get_llm_client()
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
                "Once you have enough data, provide the EXACT answer the user asked for.\n"
                "NOTE: Quantities in SAP are absolute units, not Megawatts (MW).\n"
                "CRITICAL RULES:\n"
                "1. If the user asks a general question (like 'what can you do?', 'who are you?', or 'hi', 'hello'), DO NOT call any tools. Be conversational, interactive, and friendly. Explain your capabilities clearly.\n"
                "2. When answering data questions, NEVER use templates or boilerplate. Every metric must come from the actual data you retrieved.\n"
                "3. Answer ONLY what the user asked regarding data. If they ask 'how many delayed lines?', give the count and list them.\n"
                "4. Use **bold** for key numbers/metrics. Use markdown tables when comparing multiple items.\n"
                "5. Do NOT add disclaimers or filler like 'Based on the provided data...' or 'Let me analyze...'.\n"
                "6. Write like a senior analyst speaking to the CEO — direct, factual, and insightful.\n"
                "7. When discussing DELAYED TRANSMISSION LINES, always show 'days delayed' and 'affected projects' instead of schedule 'float'. Do not mention float unless specifically asked about P6 schedules.\n"
                "8. ALWAYS refer to projects by their project_name (human-readable name), NEVER by project_id or internal IDs in your final answer. The project_name field is always available in the tool results.\n"
                "9. All quantities (ordered, delivered, pending) are whole numbers — never show decimals like 47.0, always show 47. Durations are in integer hours.\n"
                "10. NEVER hardcode answers, guess, or hallucinate data. You MUST always use your tools to query the real database first before answering any project or data-related question.\n"
                "11. Provide analytics, trends, risks, and aggregations when the user asks for insights or analysis.\n\n"
                + EXECUTIVE_RESPONSE_GUIDANCE
            )
        }
    ]
    
    # Append recent history
    for h in history[-6:]:
        r = h.get("role") or h.get("type", "user")
        if r == "bot": r = "assistant"
        messages.append({"role": r, "content": h.get("content", "")})
        
    messages.append({"role": "user", "content": message})
    
    max_loops = 15
    loop_count = 0
    tools_used = set()
    
    while loop_count < max_loops:
        loop_count += 1
        logger.info(f"Agent Loop {loop_count} starting...")
        
        result = provider.invoke(
            messages,
            tools=TOOLS,
            tool_choice="auto",
            temperature=0.2,
            max_tokens=2048,
        )
        response_message = result.message
        
        # If the LLM didn't call any tools, it means it has formulated a final answer.
        if not response_message.tool_calls:
            logger.info("Agent decided to return final answer.")
            final_content = _apply_executive_quality_guard(
                provider,
                message,
                response_message.content or "",
            )
            return final_content, list(tools_used)
            
        # The LLM called one or more tools. We must append its message to history first.
        messages.append(response_message)
        
        for tool_call in response_message.tool_calls:
            tool_name = tool_call.function.name
            tools_used.add(tool_name)
            
            try:
                args = json.loads(tool_call.function.arguments)
                logger.info("Agent calling tool: %s", tool_name)
            except Exception as e:
                logger.warning(f"Failed to parse tool args: {e}")
                args = {}
                
            # Execute the tool
            result_str = execute_tool(db, tool_name, args)
            
            # Append the tool result to messages
            messages.append({
                "tool_call_id": tool_call.id,
                "role": "tool",
                "name": tool_name,
                "content": result_str,
            })
            
    logger.warning("Agent loop reached max iterations without final answer.")
    return "Deep analysis timed out. I was able to gather some data but could not synthesize a final answer in time. Try asking a more specific question.", list(tools_used)

def run_deep_analysis_agent_stream(
    db: Session,
    message: str,
    history: list,
    request_id: str | None = None,
    session_id: str | None = None,
    tool_names_out: list[str] | None = None,
):
    """
    Run the ReAct loop until the agent decides to return a final answer, then streams it.
    """
    provider = _get_llm_client()
    
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
                "Once you have enough data, answer the user's exact question from the retrieved facts. "
                "NOTE: Quantities in SAP are absolute units, not Megawatts (MW).\n"
                "CRITICAL TONE INSTRUCTIONS:\n"
                "- If the user asks a general question (like 'what can you do?', 'who are you?', or 'hi', 'hello'), DO NOT call any tools. Be conversational, interactive, and friendly. Explain your capabilities clearly.\n"
                "- When discussing data, write naturally like a senior human analyst reporting to leadership. Do not sound like a robotic chatbot.\n"
                "- AVOID all AI clichés (e.g., \"It is important to note,\" \"Furthermore,\" \"Delve,\" \"In conclusion\", \"Based on the provided data\").\n"
                "- Get straight to the point. Give the exact numbers requested.\n"
                "- Use bold text to highlight key metrics or variances to make it easy for humans to read.\n"
                "- When discussing DELAYED TRANSMISSION LINES, always show 'days delayed' and 'affected projects' instead of schedule 'float'. Do not mention float unless specifically asked about P6 schedules.\n"
                "- ALWAYS refer to projects by their project_name (human-readable name), NEVER by project_id or internal IDs in your final answer. The project_name field is always available in the tool results.\n"
                "- All quantities (ordered, delivered, pending) are whole numbers — never show decimals like 47.0, always show 47. Durations are in integer hours.\n"
                "VISUALIZATIONS:\n"
                "- You can draw charts with the `render_chart` tool; they appear inline in the chat. Use it when the user asks for a chart/graph/visual/plot, or when a chart communicates the answer better than text (comparisons, rankings, status distributions, delays).\n"
                "- YOU pick the chart_type that best fits the data. If the user explicitly asked for a specific format, use that. Use chart_type='auto' to let the system choose.\n"
                "- The chart's data is pulled from the database automatically — never invent chart values. Resolve the project name to its project_id first, then call render_chart.\n"
                "- After a chart renders, briefly say in words what it shows. If render_chart returns status 'no_data', tell the user plainly instead of describing a chart that wasn't drawn.\n"
                "FORECASTS / FUTURE QUESTIONS:\n"
                "- For forward-looking questions ('when will X finish?', 'expected completion month', 'will it slip?', 'on track for commissioning?', 'forecast vs baseline'), CALL `sim_forecast_completion`. Projecting a completion date from real progress data is expected of you — it is NOT guessing or hallucinating, so do not refuse these.\n"
                "- For monthly or yearly activity questions ('how many activities this month/year?', 'scheduled to finish in August', or a period finish outlook), CALL `sim_forecast_activity_finishes`. Lead with the exact P6 scheduled count, then briefly state the likely range, risk, confidence, and data date.\n"
                "- Report the forecast's dates, whether it's ahead/behind baseline, the confidence level, and its stated assumptions. If the tool says the project hasn't started, say the date is the planned baseline, not a forecast.\n"
                "- Only say you can't answer when NO tool can produce the number from data (e.g. external market prices, weather) — never for schedule/cost/progress projections your tools cover.\n"
                "SCHEDULE PERFORMANCE / KPIs:\n"
                "- For overall project progress and status, call `p6_get_project_summary`; duration_percent_complete is the authoritative P6 duration progress.\n"
                "- Completed activities / total activities is an activity-count ratio, not overall P6 progress. Label it separately if useful.\n"
                "- For broader project exposure, call `get_project_kpis`, but never replace null SPI/CPI with a calculated proxy or classify ahead/behind/health when the tool says the required indicator is unavailable.\n\n"
                + EXECUTIVE_RESPONSE_GUIDANCE
            )
        }
    ]

    for h in history[-6:]:
        r = h.get("role") or h.get("type", "user")
        if r == "bot": r = "assistant"
        messages.append({"role": r, "content": h.get("content", "")})
        
    messages.append({"role": "user", "content": message})
    
    max_loops = 15
    loop_count = 0
    tools_used = set()
    
    while loop_count < max_loops:
        loop_count += 1
        
        result = provider.invoke(
            messages,
            tools=TOOLS,
            tool_choice="auto",
            temperature=0.2,
            max_tokens=2048,
        )
        response_message = result.message
        
        # If the LLM didn't call any tools, it means it has formulated a final answer.
        if not response_message.tool_calls:
            yield {"type": "tools_used", "tools": list(tools_used)}
            
            # Stream the final answer that the model already computed in this loop iteration.
            # We do NOT re-call the LLM here — doing so caused local models (Ollama/Groq) to
            # emit raw XML function-call syntax instead of the answer because the messages array
            # contains "tool" role entries that some models misinterpret when asked to stream.
            final_content = _apply_executive_quality_guard(
                provider,
                message,
                response_message.content or "",
            )
            # Yield line-by-line to preserve markdown formatting (newlines, bullets, bold, tables)
            import re
            # Split on line endings but keep the delimiter so recipient sees correct line structure
            chunks = re.split(r'(\n)', final_content)
            for chunk in chunks:
                if chunk:  # skip empty strings from split
                    yield chunk
            return
            
        messages.append(response_message)

        for tool_call in response_message.tool_calls:
            tool_name = tool_call.function.name
            tools_used.add(tool_name)
            if tool_names_out is not None and tool_name not in tool_names_out:
                tool_names_out.append(tool_name)

            try:
                args = json.loads(tool_call.function.arguments)
            except Exception:
                args = {}

            tool_started_at = time.perf_counter()
            tool_status = "error"
            visualization = None
            try:
                if tool_name == "render_chart":
                    # Build the chart from real DB data, stream the spec straight to the UI, and
                    # feed the LLM only a compact confirmation (never the full option JSON).
                    spec, result_str = build_chart_result(db, args)
                    if spec is not None:
                        visualization = {
                            "type": "visualization",
                            "chart_type": spec.get("chart_type"),
                            "title": spec.get("title"),
                            "spec": spec.get("option"),
                        }
                else:
                    result_str = execute_tool(db, tool_name, args)
                tool_status = _tool_result_status(result_str)
            finally:
                tool_elapsed_ms = int((time.perf_counter() - tool_started_at) * 1000)
                log_observability_event(
                    logger,
                    "chat_tool_completed",
                    request_id=request_id,
                    session_id=session_id,
                    elapsed_ms=tool_elapsed_ms,
                    response_intent="deep_analysis",
                    tool_names=[tool_name],
                    tool_name=tool_name,
                    tool_status=tool_status,
                    tool_elapsed_ms=tool_elapsed_ms,
                )

            if visualization is not None:
                yield visualization

            messages.append({
                "tool_call_id": tool_call.id,
                "role": "tool",
                "name": tool_name,
                "content": result_str,
            })

    yield {"type": "tools_used", "tools": list(tools_used)}
    yield "Deep analysis timed out. I was able to gather some data but could not synthesize a final answer in time. Try asking a more specific question."
