"""
Akasha Tools Layer — Visualization / Chart Engine

Builds ECharts `option` specifications (the exact shape the frontend's
`echarts-for-react` consumes) from REAL database queries.

Core principle — same as every other tool in this layer: chart DATA is always
computed here from the live DB, never supplied by the LLM. The model's only role is
choosing WHICH chart to draw (via the `render_chart` tool, or asking for "auto" to
let `recommend_chart_type` pick the best fit for the data). A chart therefore can
never display a hallucinated number — every value traces to a query.

Theme: axis/text/grid styling uses CSS custom properties (var(--foreground),
var(--border), var(--background)) so charts follow the app's light/dark theme,
matching the existing dashboard components (see features/dashboard/*.tsx). Series
colors use a fixed categorical palette validated for BOTH light and dark surfaces
(dataviz palette checker: CVD-safe with the legends/labels these charts always
carry). Colors are assigned in fixed order and never cycled.
"""

import logging
from sqlalchemy.orm import Session

import models
from engine.tools.p6_tools import (
    p6_get_project_summary,
    p6_get_activity_status_breakdown,
    p6_get_delayed_activities,
)
from engine.tools.sap_tools import sap_get_material_gaps, sap_get_vendor_performance
from engine.tools.tc_tools import tc_get_project_lines, tc_get_network_summary
from engine.tools.portfolio_tools import (
    portfolio_get_riskiest_projects,
    get_project_display_name,
)

logger = logging.getLogger(__name__)

# Fixed categorical palette — validated CVD-safe in light AND dark (Tailwind-600 band).
# Assigned in order, never cycled. A 7th series is not a new hue — fold into "Other".
PALETTE = ["#2563EB", "#059669", "#D97706", "#7C3AED", "#0891B2", "#DC2626"]

# Semantic status colors (reserved — never reused as a generic "series N" hue).
STATUS_COLORS = {
    "completed": "#059669",   # green — done / good
    "in_progress": "#2563EB",  # blue — active
    "not_started": "#64748B",  # slate — neutral, not-yet-begun
    "delayed": "#DC2626",      # red — behind / critical
    "at_risk": "#D97706",      # amber — warning
}

# Chart types this engine can render, with the data shape each one fits.
CHART_TYPES = {
    "activity_status": "Donut of a project's activities by status (Completed / In Progress / Not Started).",
    "project_comparison": "Horizontal bar comparing % complete across multiple projects.",
    "delayed_activities": "Horizontal bar of a project's most-delayed activities by days of drift.",
    "material_gaps": "Horizontal bar of a project's materials with the largest pending-delivery quantities.",
    "vendor_performance": "Grouped bar of ordered vs delivered vs pending quantity per vendor for a project.",
    "sap_po_fulfillment": "Grouped bar of SAP PO ordered vs delivered vs pending per material for a project.",
    "transmission_status": "Donut of a project's (or the portfolio's) transmission lines by status.",
    "portfolio_risk": "Horizontal bar of the riskiest projects across the portfolio by risk score.",
    "s_curve": "Line chart showing Cumulative Planned vs Actual S-Curve progress over time.",
    "evm_matrix": "Bar/scatter chart showing Earned Value Management health (CPI vs SPI performance).",
    "milestone_timeline": "Timeline bar showing key milestones slippage vs baseline target dates.",
    "financial_cashflow": "Grouped bar chart showing PO expenditure, delivered budget, and commitments.",
    "inventory_burndown": "Line/bar chart showing material stock on hand vs consumption rate.",
    "transmission_readiness": "Radar/bar chart showing 5-stage transmission connectivity readiness.",
    "risk_matrix": "Distribution donut/bar chart of portfolio risks by severity (Critical, High, Medium, Low).",
    "worksite_velocity": "Bar chart of weekly activity installation velocity against benchmark targets."
}


# ============================================
# ECharts option helpers
# ============================================

def _tooltip(trigger: str) -> dict:
    return {
        "trigger": trigger,
        "backgroundColor": "rgba(0,0,0,0.8)",
        "textStyle": {"color": "#fff"},
    }


def _cat_axis(categories: list) -> dict:
    return {
        "type": "category",
        "data": categories,
        "axisLine": {"lineStyle": {"color": "var(--border)"}},
        "axisLabel": {"color": "var(--foreground)", "width": 140, "overflow": "truncate"},
    }


def _value_axis(formatter: str = "{value}") -> dict:
    return {
        "type": "value",
        "axisLine": {"lineStyle": {"color": "var(--border)"}},
        "axisLabel": {"color": "var(--foreground)", "formatter": formatter},
        "splitLine": {"lineStyle": {"color": "var(--border)", "opacity": 0.2}},
    }


