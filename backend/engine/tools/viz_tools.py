"""
Akasha Tools Layer — Visualization / Chart Engine

Builds ECharts `option` specifications (the exact shape the frontend's
`echarts-for-react` consumes) from authoritative service datasets.

Core principle — same as every other tool in this layer: chart DATA is always
computed by shared services from the live DB, never supplied by the LLM. The model's only role is
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

from services.chart_spec_service import ChartSpecService
from services.capacity_milestone_service import CapacityMilestoneService
from services.project_catalog_service import ProjectCatalogService
from services.quality_analytics_service import QualityAnalyticsService
from services.schedule_metrics_service import ScheduleMetricsService
from services.visualization_spec import (
    VisualizationSeriesV1,
    VisualizationSpecV1,
    activity_composition_spec,
    baseline_slip_spec,
    block_progress_spec,
    daily_completion_spec,
    duration_comparison_spec,
    planned_vs_actual_progress_spec,
    portfolio_status_spec,
    project_progress_spec,
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
    "auto_dashboard": "Three or four domain-aware charts for broad 'show me' requests.",
    "activity_status": "Rose chart of a project's activities by status (Completed / In Progress / Not Started).",
    "project_comparison": "Horizontal bar comparing % complete across multiple projects.",
    "delayed_activities": "Horizontal bar of a project's most-delayed activities by days of drift.",
    "material_gaps": "Horizontal bar of a project's materials with the largest pending-delivery quantities.",
    "vendor_performance": "Grouped bar of ordered vs delivered vs pending quantity per vendor for a project.",
    "sap_po_fulfillment": "Grouped bar of SAP PO ordered vs delivered vs pending per material for a project.",
    "transmission_status": "Rose chart of a project's (or the portfolio's) transmission lines by status.",
    "portfolio_risk": "Lollipop ranking of the riskiest projects across the portfolio by risk score.",
    "daily_completion_trend": "Daily activity actual-finish events with cumulative completion-event context.",
    "planned_vs_actual_progress": "Cumulative planned versus actual activity-finish S-curve through the P6 data cutoff.",
    "block_progress": "Horizontal bar of the current average activity completion by project block.",
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


def _base_option(accessibility_description: str) -> dict:
    return {
        "animationDuration": 550,
        "animationEasing": "cubicOut",
        "aria": {
            "enabled": True,
            "decal": {"show": True},
            "description": accessibility_description,
        },
        "textStyle": {"fontFamily": "Inter, ui-sans-serif, system-ui, sans-serif"},
    }


def _donut_option(title: str, subtitle: str, data: list) -> dict:
    """data: list of {name, value, color}.
    Labels are disabled on the slices — crowded for thin segments.
    The tooltip and legend carry all the information instead.
    """
    # Add count to each legend label so values are visible even without slice labels
    legend_data = [
        {"name": f"{d['name']}: {d['value']}", "itemStyle": {"color": d["color"]}}
        for d in data
    ]
    series_data = [
        {"value": d["value"], "name": f"{d['name']}: {d['value']}", "itemStyle": {"color": d["color"]}}
        for d in data
    ]
    return {
        **_base_option(f"{title}. {subtitle}."),
        "title": {
            "text": title,
            "subtext": subtitle,
            "left": "center",
            "top": "4%",
            "textStyle": {"color": "var(--foreground)", "fontSize": 14, "fontWeight": "bold"},
            "subtextStyle": {"color": "var(--muted-foreground)", "fontSize": 12},
        },
        "tooltip": {
            "trigger": "item",
            "backgroundColor": "rgba(0,0,0,0.85)",
            "textStyle": {"color": "#fff"},
            "formatter": "{b}<br/>Count: <b>{c}</b>  ({d}%)",
        },
        "legend": {
            "bottom": "2%",
            "left": "center",
            "orient": "horizontal",
            "data": legend_data,
            "textStyle": {"color": "var(--foreground)", "fontSize": 12},
            "itemGap": 16,
        },
        "series": [{
            "name": title,
            "type": "pie",
            "radius": ["42%", "68%"],
            "center": ["50%", "48%"],
            "avoidLabelOverlap": True,
            "itemStyle": {"borderRadius": 6, "borderColor": "var(--background)", "borderWidth": 3},
            # Labels OFF on slices — tooltip + legend are sufficient and never overlap
            "label": {"show": False},
            "labelLine": {"show": False},
            "emphasis": {
                "label": {"show": True, "fontSize": 14, "fontWeight": "bold", "color": "var(--foreground)"},
                "itemStyle": {"shadowBlur": 10, "shadowOffsetX": 0, "shadowColor": "rgba(0,0,0,0.3)"},
            },
            "data": series_data,
        }],
    }


def _hbar_option(title: str, subtitle: str, categories: list, series: list, value_formatter: str = "{value}") -> dict:
    """Horizontal bar. series: list of {name, data, color}. Categories on Y (reversed so
    the largest sits on top when the caller sorts descending)."""
    return {
        **_base_option(f"{title}. {subtitle}."),
        "title": {
            "text": title,
            "subtext": subtitle,
            "left": "center",
            "textStyle": {"color": "var(--foreground)", "fontSize": 14},
            "subtextStyle": {"color": "var(--muted-foreground)", "fontSize": 12},
        },
        "tooltip": _tooltip("axis"),
        "legend": {"bottom": "0%", "textStyle": {"color": "var(--foreground)"}} if len(series) > 1 else {"show": False},
        "grid": {"left": "3%", "right": "6%", "bottom": "12%", "top": "18%", "containLabel": True},
        "xAxis": _value_axis(value_formatter),
        "yAxis": {**_cat_axis(list(reversed(categories))), "inverse": False},
        "series": [{
            "name": s["name"],
            "type": "bar",
            "data": list(reversed(s["data"])),
            "itemStyle": {"color": s["color"], "borderRadius": [0, 4, 4, 0]},
            "barMaxWidth": 26,
        } for s in series],
    }


def _no_data(chart_type: str, message: str) -> dict:
    return {"chart_type": chart_type, "no_data": True, "message": message}


def _finalize_chart(chart: dict) -> dict:
    """Apply the stable transport contract to every grounded chart builder."""
    if chart.get("no_data"):
        return chart
    title = chart.get("title") or "Akasha visualization"
    option = chart.get("option") or {}
    option.setdefault("aria", {
        "enabled": True,
        "decal": {"show": True},
        "description": chart.get("accessibility_description") or title,
    })
    subtitle = chart.get("subtitle")
    if not subtitle and isinstance(option.get("title"), dict):
        subtitle = option["title"].get("subtext")
    return {
        "schema_version": "visualization.v1",
        "summary": chart.get("summary") or f"Grounded {chart.get('chart_type', 'data')} visualization.",
        "subtitle": subtitle,
        "accessibility_description": (
            chart.get("accessibility_description")
            or option.get("aria", {}).get("description")
            or title
        ),
        "data_as_of": chart.get("data_as_of"),
        "data_table": chart.get("data_table") or [],
        **chart,
        "option": option,
    }


def _rose_option(title: str, subtitle: str, data: list) -> dict:
    """A compact polar-area view for small categorical status distributions."""
    series_data = [
        {"value": item["value"], "name": item["name"], "itemStyle": {"color": item["color"]}}
        for item in data
    ]
    return {
        **_base_option(f"{title}. {subtitle}."),
        "tooltip": {**_tooltip("item"), "formatter": "{b}<br/><b>{c}</b> ({d}%)"},
        "legend": {
            "bottom": 0,
            "left": "center",
            "textStyle": {"color": "var(--foreground)", "fontSize": 11},
        },
        "series": [{
            "name": title,
            "type": "pie",
            "roseType": "radius",
            "radius": [34, "68%"],
            "center": ["50%", "44%"],
            "minAngle": 8,
            "itemStyle": {
                "borderRadius": 9,
                "borderColor": "var(--card)",
                "borderWidth": 3,
            },
            "label": {
                "show": True,
                "color": "var(--foreground)",
                "formatter": "{b}\n{c}",
                "fontSize": 11,
            },
            "labelLine": {"length": 10, "length2": 8},
            "emphasis": {"scaleSize": 8},
            "data": series_data,
        }],
    }


def _lollipop_option(
    title: str,
    subtitle: str,
    categories: list,
    values: list,
    colors: list | None = None,
    value_formatter: str = "{value}",
) -> dict:
    """A low-ink ranking chart that emphasizes endpoints instead of heavy bars."""
    item_colors = colors or [PALETTE[0]] * len(values)
    points = [
        {
            "value": [value, index],
            "itemStyle": {"color": item_colors[index]},
            "label": {
                "show": True,
                "position": "right",
                "formatter": str(value) if value_formatter == "{value}" else f"{value}d",
                "color": "var(--foreground)",
                "fontWeight": 700,
            },
        }
        for index, value in enumerate(values)
    ]
    stems = [
        {"value": value, "itemStyle": {"color": item_colors[index], "opacity": 0.72}}
        for index, value in enumerate(values)
    ]
    return {
        **_base_option(f"{title}. {subtitle}."),
        "tooltip": _tooltip("axis"),
        "grid": {"left": "3%", "right": "12%", "top": 24, "bottom": 30, "containLabel": True},
        "xAxis": _value_axis(value_formatter),
        "yAxis": {**_cat_axis(categories), "inverse": True},
        "series": [
            {"name": title, "type": "bar", "data": stems, "barWidth": 4, "silent": True},
            {"name": title, "type": "scatter", "data": points, "symbolSize": 18, "z": 3},
        ],
    }


def _vertical_grouped_option(title: str, subtitle: str, categories: list, series: list) -> dict:
    """Grouped columns for side-by-side entity comparisons."""
    return {
        **_base_option(f"{title}. {subtitle}."),
        "tooltip": _tooltip("axis"),
        "legend": {"bottom": 0, "textStyle": {"color": "var(--foreground)"}},
        "grid": {"left": 44, "right": 20, "top": 24, "bottom": 78, "containLabel": True},
        "xAxis": {
            **_cat_axis(categories),
            "axisLabel": {
                "color": "var(--muted-foreground)",
                "width": 86,
                "overflow": "truncate",
                "rotate": 18 if len(categories) > 5 else 0,
            },
        },
        "yAxis": _value_axis(),
        "series": [{
            "name": item["name"],
            "type": "bar",
            "data": item["data"],
            "barMaxWidth": 30,
            "itemStyle": {"color": item["color"], "borderRadius": [7, 7, 0, 0]},
        } for item in series],
    }


def _fulfillment_option(title: str, subtitle: str, categories: list, delivered: list, pending: list) -> dict:
    """A 100%-meaningful stacked fulfillment bar: delivered plus pending equals ordered scope."""
    return {
        **_base_option(f"{title}. {subtitle}."),
        "tooltip": _tooltip("axis"),
        "legend": {"bottom": 0, "textStyle": {"color": "var(--foreground)"}},
        "grid": {"left": "3%", "right": "8%", "top": 24, "bottom": 44, "containLabel": True},
        "xAxis": _value_axis(),
        "yAxis": {**_cat_axis(categories), "inverse": True},
        "series": [
            {
                "name": "Delivered",
                "type": "bar",
                "stack": "ordered",
                "data": delivered,
                "barMaxWidth": 24,
                "itemStyle": {"color": STATUS_COLORS["completed"], "borderRadius": [7, 0, 0, 7]},
            },
            {
                "name": "Pending",
                "type": "bar",
                "stack": "ordered",
                "data": pending,
                "barMaxWidth": 24,
                "itemStyle": {"color": STATUS_COLORS["at_risk"], "borderRadius": [0, 7, 7, 0]},
            },
        ],
    }


def _display_name(db: Session, project_id: str) -> str:
    project = ProjectCatalogService.get_by_project_id(db, project_id)
    return project.display_name if project else project_id


def _semantic_transport(spec) -> dict | None:
    return spec.transport() if spec is not None else None


def _chart_from_semantic(spec) -> dict:
    payload = spec.transport()
    return {
        "schema_version": payload["schema_version"],
        "chart_type": payload["chart_type"],
        "title": payload["title"],
        "subtitle": payload.get("subtitle"),
        "summary": payload["summary"],
        "accessibility_description": payload["accessibility_description"],
        "data_points": len(payload["categories"]),
        "data_as_of": payload.get("data_as_of"),
        "data_table": payload.get("data_table") or [],
        "visualization_spec": payload,
        "option": {},
        "_source_tables": payload.get("source_tables") or [],
    }


def build_project_comparison_dashboard(db: Session, project_ids: list[str]) -> list[dict]:
    """Return one coordinated, unit-safe chart bundle for a project comparison."""
    data = ChartSpecService.project_comparison(db, project_ids)
    rows = data.get("projects") or []
    if len(rows) < 2:
        return []
    specs = [
        project_progress_spec(rows, title="Project Comparison — % Complete"),
        activity_composition_spec(rows),
        duration_comparison_spec(rows),
        baseline_slip_spec(rows),
    ]
    return [_chart_from_semantic(spec) for spec in specs if spec is not None][:4]


# ============================================
# Grounded chart builders (one per chart_type)
# ============================================

def _chart_activity_status(db: Session, project_id: str) -> dict:
    b = ChartSpecService.activity_status(db, project_id)
    breakdown = b.get("breakdown", {})
    if not breakdown:
        return _no_data("activity_status", f"No activity data found for {_display_name(db, project_id)}.")

    name = b.get("project_name", project_id)
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
        "option": _rose_option(f"{name} — Activity Status", f"{b.get('total', 0)} activities", data),
        "_source_tables": b["sources"],
    }


def _chart_project_comparison(db: Session, project_ids: list) -> dict:
    data = ChartSpecService.project_comparison(db, project_ids)
    rows = [(row["project_name"], row["progress_pct"]) for row in data["projects"]]
    if not rows:
        return _no_data("project_comparison", "None of the requested projects were found.")

    rows.sort(key=lambda r: r[1], reverse=True)
    categories = [r[0] for r in rows]
    values = [r[1] for r in rows]
    semantic = project_progress_spec(data["projects"], title="Project Comparison — % Complete")
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
        "visualization_spec": _semantic_transport(semantic),
        "summary": semantic.summary if semantic else None,
        "accessibility_description": semantic.accessibility_description if semantic else None,
        "data_table": semantic.data_table if semantic else [],
        "_source_tables": data["sources"],
    }


def _chart_delayed_activities(db: Session, project_id: str, limit: int = 12) -> dict:
    data = ChartSpecService.delayed_activities(db, project_id, limit)
    acts = data["activities"]
    if not acts:
        return _no_data("delayed_activities", f"No delayed activities found for {_display_name(db, project_id)}.")

    name = data["project_name"]
    categories = [
        str(a.get("name") or a.get("activity_id") or "Unnamed activity")[:40]
        for a in acts
    ]
    values = [a["drift_days"] for a in acts]
    # Color by severity: critical-path (float<=0) red, otherwise amber warning.
    colors_per_bar = [STATUS_COLORS["delayed"] if a.get("is_critical") else STATUS_COLORS["at_risk"] for a in acts]
    return {
        "chart_type": "delayed_activities",
        "title": f"{name} — Most Delayed Activities",
        "data_points": len(acts),
        "option": _lollipop_option(
            f"{name} — Most Delayed Activities",
            "days drifted from baseline finish",
            categories,
            values,
            colors_per_bar,
            value_formatter="{value}d",
        ),
        "_source_tables": data["sources"],
    }


def _chart_material_gaps(db: Session, project_id: str, limit: int = 12) -> dict:
    data = ChartSpecService.material_gaps(db, project_id, limit)
    gaps = data["rows"]
    if not gaps:
        return _no_data("material_gaps", f"No pending material gaps found for {_display_name(db, project_id)}.")

    name = data["project_name"]
    # Sort by pending descending so most critical gap is at the top
    gaps_sorted = sorted(gaps, key=lambda g: g.get("pending", 0), reverse=True)[:limit]
    categories = [g["name"][:40] for g in gaps_sorted]
    delivered = [g.get("delivered", 0) for g in gaps_sorted]
    pending  = [g.get("pending", 0) for g in gaps_sorted]
    return {
        "chart_type": "material_gaps",
        "title": f"{name} — Pending Material Deliveries",
        "data_points": len(gaps_sorted),
        "option": _fulfillment_option(
            f"{name} — Pending Material Deliveries",
            "ordered / delivered / pending quantity by material",
            categories,
            delivered,
            pending,
        ),
        "_source_tables": data["sources"],
    }


def _chart_vendor_performance(db: Session, project_id: str, limit: int = 8) -> dict:
    data = ChartSpecService.vendor_performance(db, project_id, limit)
    vendors = data["rows"]
    if not vendors:
        return _no_data("vendor_performance", f"No vendor/PO data found for {_display_name(db, project_id)}.")

    name = data["project_name"]
    categories = [v["name"][:32] for v in vendors]
    delivered = [v["delivered"] for v in vendors]
    pending = [v["pending"] for v in vendors]
    ordered = [v["ordered"] for v in vendors]
    return {
        "chart_type": "vendor_performance",
        "title": f"{name} — Vendor Delivery",
        "data_points": len(vendors),
        "option": _vertical_grouped_option(
            f"{name} — Vendor Delivery", "ordered vs delivered vs pending quantity by vendor",
            categories,
            [
                {"name": "Ordered",   "data": ordered,   "color": PALETTE[3]},
                {"name": "Delivered", "data": delivered, "color": STATUS_COLORS["completed"]},
                {"name": "Pending",   "data": pending,   "color": STATUS_COLORS["at_risk"]},
            ],
        ),
        "_source_tables": data["sources"],
    }


def _chart_sap_po_fulfillment(db: Session, project_id: str, limit: int = 12) -> dict:
    """SAP PO Fulfillment: ordered vs delivered vs pending grouped by material."""
    po = ChartSpecService.sap_po_fulfillment(db, project_id, limit)
    if not po["has_data"]:
        return _no_data("sap_po_fulfillment", f"No SAP PO data found for {_display_name(db, project_id)}.")

    name = po.get("project_name", project_id)
    mats = po["rows"]
    categories = [m["name"][:40] for m in mats]
    delivered = [m["delivered"] for m in mats]
    pending = [m["pending"] for m in mats]
    fulfill_pct = round(po.get("fulfillment_pct", 0), 1)
    return {
        "chart_type": "sap_po_fulfillment",
        "title": f"{name} — SAP PO Fulfillment",
        "data_points": len(mats),
        "option": _fulfillment_option(
            f"{name} — SAP PO Fulfillment",
            f"Overall fulfillment: {fulfill_pct}%  |  ordered / delivered / pending by material",
            categories,
            delivered,
            pending,
        ),
        "_source_tables": po["sources"],
    }


def _chart_transmission_status(db: Session, project_id: str = None) -> dict:
    t = ChartSpecService.transmission_status(db, project_id)
    if project_id:
        if not t.get("has_data"):
            return _no_data("transmission_status", f"No transmission lines mapped to {_display_name(db, project_id)}.")
        name = t.get("project_name", project_id)
        title = f"{name} — Transmission Line Status"
        total = t.get("total_lines", 0)
        buckets = [
            ("Completed", t.get("completed", 0), STATUS_COLORS["completed"]),
            ("In Progress", t.get("in_progress", 0), STATUS_COLORS["in_progress"]),
            ("Not Started", t.get("not_started", 0), STATUS_COLORS["not_started"]),
        ]
    else:
        total = t.get("total_lines", 0)
        delayed = t.get("delayed_lines", 0)
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
        "option": _rose_option(title, f"{total} lines", data),
        "_source_tables": t["sources"],
    }


def _chart_portfolio_risk(db: Session, limit: int = 8) -> dict:
    data = ChartSpecService.portfolio_risk(db, limit)
    projects = data["projects"]
    if not projects:
        return _no_data("portfolio_risk", "No portfolio project data available.")

    rows = [(project["project_name"], project["risk_level"]) for project in projects]
    subtitle = "named Project360 tier: Healthy 0, Watchlist 1, High Risk 2, Critical 3"

    categories = [x[0] for x in rows]
    values = [x[1] for x in rows]
    return {
        "chart_type": "portfolio_risk",
        "title": "Portfolio — Riskiest Projects",
        "data_points": len(rows),
        "option": _lollipop_option(
            "Portfolio — Riskiest Projects",
            subtitle,
            categories,
            values,
            [
                STATUS_COLORS["delayed"] if value >= 2 else STATUS_COLORS["at_risk"]
                for value in values
            ],
        ),
        "_source_tables": data["sources"],
    }


def _chart_daily_completion_trend(db: Session, project_id: str, days: int = 30) -> dict:
    data = ChartSpecService.daily_completion_trend(db, project_id, days)
    rows = data.get("daily") or []
    if not rows:
        return _no_data(
            "daily_completion_trend",
            f"No daily activity completion data found for {_display_name(db, project_id)}.",
        )

    semantic = daily_completion_spec(data, data.get("project_name"))

    name = data["project_name"]
    dates = [row["date"][5:] for row in rows]
    completed = [row["activities_completed"] for row in rows]
    cumulative = [row["cumulative_activity_finish_pct"] for row in rows]
    total_events = data.get("completion_events_in_period", 0)
    title = f"{name} — Daily Completion Trend"
    subtitle = (
        f"{total_events} activity actual-finish events • "
        f"{data.get('period_start')} to {data.get('period_end_inclusive')}"
    )
    option = {
        **_base_option(
            f"{title}. Bars show daily completed activities and the line shows cumulative "
            "activity finish percentage. This is event-based and is not historical duration progress."
        ),
        "title": {
            "text": title,
            "subtext": subtitle,
            "left": 18,
            "top": 10,
            "textStyle": {"color": "var(--foreground)", "fontSize": 15, "fontWeight": 700},
            "subtextStyle": {"color": "var(--muted-foreground)", "fontSize": 11},
        },
        "tooltip": {**_tooltip("axis"), "axisPointer": {"type": "cross"}},
        "legend": {
            "top": 58,
            "right": 18,
            "textStyle": {"color": "var(--foreground)", "fontSize": 11},
        },
        "grid": {"left": 46, "right": 54, "top": 94, "bottom": 52, "containLabel": True},
        "xAxis": {
            **_cat_axis(dates),
            "boundaryGap": True,
            "axisLabel": {
                "color": "var(--muted-foreground)",
                "hideOverlap": True,
            },
        },
        "yAxis": [
            {**_value_axis("{value}"), "name": "Activities", "minInterval": 1},
            {**_value_axis("{value}%"), "name": "Cumulative", "min": 0, "max": 100},
        ],
        "series": [
            {
                "name": "Completed activities",
                "type": "bar",
                "data": completed,
                "barMaxWidth": 18,
                "itemStyle": {"color": PALETTE[4], "borderRadius": [5, 5, 0, 0]},
            },
            {
                "name": "Cumulative activity finish",
                "type": "line",
                "yAxisIndex": 1,
                "data": cumulative,
                "smooth": 0.24,
                "symbol": "circle",
                "symbolSize": 6,
                "lineStyle": {"color": PALETTE[0], "width": 3},
                "itemStyle": {"color": PALETTE[0], "borderColor": "var(--card)", "borderWidth": 2},
                "areaStyle": {"color": PALETTE[0], "opacity": 0.08},
            },
        ],
    }
    latest_pct = next((value for value in reversed(cumulative) if value is not None), None)
    summary = (
        f"{total_events} activities recorded an actual finish during the period. "
        f"Cumulative activity finishes reached {latest_pct}% of project activities."
        if latest_pct is not None else
        f"{total_events} activities recorded an actual finish during the period."
    )
    return {
        "schema_version": "visualization.v1",
        "chart_type": "daily_completion_trend",
        "title": title,
        "subtitle": subtitle,
        "summary": summary,
        "accessibility_description": option["aria"]["description"],
        "data_points": len(rows),
        "data_as_of": data.get("data_as_of"),
        "data_table": [
            {
                "date": row["date"],
                "completed_activities": row["activities_completed"],
                "cumulative_activity_finish_pct": row["cumulative_activity_finish_pct"],
            }
            for row in rows
        ],
        "visualization_spec": _semantic_transport(semantic),
        "option": option,
        "_source_tables": data["sources"],
    }


def _chart_planned_vs_actual_progress(db: Session, project_id: str) -> dict:
    data = ChartSpecService.planned_vs_actual_progress(db, project_id)
    rows = data.get("timeline") or []
    if not rows:
        return _no_data(
            "planned_vs_actual_progress",
            f"No planned-versus-actual activity finish data found for {_display_name(db, project_id)}.",
        )

    semantic = planned_vs_actual_progress_spec(data, data.get("project_name"))
    title = f"{data['project_name']} - Planned vs Actual Activity Completion"
    subtitle = (
        "Cumulative activity finish S-curve through "
        f"{data.get('period_end_inclusive') or data.get('data_as_of') or 'latest P6 cutoff'}"
    )
    dates = [row["date"] for row in rows]
    planned = [row["planned_activity_finish_pct"] for row in rows]
    actual = [row["actual_activity_finish_pct"] for row in rows]
    option = {
        **_base_option(
            f"{title}. Lines compare cumulative planned activity finishes with recorded actual "
            "activity finishes. This is not historical duration-percent progress."
        ),
        "title": {
            "text": title,
            "subtext": subtitle,
            "left": 18,
            "top": 10,
            "textStyle": {"color": "var(--foreground)", "fontSize": 15, "fontWeight": 700},
            "subtextStyle": {"color": "var(--muted-foreground)", "fontSize": 11},
        },
        "tooltip": {**_tooltip("axis"), "axisPointer": {"type": "cross"}},
        "legend": {
            "top": 58,
            "right": 18,
            "textStyle": {"color": "var(--foreground)", "fontSize": 11},
        },
        "grid": {"left": 52, "right": 28, "top": 94, "bottom": 52, "containLabel": True},
        "xAxis": {
            **_cat_axis(dates),
            "boundaryGap": False,
            "axisLabel": {"color": "var(--muted-foreground)", "hideOverlap": True},
        },
        "yAxis": {
            **_value_axis("{value}%"),
            "name": "Cumulative activities",
            "min": 0,
            "max": 100,
        },
        "series": [
            {
                "name": "Planned activity finishes",
                "type": "line",
                "data": planned,
                "smooth": 0.2,
                "showSymbol": False,
                "lineStyle": {"color": PALETTE[0], "width": 3},
                "itemStyle": {"color": PALETTE[0]},
            },
            {
                "name": "Actual activity finishes",
                "type": "line",
                "data": actual,
                "smooth": 0.2,
                "showSymbol": False,
                "lineStyle": {"color": STATUS_COLORS["completed"], "width": 3},
                "itemStyle": {"color": STATUS_COLORS["completed"]},
                "areaStyle": {"color": STATUS_COLORS["completed"], "opacity": 0.06},
            },
        ],
    }
    planned_now = data["current_planned_activity_finish_pct"]
    actual_now = data["current_actual_activity_finish_pct"]
    variance = data["current_variance_pct_points"]
    direction = "ahead of" if variance > 0 else "behind" if variance < 0 else "equal to"
    summary = (
        f"Planned completion is {planned_now}% and actual completion is {actual_now}% as of the cutoff. "
        f"Actual is {abs(variance)} percentage points {direction} plan."
    )
    return {
        "schema_version": "visualization.v1",
        "chart_type": "planned_vs_actual_progress",
        "title": title,
        "subtitle": subtitle,
        "summary": summary,
        "accessibility_description": option["aria"]["description"],
        "data_points": len(rows),
        "data_as_of": data.get("data_as_of"),
        "data_table": semantic.data_table if semantic is not None else rows,
        "visualization_spec": _semantic_transport(semantic),
        "option": option,
        "_source_tables": data["sources"],
    }


def _chart_block_progress(db: Session, project_id: str, limit: int = 16) -> dict:
    data = ChartSpecService.block_progress(db, project_id)
    blocks = [
        row for row in (data.get("blocks") or [])
        if row.get("current_activity_completion_pct") is not None
    ]
    if not blocks:
        return _no_data("block_progress", f"No block progress data found for {_display_name(db, project_id)}.")

    semantic = block_progress_spec(data, data.get("project_name"), limit=limit)

    blocks.sort(key=lambda row: (-row["current_activity_completion_pct"], row["block"]))
    blocks = blocks[:limit]
    title = f"{data['project_name']} — Block Progress Snapshot"
    subtitle = f"Current average activity completion • data as of {data.get('data_as_of') or 'latest sync'}"
    categories = [row["block"] for row in blocks]
    values = [row["current_activity_completion_pct"] for row in blocks]
    bar_values = [
        {
            "value": value,
            "itemStyle": {
                "color": (
                    STATUS_COLORS["completed"] if value >= 75
                    else PALETTE[0] if value >= 40
                    else STATUS_COLORS["at_risk"]
                ),
                "borderRadius": [0, 6, 6, 0],
            },
        }
        for value in values
    ]
    option = _hbar_option(
        title,
        subtitle,
        categories,
        [{"name": "Average activity completion", "data": bar_values, "color": PALETTE[0]}],
        value_formatter="{value}%",
    )
    option["series"][0]["label"] = {
        "show": True,
        "position": "right",
        "formatter": "{c}%",
        "color": "var(--foreground)",
        "fontWeight": 600,
    }
    low = min(blocks, key=lambda row: row["current_activity_completion_pct"])
    high = max(blocks, key=lambda row: row["current_activity_completion_pct"])
    return {
        "schema_version": "visualization.v1",
        "chart_type": "block_progress",
        "title": title,
        "subtitle": subtitle,
        "summary": (
            f"{high['block']} is highest at {high['current_activity_completion_pct']}%; "
            f"{low['block']} is lowest at {low['current_activity_completion_pct']}%."
        ),
        "accessibility_description": option["aria"]["description"],
        "data_points": len(blocks),
        "data_as_of": data.get("data_as_of"),
        "data_table": [
            {
                "block": row["block"],
                "current_activity_completion_pct": row["current_activity_completion_pct"],
                "activities": row["activity_count"],
                "completed_this_month": row["completed_in_period"],
            }
            for row in blocks
        ],
        "visualization_spec": _semantic_transport(semantic),
        "option": option,
        "_source_tables": data["sources"],
    }


def _capacity_dashboard_charts(db: Session, project_id: str | None = None) -> list[dict]:
    data = (
        CapacityMilestoneService.get_project_status(db, project_id)
        if project_id else CapacityMilestoneService.get_portfolio_overview(db)
    )
    rows = data.get("projects") or []
    if not rows:
        return []
    scope_name = rows[0]["project_name"] if project_id and len(rows) == 1 else "Portfolio"
    freshness = (data.get("metadata") or {}).get("freshness") or {}
    data_as_of = freshness.get("data_as_of")
    sources = ["project_mapping", "p6_project", "p6_activity"]
    specs = []

    cod = round(sum(float(row.get("cod_mw") or 0) for row in rows), 2)
    trial = round(sum(float(row.get("tr_mw") or 0) for row in rows), 2)
    remaining = round(sum(float(row.get("remaining_capacity") or 0) for row in rows), 2)
    status_buckets = [
        ("COD", cod, "progress"),
        ("Trial Run", trial, "primary"),
        ("Remaining", remaining, "warning"),
    ]
    status_buckets = [item for item in status_buckets if item[1] > 0]
    if status_buckets:
        specs.append(VisualizationSpecV1(
            chart_id="capacity.status-mw",
            chart_type="capacity_status_mw",
            shape="donut",
            title=f"{scope_name} - Capacity Status",
            subtitle="COD precedence applied; capacity in MW",
            summary=f"{cod} MW is at COD, {trial} MW is at Trial Run, and {remaining} MW remains.",
            accessibility_description="Donut chart showing COD, Trial Run, and remaining capacity in MW.",
            categories=[item[0] for item in status_buckets],
            series=[VisualizationSeriesV1(
                name="Capacity",
                shape="donut",
                values=[item[1] for item in status_buckets],
                semantic_color="primary",
                value_format="decimal",
                item_semantic_colors=[item[2] for item in status_buckets],
            )],
            data_as_of=data_as_of,
            source_tables=sources,
            data_table=[{"status": item[0], "capacity_mw": item[1]} for item in status_buckets],
        ))

    if project_id and len(rows) == 1:
        blocks = rows[0].get("blocks") or []
        if blocks:
            specs.append(VisualizationSpecV1(
                chart_id="capacity.blocks",
                chart_type="capacity_blocks",
                shape="horizontal_bar",
                title=f"{scope_name} - Block Capacity",
                subtitle="Capacity and milestone state by block or WTG",
                summary=f"{len(blocks)} capacity blocks or WTGs are represented.",
                accessibility_description="Horizontal bars show capacity by block or WTG and milestone state.",
                categories=[str(row.get("block") or "Unknown") for row in blocks[:16]],
                series=[VisualizationSeriesV1(
                    name="Capacity",
                    shape="bar",
                    values=[row.get("capacity") for row in blocks[:16]],
                    semantic_color="primary",
                    value_format="decimal",
                    item_semantic_colors=[
                        "progress" if row.get("cod_status") == "Completed"
                        else "primary" if row.get("trial_run_status") == "Completed"
                        else "warning"
                        for row in blocks[:16]
                    ],
                )],
                x_axis_title="Capacity (MW)",
                data_as_of=data_as_of,
                source_tables=sources,
                data_table=blocks[:16],
            ))
    else:
        project_rows = [row for row in rows if float(row.get("total_capacity") or 0) > 0][:12]
        if project_rows:
            specs.append(VisualizationSpecV1(
                chart_id="capacity.projects",
                chart_type="capacity_by_project",
                shape="horizontal_bar",
                title="Portfolio - Capacity by Project",
                summary="Projects are ranked by mapped or calculated capacity.",
                accessibility_description="Horizontal bars compare project capacity in MW.",
                categories=[str(row["project_name"]) for row in project_rows],
                series=[VisualizationSeriesV1(
                    name="Capacity",
                    shape="bar",
                    values=[row.get("total_capacity") for row in project_rows],
                    semantic_color="primary",
                    value_format="decimal",
                )],
                x_axis_title="Capacity (MW)",
                data_as_of=data_as_of,
                source_tables=sources,
                data_table=project_rows,
            ))

    monthly = data.get("monthly_trends") or []
    if monthly:
        names = ["Solar COD", "Solar Trial Run", "Wind COD", "Wind Trial Run"]
        colors = ["progress", "primary", "teal", "warning"]
        specs.append(VisualizationSpecV1(
            chart_id="capacity.monthly-trend",
            chart_type="capacity_monthly_trend",
            shape="combo",
            title=f"{scope_name} - Cumulative Capacity Milestones",
            summary="Lines show independently accumulated COD and Trial Run capacity by month.",
            accessibility_description="Four lines show cumulative Solar and Wind COD and Trial Run capacity by month.",
            categories=[str(row["name"]) for row in monthly],
            series=[VisualizationSeriesV1(
                name=name,
                shape="line",
                values=[row.get(name) for row in monthly],
                semantic_color=color_name,
                value_format="decimal",
            ) for name, color_name in zip(names, colors)],
            y_axis_title="Cumulative capacity (MW)",
            data_as_of=data_as_of,
            source_tables=sources,
            data_table=monthly,
        ))

    financial_years = data.get("financial_years") or []
    if financial_years:
        specs.append(VisualizationSpecV1(
            chart_id="capacity.financial-year",
            chart_type="capacity_by_financial_year",
            shape="vertical_bar",
            title=f"{scope_name} - Capacity by Financial Year",
            summary="Grouped bars show milestone capacity allocated to each financial year.",
            accessibility_description="Grouped bars compare Solar and Wind COD and Trial Run capacity by financial year.",
            categories=[str(row["name"]) for row in financial_years],
            series=[
                VisualizationSeriesV1(name="Solar COD", shape="bar", values=[row["solar_cod"] for row in financial_years], semantic_color="progress"),
                VisualizationSeriesV1(name="Solar Trial Run", shape="bar", values=[row["solar_tr"] for row in financial_years], semantic_color="primary"),
                VisualizationSeriesV1(name="Wind COD", shape="bar", values=[row["wind_cod"] for row in financial_years], semantic_color="teal"),
                VisualizationSeriesV1(name="Wind Trial Run", shape="bar", values=[row["wind_tr"] for row in financial_years], semantic_color="warning"),
            ],
            y_axis_title="Capacity (MW)",
            data_as_of=data_as_of,
            source_tables=sources,
            data_table=financial_years,
        ))
    return [_chart_from_semantic(spec) for spec in specs[:4]]


def _quality_dashboard_charts(db: Session, project_id: str | None = None) -> list[dict]:
    if project_id:
        data = QualityAnalyticsService.project_status(db, project_id).to_dict()
        scope_name = data.get("project_name") or project_id
    else:
        data = QualityAnalyticsService.portfolio_overview(db).to_dict()
        scope_name = "Portfolio"
    if not data.get("available"):
        return []
    provenance = data.get("provenance") or {}
    data_as_of = provenance.get("data_as_of")
    sources = list(data.get("_sources_used") or ["pulse_nc", "pulse_rfi"])
    specs = []

    for kind, completed_key, open_key, total_key in (
        ("NC", "completed_ncs", "open_ncs", "total_ncs"),
        ("RFI", "rfis_completed", "open_rfis", "total_rfis"),
    ):
        completed = int(data.get(completed_key) or 0)
        opened = int(data.get(open_key) or 0)
        if completed + opened == 0:
            continue
        specs.append(VisualizationSpecV1(
            chart_id=f"quality.{kind.casefold()}-status",
            chart_type=f"quality_{kind.casefold()}_status",
            shape="donut",
            title=f"{scope_name} - {kind} Status",
            summary=f"{completed} of {int(data.get(total_key) or 0)} {kind}s are completed; {opened} remain open.",
            accessibility_description=f"Donut chart comparing completed and open {kind} records.",
            categories=["Completed", "Open"],
            series=[VisualizationSeriesV1(
                name=kind,
                shape="donut",
                values=[completed, opened],
                semantic_color="primary",
                value_format="integer",
                item_semantic_colors=["progress", "warning"],
            )],
            data_as_of=data_as_of,
            source_tables=sources,
            data_table=[{"status": "Completed", "count": completed}, {"status": "Open", "count": opened}],
        ))

    if project_id:
        blocks = data.get("blocks") or []
        usable = [row for row in blocks if int(row.get("open") or 0) > 0][:12]
        if usable:
            specs.append(VisualizationSpecV1(
                chart_id="quality.open-by-block",
                chart_type="quality_open_by_block",
                shape="horizontal_bar",
                title=f"{scope_name} - Open NCs by Work Area",
                summary="Work areas are ranked by open non-conformances.",
                accessibility_description="Horizontal bars compare open NC counts by work area.",
                categories=[str(row["name"]) for row in usable],
                series=[VisualizationSeriesV1(name="Open NCs", shape="bar", values=[row["open"] for row in usable], semantic_color="warning", value_format="integer")],
                x_axis_title="Open NCs",
                data_as_of=data_as_of,
                source_tables=sources,
                data_table=usable,
            ))
        score = data.get("quality_score")
        if score is not None:
            specs.append(VisualizationSpecV1(
                chart_id="quality.project-score",
                chart_type="quality_project_score",
                shape="radial_progress",
                title=f"{scope_name} - Quality Score",
                summary=f"The authoritative project quality score is {score} out of 100.",
                accessibility_description="Radial gauge showing the project quality score out of 100.",
                categories=[scope_name],
                series=[VisualizationSeriesV1(name="Quality score", shape="bar", values=[score], semantic_color="progress", value_format="percent")],
                data_as_of=data_as_of,
                source_tables=sources,
                data_table=[{"project": scope_name, "quality_score": score}],
            ))
    else:
        aging = data.get("aging") or {}
        if any(int(value or 0) > 0 for value in aging.values()):
            specs.append(VisualizationSpecV1(
                chart_id="quality.nc-aging",
                chart_type="quality_nc_aging",
                shape="vertical_bar",
                title="Portfolio - Open NC Aging",
                summary="Bars group open NCs into authoritative aging buckets.",
                accessibility_description="Vertical bars compare open NC counts by age bucket.",
                categories=list(aging.keys()),
                series=[VisualizationSeriesV1(name="Open NCs", shape="bar", values=list(aging.values()), semantic_color="warning", value_format="integer")],
                y_axis_title="Open NCs",
                data_as_of=data_as_of,
                source_tables=sources,
                data_table=[{"age_bucket": key, "count": value} for key, value in aging.items()],
            ))
        trends = data.get("trends") or []
        if trends:
            specs.append(VisualizationSpecV1(
                chart_id="quality.nc-trend",
                chart_type="quality_nc_trend",
                shape="combo",
                title="Portfolio - NC Creation and Closure Trend",
                summary="Lines compare NCs created and closed by month.",
                accessibility_description="Two lines compare monthly created and closed NC counts.",
                categories=[str(row["month"]) for row in trends],
                series=[
                    VisualizationSeriesV1(name="Created", shape="line", values=[row["created"] for row in trends], semantic_color="warning", value_format="integer"),
                    VisualizationSeriesV1(name="Closed", shape="line", values=[row["closed"] for row in trends], semantic_color="progress", value_format="integer"),
                ],
                y_axis_title="NC count",
                data_as_of=data_as_of,
                source_tables=sources,
                data_table=trends,
            ))
    return [_chart_from_semantic(spec) for spec in specs[:4]]


def _transmission_dashboard_charts(db: Session, project_id: str | None = None) -> list[dict]:
    data = ChartSpecService.transmission_status(db, project_id)
    lines = data.get("lines") or []
    scope_name = data.get("project_name") or "Portfolio"
    sources = list(data.get("sources") or ["tc_network_edge"])
    charts = []
    status = _chart_transmission_status(db, project_id)
    if not status.get("no_data"):
        charts.append(_finalize_chart(status))

    progress_rows = [row for row in lines if row.get("avg_progress") is not None]
    progress_rows.sort(key=lambda row: (-float(row["avg_progress"]), str(row.get("edge_id") or "")))
    progress_rows = progress_rows[:12]
    if progress_rows:
        charts.append(_chart_from_semantic(VisualizationSpecV1(
            chart_id="transmission.line-progress",
            chart_type="transmission_line_progress",
            shape="horizontal_bar",
            title=f"{scope_name} - Transmission Line Progress",
            summary="Lines are ranked by average foundation, erection, and stringing progress.",
            accessibility_description="Horizontal bars compare average physical progress by transmission line.",
            categories=[str(row.get("edge_id") or "Unknown") for row in progress_rows],
            series=[VisualizationSeriesV1(name="Average progress", shape="bar", values=[row["avg_progress"] for row in progress_rows], semantic_color="primary", value_format="percent")],
            x_axis_title="Average progress",
            source_tables=sources,
            data_table=progress_rows,
        )))
        charts.append(_chart_from_semantic(VisualizationSpecV1(
            chart_id="transmission.workstreams",
            chart_type="transmission_workstream_progress",
            shape="horizontal_bar",
            title=f"{scope_name} - Transmission Workstream Progress",
            summary="Grouped bars compare foundation, erection, and stringing completion by line.",
            accessibility_description="Grouped horizontal bars compare foundation, erection, and stringing progress for transmission lines.",
            categories=[str(row.get("edge_id") or "Unknown") for row in progress_rows],
            series=[
                VisualizationSeriesV1(name="Foundation", shape="bar", values=[row.get("foundation_pct") for row in progress_rows], semantic_color="neutral", value_format="percent"),
                VisualizationSeriesV1(name="Erection", shape="bar", values=[row.get("erection_pct") for row in progress_rows], semantic_color="primary", value_format="percent"),
                VisualizationSeriesV1(name="Stringing", shape="bar", values=[row.get("stringing_pct") for row in progress_rows], semantic_color="progress", value_format="percent"),
            ],
            x_axis_title="Progress",
            source_tables=sources,
            data_table=progress_rows,
        )))

    delayed = [row for row in lines if row.get("days_delayed") is not None and row["days_delayed"] > 0]
    delayed.sort(key=lambda row: (-row["days_delayed"], str(row.get("edge_id") or "")))
    delayed = delayed[:12]
    if delayed:
        charts.append(_chart_from_semantic(VisualizationSpecV1(
            chart_id="transmission.delays",
            chart_type="transmission_delay_ranking",
            shape="lollipop",
            title=f"{scope_name} - Delayed Transmission Lines",
            summary="Lines are ranked by the authoritative expected-versus-scheduled delay in days.",
            accessibility_description="Lollipop chart ranking transmission lines by delay days.",
            categories=[str(row.get("edge_id") or "Unknown") for row in delayed],
            series=[VisualizationSeriesV1(name="Delay", shape="bar", values=[row["days_delayed"] for row in delayed], semantic_color="critical", value_format="days")],
            x_axis_title="Delay (days)",
            source_tables=sources,
            data_table=delayed,
        )))
    return charts[:4]


def _portfolio_dashboard_charts(db: Session) -> list[dict]:
    ids = []
    seen = set()
    for project in ProjectCatalogService.list_projects(db):
        if project.project_id and project.project_id not in seen:
            seen.add(project.project_id)
            ids.append(project.project_id)
    data = ChartSpecService.project_comparison(db, ids)
    rows = data.get("projects") or []
    specs = []
    progress = project_progress_spec(rows, title="Portfolio - Project Progress")
    if progress is not None:
        specs.append(progress)
    counts = {"delayed": 0, "on_track": 0, "completed": 0, "p6_unavailable": max(0, len(ids) - len(rows))}
    for row in rows:
        schedule = ScheduleMetricsService.get_by_project_id(db, row["project_id"])
        if schedule.progress_pct is not None and schedule.progress_pct >= 100:
            counts["completed"] += 1
        elif schedule.is_delayed:
            counts["delayed"] += 1
        else:
            counts["on_track"] += 1
    status = portfolio_status_spec(counts)
    if status is not None:
        specs.append(status)
    charts = [_chart_from_semantic(spec) for spec in specs]
    risk = _chart_portfolio_risk(db, 10)
    if not risk.get("no_data"):
        charts.append(_finalize_chart(risk))
    charts.extend(_capacity_dashboard_charts(db)[:1])
    return charts[:4]


def build_show_me_dashboard(
    db: Session,
    *,
    project_id: str | None = None,
    project_ids: list[str] | None = None,
    domain_hint: str | None = None,
    days: int = 30,
    limit: int = 12,
) -> list[dict]:
    """Build a deterministic 3-4 panel dashboard for broad ``show me`` requests."""
    project_ids = list(project_ids or [])
    if len(project_ids) >= 2:
        return build_project_comparison_dashboard(db, project_ids)[:4]

    hint = (domain_hint or "").casefold()
    if not project_id and len(project_ids) == 1:
        project_id = project_ids[0]
    charts: list[dict] = []
    seen_types = set()

    def add(items):
        for chart in items:
            if len(charts) >= 4:
                return
            if not chart or chart.get("no_data"):
                continue
            finalized = _finalize_chart(chart)
            chart_type = finalized.get("chart_type")
            if chart_type in seen_types:
                continue
            seen_types.add(chart_type)
            charts.append(finalized)

    if project_id:
        if any(word in hint for word in ("procurement", "purchase", "material", "vendor", "inventory", "sap")):
            add([
                _chart_sap_po_fulfillment(db, project_id, limit),
                _chart_material_gaps(db, project_id, limit),
                _chart_vendor_performance(db, project_id, min(limit, 8)),
            ])
        elif any(word in hint for word in ("transmission", "grid", "line", "evacuation", "readiness", "tc")):
            add(_transmission_dashboard_charts(db, project_id))
        elif any(word in hint for word in ("capacity", "cod", "trial run", "mwac", "wtg")):
            add(_capacity_dashboard_charts(db, project_id))
        elif any(word in hint for word in ("quality", "non-conformance", "nonconformance", " rfi", " nc", "contractor")):
            add(_quality_dashboard_charts(db, project_id))
        elif any(word in hint for word in ("risk", "health", "exposure")):
            add([
                _chart_planned_vs_actual_progress(db, project_id),
                _chart_delayed_activities(db, project_id, limit),
            ])
            add(_transmission_dashboard_charts(db, project_id))
        else:
            add([
                _chart_planned_vs_actual_progress(db, project_id),
                _chart_activity_status(db, project_id),
                _chart_delayed_activities(db, project_id, limit),
                _chart_block_progress(db, project_id, limit),
            ])

        # Fill sparse domain dashboards with useful project context, never fabricated panels.
        add([
            _chart_planned_vs_actual_progress(db, project_id),
            _chart_activity_status(db, project_id),
            _chart_delayed_activities(db, project_id, limit),
            _chart_block_progress(db, project_id, limit),
            _chart_transmission_status(db, project_id),
        ])
        if len(charts) < 4:
            add(_capacity_dashboard_charts(db, project_id))
        if len(charts) < 4:
            add(_quality_dashboard_charts(db, project_id))
    else:
        if any(word in hint for word in ("transmission", "grid", "line", "evacuation", "readiness", "tc")):
            add(_transmission_dashboard_charts(db))
        elif any(word in hint for word in ("capacity", "cod", "trial run", "mwac", "wtg")):
            add(_capacity_dashboard_charts(db))
        elif any(word in hint for word in ("quality", "non-conformance", "nonconformance", " rfi", " nc", "contractor")):
            add(_quality_dashboard_charts(db))
        add(_portfolio_dashboard_charts(db))
        if len(charts) < 4:
            add(_capacity_dashboard_charts(db))
        if len(charts) < 4:
            add(_quality_dashboard_charts(db))
    return charts[:4]


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
    if "planned" in hint and "actual" in hint and "progress" in hint:
        return "planned_vs_actual_progress"
    if any(k in hint for k in ("daily", "day-by-day", "trend", "over time")):
        return "daily_completion_trend"
    if any(k in hint for k in ("block", "wbs", "phase-wise")):
        return "block_progress"
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
                project_ids: list = None, domain_hint: str = None, limit: int = 12,
                days: int = 30) -> dict:
    """Main entry point. Returns an ECharts spec dict grounded in real DB data, or a
    {no_data: True, message} dict the agent can relay honestly instead of an empty chart."""
    if chart_type == "auto":
        chart_type = recommend_chart_type(project_id, project_ids, domain_hint)

    try:
        if chart_type == "activity_status":
            if not project_id:
                return _no_data(chart_type, "This chart needs a specific project.")
            return _finalize_chart(_chart_activity_status(db, project_id))
        if chart_type == "project_comparison":
            ids = project_ids or ([project_id] if project_id else [])
            if len(ids) < 2:
                return _no_data(chart_type, "Project comparison needs at least two projects.")
            return _finalize_chart(_chart_project_comparison(db, ids))
        if chart_type == "delayed_activities":
            if not project_id:
                return _no_data(chart_type, "This chart needs a specific project.")
            return _finalize_chart(_chart_delayed_activities(db, project_id, limit))
        if chart_type == "material_gaps":
            if not project_id:
                return _no_data(chart_type, "This chart needs a specific project.")
            return _finalize_chart(_chart_material_gaps(db, project_id, limit))
        if chart_type == "vendor_performance":
            if not project_id:
                return _no_data(chart_type, "This chart needs a specific project.")
            return _finalize_chart(_chart_vendor_performance(db, project_id, limit))
        if chart_type == "sap_po_fulfillment":
            if not project_id:
                return _no_data(chart_type, "This chart needs a specific project.")
            return _finalize_chart(_chart_sap_po_fulfillment(db, project_id, limit))
        if chart_type == "transmission_status":
            return _finalize_chart(_chart_transmission_status(db, project_id))
        if chart_type == "portfolio_risk":
            return _finalize_chart(_chart_portfolio_risk(db, limit))
        if chart_type == "daily_completion_trend":
            if not project_id:
                return _no_data(chart_type, "This chart needs a specific project.")
            return _finalize_chart(_chart_daily_completion_trend(db, project_id, days))
        if chart_type == "planned_vs_actual_progress":
            if not project_id:
                return _no_data(chart_type, "This chart needs a specific project.")
            return _finalize_chart(_chart_planned_vs_actual_progress(db, project_id))
        if chart_type == "block_progress":
            if not project_id:
                return _no_data(chart_type, "This chart needs a specific project.")
            return _finalize_chart(_chart_block_progress(db, project_id, limit))
        return _no_data(chart_type, f"Unknown chart type '{chart_type}'. Available: {', '.join(CHART_TYPES)}.")
    except Exception as e:
        logger.error(f"build_chart({chart_type}) failed: {e}")
        return _no_data(chart_type, f"Chart generation failed: {e}")
