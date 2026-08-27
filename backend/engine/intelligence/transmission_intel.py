"""
Akasha Intelligence Engine — Transmission & Connectivity Intelligence

Analyzes TC network data to produce:
- Connectivity readiness scoring per project
- COD impact analysis (is transmission the binding constraint?)
- Network bottleneck identification
- SCD revision tracking
- Transmission-specific insights and next steps

Read-only: never modifies existing data.
"""

import logging
import json
from datetime import datetime, date
from collections import defaultdict
from sqlalchemy.orm import Session
from sqlalchemy import func, or_

import models

logger = logging.getLogger(__name__)


def _parse_pct(value) -> float:
    if value is None:
        return 0.0
    s = str(value).strip().replace('%', '')
    try:
        return float(s)
    except (ValueError, TypeError):
        return 0.0


def _parse_month_year(s: str) -> date | None:
    """Parse 'Mon-YY' format (e.g. 'Mar-27', 'Oct-26') to a date."""
    if not s or not isinstance(s, str):
        return None
    try:
        return datetime.strptime(s.strip(), "%b-%y").date()
    except (ValueError, TypeError):
        return None


def analyze_transmission(db: Session, ctx: dict) -> dict:
    """Full transmission & connectivity intelligence analysis."""
    mapping = ctx.get("mapping")
    project_name = ctx["project_name"]

    if not mapping:
        return {
            "has_data": False, "health_score": None,
            "insights": [], "next_steps": [],
        }

    # Query TC edges for this project
    conditions = [models.TcNetworkEdge.mapping_id == mapping.id]
    if mapping.project_id:
        conditions.append(models.TcNetworkEdge.projects.ilike(f"%{mapping.project_id}%"))

    # Get latest version of each edge
    subq = db.query(
        models.TcNetworkEdge.edge_id,
        func.max(models.TcNetworkEdge.upload_time).label('max_time')
    ).group_by(models.TcNetworkEdge.edge_id).subquery()

    edges = db.query(models.TcNetworkEdge).join(
        subq,
        (models.TcNetworkEdge.edge_id == subq.c.edge_id) &
        (models.TcNetworkEdge.upload_time == subq.c.max_time)
    ).filter(or_(*conditions)).all()

    if not edges:
        return {
            "has_data": False, "health_score": None,
            "insights": [{
                "severity": "info",
                "domain": "transmission",
                "title": f"No transmission line data for {project_name}",
                "description": "No TC network edges mapped to this project.",
                "impact": "Cannot assess grid connectivity readiness",
            }],
            "next_steps": [],
        }

    today = date.today()

    # ═══════════════════════════════════════════════════════
    # 1. LINE-BY-LINE ANALYSIS
    # ═══════════════════════════════════════════════════════
    total_lines = len(edges)
    charged = 0
    in_progress = 0
    not_started = 0
    delayed_lines = []
    line_details = []

    for e in edges:
        foundation_pct = _parse_pct(e.foundation)
        erection_pct = _parse_pct(e.erection)
        stringing_pct = _parse_pct(e.stringing)
        avg_progress = round((foundation_pct + erection_pct + stringing_pct) / 3, 1)

        status_norm = (e.normalized_status or e.status or "").lower()
        is_charged = 'charged' in status_norm or 'commission' in status_norm

        if is_charged:
            charged += 1
        elif avg_progress > 0:
            in_progress += 1
        else:
            not_started += 1

        # Delay detection
        scd_date = _parse_month_year(e.scd)
        expected_date = _parse_month_year(e.expected_date)
        charged_date_parsed = _parse_month_year(e.charged_date)
        delay_days = 0

        if expected_date and scd_date and expected_date > scd_date:
            delay_days = (expected_date - scd_date).days

        is_delayed = e.is_delayed or delay_days > 0

        line_info = {
            "edge_id": e.edge_id,
            "from": e.from_label or e.from_node,
            "to": e.to_label or e.to_node,
            "contractor": e.contractor,
            "voltage": e.voltage,
            "status": e.normalized_status or e.status,
            "is_charged": is_charged,
            "is_delayed": is_delayed,
            "foundation_pct": foundation_pct,
            "erection_pct": erection_pct,
            "stringing_pct": stringing_pct,
            "avg_progress": avg_progress,
            "scd": e.scd,
            "expected_date": e.expected_date,
            "charged_date": e.charged_date,
            "delay_days": delay_days,
        }
        line_details.append(line_info)

        if is_delayed and not is_charged:
            delayed_lines.append(line_info)

    delayed_lines.sort(key=lambda x: x["delay_days"], reverse=True)

    # ═══════════════════════════════════════════════════════
    # 2. CONNECTIVITY READINESS SCORE
    # ═══════════════════════════════════════════════════════
    readiness_pct = round(charged / max(total_lines, 1) * 100, 1)

    # ═══════════════════════════════════════════════════════
    # 3. COD IMPACT — Is transmission the binding constraint?
    # ═══════════════════════════════════════════════════════
    # Find the latest expected charge date among uncharged lines
    latest_expected = None
    binding_line = None

    for line in line_details:
        if not line["is_charged"]:
            exp = _parse_month_year(line["expected_date"])
            if exp and (latest_expected is None or exp > latest_expected):
                latest_expected = exp
                binding_line = line

    is_tc_binding = False
    tc_extends_cod_by = 0

    p6_proj = ctx.get("p6_project")
    if p6_proj and latest_expected and p6_proj.finish_date:
        construction_finish = p6_proj.finish_date.date() if isinstance(p6_proj.finish_date, datetime) else p6_proj.finish_date
        if latest_expected > construction_finish:
            is_tc_binding = True
            tc_extends_cod_by = (latest_expected - construction_finish).days

    # ═══════════════════════════════════════════════════════
    # 4. HEALTH SCORE
    # ═══════════════════════════════════════════════════════
    readiness_score = readiness_pct * 0.5
    delay_penalty = min(len(delayed_lines) * 10, 40)
    binding_penalty = 20 if is_tc_binding else 0
    health_score = round(max(0, min(100, readiness_score + 50 - delay_penalty - binding_penalty)), 1)

    # ═══════════════════════════════════════════════════════
    # 5. INSIGHTS
    # ═══════════════════════════════════════════════════════
    insights = []

    if is_tc_binding:
        insights.append({
            "severity": "critical",
            "domain": "transmission",
            "title": "Transmission is the BINDING CONSTRAINT — will delay COD",
            "description": f"Even if construction finishes on {p6_proj.finish_date.strftime('%Y-%m-%d') if p6_proj and p6_proj.finish_date else 'N/A'}, "
                          f"COD will be delayed by ~{tc_extends_cod_by} days because line "
                          f"'{binding_line['from']} → {binding_line['to']}' "
                          f"has expected charge date of {binding_line['expected_date']}",
            "impact": f"COD extended by {tc_extends_cod_by} days due to transmission delay",
            "evidence": {"binding_line": binding_line},
        })

    if delayed_lines:
        worst = delayed_lines[0]
        insights.append({
            "severity": "high" if len(delayed_lines) > 2 else "medium",
            "domain": "transmission",
            "title": f"{len(delayed_lines)} transmission lines are delayed",
            "description": f"Worst: '{worst['from']} → {worst['to']}' — "
                          f"{worst['delay_days']} days behind SCD ({worst['scd']} → {worst['expected_date']}). "
                          f"Contractor: {worst['contractor']}",
            "impact": "Delayed lines may block grid synchronization and commissioning",
        })

    if readiness_pct < 30:
        insights.append({
            "severity": "high",
            "domain": "transmission",
            "title": f"Only {readiness_pct}% of transmission lines charged",
            "description": f"{charged} of {total_lines} lines are charged. "
                          f"{in_progress} in progress, {not_started} not started.",
            "impact": "Low connectivity readiness creates commissioning risk",
        })

    # ═══════════════════════════════════════════════════════
    # 6. NEXT STEPS
    # ═══════════════════════════════════════════════════════
    next_steps = []

    if is_tc_binding and binding_line:
        next_steps.append({
            "priority": "P1",
            "category": "transmission",
            "action": f"Escalate line '{binding_line['from']} → {binding_line['to']}' — "
                      f"this is the COD binding constraint",
            "reason": f"Expected charge: {binding_line['expected_date']}. "
                      f"Current progress: Foundation {binding_line['foundation_pct']}%, "
                      f"Erection {binding_line['erection_pct']}%, "
                      f"Stringing {binding_line['stringing_pct']}%",
            "assigned_role": "tc_head",
        })

    if delayed_lines:
        for line in delayed_lines[:2]:
            if line["stringing_pct"] < 50:
                next_steps.append({
                    "priority": "P1",
                    "category": "transmission",
                    "action": f"Accelerate stringing on '{line['from']} → {line['to']}' "
                              f"(currently {line['stringing_pct']}%)",
                    "reason": f"Line is {line['delay_days']} days behind SCD. "
                              f"Contractor: {line['contractor']}",
                    "assigned_role": "tc_head",
                })

    return {
        "has_data": True,
        "health_score": health_score,

        "summary": {
            "total_lines": total_lines,
            "charged": charged,
            "in_progress": in_progress,
            "not_started": not_started,
            "delayed": len(delayed_lines),
            "readiness_pct": readiness_pct,
            "is_tc_binding_constraint": is_tc_binding,
            "tc_extends_cod_by_days": tc_extends_cod_by,
        },

        "line_details": line_details,
        "delayed_lines": delayed_lines,
        "binding_line": binding_line,

        "insights": insights,
        "next_steps": next_steps,
    }