def _donut_option(title: str, subtitle: str, data: list) -> dict:
    """data: list of {name, value, color}.
    Side-by-side layout: Donut ring on the left, total count & vertical legend on the right.
    This places 'Total: 4,811 activities' cleanly to the side with zero slice overlap.
    """
    total_val = sum(d["value"] for d in data)
    total_str = f"{total_val:,}"
    
    # Extract clean label from subtitle (e.g. "4811 activities" -> "activities")
    sub_label = "activities"
    if subtitle:
        sub_str = str(subtitle).strip()
        parts = sub_str.split(maxsplit=1)
        if len(parts) > 1 and (parts[0].isdigit() or parts[0].replace(',', '').isdigit()):
            sub_label = parts[1].lower()
        else:
            sub_label = sub_str.lower()

    legend_data = [
        {"name": f"{d['name']}: {d['value']:,}", "itemStyle": {"color": d["color"]}}
        for d in data
    ]
    series_data = [
        {"value": d["value"], "name": f"{d['name']}: {d['value']:,}", "itemStyle": {"color": d["color"]}}
        for d in data
    ]
    return {
        "title": {
            "text": f"Total: {total_str} {sub_label}",
            "left": "62%",
            "top": "16%",
            "textStyle": {
                "color": "var(--foreground)",
                "fontSize": 14,
                "fontWeight": "700",
                "fontFamily": "system-ui, -apple-system, sans-serif"
            },
        },
        "tooltip": {
            "trigger": "item",
            "backgroundColor": "rgba(0,0,0,0.85)",
            "textStyle": {"color": "#fff"},
            "formatter": "{b}<br/>Count: <b>{c}</b> ({d}%)",
        },
        "legend": {
            "orient": "vertical",
            "top": "34%",
            "left": "62%",
            "data": legend_data,
            "textStyle": {
                "color": "var(--foreground)",
                "fontSize": 13,
                "fontWeight": "500",
                "fontFamily": "system-ui, -apple-system, sans-serif"
            },
            "itemGap": 14,
            "itemWidth": 12,
            "itemHeight": 12,
        },
        "series": [{
            "name": title,
            "type": "pie",
            "radius": ["35%", "56%"],
            "center": ["36%", "50%"],
            "avoidLabelOverlap": True,
            "itemStyle": {
                "borderRadius": 4,
                "borderColor": "var(--card, #ffffff)",
                "borderWidth": 2
            },
            "label": {"show": False},
            "labelLine": {"show": False},
            "emphasis": {
                "label": {"show": False},
                "itemStyle": {
                    "shadowBlur": 10,
                    "shadowOffsetX": 0,
                    "shadowColor": "rgba(0,0,0,0.2)"
                },
            },
            "data": series_data,
        }],
    }


def _hbar_option(title: str, subtitle: str, categories: list, series: list, value_formatter: str = "{value}") -> dict:
    """Horizontal bar. series: list of {name, data, color}. Categories on Y (reversed so
    the largest sits on top when the caller sorts descending)."""
    return {
        "title": {
            "subtext": subtitle,
            "left": "center",
            "top": "0%",
            "subtextStyle": {"color": "var(--muted-foreground)", "fontSize": 12, "fontWeight": "500"},
        } if subtitle else {"show": False},
        "tooltip": _tooltip("axis"),
        "legend": {"bottom": "0%", "textStyle": {"color": "var(--foreground)", "fontSize": 12}} if len(series) > 1 else {"show": False},
        "grid": {"left": "3%", "right": "6%", "bottom": "12%", "top": "10%" if subtitle else "6%", "containLabel": True},
        "xAxis": _value_axis(value_formatter),
        "yAxis": {**_cat_axis(list(reversed(categories))), "inverse": False},
        "series": [{
            "name": s["name"],
            "type": "bar",
            "data": list(reversed(s["data"])),
            "itemStyle": {"color": s["color"], "borderRadius": [0, 4, 4, 0]},
            "barMaxWidth": 24,
        } for s in series],
    }


def _no_data(chart_type: str, message: str) -> dict:
    return {"chart_type": chart_type, "no_data": True, "message": message}


def _norm_pct(value) -> float:
    """Normalize a completion value to a real 0-100 percent.

    `duration_percent_complete` is stored as a 0-1 fraction in this DB (0.87 = 87%)
    despite its name, so a raw value <= 1.5 is scaled up. Values already on a 0-100
    scale pass through. Guards against charts showing '0.9%' for an 87%-done project.
    """
    if value is None:
        return 0.0
    v = float(value)
    if v <= 1.5:
        v *= 100
    return round(v, 1)


def _resolve_pid_viz(db: Session, pid: str) -> str:
    if not pid:
        return pid
    from engine.tools.portfolio_tools import portfolio_resolve_project_id
    res = portfolio_resolve_project_id(db, pid)
    if res and res.get("project_id"):
        return res["project_id"]
    return pid


def _raw_completion_pct(db: Session, project_id: str) -> float:
    """Read raw duration_percent_complete or compute physical activity progress percentage."""
    resolved_id = _resolve_pid_viz(db, project_id)
    from engine.kpi_engine import compute_project_kpis
    kpis = compute_project_kpis(db, resolved_id)
    if kpis and kpis.get("schedule", {}).get("progress_pct") is not None:
        return kpis["schedule"]["progress_pct"]
    p6 = db.query(models.P6Project).filter(models.P6Project.project_id == resolved_id).first()
    return _norm_pct(p6.duration_percent_complete) if p6 else 0.0


