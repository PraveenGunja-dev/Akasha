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
    sap_get_consumption
)
from engine.tools.tc_tools import tc_get_project_lines, tc_get_at_risk_lines, tc_get_network_summary
from engine.tools.portfolio_tools import portfolio_resolve_project_id, portfolio_get_riskiest_projects, portfolio_get_notifications
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
            "name": "project_get_story_and_health",
            "description": (
                "Get the connected multi-system Project Story and 8-dimension health radar for an EPC project. "
                "Synthesizes Primavera P6 schedule delays, Pulse NC quality issues, Pulse RFI inspections, "
                "SAP purchase orders, and commercial/invoice exposures into a unified narrative. "
                "Returns the 8-dimension health radar scores (0-100), top root causes across 18 standard categories, "
                "contractor delay impact rankings, and detected system disconnects (Cases A-E). "
                "Resolve the project name to canonical project_id first."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "The canonical project_id (e.g., 'FY25-P15', 'AGE26AL')."
                    }
                },
                "required": ["project_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "project_investigate_activity",
            "description": (
                "Deep-dive causal investigation for 'Why is this activity delayed?'. "
                "Unpacks the multi-system evidence chain: "
                "Delay -> Activity -> Package -> Connected Pulse NC/RFI -> Root Cause -> Responsible Party -> Commercial Impact. "
                "Provides verified evidence, confidence tier (CONFIRMED, HIGH CONFIDENCE, LIKELY, POSSIBLE, NO EVIDENCE FOUND), "
                "and an executive narrative synthesis. "
                "Use this whenever the user asks 'why is activity X delayed', 'what caused delay in Y', or for root-cause evidence."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "The canonical project_id."
                    },
                    "activity_id": {
                        "type": "string",
                        "description": "The P6 activity ID (e.g., '6061-CC-3268', '6061-CC-3370')."
                    }
                },
                "required": ["project_id", "activity_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "project_get_gaps_and_discrepancies",
            "description": (
                "Identifies cross-system disconnects and missing interactions for a project across Cases A-E: "
                "Case A: Schedule delay with no issue/RFI logged. "
                "Case B: Critical NC/issue open with zero schedule impact. "
                "Case C: Financial/commercial expenditure with no progress on site. "
                "Case D: Interface dependencies uncoordinated between packages. "
                "Case E: Quality issue closed in Pulse but activity still stalled in P6. "
                "Returns prioritized discrepancy patterns with recommended actions."
            ),
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
            "name": "pulse_get_quality_issues",
            "description": (
                "Query Pulse Quality Non-Conformance (NC) records. "
                "Filter by canonical project_id, severity ('CRITICAL', 'MAJOR', 'MINOR'), status ('OPEN', 'CLOSED'), "
                "or contractor name. Returns NC number, severity, title, root cause category, responsible contractor, "
                "days open, and resolution details. Use when the user asks about quality issues, defects, or NCs."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "string", "description": "The canonical project_id."},
                    "severity": {"type": "string", "description": "Filter by severity: 'CRITICAL', 'MAJOR', 'MINOR', or 'ALL'."},
                    "status": {"type": "string", "description": "Filter by status: 'OPEN', 'CLOSED', or 'ALL'."},
                    "contractor": {"type": "string", "description": "Filter by contractor name."},
                    "limit": {"type": "integer", "description": "Max records to return (default 10)."}
                },
                "required": ["project_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "pulse_get_rfis",
            "description": (
                "Query Pulse Request-For-Inspection (RFI) records. "
                "Returns field inspection hold points, workfront inspection submissions, contractor submissions, "
                "approval status, and inspection dates. Use when user asks about site inspections, RFI backlogs, or pending clearances."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "string", "description": "The canonical project_id."},
                    "status": {"type": "string", "description": "Filter by status (e.g. 'PENDING', 'APPROVED', 'REJECTED', or 'ALL')."},
                    "contractor": {"type": "string", "description": "Filter by contractor name."},
                    "rfi_type": {"type": "string", "description": "Filter by inspection type (e.g., 'Civil', 'Electrical', 'Mechanical')."},
                    "limit": {"type": "integer", "description": "Max records to return (default 10)."}
                },
                "required": ["project_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "invoice_get_slr_status",
            "description": (
                "Query E-Invoice and Service Level Report (SLR) commercial status. "
                "Returns pending contractor invoices, value-at-risk, payment approval stages, current approvers, "
                "and work order breakdowns. Use when asked about invoices, contractor payments, SLR blocks, or financial commitments."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "string", "description": "The canonical project_id or location hint."},
                    "vendor_name": {"type": "string", "description": "Filter by specific vendor / contractor name."},
                    "status": {"type": "string", "description": "Filter by status (e.g. 'PENDING', 'COMPLETED', or 'ALL')."},
                    "is_pending": {"type": "boolean", "description": "True to get only pending / blocked invoices."},
                    "limit": {"type": "integer", "description": "Max records to return (default 10)."}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "drone_verify_progress",
            "description": (
                "Cross-check contractor-reported schedule progress against Spectra Drone aerial orthomosaic measurements. "
                "Compares physical ground truth for Piling, MMS/Tracker Erection, Module Mounting, Inverters, and IDT Foundation "
                "against P6 milestones for surveyed sites (Khavda, Baiya, Bandha)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "string", "description": "The canonical project_id or project name."},
                    "block_prefix": {"type": "string", "description": "Optional block prefix (e.g. 'A16A', 'A16B')."}
                },
                "required": ["project_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_project_docx_report",
            "description": (
                "Generates an executive-ready Adani-branded PDF (.pdf) and Microsoft Word (.docx) report for a project. "
                "Includes high-resolution 4-quadrant visual analytics charts (Delay by Package, Loss & Delay Attribution by Root Cause, "
                "Schedule Performance Ratio SPI with Deficit Shading, and Component Breakdown Donut), "
                "critical path delayed activities table with real dates, contractor accountability, and strategic action plans. "
                "Returns direct download links for both PDF and DOCX. Always use this whenever the user asks for a report, PDF, Word doc, or executive briefing."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "string", "description": "The canonical project_id."},
                    "report_title": {"type": "string", "description": "Optional custom report title."}
                },
                "required": ["project_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "draft_stakeholder_email",
            "description": (
                "Drafts an executive, formal communication or escalation email to contractors, project directors, or package heads. "
                "Generates corporate email format with Subject, To, Cc, Context, Specific Delay/NC Evidence, Contractual Reference, Action Required, and SLA Deadline. "
                "Use when the user asks to draft an email, notice of delay, escalation memo, or communication regarding project findings."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "recipient_role": {"type": "string", "description": "Recipient role (e.g., 'Contractor Project Lead', 'Project Director', 'QA/QC Lead', 'Procurement Head')."},
                    "project_id": {"type": "string", "description": "The canonical project_id."},
                    "issue_type": {"type": "string", "description": "Type of issue: 'DELAY_NOTICE', 'QUALITY_NON_CONFORMANCE', 'COMMERCIAL_SLR_HOLD', 'INTERFACE_BLOCKER'."},
                    "contractor_name": {"type": "string", "description": "Contractor or vendor name involved."},
                    "action_required": {"type": "string", "description": "Specific action required from the recipient."},
                    "deadline_days": {"type": "integer", "description": "Number of days for resolution deadline (default 3)."}
                },
                "required": ["recipient_role", "project_id", "issue_type"]
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

        elif name == "get_project_kpis":
            res = compute_project_kpis(db, kwargs.get("project_id"))
            return json.dumps(res, default=str)

        elif name == "render_chart":
            # Non-stream path: build the chart so it doesn't error, but there's no channel to
            # deliver the spec here — the streaming loop is what actually emits the visualization.
            _spec, confirmation = build_chart_result(db, kwargs)
            return confirmation

        elif name == "project_get_story_and_health":
            from engine.intelligence.core import get_project_intelligence
            intel = get_project_intelligence(db, kwargs.get("project_id"))
            story = intel.get("story", {})
            return json.dumps({
                "project_id": kwargs.get("project_id"),
                "overall_risk_score": story.get("overall_risk_score"),
                "overall_status": story.get("overall_status"),
                "health_radar": story.get("health_radar", {}),
                "top_delays": [
                    {
                        "activity_id": a["activity_id"],
                        "name": a["name"],
                        "package": a.get("package"),
                        "delay_days": a["delay_days"],
                        "root_cause": a.get("root_cause", {}).get("category"),
                        "responsible_party": a.get("root_cause", {}).get("responsible_party"),
                        "has_linked_issue": a.get("has_linked_issue"),
                    }
                    for a in story.get("top_delays", [])[:5]
                ],
                "top_root_causes": story.get("top_root_causes", []),
                "contractor_impact_ranking": story.get("contractor_impact_ranking", [])[:5],
                "gaps_count": len(story.get("gaps", [])),
                "critical_insights": story.get("executive_summary", {}).get("critical_insights", [])
            }, default=str)

        elif name == "project_investigate_activity":
            from engine.intelligence.project_story import investigate_single_activity
            res = investigate_single_activity(db, kwargs.get("project_id"), kwargs.get("activity_id"))
            return json.dumps(res, default=str)

        elif name == "project_get_gaps_and_discrepancies":
            from engine.intelligence.core import get_project_intelligence
            intel = get_project_intelligence(db, kwargs.get("project_id"))
            gaps = intel.get("story", {}).get("gaps", [])
            return json.dumps({"project_id": kwargs.get("project_id"), "gaps": gaps}, default=str)

        elif name == "pulse_get_quality_issues":
            import models
            from services.project_identity import resolve
            pid = kwargs.get("project_id")
            identity = resolve(db, pid) if pid else None
            query = db.query(models.PulseNC)
            if identity and identity.pulse_project_uuid:
                query = query.filter(models.PulseNC.project_id == identity.pulse_project_uuid)
            elif identity and identity.pulse_project_name:
                query = query.filter(models.PulseNC.project_name == identity.pulse_project_name)
            sev = kwargs.get("severity")
            if sev and sev.upper() != "ALL":
                query = query.filter(models.PulseNC.category.ilike(f"%{sev}%"))
            status = kwargs.get("status")
            if status and status.upper() != "ALL":
                query = query.filter(models.PulseNC.status.ilike(f"%{status}%"))
            contractor = kwargs.get("contractor")
            if contractor:
                query = query.filter(models.PulseNC.contractor_name.ilike(f"%{contractor}%"))
            limit = int(kwargs.get("limit", 10))
            ncs = query.order_by(models.PulseNC.created_at.desc()).limit(limit).all()
            return json.dumps([
                {
                    "nc_number": nc.nc_label or nc.pulse_id,
                    "title": nc.description or nc.defect_type,
                    "severity": nc.category or "Non Critical",
                    "status": nc.status_label or nc.status,
                    "defect_type": nc.defect_type,
                    "package": nc.package_name,
                    "contractor": nc.contractor_name,
                    "created_date": str(nc.created_at) if nc.created_at else None,
                    "approved_date": str(nc.approved_at) if nc.approved_at else None,
                }
                for nc in ncs
            ], default=str)

        elif name == "pulse_get_rfis":
            import models
            from services.project_identity import resolve
            pid = kwargs.get("project_id")
            identity = resolve(db, pid) if pid else None
            query = db.query(models.PulseRFI)
            if identity and identity.pulse_project_uuid:
                query = query.filter(models.PulseRFI.project_id == identity.pulse_project_uuid)
            elif identity and identity.pulse_project_name:
                query = query.filter(models.PulseRFI.project_name == identity.pulse_project_name)
            status = kwargs.get("status")
            if status and status.upper() != "ALL":
                query = query.filter(models.PulseRFI.status.ilike(f"%{status}%"))
            contractor = kwargs.get("contractor")
            if contractor:
                query = query.filter(models.PulseRFI.contractor_name.ilike(f"%{contractor}%"))
            limit = int(kwargs.get("limit", 10))
            rfis = query.order_by(models.PulseRFI.created_at.desc()).limit(limit).all()
            return json.dumps([
                {
                    "rfi_number": r.rfi_label or r.pulse_id,
                    "package": r.package_name,
                    "inspection_point": r.inspection_point_name,
                    "status": r.status_label or r.status,
                    "contractor": r.contractor_name,
                    "workarea": r.workarea_name,
                    "created_date": str(r.created_at) if r.created_at else None,
                }
                for r in rfis
            ], default=str)

        elif name == "invoice_get_slr_status":
            import models
            query = db.query(models.EInvoiceRecord)
            vendor = kwargs.get("vendor_name")
            if vendor:
                query = query.filter(models.EInvoiceRecord.vendorName.ilike(f"%{vendor}%"))
            if kwargs.get("is_pending"):
                query = query.filter(models.EInvoiceRecord.isPending == True)
            status = kwargs.get("status")
            if status and status.upper() != "ALL":
                query = query.filter(models.EInvoiceRecord.statusDesc.ilike(f"%{status}%"))
            limit = int(kwargs.get("limit", 10))
            invoices = query.order_by(models.EInvoiceRecord.invoiceAmount.desc()).limit(limit).all()
            total_val = sum(float(inv.invoiceAmount or 0) for inv in invoices)
            return json.dumps({
                "invoice_count": len(invoices),
                "total_amount_in_sample": round(total_val, 2),
                "invoices": [
                    {
                        "invoice_no": inv.invoiceNo,
                        "vendor": inv.vendorName,
                        "amount": float(inv.invoiceAmount or 0),
                        "status": inv.statusDesc,
                        "stage": inv.stage,
                        "is_pending": inv.isPending,
                        "approver": inv.currentApprover,
                        "location": inv.workLocation or inv.site,
                        "description": inv.workDescription,
                    }
                    for inv in invoices
                ]
            }, default=str)

        elif name == "drone_verify_progress":
            from services.spectra_service import resolve_spectra_project_id, resolve_khavda_block, get_drone_summary, fetch_all_drone_data
            import asyncio
            pid = kwargs.get("project_id", "")
            spec_id = resolve_spectra_project_id(pid, pid)
            block = kwargs.get("block_prefix") or resolve_khavda_block(pid, pid)
            if not spec_id:
                return json.dumps({
                    "status": "NOT_SURVEYED",
                    "message": f"Project {pid} is not actively flown by Spectra Drone orthomosaics. Drone surveys currently cover Khavda (Blocks A16A-D), Baiya, and Bandha."
                })
            loop = asyncio.new_event_loop()
            try:
                drone_raw = loop.run_until_complete(fetch_all_drone_data(spec_id))
                summary = get_drone_summary(drone_raw, block)
                return json.dumps({
                    "project_id": pid,
                    "spectra_project_id": spec_id,
                    "block": block,
                    "activities_verified": summary
                }, default=str)
            finally:
                loop.close()

        elif name in ("generate_project_docx_report", "generate_project_executive_report"):
            from engine.intelligence.report_generator import build_project_intelligence_docx
            pid = kwargs.get("project_id")
            title = kwargs.get("report_title")
            docx_fn, path, size, metrics = build_project_intelligence_docx(db, pid, title)
            pdf_fn = metrics.get("pdf_filename", docx_fn.replace(".docx", ".pdf"))
            docx_url = f"/akasha/api/reports/download/{docx_fn}"
            pdf_url = f"/akasha/api/reports/download/{pdf_fn}"
            return json.dumps({
                "status": "SUCCESS",
                "message": f"Adani Executive Report generated successfully ({metrics['file_size_kb']} KB).",
                "docx_download_url": docx_url,
                "pdf_download_url": pdf_url,
                "docx_filename": docx_fn,
                "pdf_filename": pdf_fn,
                "metrics": metrics,
                "instructions_for_agent": (
                    f"Present BOTH direct markdown download links prominently at the top of your response:\n"
                    f"- [📥 Download Adani Executive Report (PDF)]({pdf_url})\n"
                    f"- [📄 Download Adani Executive Report (Word DOCX)]({docx_url})\n\n"
                    f"Then provide a crisp executive summary table of key variance metrics (Critical Delay Days, Delayed Activities, Commercial Exposure, and Primary Bottleneck). State facts only; DO NOT display arbitrary or synthetic scores."
                )
            })

        elif name == "draft_stakeholder_email":
            pid = kwargs.get("project_id", "")
            role = kwargs.get("recipient_role", "Project Stakeholder")
            issue_type = kwargs.get("issue_type", "DELAY_NOTICE")
            contractor = kwargs.get("contractor_name", "Primary Contractor")
            action = kwargs.get("action_required", "Provide immediate recovery schedule and root-cause explanation.")
            days = kwargs.get("deadline_days", 3)
            
            subject_map = {
                "DELAY_NOTICE": f"[URGENT] Formal Notice of Schedule Slippage & Recovery Mandate — Project {pid}",
                "QUALITY_NON_CONFORMANCE": f"[ACTION REQUIRED] Critical Quality Non-Conformance Notice — Project {pid}",
                "COMMERCIAL_SLR_HOLD": f"[COMMERCIAL NOTICE] Pending Invoice SLR Reconciliation Hold — Project {pid}",
                "INTERFACE_BLOCKER": f"[COORDINATION REQUIRED] Cross-Package Interface Blockage Resolution — Project {pid}",
            }
            subj = subject_map.get(issue_type, f"Project {pid} — Governance & Action Required")
            
            email_body = (
                f"Dear {role},\n\n"
                f"This is an official communication regarding operational progress on Project {pid}.\n\n"
                f"SYSTEM FINDINGS & CAUSAL EVIDENCE:\n"
                f"• Project Identifier: {pid}\n"
                f"• Contractor / Responsible Party: {contractor}\n"
                f"• Issue Classification: {issue_type.replace('_', ' ')}\n"
                f"• Identified Impact: Schedule variance and workfront bottlenecks detected across integrated P6/Pulse logs.\n\n"
                f"MANDATORY ACTION REQUIRED:\n"
                f"{action}\n\n"
                f"CONTRACTUAL COMPLIANCE & SLA:\n"
                f"In accordance with EPC General Conditions of Contract, please submit your formal response, "
                f"catch-up schedule, and mitigation plan within {days} business days from the receipt of this notice.\n\n"
                f"Sincerely,\n"
                f"Project Management & Assurance Group (PMAG)\n"
                f"Adani Green Energy Limited"
            )
            return json.dumps({
                "subject": subj,
                "to": f"{contractor.lower().replace(' ', '.')}@contractor.in" if "contractor" in role.lower() else "project.director@adani.com",
                "cc": ["pmag.assurance@adani.com", "planning.epc@adani.com"],
                "email_body": email_body,
                "status": "DRAFT_READY"
            })

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
        else:
            endpoint = os.environ.get("OLLAMA_ENDPOINT", "http://192.168.0.61:11434/v1")
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


def sanitize_executive_response(content: str) -> str:
    """
    Post-processes executive LLM response to ensure links, URLs, and formatting
    meet institutional Adani standards:
    1. Replaces any hallucinated dummy domains (e.g. adani-reporting.example/...)
       or raw docx/pdf references with valid API download endpoints: /akasha/api/reports/download/{filename}.
    2. Strips out raw prompt placeholders (e.g. <pdf_download_url>, <docx_download_url>).
    """
    if not content:
        return content

    import re

    def fix_report_link(match):
        label = match.group(1)
        url = match.group(2).strip()
        
        # If it's already an absolute or relative /akasha/api/reports/download/ URL, keep it
        if "/akasha/api/reports/download/" in url:
            return f"[{label}]({url})"
        if "/reports/download/" in url:
            clean = url.lstrip("/")
            return f"[{label}](/akasha/{clean})"

        # Check if URL contains a docx or pdf file
        m = re.search(r'([A-Za-z0-9_\-\.]+\.(?:docx|pdf))', url, re.IGNORECASE)
        if m:
            clean_fn = m.group(1)
            return f"[{label}](/akasha/api/reports/download/{clean_fn})"

        # Discard placeholder URLs
        if "<" in url and ">" in url:
            return ""

        return match.group(0)

    # Process all Markdown links [text](url)
    content = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', fix_report_link, content)
    
    # Strip any bare dummy domains or placeholders
    content = re.sub(r'https?://[^\s)]*\.example[^\s)]*', '', content)
    content = re.sub(r'adani-reporting\.example/[^\s)]*', '', content)
    content = re.sub(r'<pdf_download_url>', '', content)
    content = re.sub(r'<docx_download_url>', '', content)

    return content


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
    else:
        endpoint = os.environ.get("OLLAMA_ENDPOINT", "http://192.168.0.61:11434/v1")
        model_name = os.environ.get("OLLAMA_MODEL", "qwen3:30b-a3b")
        # connect=15s fails fast if the Ollama host is down; read=300s tolerates a 30B cold-load.
        client = openai.OpenAI(base_url=endpoint, api_key="ollama", timeout=httpx.Timeout(300.0, connect=15.0))
    # Initialize messages
    messages = [
        {
            "role": "system", 
            "content": (
                "You are Akasha Executive Copilot, the Chief Project Intelligence Assistant for Adani Portfolio Leadership (Group Executive Office, Managing Director, and PMAG - Project Management & Assurance Group).\n"
                "You have access to live cross-system telemetry querying P6 (Schedule), SAP (Procurement), TC (Transmission), Quality & RFIs (Pulse NC/RFI), E-Invoices (SLR), Drone Surveys, and Project Story Intelligence.\n"
                "TOOL CALLING DIRECTIVES:\n"
                "- If a user asks about a project by name, ALWAYS call `portfolio_resolve_project_id` first to obtain the canonical ID and project name.\n"
                "- If a user asks about overall project health, story, risks, contractor delay rankings, or root causes, call `project_get_story_and_health`.\n"
                "- If a user asks why an activity is delayed or what caused schedule slippage, call `project_investigate_activity`.\n"
                "- If a user asks about system disconnects, blindspots, or discrepancy gaps (Case A-E), call `project_get_gaps_and_discrepancies`.\n"
                "- If a user asks for quality NCs, defects, or quality issues, call `pulse_get_quality_issues`.\n"
                "- If a user asks about site inspections, RFIs, or hold points, call `pulse_get_rfis`.\n"
                "- If a user asks about contractor invoices, payment blocks, or SLR status, call `invoice_get_slr_status`.\n"
                "- If a user asks to verify progress using drone flights or aerial surveys, call `drone_verify_progress`.\n"
                "- If a user asks for a report, export, PDF, Word document, or formal briefing, you MUST call `generate_project_docx_report`. Present BOTH download links using the exact URLs returned by the tool (`docx_download_url` and `pdf_download_url`):\n"
                "  - `[📥 Download Adani Executive Report (PDF)](docx_download_url)`\n"
                "  - `[📄 Download Adani Executive Report (Word DOCX)](pdf_download_url)`\n"
                "  CRITICAL SAFETY: NEVER invent, hallucinate, or guess URLs (never use `.example`). Only output download links if `generate_project_docx_report` was called.\n"
                "- If a user asks to draft an email, notice of delay, cure letter, or escalation memo, call `draft_stakeholder_email`.\n"
                "- If a user asks about alerts or notifications, call `portfolio_get_notifications`.\n"
                "- Use tools step-by-step to gather real telemetry before answering.\n"
                "EXECUTIVE WRITING & PRESENTATION STANDARDS (ADANI PMAG / C-SUITE STANDARD):\n"
                "1. Persona & Tone: Write with the authority, rigor, and clarity of a Senior Infrastructure Partner presenting to the Group Managing Director. Be direct, factual, and analytical.\n"
                "2. Directness & Zero Fluff: Jump straight to the core strategic conclusion and figures. Never use robotic filler or clichés (e.g. 'It is important to note', 'Furthermore', 'Delve', 'In conclusion', 'Based on the provided data', 'Certainly, I can help').\n"
                "3. Quantitative Rigor: Always quantify variances (exact days delayed, e.g. +38 Days), affected capacity (MW), commercial capex exposure in ₹ Crores (₹ Cr), or physical units.\n"
                "4. No Synthetic Scores: Strictly forbid arbitrary synthetic scores or percentage ratings (e.g. 'Score: 41.5/100'). Report verified schedule variance, critical path delays, and commercial exposure.\n"
                "5. Mandatory Markdown Tables: When presenting multiple activities, rankings, root cause breakdowns, contractors, or invoices, ALWAYS format them as neat Markdown tables with clear column headers and right-aligned metrics.\n"
                "6. Absolute Units in SAP: Quantities in SAP are absolute Units, NOT Megawatts (MW). Durations are whole hours. Quantities are integers.\n"
                "7. Delayed Transmission Lines: Always report 'days delayed' and 'affected downstream projects' instead of schedule 'float'.\n"
                "8. Human-Readable Names: Always refer to projects by their human-readable project_name, never raw internal IDs.\n"
                "9. Executive Directives: Conclude every project analysis with a structured section `### 💡 Executive Directives & Suggested Interventions` with 3 prioritized, high-impact actions indicating responsible roles (e.g. Head - PMAG, Package Lead, Site Director) and turnaround SLAs (e.g. 24h / 48h)."
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
            cleaned_content = sanitize_executive_response(response_message.content)
            return cleaned_content, list(tools_used)
            
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
        model_name = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME")
    else:
        endpoint = os.environ.get("OLLAMA_ENDPOINT", "http://192.168.0.61:11434/v1")
        model_name = os.environ.get("OLLAMA_MODEL", "qwen3:30b-a3b")
        # connect=15s fails fast if the Ollama host is down; read=300s tolerates a 30B cold-load.
        client = openai.OpenAI(base_url=endpoint, api_key="ollama", timeout=httpx.Timeout(300.0, connect=15.0))
    
    # Initialize messages
    messages = [
        {
            "role": "system", 
            "content": (
                "You are Akasha Executive Copilot, the Chief Project Intelligence Assistant for Adani Portfolio Leadership (Group Executive Office, Managing Director, and PMAG - Project Management & Assurance Group).\n"
                "You have access to live cross-system telemetry querying P6 (Schedule), SAP (Procurement), TC (Transmission), Quality & RFIs (Pulse NC/RFI), E-Invoices (SLR), Drone Surveys, and Project Story Intelligence.\n"
                "TOOL CALLING DIRECTIVES:\n"
                "- If a user asks about a project by name, ALWAYS call `portfolio_resolve_project_id` first to get the canonical ID and project name.\n"
                "- If a user asks about overall project health, story, risks, contractor delay rankings, or root causes, call `project_get_story_and_health`.\n"
                "- If a user asks why an activity is delayed or what caused a schedule slippage, call `project_investigate_activity`.\n"
                "- If a user asks about system disconnects, blindspots, or discrepancy gaps (Case A-E), call `project_get_gaps_and_discrepancies`.\n"
                "- If a user asks for quality NCs, defects, or quality issues, call `pulse_get_quality_issues`.\n"
                "- If a user asks about site inspections, RFIs, or hold points, call `pulse_get_rfis`.\n"
                "- If a user asks about contractor invoices, payment blocks, or SLR status, call `invoice_get_slr_status`.\n"
                "- If a user asks to verify progress using drone flights or aerial surveys, call `drone_verify_progress`.\n"
                "- If a user asks for a report, export, PDF, Word document, or formal briefing, you MUST call `generate_project_docx_report`. Present BOTH download links using the exact URLs returned by the tool (`docx_download_url` and `pdf_download_url`):\n"
                "  - `[📥 Download Adani Executive Report (PDF)](docx_download_url)`\n"
                "  - `[📄 Download Adani Executive Report (Word DOCX)](pdf_download_url)`\n"
                "  CRITICAL SAFETY: NEVER invent, hallucinate, or guess URLs (never use `.example`). Only output download links if `generate_project_docx_report` was called.\n"
                "- If a user asks to draft an email, notice of delay, cure letter, or escalation memo, call `draft_stakeholder_email`.\n"
                "- If a user asks about alerts or notifications, call `portfolio_get_notifications`.\n"
                "- Use the tools step-by-step to gather the data you need to answer the user's question.\n"
                "- Once you have enough data, provide a comprehensive, analytical final answer to the user in markdown.\n"
                "EXECUTIVE WRITING & PRESENTATION STANDARDS (ADANI PMAG / C-SUITE STANDARD):\n"
                "- If the user asks a general question (like 'what can you do?', 'who are you?', or 'hi', 'hello'), DO NOT call any tools. Be conversational, interactive, and friendly. Explain your capabilities clearly.\n"
                "- Persona & Tone: Write with the authority, rigor, and clarity of a Senior Infrastructure Partner presenting to the Group Managing Director. Be direct, factual, and analytical.\n"
                "- AVOID all AI clichés (e.g., \"It is important to note,\" \"Furthermore,\" \"Delve,\" \"In conclusion\", \"Based on the provided data\").\n"
                "- MANDATORY MARKDOWN TABLES: When presenting rankings, multiple activities, root causes, contractors, or invoices, ALWAYS format them as neat markdown tables with clear column headers.\n"
                "- Get straight to the point. Give the exact numbers requested.\n"
                "- Use bold text to highlight key metrics or variances to make it easy for leadership to read.\n"
                "- When discussing DELAYED TRANSMISSION LINES, always show 'days delayed' and 'affected projects' instead of schedule 'float'. Do not mention float unless specifically asked about P6 schedules.\n"
                "- ALWAYS refer to projects by their project_name (human-readable name), NEVER by project_id or internal IDs in your final answer.\n"
                "- Quantities in SAP are absolute units, not Megawatts (MW). Durations are in integer hours.\n"
                "- Do NOT report arbitrary synthetic scores or status ratings (e.g., 41.5/100). Focus on tangible variances, critical path slippage, and commercial capex at risk.\n"
                "VISUALIZATIONS:\n"
                "- You can draw charts with the `render_chart` tool; they appear inline in the chat. Use it when the user asks for a chart/graph/visual/plot, or when a chart communicates the answer better than text.\n"
                "- YOU pick the chart_type that best fits the data. If the user explicitly asked for a specific format, use that. Use chart_type='auto' to let the system choose.\n"
                "- The chart's data is pulled from the database automatically — never invent chart values. Resolve the project name to its project_id first, then call render_chart.\n"
                "- After a chart renders, briefly say in words what it shows. If render_chart returns status 'no_data', tell the user plainly instead of describing a chart that wasn't drawn.\n"
                "FORECASTS / FUTURE QUESTIONS:\n"
                "- For forward-looking questions ('when will X finish?', 'expected completion month', 'will it slip?', 'on track for commissioning?', 'forecast vs baseline'), CALL `sim_forecast_completion`.\n"
                "SCHEDULE PERFORMANCE / KPIs:\n"
                "- For SPI, schedule variance, physical progress, risk, or project health, ALWAYS call `get_project_kpis` (single project) or `portfolio_get_riskiest_projects` (portfolio).\n"
                "- Do NOT report SPI, float, or % complete from `p6_get_project_summary`.\n"
                "EXECUTIVE DIRECTIVES & NEXT STEPS:\n"
                "- At the end of every analysis, conclude with `### 💡 Executive Directives & Suggested Interventions` providing 3 concrete, high-value recommendations with designated owner roles and turnaround SLAs."
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
            yield {"type": "tools_used", "tools": list(tools_used)}
            
            # Stream the final answer that the model already computed in this loop iteration.
            # We do NOT re-call the LLM here — doing so caused local models (Ollama/Groq) to
            # emit raw XML function-call syntax instead of the answer because the messages array
            # contains "tool" role entries that some models misinterpret when asked to stream.
            final_content = response_message.content or ""
            final_content = sanitize_executive_response(final_content)
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

            try:
                args = json.loads(tool_call.function.arguments)
            except Exception:
                args = {}

            if tool_name == "render_chart":
                # Build the chart from real DB data, stream the spec straight to the UI, and
                # feed the LLM only a compact confirmation (never the full option JSON).
                spec, result_str = build_chart_result(db, args)
                if spec is not None:
                    yield {
                        "type": "visualization",
                        "chart_type": spec.get("chart_type"),
                        "title": spec.get("title"),
                        "spec": spec.get("option"),
                    }
            else:
                result_str = execute_tool(db, tool_name, args)

            messages.append({
                "tool_call_id": tool_call.id,
                "role": "tool",
                "name": tool_name,
                "content": result_str,
            })

    yield {"type": "tools_used", "tools": list(tools_used)}
    yield "Deep analysis timed out. I was able to gather some data but could not synthesize a final answer in time. Try asking a more specific question."
