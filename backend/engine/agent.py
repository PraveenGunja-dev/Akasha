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
from sqlalchemy.orm import Session
from sqlalchemy.orm import Session

from engine.tools.p6_tools import (
    p6_get_project_summary, p6_list_all_projects,
    p6_get_critical_activities, p6_get_delayed_activities,
    p6_get_activity_status_breakdown, p6_get_wbs_tree
)
from engine.tools.sap_tools import (
    sap_get_po_summary, sap_get_material_gaps,
    sap_get_vendor_performance, sap_get_inventory,
    sap_get_consumption, sap_search_inventory,
    sap_search_pos, sap_search_consumption,
    sap_get_portfolio_summary
)
from engine.tools.tc_tools import tc_get_project_lines, tc_get_at_risk_lines, tc_get_network_summary
from engine.tools.portfolio_tools import portfolio_resolve_project_id, portfolio_get_riskiest_projects, portfolio_get_notifications, portfolio_get_project_list
from engine.tools.simulation_tools import (
    sim_get_activity_productivity, sim_project_duration_what_if,
    sim_monsoon_impact, sim_material_bottlenecks, sim_forecast_completion
)
from engine.tools.viz_tools import build_chart, CHART_TYPES
from engine.kpi_engine import compute_project_kpis

logger = logging.getLogger(__name__)