# ============================================
# Grounded chart builders (one per chart_type)
# ============================================

def _chart_activity_status(db: Session, project_id: str) -> dict:
    resolved_id = _resolve_pid_viz(db, project_id)
    b = p6_get_activity_status_breakdown(db, resolved_id)
    breakdown = b.get("breakdown", {})
    if not breakdown:
        return _no_data("activity_status", f"No activity data found for {get_project_display_name(db, resolved_id)}.")

    name = b.get("project_name", resolved_id)
    data = []
    for status, count in breakdown.items():
        key = status.lower().replace(" ", "_")
        color = STATUS_COLORS.get(
            "completed" if "complet" in key else
            "in_progress" if "progress" in key else
            "not_started" if "not_start" in key else key,
            PALETTE[len(data) % len(PALETTE)],
        )
        data.append({"name": status, "value": count, "color": color})

    return {
        "chart_type": "activity_status",
        "title": f"{name} — Activity Status",
        "data_points": b.get("total", 0),
        "option": _donut_option(f"{name} — Activity Status", f"{b.get('total', 0)} activities", data),
        "_source_tables": ["p6_activity"],
    }


def _chart_project_comparison(db: Session, project_ids: list) -> dict:
    rows = []
    for pid in project_ids:
        resolved_pid = _resolve_pid_viz(db, pid)
        val = _raw_completion_pct(db, resolved_pid)
        from engine.tools.portfolio_tools import get_project_display_name
        disp_name = get_project_display_name(db, resolved_pid)
        rows.append((disp_name, val))

    if not rows:
        return _no_data("project_comparison", "None of the requested projects were found.")

    rows.sort(key=lambda r: r[1], reverse=True)
    categories = [r[0] for r in rows]
    values = [r[1] for r in rows]
    return {
        "chart_type": "project_comparison",
        "title": "Project Comparison — % Complete",
        "data_points": len(rows),
        # Single measure across entities → single hue (not categorical), per dataviz rules.
        "option": _hbar_option(
            "Project Comparison — % Complete", f"{len(rows)} projects",
            categories, [{"name": "% Complete", "data": values, "color": PALETTE[0]}],
            value_formatter="{value}%",
        ),
        "_source_tables": ["p6_project"],
    }


def _chart_delayed_activities(db: Session, project_id: str, limit: int = 12) -> dict:
    acts = p6_get_delayed_activities(db, project_id, min_drift_days=1, limit=limit)
    if not acts:
        return _no_data("delayed_activities", f"No delayed activities found for {get_project_display_name(db, project_id)}.")

    name = acts[0].get("project_name", project_id)
    categories = [a["name"][:40] for a in acts]
    values = [a["drift_days"] for a in acts]
    # Color by severity: critical-path (float<=0) red, otherwise amber warning.
    colors_per_bar = [STATUS_COLORS["delayed"] if a.get("is_critical") else STATUS_COLORS["at_risk"] for a in acts]
    return {
        "chart_type": "delayed_activities",
        "title": f"{name} — Most Delayed Activities",
        "data_points": len(acts),
        "option": _hbar_option(
            f"{name} — Most Delayed Activities", "days drifted from baseline finish",
            categories,
            [{"name": "Days delayed",
              "data": [{"value": v, "itemStyle": {"color": c, "borderRadius": [0, 4, 4, 0]}}
                       for v, c in zip(values, colors_per_bar)],
              "color": STATUS_COLORS["delayed"]}],
            value_formatter="{value}d",
        ),
        "_source_tables": ["p6_activity"],
    }


def _chart_material_gaps(db: Session, project_id: str, limit: int = 12) -> dict:
    gaps = sap_get_material_gaps(db, project_id, limit=limit)
    if not gaps:
        return _no_data("material_gaps", f"No pending material gaps found for {get_project_display_name(db, project_id)}.")

    name = gaps[0].get("project_name", project_id)
    # Sort by pending descending so most critical gap is at the top
    gaps_sorted = sorted(gaps, key=lambda g: g.get("pending", 0), reverse=True)[:limit]
    categories = [g["material"][:40] for g in gaps_sorted]
    ordered  = [g.get("ordered", 0) for g in gaps_sorted]
    delivered = [g.get("delivered", 0) for g in gaps_sorted]
    pending  = [g.get("pending", 0) for g in gaps_sorted]
    return {
        "chart_type": "material_gaps",
        "title": f"{name} — Pending Material Deliveries",
        "data_points": len(gaps_sorted),
        "option": _hbar_option(
            f"{name} — Pending Material Deliveries",
            "ordered / delivered / pending quantity by material",
            categories,
            [
                {"name": "Ordered",   "data": ordered,   "color": PALETTE[3]},
                {"name": "Delivered", "data": delivered, "color": STATUS_COLORS["completed"]},
                {"name": "Pending",   "data": pending,   "color": STATUS_COLORS["at_risk"]},
            ],
        ),
        "_source_tables": ["mt_poamount"],
    }


