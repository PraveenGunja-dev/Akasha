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
from services.project_catalog_service import ProjectCatalogService
from services.visualization_spec import (
    activity_composition_spec,
    activity_status_spec,
    baseline_slip_spec,
    block_progress_spec,
    daily_completion_spec,
    duration_comparison_spec,
    planned_vs_actual_progress_spec,
    project_progress_spec,
)

logger = logging.getLogger(__name__)

# Adani logo colors lead the palette; tonal tints provide quiet extra series.
PALETTE = ["#0B74B0", "#75479C", "#BD3861", "#4B91BC", "#966EB5", "#CC6787"]

# Semantic status colors (reserved — never reused as a generic "series N" hue).
STATUS_COLORS = {
    "completed": "#75479C",
    "in_progress": "#0B74B0",
    "not_started": "#98A2B3",
    "delayed": "#B42318",
    "at_risk": "#BD3861",
}

# Chart types this engine can render, with the data shape each one fits.
CHART_TYPES = {
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
    "project_overview": "Coordinated four-chart executive overview for one project.",
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
            "decal": {"show": False},
            "description": accessibility_description,
        },
        "color": PALETTE,
        "textStyle": {"fontFamily": "Aptos, Avenir Next, Segoe UI, sans-serif"},
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
        "decal": {"show": False},
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


def build_project_overview_dashboard(db: Session, project_id: str) -> list[dict]:
    """Return a coordinated, decision-focused overview for one project."""
    comparison = ChartSpecService.project_comparison(db, [project_id])
    rows = comparison.get("projects") or []
    project_name = rows[0]["project_name"] if rows else _display_name(db, project_id)
    specs = [
        project_progress_spec(rows, title=f"{project_name} - Overall Progress"),
        planned_vs_actual_progress_spec(
            ChartSpecService.planned_vs_actual_progress(db, project_id), project_name
        ),
        activity_status_spec(ChartSpecService.activity_status(db, project_id), project_name),
        block_progress_spec(ChartSpecService.block_progress(db, project_id), project_name, limit=8),
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

    semantic = activity_status_spec(b, name)
    return {
        "chart_type": "activity_status",
        "title": f"{name} — Activity Status",
        "data_points": b.get("total", 0),
        "option": _rose_option(f"{name} — Activity Status", f"{b.get('total', 0)} activities", data),
        "visualization_spec": _semantic_transport(semantic),
        "summary": semantic.summary if semantic else None,
        "accessibility_description": semantic.accessibility_description if semantic else None,
        "data_table": semantic.data_table if semantic else [],
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