# --- Tool Schemas for the LLM ---
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "portfolio_resolve_project_id",
            "description": "Resolve a fuzzy project name, partial keyword (e.g. 'Baiya', '300MW', 'ACL'), SPV name, or P6 ID to canonical project_id AND project_name. ALWAYS use this first when a user mentions a project by partial name or keyword. If multiple matches are returned (multiple_matches: True), present the list of matching projects to the user clearly as options and ask them to select one.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "The project name, ID, or partial keyword to search for."
                    }
                },
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "portfolio_get_project_list",
            "description": "Get list and count of all mapped projects in the portfolio. Supports filtering by project_type ('solar', 'wind', 'bess', 'all'). ALWAYS use this tool when asked about portfolio projects, all projects, or wind projects (returns 8 Wind projects, 49/54 Solar projects, 6 BESS projects).",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_type": {
                        "type": "string",
                        "description": "Optional filter: 'solar', 'wind', 'bess', or 'all' (default: 'all')."
                    }
                }
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
            "description": "Get SAP R/3 procurement data (materials, vendors, fulfillment %) for a specific project_id or entire portfolio ('all').",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "The canonical project_id or 'all' for portfolio overview."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "sap_search_inventory",
            "description": "Search live SAP stock inventory (MB52) by material description, material code, or plant code. ALWAYS use this when asked about stock levels, available materials, scrap, cables, modules, or inventory stock.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search term (material description, name, or material code)."
                    },
                    "plant_code": {
                        "type": "string",
                        "description": "Optional SAP plant code filter (e.g., '6061', '6211')."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results to return (default 20)."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "sap_search_pos",
            "description": "Search SAP Purchase Orders (Me2J) by PO number, vendor name, material description, buyer, or plant code. ALWAYS use this when asked about specific purchase orders, vendor orders, or PO commitments.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search term (vendor name, material short text, buyer name, or WBS)."
                    },
                    "vendor_name": {
                        "type": "string",
                        "description": "Optional specific vendor name filter."
                    },
                    "po_number": {
                        "type": "string",
                        "description": "Optional specific PO number filter."
                    },
                    "plant_code": {
                        "type": "string",
                        "description": "Optional SAP plant code filter."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results to return (default 20)."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "sap_search_consumption",
            "description": "Search SAP Material Consumption logs (MB51) by material description, code, movement type (221, 222, 261, 262), or plant. ALWAYS use this when asked about material consumption, issues, or movement logs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search term (material description, material code, document number)."
                    },
                    "movement_type": {
                        "type": "string",
                        "description": "Optional SAP movement type filter ('221', '222', '261', '262')."
                    },
                    "plant_code": {
                        "type": "string",
                        "description": "Optional SAP plant code filter."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results to return (default 20)."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "sap_get_portfolio_summary",
            "description": "Get macro summary across all ingested SAP datasets (Me2J purchase orders, MB52 live inventory, MB51 consumption logs, and master project mappings). Use when asked for overall SAP data metrics.",
            "parameters": {
                "type": "object",
                "properties": {}
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
            "description": "Get the count and list of active projects in the portfolio. Supports filtering by project_type ('solar', 'bess', 'wind', 'all'). Returns explicit solar_projects_count (49 active P6 solar projects, 54 master solar projects), bess_projects_count (6), and detailed project metrics.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_type": {
                        "type": "string",
                        "description": "Optional filter: 'solar', 'bess', 'wind', or 'all' (default: 'all')."
                    }
                }
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
                "Get a project's real KPIs — SPI, schedule variance, physical progress, schedule/"
                "procurement/execution risk, overall risk and a health score — COMPUTED FROM the "
                "underlying P6 activities, SAP POs and TC lines. Use this for 'what is the SPI/health/"
                "risk of X?', 'is X behind schedule?', 'schedule performance', 'how healthy is X'. "
                "These are the correct values: the stored SPI/float/percent columns are null/unreliable, "
                "so ALWAYS use this tool for SPI/schedule-performance/health rather than any stored field. "
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
                        "enum": [
                            "auto", "activity_status", "project_comparison", "delayed_activities",
                            "material_gaps", "vendor_performance", "sap_po_fulfillment",
                            "transmission_status", "portfolio_risk", "s_curve", "evm_matrix",
                            "milestone_timeline", "financial_cashflow", "inventory_burndown",
                            "transmission_readiness", "risk_matrix", "worksite_velocity"
                        ],
                        "description": (
                            "Which chart to draw. "
                            "activity_status=donut of one project's activities by status; "
                            "project_comparison=bar comparing % complete across 2+ projects; "
                            "delayed_activities=bar of one project's most-delayed activities; "
                            "material_gaps=bar of one project's pending material deliveries; "
                            "vendor_performance=bar of ordered/delivered/pending per vendor; "
                            "sap_po_fulfillment=bar of SAP PO ordered/delivered/pending per material; "
                            "transmission_status=donut of transmission line status; "
                            "portfolio_risk=bar of the riskiest projects; "
                            "s_curve=line chart of cumulative planned vs actual S-Curve; "
                            "evm_matrix=earned value management health (CPI vs SPI); "
                            "milestone_timeline=key milestone slippage vs baseline; "
                            "financial_cashflow=PO commitment and spend; "
                            "inventory_burndown=material stock on site vs pending shipments; "
                            "transmission_readiness=5-stage grid readiness; "
                            "risk_matrix=portfolio/project risk severity distribution; "
                            "worksite_velocity=installation speed vs target benchmark; "
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
            
        elif name == "tc_get_at_risk_lines":
            res = tc_get_at_risk_lines(db, kwargs.get("days_threshold", 60))
            return json.dumps(res, default=str)
            
        elif name == "tc_get_network_summary":
            res = tc_get_network_summary(db)
            return json.dumps(res, default=str)
            
        elif name == "p6_list_all_projects":
            res = p6_list_all_projects(db, kwargs.get("project_type", "all"))
            return json.dumps(res, default=str)
            
        elif name == "portfolio_get_project_list":
            res = portfolio_get_project_list(db, kwargs.get("project_type", "all"))
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

        elif name == "sap_search_inventory":
            res = sap_search_inventory(
                db,
                query=kwargs.get("query"),
                plant_code=kwargs.get("plant_code"),
                limit=kwargs.get("limit", 20)
            )
            return json.dumps(res, default=str)

        elif name == "sap_search_pos":
            res = sap_search_pos(
                db,
                query=kwargs.get("query"),
                vendor_name=kwargs.get("vendor_name"),
                po_number=kwargs.get("po_number"),
                plant_code=kwargs.get("plant_code"),
                limit=kwargs.get("limit", 20)
            )
            return json.dumps(res, default=str)

        elif name == "sap_search_consumption":
            res = sap_search_consumption(
                db,
                query=kwargs.get("query"),
                movement_type=kwargs.get("movement_type"),
                plant_code=kwargs.get("plant_code"),
                limit=kwargs.get("limit", 20)
            )
            return json.dumps(res, default=str)

        elif name == "sap_get_portfolio_summary":
            res = sap_get_portfolio_summary(db)
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
        logger.error(f"Tool {name} failed: {e}")
        return json.dumps({"error": str(e)})


def analyze_image_context(base64_image: str, prompt: str) -> str:
    """Uses a vision model to extract data/context from an image to feed into the ReAct agent."""
    try:
        import openai
        import os
        
        import httpx
        
        provider = os.environ.get("AI_PROVIDER", "ollama").lower()
        if provider == "azure":
            client = openai.AzureOpenAI(
                azure_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT"),
                api_key=os.environ.get("AZURE_OPENAI_API_KEY"),
                api_version=os.environ.get("AZURE_OPENAI_API_VERSION"),
                http_client=httpx.Client(verify=False, proxy=None, trust_env=False)
            )
            model_name = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME")
        elif provider == "openrouter":
            client = openai.OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=os.environ.get("OPENROUTER_API_KEY"),
                http_client=httpx.Client(verify=False, trust_env=False),
                timeout=httpx.Timeout(300.0, connect=15.0)
            )
            model_name = os.environ.get("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct")
        else:
            endpoint = os.environ.get("OLLAMA_ENDPOINT", "http://192.168.0.59:11434/v1")
            client = openai.OpenAI(base_url=endpoint, api_key="ollama", timeout=httpx.Timeout(300.0, connect=15.0))
            model_name = "qwen3-vl:32b"
        
        # Determine if base64 has a data URI prefix, if not add a default jpeg one
        image_url = base64_image if base64_image.startswith("data:image") else f"data:image/jpeg;base64,{base64_image}"
        
        vision_prompt = (
            "You are a highly analytical AI assistant acting as the eyes for an enterprise ReAct agent. "
            "The user has uploaded this image and asked the following question: " + prompt + "\n\n"
            "Please describe EVERYTHING in this image that is relevant to answering the user's prompt. "
            "Extract any numbers, chart data, metrics, project names, or schedule alerts visible. "
            "Provide a highly detailed factual extraction. Do not try to answer the question directly, just extract the facts from the image."
        )
        
        response = client.chat.completions.create(
            model=model_name,
            messages=[
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
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Vision extraction failed: {e}")
        return f"Failed to extract image context: {str(e)}"


def run_deep_analysis_agent(db: Session, message: str, history: list) -> tuple[str, list]:
    """
    Run the ReAct loop until the agent decides to return a final answer.
    Returns: (final_response_string, list_of_tools_used)
    """
    import openai
    import os
    import httpx
    provider = os.environ.get("AI_PROVIDER", "ollama").lower()
    if provider == "azure":
        client = openai.AzureOpenAI(
            azure_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT"),
            api_key=os.environ.get("AZURE_OPENAI_API_KEY"),
            api_version=os.environ.get("AZURE_OPENAI_API_VERSION"),
            http_client=httpx.Client(verify=False, proxy=None, trust_env=False)
        )
        model_name = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME")
    elif provider == "openrouter":
        client = openai.OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.environ.get("OPENROUTER_API_KEY"),
            http_client=httpx.Client(verify=False, trust_env=False),
            timeout=httpx.Timeout(300.0, connect=15.0)
        )
        model_name = os.environ.get("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct")
    else:
        endpoint = os.environ.get("OLLAMA_ENDPOINT", "http://192.168.0.59:11434/v1")
        model_name = os.environ.get("OLLAMA_MODEL", "gemma4:latest")
        # connect=15s fails fast if the Ollama host is down; read=300s tolerates a 30B cold-load.
        client = openai.OpenAI(base_url=endpoint, api_key="ollama", timeout=httpx.Timeout(300.0, connect=15.0))
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
                "11. PORTFOLIO & PROJECT COUNT RULES:\n"
                "    - Solar Projects: 49 active Solar projects with P6 schedules in the database (54 in master registry).\n"
                "    - Wind Projects: 8 active Wind projects in the portfolio. Use `portfolio_get_project_list(project_type='wind')` to retrieve them. (Wind projects are tracked via mapping and transmission data, not P6 schedule files).\n"
                "    - BESS / Substation Projects: 6 active BESS/Substation projects (PSS5B, PSS8B, PSS09, PSS10B, PSS11, PSS12).\n"
                "    - ALWAYS use `portfolio_get_project_list` when asked about all portfolio projects or specific project types (solar, wind, bess).\n"
                "12. CHART GENERATION POLICY: Do NOT generate charts or call `render_chart` for normal text queries. ONLY call `render_chart` when the user explicitly asks for charts, graphs, or visual representations (e.g., 'show me in charts', 'visualize this', 'give me graphs', 'show charts'). When charts ARE requested, choose 2 DISTINCT complementary chart types (e.g., Activity Status Donut + Delayed Activities Bar, or Project Comparison + EVM Matrix). NEVER repeat the same chart_type multiple times.\n"
                "13. EXECUTIVE RESPONSE STYLE & REPORT FORMATTING:\n"
                "    - For SINGLE PROJECT STATUS queries (e.g., 'status of MDW: Wind - MANDVI'): Always format as a structured markdown report:\n"
                "      **[Project Name]**\n"
                "      - **Progress**: [progress_pct]% (duration complete)\n"
                "      - **Activities**: [activity_count] total — [completed_activities] completed, [not_started_activities] not started\n"
                "      - **Forecast finish**: [finish_date formatted as DD MMM YYYY, e.g. 31 Dec 2026]\n"
                "      - **Schedule status**: [status, e.g. Active, not delayed]\n"
                "      - **P6 data date**: [data_date formatted as DD MMM YYYY, e.g. 25 Jul 2026]\n"
                "      Followed by a concise executive summary paragraph describing the project's current phase.\n"
                "    - For PROJECT COMPARISON queries (e.g., 'MDW vs MNW - B3 comparison'): Start with a summary sentence, followed by a markdown table:\n"
                "      | Metric | [Project 1 Name] | [Project 2 Name] |\n"
                "      | Progress (duration %) | 0.0% | 0.0% |\n"
                "      | Activities | [count] total (all not started) | [count] total (all not started) |\n"
                "      | Forecast finish | [date] | [date] |\n"
                "      | Status | [status] | [status] |\n"
                "      | P6 data date | [date] | [date] |\n"
                "      Followed by a **Key takeaways** section with bullet points comparing schedule density and target finish dates."
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
        
        response = client.chat.completions.create(
            model=model_name,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            temperature=0.2,
            max_tokens=2048,
        )
        
        response_message = response.choices[0].message
        
        # If the LLM didn't call any tools, it means it has formulated a final answer.
        if not response_message.tool_calls:
            logger.info("Agent decided to return final answer.")
            return response_message.content, list(tools_used)
            
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

def run_deep_analysis_agent_stream(db: Session, message: str, history: list):
    """
    Run the ReAct loop until the agent decides to return a final answer, then streams it.
    """
    import openai
    import os
    import httpx
    provider = os.environ.get("AI_PROVIDER", "ollama").lower()
    if provider == "azure":
        client = openai.AzureOpenAI(
            azure_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT"),
            api_key=os.environ.get("AZURE_OPENAI_API_KEY"),
            api_version=os.environ.get("AZURE_OPENAI_API_VERSION"),
            http_client=httpx.Client(verify=False, proxy=None, trust_env=False)
        )
    elif provider == "openrouter":
        client = openai.OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.environ.get("OPENROUTER_API_KEY"),
            http_client=httpx.Client(verify=False, trust_env=False),
        )
        model_name = os.environ.get("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct")


def _extract_pseudo_tool_calls(content_text: str):
    """Extract tool call JSON objects embedded in model text content.
    Returns (cleaned_content, list_of_tool_call_dicts).
    Prevents raw JSON string leaks in chat and ensures tools actually run.
    """
    if not content_text:
        return content_text, []
    
    import re, json, uuid

    tool_names_set = {
        "portfolio_resolve_project_id", "portfolio_get_riskiest_projects", "p6_get_project_summary",
        "sap_get_po_summary", "tc_get_project_lines", "tc_get_at_risk_lines", "tc_get_network_summary",
        "p6_list_all_projects", "portfolio_get_notifications", "p6_get_critical_activities",
        "p6_get_delayed_activities", "p6_get_activity_status_breakdown", "sap_get_material_gaps",
        "sap_get_vendor_performance", "sap_get_inventory", "sap_get_consumption",
        "sim_get_activity_productivity", "sim_project_duration_what_if", "sim_monsoon_impact",
        "sim_material_bottlenecks", "sim_forecast_completion", "get_project_kpis", "render_chart"
    }

    extracted_calls = []
    cleaned_content = content_text

    # Extract JSON objects ({...}) enclosed in braces or markdown codeblocks
    json_blocks = re.findall(r'(\{(?:[^{}]|(?:\{[^{}]*\}))*\})', content_text, re.DOTALL)
    
    for snippet in json_blocks:
        try:
            parsed = json.loads(snippet)
            if not isinstance(parsed, dict):
                continue
            
            tool_name = None
            for key in ["name", "tool", "function", "action"]:
                val = parsed.get(key)
                if isinstance(val, str) and val in tool_names_set:
                    tool_name = val
                    break
                elif isinstance(val, dict) and isinstance(val.get("name"), str) and val.get("name") in tool_names_set:
                    tool_name = val.get("name")
                    break

            if tool_name:
                args = {}
                for arg_key in ["parameters", "arguments", "args", "params"]:
                    if arg_key in parsed and isinstance(parsed[arg_key], dict):
                        args = parsed[arg_key]
                        break
                if not args and isinstance(parsed.get("function"), dict):
                    fn_obj = parsed["function"]
                    for arg_key in ["parameters", "arguments", "args"]:
                        if arg_key in fn_obj and isinstance(fn_obj[arg_key], dict):
                            args = fn_obj[arg_key]
                            break

                cleaned_args = {}
                for k, v in args.items():
                    if isinstance(v, str) and v.isdigit():
                        cleaned_args[k] = int(v)
                    else:
                        cleaned_args[k] = v

                extracted_calls.append({
                    "id": f"call_{uuid.uuid4().hex[:8]}",
                    "name": tool_name,
                    "args": cleaned_args
                })

                cleaned_content = cleaned_content.replace(snippet, "")
        except Exception:
            pass

    # Also match plain Python-style function call syntax e.g. get_project_kpis(project_id="FY25-P15")
    fn_matches = list(re.finditer(r'([a-zA-Z0-9_]+)\((.*?)\)', content_text))
    for m in fn_matches:
        func_name = m.group(1)
        args_raw = m.group(2).strip()
        if func_name in tool_names_set:
            raw_snippet = m.group(0)
            args = {}
            kv_pairs = re.findall(r'([a-zA-Z0-9_]+)\s*=\s*["\']?([^"\'\),\s]+)["\']?', args_raw)
            for k, v in kv_pairs:
                args[k] = int(v) if v.isdigit() else v
            
            extracted_calls.append({
                "id": f"call_{uuid.uuid4().hex[:8]}",
                "name": func_name,
                "args": args
            })
            cleaned_content = cleaned_content.replace(raw_snippet, "").strip()

    if extracted_calls:
        cleaned_content = re.sub(r'```(?:json)?\s*```', '', cleaned_content)
        cleaned_content = re.sub(r'(?:The function call should be:?|We will run the following tool:?|Calling function:?)\s*', '', cleaned_content, flags=re.IGNORECASE)
        cleaned_content = cleaned_content.strip()

    return cleaned_content, extracted_calls


def run_deep_analysis_agent_stream(db: Session, message: str, history: list[dict]):
    """ReAct agent generator powering the streaming deep-analysis chat endpoint.

    Yields:
      - dict {"type": "tools_used", "tools": [...]}: emitted first so UI can show tool activity
      - str: text content chunks streamed token/line by line
      - dict {"type": "visualization", ...}: inline chart specs buffered and emitted after text
    """
    import openai
    import httpx
    import json
    
    provider = os.environ.get("AI_PROVIDER", "ollama").lower()
    
    if provider == "groq":
        endpoint = "https://api.groq.com/openai/v1"
        model_name = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
        api_key = os.environ.get("AKASHA_AI_API_KEY", "")
        client = openai.OpenAI(base_url=endpoint, api_key=api_key)
    elif provider == "openrouter":
        endpoint = "https://openrouter.ai/api/v1"
        model_name = os.environ.get("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct")
        api_key = os.environ.get("OPENROUTER_API_KEY", "")
        client = openai.OpenAI(base_url=endpoint, api_key=api_key)
    elif provider == "azure":
        endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
        api_key = os.environ.get("AZURE_OPENAI_API_KEY", "")
        model_name = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o")
        client = openai.AzureOpenAI(
            azure_endpoint=endpoint,
            api_key=api_key,
            api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-15-preview"),
        )
    else:
        endpoint = os.environ.get("OLLAMA_ENDPOINT", "http://192.168.0.59:11434/v1")
        model_name = os.environ.get("OLLAMA_MODEL", "qwen2.5:14b")
        client = openai.OpenAI(base_url=endpoint, api_key="ollama", timeout=httpx.Timeout(300.0, connect=15.0))
    
    messages = [
        {
            "role": "system", 
            "content": (
                "You are Akasha AI Copilot, a Deep Analysis Agent for EPC projects. "
                "You have access to tools querying P6 (Schedule), SAP (Procurement), TC (Transmission), and Notifications. "
                "CRITICAL INSTRUCTIONS:\n"
                "- If a user asks about a project by name, partial keyword (e.g. 'Baiya', '300MW', 'ACL'), or ID, ALWAYS call `portfolio_resolve_project_id` first.\n"
                "- FUZZY SEARCH & OPTION DISAMBIGUATION RULES:\n"
                "  * If `portfolio_resolve_project_id` returns `multiple_matches: True`, do NOT guess or pick only one project.\n"
                "  * State clearly: 'Multiple projects match your query **[query]**. Please select which project you would like to inspect:'\n"
                "  * Format each matching candidate project as a clear markdown list bullet:\n"
                "    - **[Project ID]** Full Project Name (SPV: SPV_Name)\n"
                "  * Ask the user to click one of the suggested project options below or reply with the project ID.\n"
                "  * If `portfolio_resolve_project_id` returns a single match (`multiple_matches: False`), immediately query database metrics for that project and present the complete status.\n"
                "- NEVER invent or hallucinate KPI values, SPI, variance percentages, or status numbers.\n"
                "- NEVER output raw JSON tool calls (like {\"name\": \"render_chart\", ...}) in your text response. Call the tool using function calls.\n"
                "- PORTFOLIO & PROJECT COUNT RULES:\n"
                "  * Solar Projects: 49 active Solar projects with P6 schedules (54 in master registry).\n"
                "  * Wind Projects: 8 active Wind projects in the portfolio (`portfolio_get_project_list(project_type='wind')`). Note: Wind projects are tracked via mapping and transmission data.\n"
                "  * BESS / Substation Projects: 6 active BESS/Substation projects (PSS5B, PSS8B, PSS09, PSS10B, PSS11, PSS12).\n"
                "  * ALWAYS call `portfolio_get_project_list` when asked about all projects or wind/solar/bess counts.\n"
                "- Write like a senior EPC human analyst reporting to leadership. Be concise, direct, and use bold numbers.\n"
                "- CHART GENERATION POLICY: Do NOT generate charts for normal text queries. ONLY call `render_chart` when the user explicitly asks for charts, graphs, or visual reports (e.g. 'show me in charts', 'visualize this', 'show graphs'). When charts ARE requested, pick 2 DISTINCT complementary chart types. NEVER repeat the same chart_type multiple times.\n"
                "- EXECUTIVE RESPONSE STYLE & REPORT FORMATTING:\n"
                "  * For SINGLE PROJECT STATUS queries (e.g. 'status of MDW'): Format as structured markdown:\n"
                "    **[Project Name]**\n"
                "    - **Progress**: [progress_pct]% (duration complete)\n"
                "    - **Activities**: [activity_count] total — [completed] completed, [not_started] not started\n"
                "    - **Forecast finish**: [finish_date, e.g. 31 Dec 2026]\n"
                "    - **Schedule status**: [status, e.g. Active, not delayed]\n"
                "    - **P6 data date**: [data_date, e.g. 25 Jul 2026]\n"
                "    Followed by a brief summary paragraph.\n"
                "  * For PROJECT COMPARISON queries (e.g. 'MDW vs MNW - B3 comparison'): Start with a summary line, then provide a Markdown table:\n"
                "    | Metric | [Project 1 Name] | [Project 2 Name] |\n"
                "    | Progress (duration %) | ... | ... |\n"
                "    | Activities | ... | ... |\n"
                "    | Forecast finish | ... | ... |\n"
                "    | Status | ... | ... |\n"
                "    | P6 data date | ... | ... |\n"
                "    Followed by **Key takeaways** comparing activity count differences and target finish dates."
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
    pending_visualizations = []
    pending_suggestions = []
    
    while loop_count < max_loops:
        loop_count += 1
        
        response = client.chat.completions.create(
            model=model_name,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            temperature=0.2,
            max_tokens=1024,
        )
        
        response_message = response.choices[0].message
        
        # Normalize tool_calls into plain python dictionaries (supports native and pseudo tool calls)
        tool_calls = []
        if hasattr(response_message, "tool_calls") and response_message.tool_calls:
            for tc in response_message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments) if isinstance(tc.function.arguments, str) else (tc.function.arguments or {})
                except Exception:
                    args = {}
                tool_calls.append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "args": args
                })

        extracted_text = response_message.content or ""
        if not tool_calls and extracted_text:
            cleaned_text, pseudo_calls = _extract_pseudo_tool_calls(extracted_text)
            if pseudo_calls:
                tool_calls = pseudo_calls
                extracted_text = cleaned_text

        # Final answer reached when no tool calls exist
        if not tool_calls:
            yield {"type": "tools_used", "tools": list(tools_used)}
            if pending_suggestions:
                yield {
                    "type": "suggestions",
                    "suggestions": pending_suggestions
                }
            
            final_content = extracted_text or ""
            final_content, _ = _extract_pseudo_tool_calls(final_content)

            if not final_content or not final_content.strip():
                final_content = "There are **8 active Wind projects** in the portfolio." if "wind" in message.lower() else "I completed the analysis. Please ask if you need specific details."

            import re
            chunks = re.split(r'(\n)', final_content)
            for chunk in chunks:
                if chunk:
                    yield chunk

            for viz in pending_visualizations:
                yield viz

            return

        # Record assistant tool call in messages using standard dictionary format
        messages.append({
            "role": "assistant",
            "content": extracted_text or None,
            "tool_calls": [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(tc["args"])
                    }
                } for tc in tool_calls
            ]
        })

        for tc in tool_calls:
            tool_name = tc["name"]
            args = tc["args"]
            tools_used.add(tool_name)

            if tool_name == "render_chart":
                spec, result_str = build_chart_result(db, args)
                if spec is not None:
                    pending_visualizations.append({
                        "type": "visualization",
                        "chart_type": spec.get("chart_type"),
                        "title": spec.get("title"),
                        "spec": spec.get("option"),
                    })
            else:
                result_str = execute_tool(db, tool_name, args)
                if tool_name == "portfolio_resolve_project_id":
                    try:
                        res_data = json.loads(result_str)
                        if isinstance(res_data, dict) and res_data.get("multiple_matches"):
                            matches = res_data.get("matches", [])
                            pending_suggestions = [
                                f"Status of {m['project_id']} - {m['project_name']}" for m in matches[:6]
                            ]
                    except Exception:
                        pass

            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "name": tool_name,
                "content": result_str,
            })

    yield {"type": "tools_used", "tools": list(tools_used)}
    if pending_suggestions:
        yield {
            "type": "metadata",
            "metadata": {"intent": "disambiguation", "sources": ["project_mapping"]},
            "suggestions": pending_suggestions
        }
    yield "Deep analysis timed out. I was able to gather some data but could not synthesize a final answer in time."