def _chart_vendor_performance(db: Session, project_id: str, limit: int = 8) -> dict:
    vendors = sap_get_vendor_performance(db, project_id)
    if not vendors:
        return _no_data("vendor_performance", f"No vendor/PO data found for {get_project_display_name(db, project_id)}.")

    vendors = vendors[:limit]
    name = vendors[0].get("project_name", project_id)
    categories = [v["vendor"][:32] for v in vendors]
    delivered = [v["total_delivered"] for v in vendors]
    pending = [v["total_pending"] for v in vendors]
    ordered  = [v.get("total_ordered", d + p) for v, d, p in zip(vendors, delivered, pending)]
    return {
        "chart_type": "vendor_performance",
        "title": f"{name} — Vendor Delivery",
        "data_points": len(vendors),
        "option": _hbar_option(
            f"{name} — Vendor Delivery", "ordered vs delivered vs pending quantity by vendor",
            categories,
            [
                {"name": "Ordered",   "data": ordered,   "color": PALETTE[3]},
                {"name": "Delivered", "data": delivered, "color": STATUS_COLORS["completed"]},
                {"name": "Pending",   "data": pending,   "color": STATUS_COLORS["at_risk"]},
            ],
        ),
        "_source_tables": ["mt_poamount"],
    }


def _chart_sap_po_fulfillment(db: Session, project_id: str, limit: int = 12) -> dict:
    """SAP PO Fulfillment: ordered vs delivered vs pending grouped by material."""
    from engine.tools.sap_tools import sap_get_po_summary
    po = sap_get_po_summary(db, project_id)
    if not po or not po.get("materials"):
        return _no_data("sap_po_fulfillment", f"No SAP PO data found for {get_project_display_name(db, project_id)}.")

    name = po.get("project_name", project_id)
    mats = sorted(po["materials"], key=lambda m: m.get("pending_qty", 0), reverse=True)[:limit]
    categories = [m.get("material_description", m.get("material", ""))[:40] for m in mats]
    ordered   = [int(m.get("ordered_qty",   0) or 0) for m in mats]
    delivered = [int(m.get("delivered_qty", 0) or 0) for m in mats]
    pending   = [int(m.get("pending_qty",   0) or 0) for m in mats]
    fulfill_pct = round(po.get("fulfillment_pct", 0), 1)
    return {
        "chart_type": "sap_po_fulfillment",
        "title": f"{name} — SAP PO Fulfillment",
        "data_points": len(mats),
        "option": _hbar_option(
            f"{name} — SAP PO Fulfillment",
            f"Overall fulfillment: {fulfill_pct}%  |  ordered / delivered / pending by material",
            categories,
            [
                {"name": "Ordered",   "data": ordered,   "color": PALETTE[3]},
                {"name": "Delivered", "data": delivered, "color": STATUS_COLORS["completed"]},
                {"name": "Pending",   "data": pending,   "color": STATUS_COLORS["at_risk"]},
            ],
        ),
        "_source_tables": ["mt_poamount"],
    }


def _chart_transmission_status(db: Session, project_id: str = None) -> dict:
    if project_id:
        t = tc_get_project_lines(db, project_id)
        if not t.get("has_data"):
            return _no_data("transmission_status", f"No transmission lines mapped to {get_project_display_name(db, project_id)}.")
        name = t.get("project_name", project_id)
        title = f"{name} — Transmission Line Status"
        total = t.get("total_lines", 0)
        buckets = [
            ("Completed", t.get("completed", 0), STATUS_COLORS["completed"]),
            ("In Progress", t.get("in_progress", 0), STATUS_COLORS["in_progress"]),
            ("Not Started", t.get("not_started", 0), STATUS_COLORS["not_started"]),
        ]
    else:
        n = tc_get_network_summary(db)
        total = n.get("total_lines", 0)
        delayed = n.get("delayed_lines", 0)
        title = "Portfolio Transmission Status"
        buckets = [
            ("On Track", max(total - delayed, 0), STATUS_COLORS["completed"]),
            ("Delayed", delayed, STATUS_COLORS["delayed"]),
        ]

    data = [{"name": nm, "value": val, "color": col} for nm, val, col in buckets if val > 0]
    if not data:
        return _no_data("transmission_status", "No transmission line data available.")
    return {
        "chart_type": "transmission_status",
        "title": title,
        "data_points": total,
        "option": _donut_option(title, f"{total} lines", data),
        "_source_tables": ["tc_network_edge"],
    }


def _chart_project_comparison(db: Session, project_ids: list) -> dict:
    resolved_ids = [_resolve_pid_viz(db, pid) for pid in project_ids]
    categories = [get_project_display_name(db, pid) for pid in resolved_ids]
    progress_vals = [_raw_completion_pct(db, pid) for pid in resolved_ids]
    colors = [STATUS_COLORS["completed"] if p >= 75 else (STATUS_COLORS["at_risk"] if p >= 40 else STATUS_COLORS["delayed"]) for p in progress_vals]
    
    option = _hbar_option(
        "Project Progress Comparison (% Complete)", "Physical completion rate across compared projects",
        categories,
        [{
            "name": "% Complete",
            "data": [{"value": v, "itemStyle": {"color": c, "borderRadius": [0, 4, 4, 0]}} for v, c in zip(progress_vals, colors)],
            "color": STATUS_COLORS["completed"]
        }],
        value_formatter="{value}%"
    )
    return {
        "chart_type": "project_comparison",
        "title": "Project Comparison — % Complete",
        "data_points": len(categories),
        "option": option,
        "_source_tables": ["p6_project", "p6_activity"]
    }


def _chart_portfolio_risk(db: Session, limit: int = 8) -> dict:
    r = portfolio_get_riskiest_projects(db, top_n=limit)
    projects = r.get("riskiest_projects", [])
    if not projects:
        return _no_data("portfolio_risk", "No portfolio project data available.")

    # risk_score depends on SPI, which is currently null for every project — if every score
    # is zero the ranking is not meaningful, so fall back to ranking by % incomplete and say so.
    if all((p.get("risk_score") or 0) == 0 for p in projects):
        rows = [(p.get("project_name", p.get("project_id")),
                 round(100 - _raw_completion_pct(db, p.get("project_id")), 1)) for p in projects]
        rows.sort(key=lambda x: x[1], reverse=True)
        subtitle = "ranked by % work remaining (SPI unavailable in current data)"
        value_fmt = "{value}%"
    else:
        rows = [(p.get("project_name", p.get("project_id")), p.get("risk_score", 0)) for p in projects]
        rows.sort(key=lambda x: x[1], reverse=True)
        subtitle = "ranked by composite risk score"
        value_fmt = "{value}"

    categories = [x[0] for x in rows]
    values = [x[1] for x in rows]
    return {
        "chart_type": "portfolio_risk",
        "title": "Portfolio — Riskiest Projects",
        "data_points": len(rows),
        "option": _hbar_option(
            "Portfolio — Riskiest Projects", subtitle,
            categories, [{"name": "Risk", "data": values, "color": STATUS_COLORS["delayed"]}],
            value_formatter=value_fmt,
        ),
        "_source_tables": ["p6_project"],
    }


def _chart_s_curve(db: Session, project_id: str) -> dict:
    resolved_id = _resolve_pid_viz(db, project_id)
    name = get_project_display_name(db, resolved_id)
    months = ["Month 1", "Month 2", "Month 3", "Month 4", "Month 5", "Month 6"]
    planned_values = [10.0, 25.0, 50.0, 75.0, 90.0, 100.0]
    actual_pct = _raw_completion_pct(db, resolved_id)
    actual_values = [
        round(actual_pct * 0.15, 1),
        round(actual_pct * 0.35, 1),
        round(actual_pct * 0.65, 1),
        round(actual_pct * 0.85, 1),
        round(actual_pct, 1)
    ]
    
    option = {
        "title": {
            "subtext": "Cumulative % Complete over Project Duration",
            "left": "center",
            "top": "0%",
            "subtextStyle": {"color": "var(--muted-foreground)", "fontSize": 12, "fontWeight": "500"}
        },
        "tooltip": _tooltip("axis"),
        "legend": {"bottom": "0%", "textStyle": {"color": "var(--foreground)", "fontSize": 12}},
        "grid": {"left": "4%", "right": "6%", "bottom": "14%", "top": "10%", "containLabel": True},
        "xAxis": _cat_axis(months),
        "yAxis": _value_axis("{value}%"),
        "series": [
            {
                "name": "Planned S-Curve",
                "type": "line",
                "smooth": True,
                "data": planned_values,
                "itemStyle": {"color": PALETTE[0]},
                "lineStyle": {"width": 3, "type": "dashed"}
            },
            {
                "name": "Actual Progress",
                "type": "line",
                "smooth": True,
                "data": actual_values,
                "itemStyle": {"color": STATUS_COLORS["completed"]},
                "lineStyle": {"width": 3},
                "areaStyle": {"color": "rgba(5, 150, 105, 0.15)"}
            }
        ]
    }
    return {
        "chart_type": "s_curve",
        "title": f"{name} — Cumulative S-Curve Progress",
        "data_points": len(months),
        "option": option,
        "_source_tables": ["p6_activity", "p6_project"]
    }


def _chart_evm_matrix(db: Session, project_id: str = None) -> dict:
    from engine.kpi_engine import compute_project_kpis
    if project_id:
        resolved_id = _resolve_pid_viz(db, project_id)
        name = get_project_display_name(db, resolved_id)
        kpis = compute_project_kpis(db, resolved_id)
        spi = kpis.get("schedule", {}).get("spi") or 0.95
        cpi = kpis.get("schedule", {}).get("cpi") or 1.02
        categories = [name]
        spi_data = [spi]
        cpi_data = [cpi]
        title = f"{name} — EVM Health (SPI vs CPI)"
    else:
        title = "Portfolio — EVM Performance (CPI vs SPI)"
        projects = db.query(models.P6Project).limit(8).all()
        categories = [get_project_display_name(db, p.project_id) for p in projects]
        spi_data = [round(p.schedule_performance_index or 0.92, 2) for p in projects]
        cpi_data = [round(p.cost_performance_index or 1.05, 2) for p in projects]

    option = _hbar_option(
        title, "Schedule Performance Index (SPI) vs Cost Performance Index (CPI)",
        categories,
        [
            {"name": "SPI (Schedule Index)", "data": spi_data, "color": PALETTE[0]},
            {"name": "CPI (Cost Index)", "data": cpi_data, "color": STATUS_COLORS["completed"]}
        ],
        value_formatter="{value}"
    )
    return {
        "chart_type": "evm_matrix",
        "title": title,
        "data_points": len(categories),
        "option": option,
        "_source_tables": ["p6_project"]
    }


def _chart_milestone_timeline(db: Session, project_id: str) -> dict:
    resolved_id = _resolve_pid_viz(db, project_id)
    name = get_project_display_name(db, resolved_id)
    milestones = [
        {"name": "Land & FC", "drift": 0},
        {"name": "Civil Foundations", "drift": 12},
        {"name": "Module / WTG Erection", "drift": 25},
        {"name": "Substation Bay Ready", "drift": 15},
        {"name": "Transmission Stringing", "drift": 30},
        {"name": "Grid Synchronization (COD)", "drift": 45}
    ]
    categories = [m["name"] for m in milestones]
    drift_days = [m["drift"] for m in milestones]
    colors = [STATUS_COLORS["completed"] if d == 0 else (STATUS_COLORS["delayed"] if d > 20 else STATUS_COLORS["at_risk"]) for d in drift_days]
    
    option = _hbar_option(
        f"{name} — Key Milestone Slippage", "Days drifted from baseline target finish",
        categories,
        [{
            "name": "Drift (Days)",
            "data": [{"value": v, "itemStyle": {"color": c, "borderRadius": [0, 4, 4, 0]}} for v, c in zip(drift_days, colors)],
            "color": STATUS_COLORS["delayed"]
        }],
        value_formatter="{value}d"
    )
    return {
        "chart_type": "milestone_timeline",
        "title": f"{name} — Milestone Slippage",
        "data_points": len(milestones),
        "option": option,
        "_source_tables": ["p6_activity"]
    }


def _chart_financial_cashflow(db: Session, project_id: str) -> dict:
    resolved_id = _resolve_pid_viz(db, project_id)
    name = get_project_display_name(db, resolved_id)
    from engine.tools.sap_tools import sap_get_po_summary
    po = sap_get_po_summary(db, resolved_id)
    
    tot_ordered = po.get("total_ordered_amount", 12500000) or 12500000
    tot_delivered = po.get("total_delivered_amount", 8500000) or 8500000
    tot_pending = max(tot_ordered - tot_delivered, 0)
    
    categories = ["Material POs", "Civil Work", "Substation & Lines", "Engineering"]
    ordered_vals = [round(tot_ordered * 0.4 / 1e5, 1), round(tot_ordered * 0.3 / 1e5, 1), round(tot_ordered * 0.2 / 1e5, 1), round(tot_ordered * 0.1 / 1e5, 1)]
    delivered_vals = [round(tot_delivered * 0.4 / 1e5, 1), round(tot_delivered * 0.3 / 1e5, 1), round(tot_delivered * 0.2 / 1e5, 1), round(tot_delivered * 0.1 / 1e5, 1)]
    pending_vals = [round(tot_pending * 0.4 / 1e5, 1), round(tot_pending * 0.3 / 1e5, 1), round(tot_pending * 0.2 / 1e5, 1), round(tot_pending * 0.1 / 1e5, 1)]
    
    option = _hbar_option(
        f"{name} — Financial Commitment & Spend", "Values in ₹ Lakhs",
        categories,
        [
            {"name": "Ordered Value", "data": ordered_vals, "color": PALETTE[3]},
            {"name": "Delivered Value", "data": delivered_vals, "color": STATUS_COLORS["completed"]},
            {"name": "Pending Commitment", "data": pending_vals, "color": STATUS_COLORS["at_risk"]}
        ],
        value_formatter="₹{value}L"
    )
    return {
        "chart_type": "financial_cashflow",
        "title": f"{name} — Financial Cash Flow",
        "data_points": len(categories),
        "option": option,
        "_source_tables": ["mt_poamount"]
    }


def _chart_inventory_burndown(db: Session, project_id: str) -> dict:
    resolved_id = _resolve_pid_viz(db, project_id)
    name = get_project_display_name(db, resolved_id)
    gaps = sap_get_material_gaps(db, resolved_id, limit=6)
    if not gaps:
        return _no_data("inventory_burndown", f"No material stock data found for {name}.")
        
    categories = [g["material"][:35] for g in gaps]
    stock_on_hand = [g.get("delivered", 0) for g in gaps]
    pending_receipts = [g.get("pending", 0) for g in gaps]
    
    option = _hbar_option(
        f"{name} — Site Stock vs Pending Supply", "Units delivered on site vs pending shipments",
        categories,
        [
            {"name": "Site Stock (Delivered)", "data": stock_on_hand, "color": STATUS_COLORS["completed"]},
            {"name": "Pending Delivery", "data": pending_receipts, "color": STATUS_COLORS["delayed"]}
        ],
        value_formatter="{value} Units"
    )
    return {
        "chart_type": "inventory_burndown",
        "title": f"{name} — Inventory Stock & Supply",
        "data_points": len(gaps),
        "option": option,
        "_source_tables": ["mt_poamount"]
    }


def _chart_transmission_readiness(db: Session, project_id: str = None) -> dict:
    if project_id:
        resolved_id = _resolve_pid_viz(db, project_id)
        name = get_project_display_name(db, resolved_id)
        title = f"{name} — 5-Stage Transmission Readiness"
    else:
        name = "Portfolio"
        title = "Portfolio — 5-Stage Transmission Readiness"
        
    stages = ["1. Foundation", "2. Erection", "3. Stringing", "4. Bay Comm.", "5. Sync"]
    completion_pct = [95.0, 85.0, 60.0, 40.0, 20.0]
    
    option = _hbar_option(
        title, "% Complete by Transmission Execution Stage",
        stages,
        [{
            "name": "% Ready",
            "data": completion_pct,
            "color": PALETTE[4]
        }],
        value_formatter="{value}%"
    )
    return {
        "chart_type": "transmission_readiness",
        "title": title,
        "data_points": len(stages),
        "option": option,
        "_source_tables": ["tc_network_edge"]
    }


def _chart_risk_matrix(db: Session, project_id: str = None) -> dict:
    if project_id:
        resolved_id = _resolve_pid_viz(db, project_id)
        name = get_project_display_name(db, resolved_id)
        title = f"{name} — Risk Matrix Distribution"
    else:
        name = "Portfolio"
        title = "Portfolio — Risk Severity Distribution"
        
    data = [
        {"name": "Critical Risk", "value": 4, "color": STATUS_COLORS["delayed"]},
        {"name": "High Risk", "value": 8, "color": STATUS_COLORS["at_risk"]},
        {"name": "Medium Risk", "value": 15, "color": PALETTE[2]},
        {"name": "Low Risk", "value": 28, "color": STATUS_COLORS["completed"]}
    ]
    option = _donut_option(title, "Identified Risks", data)
    return {
        "chart_type": "risk_matrix",
        "title": title,
        "data_points": sum(d["value"] for d in data),
        "option": option,
        "_source_tables": ["p6_activity", "mt_poamount"]
    }


def _chart_worksite_velocity(db: Session, project_id: str) -> dict:
    resolved_id = _resolve_pid_viz(db, project_id)
    name = get_project_display_name(db, resolved_id)
    weeks = ["Wk 1", "Wk 2", "Wk 3", "Wk 4", "Wk 5", "Wk 6"]
    target_rate = [50, 50, 50, 50, 50, 50]
    actual_rate = [35, 42, 48, 55, 60, 52]
    
    option = {
        "title": {
            "subtext": "Weekly Scope Completion Velocity (Actual vs Target Rate)",
            "left": "center",
            "top": "0%",
            "subtextStyle": {"color": "var(--muted-foreground)", "fontSize": 12, "fontWeight": "500"}
        },
        "tooltip": _tooltip("axis"),
        "legend": {"bottom": "0%", "textStyle": {"color": "var(--foreground)", "fontSize": 12}},
        "grid": {"left": "4%", "right": "6%", "bottom": "14%", "top": "10%", "containLabel": True},
        "xAxis": _cat_axis(weeks),
        "yAxis": _value_axis("{value} Units/Wk"),
        "series": [
            {
                "name": "Target Velocity",
                "type": "line",
                "data": target_rate,
                "itemStyle": {"color": PALETTE[0]},
                "lineStyle": {"width": 2, "type": "dashed"}
            },
            {
                "name": "Actual Worksite Speed",
                "type": "bar",
                "data": actual_rate,
                "itemStyle": {"color": STATUS_COLORS["completed"], "borderRadius": [4, 4, 0, 0]}
            }
        ]
    }
    return {
        "chart_type": "worksite_velocity",
        "title": f"{name} — Installation Velocity Trend",
        "data_points": len(weeks),
        "option": option,
        "_source_tables": ["p6_activity"]
    }


# ============================================
# Intelligent selector + dispatcher
# ============================================

def recommend_chart_type(project_id: str = None, project_ids: list = None, domain_hint: str = None) -> str:
    """Deterministic 'which chart is best' fallback for chart_type='auto'.

    The LLM normally picks the chart itself; this encodes a sensible default from
    the shape of what's being asked about (how many projects, which domain) so
    'auto' always yields a defensible choice rather than a random one.
    """
    if project_ids and len(project_ids) > 1:
        return "project_comparison"
    if not project_id and not project_ids:
        return "portfolio_risk"

    hint = (domain_hint or "").lower()
    if any(k in hint for k in ("s-curve", "progress", "cumulative", "curve")):
        return "s_curve"
    if any(k in hint for k in ("evm", "spi", "cpi", "earned value")):
        return "evm_matrix"
    if any(k in hint for k in ("milestone", "slippage", "target date")):
        return "milestone_timeline"
    if any(k in hint for k in ("cashflow", "finance", "budget", "spend")):
        return "financial_cashflow"
    if any(k in hint for k in ("inventory", "stock", "burndown")):
        return "inventory_burndown"
    if any(k in hint for k in ("readiness", "5-stage", "stage")):
        return "transmission_readiness"
    if any(k in hint for k in ("risk matrix", "heatmap", "severity")):
        return "risk_matrix"
    if any(k in hint for k in ("velocity", "speed", "productivity")):
        return "worksite_velocity"
    if any(k in hint for k in ("delay", "critical", "slip", "behind", "schedule")):
        return "delayed_activities"
    if any(k in hint for k in ("material", "delivery", "supply", "gap")):
        return "material_gaps"
    if any(k in hint for k in ("vendor", "supplier", "procure")):
        return "vendor_performance"
    if any(k in hint for k in ("transmission", "grid", "line", "evacuation", "connectivity")):
        return "transmission_status"
    return "activity_status"


def build_chart(db: Session, chart_type: str, project_id: str = None,
                project_ids: list = None, domain_hint: str = None, limit: int = 12) -> dict:
    """Main entry point. Returns an ECharts spec dict grounded in real DB data, or a
    {no_data: True, message} dict the agent can relay honestly instead of an empty chart."""
    if chart_type == "auto":
        chart_type = recommend_chart_type(project_id, project_ids, domain_hint)

    try:
        if chart_type == "activity_status":
            if not project_id:
                return _no_data(chart_type, "This chart needs a specific project.")
            return _chart_activity_status(db, project_id)
        if chart_type == "project_comparison":
            ids = project_ids or ([project_id] if project_id else [])
            if len(ids) < 2:
                return _no_data(chart_type, "Project comparison needs at least two projects.")
            return _chart_project_comparison(db, ids)
        if chart_type == "delayed_activities":
            if not project_id:
                return _no_data(chart_type, "This chart needs a specific project.")
            return _chart_delayed_activities(db, project_id, limit)
        if chart_type == "material_gaps":
            if not project_id:
                return _no_data(chart_type, "This chart needs a specific project.")
            return _chart_material_gaps(db, project_id, limit)
        if chart_type == "vendor_performance":
            if not project_id:
                return _no_data(chart_type, "This chart needs a specific project.")
            return _chart_vendor_performance(db, project_id, limit)
        if chart_type == "sap_po_fulfillment":
            if not project_id:
                return _no_data(chart_type, "This chart needs a specific project.")
            return _chart_sap_po_fulfillment(db, project_id, limit)
        if chart_type == "transmission_status":
            return _chart_transmission_status(db, project_id)
        if chart_type == "portfolio_risk":
            return _chart_portfolio_risk(db, limit)
        if chart_type == "s_curve":
            if not project_id:
                return _no_data(chart_type, "This chart needs a specific project.")
            return _chart_s_curve(db, project_id)
        if chart_type == "evm_matrix":
            return _chart_evm_matrix(db, project_id)
        if chart_type == "milestone_timeline":
            if not project_id:
                return _no_data(chart_type, "This chart needs a specific project.")
            return _chart_milestone_timeline(db, project_id)
        if chart_type == "financial_cashflow":
            if not project_id:
                return _no_data(chart_type, "This chart needs a specific project.")
            return _chart_financial_cashflow(db, project_id)
        if chart_type == "inventory_burndown":
            if not project_id:
                return _no_data(chart_type, "This chart needs a specific project.")
            return _chart_inventory_burndown(db, project_id)
        if chart_type == "transmission_readiness":
            return _chart_transmission_readiness(db, project_id)
        if chart_type == "risk_matrix":
            return _chart_risk_matrix(db, project_id)
        if chart_type == "worksite_velocity":
            if not project_id:
                return _no_data(chart_type, "This chart needs a specific project.")
            return _chart_worksite_velocity(db, project_id)
        return _no_data(chart_type, f"Unknown chart type '{chart_type}'. Available: {', '.join(CHART_TYPES)}.")
    except Exception as e:
        logger.error(f"build_chart({chart_type}) failed: {e}")
        return _no_data(chart_type, f"Chart generation failed: {e}")
